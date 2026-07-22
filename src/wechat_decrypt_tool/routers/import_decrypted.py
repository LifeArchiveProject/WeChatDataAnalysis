from __future__ import annotations

import os
import shutil
import json
import hashlib
import re
import sqlite3
import asyncio
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..app_paths import get_data_dir, get_output_databases_dir
from ..logging_config import get_logger
from ..path_fix import PathFixRoute
from ..session_last_message import build_session_last_message_table
from ..media_helpers import _wxgf_to_image_bytes

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)

_IMPORT_CANCEL_EVENTS: dict[str, asyncio.Event] = {}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ImportCancelled(Exception):
    pass

class ImportRequest(BaseModel):
    import_path: str = Field(..., description="账号归档 ZIP 或已解密数据库目录的绝对路径")

def _is_valid_sqlite(path: Path) -> bool:
    SQLITE_HEADER = b"SQLite format 3\x00"
    try:
        if not path.exists() or not path.is_file():
            return False
        with path.open("rb") as f:
            return f.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except Exception:
        return False

def _clean_profile_text(value: object) -> str:
    text = str(value or "").replace("\u3164", "").strip()
    return text


def _validated_account_name(value: object) -> str:
    name = _clean_profile_text(value)
    reserved_base = name.rstrip(" .").split(".", 1)[0].upper()
    if (
        not name
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)
        or reserved_base in _WINDOWS_RESERVED_NAMES
    ):
        raise HTTPException(status_code=400, detail="账号标识不能安全地用作跨平台目录名")
    return name


def _pick_import_account_dir(import_path: Path) -> Path:
    """Resolve the actual account directory; supports selecting output root or wxid_xxx."""
    if (import_path / "databases").is_dir() or (import_path / "database").is_dir():
        return import_path
    if _is_valid_sqlite(import_path / "contact.db") and _is_valid_sqlite(import_path / "session.db"):
        return import_path
    account_dirs: list[Path] = []
    try:
        for child in import_path.iterdir():
            if child.is_dir() and (
                (child / "databases").is_dir()
                or (child / "database").is_dir()
                or (_is_valid_sqlite(child / "contact.db") and _is_valid_sqlite(child / "session.db"))
            ):
                account_dirs.append(child)
    except Exception:
        account_dirs = []
    if len(account_dirs) == 1:
        return account_dirs[0]
    if len(account_dirs) > 1:
        names = ", ".join(p.name for p in account_dirs[:5])
        raise HTTPException(status_code=400, detail=f"Multiple account directories found. Please select one account directory: {names}")
    return import_path


def _pick_database_dir(account_dir: Path) -> Path:
    """Support both this app's databases/ and wxdump's database/ directory names."""
    if _is_valid_sqlite(account_dir / "contact.db") and _is_valid_sqlite(account_dir / "session.db"):
        return account_dir
    for name in ("databases", "database"):
        db_dir = account_dir / name
        if db_dir.exists() and db_dir.is_dir():
            return db_dir
    raise HTTPException(status_code=400, detail="Missing databases or database directory")


def _pick_resource_dir(account_dir: Path) -> Optional[Path]:
    """Support both this app's resource/ and wxdump's media/ directory names."""
    for name in ("resource", "media"):
        resource_dir = account_dir / name
        if resource_dir.exists() and resource_dir.is_dir():
            return resource_dir
    return None


def _read_contact_profile(db_dir: Path, username: str) -> dict:
    """Best-effort account profile inference from contact.db."""
    contact_db = db_dir / "contact.db"
    if not _is_valid_sqlite(contact_db):
        return {}
    try:
        conn = sqlite3.connect(str(contact_db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("""
                SELECT username, remark, nick_name, alias, big_head_url, small_head_url
                FROM contact
                WHERE username = ?
                LIMIT 1
                """, (username,)).fetchone()
        finally:
            conn.close()
        if not row:
            return {}
        nick = _clean_profile_text(row["nick_name"]) or _clean_profile_text(row["remark"]) or _clean_profile_text(row["alias"]) or username
        return {"username": _clean_profile_text(row["username"]) or username, "nick": nick, "avatar_url": str(row["big_head_url"] or row["small_head_url"] or "").strip(), "alias": _clean_profile_text(row["alias"])}
    except Exception as e:
        logger.warning(f"Failed to read account profile from contact.db: {contact_db}, {e}")
        return {}


def _load_or_infer_account_info(account_dir: Path, db_dir: Path) -> tuple[dict, Optional[Path], bool]:
    """Read account.json; if missing in wxdump output, infer from folder name and contact.db."""
    account_json_path = account_dir / "account.json"
    if account_json_path.exists():
        try:
            account_info = json.loads(account_json_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse account.json: {e}")
        username = _clean_profile_text(account_info.get("username"))
        nick = _clean_profile_text(account_info.get("nick") or account_info.get("nickname"))
        if not username or not nick:
            raise HTTPException(status_code=400, detail="account.json is missing username or nick")
        account_info["username"] = _validated_account_name(username)
        account_info["nick"] = nick
        account_info.setdefault("avatar_url", "")
        return account_info, account_json_path, False
    inferred_username = _clean_profile_text(account_dir.name)
    if not inferred_username:
        raise HTTPException(status_code=400, detail="Missing account.json and cannot infer account from directory name")
    profile = _read_contact_profile(db_dir, inferred_username)
    username = _validated_account_name(_clean_profile_text(profile.get("username")) or inferred_username)
    nick = _clean_profile_text(profile.get("nick")) or _clean_profile_text(profile.get("alias")) or username
    return {"username": username, "nick": nick, "avatar_url": str(profile.get("avatar_url") or ""), "alias": str(profile.get("alias") or "")}, None, True


def _validate_import_structure(import_path: Path) -> dict:
    account_dir = _pick_import_account_dir(import_path)
    db_dir = _pick_database_dir(account_dir)
    resource_dir = _pick_resource_dir(account_dir)
    for db_name in ["contact.db", "session.db"]:
        if not _is_valid_sqlite(db_dir / db_name):
            raise HTTPException(status_code=400, detail=f"Missing valid {db_name} in {db_dir.name}")
    account_info, account_json_path, inferred_account = _load_or_infer_account_info(account_dir, db_dir)
    return {"username": account_info["username"], "nick": account_info["nick"], "avatar_url": account_info.get("avatar_url", ""), "alias": account_info.get("alias", ""), "has_resource": resource_dir is not None, "source_format": "wxdump" if db_dir.name == "database" or inferred_account else "wechat_data_analysis", "inferred_account": inferred_account, "account_dir": str(account_dir), "db_dir": str(db_dir), "resource_dir": str(resource_dir) if resource_dir else "", "account_json_path": str(account_json_path) if account_json_path else ""}


def _safe_zip_parts(name: str) -> tuple[str, ...]:
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or "\x00" in normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in path.parts)
    ):
        raise HTTPException(status_code=400, detail=f"Archive contains an unsafe path: {name}")
    return tuple(path.parts)


def _archive_file_map(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    result: dict[str, zipfile.ZipInfo] = {}
    casefold_names: set[str] = set()
    for item in archive.infolist():
        parts = _safe_zip_parts(item.filename)
        mode = (item.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise HTTPException(status_code=400, detail=f"Archive contains an unsupported symbolic link: {item.filename}")
        if item.flag_bits & 0x1:
            raise HTTPException(status_code=400, detail="Encrypted ZIP archives are not supported")
        if item.is_dir():
            continue
        normalized = "/".join(parts)
        folded = normalized.casefold()
        if normalized in result or folded in casefold_names:
            raise HTTPException(status_code=400, detail=f"Archive contains a duplicate path: {item.filename}")
        result[normalized] = item
        casefold_names.add(folded)
    return result


def _read_archive_json(archive: zipfile.ZipFile, files: dict[str, zipfile.ZipInfo], name: str) -> dict:
    item = files.get(name)
    if item is None:
        return {}
    try:
        payload = json.loads(archive.read(item).decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse {name}: {exc}") from exc


def _validate_import_archive(import_path: Path) -> dict:
    try:
        archive = zipfile.ZipFile(import_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ZIP archive: {exc}") from exc

    with archive:
        files = _archive_file_map(archive)
        database_parents: dict[str, set[str]] = {}
        for name in files:
            parts = PurePosixPath(name)
            if parts.suffix.lower() != ".db":
                continue
            database_parents.setdefault(str(parts.parent), set()).add(parts.name.lower())

        candidates = [
            parent
            for parent, names in database_parents.items()
            if {"contact.db", "session.db"}.issubset(names)
        ]
        if len(candidates) != 1:
            raise HTTPException(
                status_code=400,
                detail="Archive must contain exactly one account with valid contact.db and session.db",
            )

        db_prefix = candidates[0].strip("/")
        db_prefix_path = PurePosixPath(db_prefix)
        account_prefix_path = db_prefix_path.parent if db_prefix_path.name in {"databases", "database"} else db_prefix_path
        account_prefix = str(account_prefix_path).strip("/")
        if not account_prefix or account_prefix == ".":
            raise HTTPException(status_code=400, detail="Archive is missing an account directory")

        for required_name in ("contact.db", "session.db"):
            item = files.get(f"{db_prefix}/{required_name}")
            if item is None:
                raise HTTPException(status_code=400, detail=f"Archive is missing {required_name}")
            with archive.open(item, "r") as stream:
                if stream.read(16) != b"SQLite format 3\x00":
                    raise HTTPException(status_code=400, detail=f"Archive contains an invalid {required_name}")

        account_json_name = f"{account_prefix}/account.json"
        account_info = _read_archive_json(archive, files, account_json_name)
        inferred_username = account_prefix_path.name
        username = _validated_account_name(_clean_profile_text(account_info.get("username")) or inferred_username)
        nick = _clean_profile_text(account_info.get("nick") or account_info.get("nickname")) or username
        if not username:
            raise HTTPException(status_code=400, detail="Archive account name is empty")

        db_count = sum(1 for name in files if name.startswith(db_prefix + "/") and name.lower().endswith(".db"))
        resource_prefix = f"{account_prefix}/resource/"
        integrity_present = "_integrity/manifest.wce" in files
        return {
            "username": username,
            "nick": nick,
            "avatar_url": str(account_info.get("avatar_url") or ""),
            "alias": str(account_info.get("alias") or ""),
            "has_resource": any(name.startswith(resource_prefix) for name in files),
            "source_format": "wechat_data_analysis_archive",
            "inferred_account": not bool(account_info),
            "account_dir": "",
            "db_dir": "",
            "resource_dir": "",
            "account_json_path": "",
            "archive_path": str(import_path),
            "archive_account_prefix": account_prefix,
            "archive_db_prefix": db_prefix,
            "incoming_db_count": db_count,
            "integrity_present": integrity_present,
        }


def _validate_import_source(import_path: Path) -> dict:
    if import_path.is_file():
        if import_path.suffix.lower() != ".zip":
            raise HTTPException(status_code=400, detail="Import file must be a ZIP account archive")
        return _validate_import_archive(import_path)
    if import_path.is_dir():
        return _validate_import_structure(import_path)
    raise HTTPException(status_code=400, detail="Import path does not exist")


def _count_db_files(db_dir: Path) -> int:
    try:
        return sum(1 for f in db_dir.iterdir() if f.is_file() and f.suffix.lower() == ".db")
    except Exception:
        return 0


def _is_dir_nonempty(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except Exception:
        return False


def _paths_overlap(a: Path, b: Path) -> bool:
    try:
        ar = a.resolve()
        br = b.resolve()
    except Exception:
        ar = a.absolute()
        br = b.absolute()
    return ar == br or ar in br.parents or br in ar.parents


def _build_target_state(info: dict) -> dict:
    output_base = get_output_databases_dir()
    account_name = str(info.get("username") or "").strip()
    target_dir = output_base / account_name if account_name else output_base
    resource_dir = target_dir / "resource"
    db_files: list[str] = []
    try:
        if target_dir.exists() and target_dir.is_dir():
            db_files = sorted(f.name for f in target_dir.iterdir() if f.is_file() and f.suffix.lower() == ".db")
    except Exception:
        db_files = []
    paths = [Path(str(info.get("account_dir") or "")), Path(str(info.get("db_dir") or ""))]
    if info.get("resource_dir"):
        paths.append(Path(str(info.get("resource_dir"))))
    archive_source = bool(info.get("archive_path"))
    incoming_db_count = (
        int(info.get("incoming_db_count") or 0)
        if archive_source
        else _count_db_files(Path(str(info.get("db_dir") or "")))
    )
    return {"target_dir": str(target_dir), "target_exists": target_dir.exists(), "target_nonempty": _is_dir_nonempty(target_dir), "existing_db_count": len(db_files), "existing_db_files": db_files[:50], "incoming_db_count": incoming_db_count, "target_has_resource": resource_dir.exists(), "will_replace_resource": bool(resource_dir.exists() and (info.get("resource_dir") or archive_source)), "source_overlaps_target": False if archive_source else any(_paths_overlap(x, target_dir) for x in paths if str(x))}


def _archive_manifest_hashes(archive: zipfile.ZipFile, files: dict[str, zipfile.ZipInfo]) -> dict[str, str]:
    item = files.get("_integrity/manifest.wce")
    if item is None:
        return {}
    try:
        manifest = json.loads(archive.read(item).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"归档完整性清单无法解析: {exc}") from exc
    entries = manifest.get("f") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("归档完整性清单缺少文件列表")
    result: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = "/".join(_safe_zip_parts(str(entry.get("path") or "")))
        digest = str(entry.get("sha256") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"归档完整性清单包含无效哈希: {name}")
        if name in result:
            raise RuntimeError(f"归档完整性清单包含重复文件: {name}")
        result[name] = digest
    return result


def _extract_import_archive(import_path: Path, destination: Path, check_cancel) -> None:
    with zipfile.ZipFile(import_path, "r") as archive:
        files = _archive_file_map(archive)
        expected_hashes = _archive_manifest_hashes(archive, files)
        if expected_hashes:
            unsigned = sorted(name for name in files if not name.startswith("_integrity/") and name not in expected_hashes)
            if unsigned:
                raise RuntimeError(f"归档包含未登记到完整性清单的文件: {unsigned[0]}")
        verified_names: set[str] = set()
        for name, item in files.items():
            check_cancel()
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(item, "r") as source, target.open("wb") as output:
                while True:
                    check_cancel()
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
            expected = expected_hashes.get(name)
            if expected and digest.hexdigest() != expected:
                raise RuntimeError(f"归档文件校验失败: {name}")
            if expected:
                verified_names.add(name)
        missing = sorted(set(expected_hashes) - verified_names)
        if missing:
            raise RuntimeError(f"归档完整性清单中的文件缺失: {missing[0]}")


def _copy_supplemental_account_entries(info: dict, destination: Path) -> None:
    account_source = Path(str(info.get("account_dir") or ""))
    db_source = Path(str(info.get("db_dir") or ""))
    resource_source = Path(str(info.get("resource_dir") or "")) if info.get("resource_dir") else None
    if not account_source.is_dir():
        return

    excluded_names = {"account.json", "_source.json"}
    for item in account_source.iterdir():
        if item.name in excluded_names or item == db_source or (resource_source is not None and item == resource_source):
            continue
        if item.is_file() and item.suffix.lower() == ".db":
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True, symlinks=False)
        elif item.is_file():
            shutil.copy2(item, target)


def _next_backup_dir(account_output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = account_output_dir.with_name(f"{account_output_dir.name}.backup-{stamp}")
    candidate = base
    i = 1
    while candidate.exists():
        candidate = account_output_dir.with_name(f"{base.name}-{i}")
        i += 1
    return candidate


def _backup_existing_account_dir(account_output_dir: Path) -> Optional[Path]:
    if not account_output_dir.exists():
        return None
    backup_dir = _next_backup_dir(account_output_dir)
    shutil.move(str(account_output_dir), str(backup_dir))
    return backup_dir


def _rollback_account_backup(account_output_dir: Path, backup_dir: Optional[Path]) -> None:
    if not backup_dir or not backup_dir.exists():
        return
    if account_output_dir.exists():
        if account_output_dir.is_symlink() or account_output_dir.is_file():
            account_output_dir.unlink()
        else:
            shutil.rmtree(account_output_dir)
    shutil.move(str(backup_dir), str(account_output_dir))


def _remove_path(path: Optional[Path]) -> None:
    if path is None or not path.exists():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _install_staged_account(staging_dir: Path, account_output_dir: Path) -> Optional[Path]:
    backup_dir = _backup_existing_account_dir(account_output_dir)
    try:
        shutil.move(str(staging_dir), str(account_output_dir))
    except Exception:
        _rollback_account_backup(account_output_dir, backup_dir)
        raise
    return backup_dir


@router.post("/api/import_decrypted/preview", summary="预览待导入的账号信息")
async def preview_import(request: ImportRequest):
    import_path = Path(request.import_path.strip())
    if not import_path.exists():
        raise HTTPException(status_code=400, detail="导入路径不存在")
        
    info = _validate_import_source(import_path)
    info.update(_build_target_state(info))
    return info

@router.post("/api/import_decrypted/cancel", summary="取消正在执行的导入任务")
async def cancel_import_decrypted(job_id: str = Query(..., description="导入任务 ID")):
    cancel_event = _IMPORT_CANCEL_EVENTS.get(str(job_id or ""))
    if cancel_event:
        cancel_event.set()
        return {"status": "cancel_requested"}
    return {"status": "not_found"}

@router.get("/api/import_decrypted", summary="执行导入已解密的数据库和资源目录 (SSE)")
async def import_decrypted_directory(
    import_path: str = Query(..., description="已解密的数据库和资源所在目录的绝对路径"),
    job_id: str = Query("", description="导入任务 ID，用于取消导入")
):
    import_path_obj = Path(import_path.strip())
    account_output_dir: Optional[Path] = None
    staging_output_dir: Optional[Path] = None
    backup_dir: Optional[Path] = None
    backup_restored = False
    archive_temp_dir: Optional[tempfile.TemporaryDirectory] = None
    job_key = str(job_id or "").strip()
    cancel_event: Optional[asyncio.Event] = None
    if job_key:
        cancel_event = _IMPORT_CANCEL_EVENTS.setdefault(job_key, asyncio.Event())
        cancel_event.clear()
    
    def _sse(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise ImportCancelled("用户已取消导入")

    async def generate_progress():
        nonlocal account_output_dir, staging_output_dir, backup_dir, backup_restored, archive_temp_dir
        try:
            if not import_path_obj.exists():
                yield _sse({"type": "error", "message": "导入路径不存在"})
                return

            yield _sse({"type": "progress", "percent": 5, "message": "正在验证目录结构..."})
            import_source = import_path_obj
            archive_source = import_path_obj.is_file()
            if archive_source:
                if import_path_obj.suffix.lower() != ".zip":
                    yield _sse({"type": "error", "message": "导入文件必须是 ZIP 账号归档"})
                    return
                temp_root = get_data_dir() / "import-tmp"
                await asyncio.to_thread(temp_root.mkdir, parents=True, exist_ok=True)
                archive_temp_dir = tempfile.TemporaryDirectory(prefix="account-archive-", dir=temp_root)
                yield _sse({"type": "progress", "percent": 7, "message": "正在校验并解压账号归档..."})
                await asyncio.to_thread(
                    _extract_import_archive,
                    import_path_obj,
                    Path(archive_temp_dir.name),
                    _check_cancel,
                )
                import_source = Path(archive_temp_dir.name)

            # 1. 验证并获取账号信息
            try:
                info = await asyncio.to_thread(_validate_import_structure, import_source)
                if archive_source:
                    info["source_format"] = "wechat_data_analysis_archive"
                    info["archive_path"] = str(import_path_obj)
            except HTTPException as e:
                yield _sse({"type": "error", "message": e.detail})
                return
            except Exception as e:
                yield _sse({"type": "error", "message": f"验证失败: {e}"})
                return
            
            _check_cancel()
            info.update(_build_target_state(info))
            if info.get("source_overlaps_target"):
                yield _sse({"type": "error", "message": "导入源目录与目标数据目录相同或相互包含，请选择外部备份目录。"})
                return

            account_name = info["username"]
            yield _sse({"type": "progress", "percent": 10, "message": f"验证成功：{account_name}"})
            
            # 2. 先写入同盘临时目录，全部成功后再替换正式账号目录。
            output_base = get_output_databases_dir()
            await asyncio.to_thread(output_base.mkdir, parents=True, exist_ok=True)
            account_output_dir = output_base / account_name
            staging_output_dir = Path(
                await asyncio.to_thread(
                    tempfile.mkdtemp,
                    prefix=f".{account_name}.import-",
                    dir=output_base,
                )
            )

            yield _sse({"type": "progress", "percent": 15, "message": "正在准备目标目录..."})

            # 3. 导入 databases 目录下的 .db 文件
            db_src_dir = Path(info["db_dir"])
            db_files = [f for f in db_src_dir.iterdir() if f.is_file() and f.suffix == ".db"]
            imported_files = []
            
            for i, item in enumerate(db_files):
                _check_cancel()
                target = staging_output_dir / item.name
                def _do_import_db(src, dst):
                    if dst.exists():
                        dst.unlink()
                    try:
                        os.link(src, dst)
                    except Exception:
                        shutil.copy2(src, dst)
                
                try:
                    await asyncio.to_thread(_do_import_db, item, target)
                    imported_files.append(item.name)
                except Exception as e:
                    logger.error(f"导入数据库失败: {item.name}, error: {e}")
                    raise RuntimeError(f"导入数据库失败: {item.name}: {e}") from e
                
                percent = 15 + int((i + 1) / (len(db_files) or 1) * 15)
                yield _sse({"type": "progress", "percent": percent, "message": f"正在导入数据库: {item.name}"})

            # 4. 导入 resource 目录
            resource_src = Path(info["resource_dir"]) if info.get("resource_dir") else None
            if resource_src and resource_src.exists() and resource_src.is_dir():
                yield _sse({"type": "progress", "percent": 30, "message": "正在导入资源文件 (这可能需要一些时间)..."})
                resource_dst = staging_output_dir / "resource"
                
                def _reset_resource_dst(dst: Path) -> None:
                    if dst.exists():
                        if dst.is_symlink() or dst.is_file():
                            dst.unlink()
                        else:
                            shutil.rmtree(dst)

                def _try_link_resource(src: Path, dst: Path) -> bool:
                    try:
                        os.symlink(src, dst, target_is_directory=True)
                        return True
                    except Exception:
                        return False

                def _collect_resource_files(src: Path) -> list[tuple[Path, Path]]:
                    files: list[tuple[Path, Path]] = []
                    for root, _, names in os.walk(src):
                        root_path = Path(root)
                        for name in names:
                            file_path = root_path / name
                            try:
                                if file_path.is_file():
                                    files.append((file_path, file_path.relative_to(src)))
                            except Exception:
                                continue
                    return files

                def _copy_resource_batch(batch: list[tuple[Path, Path]], dst_root: Path) -> int:
                    copied = 0
                    for src_file, rel_path in batch:
                        dst_file = dst_root / rel_path
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        copied += 1
                    return copied

                try:
                    prefer_copy_resource = info.get("source_format") in {"wxdump", "wechat_data_analysis_archive"}
                    await asyncio.to_thread(_reset_resource_dst, resource_dst)

                    if not prefer_copy_resource:
                        linked = await asyncio.to_thread(_try_link_resource, resource_src, resource_dst)
                        if linked:
                            yield _sse({"type": "progress", "percent": 48, "message": "资源目录已通过快捷链接导入。"})
                        else:
                            prefer_copy_resource = True

                    if prefer_copy_resource:
                        yield _sse({"type": "progress", "percent": 31, "message": "正在扫描资源文件数量..."})
                        resource_files = await asyncio.to_thread(_collect_resource_files, resource_src)
                        total_resources = len(resource_files)
                        if total_resources <= 0:
                            await asyncio.to_thread(resource_dst.mkdir, parents=True, exist_ok=True)
                            yield _sse({"type": "progress", "percent": 48, "message": "资源目录为空，已跳过资源复制。"})
                        else:
                            await asyncio.to_thread(resource_dst.mkdir, parents=True, exist_ok=True)
                            batch_size = 300
                            copied_resources = 0
                            for batch_start in range(0, total_resources, batch_size):
                                _check_cancel()
                                batch = resource_files[batch_start:batch_start + batch_size]
                                copied_resources += await asyncio.to_thread(_copy_resource_batch, batch, resource_dst)
                                percent = 31 + int(min(copied_resources, total_resources) / total_resources * 17)
                                yield _sse({
                                    "type": "progress",
                                    "percent": min(percent, 48),
                                    "message": f"正在复制资源文件：{copied_resources}/{total_resources}"
                                })
                except Exception as e:
                    logger.error(f"导入 resource 目录失败: {e}")
                    raise RuntimeError(f"导入资源目录失败: {e}") from e
                
                # 5. 转换 .wxgf 资源 (新增加的流程)
                yield _sse({"type": "progress", "percent": 50, "message": "正在搜索并转换 .wxgf 图片..."})
                
                if resource_dst.exists():
                    # 搜索 wxgf 文件
                    def _find_wxgf(root_dir):
                        found = []
                        for root, _, files in os.walk(root_dir):
                            for f in files:
                                if f.lower().endswith(".wxgf"):
                                    found.append(Path(root) / f)
                        return found
                    
                    wxgf_files = await asyncio.to_thread(_find_wxgf, resource_dst)
                    
                    if wxgf_files:
                        total_wxgf = len(wxgf_files)
                        converted_count = 0
                        for i, wxgf_path in enumerate(wxgf_files):
                            _check_cancel()
                            def _convert_one(p):
                                jpg_p = p.with_suffix(".wxgf.jpg")
                                if not jpg_p.exists():
                                    data = p.read_bytes()
                                    if data.startswith(b"wxgf"):
                                        converted = _wxgf_to_image_bytes(data)
                                        if converted:
                                            jpg_p.write_bytes(converted)
                                            return True
                                else:
                                    return True # 已经存在视为成功
                                return False

                            try:
                                success = await asyncio.to_thread(_convert_one, wxgf_path)
                                if success:
                                    converted_count += 1
                            except Exception as e:
                                logger.error(f"转换 wxgf 失败: {wxgf_path}, {e}")
                            
                            if i % max(1, total_wxgf // 20) == 0 or i == total_wxgf - 1:
                                progress_val = 50 + int((i + 1) / total_wxgf * 30)
                                yield _sse({"type": "progress", "percent": progress_val, "message": f"转换 wxgf 图片: {i+1}/{total_wxgf}"})
                        
                        logger.info(f"账号 {account_name} 转换完成: {converted_count}/{total_wxgf} 个 .wxgf 文件")
                
            # 6. Copy metadata and all additional account resources (sns_resource, caches, media keys, ...).
            await asyncio.to_thread(_copy_supplemental_account_entries, info, staging_output_dir)

            # 7. Copy or generate account.json
            def _write_imported_account_json(dst: Path, info: dict) -> None:
                src = Path(str(info.get("account_json_path") or ""))
                target = dst / "account.json"
                if src.exists() and src.is_file():
                    shutil.copy2(src, target)
                    return
                payload = {
                    "username": info.get("username") or dst.name,
                    "nick": info.get("nick") or info.get("username") or dst.name,
                    "avatar_url": info.get("avatar_url") or "",
                    "alias": info.get("alias") or "",
                    "generated_by": "manual_import",
                    "source_format": info.get("source_format") or "unknown",
                }
                target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            yield _sse({"type": "progress", "percent": 85, "message": "正在更新账号配置..."})
            await asyncio.to_thread(_write_imported_account_json, staging_output_dir, info)

            # 8. 保存来源信息
            def _save_source_info(dst, path, info):
                (dst / "_source.json").write_text(
                    json.dumps(
                        {
                            "db_storage_path": str(path), 
                            "import_mode": "manual_import", 
                            "imported_at": __import__('datetime').datetime.now().isoformat(),
                            "original_info": info
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            try:
                source_path = import_path_obj if archive_source else Path(info.get("account_dir") or import_path_obj)
                await asyncio.to_thread(_save_source_info, staging_output_dir, source_path, info)
            except Exception:
                pass

            # 9. 构建缓存
            yield _sse({"type": "progress", "percent": 90, "message": "正在构建会话缓存 (这可能需要较长时间)..."})
            try:
                await asyncio.to_thread(
                    build_session_last_message_table,
                    staging_output_dir,
                    rebuild=True,
                    include_hidden=True,
                    include_official=True,
                )
            except Exception as e:
                logger.error(f"构建会话缓存失败: {e}")

            _check_cancel()
            if account_output_dir.exists():
                yield _sse({"type": "progress", "percent": 96, "message": "正在备份旧账号数据并切换到新归档..."})
            else:
                yield _sse({"type": "progress", "percent": 96, "message": "正在启用导入的账号数据..."})
            backup_dir = await asyncio.to_thread(_install_staged_account, staging_output_dir, account_output_dir)
            staging_output_dir = None

            yield _sse({
                "type": "complete",
                "status": "success",
                "account": account_name,
                "nick": info["nick"],
                "message": f"成功导入账号 {info['nick']} ({account_name})",
                "backup_dir": str(backup_dir) if backup_dir else ""
            })

        except ImportCancelled:
            try:
                await asyncio.to_thread(_remove_path, staging_output_dir)
            except Exception as rollback_error:
                logger.error(f"取消导入后清理临时目录失败: {rollback_error}", exc_info=True)
            suffix = "，已恢复导入前备份" if backup_restored else ""
            yield _sse({"type": "error", "message": f"导入已取消{suffix}"})
        except Exception as e:
            logger.error(f"导入失败: {e}", exc_info=True)
            try:
                await asyncio.to_thread(_remove_path, staging_output_dir)
            except Exception as rollback_error:
                logger.error(f"导入失败后清理临时目录失败: {rollback_error}", exc_info=True)
            suffix = "，已恢复导入前备份" if backup_restored else ""
            yield _sse({"type": "error", "message": f"导入失败: {str(e)}{suffix}"})
        finally:
            if staging_output_dir is not None:
                try:
                    await asyncio.to_thread(_remove_path, staging_output_dir)
                except Exception:
                    pass
            if archive_temp_dir is not None:
                try:
                    await asyncio.to_thread(archive_temp_dir.cleanup)
                except Exception:
                    pass
            if job_key:
                _IMPORT_CANCEL_EVENTS.pop(job_key, None)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(generate_progress(), headers=headers)
