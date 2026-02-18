from __future__ import annotations

"""SNS (Moments) HTML export service (offline ZIP)."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import html
import json
import os
import re
import sqlite3
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Literal, Optional

from .chat_helpers import _load_contact_rows, _pick_display_name, _resolve_account_dir
from .logging_config import get_logger
from .media_helpers import _detect_image_media_type, _read_and_maybe_decrypt_media, _resolve_account_wxid_dir

# Reuse UI CSS + wxemoji mapping from chat export to keep styling consistent.
from .chat_export_service import (  # pylint: disable=protected-access
    _load_ui_css_bundle,
    _load_wechat_emoji_regex,
    _load_wechat_emoji_table,
    _resolve_ui_public_dir,
    _zip_write_tree,
)

# Reuse SNS timeline/local cache helpers.
from .routers.sns import (  # pylint: disable=protected-access
    _generate_sns_cache_key,
    _resolve_sns_cached_image_path,
    _resolve_sns_cached_image_path_by_cache_key,
    _resolve_sns_cached_image_path_by_md5,
    _resolve_sns_cached_video_path,
    list_sns_timeline,
)

# SNS remote download+decrypt helpers (shared with API endpoints).
from .sns_media import (  # pylint: disable=protected-access
    fix_sns_cdn_url as _fix_sns_cdn_url,
    materialize_sns_remote_video as _materialize_sns_remote_video,
    try_fetch_and_decrypt_sns_image_remote as _try_fetch_and_decrypt_sns_image_remote,
)

logger = get_logger(__name__)

ExportStatus = Literal["queued", "running", "done", "error", "cancelled"]
ExportScope = Literal["selected", "all"]

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(s: str, max_len: int = 80) -> str:
    t = str(s or "").strip()
    if not t:
        return ""
    t = _INVALID_PATH_CHARS.sub("_", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    return t


def _resolve_export_output_dir(account_dir: Path, output_dir_raw: Any) -> Path:
    text = str(output_dir_raw or "").strip()
    if not text:
        default_dir = account_dir.parents[1] / "exports" / account_dir.name
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir

    out_dir = Path(text).expanduser()
    if not out_dir.is_absolute():
        raise ValueError("output_dir must be an absolute path.")

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ValueError(f"Failed to prepare output_dir: {e}") from e

    return out_dir.resolve()


def _mime_to_ext(mt: str) -> str:
    m = str(mt or "").split(";", 1)[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/avif": ".avif",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }.get(m, ".bin")


def _format_dt(ts_seconds: Any) -> str:
    try:
        t = int(ts_seconds or 0)
    except Exception:
        t = 0
    if t <= 0:
        return ""
    try:
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(t)


def _clean_name(v: Any) -> str:
    return str(v or "").replace("\xa0", " ").strip()


def _esc_text(v: Any) -> str:
    return html.escape(str(v or ""), quote=False)


def _esc_attr(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


_SNS_EXPORT_CSS_PATCH = """
/* Moments export tweaks (keep consistent with frontend `sns.vue`). */
body { background-color: #EDEDED; }
.wse-live-photo video { display: none; }
.wse-live-photo:hover video { display: block; }
.wse-live-photo:hover img { display: none; }
"""


def _load_sns_users(account_dir: Path, *, usernames: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Return [{username, displayName, postCount}] sorted by postCount desc."""
    sns_db_path = account_dir / "sns.db"
    if not sns_db_path.exists():
        raise FileNotFoundError("sns.db not found for this account.")

    wanted = {str(u or "").strip() for u in (usernames or []) if str(u or "").strip()}
    conn = sqlite3.connect(str(sns_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT user_name AS username, COUNT(*) AS postCount
            FROM SnsTimeLine
            WHERE content IS NOT NULL
              AND content != ''
              AND content NOT LIKE '%<type>7</type>%'
            GROUP BY user_name
            ORDER BY postCount DESC
            """
        ).fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    names = [str(r["username"] or "").strip() for r in (rows or []) if r is not None]
    names = [u for u in names if u]
    if wanted:
        names = [u for u in names if u in wanted]

    contact_db_path = account_dir / "contact.db"
    contact_rows = _load_contact_rows(contact_db_path, names) if contact_db_path.exists() else {}

    items: list[dict[str, Any]] = []
    for r in rows or []:
        try:
            uname = str(r["username"] or "").strip()
        except Exception:
            uname = ""
        if not uname:
            continue
        if wanted and uname not in wanted:
            continue
        try:
            post_count = int(r["postCount"] or 0)
        except Exception:
            post_count = 0
        display = _clean_name(_pick_display_name(contact_rows.get(uname), uname)) or uname
        items.append({"username": uname, "displayName": display, "postCount": post_count})
    return items


@dataclass
class ExportProgress:
    users_total: int = 0
    users_done: int = 0
    current_username: str = ""
    current_display_name: str = ""
    posts_exported: int = 0
    media_copied: int = 0
    media_missing: int = 0


@dataclass
class ExportJob:
    export_id: str
    account: str
    status: ExportStatus = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: str = ""
    zip_path: Optional[Path] = None
    options: dict[str, Any] = field(default_factory=dict)
    progress: ExportProgress = field(default_factory=ExportProgress)
    cancel_requested: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "exportId": self.export_id,
            "account": self.account,
            "status": self.status,
            "createdAt": int(self.created_at),
            "startedAt": int(self.started_at) if self.started_at else None,
            "finishedAt": int(self.finished_at) if self.finished_at else None,
            "error": self.error or "",
            "zipPath": str(self.zip_path) if self.zip_path else "",
            "zipReady": bool(self.zip_path and self.zip_path.exists()),
            "options": self.options,
            "progress": {
                "usersTotal": self.progress.users_total,
                "usersDone": self.progress.users_done,
                "currentUsername": self.progress.current_username,
                "currentDisplayName": self.progress.current_display_name,
                "postsExported": self.progress.posts_exported,
                "mediaCopied": self.progress.media_copied,
                "mediaMissing": self.progress.media_missing,
            },
        }


class _JobCancelled(Exception):
    pass


class SnsExportManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ExportJob] = {}

    def list_jobs(self) -> list[ExportJob]:
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, export_id: str) -> Optional[ExportJob]:
        with self._lock:
            return self._jobs.get(export_id)

    def cancel_job(self, export_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(export_id)
            if not job:
                return False
            job.cancel_requested = True
            if job.status in {"queued"}:
                job.status = "cancelled"
                job.finished_at = time.time()
            return True

    def create_job(
        self,
        *,
        account: Optional[str],
        scope: ExportScope,
        usernames: list[str],
        use_cache: bool,
        output_dir: Optional[str],
        file_name: Optional[str],
    ) -> ExportJob:
        account_dir = _resolve_account_dir(account)
        export_id = uuid.uuid4().hex[:12]

        job = ExportJob(
            export_id=export_id,
            account=account_dir.name,
            status="queued",
            options={
                "scope": str(scope or "selected"),
                "usernames": [str(u or "").strip() for u in (usernames or []) if str(u or "").strip()],
                "useCache": bool(use_cache),
                "outputDir": str(output_dir or "").strip(),
                "fileName": str(file_name or "").strip(),
            },
        )

        with self._lock:
            self._jobs[export_id] = job

        t = threading.Thread(
            target=self._run_job_safe,
            args=(job, account_dir),
            name=f"sns-export-{export_id}",
            daemon=True,
        )
        t.start()
        return job

    def _should_cancel(self, job: ExportJob) -> bool:
        with self._lock:
            return bool(job.cancel_requested)

    def _run_job_safe(self, job: ExportJob, account_dir: Path) -> None:
        tmp_zip: Optional[Path] = None
        try:
            tmp_zip = self._run_job(job, account_dir)
        except _JobCancelled:
            logger.info("sns export cancelled: %s", job.export_id)
            with self._lock:
                job.status = "cancelled"
                job.finished_at = time.time()
            if tmp_zip is not None:
                try:
                    tmp_zip.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.exception("sns export job failed: %s: %s", job.export_id, e)
            with self._lock:
                job.status = "error"
                job.error = str(e)
                job.finished_at = time.time()
            if tmp_zip is not None:
                try:
                    tmp_zip.unlink(missing_ok=True)
                except Exception:
                    pass

    def _run_job(self, job: ExportJob, account_dir: Path) -> Path:
        with self._lock:
            if job.status == "cancelled":
                raise _JobCancelled()
            job.status = "running"
            job.started_at = time.time()
            job.error = ""

        opts = dict(job.options or {})
        scope_raw = str(opts.get("scope") or "selected").strip() or "selected"
        scope: ExportScope = "all" if scope_raw == "all" else "selected"  # type: ignore[assignment]
        target_usernames = [str(u or "").strip() for u in (opts.get("usernames") or []) if str(u or "").strip()]
        if scope == "selected" and not target_usernames:
            raise ValueError("No target usernames to export.")

        use_cache = bool(opts.get("useCache"))
        exports_root = _resolve_export_output_dir(account_dir, opts.get("outputDir"))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        base_name = str(opts.get("fileName") or "").strip()
        if not base_name:
            if scope == "all":
                base_name = f"wechat_sns_export_{account_dir.name}_{ts}_{job.export_id}.zip"
            else:
                hint = _safe_name(target_usernames[0], max_len=40) or "selected"
                base_name = f"wechat_sns_export_{account_dir.name}_{hint}_{ts}_{job.export_id}.zip"
        if not base_name.lower().endswith(".zip"):
            base_name += ".zip"
        base_name = _safe_name(base_name, max_len=120) or f"wechat_sns_export_{account_dir.name}_{ts}_{job.export_id}.zip"

        final_zip = (exports_root / base_name).resolve()
        tmp_zip = (exports_root / f".{base_name}.{job.export_id}.part").resolve()
        try:
            tmp_zip.unlink(missing_ok=True)
        except Exception:
            pass

        report: dict[str, Any] = {"errors": []}
        ui_public_dir = _resolve_ui_public_dir()

        emoji_table = _load_wechat_emoji_table()
        emoji_regex = _load_wechat_emoji_regex()

        def render_text_with_emojis(v: Any) -> str:
            text = str(v or "")
            if not text:
                return ""
            if not emoji_table or emoji_regex is None:
                return _esc_text(text)

            parts: list[str] = []
            last = 0
            for match in emoji_regex.finditer(text):
                start = match.start()
                end = match.end()
                if start > last:
                    parts.append(_esc_text(text[last:start]))

                key = match.group(0)
                value = str(emoji_table.get(key) or "")
                if value:
                    src = f"wxemoji/{value}"
                    parts.append(
                        '<img class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" '
                        f'src="{_esc_attr(src)}" alt="" />'
                    )
                else:
                    parts.append(_esc_text(key))
                last = end

            if last < len(text):
                parts.append(_esc_text(text[last:]))
            return "".join(parts)

        def should_cancel() -> None:
            if self._should_cancel(job):
                raise _JobCancelled()

        written: set[str] = set()
        media_written: dict[str, str] = {}
        avatar_written: dict[str, str] = {}

        wxid_dir = _resolve_account_wxid_dir(account_dir)

        avatar_conn: Optional[sqlite3.Connection] = None
        head_image_db_path = account_dir / "head_image.db"
        if head_image_db_path.exists():
            try:
                avatar_conn = sqlite3.connect(str(head_image_db_path))
                avatar_conn.row_factory = sqlite3.Row
            except Exception:
                avatar_conn = None

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def run_async(coro):
            return loop.run_until_complete(coro)

        _HEX_ONLY_RE = re.compile(r"[^0-9a-fA-F]+")

        def _pick_str(*vals: Any) -> str:
            for v in vals:
                try:
                    s = str(v or "").strip()
                except Exception:
                    s = ""
                if s:
                    return s
            return ""

        def _normalize_hex32(v: Any) -> str:
            raw = str(v or "").strip()
            if not raw:
                return ""
            hex_only = _HEX_ONLY_RE.sub("", raw).lower()
            return hex_only[:32] if len(hex_only) >= 32 else ""

        def _sns_media_token(m: dict[str, Any]) -> str:
            url_attrs = m.get("urlAttrs") if isinstance(m.get("urlAttrs"), dict) else {}
            thumb_attrs = m.get("thumbAttrs") if isinstance(m.get("thumbAttrs"), dict) else {}
            return _pick_str(m.get("token"), url_attrs.get("token"), thumb_attrs.get("token"))

        def _sns_media_key(m: dict[str, Any]) -> str:
            url_attrs = m.get("urlAttrs") if isinstance(m.get("urlAttrs"), dict) else {}
            thumb_attrs = m.get("thumbAttrs") if isinstance(m.get("thumbAttrs"), dict) else {}
            return _pick_str(m.get("key"), url_attrs.get("key"), thumb_attrs.get("key"))

        def _sns_media_md5(m: dict[str, Any], raw_url: str) -> str:
            url_attrs = m.get("urlAttrs") if isinstance(m.get("urlAttrs"), dict) else {}
            thumb_attrs = m.get("thumbAttrs") if isinstance(m.get("thumbAttrs"), dict) else {}
            md5_raw = _pick_str(url_attrs.get("md5"), thumb_attrs.get("md5"), url_attrs.get("MD5"), thumb_attrs.get("MD5"))
            if not md5_raw:
                match = re.search(r"[?&]md5=([0-9a-fA-F]{16,32})", str(raw_url or ""))
                if match and match.group(1):
                    md5_raw = match.group(1)
            return _normalize_hex32(md5_raw)

        def _sns_media_size(m: dict[str, Any]) -> tuple[int, int, int]:
            size = m.get("size") if isinstance(m.get("size"), dict) else {}
            try:
                w0 = int(size.get("width") or size.get("w") or 0)
            except Exception:
                w0 = 0
            try:
                h0 = int(size.get("height") or size.get("h") or 0)
            except Exception:
                h0 = 0
            ts0 = size.get("totalSize")
            if ts0 is None:
                ts0 = size.get("total_size")
            if ts0 is None:
                ts0 = size.get("total")
            try:
                t0 = int(ts0 or 0)
            except Exception:
                t0 = 0
            return w0, h0, t0

        def _response_bytes(resp: Any) -> tuple[bytes, str]:
            if resp is None:
                return b"", ""
            mt = str(getattr(resp, "media_type", "") or "")
            path = getattr(resp, "path", None)
            if path:
                try:
                    data = Path(str(path)).read_bytes()
                except Exception:
                    data = b""
                if not mt and data:
                    mt = _detect_image_media_type(data[:32])
                return bytes(data), mt
            try:
                data = bytes(getattr(resp, "body", b"") or b"")
            except Exception:
                data = b""
            if not mt and data:
                mt = _detect_image_media_type(data[:32])
            return data, mt

        def _write_image_payload(
            *,
            zf: zipfile.ZipFile,
            payload: bytes,
            media_type: str,
            cache_key: str,
            subdir: str,
        ) -> str:
            if not payload:
                return ""
            mt = str(media_type or "").split(";", 1)[0].strip()
            if (not mt) or mt == "application/octet-stream":
                mt = _detect_image_media_type(payload[:32])
            if not mt:
                return ""
            ext = _mime_to_ext(mt)
            arc = f"media/{str(subdir or 'images').strip().strip('/')}/{cache_key}{ext}".replace("\\", "/")
            try:
                if arc not in written:
                    zf.writestr(arc, payload)
                    written.add(arc)
                    with self._lock:
                        job.progress.media_copied += 1
                return arc
            except Exception:
                return ""

        def export_avatar_to_zip(*, zf: zipfile.ZipFile, username: str, display_name: str) -> str:
            uname0 = str(username or "").strip()
            if not uname0:
                return ""
            if uname0 in avatar_written:
                return avatar_written[uname0]

            payload = b""
            mt = ""

            if avatar_conn is not None:
                try:
                    row = avatar_conn.execute(
                        "SELECT image_buffer FROM head_image WHERE username = ? ORDER BY update_time DESC LIMIT 1",
                        (uname0,),
                    ).fetchone()
                    if row is not None and row[0] is not None:
                        buf = row[0]
                        if isinstance(buf, (bytes, bytearray)):
                            payload = bytes(buf)
                        elif isinstance(buf, memoryview):
                            payload = buf.tobytes()
                        else:
                            payload = bytes(buf)
                except Exception:
                    payload = b""

            # Fallback: reuse the backend avatar endpoint (supports remote URL cache).
            if not payload:
                try:
                    from .routers.chat_media import get_chat_avatar  # pylint: disable=import-outside-toplevel

                    resp = run_async(get_chat_avatar(username=uname0, account=account_dir.name))
                    payload2, mt2 = _response_bytes(resp)
                    if payload2:
                        payload = payload2
                        mt = mt2
                except Exception:
                    payload = b""

            if not payload:
                avatar_written[uname0] = ""
                return ""

            if not mt:
                mt = _detect_image_media_type(payload[:32])

            cache_key = hashlib.md5(f"avatar|{uname0}".encode("utf-8", errors="ignore")).hexdigest()
            arc = _write_image_payload(zf=zf, payload=payload, media_type=mt, cache_key=cache_key, subdir="avatars")
            avatar_written[uname0] = arc
            return arc

        def export_image_to_zip(
            *,
            zf: zipfile.ZipFile,
            post: dict[str, Any],
            media: dict[str, Any],
            idx: int,
            prefer_thumb: bool = False,
        ) -> str:
            m = media if isinstance(media, dict) else {}
            raw_url = str(m.get("thumb") or m.get("url") or "").strip() if prefer_thumb else str(m.get("url") or m.get("thumb") or "").strip()
            if not raw_url:
                return ""

            token = _sns_media_token(m)
            key = _sns_media_key(m)
            fixed = _fix_sns_cdn_url(raw_url, token=token, is_video=False)

            post_id = str(post.get("id") or post.get("tid") or "").strip()
            media_id = str(m.get("id") or "").strip()
            kind = "thumb" if prefer_thumb else "url"
            if post_id and media_id:
                ident = f"snsimg|{kind}|{post_id}|{media_id}"
            else:
                ident = f"snsimg|{kind}|{fixed or raw_url}|{key}"
            cache_key = hashlib.md5(ident.encode("utf-8", errors="ignore")).hexdigest()

            if cache_key in media_written:
                return media_written[cache_key]

            payload = b""
            mt = ""

            # 0) Prefer WeFlow-style remote download+decrypt (accurate when keys are present).
            if fixed:
                should_cancel()
                res = run_async(
                    _try_fetch_and_decrypt_sns_image_remote(
                        account_dir=account_dir,
                        url=fixed,
                        key=str(key or ""),
                        token=str(token or ""),
                        use_cache=use_cache,
                    )
                )
                if res is not None:
                    payload = bytes(res.payload or b"")
                    mt = str(res.media_type or "")

            # 1) Local cache fallback (only when cache is enabled; mirrors `/api/sns/media` semantics).
            if (not payload) and use_cache:
                try:
                    post_type = int(post.get("type") or 1)
                except Exception:
                    post_type = 1
                try:
                    media_type = int(m.get("type") or 2)
                except Exception:
                    media_type = 2

                try:
                    create_time = int(post.get("createTime") or 0)
                except Exception:
                    create_time = 0

                w0, h0, total_size = _sns_media_size(m)
                md5_32 = _sns_media_md5(m, fixed or raw_url)

                local_path = ""

                # Special case: Moments cover background (type=7) may live in `business/sns/bkg`.
                if wxid_dir and post_id and media_id and post_type == 7:
                    try:
                        raw_key = f"{post_id}_{media_id}_4"
                        bkg_md5 = hashlib.md5(raw_key.encode("utf-8", errors="ignore")).hexdigest()
                        bkg_path = wxid_dir / "business" / "sns" / "bkg" / bkg_md5[:2] / bkg_md5
                        if bkg_path.exists() and bkg_path.is_file():
                            payload = bkg_path.read_bytes()
                            mt = "image/jpeg"
                    except Exception:
                        payload = b""
                        mt = ""

                # Deterministic cache key match: md5(tid_mediaId_type)
                if (not payload) and wxid_dir and post_id and media_id:
                    try:
                        key_post = _generate_sns_cache_key(post_id, media_id, post_type)
                        local_path = _resolve_sns_cached_image_path_by_cache_key(
                            wxid_dir=wxid_dir, cache_key=key_post, create_time=0
                        ) or ""
                    except Exception:
                        local_path = ""

                    if (not local_path) and post_type != media_type:
                        try:
                            key_media = _generate_sns_cache_key(post_id, media_id, media_type)
                            local_path = _resolve_sns_cached_image_path_by_cache_key(
                                wxid_dir=wxid_dir, cache_key=key_media, create_time=0
                            ) or ""
                        except Exception:
                            local_path = ""

                # Md5-based SNS cache layout fallback (when available).
                if (not payload) and (not local_path) and wxid_dir and md5_32:
                    try:
                        local_path = _resolve_sns_cached_image_path_by_md5(
                            wxid_dir=wxid_dir,
                            md5=md5_32,
                            create_time=create_time,
                        ) or ""
                    except Exception:
                        local_path = ""

                # Heuristic match by (create_time, width, height, idx, total_size).
                if (not payload) and (not local_path):
                    try:
                        local_path = _resolve_sns_cached_image_path(
                            account_dir_str=str(account_dir),
                            create_time=create_time,
                            width=int(w0 or 0),
                            height=int(h0 or 0),
                            idx=max(0, int(idx or 0)),
                            total_size=int(total_size or 0),
                        ) or ""
                    except Exception:
                        local_path = ""

                if (not payload) and local_path:
                    try:
                        payload2, mt2 = _read_and_maybe_decrypt_media(Path(local_path), account_dir)
                        if payload2 and str(mt2 or "").startswith("image/"):
                            payload = payload2
                            mt = str(mt2 or "")
                    except Exception:
                        payload = b""
                        mt = ""

            # 2) Last resort: proxy the raw URL (may return a Tencent placeholder image).
            if (not payload) and str(raw_url or "").startswith("http"):
                try:
                    from .routers.chat_media import proxy_image  # pylint: disable=import-outside-toplevel

                    should_cancel()
                    resp = run_async(proxy_image(url=str(raw_url)))
                    payload2, mt2 = _response_bytes(resp)
                    if payload2:
                        payload = payload2
                        mt = mt2
                except Exception:
                    payload = b""
                    mt = ""

            if not payload:
                with self._lock:
                    job.progress.media_missing += 1
                media_written[cache_key] = ""
                return ""

            arc = _write_image_payload(zf=zf, payload=payload, media_type=mt, cache_key=cache_key, subdir="images")
            if not arc:
                with self._lock:
                    job.progress.media_missing += 1
                media_written[cache_key] = ""
                return ""

            media_written[cache_key] = arc
            return arc

        def export_video_to_zip(
            *,
            zf: zipfile.ZipFile,
            post_id: str,
            media_id: str,
            url: str,
            key: str,
            token: str,
        ) -> str:
            fixed = _fix_sns_cdn_url(str(url or ""), token=str(token or ""), is_video=True)
            if not fixed:
                return ""

            ident = f"snsvid|{str(post_id or '').strip()}|{str(media_id or '').strip()}|{fixed}|{key}"
            cache_key = hashlib.md5(ident.encode("utf-8", errors="ignore")).hexdigest()

            if cache_key in media_written:
                return media_written[cache_key]

            # Prefer local cached video when possible (fast, offline-friendly).
            if use_cache and wxid_dir and str(post_id or "").strip() and str(media_id or "").strip():
                try:
                    local = _resolve_sns_cached_video_path(wxid_dir, str(post_id), str(media_id))
                except Exception:
                    local = None
                if local:
                    arc = f"media/videos/{cache_key}.mp4"
                    if arc not in written:
                        try:
                            zf.write(str(local), arcname=arc)
                            written.add(arc)
                            with self._lock:
                                job.progress.media_copied += 1
                        except Exception:
                            arc = ""
                    if arc:
                        media_written[cache_key] = arc
                        return arc

            should_cancel()
            path = run_async(
                _materialize_sns_remote_video(
                    account_dir=account_dir,
                    url=fixed,
                    key=str(key or ""),
                    token=str(token or ""),
                    use_cache=use_cache,
                )
            )
            if path is None:
                with self._lock:
                    job.progress.media_missing += 1
                media_written[cache_key] = ""
                return ""

            arc = f"media/videos/{cache_key}.mp4"
            if arc not in written:
                try:
                    zf.write(str(path), arcname=arc)
                    written.add(arc)
                    with self._lock:
                        job.progress.media_copied += 1
                    # When cache is disabled, `_materialize_sns_remote_video` returns a temp file path.
                    # Clean it up after the zip entry is written to avoid leaving `.tmp` files behind.
                    if not use_cache:
                        try:
                            Path(str(path)).unlink(missing_ok=True)
                        except Exception:
                            pass
                except Exception:
                    with self._lock:
                        job.progress.media_missing += 1
                    media_written[cache_key] = ""
                    return ""

            media_written[cache_key] = arc
            return arc

        def render_media_block(*, zf: zipfile.ZipFile, post: dict[str, Any]) -> str:
            media = post.get("media") if isinstance(post.get("media"), list) else []
            if not media:
                return ""

            def is_live_photo(m: dict[str, Any]) -> bool:
                lp = m.get("livePhoto")
                return isinstance(lp, dict) and bool(str(lp.get("url") or "").strip())

            def media_size_key(m: dict[str, Any]) -> str:
                try:
                    t0 = str(m.get("type") or "").strip()
                except Exception:
                    t0 = ""
                w0, h0, _ts0 = _sns_media_size(m)
                if w0 <= 0 or h0 <= 0:
                    return ""
                return f"{t0}:{w0}x{h0}"

            def media_size_group_index(idx0: int) -> int:
                i0 = int(idx0 or 0)
                if i0 <= 0 or i0 >= len(media):
                    return max(0, i0)
                m0 = media[i0] if isinstance(media[i0], dict) else {}
                key0 = media_size_key(m0)
                if not key0:
                    return max(0, i0)
                count = 0
                for j in range(i0):
                    mj = media[j] if isinstance(media[j], dict) else {}
                    if media_size_key(mj) == key0:
                        count += 1
                return count

            if len(media) == 1:
                m0 = media[0] if isinstance(media[0], dict) else {}
                mtype = int(m0.get("type") or 0)
                idx_group = 0
                post_id = str(post.get("id") or "").strip()
                media_id = str(m0.get("id") or "").strip()

                if mtype == 6:
                    vid_arc = export_video_to_zip(
                        zf=zf,
                        post_id=post_id,
                        media_id=media_id,
                        url=str(m0.get("url") or ""),
                        key=str(m0.get("videoKey") or ""),
                        token=_sns_media_token(m0),
                    )
                    poster_arc = export_image_to_zip(
                        zf=zf,
                        post=post,
                        media=m0,
                        idx=idx_group,
                        prefer_thumb=True,
                    )
                    if not vid_arc:
                        return ""
                    poster_attr = f' poster="{_esc_attr(poster_arc)}"' if poster_arc else ""
                    return (
                        '<div class="mt-2 max-w-[360px]">'
                        '<div class="inline-block cursor-pointer relative">'
                        f'<video src="{_esc_attr(vid_arc)}"{poster_attr} '
                        'class="rounded-sm max-h-[360px] max-w-full object-cover" autoplay loop muted playsinline></video>'
                        '<div class="absolute inset-0 flex items-center justify-center pointer-events-none">'
                        '<div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">'
                        '<svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'
                        "</div></div></div>"
                        "</div>"
                    )

                img_arc = export_image_to_zip(
                    zf=zf,
                    post=post,
                    media=m0,
                    idx=idx_group,
                    prefer_thumb=True,
                )
                if not img_arc:
                    return ""

                if is_live_photo(m0):
                    lp = m0.get("livePhoto") if isinstance(m0.get("livePhoto"), dict) else {}
                    vid_arc = export_video_to_zip(
                        zf=zf,
                        url=str(lp.get("url") or ""),
                        key=str(lp.get("key") or m0.get("videoKey") or ""),
                        token=_pick_str(lp.get("token"), _sns_media_token(m0)),
                        post_id="",
                        media_id="",
                    )
                    video_html = ""
                    if vid_arc:
                        video_html = (
                            f'<video src="{_esc_attr(vid_arc)}" poster="{_esc_attr(img_arc)}" '
                            'class="rounded-sm max-h-[360px] max-w-full object-cover" '
                            "autoplay loop muted playsinline></video>"
                        )
                    return (
                        '<div class="mt-2 max-w-[360px]">'
                        '<div class="inline-block cursor-pointer relative wse-live-photo">'
                        f'<a href="{_esc_attr(img_arc)}" target="_blank" rel="noopener noreferrer">'
                        f'<img src="{_esc_attr(img_arc)}" class="rounded-sm max-h-[360px] object-cover" alt="" loading="lazy" />'
                        "</a>"
                        f"{video_html}"
                        '<div class="absolute bottom-2 left-2 text-[10px] text-white bg-black/45 px-2 py-1 rounded-full pointer-events-none">实况</div>'
                        "</div></div>"
                    )

                return (
                    '<div class="mt-2 max-w-[360px]">'
                    f'<a href="{_esc_attr(img_arc)}" target="_blank" rel="noopener noreferrer" class="inline-block cursor-pointer relative">'
                    f'<img src="{_esc_attr(img_arc)}" class="rounded-sm max-h-[360px] object-cover" alt="" loading="lazy" />'
                    "</a></div>"
                )

            cells: list[str] = []
            for idx0, m_raw in enumerate(media[:9]):
                m = m_raw if isinstance(m_raw, dict) else {}
                mtype = int(m.get("type") or 0)
                idx_group = media_size_group_index(idx0)
                post_id = str(post.get("id") or "").strip()
                media_id = str(m.get("id") or "").strip()

                if mtype == 6:
                    vid_arc = export_video_to_zip(
                        zf=zf,
                        post_id=post_id,
                        media_id=media_id,
                        url=str(m.get("url") or ""),
                        key=str(m.get("videoKey") or ""),
                        token=_sns_media_token(m),
                    )
                    poster_arc = export_image_to_zip(
                        zf=zf,
                        post=post,
                        media=m,
                        idx=idx_group,
                        prefer_thumb=True,
                    )
                    if not vid_arc:
                        continue
                    poster_attr = f' poster="{_esc_attr(poster_arc)}"' if poster_arc else ""
                    cells.append(
                        '<div class="w-[116px] h-[116px] rounded-[2px] overflow-hidden bg-gray-100 border border-gray-200 flex items-center justify-center relative">'
                        f'<video src="{_esc_attr(vid_arc)}"{poster_attr} class="w-full h-full object-cover" autoplay loop muted playsinline></video>'
                        '<div class="absolute inset-0 flex items-center justify-center pointer-events-none">'
                        '<div class="w-10 h-10 rounded-full bg-black/45 flex items-center justify-center">'
                        '<svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'
                        "</div></div>"
                        "</div>"
                    )
                    continue

                img_arc = export_image_to_zip(
                    zf=zf,
                    post=post,
                    media=m,
                    idx=idx_group,
                    prefer_thumb=True,
                )
                if not img_arc:
                    continue

                if is_live_photo(m):
                    lp = m.get("livePhoto") if isinstance(m.get("livePhoto"), dict) else {}
                    vid_arc = export_video_to_zip(
                        zf=zf,
                        url=str(lp.get("url") or ""),
                        key=str(lp.get("key") or m.get("videoKey") or ""),
                        token=_pick_str(lp.get("token"), _sns_media_token(m)),
                        post_id="",
                        media_id="",
                    )
                    video_html = ""
                    if vid_arc:
                        video_html = (
                            f'<video src="{_esc_attr(vid_arc)}" poster="{_esc_attr(img_arc)}" class="w-full h-full object-cover" autoplay loop muted playsinline></video>'
                        )
                    cells.append(
                        '<div class="w-[116px] h-[116px] rounded-[2px] overflow-hidden bg-gray-100 border border-gray-200 flex items-center justify-center relative wse-live-photo">'
                        f'<a href="{_esc_attr(img_arc)}" target="_blank" rel="noopener noreferrer">'
                        f'<img src="{_esc_attr(img_arc)}" class="w-full h-full object-cover" alt="" loading="lazy" />'
                        "</a>"
                        f"{video_html}"
                        '<div class="absolute bottom-1 left-1 text-[9px] text-white bg-black/45 px-1.5 py-0.5 rounded-full pointer-events-none">实况</div>'
                        "</div>"
                    )
                else:
                    cells.append(
                        '<div class="w-[116px] h-[116px] rounded-[2px] overflow-hidden bg-gray-100 border border-gray-200 flex items-center justify-center relative">'
                        f'<a href="{_esc_attr(img_arc)}" target="_blank" rel="noopener noreferrer">'
                        f'<img src="{_esc_attr(img_arc)}" class="w-full h-full object-cover" alt="" loading="lazy" />'
                        "</a></div>"
                    )

            if not cells:
                return ""
            return '<div class="mt-2 grid grid-cols-3 gap-1 max-w-[360px]">' + "".join(cells) + "</div>"

        def render_post_html(*, zf: zipfile.ZipFile, post: dict[str, Any]) -> str:
            pid = str(post.get("id") or "").strip()
            uname = str(post.get("username") or "").strip()
            display = _clean_name(post.get("displayName")) or uname
            ts = _format_dt(post.get("createTime"))
            content_desc = str(post.get("contentDesc") or "")
            location = str(post.get("location") or "").strip()
            likes = post.get("likes") if isinstance(post.get("likes"), list) else []
            comments = post.get("comments") if isinstance(post.get("comments"), list) else []

            def guess_official_name_from_title(title: str) -> str:
                t0 = str(title or "").strip()
                if not t0:
                    return ""
                m = re.search(r"[《「【](.+?)[》」】]", t0)
                return str(m.group(1) or "").strip() if m and m.group(1) else ""

            def format_moment_type_label(p: dict[str, Any]) -> str:
                try:
                    t = int(p.get("type") or 0)
                except Exception:
                    t = 0
                if t == 3:
                    off = p.get("official") if isinstance(p.get("official"), dict) else {}
                    st0 = off.get("serviceType") if isinstance(off, dict) else None
                    try:
                        st = int(st0) if st0 not in (None, "") else None
                    except Exception:
                        st = None
                    prefix = "服务号" if st == 1 else "公众号"
                    name = str(off.get("displayName") or "").strip() if isinstance(off, dict) else ""
                    if not name:
                        name = guess_official_name_from_title(str(p.get("title") or ""))
                    return f"{prefix}·{name}" if name else prefix
                if t == 28:
                    ff = p.get("finderFeed") if isinstance(p.get("finderFeed"), dict) else {}
                    name = str(ff.get("nickname") or "").strip() if isinstance(ff, dict) else ""
                    return f"视频号·{name}" if name else "视频号"
                return ""

            def format_finder_feed_card_text(p: dict[str, Any]) -> str:
                title0 = str(p.get("title") or "").strip()
                if title0:
                    return title0
                ff = p.get("finderFeed") if isinstance(p.get("finderFeed"), dict) else {}
                desc0 = str(ff.get("desc") or "").strip() if isinstance(ff, dict) else ""
                if desc0:
                    return re.sub(r"\\s+", " ", desc0)
                fallback0 = str(p.get("contentDesc") or "").strip()
                return re.sub(r"\\s+", " ", fallback0) if fallback0 else "视频号"

            def export_external_thumb(url: str, *, kind: str) -> str:
                u0 = str(url or "").strip()
                if not u0 or (not u0.lower().startswith("http")):
                    return ""
                ident = f"extimg|{kind}|{u0}"
                ck = hashlib.md5(ident.encode("utf-8", errors="ignore")).hexdigest()
                if ck in media_written:
                    return media_written[ck]
                try:
                    from .routers.chat_media import proxy_image  # pylint: disable=import-outside-toplevel

                    should_cancel()
                    resp = run_async(proxy_image(url=u0))
                    payload, mt = _response_bytes(resp)
                except Exception:
                    payload, mt = b"", ""
                if not payload:
                    media_written[ck] = ""
                    return ""
                arc0 = _write_image_payload(zf=zf, payload=payload, media_type=mt, cache_key=ck, subdir="images")
                media_written[ck] = arc0
                return arc0

            avatar_arc = export_avatar_to_zip(zf=zf, username=uname, display_name=display)
            if avatar_arc:
                avatar_html = (
                    '<div class="w-9 h-9 rounded-md overflow-hidden bg-gray-300 flex-shrink-0">'
                    f'<img src="{_esc_attr(avatar_arc)}" alt="{_esc_attr(display or uname)}" '
                    'class="w-full h-full object-cover" referrerpolicy="no-referrer" />'
                    "</div>"
                )
            else:
                fallback = _esc_text((display or uname or "友")[:1] or "友")
                avatar_html = (
                    '<div class="w-9 h-9 rounded-md overflow-hidden bg-gray-300 flex-shrink-0">'
                    '<div class="w-full h-full flex items-center justify-center text-white text-xs font-bold" '
                    f'style="background-color:#4B5563">{fallback}</div></div>'
                )

            moment_label = format_moment_type_label(post)
            try:
                post_type = int(post.get("type") or 1)
            except Exception:
                post_type = 1

            out: list[str] = []
            out.append(f'<div class="bg-white rounded-sm px-4 py-4 mb-3" id="{_esc_attr(pid)}">')
            out.append('<div class="flex items-start gap-3">')
            out.append(avatar_html)
            out.append('<div class="flex-1 min-w-0">')
            out.append(f'<div class="text-sm font-medium leading-5 text-[#576b95]">{_esc_text(display)}</div>')

            if content_desc:
                out.append(
                    '<div class="mt-1 text-sm text-gray-900 leading-6 whitespace-pre-wrap break-words">'
                    + render_text_with_emojis(content_desc)
                    + "</div>"
                )

            if post_type == 3:
                # Official account article card (matches `sns.vue` layout).
                content_url = str(post.get("contentUrl") or "").strip()
                title0 = str(post.get("title") or "").strip()
                media_list = post.get("media") if isinstance(post.get("media"), list) else []
                m0 = media_list[0] if (media_list and isinstance(media_list[0], dict)) else {}
                thumb_arc = export_image_to_zip(zf=zf, post=post, media=m0, idx=0, prefer_thumb=True) if m0 else ""

                # Best-effort: extract thumb from mp.weixin.qq.com HTML when SNS media is missing.
                if (not thumb_arc) and content_url.lower().startswith("http"):
                    try:
                        from .routers.sns import proxy_article_thumb  # pylint: disable=import-outside-toplevel

                        should_cancel()
                        resp = run_async(proxy_article_thumb(url=content_url))
                        payload, mt = _response_bytes(resp)
                        if payload:
                            ck = hashlib.md5(f"articlethumb|{content_url}".encode("utf-8", errors="ignore")).hexdigest()
                            if ck in media_written:
                                thumb_arc = media_written[ck]
                            else:
                                thumb_arc = _write_image_payload(
                                    zf=zf, payload=payload, media_type=mt, cache_key=ck, subdir="images"
                                )
                                media_written[ck] = thumb_arc
                    except Exception:
                        pass

                out.append('<div class="mt-2 w-full">')
                if content_url:
                    out.append(
                        f'<a href="{_esc_attr(content_url)}" target="_blank" rel="noopener noreferrer" '
                        'class="block w-full bg-[#F7F7F7] p-2 rounded-sm no-underline hover:bg-[#EFEFEF] transition-colors">'
                    )
                else:
                    out.append('<div class="block w-full bg-[#F7F7F7] p-2 rounded-sm">')
                out.append('<div class="flex items-center gap-3">')
                if thumb_arc:
                    out.append(
                        f'<img src="{_esc_attr(thumb_arc)}" class="w-12 h-12 object-cover flex-shrink-0 bg-white" '
                        'alt="" loading="lazy" referrerpolicy="no-referrer" />'
                    )
                else:
                    out.append(
                        '<div class="w-12 h-12 flex items-center justify-center bg-gray-200 text-gray-400 flex-shrink-0 text-xs">文章</div>'
                    )
                out.append('<div class="flex-1 min-w-0 flex items-center overflow-hidden h-12">')
                out.append(f'<div class="text-[13px] text-gray-900 leading-tight line-clamp-2">{_esc_text(title0)}</div>')
                out.append("</div></div>")
                out.append("</a>" if content_url else "</div>")
                out.append("</div>")
            elif post_type == 28 and isinstance(post.get("finderFeed"), dict) and post.get("finderFeed"):
                ff = post.get("finderFeed") if isinstance(post.get("finderFeed"), dict) else {}
                thumb_url = str(ff.get("thumbUrl") or "").strip() if isinstance(ff, dict) else ""
                thumb_arc = export_external_thumb(thumb_url, kind="finder") if thumb_url else ""
                out.append('<div class="mt-2 w-full">')
                out.append('<div class="block w-full bg-[#F7F7F7] p-2 rounded-sm">')
                out.append('<div class="flex items-center gap-3">')
                out.append('<div class="flex-1 min-w-0 flex items-center overflow-hidden h-12">')
                out.append(
                    f'<div class="text-[13px] text-gray-900 leading-tight line-clamp-2">{_esc_text(format_finder_feed_card_text(post))}</div>'
                )
                out.append("</div>")
                out.append('<div class="relative w-12 h-12 rounded-sm overflow-hidden flex-shrink-0 bg-white">')
                if thumb_arc:
                    out.append(
                        f'<img src="{_esc_attr(thumb_arc)}" class="w-full h-full object-cover" alt="" loading="lazy" referrerpolicy="no-referrer" />'
                    )
                else:
                    out.append(
                        '<div class="w-full h-full flex items-center justify-center bg-gray-200 text-gray-400 text-xs">视频</div>'
                    )
                out.append('<div class="absolute inset-0 flex items-center justify-center pointer-events-none">')
                out.append('<div class="w-8 h-8 rounded-full bg-black/45 flex items-center justify-center">')
                out.append(
                    '<svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'
                )
                out.append("</div></div></div></div></div></div>")
            else:
                out.append(render_media_block(zf=zf, post=post))

            if location:
                out.append(f'<div class="mt-2 text-xs text-[#576b95] truncate">{_esc_text(location)}</div>')

            out.append('<div class="mt-2 flex items-center justify-between"><div class="flex items-center gap-2 min-w-0">')
            if ts:
                out.append(f'<span class="text-xs text-gray-400">{_esc_text(ts)}</span>')
            if moment_label:
                out.append(
                    f'<span class="text-xs text-[#576b95] truncate" title="{_esc_attr(moment_label)}">{_esc_text(moment_label)}</span>'
                )
            out.append("</div></div>")

            if (likes and len(likes) > 0) or (comments and len(comments) > 0):
                out.append('<div class="mt-2 bg-gray-100 rounded-sm px-2 py-1">')
                if likes and len(likes) > 0:
                    like_names = "、".join([_clean_name(x) for x in likes if _clean_name(x)])
                    out.append('<div class="flex items-start gap-1 text-xs text-[#576b95] leading-5">')
                    out.append(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
                        'class="mt-[3px] mr-[10px] flex-shrink-0 opacity-80" viewBox="0 0 24 24" '
                        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                        '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 1-4.5 2.5C10.5 4 9.26 3 7.5 3A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />'
                        "</svg>"
                    )
                    out.append(f'<div class="break-words">{_esc_text(like_names)}</div>')
                    out.append("</div>")

                if likes and len(likes) > 0 and comments and len(comments) > 0:
                    out.append('<div class="my-1 border-t border-gray-200"></div>')

                if comments and len(comments) > 0:
                    out.append('<div class="space-y-1">')
                    for c0 in comments:
                        c = c0 if isinstance(c0, dict) else {}
                        cn = _clean_name(c.get("nickname") or c.get("displayName") or c.get("username") or "") or "未知"
                        refn = _clean_name(c.get("refNickname") or c.get("refUsername") or c.get("refUserName") or "")
                        text = str(c.get("content") or "").strip()
                        out.append('<div class="text-xs leading-5 break-words">')
                        out.append(f'<span class="font-medium text-[#576b95]">{_esc_text(cn)}</span>')
                        if refn:
                            out.append('<span class="mx-1 text-gray-500">回复</span>')
                            out.append(f'<span class="font-medium text-[#576b95]">{_esc_text(refn)}</span>')
                        out.append('<span class="text-gray-900">: ')
                        out.append(render_text_with_emojis(text))
                        out.append("</span></div>")
                    out.append("</div>")
                out.append("</div>")

            out.append("</div></div></div>")
            return "".join(out)

        def render_cover_header_html(
            *,
            zf: zipfile.ZipFile,
            username: str,
            display_name: str,
            cover_data: Optional[dict[str, Any]],
        ) -> str:
            cover = cover_data if isinstance(cover_data, dict) else {}
            media_list = cover.get("media") if isinstance(cover.get("media"), list) else []
            m0 = media_list[0] if (media_list and isinstance(media_list[0], dict)) else {}

            cover_post: dict[str, Any] = {}
            try:
                cover_post = dict(cover)
            except Exception:
                cover_post = {}
            cover_post.setdefault("type", 7)
            cover_post.setdefault("id", str(cover.get("id") or "").strip())

            cover_arc = export_image_to_zip(zf=zf, post=cover_post, media=m0, idx=0, prefer_thumb=False) if m0 else ""
            avatar_arc = export_avatar_to_zip(zf=zf, username=username, display_name=display_name)

            out: list[str] = []
            out.append('<div class="relative w-full mb-12 -mt-4 bg-white">')
            out.append('<div class="h-64 w-full bg-[#333333] relative overflow-hidden">')
            if cover_arc:
                out.append(
                    f'<img src="{_esc_attr(cover_arc)}" class="w-full h-full object-cover" alt="朋友圈封面" '
                    'loading="lazy" referrerpolicy="no-referrer" />'
                )
            out.append("</div>")

            out.append('<div class="absolute right-4 -bottom-6 flex items-end gap-4">')
            out.append(
                f'<div class="text-white font-bold text-xl mb-7 drop-shadow-md">{_esc_text(display_name or username)}</div>'
            )

            out.append('<div class="w-[72px] h-[72px] rounded-lg bg-white p-[2px] shadow-sm">')
            if avatar_arc:
                out.append(
                    f'<img src="{_esc_attr(avatar_arc)}" class="w-full h-full rounded-md object-cover bg-gray-100" '
                    f'alt="{_esc_attr(display_name or username)}" loading="lazy" referrerpolicy="no-referrer" />'
                )
            else:
                fallback = _esc_text(((display_name or username or "友")[:1]) or "友")
                out.append(
                    '<div class="w-full h-full rounded-md bg-gray-300 flex items-center justify-center text-white text-xs font-bold" '
                    f'style="background-color:#4B5563">{fallback}</div>'
                )
            out.append("</div>")
            out.append("</div></div>")
            return "".join(out)

        try:
            with zipfile.ZipFile(str(tmp_zip), mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                css_payload = _load_ui_css_bundle(ui_public_dir=ui_public_dir, report=report) + "\n\n" + _SNS_EXPORT_CSS_PATCH
                zf.writestr("assets/wechat-sns-export.css", css_payload)
                written.add("assets/wechat-sns-export.css")

                repo_root = Path(__file__).resolve().parents[2]
                wxemoji_src: Optional[Path] = None
                if ui_public_dir is not None:
                    cand = Path(ui_public_dir) / "wxemoji"
                    if cand.is_dir():
                        wxemoji_src = cand
                if wxemoji_src is None:
                    cand = repo_root / "frontend" / "public" / "wxemoji"
                    if cand.is_dir():
                        wxemoji_src = cand
                if wxemoji_src is not None:
                    _zip_write_tree(zf=zf, src_dir=wxemoji_src, dest_prefix="wxemoji", written=written)

                if scope == "all":
                    users = _load_sns_users(account_dir)
                else:
                    users = _load_sns_users(account_dir, usernames=target_usernames)
                    order = {u: i for i, u in enumerate(target_usernames)}
                    users.sort(key=lambda x: order.get(str(x.get("username") or ""), 10**9))

                with self._lock:
                    job.progress.users_total = len(users)

                user_pages: list[dict[str, Any]] = []
                css_href = "assets/wechat-sns-export.css"

                for i, u in enumerate(users):
                    should_cancel()
                    uname = str(u.get("username") or "").strip()
                    display = _clean_name(u.get("displayName")) or uname
                    with self._lock:
                        job.progress.current_username = uname
                        job.progress.current_display_name = display

                    posts_all: list[dict[str, Any]] = []
                    cover_data: Optional[dict[str, Any]] = None
                    off = 0
                    while True:
                        should_cancel()
                        resp = list_sns_timeline(
                            account=account_dir.name,
                            limit=200,
                            offset=off,
                            usernames=uname,
                            keyword=None,
                        )
                        if off == 0 and cover_data is None and isinstance(resp, dict) and isinstance(resp.get("cover"), dict):
                            cover_data = resp.get("cover")
                        items = resp.get("timeline") if isinstance(resp, dict) else None
                        items = items if isinstance(items, list) else []
                        if not items:
                            break
                        posts_all.extend([p for p in items if isinstance(p, dict)])
                        off += len(items)
                        if not bool(resp.get("hasMore")):
                            break

                    post_parts: list[str] = []
                    for p in posts_all:
                        should_cancel()
                        post_parts.append(render_post_html(zf=zf, post=p))
                        with self._lock:
                            job.progress.posts_exported += 1

                    safe_uname = _safe_name(uname, max_len=80) or hashlib.md5(uname.encode("utf-8", errors="ignore")).hexdigest()[:12]
                    page_name = f"sns_{safe_uname}.html"
                    title = f"朋友圈导出 - {display}"
                    back_link = (
                        '<a href="index.html" class="text-sm text-[#576b95] hover:underline">← 返回</a>'
                        if scope == "all"
                        else ""
                    )
                    cover_html = render_cover_header_html(zf=zf, username=uname, display_name=display, cover_data=cover_data)
                    page_html = "\n".join(
                        [
                            "<!doctype html>",
                            "<html>",
                            "<head>",
                            '<meta charset="utf-8" />',
                            '<meta name="viewport" content="width=device-width, initial-scale=1" />',
                            f"<title>{_esc_text(title)}</title>",
                            f'<link rel="stylesheet" href="{_esc_attr(css_href)}" />',
                            "</head>",
                            '<body style="background-color:#EDEDED">',
                            '<div class="min-h-screen" style="background-color:#EDEDED">',
                            '<div class="max-w-2xl mx-auto px-4 py-4">',
                            cover_html,
                            ('<div class="flex items-center justify-between mb-4">' + back_link + (f'<div class="text-xs text-gray-500 truncate">{_esc_text(uname)}</div>' if uname else "") + "</div>") if back_link else "",
                            "".join(post_parts),
                            "</div>",
                            "</div>",
                            "</body>",
                            "</html>",
                            "",
                        ]
                    )
                    zf.writestr(page_name, page_html)
                    written.add(page_name)

                    user_pages.append(
                        {
                            "username": uname,
                            "displayName": display,
                            "postCount": int(u.get("postCount") or 0),
                            "page": page_name,
                        }
                    )

                    with self._lock:
                        job.progress.users_done = i + 1

                if scope == "all":
                    rows: list[str] = []
                    for u in user_pages:
                        uname = str(u.get("username") or "").strip()
                        display = _clean_name(u.get("displayName")) or uname
                        pc = int(u.get("postCount") or 0)
                        href = str(u.get("page") or "").strip()
                        avatar_arc = export_avatar_to_zip(zf=zf, username=uname, display_name=display)
                        if avatar_arc:
                            avatar_html = (
                                '<div class="w-8 h-8 rounded-md overflow-hidden bg-gray-300 flex-shrink-0">'
                                f'<img src="{_esc_attr(avatar_arc)}" class="w-full h-full object-cover" '
                                f'alt="{_esc_attr(display or uname)}" loading="lazy" referrerpolicy="no-referrer" />'
                                "</div>"
                            )
                        else:
                            fallback = _esc_text((display or uname or "友")[:1] or "友")
                            avatar_html = (
                                '<div class="w-8 h-8 rounded-md overflow-hidden bg-gray-300 flex-shrink-0">'
                                '<div class="w-full h-full flex items-center justify-center text-white text-xs font-bold" '
                                f'style="background-color:#4B5563">{fallback}</div></div>'
                            )
                        rows.append(
                            '<a class="px-3 py-2 text-sm cursor-pointer flex items-center gap-2 border-b border-gray-100 hover:bg-gray-50" '
                            f'href="{_esc_attr(href)}">'
                            f"{avatar_html}"
                            '<div class="flex-1 min-w-0">'
                            f'<div class="truncate">{_esc_text(display)}</div>'
                            f'<div class="text-[11px] text-gray-400 truncate">{_esc_text(uname)} · {pc} 条</div>'
                            "</div></a>"
                        )

                    index_html = "\n".join(
                        [
                            "<!doctype html>",
                            "<html>",
                            "<head>",
                            '<meta charset="utf-8" />',
                            '<meta name="viewport" content="width=device-width, initial-scale=1" />',
                            "<title>朋友圈导出</title>",
                            f'<link rel="stylesheet" href="{_esc_attr(css_href)}" />',
                            "</head>",
                            '<body style="background-color:#EDEDED">',
                            '<div class="min-h-screen" style="background-color:#EDEDED">',
                            '<div class="max-w-2xl mx-auto px-4 py-4">',
                            '<div class="mb-4 flex items-center justify-between">',
                            '<div class="text-sm font-semibold text-gray-700">朋友圈联系人</div>',
                            f'<div class="text-xs text-gray-500">{len(user_pages)} 人</div>',
                            "</div>",
                            '<div class="bg-white rounded-sm overflow-hidden border border-gray-200">',
                            "".join(rows),
                            "</div>",
                            "</div>",
                            "</div>",
                            "</body>",
                            "</html>",
                            "",
                        ]
                    )
                    zf.writestr("index.html", index_html)
                    written.add("index.html")
                else:
                    only_page = user_pages[0]["page"] if user_pages else ""
                    if only_page:
                        index_html = (
                            "<!doctype html><html><head>"
                            '<meta charset="utf-8" />'
                            f'<meta http-equiv="refresh" content="0; url={_esc_attr(only_page)}" />'
                            "</head><body></body></html>"
                        )
                        zf.writestr("index.html", index_html)
                        written.add("index.html")

                try:
                    zf.writestr("export_report.json", json.dumps(report, ensure_ascii=False, indent=2))
                except Exception:
                    pass
        finally:
            try:
                if avatar_conn is not None:
                    avatar_conn.close()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

        try:
            os.replace(str(tmp_zip), str(final_zip))
            final_out = final_zip
        except Exception:
            final_out = tmp_zip

        with self._lock:
            job.zip_path = final_out
            if job.status != "cancelled":
                job.status = "done"
            job.finished_at = time.time()

        return tmp_zip


SNS_EXPORT_MANAGER = SnsExportManager()
