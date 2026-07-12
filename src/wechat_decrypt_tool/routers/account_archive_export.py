import os
import re
import shutil
import stat
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..chat_helpers import _resolve_account_dir
from ..export_integrity import IntegrityZipWriter, write_zip_integrity_sidecars
from ..path_fix import PathFixRoute

router = APIRouter(route_class=PathFixRoute)


class AccountArchiveExportRequest(BaseModel):
    account: Optional[str] = Field(None, description="Account directory name. Defaults to the first available account.")
    output_dir: Optional[str] = Field(None, description="Absolute output directory. Defaults to output/exports/{account}.")
    include_databases: bool = Field(True, description="Whether to include decrypted database files.")
    include_resources: bool = Field(True, description="Whether to include resource folders.")
    file_name: Optional[str] = Field(None, description="Optional zip file name, with or without .zip.")


class AccountArchiveCancelled(Exception):
    pass


@dataclass(frozen=True)
class AccountArchiveFile:
    path: Path
    arcname: str
    kind: str
    size: int
    mtime: float
    mode: int


@dataclass
class AccountArchiveExportJob:
    export_id: str
    account: str = ""
    status: str = "queued"
    progress: int = 0
    message: str = "Waiting to start..."
    detail: str = ""
    error: str = ""
    zip_path: str = ""
    file_name: str = ""
    database_count: int = 0
    resource_file_count: int = 0
    total_bytes: int = 0
    processed_bytes: int = 0
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    cancel_requested: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "exportId": self.export_id,
            "account": self.account,
            "status": self.status,
            "progress": max(0, min(100, int(self.progress or 0))),
            "message": self.message,
            "detail": self.detail,
            "error": self.error,
            "zipPath": self.zip_path,
            "fileName": self.file_name,
            "databaseCount": int(self.database_count or 0),
            "resourceFileCount": int(self.resource_file_count or 0),
            "totalBytes": int(self.total_bytes or 0),
            "processedBytes": int(self.processed_bytes or 0),
            "createdAt": int(self.created_at or 0),
            "updatedAt": int(self.updated_at or 0),
            "cancelRequested": bool(self.cancel_requested),
        }


_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z._-]+")
# 账号归档以账号目录为边界。数据库通常在账号目录顶层，资源文件通常在子目录中。
_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".db3"}
_META_FILE_NAMES = {"_source.json", "_media_keys.json", "_sns_realtime_sync_state.json"}
_JOBS: dict[str, AccountArchiveExportJob] = {}
_JOBS_LOCK = threading.RLock()


def _safe_file_name(value: object, fallback: str) -> str:
    text = str(value or "").strip().replace("\\", "/").split("/")[-1]
    text = _SAFE_NAME_RE.sub("_", text).strip("._-")
    return text or fallback


def _normalize_zip_name(value: object, fallback: str) -> str:
    name = _safe_file_name(value, fallback)
    if not name.lower().endswith(".zip"):
        name += ".zip"
    return name


def _resolve_output_dir(account_dir: Path, output_dir_raw: object) -> Path:
    raw = str(output_dir_raw or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (account_dir.parents[1] / "exports" / account_dir.name).resolve()


def _iter_database_files(account_dir: Path) -> list[Path]:
    return sorted(
        (
            item
            for item in account_dir.iterdir()
            if item.is_file()
            and (
                item.suffix.lower() in _DB_SUFFIXES
                or item.name in _META_FILE_NAMES
            )
        ),
        key=lambda p: p.name.lower(),
    )


def _get_job(export_id: str) -> Optional[AccountArchiveExportJob]:
    key = str(export_id or "").strip()
    if not key:
        return None
    with _JOBS_LOCK:
        return _JOBS.get(key)


def _update_job(export_id: str, **changes: Any) -> Optional[AccountArchiveExportJob]:
    with _JOBS_LOCK:
        job = _JOBS.get(str(export_id or "").strip())
        if not job:
            return None
        for key, value in changes.items():
            if hasattr(job, key):
                setattr(job, key, value)
        job.updated_at = int(time.time())
        return job


def _check_cancel(job: AccountArchiveExportJob, tmp_path: Optional[Path] = None) -> None:
    with _JOBS_LOCK:
        cancelled = bool(job.cancel_requested)
    if not cancelled:
        return
    if tmp_path is not None:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
    raise AccountArchiveCancelled()


def _add_file(zip_file: zipfile.ZipFile, item: AccountArchiveFile) -> Optional[int]:
    try:
        modified = time.localtime(item.mtime)[:6]
        if modified[0] < 1980:
            modified = (1980, 1, 1, 0, 0, 0)
        info = zipfile.ZipInfo(item.arcname, modified)
        info.compress_type = zipfile.ZIP_STORED
        info.file_size = item.size
        info.external_attr = (item.mode & 0xFFFF) << 16
        with item.path.open("rb") as source, zip_file.open(info, "w", force_zip64=True) as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return int(item.size)
    except (FileNotFoundError, OSError):
        return None


def _is_database_or_meta_file(path: Path) -> bool:
    return path.is_file() and (path.suffix.lower() in _DB_SUFFIXES or path.name in _META_FILE_NAMES)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _iter_selected_account_files(
    *,
    job: AccountArchiveExportJob,
    account_dir: Path,
    include_databases: bool,
    include_resources: bool,
    tmp_path: Optional[Path],
    zip_path: Optional[Path],
    output_dir: Optional[Path],
):
    """Fast metadata scan for selected account files.

    Folder size is not stored as one reliable value by the filesystem. To show an
    accurate total before packing, we still have to enumerate files, but os.scandir
    reuses directory-entry metadata and avoids the heavier Path/os.walk/resolve path.
    """

    account_prefix = _safe_file_name(account_dir.name, "account")
    pack_whole_account_folder = include_databases and include_resources
    account_dir_str = os.path.abspath(os.fspath(account_dir))
    excluded_files = set()
    for candidate in (tmp_path, zip_path):
        if candidate is None:
            continue
        try:
            excluded_files.add(os.path.normcase(os.path.abspath(os.fspath(candidate))))
        except OSError:
            pass

    skipped_output_dir: Optional[str] = None
    if output_dir is not None:
        try:
            output_dir_str = os.path.abspath(os.fspath(output_dir))
            # 如果用户把导出目录选在账号目录内部，避免把正在生成的导出文件再次打包进去。
            if output_dir_str != account_dir_str and os.path.commonpath([account_dir_str, output_dir_str]) == account_dir_str:
                skipped_output_dir = os.path.normcase(output_dir_str)
        except (OSError, ValueError):
            skipped_output_dir = None

    stack: list[tuple[str, bool]] = [(account_dir_str, True)]
    while stack:
        root, is_account_root = stack.pop()
        _check_cancel(job, tmp_path)
        normalized_root = os.path.normcase(os.path.abspath(root))
        if skipped_output_dir is not None and normalized_root == skipped_output_dir:
            continue

        try:
            with os.scandir(root) as entries:
                entry_list = list(entries)
        except OSError:
            continue

        for entry in entry_list:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if is_account_root and not pack_whole_account_folder and not include_resources:
                        continue
                    stack.append((entry.path, False))
                    continue

                if not entry.is_file(follow_symlinks=False):
                    continue

                file_path_str = entry.path
                if os.path.normcase(os.path.abspath(file_path_str)) in excluded_files:
                    continue

                name = entry.name
                suffix = os.path.splitext(name)[1].lower()
                is_top_level_database = is_account_root and (suffix in _DB_SUFFIXES or name in _META_FILE_NAMES)
                if pack_whole_account_folder:
                    kind = "database" if is_top_level_database else "resource"
                elif include_databases and is_top_level_database:
                    kind = "database"
                elif include_resources and not is_account_root:
                    kind = "resource"
                else:
                    continue

                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue

                try:
                    rel = os.path.relpath(file_path_str, account_dir_str).replace(os.sep, "/")
                except ValueError:
                    continue

                yield AccountArchiveFile(
                    path=Path(file_path_str),
                    arcname=f"{account_prefix}/{rel}",
                    kind=kind,
                    size=int(st.st_size),
                    mtime=float(st.st_mtime),
                    mode=int(st.st_mode),
                )
            except OSError:
                continue

def _run_account_archive_export(export_id: str, payload: dict[str, Any]) -> None:
    job = _update_job(export_id, status="running", progress=1, message="Preparing export...", detail="")
    if not job:
        return

    zip_path: Optional[Path] = None
    tmp_path: Optional[Path] = None

    try:
        include_databases = bool(payload.get("include_databases"))
        include_resources = bool(payload.get("include_resources"))
        if not include_databases and not include_resources:
            raise ValueError("Please select at least one export option.")

        _check_cancel(job)
        account_dir = _resolve_account_dir(payload.get("account"))
        account_name = account_dir.name
        output_dir = _resolve_output_dir(account_dir, payload.get("output_dir"))
        output_dir.mkdir(parents=True, exist_ok=True)

        stamp = time.strftime("%Y%m%d_%H%M%S")
        fallback_name = f"wechat_archive_{_safe_file_name(account_name, 'account')}_{stamp}.zip"
        zip_name = _normalize_zip_name(payload.get("file_name"), fallback_name)
        zip_path = (output_dir / zip_name).resolve()
        tmp_path = zip_path.with_suffix(zip_path.suffix + ".tmp")

        _update_job(
            export_id,
            account=account_name,
            file_name=zip_name,
            zip_path=str(zip_path),
            progress=1,
            message="Scanning export content...",
            detail="Calculating total archive size.",
            total_bytes=0,
            processed_bytes=0,
        )

        if tmp_path.exists():
            tmp_path.unlink()

        selected_files = list(_iter_selected_account_files(
            job=job,
            account_dir=account_dir,
            include_databases=include_databases,
            include_resources=include_resources,
            tmp_path=tmp_path,
            zip_path=zip_path,
            output_dir=output_dir,
        ))
        if not selected_files:
            raise FileNotFoundError("No exportable files found for this account.")

        planned_db_count = sum(1 for item in selected_files if item.kind == "database")
        planned_resource_count = sum(1 for item in selected_files if item.kind != "database")
        total_files = len(selected_files)
        total_bytes = sum(max(0, int(item.size or 0)) for item in selected_files)
        if include_databases and not include_resources and planned_db_count <= 0:
            raise FileNotFoundError("No database files found for this account.")
        if include_resources and not include_databases and planned_resource_count <= 0:
            raise FileNotFoundError("No resource files found for this account.")

        _update_job(
            export_id,
            progress=5,
            database_count=planned_db_count,
            resource_file_count=planned_resource_count,
            total_bytes=total_bytes,
            processed_bytes=0,
            message="Writing ZIP archive...",
            detail=f"Ready to pack {total_files} files ({total_bytes / 1024 / 1024:.1f} MB).",
        )

        db_count = 0
        resource_file_count = 0
        processed_bytes = 0
        processed = 0
        last_progress_at = time.monotonic()

        # Use ZIP_STORED intentionally: account archives are mostly SQLite,
        # images, videos and cache files. Re-compressing them is CPU-heavy and
        # often saves little space. This makes archive export behave like a fast
        # folder pack/copy operation.
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as raw_zf:
            zf = IntegrityZipWriter(raw_zf)
            for item in selected_files:
                _check_cancel(job, tmp_path)
                added_size = _add_file(zf, item)
                if added_size is not None:
                    zf.add_file_entry(item.path, item.arcname)
                    processed += 1
                    if item.kind == "database":
                        db_count += 1
                    else:
                        resource_file_count += 1
                    processed_bytes += added_size

                now = time.monotonic()
                if processed <= 5 or processed % 20 == 0 or (now - last_progress_at) >= 0.5:
                    last_progress_at = now
                    if total_bytes > 0:
                        progress = min(95, 5 + int((processed_bytes / total_bytes) * 90))
                    else:
                        progress = min(95, 5 + int((processed / max(1, total_files)) * 90))
                    _update_job(
                        export_id,
                        progress=progress,
                        database_count=db_count,
                        resource_file_count=resource_file_count,
                        total_bytes=total_bytes,
                        processed_bytes=processed_bytes,
                        message="Writing ZIP archive...",
                        detail=(
                            f"Packed {processed}/{total_files} files "
                            f"({processed_bytes / 1024 / 1024:.1f}/{total_bytes / 1024 / 1024:.1f} MB)."
                        ),
                    )
            write_zip_integrity_sidecars(zf, export_id)

        _check_cancel(job, tmp_path)
        _update_job(export_id, progress=97, message="Finalizing ZIP archive...", detail="Moving archive to target folder.")
        if zip_path.exists():
            zip_path.unlink()
        shutil.move(str(tmp_path), str(zip_path))

        _update_job(
            export_id,
            status="done",
            progress=100,
            message="Export completed.",
            detail=f"Exported {db_count} database files and {resource_file_count} resource files.",
            database_count=db_count,
            resource_file_count=resource_file_count,
            total_bytes=total_bytes,
            processed_bytes=processed_bytes,
            zip_path=str(zip_path),
            file_name=zip_path.name,
        )
    except AccountArchiveCancelled:
        try:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        _update_job(export_id, status="cancelled", message="Export cancelled.", detail="Temporary archive has been removed.")
    except Exception as exc:
        try:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        _update_job(export_id, status="error", error=str(exc), message="Export failed.", detail="")


@router.post("/api/account/archive_export", summary="Create account archive export job")
async def export_account_archive(req: AccountArchiveExportRequest):
    if not req.include_databases and not req.include_resources:
        raise HTTPException(status_code=400, detail="Please select at least one export option.")

    payload = {
        "account": req.account,
        "output_dir": req.output_dir,
        "include_databases": bool(req.include_databases),
        "include_resources": bool(req.include_resources),
        "file_name": req.file_name,
    }
    export_id = uuid.uuid4().hex
    job = AccountArchiveExportJob(export_id=export_id)
    with _JOBS_LOCK:
        _JOBS[export_id] = job

    thread = threading.Thread(target=_run_account_archive_export, args=(export_id, payload), daemon=True)
    thread.start()
    return {"status": "success", "job": job.to_public_dict()}


@router.get("/api/account/archive_export/download", summary="Download account archive by file path")
async def download_account_archive(path: str):
    zip_path = Path(str(path or "").strip()).expanduser().resolve()
    if not zip_path.exists() or not zip_path.is_file():
        raise HTTPException(status_code=404, detail="Export file not found.")
    if zip_path.suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Invalid export file.")
    return FileResponse(str(zip_path), media_type="application/zip", filename=zip_path.name)


@router.get("/api/account/archive_export/{export_id}", summary="Get account archive export job")
async def get_account_archive_export(export_id: str):
    job = _get_job(export_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")
    return {"status": "success", "job": job.to_public_dict()}


@router.delete("/api/account/archive_export/{export_id}", summary="Cancel account archive export job")
async def cancel_account_archive_export(export_id: str):
    job = _get_job(export_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")

    with _JOBS_LOCK:
        if job.status in {"done", "error", "cancelled"}:
            return {"status": "success", "job": job.to_public_dict()}
        job.cancel_requested = True
        job.message = "Cancelling export..."
        job.detail = "Waiting for the current file operation to stop."
        job.updated_at = int(time.time())

    return {"status": "success", "job": job.to_public_dict()}
