from __future__ import annotations

import functools
import base64
import hashlib
import heapq
import html
import ipaddress
import json
import os
import re
import sqlite3
import socket
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional
from urllib.parse import urljoin, urlparse

import requests

from .chat_helpers import (
    _decode_message_content,
    _decode_sqlite_text,
    _extract_md5_from_packed_info,
    _extract_sender_from_group_xml,
    _extract_xml_attr,
    _extract_xml_tag_or_attr,
    _extract_xml_tag_text,
    _format_session_time,
    _infer_message_brief_by_local_type,
    _infer_transfer_status_text,
    _iter_message_db_paths,
    _list_decrypted_accounts,
    _load_contact_rows,
    _load_latest_message_previews,
    _lookup_resource_md5,
    _parse_app_message,
    _parse_location_message,
    _parse_system_message_content,
    _parse_pat_message,
    _build_avatar_url,
    _pick_display_name,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
    _resource_lookup_chat_id,
    _should_keep_session,
    _split_group_sender_prefix,
    _resolve_msg_table_name_by_map,
)
from .chat_realtime_autosync import CHAT_REALTIME_AUTOSYNC
from .chat_realtime_reader import count_realtime_message_rows_via_exec, read_all_realtime_message_rows
from .logging_config import get_logger
from .media_helpers import (
    MediaPathIndex,
    _convert_silk_to_browser_audio,
    _detect_image_media_type,
    _fallback_search_media_by_file_id,
    _read_and_maybe_decrypt_media,
    _resolve_account_db_storage_dir,
    _resolve_account_wxid_dir,
    _resolve_media_path_for_kind,
    _try_find_decrypted_resource,
)
from .perf_trace import create_perf_trace
from .wcdb_realtime import (
    WCDB_REALTIME,
    WCDBRealtimeError,
    close_message_cursor as _wcdb_close_message_cursor,
    exec_query as _wcdb_exec_query,
    fetch_message_batch as _wcdb_fetch_message_batch,
    get_avatar_urls as _wcdb_get_avatar_urls,
    get_display_names as _wcdb_get_display_names,
    get_message_count as _wcdb_get_message_count,
    get_messages as _wcdb_get_messages,
    get_sessions as _wcdb_get_sessions,
    open_message_cursor as _wcdb_open_message_cursor,
)

logger = get_logger(__name__)

ExportFormat = Literal["json", "txt", "html"]
ExportScope = Literal["selected", "all", "groups", "singles"]
ChatSource = Literal["auto", "decrypted", "realtime"]
ExportStatus = Literal["queued", "running", "done", "error", "cancelled"]
MediaKind = Literal["image", "emoji", "video", "video_thumb", "voice", "file"]

_EXPORT_PROGRESS_LOG_INTERVAL = 1000
_EXPORT_SLOW_STEP_MS = 500.0


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 1)


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _normalize_chat_source(value: Optional[str], *, default: str = "auto") -> str:
    v = str(value or "").strip().lower()
    if not v:
        v = str(default or "auto").strip().lower()
    if v in {"decrypted", "local", "sqlite"}:
        return "decrypted"
    if v in {"auto", "default", "wechat"}:
        return "auto"
    if v in {"realtime", "real-time", "wcdb"}:
        return "realtime"
    raise ValueError("Invalid source, use 'auto', 'decrypted' or 'realtime'.")


def _has_decrypted_export_dbs(account_dir: Path) -> bool:
    try:
        return bool((account_dir / "session.db").exists() and (account_dir / "contact.db").exists())
    except Exception:
        return False


def _safe_trace(trace_log: Optional[Callable[..., None]], phase: str, **fields: Any) -> None:
    if trace_log is None:
        return
    try:
        trace_log(phase, **fields)
    except Exception:
        pass


def _log_export_slow_step(stage: str, started_at: float, **fields: Any) -> None:
    elapsed = _elapsed_ms(started_at)
    if elapsed < _EXPORT_SLOW_STEP_MS:
        return
    payload = {
        **fields,
        "stage": stage,
        "elapsedMs": elapsed,
        "thread": threading.current_thread().name,
    }
    logger.info("chat export slow step %s", _safe_json_dumps(payload))


def _raise_if_job_cancelled(
    job: Any,
    stage: str,
    trace_log: Optional[Callable[..., None]] = None,
    **fields: Any,
) -> None:
    if not bool(getattr(job, "cancel_requested", False)):
        return
    export_id = str(getattr(job, "export_id", "") or "")
    payload = {
        **fields,
        "exportId": export_id,
        "stage": stage,
        "thread": threading.current_thread().name,
    }
    _safe_trace(trace_log, "cancel_detected", **payload)
    logger.info("chat export cancel detected %s", _safe_json_dumps(payload))
    raise _JobCancelled()


def _log_writer_progress(
    trace_log: Optional[Callable[..., None]],
    *,
    export_format: str,
    job: Any,
    conv_username: str,
    scanned: int,
    exported: int,
    force: bool = False,
) -> None:
    if not force and (scanned <= 0 or scanned % _EXPORT_PROGRESS_LOG_INTERVAL != 0):
        return
    progress = getattr(job, "progress", None)
    _safe_trace(
        trace_log,
        "writer_progress",
        format=export_format,
        conversation=conv_username,
        scanned=scanned,
        exported=exported,
        messagesExported=int(getattr(progress, "messages_exported", 0) or 0),
        mediaCopied=int(getattr(progress, "media_copied", 0) or 0),
        mediaMissing=int(getattr(progress, "media_missing", 0) or 0),
    )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def _resolve_ui_public_dir() -> Optional[Path]:
    """Best-effort resolve Nuxt generated public directory for exporting UI CSS.

    Priority:
      1) `WECHAT_TOOL_UI_DIR` env
      2) repo default `frontend/.output/public`
    """

    ui_dir_env = os.environ.get("WECHAT_TOOL_UI_DIR", "").strip()
    candidates: list[Path] = []
    if ui_dir_env:
        candidates.append(Path(ui_dir_env))

    # Repo defaults: generated Nuxt output or checked-in desktop UI assets.
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "frontend" / ".output" / "public")
    candidates.append(repo_root / "desktop" / "resources" / "ui")

    for p in candidates:
        try:
            nuxt_dir = p / "_nuxt"
            if nuxt_dir.is_dir() and any(nuxt_dir.glob("entry.*.css")):
                return p
        except Exception:
            continue
    return None


def _load_ui_entry_css(ui_public_dir: Path) -> str:
    """Load Nuxt `entry.*.css` content (choose largest file if multiple)."""

    nuxt_dir = Path(ui_public_dir) / "_nuxt"
    try:
        css_files = list(nuxt_dir.glob("entry.*.css"))
    except Exception:
        css_files = []

    if not css_files:
        return ""

    def sort_key(p: Path) -> int:
        try:
            return int(p.stat().st_size)
        except Exception:
            return 0

    css_files.sort(key=sort_key, reverse=True)
    best = css_files[0]
    try:
        return best.read_text(encoding="utf-8")
    except Exception:
        try:
            return best.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""


_VUE_SCOPED_ATTR_RE = re.compile(r"\[data-v-[0-9a-f]{8}\]", flags=re.IGNORECASE)
_CHAT_HISTORY_MD5_TAG_RE = re.compile(
    r"(?i)<(?:fullmd5|thumbfullmd5|md5|emoticonmd5|emojimd5|cdnthumbmd5)>([0-9a-f]{32})<"
)
_CHAT_HISTORY_URL_TAG_RE = re.compile(r"(?i)<(?:sourceheadurl|cdnurlstring|encrypturlstring|externurl)>(https?://[^<\s]+)<")
_CHAT_HISTORY_SERVER_ID_TAG_RE = re.compile(r"(?i)<fromnewmsgid>\s*(\d+)\s*<")


def _strip_vue_scoped_attrs(css: str) -> str:
    """Strip Vue SFC scoped attribute selectors like `[data-v-xxxxxxxx]`."""

    if not css:
        return ""
    try:
        return _VUE_SCOPED_ATTR_RE.sub("", css)
    except Exception:
        return css


def _load_ui_css_bundle(*, ui_public_dir: Optional[Path], report: dict[str, Any]) -> str:
    """Load Nuxt CSS bundle for offline HTML export.

    Includes:
      - `_nuxt/entry.*.css` (base + tailwind utilities)
      - Chat page chunks `_nuxt/*_username_*.css` (scoped selectors stripped)
      - native CSS patch appended last

    Falls back to native fallback CSS when entry css is missing.

    Note: We only bundle chat-related chunks because stripping Vue SFC scoped selectors (`[data-v-...]`) can
    otherwise leak scoped utility overrides (e.g. `.text-sm[data-v-...]`) into global rules in the export.
    """

    if ui_public_dir is None:
        try:
            report["errors"].append("WARN: Nuxt UI dir not found; export HTML will use fallback styles.")
        except Exception:
            pass
        return _html_export_css_fallback() + "\n\n" + _html_export_css_patch()

    entry_css = _load_ui_entry_css(ui_public_dir)
    if not entry_css:
        try:
            report["errors"].append("WARN: Nuxt UI CSS not found; export HTML will use fallback styles.")
        except Exception:
            pass
        return _html_export_css_fallback() + "\n\n" + _html_export_css_patch()

    entry_css = _strip_vue_scoped_attrs(entry_css)

    nuxt_dir = Path(ui_public_dir) / "_nuxt"
    chat_css_paths: list[Path] = []
    try:
        chat_css_paths = [p for p in nuxt_dir.glob("*_username_*.css") if p.is_file()]
    except Exception:
        chat_css_paths = []

    chat_css_paths.sort(key=lambda p: p.name)

    if not chat_css_paths:
        try:
            report["errors"].append(
                "WARN: Nuxt chat CSS chunk not found (*_username_*.css); some message styles may be missing."
            )
        except Exception:
            pass

    extra_chunks: list[str] = []
    for p in chat_css_paths:
        try:
            extra_chunks.append(_strip_vue_scoped_attrs(p.read_text(encoding="utf-8")))
        except Exception:
            try:
                extra_chunks.append(_strip_vue_scoped_attrs(p.read_text(encoding="utf-8", errors="ignore")))
            except Exception:
                continue

    parts = [entry_css]
    if extra_chunks:
        parts.append("\n\n".join(extra_chunks))
    parts.append(_html_export_css_patch())
    return "\n\n".join(parts)


@functools.lru_cache(maxsize=1)
def _load_wechat_emoji_table() -> dict[str, str]:
    """Load WeChat built-in text emoji mapping from one fixed UI asset path."""

    ui_public_dir = _resolve_ui_public_dir()
    if ui_public_dir is None:
        return {}

    path = Path(ui_public_dir) / "wxemoji" / "wechat-emojis.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if str(key or "").strip() and str(value or "").strip()
    }


@functools.lru_cache(maxsize=1)
def _load_wechat_emoji_regex() -> Optional[re.Pattern[str]]:
    table = _load_wechat_emoji_table()
    if not table:
        return None

    keys = sorted(table.keys(), key=len, reverse=True)
    escaped = [re.escape(k) for k in keys if k]
    if not escaped:
        return None

    try:
        return re.compile(f"({'|'.join(escaped)})")
    except Exception:
        return None


def _zip_write_tree(
    *,
    zf: zipfile.ZipFile,
    src_dir: Path,
    dest_prefix: str,
    written: set[str],
) -> int:
    """Recursively add a directory tree to the zip under `dest_prefix`.

    Skips any file whose `arcname` already exists in `written`.
    Returns number of files written.
    """

    try:
        if not src_dir.exists() or (not src_dir.is_dir()):
            return 0
    except Exception:
        return 0

    prefix = str(dest_prefix or "").strip().strip("/").replace("\\", "/")
    count = 0
    try:
        for p in src_dir.rglob("*"):
            try:
                if not p.is_file():
                    continue
            except Exception:
                continue
            try:
                rel = p.relative_to(src_dir).as_posix()
            except Exception:
                rel = p.name
            arc = f"{prefix}/{rel}" if prefix else rel
            arc = arc.lstrip("/").replace("\\", "/")
            if not arc or arc in written:
                continue
            try:
                zf.write(str(p), arcname=arc)
            except Exception:
                continue
            written.add(arc)
            count += 1
    except Exception:
        return count
    return count


_REMOTE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_REMOTE_IMAGE_TIMEOUT = (5, 10)
_REMOTE_IMAGE_ALLOWED_CT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


def _is_public_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(ip_text or "").strip())
    except Exception:
        return False
    return bool(getattr(ip, "is_global", False))


def _is_safe_remote_host(hostname: str, port: Optional[int]) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        if _is_public_ip(host):
            return True
        if re.fullmatch(r"[0-9a-f:]+", host) and ":" in host and (not _is_public_ip(host)):
            return False
    except Exception:
        pass

    try:
        infos = socket.getaddrinfo(host, int(port or 443), type=socket.SOCK_STREAM)
    except Exception:
        return False

    for info in infos:
        try:
            sockaddr = info[4]
            ip_text = str(sockaddr[0] or "")
        except Exception:
            ip_text = ""
        if not _is_public_ip(ip_text):
            return False
    return True


def _download_remote_image_to_zip(
    *,
    zf: zipfile.ZipFile,
    url: str,
    remote_written: dict[str, str],
    report: dict[str, Any],
) -> str:
    started_at = time.perf_counter()
    raw = str(url or "").strip()
    if not raw:
        return ""

    cached = remote_written.get(raw)
    if cached is not None:
        return cached

    current = raw
    last_error = ""

    for _ in range(4):  # 0..3 redirects
        parsed = urlparse(current)
        if parsed.scheme not in {"http", "https"}:
            last_error = f"unsupported scheme: {parsed.scheme}"
            break
        host = parsed.hostname or ""
        if not host:
            last_error = "missing hostname"
            break
        if not _is_safe_remote_host(host, parsed.port):
            last_error = f"blocked host: {host}"
            break

        resp = None
        try:
            resp = requests.get(
                current,
                stream=True,
                timeout=_REMOTE_IMAGE_TIMEOUT,
                allow_redirects=False,
                headers={
                    "User-Agent": "wechat-chat-export/1.0",
                    "Accept": "image/*",
                },
            )

            if int(resp.status_code) in {301, 302, 303, 307, 308}:
                loc = str(resp.headers.get("Location") or "").strip()
                if not loc:
                    last_error = f"redirect without Location ({resp.status_code})"
                    break
                current = urljoin(current, loc)
                continue

            if int(resp.status_code) != 200:
                last_error = f"http {resp.status_code}"
                break

            ct = str(resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            ext = _REMOTE_IMAGE_ALLOWED_CT.get(ct, "")

            cl = str(resp.headers.get("Content-Length") or "").strip()
            if cl:
                try:
                    if int(cl) > _REMOTE_IMAGE_MAX_BYTES:
                        last_error = f"remote image too large: {cl} bytes"
                        break
                except Exception:
                    pass

            buf = bytearray()
            too_large = False
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                buf.extend(chunk)
                if len(buf) > _REMOTE_IMAGE_MAX_BYTES:
                    too_large = True
                    break

            if too_large:
                last_error = f"remote image too large: >{_REMOTE_IMAGE_MAX_BYTES} bytes"
                break

            if not ext:
                # Some WeChat CDN endpoints return `application/octet-stream` even for images.
                # Detect by magic bytes to improve offline exports for merged-forward emojis/avatars.
                try:
                    mt2 = _detect_image_media_type(bytes(buf[:32]))
                except Exception:
                    mt2 = ""
                ext = _REMOTE_IMAGE_ALLOWED_CT.get(str(mt2 or "").strip().lower(), "")
            if not ext:
                last_error = f"unsupported content-type: {ct or 'unknown'}"
                break

            h = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()
            arc = f"media/remote/{h[:32]}.{ext}"
            zf.writestr(arc, bytes(buf))
            remote_written[raw] = arc
            _log_export_slow_step(
                "download_remote_image",
                started_at,
                url=raw,
                finalUrl=current,
                arc=arc,
                contentType=ct,
                bytes=len(buf),
            )
            return arc
        except Exception as e:
            last_error = f"request failed: {e}"
            break
        finally:
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass

    try:
        clipped = raw if len(raw) <= 260 else (raw[:257] + "...")
        report["errors"].append(f"WARN: Remote image download skipped/failed: {clipped} ({last_error})")
    except Exception:
        pass
    remote_written[raw] = ""
    _log_export_slow_step(
        "download_remote_image_failed",
        started_at,
        url=raw,
        finalUrl=current,
        error=last_error,
    )
    return ""



# HTML export integrity/style/runtime core is provided by native/wce_integrity.pyd.
# Keep Python as orchestration only; do not provide Python fallbacks for these pieces.
_HTML_EXPORT_NATIVE_ERROR = "\u0048\u0054\u004d\u004c \u5bfc\u51fa\u7ec4\u4ef6\u521d\u59cb\u5316\u5931\u8d25\u3002"


def _load_wce_integrity_native() -> Any:
    try:
        from .native import wce_integrity  # type: ignore

        return wce_integrity
    except Exception as e:
        raise RuntimeError(_HTML_EXPORT_NATIVE_ERROR) from e


def _native_text(native_integrity: Any, func_name: str, *args: Any, error: str = _HTML_EXPORT_NATIVE_ERROR) -> str:
    try:
        fn = getattr(native_integrity, func_name)
        value = str(fn(*args))
    except Exception as e:
        raise RuntimeError(error) from e
    if not value.strip():
        raise RuntimeError(error)
    return value


def _native_json_list(
    native_integrity: Any,
    func_name: str,
    *args: Any,
    length: int,
    error: str = _HTML_EXPORT_NATIVE_ERROR,
) -> list[str]:
    raw = _native_text(native_integrity, func_name, *args, error=error)
    try:
        value = json.loads(raw)
    except Exception as e:
        raise RuntimeError(error) from e
    if not isinstance(value, list) or len(value) < length:
        raise RuntimeError(error)
    out = [str(value[i] or "").strip() for i in range(length)]
    if any(not item for item in out):
        raise RuntimeError(error)
    return out


def _html_export_css_fallback() -> str:
    return _native_text(_load_wce_integrity_native(), "css_fallback")


def _html_export_css_patch() -> str:
    return _native_text(_load_wce_integrity_native(), "css_patch")


def _html_export_runtime_js(native_integrity: Any) -> str:
    return _native_text(native_integrity, "runtime_js")


def _html_export_asset_paths(export_id: str) -> tuple[str, str, str]:
    values = _native_json_list(
        _load_wce_integrity_native(),
        "asset_paths",
        str(export_id or ""),
        length=3,
    )
    return values[0], values[1], values[2]


def _html_export_integrity_sidecar_paths(export_id: str) -> tuple[str, str]:
    values = _native_json_list(
        _load_wce_integrity_native(),
        "integrity_sidecar_paths",
        str(export_id or ""),
        length=2,
    )
    return values[0], values[1]


def _html_export_integrity_script_tag(*, src: str) -> str:
    return _native_text(_load_wce_integrity_native(), "integrity_script_tag", str(src or ""))


def _html_export_attribution_html() -> str:
    return _native_text(_load_wce_integrity_native(), "attribution_html")


def _html_export_gate_style() -> str:
    return _native_text(_load_wce_integrity_native(), "gate_style")


def _html_export_page_fragment_js(*, export_id: str, arc_js: str, page_no: int, fragment_html: str) -> str:
    return _native_text(
        _load_wce_integrity_native(),
        "page_fragment_js",
        str(export_id or ""),
        _zip_arcname(arc_js),
        int(page_no),
        str(fragment_html or ""),
    )


def _sri_sha384(text: str) -> str:
    digest = hashlib.sha384(str(text or "").encode("utf-8")).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def _sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(bytes(data or b"")).hexdigest()


def _sha256_hex_file(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return size, h.hexdigest()


def _zip_arcname(value: Any) -> str:
    s = str(value or "").strip().replace("\\", "/").lstrip("/")
    while "//" in s:
        s = s.replace("//", "/")
    return s


class _ZipIntegrityWriter:
    """Small ZipFile proxy that records hashes for the exported integrity bundle."""

    def __init__(self, zf: zipfile.ZipFile, *, native_integrity: Any = None):
        self._zf = zf
        self._native_integrity = native_integrity
        self._entries: dict[str, dict[str, Any]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._zf, name)

    def _record_bytes(self, arcname: Any, data: Any) -> None:
        arc = _zip_arcname(arcname)
        if not arc or arc.endswith("/"):
            return
        if isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, bytes):
            raw = data
        elif isinstance(data, bytearray):
            raw = bytes(data)
        elif isinstance(data, memoryview):
            raw = data.tobytes()
        else:
            raw = bytes(data or b"")
        native = self._native_integrity
        if native is not None:
            try:
                entry = json.loads(str(native.record_bytes(arc, raw)))
            except Exception as e:
                raise RuntimeError("HTML 导出完整性组件记录文件失败。") from e
        else:
            entry = {"path": arc, "size": len(raw), "sha256": _sha256_hex_bytes(raw)}
        self._entries[arc] = entry

    def _record_file(self, src: Any, arcname: Any) -> None:
        arc = _zip_arcname(arcname)
        if not arc or arc.endswith("/"):
            return
        native = self._native_integrity
        if native is not None:
            try:
                entry = json.loads(str(native.record_file(str(Path(src)), arc)))
            except Exception as e:
                raise RuntimeError("HTML 导出完整性组件记录资源失败。") from e
        else:
            try:
                size, digest = _sha256_hex_file(Path(src))
            except Exception:
                return
            entry = {"path": arc, "size": int(size), "sha256": digest}
        self._entries[arc] = entry

    def writestr(self, zinfo_or_arcname: Any, data: Any, *args: Any, **kwargs: Any) -> Any:
        result = self._zf.writestr(zinfo_or_arcname, data, *args, **kwargs)
        arc = getattr(zinfo_or_arcname, "filename", zinfo_or_arcname)
        self._record_bytes(arc, data)
        return result

    def write(self, filename: Any, arcname: Any = None, *args: Any, **kwargs: Any) -> Any:
        if arcname is None:
            result = self._zf.write(filename, *args, **kwargs)
        else:
            result = self._zf.write(filename, arcname, *args, **kwargs)
        arc = arcname if arcname is not None else filename
        self._record_file(filename, arc)
        return result

    def integrity_entries(self) -> list[dict[str, Any]]:
        return [self._entries[k] for k in sorted(self._entries)]


def _minify_css_for_export(css: str) -> str:
    text = str(css or "")
    if not text:
        return ""
    try:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s*([{}:;,>+~])\s*", r"\1", text)
        text = text.replace(";}", "}")
        return text.strip()
    except Exception:
        return str(css or "")


def _minify_html_for_export(text: str) -> str:
    html_text = str(text or "")
    if not html_text:
        return ""
    try:
        html_text = re.sub(r"<!--(?!\[if).*?-->", "", html_text, flags=re.DOTALL)
        html_text = re.sub(r">\s+<", "><", html_text)
        return html_text.strip() + "\n"
    except Exception:
        return str(text or "")


def _seal_html_export_with_native(
    *,
    native_integrity: Any,
    export_id: str,
    entries: Iterable[dict[str, Any]],
    html_assets: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = json.loads(
            str(
                native_integrity.seal_export(
                    str(export_id or ""),
                    json.dumps(list(entries), ensure_ascii=False, separators=(",", ":")),
                    json.dumps(dict(html_assets or {}), ensure_ascii=False, separators=(",", ":")),
                )
            )
        )
    except Exception as e:
        raise RuntimeError("HTML 导出完整性组件生成校验失败。") from e
    if not isinstance(result, dict) or not str(result.get("bundle") or "").strip():
        raise RuntimeError("HTML 导出完整性组件返回结果为空。")
    return result


def _format_ts(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _is_md5(s: str) -> bool:
    return bool(re.fullmatch(r"(?i)[0-9a-f]{32}", str(s or "").strip()))


def _normalize_render_type_key(value: Any) -> str:
    v = str(value or "").strip()
    if not v:
        return ""
    if v == "redPacket":
        return "redpacket"
    lower = v.lower()
    if lower in {"redpacket", "red_packet", "red-packet", "redenvelope", "red_envelope"}:
        return "redpacket"
    return lower


def _is_render_type_selected(render_type: Any, selected_render_types: Optional[set[str]]) -> bool:
    if selected_render_types is None:
        return True
    rt = _normalize_render_type_key(render_type) or "text"
    return rt in selected_render_types


def _media_kinds_from_selected_types(selected_render_types: Optional[set[str]]) -> Optional[set[MediaKind]]:
    if selected_render_types is None:
        return None

    out: set[MediaKind] = set()
    # Merged-forward chat history items can contain arbitrary media types; enable packing those
    # even when users only select `chatHistory` in the renderType filter.
    if "chathistory" in selected_render_types:
        out.update({"image", "emoji", "video", "video_thumb", "voice", "file"})
    if "image" in selected_render_types:
        out.add("image")
    if "emoji" in selected_render_types:
        out.add("emoji")
    if "video" in selected_render_types:
        out.add("video")
        out.add("video_thumb")
    if "voice" in selected_render_types:
        out.add("voice")
    if "file" in selected_render_types:
        out.add("file")
    return out


def _resolve_effective_media_kinds(
    *,
    include_media: bool,
    media_kinds: list[MediaKind],
    selected_render_types: Optional[set[str]],
    privacy_mode: bool,
) -> tuple[bool, list[MediaKind]]:
    if privacy_mode or (not include_media):
        return False, []

    kinds = [k for k in media_kinds if k in {"image", "emoji", "video", "video_thumb", "voice", "file"}]
    if not kinds:
        return False, []

    selected_media_kinds = _media_kinds_from_selected_types(selected_render_types)
    if selected_media_kinds is not None:
        kinds = [k for k in kinds if k in selected_media_kinds]

    kinds = list(dict.fromkeys(kinds))
    if not kinds:
        return False, []
    return True, kinds


@dataclass
class ExportProgress:
    conversations_total: int = 0
    conversations_done: int = 0
    current_conversation_index: int = 0  # 1-based
    current_conversation_username: str = ""
    current_conversation_name: str = ""
    current_conversation_messages_total: int = 0
    current_conversation_messages_exported: int = 0
    messages_exported: int = 0
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
                "conversationsTotal": self.progress.conversations_total,
                "conversationsDone": self.progress.conversations_done,
                "currentConversationIndex": self.progress.current_conversation_index,
                "currentConversationUsername": self.progress.current_conversation_username,
                "currentConversationName": self.progress.current_conversation_name,
                "currentConversationMessagesTotal": self.progress.current_conversation_messages_total,
                "currentConversationMessagesExported": self.progress.current_conversation_messages_exported,
                "messagesExported": self.progress.messages_exported,
                "mediaCopied": self.progress.media_copied,
                "mediaMissing": self.progress.media_missing,
            },
        }


class _JobCancelled(Exception):
    pass


class ChatExportManager:
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
                logger.info("chat export cancel requested for missing job export_id=%s", export_id)
                return False
            job.cancel_requested = True
            logger.info(
                "chat export cancel requested %s",
                _safe_json_dumps(
                    {
                        "exportId": job.export_id,
                        "status": job.status,
                        "createdAt": job.created_at,
                        "startedAt": job.started_at,
                        "progress": {
                            "conversationsDone": job.progress.conversations_done,
                            "conversationsTotal": job.progress.conversations_total,
                            "currentConversationIndex": job.progress.current_conversation_index,
                            "messagesExported": job.progress.messages_exported,
                            "mediaCopied": job.progress.media_copied,
                            "mediaMissing": job.progress.media_missing,
                        },
                    }
                ),
            )
            if job.status in {"queued"}:
                job.status = "cancelled"
                job.finished_at = time.time()
                logger.info("chat export queued job cancelled export_id=%s", job.export_id)
            return True

    def create_job(
        self,
        *,
        account: Optional[str],
        source: Optional[ChatSource] = "auto",
        scope: ExportScope,
        usernames: list[str],
        export_format: ExportFormat,
        start_time: Optional[int],
        end_time: Optional[int],
        include_hidden: bool,
        include_official: bool,
        include_media: bool,
        media_kinds: list[MediaKind],
        message_types: list[str],
        output_dir: Optional[str],
        allow_process_key_extract: bool,
        download_remote_media: bool,
        html_page_size: int = 1000,
        privacy_mode: bool,
        file_name: Optional[str],
    ) -> ExportJob:
        account_dir = _resolve_account_dir(account)
        source_norm = _normalize_chat_source(source, default="auto")
        if source_norm in {"auto", "realtime"}:
            try:
                WCDB_REALTIME.ensure_connected(account_dir)
            except WCDBRealtimeError as e:
                raise ValueError(f"Realtime export requires WCDB/direct mode but connection failed: {e}") from e
        export_id = uuid.uuid4().hex[:12]

        job = ExportJob(
            export_id=export_id,
            account=account_dir.name,
            status="queued",
            options={
                "scope": scope,
                "source": source_norm,
                "usernames": usernames,
                "format": export_format,
                "startTime": int(start_time) if start_time else None,
                "endTime": int(end_time) if end_time else None,
                "includeHidden": bool(include_hidden),
                "includeOfficial": bool(include_official),
                "includeMedia": bool(include_media),
                "mediaKinds": media_kinds,
                "messageTypes": list(dict.fromkeys([str(t or "").strip() for t in (message_types or []) if str(t or "").strip()])),
                "outputDir": str(output_dir or "").strip(),
                "allowProcessKeyExtract": bool(allow_process_key_extract),
                "downloadRemoteMedia": bool(download_remote_media),
                "htmlPageSize": int(html_page_size) if int(html_page_size or 0) > 0 else int(html_page_size or 0),
                "privacyMode": bool(privacy_mode),
                "fileName": str(file_name or "").strip(),
            },
        )

        with self._lock:
            self._jobs[export_id] = job

        logger.info(
            "chat export job created %s",
            _safe_json_dumps(
                {
                    "exportId": job.export_id,
                    "account": account_dir.name,
                    "options": job.options,
                }
            ),
        )

        t = threading.Thread(
            target=self._run_job_safe,
            args=(job, account_dir),
            name=f"chat-export-{export_id}",
            daemon=True,
        )
        t.start()
        return job

    def _run_job_safe(self, job: ExportJob, account_dir: Path) -> None:
        try:
            self._run_job(job, account_dir)
        except Exception as e:
            logger.exception(f"export job failed: {job.export_id}: {e}")
            with self._lock:
                job.status = "error"
                job.error = str(e)
                job.finished_at = time.time()

    def _should_cancel(self, job: ExportJob) -> bool:
        with self._lock:
            return bool(job.cancel_requested)

    def _run_job(self, job: ExportJob, account_dir: Path) -> None:
        with self._lock:
            if job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = time.time()
            job.error = ""

        _trace_id, trace = create_perf_trace(
            logger,
            "chat_export_job",
            exportId=job.export_id,
            account=account_dir.name,
        )
        _safe_trace(trace, "job_started", thread=threading.current_thread().name)
        opts = dict(job.options or {})
        source_requested = _normalize_chat_source(opts.get("source"), default="auto")
        source_norm = "realtime" if source_requested in {"auto", "realtime"} else "decrypted"
        rt_conn = None
        if source_norm == "realtime":
            try:
                rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
                _safe_trace(
                    trace,
                    "realtime_connected",
                    sourceRequested=source_requested,
                    dbStorageDir=str(getattr(rt_conn, "db_storage_dir", "") or ""),
                )
            except WCDBRealtimeError as e:
                raise RuntimeError(f"Realtime export requires WCDB/direct mode but connection failed: {e}") from e

        realtime_pause_reason = f"chat_export:{job.export_id}"
        realtime_paused = False
        if source_norm == "decrypted":
            try:
                pause_depth = CHAT_REALTIME_AUTOSYNC.pause_account(account_dir.name, reason=realtime_pause_reason)
                realtime_paused = bool(pause_depth > 0)
                _safe_trace(
                    trace,
                    "realtime_autosync_paused",
                    account=account_dir.name,
                    reason=realtime_pause_reason,
                    depth=int(pause_depth),
                )
            except Exception:
                logger.exception("failed to pause realtime autosync account=%s export_id=%s", account_dir.name, job.export_id)
                _safe_trace(
                    trace,
                    "realtime_autosync_pause_failed",
                    account=account_dir.name,
                    reason=realtime_pause_reason,
                )
        else:
            _safe_trace(trace, "realtime_autosync_pause_skipped", source=source_norm)

        scope: ExportScope = str(opts.get("scope") or "selected")  # type: ignore[assignment]
        export_format_raw = str(opts.get("format") or "json").strip() or "json"
        if export_format_raw not in {"json", "txt", "html"}:
            raise ValueError(f"Unsupported export format: {export_format_raw}")
        export_format: ExportFormat = export_format_raw  # type: ignore[assignment]
        include_hidden = bool(opts.get("includeHidden"))
        include_official = bool(opts.get("includeOfficial"))
        include_media = bool(opts.get("includeMedia"))
        allow_process_key_extract = bool(opts.get("allowProcessKeyExtract"))
        download_remote_media = bool(opts.get("downloadRemoteMedia"))
        privacy_mode = bool(opts.get("privacyMode"))
        try:
            html_page_size = int(opts.get("htmlPageSize") or 1000)
        except Exception:
            html_page_size = 1000
        if html_page_size < 0:
            html_page_size = 0

        media_kinds_raw = opts.get("mediaKinds") or []
        media_kinds: list[MediaKind] = []
        for k in media_kinds_raw:
            ks = str(k or "").strip()
            if ks in {"image", "emoji", "video", "video_thumb", "voice", "file"}:
                media_kinds.append(ks)  # type: ignore[arg-type]

        st = int(opts.get("startTime") or 0) or None
        et = int(opts.get("endTime") or 0) or None

        message_types_raw = opts.get("messageTypes") or []
        want_types: Optional[set[str]] = None
        if message_types_raw:
            parts = [_normalize_render_type_key(x) for x in message_types_raw]
            want = {p for p in parts if p}
            if want:
                want_types = want

        include_media, media_kinds = _resolve_effective_media_kinds(
            include_media=include_media,
            media_kinds=media_kinds,
            selected_render_types=want_types,
            privacy_mode=privacy_mode,
        )

        local_types = None
        estimate_local_types = None

        _safe_trace(
            trace,
            "options_resolved",
            scope=scope,
            source=source_norm,
            sourceRequested=source_requested,
            format=export_format,
            includeMedia=include_media,
            mediaKinds=media_kinds,
            messageTypes=sorted(want_types) if want_types else None,
            startTime=st,
            endTime=et,
            htmlPageSize=html_page_size,
            downloadRemoteMedia=download_remote_media,
            privacyMode=privacy_mode,
        )
        _raise_if_job_cancelled(job, "options_resolved", trace)

        phase_started = time.perf_counter()
        target_usernames = _resolve_export_targets(
            account_dir=account_dir,
            scope=scope,
            usernames=list(opts.get("usernames") or []),
            include_hidden=include_hidden,
            include_official=include_official,
            source=source_norm,
            rt_conn=rt_conn,
        )
        _safe_trace(
            trace,
            "targets_resolved",
            durationMs=_elapsed_ms(phase_started),
            conversationCount=len(target_usernames),
            scope=scope,
        )
        if not target_usernames:
            raise ValueError("No target conversations to export.")

        phase_started = time.perf_counter()
        exports_root = _resolve_export_output_dir(account_dir, opts.get("outputDir"))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _safe_trace(trace, "output_dir_resolved", durationMs=_elapsed_ms(phase_started), outputDir=str(exports_root))

        base_name = str(opts.get("fileName") or "").strip()
        if not base_name:
            if privacy_mode:
                base_name = f"wechat_chat_export_privacy_{ts}_{job.export_id}.zip"
            else:
                base_name = f"wechat_chat_export_{account_dir.name}_{ts}_{job.export_id}.zip"
        else:
            base_name = _safe_name(base_name, max_len=120) or f"wechat_chat_export_{account_dir.name}_{ts}_{job.export_id}.zip"
            if not base_name.lower().endswith(".zip"):
                base_name += ".zip"

        final_zip = (exports_root / base_name).resolve()
        tmp_zip = (exports_root / f".{base_name}.{job.export_id}.part").resolve()
        _safe_trace(trace, "zip_paths_prepared", finalZip=str(final_zip), tmpZip=str(tmp_zip))

        contact_db_path = account_dir / "contact.db"
        message_resource_db_path = account_dir / "message_resource.db"
        media_db_path = account_dir / "media_0.db"
        head_image_db_path = account_dir / "head_image.db"

        phase_started = time.perf_counter()
        resource_conn: Optional[sqlite3.Connection] = None
        try:
            if message_resource_db_path.exists():
                resource_conn = sqlite3.connect(str(message_resource_db_path))
                resource_conn.row_factory = sqlite3.Row
        except Exception:
            try:
                if resource_conn is not None:
                    resource_conn.close()
            except Exception:
                pass
            resource_conn = None

        head_image_conn: Optional[sqlite3.Connection] = None
        if not privacy_mode:
            try:
                if head_image_db_path.exists():
                    head_image_conn = sqlite3.connect(str(head_image_db_path))
            except Exception:
                try:
                    if head_image_conn is not None:
                        head_image_conn.close()
                except Exception:
                    pass
                head_image_conn = None

        _safe_trace(
            trace,
            "db_connections_opened",
            durationMs=_elapsed_ms(phase_started),
            hasResourceDb=resource_conn is not None,
            hasHeadImageDb=head_image_conn is not None,
            hasMediaDb=media_db_path.exists(),
        )
        _raise_if_job_cancelled(job, "db_connections_opened", trace)

        contact_cache: dict[str, str] = {}
        contact_row_cache: dict[str, sqlite3.Row] = {}
        wcdb_display_cache: dict[str, str] = {}
        if source_norm == "realtime" and target_usernames and rt_conn is not None:
            try:
                with rt_conn.lock:
                    wcdb_display_cache = _wcdb_get_display_names(rt_conn.handle, list(target_usernames))
            except Exception:
                wcdb_display_cache = {}

        def resolve_display_name(u: str) -> str:
            if not u:
                return ""
            if u in contact_cache:
                return contact_cache[u]
            wd = str(wcdb_display_cache.get(u) or "").strip()
            if wd and wd != u:
                contact_cache[u] = wd
                return wd
            rows = _load_contact_rows(contact_db_path, [u])
            row = rows.get(u)
            if row is not None:
                contact_row_cache[u] = row
            name = _pick_display_name(row, u)
            if name == u:
                try:
                    if rt_conn is not None:
                        with rt_conn.lock:
                            extra = _wcdb_get_display_names(rt_conn.handle, [u])
                        wd2 = str(extra.get(u) or "").strip()
                        if wd2 and wd2 != u:
                            name = wd2
                            wcdb_display_cache[u] = wd2
                except Exception:
                    pass
            contact_cache[u] = name
            return name

        phase_started = time.perf_counter()
        conv_rows = _load_contact_rows(contact_db_path, target_usernames)
        for k, v in conv_rows.items():
            contact_row_cache[k] = v
            contact_cache[k] = _pick_display_name(v, k)
        _safe_trace(
            trace,
            "contacts_preloaded",
            durationMs=_elapsed_ms(phase_started),
            requested=len(target_usernames),
            loaded=len(conv_rows),
        )
        _raise_if_job_cancelled(job, "contacts_preloaded", trace)

        media_index: Optional[MediaPathIndex] = None
        if include_media and any(kind in {"image", "emoji", "video", "video_thumb", "file"} for kind in media_kinds):
            phase_started = time.perf_counter()
            media_index = MediaPathIndex.build(
                account_dir=account_dir,
                usernames=target_usernames,
                media_kinds=media_kinds,
            )
            _safe_trace(
                trace,
                "media_index_built",
                durationMs=_elapsed_ms(phase_started),
                usernames=len(target_usernames),
                mediaKinds=media_kinds,
                md5Keys=int(media_index.stats.get("md5Keys") or 0),
                fileIdKeys=int(media_index.stats.get("fileIdKeys") or 0),
                scannedFiles=int(media_index.stats.get("scannedFiles") or 0),
                hardlinkRows=int(media_index.stats.get("hardlinkRows") or 0),
            )
            _raise_if_job_cancelled(job, "media_index_built", trace)

        media_written: dict[str, str] = {}
        avatar_written: dict[str, str] = {}
        report: dict[str, Any] = {
            "schemaVersion": 1,
            "exportId": job.export_id,
            "account": account_dir.name,
            "createdAt": _now_iso(),
            "missingMedia": [],
            "errors": [],
        }

        with self._lock:
            job.progress.conversations_total = len(target_usernames)
            job.progress.conversations_done = 0
            job.progress.messages_exported = 0
            job.progress.media_copied = 0
            job.progress.media_missing = 0
        _safe_trace(trace, "progress_initialized", conversationCount=len(target_usernames))

        try:
            if tmp_zip.exists():
                try:
                    tmp_zip.unlink()
                except Exception:
                    pass

            phase_started = time.perf_counter()
            _safe_trace(trace, "zip_open_start", tmpZip=str(tmp_zip))
            native_integrity = _load_wce_integrity_native() if export_format == "html" else None
            with zipfile.ZipFile(tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as raw_zf:
                zf = _ZipIntegrityWriter(raw_zf, native_integrity=native_integrity)
                _safe_trace(trace, "zip_opened", durationMs=_elapsed_ms(phase_started))
                html_index_items: list[dict[str, Any]] = []
                self_avatar_path = ""
                session_items: list[dict[str, Any]] = []
                remote_written: dict[str, str] = {}
                remote_download_enabled = bool(download_remote_media) and (export_format == "html") and include_media and (not privacy_mode)
                if export_format == "html":
                    phase_started = time.perf_counter()
                    _safe_trace(trace, "html_assets_start")
                    ui_public_dir = _resolve_ui_public_dir()
                    css_asset_path, js_asset_path, integrity_asset_path = _html_export_asset_paths(job.export_id)
                    manifest_asset_path, signature_asset_path = _html_export_integrity_sidecar_paths(job.export_id)
                    css_payload = _minify_css_for_export(_load_ui_css_bundle(ui_public_dir=ui_public_dir, report=report))
                    js_payload = _html_export_runtime_js(native_integrity)
                    job.options["_htmlAssets"] = {
                        "cssPath": css_asset_path,
                        "jsPath": js_asset_path,
                        "integrityPath": integrity_asset_path,
                        "manifestPath": manifest_asset_path,
                        "signaturePath": signature_asset_path,
                        "cssIntegrity": _sri_sha384(css_payload),
                        "jsIntegrity": _sri_sha384(js_payload),
                    }
                    zf.writestr(css_asset_path, css_payload)
                    zf.writestr(js_asset_path, js_payload)

                    # Bundle UI static assets so the HTML works offline.
                    repo_root = Path(__file__).resolve().parents[2]
                    static_written: set[str] = {
                        css_asset_path,
                        js_asset_path,
                    }

                    if ui_public_dir is not None:
                        _zip_write_tree(
                            zf=zf,
                            src_dir=Path(ui_public_dir) / "fonts",
                            dest_prefix="fonts",
                            written=static_written,
                        )
                        _zip_write_tree(
                            zf=zf,
                            src_dir=Path(ui_public_dir) / "wxemoji",
                            dest_prefix="wxemoji",
                            written=static_written,
                        )
                        _zip_write_tree(
                            zf=zf,
                            src_dir=Path(ui_public_dir) / "assets" / "images" / "wechat",
                            dest_prefix="assets/images/wechat",
                            written=static_written,
                        )

                    _zip_write_tree(
                        zf=zf,
                        src_dir=repo_root / "frontend" / "public" / "assets" / "images" / "wechat",
                        dest_prefix="assets/images/wechat",
                        written=static_written,
                    )
                    _zip_write_tree(
                        zf=zf,
                        src_dir=repo_root / "frontend" / "assets" / "images" / "wechat",
                        dest_prefix="assets/images/wechat",
                        written=static_written,
                    )
                    _safe_trace(
                        trace,
                        "html_assets_done",
                        durationMs=_elapsed_ms(phase_started),
                        uiPublicDir=str(ui_public_dir) if ui_public_dir is not None else "",
                        staticFiles=len(static_written),
                    )
                    _raise_if_job_cancelled(job, "html_assets_done", trace)

                    preview_by_username: dict[str, str] = {}
                    last_ts_by_username: dict[str, int] = {}

                    if not privacy_mode:
                        phase_started = time.perf_counter()
                        self_avatar_path = _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=account_dir.name,
                            avatar_written=avatar_written,
                        )

                        if source_norm == "realtime" and rt_conn is not None:
                            try:
                                with rt_conn.lock:
                                    raw_sessions_for_index = _wcdb_get_sessions(rt_conn.handle)
                                for item in _normalize_realtime_session_rows(raw_sessions_for_index):
                                    u = str(item.get("username") or "").strip()
                                    if not u or u not in target_usernames:
                                        continue
                                    preview = re.sub(r"\s+", " ", str(item.get("summary") or "").strip()).strip()
                                    if not preview:
                                        preview = _infer_message_brief_by_local_type(int(item.get("last_msg_type") or 0))
                                    preview_by_username[u] = preview
                                    last_ts_by_username[u] = int(item.get("sort_timestamp") or 0)
                            except Exception:
                                preview_by_username = {}
                                last_ts_by_username = {}
                        else:
                            try:
                                preview_by_username = _load_latest_message_previews(account_dir, target_usernames)
                            except Exception:
                                preview_by_username = {}

                        session_db_path = Path(account_dir) / "session.db"
                        if source_norm != "realtime" and session_db_path.exists():
                            sconn = sqlite3.connect(str(session_db_path))
                            sconn.row_factory = sqlite3.Row
                            try:
                                uniq = list(dict.fromkeys([u for u in target_usernames if u]))
                                chunk_size = 900
                                for i in range(0, len(uniq), chunk_size):
                                    chunk = uniq[i : i + chunk_size]
                                    placeholders = ",".join(["?"] * len(chunk))
                                    try:
                                        rows = sconn.execute(
                                            f"SELECT username, sort_timestamp, last_timestamp FROM SessionTable WHERE username IN ({placeholders})",
                                            chunk,
                                        ).fetchall()
                                        for r in rows:
                                            u = str(r["username"] or "").strip()
                                            if not u:
                                                continue
                                            ts = int(r["sort_timestamp"] or 0)
                                            if ts <= 0:
                                                ts = int(r["last_timestamp"] or 0)
                                            last_ts_by_username[u] = int(ts or 0)
                                    except sqlite3.OperationalError:
                                        rows = sconn.execute(
                                            f"SELECT username, last_timestamp FROM SessionTable WHERE username IN ({placeholders})",
                                            chunk,
                                        ).fetchall()
                                        for r in rows:
                                            u = str(r["username"] or "").strip()
                                            if not u:
                                                continue
                                            last_ts_by_username[u] = int(r["last_timestamp"] or 0)
                            except Exception:
                                last_ts_by_username = {}
                            finally:
                                sconn.close()
                        _safe_trace(
                            trace,
                            "html_session_metadata_loaded",
                            durationMs=_elapsed_ms(phase_started),
                            previews=len(preview_by_username),
                            lastTimestamps=len(last_ts_by_username),
                            hasSelfAvatar=bool(self_avatar_path),
                        )
                        _raise_if_job_cancelled(job, "html_session_metadata_loaded", trace)

                    phase_started = time.perf_counter()
                    for idx, conv_username in enumerate(target_usernames, start=1):
                        _raise_if_job_cancelled(job, "html_session_index", trace, index=idx)
                        conv_row = contact_row_cache.get(conv_username)
                        conv_name = resolve_display_name(conv_username) if not privacy_mode else _pick_display_name(conv_row, conv_username)
                        conv_is_group = bool(conv_username.endswith("@chatroom"))
                        conv_dir = f"conversations/{_conversation_dir_name(idx, conv_name, conv_username, conv_is_group, privacy_mode)}"

                        conv_avatar_path = ""
                        if not privacy_mode:
                            conv_avatar_path = _materialize_avatar(
                                zf=zf,
                                head_image_conn=head_image_conn,
                                username=conv_username,
                                avatar_written=avatar_written,
                            )

                        session_items.append(
                            {
                                "username": "" if privacy_mode else conv_username,
                                "displayName": (f"会话 {idx:04d}" if privacy_mode else conv_name),
                                "isGroup": bool(conv_is_group),
                                "convDir": conv_dir,
                                "avatarPath": "" if privacy_mode else conv_avatar_path,
                                "lastTimeText": ("" if privacy_mode else _format_session_time(last_ts_by_username.get(conv_username))),
                                "previewText": ("" if privacy_mode else str(preview_by_username.get(conv_username) or "")),
                            }
                        )
                    _safe_trace(
                        trace,
                        "html_session_index_built",
                        durationMs=_elapsed_ms(phase_started),
                        sessionItems=len(session_items),
                    )

                for idx, conv_username in enumerate(target_usernames, start=1):
                    _raise_if_job_cancelled(job, "conversation_loop_start", trace, index=idx)

                    conv_started = time.perf_counter()
                    conv_row = contact_row_cache.get(conv_username)
                    conv_name = resolve_display_name(conv_username) if not privacy_mode else _pick_display_name(conv_row, conv_username)
                    conv_is_group = bool(conv_username.endswith("@chatroom"))

                    conv_dir = f"conversations/{_conversation_dir_name(idx, conv_name, conv_username, conv_is_group, privacy_mode)}"

                    with self._lock:
                        job.progress.current_conversation_index = idx
                        job.progress.current_conversation_username = conv_username
                        job.progress.current_conversation_name = conv_name
                        job.progress.current_conversation_messages_exported = 0
                        job.progress.current_conversation_messages_total = 0

                    try:
                        phase_started = time.perf_counter()
                        estimated_total = _estimate_conversation_message_count(
                            account_dir=account_dir,
                            conv_username=conv_username,
                            start_time=st,
                            end_time=et,
                            local_types=estimate_local_types,
                            source=source_norm,
                            rt_conn=rt_conn,
                        )
                    except Exception:
                        estimated_total = 0
                    _safe_trace(
                        trace,
                        "conversation_estimated",
                        index=idx,
                        conversation=conv_username,
                        displayName=conv_name,
                        durationMs=_elapsed_ms(phase_started),
                        estimatedTotal=estimated_total,
                    )
                    _raise_if_job_cancelled(job, "conversation_estimated", trace, index=idx, conversation=conv_username)

                    with self._lock:
                        job.progress.current_conversation_messages_total = int(estimated_total)

                    chat_id = None
                    try:
                        phase_started = time.perf_counter()
                        if resource_conn is not None:
                            chat_id = _resource_lookup_chat_id(resource_conn, conv_username)
                    except Exception:
                        chat_id = None
                    _safe_trace(
                        trace,
                        "conversation_resource_lookup",
                        index=idx,
                        conversation=conv_username,
                        durationMs=_elapsed_ms(phase_started),
                        chatId=chat_id,
                    )
                    _raise_if_job_cancelled(job, "conversation_resource_lookup", trace, index=idx, conversation=conv_username)

                    conv_avatar_path = ""
                    if not privacy_mode:
                        phase_started = time.perf_counter()
                        conv_avatar_path = _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=conv_username,
                            avatar_written=avatar_written,
                        )
                        _safe_trace(
                            trace,
                            "conversation_avatar_materialized",
                            index=idx,
                            conversation=conv_username,
                            durationMs=_elapsed_ms(phase_started),
                            hasAvatar=bool(conv_avatar_path),
                        )
                    _raise_if_job_cancelled(job, "conversation_avatar_materialized", trace, index=idx, conversation=conv_username)

                    phase_started = time.perf_counter()
                    if export_format == "txt":
                        exported_count = _write_conversation_txt(
                            zf=zf,
                            conv_dir=conv_dir,
                            account_dir=account_dir,
                            conv_username=conv_username,
                            conv_name=conv_name,
                            conv_avatar_path=conv_avatar_path,
                            conv_is_group=conv_is_group,
                            start_time=st,
                            end_time=et,
                            want_types=want_types,
                            local_types=local_types,
                            source=source_norm,
                            rt_conn=rt_conn,
                            resource_conn=resource_conn,
                            resource_chat_id=chat_id,
                            head_image_conn=head_image_conn,
                            resolve_display_name=resolve_display_name,
                            privacy_mode=privacy_mode,
                            include_media=include_media,
                            media_kinds=media_kinds,
                            media_written=media_written,
                            avatar_written=avatar_written,
                            report=report,
                            allow_process_key_extract=allow_process_key_extract,
                            media_db_path=media_db_path,
                            media_index=media_index,
                            job=job,
                            lock=self._lock,
                        )
                    elif export_format == "html":
                        exported_count = _write_conversation_html(
                            zf=zf,
                            conv_dir=conv_dir,
                            account_dir=account_dir,
                            conv_username=conv_username,
                            conv_name=conv_name,
                            conv_avatar_path=conv_avatar_path,
                            conv_is_group=conv_is_group,
                            self_avatar_path=self_avatar_path,
                            session_items=session_items,
                            download_remote_media=remote_download_enabled,
                            remote_written=remote_written,
                            html_page_size=html_page_size,
                            start_time=st,
                            end_time=et,
                            want_types=want_types,
                            local_types=local_types,
                            source=source_norm,
                            rt_conn=rt_conn,
                            resource_conn=resource_conn,
                            resource_chat_id=chat_id,
                            head_image_conn=head_image_conn,
                            resolve_display_name=resolve_display_name,
                            privacy_mode=privacy_mode,
                            include_media=include_media,
                            media_kinds=media_kinds,
                            media_written=media_written,
                            avatar_written=avatar_written,
                            report=report,
                            allow_process_key_extract=allow_process_key_extract,
                            media_db_path=media_db_path,
                            media_index=media_index,
                            job=job,
                            lock=self._lock,
                        )
                    else:
                        exported_count = _write_conversation_json(
                            zf=zf,
                            conv_dir=conv_dir,
                            account_dir=account_dir,
                            conv_username=conv_username,
                            conv_name=conv_name,
                            conv_avatar_path=conv_avatar_path,
                            conv_is_group=conv_is_group,
                            start_time=st,
                            end_time=et,
                            want_types=want_types,
                            local_types=local_types,
                            source=source_norm,
                            rt_conn=rt_conn,
                            resource_conn=resource_conn,
                            resource_chat_id=chat_id,
                            head_image_conn=head_image_conn,
                            resolve_display_name=resolve_display_name,
                            privacy_mode=privacy_mode,
                            include_media=include_media,
                            media_kinds=media_kinds,
                            media_written=media_written,
                            avatar_written=avatar_written,
                            report=report,
                            allow_process_key_extract=allow_process_key_extract,
                            media_db_path=media_db_path,
                            media_index=media_index,
                            job=job,
                            lock=self._lock,
                        )

                    _safe_trace(
                        trace,
                        "conversation_writer_done",
                        index=idx,
                        conversation=conv_username,
                        displayName=conv_name,
                        format=export_format,
                        durationMs=_elapsed_ms(phase_started),
                        exportedCount=exported_count,
                        mediaCopied=job.progress.media_copied,
                        mediaMissing=job.progress.media_missing,
                    )
                    _raise_if_job_cancelled(job, "conversation_writer_done", trace, index=idx, conversation=conv_username)

                    phase_started = time.perf_counter()
                    meta = {
                        "schemaVersion": 1,
                        "username": "" if privacy_mode else conv_username,
                        "displayName": "已隐藏" if privacy_mode else conv_name,
                        "avatarPath": "" if privacy_mode else (conv_avatar_path or ""),
                        "isGroup": bool(conv_is_group),
                        "exportedAt": _now_iso(),
                        "messageCount": int(exported_count),
                    }
                    zf.writestr(f"{conv_dir}/meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
                    if export_format == "html":
                        html_index_items.append({"convDir": conv_dir, "meta": meta})

                    with self._lock:
                        job.progress.current_conversation_messages_exported = int(exported_count)
                        job.progress.current_conversation_messages_total = int(exported_count)
                        job.progress.conversations_done += 1
                    _safe_trace(
                        trace,
                        "conversation_done",
                        index=idx,
                        conversation=conv_username,
                        durationMs=_elapsed_ms(conv_started),
                        metaWriteMs=_elapsed_ms(phase_started),
                        conversationsDone=job.progress.conversations_done,
                        exportedCount=exported_count,
                    )

                if export_format == "html":
                    phase_started = time.perf_counter()
                    def esc_text(v: Any) -> str:
                        return html.escape(str(v or ""), quote=False)

                    def esc_attr(v: Any) -> str:
                        return html.escape(str(v or ""), quote=True)

                    parts: list[str] = []
                    parts.append("<!doctype html>\n")
                    parts.append('<html lang="zh-CN">\n')
                    parts.append("<head>\n")
                    parts.append('  <meta charset="utf-8" />\n')
                    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1" />\n')
                    parts.append("  <title>聊天记录导出</title>\n")
                    html_assets = dict(job.options.get("_htmlAssets") or {})
                    css_asset_path = str(html_assets.get("cssPath") or _html_export_asset_paths(job.export_id)[0])
                    js_asset_path = str(html_assets.get("jsPath") or _html_export_asset_paths(job.export_id)[1])
                    integrity_asset_path = str(html_assets.get("integrityPath") or _html_export_asset_paths(job.export_id)[2])
                    css_integrity = str(html_assets.get("cssIntegrity") or "")
                    js_integrity = str(html_assets.get("jsIntegrity") or "")
                    parts.append(_html_export_gate_style())
                    # Do not use native `integrity=` here: Chrome blocks SRI on file://
                    # because it cannot enforce CORS. Keep hashes in inert data attrs
                    # and let the export integrity checker verify them instead.
                    parts.append(f'  <link id="wceStyle" rel="stylesheet" href="{esc_attr(css_asset_path)}" data-wce-sri="{esc_attr(css_integrity)}" />\n')
                    parts.append(_html_export_integrity_script_tag(src=integrity_asset_path))
                    parts.append(f'  <script defer src="{esc_attr(js_asset_path)}" data-wce-sri="{esc_attr(js_integrity)}"></script>\n')
                    parts.append("</head>\n")
                    parts.append("<body>\n")
                    parts.append(
                        '  <div id="wceJsMissing" style="position:fixed;top:0;left:0;right:0;z-index:9999;background:#FEF3C7;color:#92400E;border-bottom:1px solid #F59E0B;padding:8px 12px;font-size:12px;line-height:1.4">'
                        "提示：此页面需要 JavaScript 才能使用“合并聊天记录”等交互功能。若该提示一直存在，请确认已完整解压导出目录，并检查 assets/_wce/ 下的运行时文件是否完整。</div>\n"
                    )
                    parts.append('<div class="wce-index">\n')
                    parts.append('  <div class="wce-index-container">\n')
                    parts.append('    <h1 class="wce-index-title">聊天记录导出（HTML）</h1>\n')
                    parts.append(
                        f'    <p class="wce-index-sub">账号: {esc_text("hidden" if privacy_mode else account_dir.name)} · 会话数: {len(html_index_items)} · 导出时间: {esc_text(_now_iso())}</p>\n'
                    )
                    parts.append('    <div class="wce-index-card">\n')

                    for item in html_index_items:
                        conv_dir0 = str(item.get("convDir") or "").strip()
                        meta0 = item.get("meta") or {}
                        display_name = str(meta0.get("displayName") or "会话").strip() or "会话"
                        avatar_path = str(meta0.get("avatarPath") or "").strip()
                        try:
                            msg_count = int(meta0.get("messageCount") or 0)
                        except Exception:
                            msg_count = 0

                        href = f"{conv_dir0}/messages.html" if conv_dir0 else ""
                        parts.append(f'      <a class="wce-index-item" href="{esc_attr(href)}">\n')
                        parts.append('        <div class="wce-session-avatar" aria-hidden="true">')
                        if avatar_path:
                            parts.append(
                                f'<img src="{esc_attr(avatar_path)}" alt="avatar" referrerpolicy="no-referrer" />'
                            )
                        else:
                            parts.append(
                                f'<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:700;background-color:#4B5563">{esc_text(display_name[:1] or "?")}</div>'
                            )
                        parts.append("</div>\n")
                        parts.append('        <div class="wce-session-meta">\n')
                        parts.append(f'          <div class="wce-session-name">{esc_text(display_name)}</div>\n')
                        parts.append(f'          <div class="wce-session-sub">共 {msg_count} 条消息</div>\n')
                        parts.append("        </div>\n")
                        parts.append("      </a>\n")

                    parts.append("    </div>\n")
                    parts.append('    <p class="wce-index-sub" style="margin-top:16px">提示：解压后直接打开本文件；媒体文件位于 media/ 目录。</p>\n')
                    parts.append("  </div>\n")
                    parts.append("</div>\n")
                    parts.append(_html_export_attribution_html())
                    parts.append("</body>\n")
                    parts.append("</html>\n")
                    zf.writestr("index.html", _minify_html_for_export("".join(parts)))
                    _safe_trace(
                        trace,
                        "html_index_written",
                        durationMs=_elapsed_ms(phase_started),
                        conversations=len(html_index_items),
                    )
                    _raise_if_job_cancelled(job, "html_index_written", trace)

                phase_started = time.perf_counter()
                manifest = {
                    "schemaVersion": 1,
                    "exportedAt": _now_iso(),
                    "exportId": job.export_id,
                    "account": "hidden" if privacy_mode else account_dir.name,
                    "source": source_norm,
                    "format": export_format,
                    "scope": scope,
                    "filters": {
                        "startTime": st,
                        "endTime": et,
                        "messageTypes": sorted(want_types) if want_types else None,
                        "includeHidden": include_hidden,
                        "includeOfficial": include_official,
                    },
                    "options": {
                        "includeMedia": include_media,
                        "mediaKinds": media_kinds,
                        "allowProcessKeyExtract": allow_process_key_extract,
                        "downloadRemoteMedia": bool(download_remote_media),
                        "htmlPageSize": int(html_page_size) if export_format == "html" else None,
                        "privacyMode": privacy_mode,
                        "sourceRequested": source_requested,
                    },
                    "stats": {
                        "conversations": len(target_usernames),
                        "messagesExported": job.progress.messages_exported,
                        "mediaCopied": job.progress.media_copied,
                        "mediaMissing": job.progress.media_missing,
                    },
                    "accountsAvailable": _list_decrypted_accounts(),
                }
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                zf.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))
                if export_format == "html":
                    try:
                        html_assets = dict(job.options.get("_htmlAssets") or {})
                        integrity_asset_path = str(html_assets.get("integrityPath") or _html_export_asset_paths(job.export_id)[2])
                        manifest_asset_path = str(html_assets.get("manifestPath") or _html_export_integrity_sidecar_paths(job.export_id)[0])
                        signature_asset_path = str(html_assets.get("signaturePath") or _html_export_integrity_sidecar_paths(job.export_id)[1])
                        sealed = _seal_html_export_with_native(
                            native_integrity=native_integrity,
                            export_id=job.export_id,
                            entries=zf.integrity_entries() if hasattr(zf, "integrity_entries") else [],
                            html_assets=html_assets,
                        )
                        zf.writestr(manifest_asset_path, str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""))
                        zf.writestr(signature_asset_path, str(sealed.get("signature") or "") + "\n")
                        zf.writestr(integrity_asset_path, str(sealed.get("bundle") or ""))
                    except Exception as e:
                        _safe_trace(trace, "html_integrity_bundle_failed", error=str(e))
                        raise
                _safe_trace(
                    trace,
                    "manifest_written",
                    durationMs=_elapsed_ms(phase_started),
                    messagesExported=job.progress.messages_exported,
                    mediaCopied=job.progress.media_copied,
                    mediaMissing=job.progress.media_missing,
                    errors=len(report.get("errors") or []),
                    missingMedia=len(report.get("missingMedia") or []),
                )

            _safe_trace(trace, "zip_closed", tmpZip=str(tmp_zip))
            _raise_if_job_cancelled(job, "before_finalize", trace)

            phase_started = time.perf_counter()
            if final_zip.exists():
                final_zip = (exports_root / f"{final_zip.stem}_{job.export_id}{final_zip.suffix}").resolve()
            tmp_zip.replace(final_zip)
            _safe_trace(trace, "zip_finalized", durationMs=_elapsed_ms(phase_started), finalZip=str(final_zip))

            with self._lock:
                job.status = "done"
                job.zip_path = final_zip
                job.finished_at = time.time()
            _safe_trace(
                trace,
                "job_done",
                durationMs=round(((job.finished_at or time.time()) - (job.started_at or job.created_at)) * 1000.0, 1),
                finalZip=str(final_zip),
                messagesExported=job.progress.messages_exported,
                mediaCopied=job.progress.media_copied,
                mediaMissing=job.progress.media_missing,
            )
        except _JobCancelled:
            try:
                if tmp_zip.exists():
                    tmp_zip.unlink()
            except Exception:
                pass
            with self._lock:
                job.status = "cancelled"
                job.finished_at = time.time()
            _safe_trace(
                trace,
                "job_cancelled",
                durationMs=round(((job.finished_at or time.time()) - (job.started_at or job.created_at)) * 1000.0, 1),
                messagesExported=job.progress.messages_exported,
                mediaCopied=job.progress.media_copied,
                mediaMissing=job.progress.media_missing,
            )
        finally:
            if realtime_paused:
                try:
                    resume_depth = CHAT_REALTIME_AUTOSYNC.resume_account(account_dir.name, reason=realtime_pause_reason)
                    _safe_trace(
                        trace,
                        "realtime_autosync_resumed",
                        account=account_dir.name,
                        reason=realtime_pause_reason,
                        depth=int(resume_depth),
                    )
                except Exception:
                    logger.exception("failed to resume realtime autosync account=%s export_id=%s", account_dir.name, job.export_id)
                    _safe_trace(
                        trace,
                        "realtime_autosync_resume_failed",
                        account=account_dir.name,
                        reason=realtime_pause_reason,
                    )
            try:
                if resource_conn is not None:
                    resource_conn.close()
            except Exception:
                pass
            try:
                if head_image_conn is not None:
                    head_image_conn.close()
            except Exception:
                pass


def _resolve_export_targets(
    *,
    account_dir: Path,
    scope: ExportScope,
    usernames: list[str],
    include_hidden: bool,
    include_official: bool,
    source: str = "decrypted",
    rt_conn: Any | None = None,
) -> list[str]:
    if scope == "selected":
        uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
        return uniq

    if source == "realtime":
        if rt_conn is None:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        with rt_conn.lock:
            raw_sessions = _wcdb_get_sessions(rt_conn.handle)
        rows = _normalize_realtime_session_rows(raw_sessions)

        def should_include_rt(item: dict[str, Any]) -> bool:
            u = str(item.get("username") or "").strip()
            if not u or u == account_dir.name:
                return False
            if not include_hidden and int(item.get("is_hidden") or 0) == 1:
                return False
            if not _should_keep_session(u, include_official=include_official):
                return False
            if scope == "groups" and (not u.endswith("@chatroom")):
                return False
            if scope == "singles" and u.endswith("@chatroom"):
                return False
            return True

        out: list[str] = []
        seen: set[str] = set()
        for item in rows:
            u = str(item.get("username") or "").strip()
            if u in seen or (not should_include_rt(item)):
                continue
            seen.add(u)
            out.append(u)
        return out

    session_rows, session_hidden_by_username = _load_export_session_targets(account_dir)
    contact_usernames = _load_export_contact_usernames(account_dir)
    discovered_message_targets = _load_message_backed_export_targets(
        account_dir=account_dir,
        seed_usernames=contact_usernames,
    )

    def should_include(u: str) -> bool:
        if not u or u == account_dir.name:
            return False
        if not include_hidden and int(session_hidden_by_username.get(u) or 0) == 1:
            return False
        if not _should_keep_session(u, include_official=include_official):
            return False
        if scope == "groups" and (not u.endswith("@chatroom")):
            return False
        if scope == "singles" and u.endswith("@chatroom"):
            return False
        return True

    out: list[str] = []
    seen: set[str] = set()
    for u, _sort_ts in session_rows:
        if u in seen or (not should_include(u)):
            continue
        seen.add(u)
        out.append(u)

    for u, _sort_ts in sorted(discovered_message_targets.items(), key=lambda item: (-int(item[1] or 0), item[0])):
        if u in seen or (not should_include(u)):
            continue
        seen.add(u)
        out.append(u)

    return out


def _pick_case_insensitive_value(item: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in item and item[k] is not None:
            return item[k]
        lk = str(k).lower()
        for kk, vv in item.items():
            if str(kk).lower() == lk and vv is not None:
                return vv
    return None


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _normalize_realtime_session_rows(raw_sessions: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw_sessions or []:
        if not isinstance(item, dict):
            continue
        username = str(_pick_case_insensitive_value(item, "username", "user_name", "UserName") or "").strip()
        if not username:
            continue
        out.append(
            {
                "username": username,
                "is_hidden": _to_int(_pick_case_insensitive_value(item, "is_hidden", "isHidden")),
                "sort_timestamp": _to_int(
                    _pick_case_insensitive_value(item, "sort_timestamp", "sortTimestamp", "last_timestamp", "lastTimestamp")
                ),
                "summary": str(_pick_case_insensitive_value(item, "summary", "Summary") or ""),
                "draft": str(_pick_case_insensitive_value(item, "draft", "Draft") or ""),
                "last_msg_type": _to_int(_pick_case_insensitive_value(item, "last_msg_type", "lastMsgType")),
                "last_msg_sub_type": _to_int(_pick_case_insensitive_value(item, "last_msg_sub_type", "lastMsgSubType")),
            }
        )
    out.sort(key=lambda r: int(r.get("sort_timestamp") or 0), reverse=True)
    return out


def _load_export_session_targets(account_dir: Path) -> tuple[list[tuple[str, int]], dict[str, int]]:
    session_db_path = account_dir / "session.db"
    if not session_db_path.exists():
        return [], {}

    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        columns = _sqlite_table_columns(conn, "SessionTable")
        if "username" not in columns:
            return [], {}

        hidden_expr = "is_hidden" if "is_hidden" in columns else "0"
        if "sort_timestamp" in columns:
            sort_expr = "sort_timestamp"
        elif "last_timestamp" in columns:
            sort_expr = "last_timestamp"
        else:
            sort_expr = "0"

        rows = conn.execute(
            f"""
            SELECT username, {hidden_expr} AS is_hidden, {sort_expr} AS sort_timestamp
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            """,
        ).fetchall()
    finally:
        conn.close()

    out: list[tuple[str, int]] = []
    hidden_by_username: dict[str, int] = {}
    seen: set[str] = set()
    for r in rows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        try:
            hidden = int(r["is_hidden"] or 0)
        except Exception:
            hidden = 0
        if hidden:
            hidden_by_username[u] = 1
        else:
            hidden_by_username.setdefault(u, 0)
        if u in seen:
            continue
        seen.add(u)
        try:
            sort_ts = int(r["sort_timestamp"] or 0)
        except Exception:
            sort_ts = 0
        out.append((u, sort_ts))
    return out, hidden_by_username


def _sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({_quote_ident(table_name)})").fetchall()
    except Exception:
        return set()

    columns: set[str] = set()
    for row in rows:
        try:
            name = str(row["name"] if isinstance(row, sqlite3.Row) else row[1] or "").strip().lower()
        except Exception:
            name = ""
        if name:
            columns.add(name)
    return columns


def _load_export_contact_usernames(account_dir: Path) -> set[str]:
    contact_db_path = account_dir / "contact.db"
    if not contact_db_path.exists():
        return set()

    out: set[str] = set()
    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        for table in ("contact", "stranger"):
            columns = _sqlite_table_columns(conn, table)
            if "username" not in columns:
                continue
            try:
                rows = conn.execute(f"SELECT username FROM {_quote_ident(table)}").fetchall()
            except Exception:
                continue
            for row in rows:
                try:
                    username = str(row["username"] or "").strip()
                except Exception:
                    username = ""
                if username:
                    out.add(username)
    finally:
        conn.close()
    return out


def _load_name2id_usernames(conn: sqlite3.Connection) -> set[str]:
    columns = _sqlite_table_columns(conn, "Name2Id")
    username_col = "user_name" if "user_name" in columns else ("username" if "username" in columns else "")
    if not username_col:
        return set()

    out: set[str] = set()
    try:
        rows = conn.execute(f"SELECT {_quote_ident(username_col)} AS username FROM Name2Id").fetchall()
    except Exception:
        return out
    for row in rows:
        try:
            username = str(row["username"] if isinstance(row, sqlite3.Row) else row[0] or "").strip()
        except Exception:
            username = ""
        if username:
            out.add(username)
    return out


def _message_table_latest_timestamp(conn: sqlite3.Connection, table_name: str) -> Optional[int]:
    quoted = _quote_ident(table_name)
    try:
        row = conn.execute(f"SELECT MAX(create_time) FROM {quoted}").fetchone()
        if row is not None and row[0] is not None:
            return int(row[0] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(f"SELECT 1 FROM {quoted} LIMIT 1").fetchone()
        if row is not None:
            return 0
    except Exception:
        pass
    return None


def _load_message_backed_export_targets(*, account_dir: Path, seed_usernames: set[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for db_path in _iter_message_db_paths(account_dir):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [str(r["name"] if isinstance(r, sqlite3.Row) else r[0] or "") for r in rows]
            lower_to_actual = {name.lower(): name for name in table_names if name}
            if not lower_to_actual:
                continue

            candidates = set(seed_usernames)
            candidates.update(_load_name2id_usernames(conn))
            for username in candidates:
                u = str(username or "").strip()
                if not u or u == account_dir.name:
                    continue
                table_name = _resolve_msg_table_name_by_map(lower_to_actual, u)
                if not table_name:
                    continue
                latest_ts = _message_table_latest_timestamp(conn, table_name)
                if latest_ts is None:
                    continue
                previous_ts = out.get(u)
                if previous_ts is None or int(latest_ts or 0) > int(previous_ts or 0):
                    out[u] = int(latest_ts or 0)
        except Exception:
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return out


def build_chat_export_targets_preview(
    *,
    account_dir: Path,
    source: str = "auto",
    rt_conn: Any | None = None,
    include_hidden: bool = True,
    include_official: bool = False,
    base_url: str = "",
) -> dict[str, Any]:
    source_norm = _normalize_chat_source(source, default="auto")
    if source_norm in {"auto", "realtime"}:
        source_norm = "realtime"
        if rt_conn is None:
            try:
                rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
            except WCDBRealtimeError as e:
                raise ValueError(f"Realtime export targets require WCDB/direct mode but connection failed: {e}") from e

    targets = _resolve_export_targets(
        account_dir=account_dir,
        scope="all",
        usernames=[],
        include_hidden=bool(include_hidden),
        include_official=bool(include_official),
        source=source_norm,
        rt_conn=rt_conn,
    )
    session_hidden_by_username: dict[str, int] = {}
    if source_norm == "realtime" and rt_conn is not None:
        with rt_conn.lock:
            session_raw = _wcdb_get_sessions(rt_conn.handle)
        session_rows_norm = _normalize_realtime_session_rows(session_raw)
        session_usernames = {str(r.get("username") or "").strip() for r in session_rows_norm if str(r.get("username") or "").strip()}
        session_hidden_by_username = {
            str(r.get("username") or "").strip(): int(r.get("is_hidden") or 0)
            for r in session_rows_norm
            if str(r.get("username") or "").strip()
        }
        try:
            with rt_conn.lock:
                wcdb_names = _wcdb_get_display_names(rt_conn.handle, targets)
        except Exception:
            wcdb_names = {}
    else:
        session_rows, session_hidden_by_username = _load_export_session_targets(account_dir)
        session_usernames = {u for u, _sort_ts in session_rows}
        wcdb_names = {}
    contact_rows = _load_contact_rows(account_dir / "contact.db", targets)
    base = str(base_url or "").rstrip("/")

    conversations: list[dict[str, Any]] = []
    for u in targets:
        row = contact_rows.get(u)
        display_name = str(wcdb_names.get(u) or "").strip()
        if not display_name:
            display_name = _pick_display_name(row, u) if row is not None else u
        avatar_path = _build_avatar_url(account_dir.name, u)
        conversations.append(
            {
                "username": u,
                "name": display_name,
                "displayName": display_name,
                "isGroup": bool(u.endswith("@chatroom")),
                "isHidden": bool(int(session_hidden_by_username.get(u) or 0) == 1),
                "inSessionList": bool(u in session_usernames),
                "avatar": f"{base}{avatar_path}" if base else avatar_path,
            }
        )

    group_count = sum(1 for item in conversations if bool(item.get("isGroup")))
    return {
        "status": "success",
        "account": account_dir.name,
        "source": source_norm,
        "includeHidden": bool(include_hidden),
        "includeOfficial": bool(include_official),
        "targets": conversations,
        "counts": {
            "total": len(conversations),
            "groups": group_count,
            "singles": len(conversations) - group_count,
        },
    }


def get_chat_export_targets_preview(
    *,
    account: Optional[str],
    source: Optional[str] = "auto",
    include_hidden: bool = True,
    include_official: bool = False,
    base_url: str = "",
) -> dict[str, Any]:
    account_dir = _resolve_account_dir(account)
    source_norm = _normalize_chat_source(source, default="auto")
    return build_chat_export_targets_preview(
        account_dir=account_dir,
        source=source_norm,
        include_hidden=include_hidden,
        include_official=include_official,
        base_url=base_url,
    )


def _conversation_dir_name(
    idx: int,
    display_name: str,
    username: str,
    is_group: bool,
    privacy_mode: bool,
) -> str:
    h = uuid.uuid5(uuid.NAMESPACE_DNS, username).hex[:8] if username else uuid.uuid4().hex[:8]
    if privacy_mode:
        kind = "group" if is_group else "single"
        return f"{idx:04d}_{kind}_{h}"

    base = _safe_name(display_name, max_len=40) or "conversation"
    user_part = _safe_name(username, max_len=50) or "unknown"
    return f"{idx:04d}_{base}_{user_part}_{h}"


def _normalize_realtime_message_item_for_export(item: dict[str, Any], *, account_dir: Path, conv_username: str) -> _Row:
    message_content = _pick_case_insensitive_value(item, "message_content", "messageContent", "MessageContent")
    compress_content = _pick_case_insensitive_value(item, "compress_content", "compressContent", "CompressContent")
    raw_text = _decode_message_content(compress_content, message_content).strip()
    sender_username = str(
        _pick_case_insensitive_value(item, "sender_username", "senderUsername", "sender", "SenderUsername") or ""
    ).strip()

    is_sent = False
    sent_value = _pick_case_insensitive_value(item, "computed_is_send", "computed_isSend", "computed_is_sent", "is_send", "isSent")
    if sent_value is not None:
        try:
            is_sent = bool(int(sent_value))
        except Exception:
            is_sent = bool(sent_value)
    if not is_sent:
        try:
            if sender_username and sender_username.lower() == account_dir.name.lower():
                is_sent = True
        except Exception:
            pass

    is_group = bool(str(conv_username or "").endswith("@chatroom"))
    if is_sent:
        sender_username = account_dir.name
    elif (not is_group) and (not sender_username):
        sender_username = conv_username

    table_name = str(_pick_case_insensitive_value(item, "table_name", "tableName") or "").strip()
    if not table_name:
        table_name = f"msg_{hashlib.md5(str(conv_username or '').strip().encode('utf-8')).hexdigest()}"
    db_path = str(_pick_case_insensitive_value(item, "_db_path", "db_path", "dbPath") or "").strip()
    db_stem = Path(db_path).stem if db_path else f"realtime_{account_dir.name}"
    return _Row(
        db_stem=db_stem,
        table_name=table_name,
        local_id=_to_int(_pick_case_insensitive_value(item, "local_id", "localId")),
        server_id=_to_int(_pick_case_insensitive_value(item, "server_id", "serverId", "MsgSvrID")),
        local_type=_to_int(_pick_case_insensitive_value(item, "local_type", "localType", "Type", "type")),
        sort_seq=_to_int(_pick_case_insensitive_value(item, "sort_seq", "sortSeq", "SortSeq")),
        create_time=_to_int(_pick_case_insensitive_value(item, "create_time", "createTime", "CreateTime")),
        raw_text=raw_text,
        sender_username=sender_username,
        is_sent=bool(is_sent),
        packed_info_data=_pick_case_insensitive_value(item, "packed_info_data", "packedInfoData", "PackedInfoData"),
    )


def _iter_realtime_rows_for_conversation(
    *,
    rt_conn: Any,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
    local_types: Optional[set[int]] = None,
) -> Iterable[_Row]:
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    result = read_all_realtime_message_rows(
        rt_conn=rt_conn,
        account_dir=account_dir,
        username=conv_username,
        db_storage_dir=db_storage_dir,
        exec_query=_wcdb_exec_query,
        open_cursor=_wcdb_open_message_cursor,
        fetch_batch=_wcdb_fetch_message_batch,
        close_cursor=_wcdb_close_message_cursor,
        get_messages=_wcdb_get_messages,
        normalize_item=lambda item: dict(item),
        start_time=start_time,
        end_time=end_time,
        local_types=local_types,
    )
    logger.info(
        "[chat-export] realtime messages loaded account=%s conversation=%s strategy=%s rows=%s "
        "tables=%s databases=%s authoritative=%s diagnostics=%s",
        account_dir.name,
        conv_username,
        result.strategy,
        len(result.rows),
        result.tables_found,
        result.databases_probed,
        result.authoritative,
        list(result.diagnostics),
    )
    rows = [
        _normalize_realtime_message_item_for_export(item, account_dir=account_dir, conv_username=conv_username)
        for item in result.rows
        if isinstance(item, dict)
    ]
    rows = [row for row in rows if row.local_id > 0]
    return rows


def _estimate_conversation_message_count(
    *,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
    local_types: Optional[set[int]] = None,
    source: str = "decrypted",
    rt_conn: Any | None = None,
) -> int:
    if source == "realtime":
        if rt_conn is None:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        direct_count = count_realtime_message_rows_via_exec(
            rt_conn=rt_conn,
            account_dir=account_dir,
            username=conv_username,
            db_storage_dir=_resolve_account_db_storage_dir(account_dir),
            exec_query=_wcdb_exec_query,
            start_time=start_time,
            end_time=end_time,
            local_types=local_types,
        )
        if direct_count is not None:
            return int(direct_count)
        if start_time is None and end_time is None and not local_types:
            with rt_conn.lock:
                return int(_wcdb_get_message_count(rt_conn.handle, conv_username) or 0)
        return sum(
            1
            for _ in _iter_realtime_rows_for_conversation(
                rt_conn=rt_conn,
                account_dir=account_dir,
                conv_username=conv_username,
                start_time=start_time,
                end_time=end_time,
                local_types=local_types,
            )
        )

    total = 0
    for db_path in _iter_message_db_paths(account_dir):
        conn = sqlite3.connect(str(db_path))
        try:
            table = _resolve_msg_table_name(conn, conv_username)
            if not table:
                continue
            quoted = _quote_ident(table)
            where = []
            params: list[Any] = []
            if local_types:
                lt = sorted({int(x) for x in local_types if int(x) != 0})
                if lt:
                    placeholders = ",".join(["?"] * len(lt))
                    where.append(f"local_type IN ({placeholders})")
                    params.extend(lt)
            if start_time is not None:
                where.append("create_time >= ?")
                params.append(int(start_time))
            if end_time is not None:
                where.append("create_time <= ?")
                params.append(int(end_time))
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""
            row = conn.execute(f"SELECT COUNT(1) FROM {quoted}{where_sql}", params).fetchone()
            if row and row[0] is not None:
                total += int(row[0])
        finally:
            conn.close()
    return total


@dataclass
class _Row:
    db_stem: str
    table_name: str
    local_id: int
    server_id: int
    local_type: int
    sort_seq: int
    create_time: int
    raw_text: str
    sender_username: str
    is_sent: bool
    packed_info_data: Any = None


def _iter_rows_for_conversation(
    *,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
    local_types: Optional[set[int]] = None,
    source: str = "decrypted",
    rt_conn: Any | None = None,
) -> Iterable[_Row]:
    if source == "realtime":
        if rt_conn is None:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        return _iter_realtime_rows_for_conversation(
            rt_conn=rt_conn,
            account_dir=account_dir,
            conv_username=conv_username,
            start_time=start_time,
            end_time=end_time,
            local_types=local_types,
        )

    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return []

    account_wxid = account_dir.name

    def iter_db(db_path: Path) -> Iterable[_Row]:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            table_name = _resolve_msg_table_name(conn, conv_username)
            if not table_name:
                return

            # Force sqlite3 to return TEXT as raw bytes for this query, so we can zstd-decompress
            # compress_content reliably (and avoid losing binary payloads).
            conn.text_factory = bytes

            my_rowid = None
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (account_wxid,),
                ).fetchone()
                if r is not None:
                    my_rowid = int(r[0])
            except Exception:
                my_rowid = None

            quoted = _quote_ident(table_name)
            has_packed_info_data = False
            try:
                cols = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
                has_packed_info_data = any(
                    _decode_sqlite_text(c[1]).strip().lower() == "packed_info_data" for c in cols
                )
            except Exception:
                has_packed_info_data = False

            where = []
            params: list[Any] = []
            if local_types:
                lt = sorted({int(x) for x in local_types if int(x) != 0})
                if lt:
                    placeholders = ",".join(["?"] * len(lt))
                    where.append(f"m.local_type IN ({placeholders})")
                    params.extend(lt)
            if start_time is not None:
                where.append("m.create_time >= ?")
                params.append(int(start_time))
            if end_time is not None:
                where.append("m.create_time <= ?")
                params.append(int(end_time))
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""

            packed_select = (
                "m.packed_info_data AS packed_info_data, " if has_packed_info_data else "NULL AS packed_info_data, "
            )
            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "n.user_name AS sender_username "
                f"FROM {quoted} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"{where_sql} "
                "ORDER BY m.create_time ASC, m.sort_seq ASC, m.local_id ASC "
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, "
                + packed_select
                + "'' AS sender_username "
                f"FROM {quoted} m "
                f"{where_sql} "
                "ORDER BY m.create_time ASC, m.sort_seq ASC, m.local_id ASC "
            )

            try:
                cur = conn.execute(sql_with_join, params)
            except Exception:
                cur = conn.execute(sql_no_join, params)

            batch = 400
            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break
                for r in rows:
                    local_id = int(r["local_id"] or 0)
                    server_id = int(r["server_id"] or 0)
                    local_type = int(r["local_type"] or 0)
                    sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                    create_time = int(r["create_time"] or 0)
                    sender_username = _decode_sqlite_text(r["sender_username"]).strip()

                    is_sent = False
                    if my_rowid is not None:
                        try:
                            is_sent = int(r["real_sender_id"] or 0) == int(my_rowid)
                        except Exception:
                            is_sent = False

                    raw_text = _decode_message_content(r["compress_content"], r["message_content"]).strip()

                    is_group = bool(conv_username.endswith("@chatroom"))

                    if is_sent:
                        sender_username = account_wxid
                    elif (not is_group) and (not sender_username):
                        sender_username = conv_username

                    yield _Row(
                        db_stem=db_path.stem,
                        table_name=table_name,
                        local_id=local_id,
                        server_id=server_id,
                        local_type=local_type,
                        sort_seq=sort_seq,
                        create_time=create_time,
                        raw_text=raw_text,
                        sender_username=sender_username,
                        is_sent=bool(is_sent),
                        packed_info_data=r["packed_info_data"],
                    )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    streams = [iter_db(p) for p in db_paths]

    def sort_key(r: _Row) -> tuple[int, int, int]:
        return (int(r.create_time or 0), int(r.sort_seq or 0), int(r.local_id or 0))

    return heapq.merge(*streams, key=sort_key)


def _parse_message_for_export(
    *,
    row: _Row,
    conv_username: str,
    is_group: bool,
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    sender_alias: str = "",
    resolve_display_name: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    raw_text = row.raw_text or ""
    sender_username = str(row.sender_username or "").strip()

    if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
        sender_prefix, raw_text = _split_group_sender_prefix(raw_text, sender_username, sender_alias)
        if sender_prefix and (not sender_username):
            sender_username = sender_prefix

    if is_group and raw_text and (raw_text.startswith("<") or raw_text.startswith('"<')):
        xml_sender = _extract_sender_from_group_xml(raw_text)
        if xml_sender:
            sender_username = xml_sender

    local_type = int(row.local_type or 0)
    is_sent = bool(row.is_sent)

    render_type = "text"
    content_text = raw_text
    title = ""
    url = ""
    from_name = ""
    from_username = ""
    link_type = ""
    link_style = ""
    record_item = ""
    image_md5 = ""
    image_md5_candidates: list[str] = []
    image_file_id = ""
    image_file_id_candidates: list[str] = []
    emoji_md5 = ""
    emoji_url = ""
    thumb_url = ""
    image_url = ""
    video_md5 = ""
    video_thumb_md5 = ""
    video_file_id = ""
    video_thumb_file_id = ""
    video_url = ""
    video_thumb_url = ""
    voice_length = ""
    quote_username = ""
    quote_server_id = ""
    quote_type = ""
    quote_thumb_url = ""
    quote_voice_length = ""
    quote_title = ""
    quote_content = ""
    object_id = ""
    object_nonce_id = ""
    amount = ""
    cover_url = ""
    file_size = ""
    pay_sub_type = ""
    transfer_status = ""
    file_md5 = ""
    transfer_id = ""
    voip_type = ""
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_poiname = ""
    location_label = ""

    if local_type == 10000:
        render_type = "system"
        system_display_name_resolver = None
        if resolve_display_name is not None:
            def system_display_name_resolver(username: str, fallback_display_name: str) -> str:
                resolved = str(resolve_display_name(username) or "").strip()
                if resolved and resolved != username:
                    return resolved
                fallback = str(fallback_display_name or "").strip()
                return fallback or resolved or username
        content_text = _parse_system_message_content(
            raw_text,
            resolve_display_name=system_display_name_resolver,
        )
    elif local_type == 49:
        parsed = _parse_app_message(raw_text)
        render_type = str(parsed.get("renderType") or "text")
        content_text = str(parsed.get("content") or "")
        title = str(parsed.get("title") or "")
        url = str(parsed.get("url") or "")
        from_name = str(parsed.get("from") or "")
        from_username = str(parsed.get("fromUsername") or "")
        link_type = str(parsed.get("linkType") or "")
        link_style = str(parsed.get("linkStyle") or "")
        object_id = str(parsed.get("objectId") or "")
        object_nonce_id = str(parsed.get("objectNonceId") or "")
        record_item = str(parsed.get("recordItem") or "")
        quote_username = str(parsed.get("quoteUsername") or "")
        quote_server_id = str(parsed.get("quoteServerId") or "")
        quote_type = str(parsed.get("quoteType") or "")
        quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
        quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
        quote_title = str(parsed.get("quoteTitle") or "")
        quote_content = str(parsed.get("quoteContent") or "")
        amount = str(parsed.get("amount") or "")
        cover_url = str(parsed.get("coverUrl") or "")
        thumb_url = str(parsed.get("thumbUrl") or "")
        file_size = str(parsed.get("size") or "")
        pay_sub_type = str(parsed.get("paySubType") or "")
        file_md5 = str(parsed.get("fileMd5") or "")
        transfer_id = str(parsed.get("transferId") or "")

        if render_type == "transfer":
            if not transfer_id:
                transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
            transfer_status = _infer_transfer_status_text(
                is_sent=is_sent,
                paysubtype=pay_sub_type,
                receivestatus=str(parsed.get("receiveStatus") or ""),
                sendertitle=str(parsed.get("senderTitle") or ""),
                receivertitle=str(parsed.get("receiverTitle") or ""),
                senderdes=str(parsed.get("senderDes") or ""),
                receiverdes=str(parsed.get("receiverDes") or ""),
            )
            if not content_text:
                content_text = transfer_status or "转账"
    elif local_type == 266287972401:
        render_type = "system"
        template = _extract_xml_tag_text(raw_text, "template")
        content_text = "[拍一拍]" if template else "[拍一拍]"
    elif local_type == 244813135921:
        render_type = "quote"
        parsed = _parse_app_message(raw_text)
        content_text = str(parsed.get("content") or "[引用消息]")
        quote_username = str(parsed.get("quoteUsername") or "")
        quote_server_id = str(parsed.get("quoteServerId") or "")
        quote_type = str(parsed.get("quoteType") or "")
        quote_thumb_url = str(parsed.get("quoteThumbUrl") or "")
        quote_voice_length = str(parsed.get("quoteVoiceLength") or "")
        quote_title = str(parsed.get("quoteTitle") or "")
        quote_content = str(parsed.get("quoteContent") or "")
    elif local_type == 48:
        parsed = _parse_location_message(raw_text)
        render_type = str(parsed.get("renderType") or "location")
        content_text = str(parsed.get("content") or "[Location]")
        location_lat = parsed.get("locationLat")
        location_lng = parsed.get("locationLng")
        location_poiname = str(parsed.get("locationPoiname") or "")
        location_label = str(parsed.get("locationLabel") or "")
    elif local_type == 3:
        render_type = "image"
        def add_md5(v: Any) -> None:
            s = str(v or "").strip().lower()
            if _is_md5(s) and s not in image_md5_candidates:
                image_md5_candidates.append(s)

        for k in [
            "md5",
            "hdmd5",
            "hevc_md5",
            "hevc_mid_md5",
            "cdnbigimgmd5",
            "cdnmidimgmd5",
            "cdnthumbmd5",
            "cdnthumd5",
            "imgmd5",
            "filemd5",
        ]:
            add_md5(_extract_xml_attr(raw_text, k))
            add_md5(_extract_xml_tag_text(raw_text, k))

        # Prefer message_resource.db md5 for local files: XML md5 frequently differs from the on-disk *.dat basename
        # (especially for *_t.dat thumbnails), causing offline media materialization to miss.
        if resource_conn is not None:
            try:
                md5_hit = _lookup_resource_md5(
                    resource_conn,
                    resource_chat_id,
                    message_local_type=local_type,
                    server_id=int(row.server_id or 0),
                    local_id=int(row.local_id or 0),
                    create_time=int(row.create_time or 0),
                )
            except Exception:
                md5_hit = ""

            md5_hit = str(md5_hit or "").strip().lower()
            if _is_md5(md5_hit):
                try:
                    image_md5_candidates.remove(md5_hit)
                except ValueError:
                    pass
                image_md5_candidates.insert(0, md5_hit)

        # Realtime/WCDB exports and newer decrypted tables may carry the real local media basename
        # in packed_info_data. Chat rendering already uses this field; keep HTML export aligned so
        # clipboard/pasted images with sparse XML still materialize offline instead of falling back to [图片].
        packed_md5 = _extract_md5_from_packed_info(getattr(row, "packed_info_data", None))
        if _is_md5(packed_md5):
            try:
                image_md5_candidates.remove(packed_md5)
            except ValueError:
                pass
            image_md5_candidates.insert(0, packed_md5)

        image_md5 = image_md5_candidates[0] if image_md5_candidates else ""

        url_or_id_candidates: list[str] = []

        def add_url_or_id(v: Any) -> None:
            s = str(v or "").strip()
            if s:
                try:
                    s = html.unescape(s).strip()
                except Exception:
                    pass
            if s and s not in url_or_id_candidates:
                url_or_id_candidates.append(s)

        for k in ["cdnthumburl", "cdnthumurl", "cdnmidimgurl", "cdnbigimgurl"]:
            add_url_or_id(_extract_xml_attr(raw_text, k))
            add_url_or_id(_extract_xml_tag_text(raw_text, k))

        for v in url_or_id_candidates:
            low = str(v or "").strip().lower()
            if low.startswith(("http://", "https://")):
                if not image_url:
                    image_url = str(v).strip()
                continue
            if str(v).startswith("//"):
                if not image_url:
                    image_url = "https:" + str(v).strip()
                continue
            if v and v not in image_file_id_candidates:
                image_file_id_candidates.append(v)

        image_file_id = image_file_id_candidates[0] if image_file_id_candidates else ""
        content_text = "[图片]"
    elif local_type == 34:
        render_type = "voice"
        duration = _extract_xml_attr(raw_text, "voicelength")
        voice_length = duration
        content_text = f"[语音 {duration}秒]" if duration else "[语音]"
    elif local_type == 43 or local_type == 62:
        render_type = "video"
        video_md5 = _extract_xml_attr(raw_text, "md5")
        video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
        video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
            raw_text, "cdnthumburl"
        )
        video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
            raw_text, "cdnvideourl"
        )

        video_thumb_url = (
            video_thumb_url_or_id
            if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
            else ""
        )
        video_url = (
            video_url_or_id if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://")) else ""
        )
        video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
        video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
        if (not video_thumb_md5) and resource_conn is not None:
            video_thumb_md5 = _lookup_resource_md5(
                resource_conn,
                resource_chat_id,
                message_local_type=local_type,
                server_id=int(row.server_id or 0),
                local_id=int(row.local_id or 0),
                create_time=int(row.create_time or 0),
            )
        packed_video_token = _extract_md5_from_packed_info(getattr(row, "packed_info_data", None))
        if _is_md5(packed_video_token):
            video_md5 = packed_video_token
            if not _is_md5(video_thumb_md5):
                video_thumb_md5 = packed_video_token
                video_thumb_file_id = ""
        content_text = "[视频]"
    elif local_type == 47:
        render_type = "emoji"
        emoji_md5 = _extract_xml_attr(raw_text, "md5")
        if not emoji_md5:
            emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
        emoji_url = _extract_xml_attr(raw_text, "cdnurl")
        if not emoji_url:
            emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
        if (not emoji_md5) and resource_conn is not None:
            emoji_md5 = _lookup_resource_md5(
                resource_conn,
                resource_chat_id,
                message_local_type=local_type,
                server_id=int(row.server_id or 0),
                local_id=int(row.local_id or 0),
                create_time=int(row.create_time or 0),
            )
        content_text = "[表情]"
    elif local_type == 50:
        render_type = "voip"
        try:
            import re as _re

            block = raw_text
            m_voip = _re.search(
                r"(<VoIPBubbleMsg[^>]*>.*?</VoIPBubbleMsg>)",
                raw_text,
                flags=_re.IGNORECASE | _re.DOTALL,
            )
            if m_voip:
                block = m_voip.group(1) or raw_text
            room_type = str(_extract_xml_tag_text(block, "room_type") or "").strip()
            if room_type == "0":
                voip_type = "video"
            elif room_type == "1":
                voip_type = "audio"

            voip_msg = str(_extract_xml_tag_text(block, "msg") or "").strip()
            content_text = voip_msg or "通话"
        except Exception:
            content_text = "通话"
    elif local_type != 1:
        if not content_text:
            content_text = _infer_message_brief_by_local_type(local_type)
        else:
            if content_text.startswith("<") or content_text.startswith('"<'):
                parsed_special = False
                if "<appmsg" in content_text.lower():
                    parsed = _parse_app_message(content_text)
                    rt = str(parsed.get("renderType") or "")
                    if rt and rt != "text":
                        parsed_special = True
                        render_type = rt
                        content_text = str(parsed.get("content") or content_text)
                        title = str(parsed.get("title") or title)
                        url = str(parsed.get("url") or url)
                        from_name = str(parsed.get("from") or from_name)
                        from_username = str(parsed.get("fromUsername") or from_username)
                        link_type = str(parsed.get("linkType") or link_type)
                        link_style = str(parsed.get("linkStyle") or link_style)
                        object_id = str(parsed.get("objectId") or object_id)
                        object_nonce_id = str(parsed.get("objectNonceId") or object_nonce_id)
                        record_item = str(parsed.get("recordItem") or record_item)
                        quote_username = str(parsed.get("quoteUsername") or quote_username)
                        quote_server_id = str(parsed.get("quoteServerId") or quote_server_id)
                        quote_type = str(parsed.get("quoteType") or quote_type)
                        quote_thumb_url = str(parsed.get("quoteThumbUrl") or quote_thumb_url)
                        quote_voice_length = str(parsed.get("quoteVoiceLength") or quote_voice_length)
                        quote_title = str(parsed.get("quoteTitle") or quote_title)
                        quote_content = str(parsed.get("quoteContent") or quote_content)
                        amount = str(parsed.get("amount") or amount)
                        cover_url = str(parsed.get("coverUrl") or cover_url)
                        thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                        file_size = str(parsed.get("size") or file_size)
                        pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                        file_md5 = str(parsed.get("fileMd5") or file_md5)
                        transfer_id = str(parsed.get("transferId") or transfer_id)

                        if render_type == "transfer":
                            if not transfer_id:
                                transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
                            transfer_status = _infer_transfer_status_text(
                                is_sent=is_sent,
                                paysubtype=pay_sub_type,
                                receivestatus=str(parsed.get("receiveStatus") or ""),
                                sendertitle=str(parsed.get("senderTitle") or ""),
                                receivertitle=str(parsed.get("receiverTitle") or ""),
                                senderdes=str(parsed.get("senderDes") or ""),
                                receiverdes=str(parsed.get("receiverDes") or ""),
                            )
                            if not content_text:
                                content_text = transfer_status or "转账"

                if not parsed_special:
                    t = _extract_xml_tag_text(content_text, "title")
                    d = _extract_xml_tag_text(content_text, "des")
                    content_text = t or d or _infer_message_brief_by_local_type(local_type)

    if not content_text:
        content_text = _infer_message_brief_by_local_type(local_type)

    if local_type == 266287972401:
        try:
            if raw_text:
                content_text = _parse_pat_message(raw_text, {})
        except Exception:
            pass

    return {
        "id": f"{row.db_stem}:{row.table_name}:{row.local_id}",
        "localId": row.local_id,
        "serverId": row.server_id,
        "createTime": row.create_time,
        "createTimeText": _format_ts(row.create_time),
        "sortSeq": row.sort_seq,
        "type": local_type,
        "renderType": render_type,
        "isSent": bool(is_sent),
        "senderUsername": sender_username,
        "conversationUsername": conv_username,
        "isGroup": bool(is_group),
        "content": content_text,
        "title": title,
        "url": url,
        "from": from_name,
        "fromUsername": from_username,
        "linkType": link_type,
        "linkStyle": link_style,
        "objectId": object_id,
        "objectNonceId": object_nonce_id,
        "recordItem": record_item,
        "thumbUrl": thumb_url,
        "imageMd5": image_md5,
        "imageFileId": image_file_id,
        "imageMd5Candidates": image_md5_candidates,
        "imageFileIdCandidates": image_file_id_candidates,
        "imageUrl": image_url,
        "emojiMd5": emoji_md5,
        "emojiUrl": emoji_url,
        "videoMd5": video_md5,
        "videoThumbMd5": video_thumb_md5,
        "videoFileId": video_file_id,
        "videoThumbFileId": video_thumb_file_id,
        "videoUrl": video_url,
        "videoThumbUrl": video_thumb_url,
        "voiceLength": voice_length,
        "quoteUsername": quote_username,
        "quoteServerId": quote_server_id,
        "quoteType": quote_type,
        "quoteThumbUrl": quote_thumb_url,
        "quoteVoiceLength": quote_voice_length,
        "quoteTitle": quote_title,
        "quoteContent": quote_content,
        "amount": amount,
        "coverUrl": cover_url,
        "fileSize": file_size,
        "fileMd5": file_md5,
        "paySubType": pay_sub_type,
        "transferStatus": transfer_status,
        "transferId": transfer_id,
        "voipType": voip_type,
        "locationLat": location_lat,
        "locationLng": location_lng,
        "locationPoiname": location_poiname,
        "locationLabel": location_label,
    }


def _write_conversation_json(
    *,
    zf: zipfile.ZipFile,
    conv_dir: str,
    account_dir: Path,
    conv_username: str,
    conv_name: str,
    conv_avatar_path: str,
    conv_is_group: bool,
    start_time: Optional[int],
    end_time: Optional[int],
    want_types: Optional[set[str]],
    local_types: Optional[set[int]],
    source: str = "decrypted",
    rt_conn: Any | None = None,
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    head_image_conn: Optional[sqlite3.Connection],
    resolve_display_name: Any,
    privacy_mode: bool,
    include_media: bool,
    media_kinds: list[MediaKind],
    media_written: dict[str, str],
    avatar_written: dict[str, str],
    report: dict[str, Any],
    allow_process_key_extract: bool,
    media_db_path: Path,
    media_index: Optional[MediaPathIndex],
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.json"
    exported = 0
    _trace_id, trace = create_perf_trace(
        logger,
        "chat_export_conversation_writer",
        exportId=job.export_id,
        format="json",
        conversation=conv_username,
    )
    _safe_trace(
        trace,
        "writer_started",
        convDir=conv_dir,
        displayName=conv_name,
        includeMedia=include_media,
        mediaKinds=media_kinds,
        privacyMode=privacy_mode,
        messageTypes=sorted(want_types) if want_types else None,
    )

    contact_conn: Optional[sqlite3.Connection] = None
    alias_cache: dict[str, str] = {}
    phase_started = time.perf_counter()
    if conv_is_group:
        try:
            contact_db_path = account_dir / "contact.db"
            if contact_db_path.exists():
                contact_conn = sqlite3.connect(str(contact_db_path))
        except Exception:
            contact_conn = None
    _safe_trace(
        trace,
        "alias_db_ready",
        durationMs=_elapsed_ms(phase_started),
        isGroup=conv_is_group,
        hasAliasDb=contact_conn is not None,
    )

    def lookup_alias(username: str) -> str:
        u = str(username or "").strip()
        if not u or contact_conn is None:
            return ""
        if u in alias_cache:
            return alias_cache[u]

        alias = ""
        try:
            r = contact_conn.execute("SELECT alias FROM contact WHERE username = ? LIMIT 1", (u,)).fetchone()
            if r is not None and r[0] is not None:
                alias = str(r[0] or "").strip()
            if not alias:
                r = contact_conn.execute("SELECT alias FROM stranger WHERE username = ? LIMIT 1", (u,)).fetchone()
                if r is not None and r[0] is not None:
                    alias = str(r[0] or "").strip()
        except Exception:
            alias = ""

        alias_cache[u] = alias
        return alias

    # NOTE: Do not keep an entry handle opened while also writing other entries (avatars/media).
    # zipfile forbids interleaving writes; stream to a temp file then add it to zip at the end.
    with tempfile.TemporaryDirectory(prefix="wechat_chat_export_") as tmp_dir:
        tmp_path = Path(tmp_dir) / "messages.json"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as tw:
            tw.write("{\n")
            tw.write("  \"schemaVersion\": 1,\n")
            tw.write(f"  \"exportedAt\": {json.dumps(_now_iso(), ensure_ascii=False)},\n")
            tw.write(f"  \"account\": {json.dumps('hidden' if privacy_mode else account_dir.name, ensure_ascii=False)},\n")
            tw.write(
                "  \"conversation\": "
                + json.dumps(
                    {
                        "username": "" if privacy_mode else conv_username,
                        "displayName": "已隐藏" if privacy_mode else conv_name,
                        "avatarPath": "" if privacy_mode else (conv_avatar_path or ""),
                        "isGroup": bool(conv_is_group),
                    },
                    ensure_ascii=False,
                )
                + ",\n"
            )
            tw.write(
                "  \"filters\": "
                + json.dumps(
                    {
                        "startTime": int(start_time) if start_time else None,
                        "endTime": int(end_time) if end_time else None,
                        "messageTypes": sorted(want_types) if want_types else None,
                    },
                    ensure_ascii=False,
                )
                + ",\n"
            )
            tw.write("  \"messages\": [\n")

            sender_alias_map: dict[str, int] = {}
            first = True
            scanned = 0
            for row in _iter_rows_for_conversation(
                account_dir=account_dir,
                conv_username=conv_username,
                start_time=start_time,
                end_time=end_time,
                local_types=local_types,
                source=source,
                rt_conn=rt_conn,
            ):
                scanned += 1
                _raise_if_job_cancelled(
                    job,
                    "json.scan",
                    trace,
                    conversation=conv_username,
                    scanned=scanned,
                    exported=exported,
                )
                _log_writer_progress(
                    trace,
                    export_format="json",
                    job=job,
                    conv_username=conv_username,
                    scanned=scanned,
                    exported=exported,
                )

                sender_alias = ""
                if conv_is_group and row.raw_text and (not row.raw_text.startswith("<")) and (not row.raw_text.startswith('"<')):
                    sep = row.raw_text.find(":\n")
                    if sep > 0:
                        prefix = row.raw_text[:sep].strip()
                        su = str(row.sender_username or "").strip()
                        if prefix and su and prefix != su:
                            strong_hint = prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix
                            if not strong_hint:
                                body_probe = row.raw_text[sep + 2 :].lstrip("\n").lstrip()
                                body_is_xml = body_probe.startswith("<") or body_probe.startswith('"<')
                                if not body_is_xml:
                                    sender_alias = lookup_alias(su)

                phase_started = time.perf_counter()
                msg = _parse_message_for_export(
                    row=row,
                    conv_username=conv_username,
                    is_group=conv_is_group,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    sender_alias=sender_alias,
                    resolve_display_name=resolve_display_name,
                )
                _log_export_slow_step(
                    "json.parse_message",
                    phase_started,
                    exportId=job.export_id,
                    conversation=conv_username,
                    scanned=scanned,
                    localType=row.local_type,
                    serverId=row.server_id,
                )
                if not _is_render_type_selected(msg.get("renderType"), want_types):
                    continue

                su = str(msg.get("senderUsername") or "").strip()
                if privacy_mode:
                    _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
                else:
                    msg["senderDisplayName"] = resolve_display_name(su) if su else ""
                    phase_started = time.perf_counter()
                    msg["senderAvatarPath"] = (
                        _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=su,
                            avatar_written=avatar_written,
                        )
                        if (su and head_image_conn is not None)
                        else ""
                    )
                    _log_export_slow_step(
                        "json.sender_avatar",
                        phase_started,
                        exportId=job.export_id,
                        conversation=conv_username,
                        scanned=scanned,
                        sender=su,
                    )

                if include_media:
                    phase_started = time.perf_counter()
                    _attach_offline_media(
                        zf=zf,
                        account_dir=account_dir,
                        conv_username=conv_username,
                        msg=msg,
                        media_written=media_written,
                        report=report,
                        media_kinds=media_kinds,
                        allow_process_key_extract=allow_process_key_extract,
                        media_db_path=media_db_path,
                        media_index=media_index,
                        lock=lock,
                        job=job,
                    )
                    _log_export_slow_step(
                        "json.attach_media",
                        phase_started,
                        exportId=job.export_id,
                        conversation=conv_username,
                        scanned=scanned,
                        renderType=msg.get("renderType"),
                        localId=msg.get("localId"),
                        serverId=msg.get("serverId"),
                    )

                if not first:
                    tw.write(",\n")
                tw.write("    " + json.dumps(msg, ensure_ascii=False))
                first = False

                exported += 1
                with lock:
                    job.progress.messages_exported += 1
                    job.progress.current_conversation_messages_exported = exported

            tw.write("\n  ]\n")
            tw.write("}\n")
            tw.flush()
            _log_writer_progress(
                trace,
                export_format="json",
                job=job,
                conv_username=conv_username,
                scanned=scanned,
                exported=exported,
                force=True,
            )
            _safe_trace(trace, "messages_temp_written", scanned=scanned, exported=exported)

        phase_started = time.perf_counter()
        try:
            tmp_html_text = tmp_path.read_text(encoding="utf-8")
            tmp_path.write_text(_minify_html_for_export(tmp_html_text), encoding="utf-8", newline="\n")
        except Exception:
            pass
        zf.write(str(tmp_path), arcname)
        _safe_trace(trace, "zip_entry_written", durationMs=_elapsed_ms(phase_started), arcname=arcname)
    if contact_conn is not None:
        try:
            contact_conn.close()
        except Exception:
            pass

    _safe_trace(trace, "writer_done", exported=exported)
    return exported


def _write_conversation_txt(
    *,
    zf: zipfile.ZipFile,
    conv_dir: str,
    account_dir: Path,
    conv_username: str,
    conv_name: str,
    conv_avatar_path: str,
    conv_is_group: bool,
    start_time: Optional[int],
    end_time: Optional[int],
    want_types: Optional[set[str]],
    local_types: Optional[set[int]],
    source: str = "decrypted",
    rt_conn: Any | None = None,
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    head_image_conn: Optional[sqlite3.Connection],
    resolve_display_name: Any,
    privacy_mode: bool,
    include_media: bool,
    media_kinds: list[MediaKind],
    media_written: dict[str, str],
    avatar_written: dict[str, str],
    report: dict[str, Any],
    allow_process_key_extract: bool,
    media_db_path: Path,
    media_index: Optional[MediaPathIndex],
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.txt"
    exported = 0
    _trace_id, trace = create_perf_trace(
        logger,
        "chat_export_conversation_writer",
        exportId=job.export_id,
        format="txt",
        conversation=conv_username,
    )
    _safe_trace(
        trace,
        "writer_started",
        convDir=conv_dir,
        displayName=conv_name,
        includeMedia=include_media,
        mediaKinds=media_kinds,
        privacyMode=privacy_mode,
        messageTypes=sorted(want_types) if want_types else None,
    )

    contact_conn: Optional[sqlite3.Connection] = None
    alias_cache: dict[str, str] = {}
    phase_started = time.perf_counter()
    if conv_is_group:
        try:
            contact_db_path = account_dir / "contact.db"
            if contact_db_path.exists():
                contact_conn = sqlite3.connect(str(contact_db_path))
        except Exception:
            contact_conn = None
    _safe_trace(
        trace,
        "alias_db_ready",
        durationMs=_elapsed_ms(phase_started),
        isGroup=conv_is_group,
        hasAliasDb=contact_conn is not None,
    )

    def lookup_alias(username: str) -> str:
        u = str(username or "").strip()
        if not u or contact_conn is None:
            return ""
        if u in alias_cache:
            return alias_cache[u]

        alias = ""
        try:
            r = contact_conn.execute("SELECT alias FROM contact WHERE username = ? LIMIT 1", (u,)).fetchone()
            if r is not None and r[0] is not None:
                alias = str(r[0] or "").strip()
            if not alias:
                r = contact_conn.execute("SELECT alias FROM stranger WHERE username = ? LIMIT 1", (u,)).fetchone()
                if r is not None and r[0] is not None:
                    alias = str(r[0] or "").strip()
        except Exception:
            alias = ""

        alias_cache[u] = alias
        return alias

    # Same as JSON: write to temp file first to avoid zip interleaving writes.
    with tempfile.TemporaryDirectory(prefix="wechat_chat_export_") as tmp_dir:
        tmp_path = Path(tmp_dir) / "messages.txt"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as tw:
            if privacy_mode:
                tw.write("会话: 已隐藏\n")
                tw.write("账号: hidden\n")
            else:
                tw.write(f"会话: {conv_name} ({conv_username})\n")
                tw.write(f"账号: {account_dir.name}\n")
                if conv_avatar_path:
                    tw.write(f"会话头像: {conv_avatar_path}\n")
            if start_time or end_time:
                st = _format_ts(int(start_time)) if start_time else "不限"
                et = _format_ts(int(end_time)) if end_time else "不限"
                tw.write(f"时间范围: {st} ~ {et}\n")
            if want_types:
                tw.write(f"消息类型: {', '.join(sorted(want_types))}\n")
            tw.write(f"导出时间: {_now_iso()}\n")
            tw.write("\n")

            sender_alias_map: dict[str, int] = {}
            scanned = 0
            prev_ts = 0
            for row in _iter_rows_for_conversation(
                account_dir=account_dir,
                conv_username=conv_username,
                start_time=start_time,
                end_time=end_time,
                local_types=local_types,
                source=source,
                rt_conn=rt_conn,
            ):
                scanned += 1
                _raise_if_job_cancelled(
                    job,
                    "txt.scan",
                    trace,
                    conversation=conv_username,
                    scanned=scanned,
                    exported=exported,
                )
                _log_writer_progress(
                    trace,
                    export_format="txt",
                    job=job,
                    conv_username=conv_username,
                    scanned=scanned,
                    exported=exported,
                )
                sender_alias = ""
                if conv_is_group and row.raw_text and (not row.raw_text.startswith("<")) and (not row.raw_text.startswith('"<')):
                    sep = row.raw_text.find(":\n")
                    if sep > 0:
                        prefix = row.raw_text[:sep].strip()
                        su = str(row.sender_username or "").strip()
                        if prefix and su and prefix != su:
                            strong_hint = prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix
                            if not strong_hint:
                                body_probe = row.raw_text[sep + 2 :].lstrip("\n").lstrip()
                                body_is_xml = body_probe.startswith("<") or body_probe.startswith('"<')
                                if not body_is_xml:
                                    sender_alias = lookup_alias(su)

                phase_started = time.perf_counter()
                msg = _parse_message_for_export(
                    row=row,
                    conv_username=conv_username,
                    is_group=conv_is_group,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    sender_alias=sender_alias,
                    resolve_display_name=resolve_display_name,
                )
                _log_export_slow_step(
                    "txt.parse_message",
                    phase_started,
                    exportId=job.export_id,
                    conversation=conv_username,
                    scanned=scanned,
                    localType=row.local_type,
                    serverId=row.server_id,
                )
                if not _is_render_type_selected(msg.get("renderType"), want_types):
                    continue

                su = str(msg.get("senderUsername") or "").strip()
                if privacy_mode:
                    _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
                else:
                    msg["senderDisplayName"] = resolve_display_name(su) if su else ""
                    phase_started = time.perf_counter()
                    msg["senderAvatarPath"] = (
                        _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=su,
                            avatar_written=avatar_written,
                        )
                        if (su and head_image_conn is not None)
                        else ""
                    )
                    _log_export_slow_step(
                        "txt.sender_avatar",
                        phase_started,
                        exportId=job.export_id,
                        conversation=conv_username,
                        scanned=scanned,
                        sender=su,
                    )

                if include_media:
                    phase_started = time.perf_counter()
                    _attach_offline_media(
                        zf=zf,
                        account_dir=account_dir,
                        conv_username=conv_username,
                        msg=msg,
                        media_written=media_written,
                        report=report,
                        media_kinds=media_kinds,
                        allow_process_key_extract=allow_process_key_extract,
                        media_db_path=media_db_path,
                        media_index=media_index,
                        lock=lock,
                        job=job,
                    )
                    _log_export_slow_step(
                        "txt.attach_media",
                        phase_started,
                        exportId=job.export_id,
                        conversation=conv_username,
                        scanned=scanned,
                        renderType=msg.get("renderType"),
                        localId=msg.get("localId"),
                        serverId=msg.get("serverId"),
                    )

                tw.write(_format_message_line_txt(msg=msg) + "\n")

                exported += 1
                with lock:
                    job.progress.messages_exported += 1
                    job.progress.current_conversation_messages_exported = exported

            tw.flush()
            _log_writer_progress(
                trace,
                export_format="txt",
                job=job,
                conv_username=conv_username,
                scanned=scanned,
                exported=exported,
                force=True,
            )
            _safe_trace(trace, "messages_temp_written", scanned=scanned, exported=exported)

        phase_started = time.perf_counter()
        zf.write(str(tmp_path), arcname)
        _safe_trace(trace, "zip_entry_written", durationMs=_elapsed_ms(phase_started), arcname=arcname)
    if contact_conn is not None:
        try:
            contact_conn.close()
        except Exception:
            pass

    _safe_trace(trace, "writer_done", exported=exported)
    return exported


def _write_conversation_html(
    *,
    zf: zipfile.ZipFile,
    conv_dir: str,
    account_dir: Path,
    conv_username: str,
    conv_name: str,
    conv_avatar_path: str,
    conv_is_group: bool,
    self_avatar_path: str,
    session_items: list[dict[str, Any]],
    download_remote_media: bool,
    remote_written: dict[str, str],
    html_page_size: int = 1000,
    start_time: Optional[int],
    end_time: Optional[int],
    want_types: Optional[set[str]],
    local_types: Optional[set[int]],
    source: str = "decrypted",
    rt_conn: Any | None = None,
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    head_image_conn: Optional[sqlite3.Connection],
    resolve_display_name: Any,
    privacy_mode: bool,
    include_media: bool,
    media_kinds: list[MediaKind],
    media_written: dict[str, str],
    avatar_written: dict[str, str],
    report: dict[str, Any],
    allow_process_key_extract: bool,
    media_db_path: Path,
    media_index: Optional[MediaPathIndex],
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.html"
    exported = 0
    _trace_id, trace = create_perf_trace(
        logger,
        "chat_export_conversation_writer",
        exportId=job.export_id,
        format="html",
        conversation=conv_username,
    )
    _safe_trace(
        trace,
        "writer_started",
        convDir=conv_dir,
        displayName=conv_name,
        includeMedia=include_media,
        mediaKinds=media_kinds,
        privacyMode=privacy_mode,
        messageTypes=sorted(want_types) if want_types else None,
        downloadRemoteMedia=download_remote_media,
        htmlPageSize=html_page_size,
        sessionItems=len(session_items),
    )

    rel_root = "../../"
    html_assets = dict(getattr(job, "options", {}).get("_htmlAssets") or {})
    css_asset_path = str(html_assets.get("cssPath") or _html_export_asset_paths(job.export_id)[0])
    js_asset_path = str(html_assets.get("jsPath") or _html_export_asset_paths(job.export_id)[1])
    integrity_asset_path = str(html_assets.get("integrityPath") or _html_export_asset_paths(job.export_id)[2])
    css_integrity = str(html_assets.get("cssIntegrity") or "")
    js_integrity = str(html_assets.get("jsIntegrity") or "")
    css_href = rel_root + css_asset_path
    integrity_src = rel_root + integrity_asset_path
    js_src = rel_root + js_asset_path

    def esc_text(v: Any) -> str:
        return html.escape(str(v or ""), quote=False)

    def esc_attr(v: Any) -> str:
        return html.escape(str(v or ""), quote=True)

    def is_http_url(u: str) -> bool:
        s = str(u or "").strip().lower()
        return s.startswith("http://") or s.startswith("https://")

    def rel_path(p: Any) -> str:
        s = str(p or "").strip().lstrip("/").replace("\\", "/")
        if not s:
            return ""
        return rel_root + s

    def offline_path(msg: dict[str, Any], kind: str) -> str:
        media = msg.get("offlineMedia") or []
        if not isinstance(media, list):
            return ""
        for item in media:
            try:
                k = str(item.get("kind") or "").strip()
            except Exception:
                k = ""
            if k != kind:
                continue
            try:
                p = str(item.get("path") or "").strip()
            except Exception:
                p = ""
            if p:
                return rel_path(p)
        return ""

    def maybe_download_remote_image(url: str) -> str:
        if not download_remote_media:
            return ""
        u = str(url or "").strip()
        if u:
            try:
                u = html.unescape(u).strip()
            except Exception:
                pass
            try:
                u = re.sub(r"\s+", "", u)
            except Exception:
                pass
        if not is_http_url(u):
            return ""
        arc = _download_remote_image_to_zip(
            zf=zf,
            url=u,
            remote_written=remote_written,
            report=report,
        )
        if not arc:
            return ""
        local = rel_path(arc)
        try:
            page_media_index.setdefault("remote", {})[u] = local
        except Exception:
            pass
        return local

    emoji_table = _load_wechat_emoji_table()
    emoji_regex = _load_wechat_emoji_regex()

    def render_text_with_emojis(v: Any) -> str:
        text = str(v or "")
        if not text:
            return ""
        if not emoji_table or emoji_regex is None:
            return esc_text(text)

        parts: list[str] = []
        last = 0
        for match in emoji_regex.finditer(text):
            start = match.start()
            end = match.end()
            if start > last:
                parts.append(esc_text(text[last:start]))

            key = match.group(0)
            value = str(emoji_table.get(key) or "")
            if value:
                src = rel_path(f"wxemoji/{value}")
                parts.append(
                    f'<img class="inline-block w-[1.25em] h-[1.25em] align-text-bottom mx-px" src="{esc_attr(src)}" alt="" />'
                )
            else:
                parts.append(esc_text(key))
            last = end

        if last < len(text):
            parts.append(esc_text(text[last:]))
        return "".join(parts)

    def build_avatar_html(*, src: str, fallback_text: str, extra_class: str) -> str:
        safe_fallback = esc_text((fallback_text or "?")[:1] or "?")
        if src:
            return (
                f'<div class="wce-avatar {extra_class} w-[calc(42px/var(--dpr))] h-[calc(42px/var(--dpr))] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">'
                f'<img src="{esc_attr(src)}" alt="avatar" class="w-full h-full object-cover" referrerpolicy="no-referrer" />'
                f"</div>"
            )
        return (
            f'<div class="wce-avatar {extra_class} w-[calc(42px/var(--dpr))] h-[calc(42px/var(--dpr))] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">'
            f'<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:700;background-color:#4B5563">{safe_fallback}</div>'
            f"</div>"
        )

    def wechat_icon(name: str) -> str:
        return rel_path(f"assets/images/wechat/{name}")

    def format_file_size(size: Any) -> str:
        if not size:
            return ""
        s = str(size).strip()
        try:
            num = float(s)
        except Exception:
            return s

        if num < 0:
            return s

        def fmt_num(n: float) -> str:
            if float(n).is_integer():
                return str(int(n))
            txt = f"{n:.2f}"
            return txt.rstrip("0").rstrip(".")

        if num < 1024:
            return f"{fmt_num(num)} B"
        if num < 1024 * 1024:
            return f"{(num / 1024):.2f} KB"
        return f"{(num / 1024 / 1024):.2f} MB"

    def format_transfer_amount(amount: Any) -> str:
        s = str(amount if amount is not None else "").strip()
        if not s:
            return ""
        return re.sub(r"[￥¥]", "", s).strip()

    def get_red_packet_text(message: dict[str, Any]) -> str:
        text = str(message.get("content") if message is not None else "").strip()
        if (not text) or text == "[Red Packet]":
            return "恭喜发财，大吉大利"
        return text

    def is_transfer_returned(message: dict[str, Any]) -> bool:
        pay_sub_type = str(message.get("paySubType") or "").strip()
        if pay_sub_type in {"4", "9"}:
            return True
        st = str(message.get("transferStatus") or "").strip()
        c = str(message.get("content") or "").strip()
        text = f"{st} {c}".strip()
        if not text:
            return False
        return ("退回" in text) or ("退还" in text)

    def is_transfer_overdue(message: dict[str, Any]) -> bool:
        pay_sub_type = str(message.get("paySubType") or "").strip()
        if pay_sub_type == "10":
            return True
        st = str(message.get("transferStatus") or "").strip()
        c = str(message.get("content") or "").strip()
        text = f"{st} {c}".strip()
        if not text:
            return False
        return "过期" in text

    def is_transfer_received(message: dict[str, Any]) -> bool:
        pay_sub_type = str(message.get("paySubType") or "").strip()
        if pay_sub_type == "3":
            return True
        st = str(message.get("transferStatus") or "").strip()
        if not st:
            return False
        return ("已收款" in st) or ("已被接收" in st)

    def get_transfer_title(message: dict[str, Any], *, is_sent: bool) -> str:
        pay_sub_type = str(message.get("paySubType") or "").strip()
        transfer_status = str(message.get("transferStatus") or "").strip()
        if transfer_status:
            return transfer_status
        if pay_sub_type == "1":
            return "转账"
        if pay_sub_type == "3":
            return "已被接收" if is_sent else "已收款"
        if pay_sub_type == "8":
            return "发起转账"
        if pay_sub_type == "4":
            return "已退还"
        if pay_sub_type == "9":
            return "已被退还"
        if pay_sub_type == "10":
            return "已过期"
        content = str(message.get("content") or "").strip()
        if content and content not in {"转账", "[转账]"}:
            return content
        return "转账"

    def get_voice_duration_in_seconds(duration_ms: Any) -> int:
        try:
            ms = int(str(duration_ms or "0").strip() or "0")
        except Exception:
            ms = 0
        return int(round(ms / 1000.0))

    def get_voice_width(duration_ms: Any) -> str:
        seconds = get_voice_duration_in_seconds(duration_ms)
        min_width = 80
        max_width = 200
        width = min(max_width, min_width + seconds * 4)
        return f"{width}px"

    def get_chat_history_preview_lines(message: dict[str, Any]) -> list[str]:
        raw = str(message.get("content") or "").strip()
        if not raw:
            return []
        lines = [ln.strip() for ln in raw.splitlines()]
        lines = [ln for ln in lines if ln]
        return lines[:4]

    def get_file_icon_url(file_name: str) -> str:
        ext = ""
        try:
            ext = (str(file_name or "").rsplit(".", 1)[-1] or "").lower().strip()
        except Exception:
            ext = ""

        if ext == "pdf":
            return wechat_icon("pdf.png")
        if ext in {"zip", "rar", "7z", "tar", "gz"}:
            return wechat_icon("zip.png")
        if ext in {"doc", "docx"}:
            return wechat_icon("word.png")
        if ext in {"xls", "xlsx", "csv"}:
            return wechat_icon("excel.png")
        return wechat_icon("zip.png")

    def get_link_from_text(message: dict[str, Any], *, url: str) -> str:
        raw = str(message.get("from") or "").strip()
        if raw:
            return raw
        try:
            from urllib.parse import urlparse

            host = urlparse(str(url or "")).hostname
            return str(host or "").strip()
        except Exception:
            return ""

    def first_glyph(text: str) -> str:
        t = str(text or "").strip()
        if not t:
            return ""
        try:
            return next(iter(t)) or ""
        except Exception:
            return t[:1]

    page_media_index: dict[str, Any] = {
        "images": {},
        "emojis": {},
        "videos": {},
        "videoThumbs": {},
        "serverMd5": {},
        "remote": {},
    }
    chat_history_md5_done: set[str] = set()

    def _remember_offline_media(message: dict[str, Any]) -> None:
        media = message.get("offlineMedia") or []
        if not isinstance(media, list):
            return
        for item in media:
            try:
                kind = str(item.get("kind") or "").strip()
            except Exception:
                kind = ""
            try:
                md5 = str(item.get("md5") or "").strip().lower()
            except Exception:
                md5 = ""
            try:
                path0 = str(item.get("path") or "").strip()
            except Exception:
                path0 = ""
            if (not md5) or (not path0):
                continue
            url0 = rel_path(path0)
            if kind == "image":
                page_media_index["images"][md5] = url0
            elif kind == "emoji":
                page_media_index["emojis"][md5] = url0
            elif kind == "video":
                page_media_index["videos"][md5] = url0
            elif kind == "video_thumb":
                page_media_index["videoThumbs"][md5] = url0

    def _ensure_chat_history_md5(md5: str) -> str:
        m = str(md5 or "").strip().lower()
        if (not m) or (not _is_md5(m)):
            return ""
        if m in chat_history_md5_done:
            for k in ("images", "emojis", "videos", "videoThumbs"):
                try:
                    hit = str((page_media_index.get(k) or {}).get(m) or "").strip()
                except Exception:
                    hit = ""
                if hit:
                    return hit
            return ""
        chat_history_md5_done.add(m)

        arc = ""
        is_new = False

        for try_kind in ("image", "emoji", "video_thumb", "video"):
            arc, is_new = _materialize_media(
                zf=zf,
                account_dir=account_dir,
                conv_username=conv_username,
                kind=try_kind,  # type: ignore[arg-type]
                md5=m,
                file_id="",
                media_written=media_written,
                suggested_name="",
                media_index=media_index,
            )
            if arc:
                break

        if not arc:
            return ""

        url0 = rel_path(arc)
        try:
            page_media_index["images"].setdefault(m, url0)
            page_media_index["emojis"].setdefault(m, url0)
            page_media_index["videoThumbs"].setdefault(m, url0)
            if arc.lower().endswith(".mp4"):
                page_media_index["videos"][m] = url0
        except Exception:
            pass

        if is_new:
            with lock:
                job.progress.media_copied += 1
        return url0

    chat_title = "已隐藏" if privacy_mode else (conv_name or conv_username or "会话")
    page_title = chat_title

    options = [
        ("all", "全部"),
        ("text", "文本"),
        ("image", "图片"),
        ("emoji", "表情"),
        ("video", "视频"),
        ("voice", "语音"),
        ("chatHistory", "聊天记录"),
        ("transfer", "转账"),
        ("redPacket", "红包"),
        ("file", "文件"),
        ("link", "链接"),
        ("quote", "引用"),
        ("system", "系统"),
        ("voip", "通话"),
    ]

    page_size = 0
    try:
        page_size = int(html_page_size or 0)
    except Exception:
        page_size = 0
    if page_size < 0:
        page_size = 0

    # NOTE: write to a temp file first to avoid zip interleaving writes.
    with tempfile.TemporaryDirectory(prefix="wechat_chat_export_") as tmp_dir:
        tmp_path = Path(tmp_dir) / "messages.html"
        pages_frag_dir = Path(tmp_dir) / "pages_fragments"
        page_frag_paths: list[Path] = []
        paged_old_page_paths: list[Path] = []
        paged_total_pages = 1
        paged_pad_width = 4
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as hw:
            class _WriteProxy:
                def __init__(self, default_target):
                    self._default = default_target
                    self._target = default_target

                def set_target(self, target) -> None:
                    self._target = target or self._default

                def write(self, s: str) -> Any:
                    return self._target.write(s)

                def flush(self) -> None:
                    try:
                        if self._target is not self._default:
                            self._target.flush()
                    except Exception:
                        pass
                    try:
                        self._default.flush()
                    except Exception:
                        pass

            tw = _WriteProxy(hw)
            tw.write("<!doctype html>\n")
            tw.write('<html lang="zh-CN">\n')
            tw.write("<head>\n")
            tw.write('  <meta charset="utf-8" />\n')
            tw.write('  <meta name="viewport" content="width=device-width, initial-scale=1" />\n')
            tw.write(f"  <title>{esc_text(page_title)}</title>\n")
            tw.write(_html_export_gate_style())
            # Do not use native `integrity=` for offline file:// exports; Chrome blocks
            # those resources before our runtime can show the page.
            tw.write(f'  <link id="wceStyle" rel="stylesheet" href="{esc_attr(css_href)}" data-wce-sri="{esc_attr(css_integrity)}" />\n')
            tw.write(_html_export_integrity_script_tag(src=integrity_src))
            tw.write(f'  <script defer src="{esc_attr(js_src)}" data-wce-sri="{esc_attr(js_integrity)}"></script>\n')
            tw.write("</head>\n")
            tw.write("<body>\n")
            tw.write(
                '  <div id="wceJsMissing" style="position:fixed;top:0;left:0;right:0;z-index:9999;background:#FEF3C7;color:#92400E;border-bottom:1px solid #F59E0B;padding:8px 12px;font-size:12px;line-height:1.4">'
                "提示：此页面需要 JavaScript 才能使用“合并聊天记录”等交互功能。若该提示一直存在，请确认已完整解压导出目录，并检查 assets/_wce/ 下的运行时文件是否完整。</div>\n"
            )

            # Root
            tw.write('<div class="wce-root h-screen flex overflow-hidden" style="background-color:#EDEDED">\n')

            # Left rail (avatar + chat icon)
            tw.write(
                '<div class="wce-rail border-r border-gray-200 flex flex-col" style="background-color:#e8e7e7;width:60px;min-width:60px;max-width:60px">\n'
            )

            self_avatar_src = "" if privacy_mode else rel_path(self_avatar_path)
            tw.write('  <div class="w-full h-[60px] flex items-center justify-center">\n')
            tw.write('    <div data-wce-rail-avatar="1" class="w-[40px] h-[40px] rounded-md overflow-hidden bg-gray-300 flex-shrink-0">\n')
            if self_avatar_src:
                tw.write(
                    f'      <img src="{esc_attr(self_avatar_src)}" alt="avatar" class="w-full h-full object-cover" referrerpolicy="no-referrer" />\n'
                )
            else:
                tw.write(
                    '      <div class="w-full h-full flex items-center justify-center text-white text-xs font-bold" style="background-color:#4B5563">我</div>\n'
                )
            tw.write("    </div>\n")
            tw.write("  </div>\n")

            tw.write(
                f'  <a href="{esc_attr(rel_root + "index.html")}" class="w-full h-[var(--sidebar-rail-step)] flex items-center justify-center group" aria-label="会话列表" title="会话列表">\n'
            )
            tw.write(
                '    <div class="w-[var(--sidebar-rail-btn)] h-[var(--sidebar-rail-btn)] rounded-md bg-transparent group-hover:bg-[#E1E1E1] flex items-center justify-center transition-colors">\n'
            )
            tw.write('      <div class="w-[var(--sidebar-rail-icon)] h-[var(--sidebar-rail-icon)] text-[#07b75b]">\n')
            tw.write('        <svg class="w-full h-full" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">\n')
            tw.write(
                '          <path d="M12 19.8C17.52 19.8 22 15.99 22 11.3C22 6.6 17.52 2.8 12 2.8C6.48 2.8 2 6.6 2 11.3C2 13.29 2.8 15.12 4.15 16.57C4.6 17.05 4.82 17.29 4.92 17.44C5.14 17.79 5.21 17.99 5.23 18.4C5.24 18.59 5.22 18.81 5.16 19.26C5.1 19.75 5.07 19.99 5.13 20.16C5.23 20.49 5.53 20.71 5.87 20.72C6.04 20.72 6.27 20.63 6.72 20.43L8.07 19.86C8.43 19.71 8.61 19.63 8.77 19.59C8.95 19.55 9.04 19.54 9.22 19.54C9.39 19.53 9.64 19.57 10.14 19.65C10.74 19.75 11.37 19.8 12 19.8Z" />\n'
            )
            tw.write("        </svg>\n")
            tw.write("      </div>\n")
            tw.write("    </div>\n")
            tw.write("  </a>\n")
            tw.write("</div>\n")

            # Middle session list (all exported conversations)
            tw.write(
                '<div class="wce-session-panel session-list-panel border-r border-gray-200 flex flex-col min-h-0 shrink-0 relative" style="background-color:#F7F7F7;--session-list-width:295px">\n'
            )
            tw.write('  <div class="p-3 border-b border-gray-200" style="background-color:#F7F7F7">\n')
            tw.write(
                '    <div class="flex items-center gap-2">\n'
            )
            tw.write('      <div class="contact-search-wrapper flex-1">\n')
            tw.write('        <svg class="contact-search-icon" fill="none" stroke="currentColor" viewBox="0 0 16 16">\n')
            tw.write(
                '          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.33333 12.6667C10.2789 12.6667 12.6667 10.2789 12.6667 7.33333C12.6667 4.38781 10.2789 2 7.33333 2C4.38781 2 2 4.38781 2 7.33333C2 10.2789 4.38781 12.6667 7.33333 12.6667Z" />\n'
            )
            tw.write(
                '          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 14L11.1 11.1" />\n'
            )
            tw.write("        </svg>\n")
            search_input_cls = "contact-search-input"
            if privacy_mode:
                search_input_cls += " privacy-blur"
            tw.write(
                f'        <input id="sessionSearchInput" type="text" placeholder="搜索联系人" class="{esc_attr(search_input_cls)}" autocomplete="off" />\n'
            )
            tw.write(
                '        <button type="button" id="sessionSearchClear" class="contact-search-clear" style="display:none" aria-label="清空搜索">\n'
            )
            tw.write('          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">\n')
            tw.write(
                '            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>\n'
            )
            tw.write("          </svg>\n")
            tw.write("        </button>\n")
            tw.write("      </div>\n")
            tw.write("    </div>\n")
            tw.write("  </div>\n")
            tw.write('  <div class="flex-1 overflow-y-auto min-h-0" data-wce-session-list="1">\n')

            conv_dir_norm = str(conv_dir or "").strip().strip("/").replace("\\", "/")
            for item in session_items:
                item_conv_dir = str(item.get("convDir") or "").strip().strip("/").replace("\\", "/")
                if not item_conv_dir:
                    continue

                href = f"{rel_root}{item_conv_dir}/messages.html"
                item_display_name = str(item.get("displayName") or "").strip() or "会话"
                item_avatar_path = str(item.get("avatarPath") or "").strip()
                item_avatar_src = rel_path(item_avatar_path) if item_avatar_path else ""
                item_last_time = str(item.get("lastTimeText") or "").strip()
                item_preview = str(item.get("previewText") or "").strip()

                is_active = False
                try:
                    is_active = (str(item.get("username") or "").strip() == conv_username) or (item_conv_dir == conv_dir_norm)
                except Exception:
                    is_active = item_conv_dir == conv_dir_norm

                safe_char = (item_display_name[:1] or "?").strip() or "?"
                classes = (
                    "px-3 cursor-pointer transition-colors duration-150 border-b border-gray-100 "
                    "h-[calc(80px/var(--dpr))] flex items-center"
                )
                if is_active:
                    classes += " bg-[#DEDEDE]"
                else:
                    classes += " hover:bg-[#F5F5F5]"

                item_username = str(item.get("username") or "").strip()
                tw.write(
                    f'    <a href="{esc_attr(href)}" class="{esc_attr(classes)}" data-wce-session-item="1" '
                    f'data-wce-session-name="{esc_attr(item_display_name)}" data-wce-session-username="{esc_attr(item_username)}"'
                )
                if is_active:
                    tw.write(' aria-current="page"')
                tw.write(">\n")
                tw.write('      <div class="relative">\n')
                tw.write(
                    '        <div class="w-[calc(45px/var(--dpr))] h-[calc(45px/var(--dpr))] rounded-md overflow-hidden bg-gray-300">\n'
                )
                if item_avatar_src and (not privacy_mode):
                    tw.write(
                        f'          <img src="{esc_attr(item_avatar_src)}" alt="{esc_attr(item_display_name)}" class="w-full h-full object-cover" referrerpolicy="no-referrer" />\n'
                    )
                else:
                    tw.write(
                        f'          <div class="w-full h-full flex items-center justify-center text-white text-xs font-bold" style="background-color:#4B5563">{esc_text(safe_char)}</div>\n'
                    )
                tw.write("        </div>\n")
                tw.write("      </div>\n")
                tw.write('      <div class="flex-1 min-w-0 ml-3">\n')
                tw.write('        <div class="flex items-center justify-between">\n')
                tw.write(
                    f'          <h3 class="text-sm font-medium text-gray-900 truncate">{esc_text(item_display_name)}</h3>\n'
                )
                tw.write('          <div class="flex items-center flex-shrink-0 ml-2">\n')
                tw.write(f'            <span class="text-xs text-gray-500">{esc_text(item_last_time)}</span>\n')
                tw.write("          </div>\n")
                tw.write("        </div>\n")
                tw.write(
                    f'        <p class="text-xs text-gray-500 truncate mt-0.5 leading-tight">{render_text_with_emojis(item_preview)}</p>\n'
                )
                tw.write("      </div>\n")
                tw.write("    </a>\n")

            tw.write("  </div>\n")
            tw.write("</div>\n")

            # Right chat area
            tw.write('<div class="wce-chat-area flex-1 flex flex-col min-h-0" style="background-color:#EDEDED">\n')
            tw.write('  <div class="wce-chat-main flex-1 flex min-h-0">\n')
            tw.write('    <div class="wce-chat-col flex-1 flex flex-col min-h-0 min-w-0">\n')
            tw.write('      <div class="flex-1 flex flex-col min-h-0 relative">\n')

            tw.write('        <div class="chat-header">\n')
            tw.write('          <div class="flex items-center gap-3 min-w-0">\n')
            tw.write(f'            <h2 class="text-base font-medium text-gray-900">{esc_text(chat_title)}</h2>\n')
            tw.write("          </div>\n")
            tw.write('          <div class="ml-auto wce-chat-tools">\n')
            tw.write('            <div class="wce-tool-group" title="搜索当前聊天记录；分页导出会在首次搜索时加载全部分页">\n')
            tw.write('              <input id="wceMessageSearchInput" class="wce-tool-input wce-tool-search" type="search" placeholder="搜索聊天记录" autocomplete="off" />\n')
            tw.write('              <button id="wceMessageSearchBtn" class="wce-tool-btn" type="button">搜索</button>\n')
            tw.write('              <button id="wceMessageSearchPrev" class="wce-tool-btn" type="button" title="上一个搜索结果">↑</button>\n')
            tw.write('              <button id="wceMessageSearchNext" class="wce-tool-btn" type="button" title="下一个搜索结果">↓</button>\n')
            tw.write('              <span id="wceMessageSearchStatus" class="wce-tool-status" aria-live="polite"></span>\n')
            tw.write("            </div>\n")
            tw.write('            <div class="wce-tool-group" title="按日期定位当前筛选下的第一条消息">\n')
            tw.write('              <input id="wceDateJumpInput" class="wce-tool-input wce-tool-date" type="date" />\n')
            tw.write('              <button id="wceDateJumpBtn" class="wce-tool-btn" type="button">定位</button>\n')
            tw.write('              <span id="wceDateJumpStatus" class="wce-tool-status" aria-live="polite"></span>\n')
            tw.write("            </div>\n")
            tw.write(f'            <select id="messageTypeFilter" class="message-filter-select" title="筛选消息类型">\n')
            for value, label in options:
                tw.write(f'              <option value="{esc_attr(value)}">{esc_text(label)}</option>\n')
            tw.write("            </select>\n")
            tw.write("          </div>\n")
            tw.write("        </div>\n")

            tw.write('        <div id="messageContainer" class="flex-1 overflow-y-auto p-4 min-h-0">\n')
            tw.write('          <div id="wcePager" class="wce-pager" style="display:none">\n')
            tw.write('            <button id="wceLoadPrevBtn" type="button" class="wce-pager-btn">加载更早消息</button>\n')
            tw.write('            <span id="wceLoadPrevStatus" class="wce-pager-status"></span>\n')
            tw.write("          </div>\n")
            tw.write('          <div id="wceMessageList">\n')

            page_fp = None
            page_fp_path: Optional[Path] = None
            page_no = 1
            page_msg_count = 0

            def _open_page_fp() -> Any:
                nonlocal page_fp, page_fp_path
                pages_frag_dir.mkdir(parents=True, exist_ok=True)
                page_fp_path = pages_frag_dir / f"page_{page_no}.htmlfrag"
                page_fp = open(page_fp_path, "w", encoding="utf-8", newline="\n")
                return page_fp

            def _close_page_fp() -> None:
                nonlocal page_fp, page_fp_path
                if page_fp is None:
                    page_fp_path = None
                    return
                try:
                    page_fp.flush()
                except Exception:
                    pass
                try:
                    page_fp.close()
                except Exception:
                    pass
                if page_fp_path is not None:
                    page_frag_paths.append(page_fp_path)
                page_fp = None
                page_fp_path = None
                tw.set_target(hw)

            def _mark_exported() -> None:
                nonlocal exported, page_no, page_msg_count
                exported += 1
                with lock:
                    job.progress.messages_exported += 1
                    job.progress.current_conversation_messages_exported = exported
                if page_size > 0:
                    page_msg_count += 1
                    if page_msg_count >= page_size:
                        _close_page_fp()
                        page_no += 1
                        page_msg_count = 0

            sender_alias_map: dict[str, int] = {}
            prev_ts = 0
            scanned = 0
            for row in _iter_rows_for_conversation(
                account_dir=account_dir,
                conv_username=conv_username,
                start_time=start_time,
                end_time=end_time,
                local_types=local_types,
                source=source,
                rt_conn=rt_conn,
            ):
                scanned += 1
                _raise_if_job_cancelled(
                    job,
                    "html.scan",
                    trace,
                    conversation=conv_username,
                    scanned=scanned,
                    exported=exported,
                )
                _log_writer_progress(
                    trace,
                    export_format="html",
                    job=job,
                    conv_username=conv_username,
                    scanned=scanned,
                    exported=exported,
                )

                phase_started = time.perf_counter()
                msg = _parse_message_for_export(
                    row=row,
                    conv_username=conv_username,
                    is_group=conv_is_group,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    sender_alias="",
                    resolve_display_name=resolve_display_name,
                )
                _log_export_slow_step(
                    "html.parse_message",
                    phase_started,
                    exportId=job.export_id,
                    conversation=conv_username,
                    scanned=scanned,
                    localType=row.local_type,
                    serverId=row.server_id,
                )
                if not _is_render_type_selected(msg.get("renderType"), want_types):
                    continue

                sender_username = str(msg.get("senderUsername") or "").strip()
                if privacy_mode:
                    _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
                else:
                    msg["senderDisplayName"] = resolve_display_name(sender_username) if sender_username else ""
                    phase_started = time.perf_counter()
                    msg["senderAvatarPath"] = (
                        _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=sender_username,
                            avatar_written=avatar_written,
                        )
                        if (sender_username and head_image_conn is not None)
                        else ""
                    )
                    _log_export_slow_step(
                        "html.sender_avatar",
                        phase_started,
                        exportId=job.export_id,
                        conversation=conv_username,
                        scanned=scanned,
                        sender=sender_username,
                    )

                if include_media:
                    phase_started = time.perf_counter()
                    _attach_offline_media(
                        zf=zf,
                        account_dir=account_dir,
                        conv_username=conv_username,
                        msg=msg,
                        media_written=media_written,
                        report=report,
                        media_kinds=media_kinds,
                        allow_process_key_extract=allow_process_key_extract,
                        media_db_path=media_db_path,
                        media_index=media_index,
                        lock=lock,
                        job=job,
                    )
                    _remember_offline_media(msg)
                    _log_export_slow_step(
                        "html.attach_media",
                        phase_started,
                        exportId=job.export_id,
                        conversation=conv_username,
                        scanned=scanned,
                        renderType=msg.get("renderType"),
                        localId=msg.get("localId"),
                        serverId=msg.get("serverId"),
                    )

                rt = str(msg.get("renderType") or "text").strip() or "text"
                create_time_text = str(msg.get("createTimeText") or "").strip()
                try:
                    ts = int(msg.get("createTime") or 0)
                except Exception:
                    ts = 0
                date_attr = ""
                if ts:
                    try:
                        date_attr = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                    except Exception:
                        date_attr = ""

                show_divider = False
                if ts and ((prev_ts == 0) or (abs(ts - prev_ts) >= 300)):
                    show_divider = True

                if page_size > 0:
                    if page_fp is None:
                        _open_page_fp()
                    tw.set_target(page_fp)

                if show_divider:
                    divider_text = _format_session_time(ts)
                    if divider_text:
                        tw.write('          <div class="flex justify-center mb-4" data-wce-time-divider="1">\n')
                        tw.write(f'            <div class="px-3 py-1 text-xs text-[#9e9e9e]">{esc_text(divider_text)}</div>\n')
                        tw.write("          </div>\n")

                # Wrapper (for filter)
                tw.write(
                    f'          <div class="mb-6" data-render-type="{esc_attr(rt)}" '
                    f'data-wce-create-time="{esc_attr(str(ts) if ts else "")}" data-wce-date="{esc_attr(date_attr)}" '
                    f'title="{esc_attr(create_time_text)}">\n'
                )

                if rt == "system":
                    tw.write('            <div class="wce-system flex justify-center">\n')
                    tw.write(f'              <div class="px-3 py-1 text-xs text-[#9e9e9e]">{esc_text(msg.get("content") or "")}</div>\n')
                    tw.write("            </div>\n")
                    tw.write("          </div>\n")
                    _mark_exported()
                    if ts:
                        prev_ts = ts
                    continue

                is_sent = bool(msg.get("isSent"))
                row_cls = "wce-msg-row wce-msg-row-sent flex items-center justify-end" if is_sent else "wce-msg-row wce-msg-row-received flex items-center justify-start"
                msg_cls = "wce-msg wce-msg-sent flex items-start max-w-md flex-row-reverse" if is_sent else "wce-msg flex items-start max-w-md"
                avatar_extra = "wce-avatar-sent ml-3" if is_sent else "wce-avatar-received mr-3"

                tw.write(f'            <div class="{esc_attr(row_cls)}">\n')
                tw.write(f'              <div class="{esc_attr(msg_cls)}">\n')

                avatar_src = rel_path(str(msg.get("senderAvatarPath") or "").strip())
                display_name = str(msg.get("senderDisplayName") or "").strip()
                fallback_char = (display_name or sender_username or "?")[:1]
                tw.write("                " + build_avatar_html(src=avatar_src, fallback_text=fallback_char, extra_class=avatar_extra) + "\n")

                align_cls = "items-end" if is_sent else "items-start"
                tw.write(f'                <div class="flex flex-col relative group {esc_attr(align_cls)}" style="min-width:0">\n')
                if conv_is_group and (not is_sent) and display_name:
                    tw.write(f'                  <div class="text-[11px] text-gray-500 mb-1 text-left">{esc_text(display_name)}</div>\n')

                pos_cls = "right-0" if is_sent else "left-0"
                tw.write(
                    '                  <div class="absolute -top-6 z-10 rounded bg-black/70 text-white text-[10px] px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap '
                    + pos_cls
                    + f'">{esc_text(create_time_text)}</div>\n'
                )

                # Message body
                bubble_dir_cls = "bg-[#95EC69] text-black bubble-tail-r" if is_sent else "bg-white text-gray-800 bubble-tail-l"
                bubble_base_cls = "px-3 py-2 text-sm max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed"
                bubble_unknown_cls = (
                    "px-3 py-2 text-xs max-w-sm relative msg-bubble whitespace-pre-wrap break-words leading-relaxed text-gray-700"
                )

                if rt == "image":
                    src = offline_path(msg, "image")
                    if not src:
                        url = str(msg.get("imageUrl") or "").strip()
                        src = url if is_http_url(url) else ""
                    if src:
                        tw.write('                  <div class="max-w-sm">\n')
                        tw.write('                    <div class="msg-radius overflow-hidden cursor-pointer">\n')
                        tw.write(f'                      <a href="{esc_attr(src)}" target="_blank" rel="noreferrer noopener">\n')
                        tw.write(f'                        <img src="{esc_attr(src)}" alt="图片" class="max-w-[240px] max-h-[240px] object-cover hover:opacity-90 transition-opacity" loading="lazy" decoding="async" />\n')
                        tw.write("                      </a>\n")
                        tw.write("                    </div>\n")
                        tw.write("                  </div>\n")
                    else:
                        tw.write(f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n')
                elif rt == "emoji":
                    src = offline_path(msg, "emoji")
                    if not src:
                        url = str(msg.get("emojiUrl") or "").strip()
                        src = url if is_http_url(url) else ""
                    if src:
                        emoji_dir = " flex-row-reverse" if is_sent else ""
                        tw.write(f'                  <div class="max-w-sm flex items-center{emoji_dir}">\n')
                        tw.write(f'                    <img src="{esc_attr(src)}" alt="表情" class="w-24 h-24 object-contain" loading="lazy" decoding="async" />\n')
                        tw.write("                  </div>\n")
                    else:
                        tw.write(f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n')
                elif rt == "video":
                    thumb = offline_path(msg, "video_thumb")
                    if not thumb:
                        url = str(msg.get("videoThumbUrl") or "").strip()
                        thumb = url if is_http_url(url) else ""
                    video = offline_path(msg, "video")
                    if not video:
                        url = str(msg.get("videoUrl") or "").strip()
                        video = url if is_http_url(url) else ""
                    if thumb:
                        tw.write('                  <div class="max-w-sm">\n')
                        tw.write('                    <div class="msg-radius overflow-hidden relative bg-black/5">\n')
                        tw.write(f'                      <img src="{esc_attr(thumb)}" alt="视频" class="block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover" loading="lazy" decoding="async" />\n')
                        if video:
                            tw.write(f'                      <a href="{esc_attr(video)}" target="_blank" rel="noreferrer noopener" class="absolute inset-0 flex items-center justify-center">\n')
                            tw.write('                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">\n')
                            tw.write('                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>\n')
                            tw.write("                        </div>\n")
                            tw.write("                      </a>\n")
                        else:
                            tw.write('                      <div class="absolute inset-0 flex items-center justify-center">\n')
                            tw.write('                        <div class="w-12 h-12 rounded-full bg-black/45 flex items-center justify-center">\n')
                            tw.write('                          <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>\n')
                            tw.write("                        </div>\n")
                            tw.write("                      </div>\n")
                        tw.write("                    </div>\n")
                        tw.write("                  </div>\n")
                    else:
                        tw.write(f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n')
                elif rt == "voice":
                    voice = offline_path(msg, "voice")
                    duration_ms = msg.get("voiceLength")
                    width = get_voice_width(duration_ms)
                    seconds = get_voice_duration_in_seconds(duration_ms)
                    voice_dir_cls = "wechat-voice-sent" if is_sent else "wechat-voice-received"
                    content_dir_cls = " flex-row-reverse" if is_sent else ""
                    icon_dir_cls = "voice-icon-sent" if is_sent else "voice-icon-received"
                    voice_id = str(msg.get("id") or "").strip()

                    tw.write('                  <div class="wechat-voice-wrapper">\n')
                    tw.write(
                        f'                    <div class="wechat-voice-bubble msg-radius {esc_attr(voice_dir_cls)}" style="width: {esc_attr(width)}" data-voice-id="{esc_attr(voice_id)}">\n'
                    )
                    tw.write(f'                      <div class="wechat-voice-content{esc_attr(content_dir_cls)}">\n')
                    tw.write(
                        f'                        <svg class="wechat-voice-icon {esc_attr(icon_dir_cls)}" viewBox="0 0 32 32" fill="currentColor">\n'
                    )
                    tw.write(
                        '                          <path d="M10.24 11.616l-4.224 4.192 4.224 4.192c1.088-1.056 1.76-2.56 1.76-4.192s-0.672-3.136-1.76-4.192z"></path>\n'
                    )
                    tw.write(
                        '                          <path class="voice-wave-2" d="M15.199 6.721l-1.791 1.76c1.856 1.888 3.008 4.48 3.008 7.328s-1.152 5.44-3.008 7.328l1.791 1.76c2.336-2.304 3.809-5.536 3.809-9.088s-1.473-6.784-3.809-9.088z"></path>\n'
                    )
                    tw.write(
                        '                          <path class="voice-wave-3" d="M20.129 1.793l-1.762 1.76c3.104 3.168 5.025 7.488 5.025 12.256s-1.921 9.088-5.025 12.256l1.762 1.76c3.648-3.616 5.887-8.544 5.887-14.016s-2.239-10.432-5.887-14.016z"></path>\n'
                    )
                    tw.write("                        </svg>\n")
                    tw.write(f'                        <span class="wechat-voice-duration">{esc_text(seconds)}"</span>\n')
                    tw.write("                      </div>\n")
                    tw.write("                    </div>\n")
                    if voice:
                        tw.write(f'                    <audio src="{esc_attr(voice)}" preload="none" class="hidden"></audio>\n')
                    tw.write("                  </div>\n")
                elif rt == "file":
                    fsrc = offline_path(msg, "file")
                    title = str(msg.get("title") or msg.get("content") or "文件").strip()
                    size = str(msg.get("fileSize") or "").strip()
                    size_text = format_file_size(size)
                    sent_side_cls = " wechat-special-sent-side" if is_sent else ""
                    cls = f"wechat-redpacket-card wechat-special-card wechat-file-card msg-radius{sent_side_cls}"
                    tag = "a" if fsrc else "div"
                    attrs = f' href="{esc_attr(fsrc)}" download' if fsrc else ""
                    tw.write(f'                  <{tag}{attrs} class="{esc_attr(cls)}">\n')
                    tw.write('                    <div class="wechat-redpacket-content">\n')
                    tw.write('                      <div class="wechat-redpacket-info wechat-file-info">\n')
                    tw.write(f'                        <span class="wechat-file-name">{esc_text(title or "文件")}</span>\n')
                    if size_text:
                        tw.write(f'                        <span class="wechat-file-size">{esc_text(size_text)}</span>\n')
                    tw.write("                      </div>\n")
                    tw.write(f'                      <img src="{esc_attr(get_file_icon_url(title))}" alt="" class="wechat-file-icon" />\n')
                    tw.write("                    </div>\n")
                    tw.write('                    <div class="wechat-redpacket-bottom wechat-file-bottom">\n')
                    tw.write(f'                      <img src="{esc_attr(wechat_icon("WeChat-Icon-Logo.wine.svg"))}" alt="" class="wechat-file-logo" />\n')
                    tw.write("                      <span>微信电脑版</span>\n")
                    tw.write("                    </div>\n")
                    tw.write(f"                  </{tag}>\n")
                elif rt == "link":
                    url = str(msg.get("url") or "").strip()
                    safe_url = url if is_http_url(url) else ""
                    if safe_url:
                        heading = str(msg.get("title") or msg.get("content") or safe_url).strip()
                        abstract = str(msg.get("content") or "").strip()
                        preview = str(msg.get("thumbUrl") or "").strip()
                        preview_url = ""
                        if is_http_url(preview):
                            local = maybe_download_remote_image(preview)
                            preview_url = local or preview
                        variant = str(msg.get("linkStyle") or "").strip().lower()

                        from_text = get_link_from_text(msg, url=safe_url)
                        from_avatar_text = first_glyph(from_text) or "\u200B"
                        from_text = from_text or "\u200B"
                        sent_side_cls = " wechat-special-sent-side" if is_sent else ""

                        if variant == "cover":
                            cls = f"wechat-link-card-cover wechat-special-card msg-radius{sent_side_cls}"
                            tw.write(
                                f'                  <a href="{esc_attr(safe_url)}" target="_blank" rel="noreferrer" class="{esc_attr(cls)}" '
                                'style="width:137px;min-width:137px;max-width:137px;display:flex;flex-direction:column;box-sizing:border-box;flex:0 0 auto;background:#fff;border:none;box-shadow:none;text-decoration:none;outline:none">\n'
                            )
                            if preview_url:
                                tw.write('                    <div class="wechat-link-cover-image-wrap">\n')
                                tw.write(
                                    f'                      <img src="{esc_attr(preview_url)}" alt="{esc_attr(heading or "链接封面")}" class="wechat-link-cover-image" referrerpolicy="no-referrer" />\n'
                                )
                                tw.write('                      <div class="wechat-link-cover-from">\n')
                                tw.write(
                                    f'                        <div class="wechat-link-cover-from-avatar" aria-hidden="true">{esc_text(from_avatar_text)}</div>\n'
                                )
                                tw.write(f'                        <div class="wechat-link-cover-from-name">{esc_text(from_text)}</div>\n')
                                tw.write("                      </div>\n")
                                tw.write("                    </div>\n")
                            else:
                                tw.write('                    <div class="wechat-link-cover-from">\n')
                                tw.write(
                                    f'                      <div class="wechat-link-cover-from-avatar" aria-hidden="true">{esc_text(from_avatar_text)}</div>\n'
                                )
                                tw.write(f'                      <div class="wechat-link-cover-from-name">{esc_text(from_text)}</div>\n')
                                tw.write("                    </div>\n")
                            tw.write(f'                    <div class="wechat-link-cover-title">{esc_text(heading or safe_url)}</div>\n')
                            tw.write("                  </a>\n")
                        else:
                            cls = f"wechat-link-card wechat-special-card msg-radius{sent_side_cls}"
                            tw.write(
                                f'                  <a href="{esc_attr(safe_url)}" target="_blank" rel="noreferrer" class="{esc_attr(cls)}" '
                                'style="width:210px;min-width:210px;max-width:210px;display:flex;flex-direction:column;box-sizing:border-box;flex:0 0 auto;background:#fff;border:none;box-shadow:none;text-decoration:none;outline:none">\n'
                            )
                            tw.write('                    <div class="wechat-link-content">\n')
                            tw.write('                      <div class="wechat-link-info">\n')
                            tw.write(f'                        <div class="wechat-link-title">{esc_text(heading or safe_url)}</div>\n')
                            if abstract:
                                tw.write(f'                        <div class="wechat-link-desc">{esc_text(abstract)}</div>\n')
                            tw.write("                      </div>\n")
                            if preview_url:
                                tw.write('                      <div class="wechat-link-thumb">\n')
                                tw.write(
                                    f'                        <img src="{esc_attr(preview_url)}" alt="{esc_attr(heading or "链接预览")}" class="wechat-link-thumb-img" referrerpolicy="no-referrer" />\n'
                                )
                                tw.write("                      </div>\n")
                            tw.write("                    </div>\n")
                            tw.write('                    <div class="wechat-link-from">\n')
                            tw.write(
                                f'                      <div class="wechat-link-from-avatar" aria-hidden="true">{esc_text(from_avatar_text)}</div>\n'
                            )
                            tw.write(f'                      <div class="wechat-link-from-name">{esc_text(from_text)}</div>\n')
                            tw.write("                    </div>\n")
                            tw.write("                  </a>\n")
                    else:
                        tw.write(f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n')
                elif rt == "voip":
                    voip_dir_cls = "wechat-voip-sent" if is_sent else "wechat-voip-received"
                    content_dir_cls = " flex-row-reverse" if is_sent else ""
                    voip_type = str(msg.get("voipType") or "").strip().lower()
                    icon = "wechat-video-light.png" if voip_type == "video" else "wechat-audio-light.png"
                    tw.write(f'                  <div class="wechat-voip-bubble msg-radius {esc_attr(voip_dir_cls)}">\n')
                    tw.write(f'                    <div class="wechat-voip-content{esc_attr(content_dir_cls)}">\n')
                    tw.write(f'                      <img src="{esc_attr(wechat_icon(icon))}" class="wechat-voip-icon" alt="" />\n')
                    tw.write(f'                      <span class="wechat-voip-text">{esc_text(msg.get("content") or "通话")}</span>\n')
                    tw.write("                    </div>\n")
                    tw.write("                  </div>\n")
                elif rt == "quote":
                    tw.write(
                        f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n'
                    )

                    qt = str(msg.get("quoteTitle") or "").strip()
                    qc = str(msg.get("quoteContent") or "").strip()
                    qthumb = str(msg.get("quoteThumbUrl") or "").strip()
                    qtype = str(msg.get("quoteType") or "").strip()
                    qsid_raw = str(msg.get("quoteServerId") or "").strip()
                    qsid = int(qsid_raw) if qsid_raw.isdigit() else 0

                    def is_quoted_voice() -> bool:
                        if qtype == "34":
                            return True
                        return (qc == "[语音]") and bool(qsid_raw)

                    def is_quoted_image() -> bool:
                        if qtype == "3":
                            return True
                        return (qc == "[图片]") and bool(qsid_raw)

                    def is_quoted_link() -> bool:
                        if qtype == "49":
                            return True
                        return bool(re.match(r"^\[链接\]\s*", qc))

                    def get_quoted_link_text() -> str:
                        if not qc:
                            return ""
                        return re.sub(r"^\[链接\]\s*", "", qc).strip() or qc

                    quoted_voice = is_quoted_voice()
                    quoted_image = is_quoted_image()
                    quoted_link = is_quoted_link()

                    quote_voice_url = ""
                    if include_media and ("voice" in media_kinds) and quoted_voice and qsid:
                        try:
                            arc, is_new = _materialize_voice(
                                zf=zf,
                                media_db_path=media_db_path,
                                server_id=int(qsid),
                                media_written=media_written,
                            )
                        except Exception:
                            arc, is_new = "", False
                        if arc:
                            quote_voice_url = rel_path(arc)
                            if is_new:
                                with lock:
                                    job.progress.media_copied += 1

                    quote_image_url = ""
                    if include_media and ("image" in media_kinds) and quoted_image and qsid and resource_conn is not None:
                        md5_hit = ""
                        try:
                            md5_hit = _lookup_resource_md5(
                                resource_conn,
                                resource_chat_id,
                                message_local_type=3,
                                server_id=int(qsid),
                                local_id=0,
                                create_time=0,
                            )
                        except Exception:
                            md5_hit = ""

                        if md5_hit:
                            try:
                                arc, is_new = _materialize_media(
                                    zf=zf,
                                    account_dir=account_dir,
                                    conv_username=conv_username,
                                    kind="image",
                                    md5=str(md5_hit or "").strip().lower(),
                                    file_id="",
                                    media_written=media_written,
                                    suggested_name="",
                                    media_index=media_index,
                                )
                            except Exception:
                                arc, is_new = "", False
                            if arc:
                                quote_image_url = rel_path(arc)
                                if is_new:
                                    with lock:
                                        job.progress.media_copied += 1

                    qthumb_url = ""
                    if is_http_url(qthumb):
                        qthumb_local = maybe_download_remote_image(qthumb) if download_remote_media else ""
                        qthumb_url = qthumb_local or qthumb

                    if qt or qc:
                        tw.write(
                            '                  <div class="mt-[5px] px-2 text-xs text-neutral-600 rounded max-w-[404px] max-h-[65px] overflow-hidden flex items-start bg-[#e1e1e1]">\n'
                        )
                        tw.write('                    <div class="py-2 min-w-0 flex-1">\n')
                        if quoted_voice:
                            seconds = get_voice_duration_in_seconds(msg.get("quoteVoiceLength"))
                            disabled = not bool(quote_voice_url)
                            btn_cls = "flex items-center gap-1 min-w-0 hover:opacity-80"
                            if disabled:
                                btn_cls += " opacity-60 cursor-not-allowed"
                            dis_attr = " disabled" if disabled else ""
                            tw.write('                      <div class="flex items-center gap-1 min-w-0" data-wce-quote-voice-wrapper="1">\n')
                            if qt:
                                tw.write(f'                        <span class="truncate flex-shrink-0">{esc_text(qt)}:</span>\n')
                            tw.write(
                                f'                        <button type="button" data-wce-quote-voice-btn="1" class="{esc_attr(btn_cls)}"{dis_attr}>\n'
                            )
                            tw.write(
                                '                          <svg class="wechat-voice-icon wechat-quote-voice-icon" viewBox="0 0 32 32" fill="currentColor">\n'
                            )
                            tw.write(
                                '                            <path d="M10.24 11.616l-4.224 4.192 4.224 4.192c1.088-1.056 1.76-2.56 1.76-4.192s-0.672-3.136-1.76-4.192z"></path>\n'
                            )
                            tw.write(
                                '                            <path class="voice-wave-2" d="M15.199 6.721l-1.791 1.76c1.856 1.888 3.008 4.48 3.008 7.328s-1.152 5.44-3.008 7.328l1.791 1.76c2.336-2.304 3.809-5.536 3.809-9.088s-1.473-6.784-3.809-9.088z"></path>\n'
                            )
                            tw.write(
                                '                            <path class="voice-wave-3" d="M20.129 1.793l-1.762 1.76c3.104 3.168 5.025 7.488 5.025 12.256s-1.921 9.088-5.025 12.256l1.762 1.76c3.648-3.616 5.887-8.544 5.887-14.016s-2.239-10.432-5.887-14.016z"></path>\n'
                            )
                            tw.write("                          </svg>\n")
                            if seconds > 0:
                                tw.write(f'                          <span class="flex-shrink-0">{esc_text(seconds)}"</span>\n')
                            else:
                                tw.write('                          <span class="flex-shrink-0">语音</span>\n')
                            tw.write("                        </button>\n")
                            if quote_voice_url:
                                tw.write(
                                    f'                        <audio src="{esc_attr(quote_voice_url)}" preload="none" class="hidden" data-wce-quote-voice-audio="1"></audio>\n'
                                )
                            tw.write("                      </div>\n")
                        else:
                            tw.write('                      <div class="min-w-0 flex items-start">\n')
                            if quoted_link:
                                link_text = get_quoted_link_text()
                                tw.write('                        <div class="line-clamp-2 min-w-0 flex-1">\n')
                                if qt:
                                    tw.write(f'                          <span>{esc_text(qt)}:</span>\n')
                                if link_text:
                                    ml = ' class="ml-1"' if qt else ""
                                    tw.write(f'                          <span{ml}>🔗 {esc_text(link_text)}</span>\n')
                                tw.write("                        </div>\n")
                            else:
                                hide_qc = quoted_image and qt and bool(quote_image_url)
                                tw.write('                        <div class="line-clamp-2 min-w-0 flex-1">\n')
                                if qt:
                                    tw.write(f'                          <span>{esc_text(qt)}:</span>\n')
                                if qc and (not hide_qc):
                                    ml = ' class="ml-1"' if qt else ""
                                    tw.write(f'                          <span{ml}>{esc_text(qc)}</span>\n')
                                tw.write("                        </div>\n")
                            tw.write("                      </div>\n")
                        tw.write("                    </div>\n")

                        if quoted_link and qthumb_url:
                            tw.write(
                                f'                    <a href="{esc_attr(qthumb_url)}" target="_blank" rel="noreferrer noopener" class="ml-2 my-2 flex-shrink-0 max-w-[98px] max-h-[49px] overflow-hidden flex items-center justify-center cursor-pointer">\n'
                            )
                            tw.write(
                                f'                      <img src="{esc_attr(qthumb_url)}" alt="引用链接缩略图" class="max-h-[49px] w-auto max-w-[98px] object-contain" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.display=\'none\'" />\n'
                            )
                            tw.write("                    </a>\n")

                        if (not quoted_link) and quoted_image and quote_image_url:
                            tw.write(
                                f'                    <a href="{esc_attr(quote_image_url)}" target="_blank" rel="noreferrer noopener" class="ml-2 my-2 flex-shrink-0 max-w-[98px] max-h-[49px] overflow-hidden flex items-center justify-center cursor-pointer">\n'
                            )
                            tw.write(
                                f'                      <img src="{esc_attr(quote_image_url)}" alt="引用图片" class="max-h-[49px] w-auto max-w-[98px] object-contain" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.display=\'none\'" />\n'
                            )
                            tw.write("                    </a>\n")

                        tw.write("                  </div>\n")
                elif rt == "chatHistory":
                    title = str(msg.get("title") or "").strip() or "聊天记录"
                    record_item = str(msg.get("recordItem") or "").strip()
                    record_item_b64 = ""
                    if record_item:
                        try:
                            record_item_b64 = base64.b64encode(record_item.encode("utf-8", errors="replace")).decode("ascii")
                        except Exception:
                            record_item_b64 = ""

                    if record_item and include_media and (not privacy_mode):
                        try:
                            for m in _CHAT_HISTORY_MD5_TAG_RE.findall(record_item):
                                _ensure_chat_history_md5(m)
                        except Exception:
                            pass
                        if resource_conn is not None:
                            try:
                                server_map = page_media_index.get("serverMd5")
                                if not isinstance(server_map, dict):
                                    server_map = {}
                                    page_media_index["serverMd5"] = server_map

                                for sid_raw in _CHAT_HISTORY_SERVER_ID_TAG_RE.findall(record_item):
                                    sid_text = str(sid_raw or "").strip()
                                    if not sid_text or sid_text in server_map:
                                        continue
                                    if (len(sid_text) > 24) or (not sid_text.isdigit()):
                                        continue
                                    sid = int(sid_text)
                                    if sid <= 0:
                                        continue

                                    md5_hit = ""
                                    try:
                                        md5_hit = _lookup_resource_md5(
                                            resource_conn,
                                            None,  # do NOT filter by chat_id: merged-forward records come from other chats
                                            0,  # do NOT filter by local_type
                                            int(sid),
                                            0,
                                            0,
                                        )
                                    except Exception:
                                        md5_hit = ""

                                    md5_hit = str(md5_hit or "").strip().lower()
                                    if not _is_md5(md5_hit):
                                        continue
                                    if _ensure_chat_history_md5(md5_hit):
                                        server_map[sid_text] = md5_hit
                            except Exception:
                                pass
                        if download_remote_media:
                            try:
                                for u in _CHAT_HISTORY_URL_TAG_RE.findall(record_item):
                                    maybe_download_remote_image(u)
                            except Exception:
                                pass

                    lines = get_chat_history_preview_lines(msg)
                    sent_side_cls = " wechat-special-sent-side" if is_sent else ""
                    cls = f"wechat-chat-history-card wechat-special-card msg-radius{sent_side_cls} cursor-pointer"
                    tw.write(
                        f'                  <div class="{esc_attr(cls)}" data-wce-chat-history="1" role="button" tabindex="0" '
                        f'data-title="{esc_attr(title)}" data-record-item-b64="{esc_attr(record_item_b64)}">\n'
                    )
                    tw.write('                    <div class="wechat-chat-history-body">\n')
                    tw.write(f'                      <div class="wechat-chat-history-title">{esc_text(title)}</div>\n')
                    if lines:
                        tw.write('                      <div class="wechat-chat-history-preview">\n')
                        for line in lines:
                            tw.write(f'                        <div class="wechat-chat-history-line">{esc_text(line)}</div>\n')
                        tw.write("                      </div>\n")
                    tw.write("                    </div>\n")
                    tw.write('                    <div class="wechat-chat-history-bottom"><span>聊天记录</span></div>\n')
                    tw.write("                  </div>\n")
                elif rt == "transfer":
                    received = is_transfer_received(msg)
                    returned = is_transfer_returned(msg)
                    overdue = is_transfer_overdue(msg)
                    side_cls = "wechat-transfer-sent-side" if is_sent else "wechat-transfer-received-side"
                    cls_parts = ["wechat-transfer-card", "msg-radius", side_cls]
                    if received:
                        cls_parts.append("wechat-transfer-received")
                    if returned:
                        cls_parts.append("wechat-transfer-returned")
                    if overdue:
                        cls_parts.append("wechat-transfer-overdue")
                    cls = " ".join(cls_parts)
                    if returned:
                        icon = "wechat-returned.png"
                    elif overdue:
                        icon = "overdue.png"
                    elif received:
                        icon = "wechat-trans-icon2.png"
                    else:
                        icon = "wechat-trans-icon1.png"
                    amount = format_transfer_amount(msg.get("amount"))
                    status = get_transfer_title(msg, is_sent=is_sent)
                    tw.write(f'                  <div class="{esc_attr(cls)}">\n')
                    tw.write('                    <div class="wechat-transfer-content">\n')
                    tw.write(f'                      <img src="{esc_attr(wechat_icon(icon))}" class="wechat-transfer-icon" alt="" />\n')
                    tw.write('                      <div class="wechat-transfer-info">\n')
                    if amount:
                        tw.write(f'                        <span class="wechat-transfer-amount">¥{esc_text(amount)}</span>\n')
                    tw.write(f'                        <span class="wechat-transfer-status">{esc_text(status)}</span>\n')
                    tw.write("                      </div>\n")
                    tw.write("                    </div>\n")
                    tw.write('                    <div class="wechat-transfer-bottom"><span>微信转账</span></div>\n')
                    tw.write("                  </div>\n")
                elif rt == "redPacket":
                    received = False
                    cls_parts = ["wechat-redpacket-card", "wechat-special-card", "msg-radius"]
                    if received:
                        cls_parts.append("wechat-redpacket-received")
                    if is_sent:
                        cls_parts.append("wechat-special-sent-side")
                    icon = "wechat-trans-icon4.png" if received else "wechat-trans-icon3.png"
                    tw.write(f'                  <div class="{esc_attr(" ".join(cls_parts))}">\n')
                    tw.write('                    <div class="wechat-redpacket-content">\n')
                    tw.write(f'                      <img src="{esc_attr(wechat_icon(icon))}" class="wechat-redpacket-icon" alt="" />\n')
                    tw.write('                      <div class="wechat-redpacket-info">\n')
                    tw.write(f'                        <span class="wechat-redpacket-text">{esc_text(get_red_packet_text(msg))}</span>\n')
                    if received:
                        tw.write('                        <span class="wechat-redpacket-status">已领取</span>\n')
                    tw.write("                      </div>\n")
                    tw.write("                    </div>\n")
                    tw.write('                    <div class="wechat-redpacket-bottom"><span>微信红包</span></div>\n')
                    tw.write("                  </div>\n")
                elif rt == "text":
                    tw.write(f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n')
                else:
                    content = str(msg.get("content") or "").strip()
                    if not content:
                        content = f"[{str(msg.get('type') or 'unknown')}] 消息"
                    tw.write(f'                  <div class="{esc_attr(bubble_unknown_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(content)}</div>\n')

                tw.write("                </div>\n")
                tw.write("              </div>\n")
                tw.write("            </div>\n")
                tw.write("          </div>\n")

                _mark_exported()
                if ts:
                    prev_ts = ts

            if page_size > 0:
                _close_page_fp()
                paged_total_pages = max(1, len(page_frag_paths))
                paged_pad_width = max(4, len(str(paged_total_pages)))
                if page_frag_paths:
                    paged_old_page_paths = list(page_frag_paths[:-1])
                    tw.set_target(hw)
                    try:
                        tw.write(page_frag_paths[-1].read_text(encoding="utf-8"))
                    except Exception:
                        try:
                            tw.write(page_frag_paths[-1].read_text(encoding="utf-8", errors="ignore"))
                        except Exception:
                            pass
                else:
                    paged_old_page_paths = []
                    tw.set_target(hw)

            # Close message list + container
            tw.set_target(hw)
            tw.write("          </div>\n")
            tw.write("        </div>\n")

            if page_size > 0 and paged_total_pages > 1:
                page_meta = {
                    "schemaVersion": 1,
                    "pageSize": int(page_size),
                    "totalPages": int(paged_total_pages),
                    "initialPage": int(paged_total_pages),
                    "totalMessages": int(exported),
                    "padWidth": int(paged_pad_width),
                    "pageFilePrefix": "pages/page-",
                    "pageFileSuffix": ".js",
                    "inlinedPages": [int(paged_total_pages)],
                }
                try:
                    page_meta_payload = json.dumps(page_meta, ensure_ascii=False)
                except Exception:
                    page_meta_payload = "{}"
                page_meta_payload = page_meta_payload.replace("</", "<\\/")
                tw.write(f'<script type="application/json" id="wcePageMeta">{page_meta_payload}</script>\n')

            tw.write("      </div>\n")
            tw.write("    </div>\n")
            tw.write("  </div>\n")
            tw.write("</div>\n")
            tw.write("</div>\n")
            tw.write(_html_export_attribution_html())

            try:
                media_index_payload = json.dumps(page_media_index, ensure_ascii=False)
            except Exception:
                media_index_payload = "{}"
            media_index_payload = media_index_payload.replace("</", "<\\/")
            tw.write(f'<script type="application/json" id="wceMediaIndex">{media_index_payload}</script>\n')

            tw.write("</body>\n")
            tw.write("</html>\n")
            tw.flush()
            _log_writer_progress(
                trace,
                export_format="html",
                job=job,
                conv_username=conv_username,
                scanned=scanned,
                exported=exported,
                force=True,
            )
            _safe_trace(
                trace,
                "messages_temp_written",
                scanned=scanned,
                exported=exported,
                pagedFragments=len(page_frag_paths),
            )

        phase_started = time.perf_counter()
        zf.write(str(tmp_path), arcname)
        _safe_trace(trace, "zip_entry_written", durationMs=_elapsed_ms(phase_started), arcname=arcname)

        if page_size > 0 and paged_old_page_paths:
            phase_started = time.perf_counter()
            for page_no, frag_path in enumerate(paged_old_page_paths, start=1):
                _raise_if_job_cancelled(
                    job,
                    "html.page_fragment_write",
                    trace,
                    conversation=conv_username,
                    page=page_no,
                    totalPages=len(paged_old_page_paths),
                )
                try:
                    frag_text = frag_path.read_text(encoding="utf-8")
                except Exception:
                    try:
                        frag_text = frag_path.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        frag_text = ""
                frag_text = _minify_html_for_export(frag_text)


                num = str(page_no).zfill(int(paged_pad_width or 4))
                arc_js = f"{conv_dir}/pages/page-{num}.js"
                js_payload = _html_export_page_fragment_js(
                    export_id=str(getattr(job, "export_id", "") or ""),
                    arc_js=arc_js,
                    page_no=int(page_no),
                    fragment_html=frag_text,
                )
                zf.writestr(arc_js, js_payload)
            _safe_trace(
                trace,
                "page_fragments_written",
                durationMs=_elapsed_ms(phase_started),
                fragments=len(paged_old_page_paths),
            )

    _safe_trace(trace, "writer_done", exported=exported)
    return exported


def _format_message_line_txt(*, msg: dict[str, Any]) -> str:
    ts = int(msg.get("createTime") or 0)
    time_text = _format_ts(ts)
    sender_username = str(msg.get("senderUsername") or "").strip()
    sender_display = str(msg.get("senderDisplayName") or "").strip()
    if sender_display and sender_username:
        sender = f"{sender_display}({sender_username})"
    else:
        sender = sender_display or sender_username or "未知"

    avatar_path = str(msg.get("senderAvatarPath") or "").strip()
    if avatar_path:
        sender = f"{sender} [avatar={avatar_path}]"

    rt = str(msg.get("renderType") or "text")
    content = str(msg.get("content") or "").strip()
    extra = ""
    if rt == "link":
        title = str(msg.get("title") or "").strip()
        url = str(msg.get("url") or "").strip()
        extra = f" {title} {url}".strip()
    elif rt == "transfer":
        amt = str(msg.get("amount") or "").strip()
        st = str(msg.get("transferStatus") or "").strip()
        extra = f" 金额={amt} 状态={st}".strip()
    elif rt == "file":
        title = str(msg.get("title") or "").strip()
        sz = str(msg.get("fileSize") or "").strip()
        extra = f" {title} size={sz}".strip()

    media = msg.get("offlineMedia") or []
    media_desc = ""
    if isinstance(media, list) and media:
        paths: list[str] = []
        for m in media:
            try:
                p = str(m.get("path") or "").strip()
            except Exception:
                p = ""
            if p:
                paths.append(p)
        if paths:
            media_desc = " " + " ".join(paths)

    if rt == "system":
        return f"[{time_text}] [系统] {content}".rstrip()

    return f"[{time_text}] {sender}: {content}{extra}{media_desc}".rstrip()


def _privacy_scrub_message(
    msg: dict[str, Any],
    *,
    conv_is_group: bool,
    sender_alias_map: dict[str, int],
) -> None:
    sender_username = str(msg.get("senderUsername") or "").strip()
    is_sent = bool(msg.get("isSent"))

    if is_sent:
        alias = "我"
        pseudo_username = "me"
    else:
        if not conv_is_group:
            alias = "对方"
            pseudo_username = "other"
        else:
            idx = sender_alias_map.get(sender_username)
            if idx is None:
                idx = len(sender_alias_map) + 1
                sender_alias_map[sender_username] = idx
            alias = f"成员#{idx}"
            pseudo_username = f"member_{idx}"

    rt = str(msg.get("renderType") or "text").strip() or "text"
    content_map = {
        "text": "[文本]",
        "system": "[系统消息]",
        "image": "[图片]",
        "emoji": "[表情]",
        "video": "[视频]",
        "voice": "[语音]",
        "link": "[链接]",
        "file": "[文件]",
        "transfer": "[转账]",
        "redPacket": "[红包]",
        "quote": "[引用消息]",
        "voip": "[通话]",
    }
    msg["content"] = content_map.get(rt, f"[{rt}]")

    msg["senderDisplayName"] = alias
    msg["senderUsername"] = pseudo_username
    msg["senderAvatarPath"] = ""
    msg["conversationUsername"] = ""

    # Remove potentially sensitive payload fields.
    for k in (
        "title",
        "url",
        "from",
        "fromUsername",
        "linkType",
        "linkStyle",
        "thumbUrl",
        "recordItem",
        "imageMd5",
        "imageFileId",
        "imageMd5Candidates",
        "imageFileIdCandidates",
        "imageUrl",
        "emojiMd5",
        "emojiUrl",
        "videoMd5",
        "videoThumbMd5",
        "videoFileId",
        "videoThumbFileId",
        "videoUrl",
        "videoThumbUrl",
        "voiceLength",
        "quoteUsername",
        "quoteServerId",
        "quoteType",
        "quoteThumbUrl",
        "quoteVoiceLength",
        "quoteTitle",
        "quoteContent",
        "amount",
        "coverUrl",
        "fileSize",
        "fileMd5",
        "paySubType",
        "transferStatus",
        "transferId",
        "voipType",
    ):
        if k in msg:
            msg[k] = ""

    msg.pop("offlineMedia", None)


def _attach_offline_media(
    *,
    zf: zipfile.ZipFile,
    account_dir: Path,
    conv_username: str,
    msg: dict[str, Any],
    media_written: dict[str, str],
    report: dict[str, Any],
    media_kinds: list[MediaKind],
    allow_process_key_extract: bool,
    media_db_path: Path,
    media_index: Optional[MediaPathIndex],
    lock: threading.Lock,
    job: ExportJob,
) -> None:
    # allow_process_key_extract is reserved; this project does not extract keys from process (use wx_key instead).
    _ = allow_process_key_extract

    rt = str(msg.get("renderType") or "")
    _raise_if_job_cancelled(
        job,
        "attach_offline_media.start",
        conversation=conv_username,
        renderType=rt,
        messageId=msg.get("id"),
        serverId=msg.get("serverId"),
    )

    def record_missing(kind: str, ident: str) -> None:
        with lock:
            job.progress.media_missing += 1
        try:
            report["missingMedia"].append(
                {
                    "kind": kind,
                    "id": ident,
                    "conversation": conv_username,
                    "messageId": msg.get("id"),
                }
            )
        except Exception:
            pass

    offline: list[dict[str, Any]] = []

    if rt == "image" and "image" in media_kinds:
        primary_md5 = str(msg.get("imageMd5") or "").strip().lower()
        primary_file_id = str(msg.get("imageFileId") or "").strip()

        md5_candidates_raw = msg.get("imageMd5Candidates") or []
        file_id_candidates_raw = msg.get("imageFileIdCandidates") or []
        md5_candidates = md5_candidates_raw if isinstance(md5_candidates_raw, list) else []
        file_id_candidates = file_id_candidates_raw if isinstance(file_id_candidates_raw, list) else []

        md5s: list[str] = []
        file_ids: list[str] = []

        def add_md5(v: Any) -> None:
            s = str(v or "").strip().lower()
            if _is_md5(s) and s not in md5s:
                md5s.append(s)

        def add_file_id(v: Any) -> None:
            s = str(v or "").strip()
            if s and s not in file_ids:
                file_ids.append(s)

        add_md5(primary_md5)
        for v in md5_candidates:
            add_md5(v)

        add_file_id(primary_file_id)
        for v in file_id_candidates:
            add_file_id(v)

        arc = ""
        is_new = False
        used_md5 = ""
        used_file_id = ""

        # Prefer md5-based resolution first (more reliable), then fall back to file_id search.
        for md5 in md5s:
            arc, is_new = _materialize_media(
                zf=zf,
                account_dir=account_dir,
                conv_username=conv_username,
                kind="image",
                md5=md5,
                file_id="",
                media_written=media_written,
                suggested_name="",
                media_index=media_index,
            )
            if arc:
                used_md5 = md5
                break

        if not arc:
            for file_id in file_ids:
                arc, is_new = _materialize_media(
                    zf=zf,
                    account_dir=account_dir,
                    conv_username=conv_username,
                    kind="image",
                    md5="",
                    file_id=file_id,
                    media_written=media_written,
                    suggested_name="",
                    media_index=media_index,
                )
                if arc:
                    used_file_id = file_id
                    break

        if arc:
            # Keep primary fields in sync with what actually resolved.
            try:
                if used_md5:
                    msg["imageMd5"] = used_md5
                if used_file_id:
                    msg["imageFileId"] = used_file_id
            except Exception:
                pass

            offline.append({"kind": "image", "path": arc, "md5": used_md5 or primary_md5, "fileId": used_file_id or primary_file_id})
            if is_new:
                with lock:
                    job.progress.media_copied += 1
        else:
            record_missing("image", primary_md5 or primary_file_id)

    if rt == "emoji" and "emoji" in media_kinds:
        md5 = str(msg.get("emojiMd5") or "").strip().lower()
        arc, is_new = _materialize_media(
            zf=zf,
            account_dir=account_dir,
            conv_username=conv_username,
            kind="emoji",
            md5=md5 if _is_md5(md5) else "",
            file_id="",
            media_written=media_written,
            suggested_name="",
            media_index=media_index,
        )
        if arc:
            offline.append({"kind": "emoji", "path": arc, "md5": md5})
            if is_new:
                with lock:
                    job.progress.media_copied += 1
        else:
            record_missing("emoji", md5)

    if rt == "video":
        if "video_thumb" in media_kinds:
            md5 = str(msg.get("videoThumbMd5") or "").strip().lower()
            file_id = str(msg.get("videoThumbFileId") or "").strip()
            arc, is_new = _materialize_media(
                zf=zf,
                account_dir=account_dir,
                conv_username=conv_username,
                kind="video_thumb",
                md5=md5 if _is_md5(md5) else "",
                file_id=file_id,
                media_written=media_written,
                suggested_name="",
                media_index=media_index,
            )
            if arc:
                offline.append({"kind": "video_thumb", "path": arc, "md5": md5, "fileId": file_id})
                if is_new:
                    with lock:
                        job.progress.media_copied += 1
            else:
                record_missing("video_thumb", md5 or file_id)

        if "video" in media_kinds:
            md5 = str(msg.get("videoMd5") or "").strip().lower()
            file_id = str(msg.get("videoFileId") or "").strip()
            arc, is_new = _materialize_media(
                zf=zf,
                account_dir=account_dir,
                conv_username=conv_username,
                kind="video",
                md5=md5 if _is_md5(md5) else "",
                file_id=file_id,
                media_written=media_written,
                suggested_name="",
                media_index=media_index,
            )
            if arc:
                offline.append({"kind": "video", "path": arc, "md5": md5, "fileId": file_id})
                if is_new:
                    with lock:
                        job.progress.media_copied += 1
            else:
                record_missing("video", md5 or file_id)

    if rt == "voice" and "voice" in media_kinds:
        server_id = int(msg.get("serverId") or 0)
        if server_id > 0:
            arc, is_new = _materialize_voice(
                zf=zf,
                media_db_path=media_db_path,
                server_id=server_id,
                media_written=media_written,
            )
            if arc:
                offline.append({"kind": "voice", "path": arc, "serverId": server_id})
                if is_new:
                    with lock:
                        job.progress.media_copied += 1
            else:
                record_missing("voice", str(server_id))

    if rt == "file" and "file" in media_kinds:
        md5 = str(msg.get("fileMd5") or "").strip().lower()
        arc, is_new = _materialize_media(
            zf=zf,
            account_dir=account_dir,
            conv_username=conv_username,
            kind="file",
            md5=md5 if _is_md5(md5) else "",
            file_id="",
            media_written=media_written,
            suggested_name=str(msg.get("title") or "").strip(),
            media_index=media_index,
        )
        if arc:
            offline.append({"kind": "file", "path": arc, "md5": md5, "title": str(msg.get("title") or "").strip()})
            if is_new:
                with lock:
                    job.progress.media_copied += 1
        else:
            record_missing("file", md5)

    if offline:
        msg["offlineMedia"] = offline


def _materialize_avatar(
    *,
    zf: zipfile.ZipFile,
    head_image_conn: Optional[sqlite3.Connection],
    username: str,
    avatar_written: dict[str, str],
) -> str:
    started_at = time.perf_counter()
    u = str(username or "").strip()
    if not u or head_image_conn is None:
        return ""

    key = f"avatar:{u}"
    if key in avatar_written:
        return avatar_written[key]

    try:
        row = head_image_conn.execute(
            "SELECT image_buffer FROM head_image WHERE username = ? ORDER BY update_time DESC LIMIT 1",
            (u,),
        ).fetchone()
    except Exception:
        row = None

    if not row or row[0] is None:
        avatar_written[key] = ""
        return ""

    data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)
    if not data:
        avatar_written[key] = ""
        return ""

    mt = _detect_image_media_type(data[:32])
    ext = "dat"
    if mt == "image/png":
        ext = "png"
    elif mt == "image/jpeg":
        ext = "jpg"
    elif mt == "image/gif":
        ext = "gif"
    elif mt == "image/webp":
        ext = "webp"

    safe = _safe_name(u, max_len=50) or "avatar"
    h = uuid.uuid5(uuid.NAMESPACE_DNS, u).hex[:8]
    arc = f"media/avatars/{safe}_{h}.{ext}"
    if len(arc) > 220:
        arc = f"media/avatars/avatar_{h}.{ext}"

    try:
        zf.writestr(arc, data)
    except Exception:
        avatar_written[key] = ""
        return ""

    avatar_written[key] = arc
    _log_export_slow_step(
        "materialize_avatar",
        started_at,
        username=u,
        arc=arc,
        bytes=len(data),
    )
    return arc


def _materialize_voice(
    *,
    zf: zipfile.ZipFile,
    media_db_path: Path,
    server_id: int,
    media_written: dict[str, str],
) -> tuple[str, bool]:
    started_at = time.perf_counter()
    key = f"voice:{int(server_id)}"
    existing = media_written.get(key)
    if existing:
        return existing, False

    if not media_db_path.exists():
        return "", False

    conn = sqlite3.connect(str(media_db_path))
    try:
        row = conn.execute(
            "SELECT voice_data FROM VoiceInfo WHERE svr_id = ? ORDER BY create_time DESC LIMIT 1",
            (int(server_id),),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row or row[0] is None:
        return "", False

    data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)

    payload, ext, _media_type = _convert_silk_to_browser_audio(data, preferred_format="mp3")
    if not payload:
        _log_export_slow_step(
            "materialize_voice_failed",
            started_at,
            serverId=server_id,
            reason="convert_failed",
        )
        return "", False

    arc = f"media/voices/voice_{int(server_id)}.{ext}"
    zf.writestr(arc, payload)
    media_written[key] = arc
    _log_export_slow_step(
        "materialize_voice",
        started_at,
        serverId=server_id,
        arc=arc,
        bytes=len(payload),
    )
    return arc, True


def _materialize_media(
    *,
    zf: zipfile.ZipFile,
    account_dir: Path,
    conv_username: str,
    kind: MediaKind,
    md5: str,
    file_id: str,
    media_written: dict[str, str],
    suggested_name: str,
    media_index: Optional[MediaPathIndex],
) -> tuple[str, bool]:
    started_at = time.perf_counter()
    ident = md5 or file_id
    if not ident:
        return "", False

    key = f"{kind}:{ident}"
    if key in media_written:
        return media_written.get(key) or "", False

    src: Optional[Path] = None
    resolved_via_index = False
    backfill_index = False
    known_missing = False
    if media_index is not None:
        try:
            known_missing = media_index.is_known_missing(
                kind=str(kind),
                md5=str(md5 or "").strip().lower(),
                file_id=str(file_id or "").strip(),
                username=str(conv_username or "").strip(),
            )
        except Exception:
            known_missing = False
    allow_fallback_scan = kind != "emoji"
    if media_index is not None and kind in {"image", "video", "video_thumb", "file"}:
        allow_fallback_scan = False
    if known_missing:
        allow_fallback_scan = False
    allow_file_id_fallback = bool(file_id) and not known_missing
    if media_index is not None and kind in {"image", "video", "video_thumb", "file"}:
        allow_file_id_fallback = False
    if md5 and _is_md5(md5):
        cache_lookup_started = time.perf_counter()
        try:
            src = _try_find_decrypted_resource(account_dir, md5)
        except Exception:
            src = None
        _log_export_slow_step(
            "materialize_media_cache_lookup",
            cache_lookup_started,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            hit=bool(src),
        )

    if src is None and media_index is not None:
        index_lookup_started = time.perf_counter()
        try:
            src = media_index.resolve(
                kind=str(kind),
                md5=str(md5 or "").strip().lower(),
                file_id=str(file_id or "").strip(),
                username=str(conv_username or "").strip(),
            )
            resolved_via_index = bool(src)
        except Exception:
            src = None
        _log_export_slow_step(
            "materialize_media_index_lookup",
            index_lookup_started,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            hit=bool(src),
            hasMd5=bool(md5 and _is_md5(md5)),
            hasFileId=bool(file_id),
            knownMissing=bool(known_missing),
        )

    if src is None and md5 and _is_md5(md5):
        resolve_started = time.perf_counter()
        try:
            src = _resolve_media_path_for_kind(
                account_dir,
                kind=kind,
                md5=md5,
                username=conv_username,
                allow_fallback_scan=False,
            )
        except Exception:
            src = None
        _log_export_slow_step(
            "materialize_media_resolve_md5",
            resolve_started,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            hit=bool(src),
            fallbackScan=False,
        )

    if src is None and file_id and media_index is None:
        file_id_lookup_started = time.perf_counter()
        try:
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            for r in [wxid_dir, db_storage_dir]:
                if not r:
                    continue
                hit = _fallback_search_media_by_file_id(
                    str(r),
                    str(file_id),
                    kind=str(kind),
                    username=str(conv_username or ""),
                )
                if hit:
                    src = Path(hit)
                    break
        except Exception:
            src = None
        _log_export_slow_step(
            "materialize_media_resolve_file_id",
            file_id_lookup_started,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            hit=bool(src),
        )

    if src is None and md5 and _is_md5(md5) and allow_fallback_scan:
        fallback_md5_started = time.perf_counter()
        try:
            src = _resolve_media_path_for_kind(
                account_dir,
                kind=kind,
                md5=md5,
                username=conv_username,
                allow_fallback_scan=True,
            )
        except Exception:
            src = None
        backfill_index = bool(src)
        _log_export_slow_step(
            "materialize_media_resolve_md5_fallback",
            fallback_md5_started,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            hit=bool(src),
            fallbackScan=True,
        )

    if src is None and allow_file_id_fallback:
        file_id_lookup_started = time.perf_counter()
        try:
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            for r in [wxid_dir, db_storage_dir]:
                if not r:
                    continue
                hit = _fallback_search_media_by_file_id(
                    str(r),
                    str(file_id),
                    kind=str(kind),
                    username=str(conv_username or ""),
                )
                if hit:
                    src = Path(hit)
                    break
        except Exception:
            src = None
        backfill_index = bool(src)
        _log_export_slow_step(
            "materialize_media_resolve_file_id",
            file_id_lookup_started,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            hit=bool(src),
            fallbackScan=True,
        )

    if src is not None and media_index is not None and backfill_index and not resolved_via_index:
        try:
            media_index.remember_path(
                kind=str(kind),
                path=src,
                username=str(conv_username or "").strip(),
            )
        except Exception:
            pass

    if not src:
        if media_index is not None:
            try:
                media_index.mark_missing(
                    kind=str(kind),
                    md5=str(md5 or "").strip().lower(),
                    file_id=str(file_id or "").strip(),
                    username=str(conv_username or "").strip(),
                )
            except Exception:
                pass
        media_written[key] = ""
        _log_export_slow_step(
            "materialize_media_miss",
            started_at,
            kind=kind,
            ident=ident,
            conversation=conv_username,
            fallbackScan=bool(allow_fallback_scan),
            fileIdFallback=bool(allow_file_id_fallback),
            knownMissing=bool(known_missing),
            lookupMode=("md5" if md5 else "file_id"),
        )
        return "", False

    try:
        if not src.exists() or (not src.is_file()):
            return "", False
    except Exception:
        return "", False

    try:
        with open(src, "rb") as f:
            head = f.read(64)
    except Exception:
        head = b""

    head_mt = _detect_image_media_type(head[:32])
    looks_like_mp4 = len(head) >= 8 and head[4:8] == b"ftyp"

    ext = src.suffix.lstrip(".").lower()
    if not ext:
        if head_mt.startswith("image/"):
            ext = head_mt.split("/", 1)[-1]
        elif looks_like_mp4:
            ext = "mp4"
        else:
            ext = "dat"

    if ext == "jpeg":
        ext = "jpg"

    folder = "misc"
    if kind == "image":
        folder = "images"
    elif kind == "emoji":
        folder = "emojis"
    elif kind == "video":
        folder = "videos"
    elif kind == "video_thumb":
        folder = "video_thumbs"
    elif kind == "file":
        folder = "files"

    nice = _safe_name(suggested_name, max_len=60)
    if nice and kind == "file":
        arc_name = f"{nice}_{ident}.{ext}" if ext else f"{nice}_{ident}"
    else:
        arc_name = f"{ident}.{ext}" if ext else ident
    if len(arc_name) > 160:
        arc_name = arc_name[:160]

    arc = f"media/{folder}/{arc_name}"
    should_stream_copy = False
    if kind == "file":
        should_stream_copy = True
    elif kind in {"image", "emoji", "video_thumb"}:
        should_stream_copy = (
            (ext == "jpg" and head_mt == "image/jpeg")
            or (ext == "png" and head_mt == "image/png")
            or (ext == "gif" and head_mt == "image/gif")
            or (ext == "webp" and head_mt == "image/webp")
        )
    elif kind == "video":
        should_stream_copy = ext == "mp4" and looks_like_mp4

    if should_stream_copy or (kind not in {"image", "emoji", "video", "video_thumb"}):
        try:
            zf.write(src, arcname=arc)
        except Exception:
            return "", False
    else:
        try:
            data, mt = _read_and_maybe_decrypt_media(src, account_dir=account_dir)
        except Exception:
            try:
                zf.write(src, arcname=arc)
            except Exception:
                return "", False
            media_written[key] = arc
            return arc, True

        mt = str(mt or "").strip()
        if mt == "image/png":
            ext2 = "png"
        elif mt == "image/jpeg":
            ext2 = "jpg"
        elif mt == "image/gif":
            ext2 = "gif"
        elif mt == "image/webp":
            ext2 = "webp"
        elif mt == "video/mp4":
            ext2 = "mp4"
        else:
            ext2 = "dat" if mt == "application/octet-stream" else (ext or "dat")

        if ext2 != ext:
            if nice and kind == "file":
                arc_name = f"{nice}_{ident}.{ext2}" if ext2 else f"{nice}_{ident}"
            else:
                arc_name = f"{ident}.{ext2}" if ext2 else ident
            if len(arc_name) > 160:
                arc_name = arc_name[:160]
            arc = f"media/{folder}/{arc_name}"

        try:
            zf.writestr(arc, data)
        except Exception:
            return "", False

    media_written[key] = arc
    try:
        src_size = int(src.stat().st_size)
    except Exception:
        src_size = 0
    _log_export_slow_step(
        "materialize_media",
        started_at,
        kind=kind,
        ident=ident,
        conversation=conv_username,
        src=str(src),
        arc=arc,
        bytes=src_size,
        streamed=bool(should_stream_copy or (kind not in {"image", "emoji", "video", "video_thumb"})),
    )
    return arc, True


CHAT_EXPORT_MANAGER = ChatExportManager()
