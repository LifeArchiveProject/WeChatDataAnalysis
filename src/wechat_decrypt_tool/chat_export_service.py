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
from typing import Any, Iterable, Literal, Optional
from urllib.parse import urljoin, urlparse

import requests

from .chat_helpers import (
    _decode_message_content,
    _decode_sqlite_text,
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
    _parse_system_message_content,
    _parse_pat_message,
    _pick_display_name,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
    _resource_lookup_chat_id,
    _should_keep_session,
    _split_group_sender_prefix,
)
from .logging_config import get_logger
from .media_helpers import (
    _convert_silk_to_wav,
    _detect_image_media_type,
    _fallback_search_media_by_file_id,
    _read_and_maybe_decrypt_media,
    _resolve_account_db_storage_dir,
    _resolve_account_wxid_dir,
    _resolve_media_path_for_kind,
    _try_find_decrypted_resource,
)

logger = get_logger(__name__)

ExportFormat = Literal["json", "txt", "html"]
ExportScope = Literal["selected", "all", "groups", "singles"]
ExportStatus = Literal["queued", "running", "done", "error", "cancelled"]
MediaKind = Literal["image", "emoji", "video", "video_thumb", "voice", "file"]


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

    # Repo default: `frontend/.output/public` after `npm --prefix frontend run generate`.
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "frontend" / ".output" / "public")

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
_CHAT_HISTORY_URL_TAG_RE = re.compile(r"(?i)<(?:sourceheadurl|cdnurlstring|encrypturlstring|externurl)>(https?://[^<\\s]+)<")
_CHAT_HISTORY_SERVER_ID_TAG_RE = re.compile(r"(?i)<fromnewmsgid>\\s*(\\d+)\\s*<")


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
      - All `_nuxt/*.css` chunks (scoped selectors stripped; chat chunk appended last)
      - `_HTML_EXPORT_CSS_PATCH` appended last

    Falls back to `_HTML_EXPORT_CSS_FALLBACK` when entry css is missing.
    """

    if ui_public_dir is None:
        try:
            report["errors"].append("WARN: Nuxt UI dir not found; export HTML will use fallback styles.")
        except Exception:
            pass
        return _HTML_EXPORT_CSS_FALLBACK + "\n\n" + _HTML_EXPORT_CSS_PATCH

    entry_css = _load_ui_entry_css(ui_public_dir)
    if not entry_css:
        try:
            report["errors"].append("WARN: Nuxt UI CSS not found; export HTML will use fallback styles.")
        except Exception:
            pass
        return _HTML_EXPORT_CSS_FALLBACK + "\n\n" + _HTML_EXPORT_CSS_PATCH

    entry_css = _strip_vue_scoped_attrs(entry_css)

    nuxt_dir = Path(ui_public_dir) / "_nuxt"
    extra_css_paths: list[Path] = []
    try:
        extra_css_paths = [p for p in nuxt_dir.glob("*.css") if (p.is_file() and (not p.name.startswith("entry.")))]
    except Exception:
        extra_css_paths = []

    chat_css_paths = [p for p in extra_css_paths if "_username_" in p.name]
    other_css_paths = [p for p in extra_css_paths if p not in chat_css_paths]
    other_css_paths.sort(key=lambda p: p.name)
    chat_css_paths.sort(key=lambda p: p.name)

    if not chat_css_paths:
        try:
            report["errors"].append(
                "WARN: Nuxt chat CSS chunk not found (*_username_*.css); some message styles may be missing."
            )
        except Exception:
            pass

    extra_chunks: list[str] = []
    for p in [*other_css_paths, *chat_css_paths]:
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
    parts.append(_HTML_EXPORT_CSS_PATCH)
    return "\n\n".join(parts)


_TS_WECHAT_EMOJI_ENTRY_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*:\s*"(?P<value>[^"]+)"\s*,?\s*$')


@functools.lru_cache(maxsize=1)
def _load_wechat_emoji_table() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "frontend" / "utils" / "wechat-emojis.ts"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    table: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        match = _TS_WECHAT_EMOJI_ENTRY_RE.match(line)
        if match:
            key = str(match.group("key") or "")
            value = str(match.group("value") or "")
            if key and value:
                table[key] = value
    return table


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
    return ""


_HTML_EXPORT_CSS_FALLBACK = """
/* Fallback styles for chat export HTML (Nuxt build CSS not found). */
html, body { height: 100%; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
    "Helvetica Neue", Helvetica, Arial, sans-serif;
  background: #EDEDED;
  color: #111827;
}
a { color: inherit; }
"""


_HTML_EXPORT_CSS_PATCH = """
/* Offline HTML viewer patch */
:root {
  --dpr: 1;
  --message-radius: 4px;
  /* Keep consistent with `frontend/app.vue`. */
  --sidebar-rail-step: 48px;
  --sidebar-rail-btn: 32px;
  --sidebar-rail-icon: 24px;
}
html, body { height: 100%; }
body { background: #EDEDED; }

/* Layout helpers (used by exported HTML). */
.wce-root { height: 100vh; display: flex; overflow: hidden; background: #EDEDED; }
.wce-rail { width: 60px; min-width: 60px; max-width: 60px; background: #e8e7e7; border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; }
.wce-session-panel { width: calc(var(--session-list-width, 295px) / var(--dpr)); min-width: calc(var(--session-list-width, 295px) / var(--dpr)); max-width: calc(var(--session-list-width, 295px) / var(--dpr)); background: #F7F7F7; border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; min-height: 0; }
.wce-chat-area { flex: 1; display: flex; flex-direction: column; min-height: 0; background: #EDEDED; }
.wce-chat-main { flex: 1; display: flex; min-height: 0; }
.wce-chat-col { flex: 1; display: flex; flex-direction: column; min-height: 0; min-width: 0; position: relative; }
.wce-chat-header { height: 56px; padding: 0 20px; display: flex; align-items: center; border-bottom: 1px solid #e5e7eb; background: #EDEDED; }
.wce-chat-title { font-size: 16px; font-weight: 500; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wce-filter-select { font-size: 12px; padding: 6px 8px; border: 0; border-radius: 8px; background: transparent; color: #374151; }
.wce-message-container { flex: 1; overflow: auto; padding: 16px; min-height: 0; }

/* Single session item (middle column). */
.wce-session-item { display: flex; align-items: center; gap: 12px; padding: 0 12px; height: 80px; border-bottom: 1px solid #f3f4f6; background: #DEDEDE; text-decoration: none; color: inherit; }
.wce-session-avatar { width: 45px; height: 45px; border-radius: 6px; overflow: hidden; background: #d1d5db; flex-shrink: 0; }
.wce-session-avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.wce-session-meta { min-width: 0; flex: 1; }
.wce-session-name { font-size: 14px; font-weight: 600; color: #111827; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wce-session-sub { font-size: 12px; color: #6b7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }

/* Message rows (right column). */
.wce-msg-row { display: flex; align-items: flex-start; margin-bottom: 24px; }
.wce-msg-row-sent { justify-content: flex-end; }
.wce-msg-row-received { justify-content: flex-start; }
.wce-msg { display: flex; align-items: flex-start; max-width: 640px; }
.wce-msg-sent { flex-direction: row-reverse; }
.wce-avatar { width: calc(42px / var(--dpr)); height: calc(42px / var(--dpr)); border-radius: 6px; overflow: hidden; background: #d1d5db; flex-shrink: 0; }
.wce-avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.wce-avatar-sent { margin-left: 12px; }
.wce-avatar-received { margin-right: 12px; }
.wce-sender-name { font-size: 11px; color: #6b7280; margin-bottom: 4px; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Bubble basics (tailwind classes may override when Nuxt CSS is present). */
.wce-bubble { padding: 8px 12px; border-radius: var(--message-radius); font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; max-width: 320px; position: relative; }
.wce-bubble-sent { background: #95EC69; color: #000; }
.wce-bubble-received { background: #fff; color: #1f2937; }

/* WeChat-like bubble tail (fallback). */
.bubble-tail-l, .bubble-tail-r { position: relative; }
.bubble-tail-l::after {
  content: '';
  position: absolute;
  left: -4px;
  top: 12px;
  width: 12px;
  height: 12px;
  background: #FFFFFF;
  transform: rotate(45deg);
  border-radius: 2px;
}
.bubble-tail-r::after {
  content: '';
  position: absolute;
  right: -4px;
  top: 12px;
  width: 12px;
  height: 12px;
  background: #95EC69;
  transform: rotate(45deg);
  border-radius: 2px;
}

/* System messages. */
.wce-system { display: flex; justify-content: center; margin: 16px 0; }
.wce-system > div { font-size: 12px; color: #9e9e9e; padding: 4px 0; }

/* Media blocks. */
.wce-media-img { max-width: 240px; max-height: 240px; border-radius: var(--message-radius); display: block; object-fit: cover; }
.wce-emoji-img { width: 96px; height: 96px; object-fit: contain; display: block; }
.wce-video-wrap { position: relative; display: inline-block; border-radius: var(--message-radius); overflow: hidden; background: rgba(0,0,0,0.05); }
.wce-video-thumb { display: block; width: 220px; max-width: 260px; height: auto; max-height: 260px; object-fit: cover; }
.wce-video-play { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
.wce-video-play > div { width: 48px; height: 48px; border-radius: 9999px; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; }

.wce-file { border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; background: #fff; max-width: 320px; }
.wce-file-name { font-size: 13px; color: #111827; word-break: break-all; }
.wce-file-meta { font-size: 12px; color: #6b7280; margin-top: 4px; }
.wce-file-actions { margin-top: 8px; }
.wce-file-actions a { font-size: 12px; color: #07c160; text-decoration: none; }
.wce-file-actions a:hover { text-decoration: underline; }

.wce-audio { width: 260px; max-width: 92vw; }
.wce-audio-actions { margin-top: 6px; }
.wce-audio-actions a { font-size: 12px; color: #07c160; text-decoration: none; }
.wce-audio-actions a:hover { text-decoration: underline; }

/* Index page helpers. */
.wce-index { min-height: 100vh; background: #EDEDED; }
.wce-index-container { max-width: 880px; margin: 0 auto; padding: 24px; }
.wce-index-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
.wce-index-item { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-bottom: 1px solid #f3f4f6; text-decoration: none; color: inherit; }
.wce-index-item:last-child { border-bottom: 0; }
.wce-index-item:hover { background: #f9fafb; }
.wce-index-title { font-size: 18px; font-weight: 700; color: #111827; margin: 0 0 6px 0; }
.wce-index-sub { font-size: 12px; color: #6b7280; margin: 0 0 16px 0; }
"""


_HTML_EXPORT_JS = r"""
(() => {
  const updateDprVar = () => {
    try {
      const dpr = window.devicePixelRatio || 1
      document.documentElement.style.setProperty('--dpr', String(dpr))
    } catch {}
  }

  const initSessionSearch = () => {
    const input = document.getElementById('sessionSearchInput')
    if (!input) return

    const clearBtn = document.getElementById('sessionSearchClear')
    const items = Array.from(document.querySelectorAll('[data-wce-session-item=\"1\"]'))

    const apply = () => {
      const q = String(input.value || '').trim().toLowerCase()
      try { if (clearBtn) clearBtn.style.display = q ? '' : 'none' } catch {}

      items.forEach((el) => {
        if (!el) return
        const isActive = String(el.getAttribute('aria-current') || '') === 'page'
        const name = String(el.getAttribute('data-wce-session-name') || '').toLowerCase()
        const username = String(el.getAttribute('data-wce-session-username') || '').toLowerCase()
        const show = !q || isActive || name.includes(q) || username.includes(q)
        try { el.style.display = show ? '' : 'none' } catch {}
      })
    }

    input.addEventListener('input', apply)
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        try { input.value = '' } catch {}
        try { input.focus() } catch {}
        apply()
      })
    }
    apply()
  }

  const initVoicePlayback = () => {
    let activeAudio = null
    let activeIcon = null

    const stopAudio = (audio, icon) => {
      if (!audio) return
      try { audio.pause() } catch {}
      try { audio.currentTime = 0 } catch {}
      try { if (icon) icon.classList.remove('voice-playing') } catch {}
    }

    const bindAudioEnd = (audio) => {
      if (!audio) return
      try {
        if (audio.dataset && audio.dataset.wceVoiceBound === '1') return
        if (audio.dataset) audio.dataset.wceVoiceBound = '1'
      } catch {}

      try {
        audio.addEventListener('ended', () => {
          try {
            const wrapper = audio.closest('.wechat-voice-wrapper') || audio.parentElement
            const icon = wrapper ? wrapper.querySelector('.wechat-voice-icon') : null
            if (icon) icon.classList.remove('voice-playing')
          } catch {}

          if (activeAudio === audio) {
            activeAudio = null
            activeIcon = null
          }
        })
      } catch {}
    }

    document.addEventListener('click', (ev) => {
      const target = ev && ev.target

      const quoteBtn = target && target.closest ? target.closest('[data-wce-quote-voice-btn=\"1\"]') : null
      if (quoteBtn) {
        if (quoteBtn.hasAttribute && quoteBtn.hasAttribute('disabled')) return

        const wrapper = quoteBtn.closest ? (quoteBtn.closest('[data-wce-quote-voice-wrapper=\"1\"]') || quoteBtn.parentElement) : quoteBtn.parentElement
        if (!wrapper) return

        const audio = wrapper.querySelector ? (wrapper.querySelector('audio[data-wce-quote-voice-audio=\"1\"]') || wrapper.querySelector('audio')) : null
        if (!audio) return

        bindAudioEnd(audio)

        const icon = (quoteBtn.querySelector && quoteBtn.querySelector('.wechat-voice-icon')) || (wrapper.querySelector && wrapper.querySelector('.wechat-voice-icon'))

        if (activeAudio && activeAudio !== audio) stopAudio(activeAudio, activeIcon)

        const isPlaying = !audio.paused && !audio.ended
        if (activeAudio === audio && isPlaying) {
          stopAudio(audio, icon)
          activeAudio = null
          activeIcon = null
          return
        }

        activeAudio = audio
        activeIcon = icon
        try { if (icon) icon.classList.add('voice-playing') } catch {}
        try {
          const p = audio.play()
          if (p && typeof p.catch === 'function') {
            p.catch(() => {
              stopAudio(audio, icon)
              if (activeAudio === audio) {
                activeAudio = null
                activeIcon = null
              }
            })
          }
        } catch {
          stopAudio(audio, icon)
          if (activeAudio === audio) {
            activeAudio = null
            activeIcon = null
          }
        }
        return
      }

      const bubble = target && target.closest ? target.closest('.wechat-voice-bubble') : null
      if (!bubble) return

      const wrapper = bubble.closest('.wechat-voice-wrapper') || bubble.parentElement
      if (!wrapper) return

      const audio = wrapper.querySelector('audio')
      if (!audio) return

      bindAudioEnd(audio)

      const icon = bubble.querySelector('.wechat-voice-icon') || wrapper.querySelector('.wechat-voice-icon')

      if (activeAudio && activeAudio !== audio) stopAudio(activeAudio, activeIcon)

      const isPlaying = !audio.paused && !audio.ended
      if (activeAudio === audio && isPlaying) {
        stopAudio(audio, icon)
        activeAudio = null
        activeIcon = null
        return
      }

      activeAudio = audio
      activeIcon = icon
      try { if (icon) icon.classList.add('voice-playing') } catch {}
      try {
        const p = audio.play()
        if (p && typeof p.catch === 'function') {
          p.catch(() => {
            stopAudio(audio, icon)
            if (activeAudio === audio) {
              activeAudio = null
              activeIcon = null
            }
          })
        }
      } catch {
        stopAudio(audio, icon)
        if (activeAudio === audio) {
          activeAudio = null
          activeIcon = null
        }
      }
    })
  }

  const applyMessageTypeFilter = () => {
    const select = document.getElementById('messageTypeFilter')
    if (!select) return
    const selected = String(select.value || 'all')
    const nodes = document.querySelectorAll('[data-render-type]')
    nodes.forEach((el) => {
      const rt = String(el.getAttribute('data-render-type') || 'text')
      const show = selected === 'all' ? true : rt === selected
      el.style.display = show ? '' : 'none'
    })
  }

  const scrollToBottom = () => {
    const container = document.getElementById('messageContainer')
    if (!container) return
    container.scrollTop = container.scrollHeight
  }

  const updateSessionMessageCount = () => {
    const el = document.getElementById('sessionMessageCount')
    const container = document.getElementById('messageContainer')
    if (!el || !container) return
    const items = container.querySelectorAll('[data-render-type]')
    el.textContent = String(items.length)
  }

  const safeJsonParse = (text) => {
    try { return JSON.parse(String(text || '')) } catch { return null }
  }

  const readMediaIndex = () => {
    const el = document.getElementById('wceMediaIndex')
    const obj = safeJsonParse(el ? el.textContent : '')
    if (!obj || typeof obj !== 'object') return {}
    return obj
  }

  const isMaybeMd5 = (value) => /^[0-9a-f]{32}$/i.test(String(value || '').trim())
  const pickFirstMd5 = (...values) => {
    for (const v of values) {
      const s = String(v || '').trim()
      if (isMaybeMd5(s)) return s.toLowerCase()
    }
    return ''
  }

  const normalizeChatHistoryUrl = (value) => String(value || '').trim().replace(/\s+/g, '')

  const decodeBase64Utf8 = (b64) => {
    try {
      const bin = atob(String(b64 || ''))
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      if (typeof TextDecoder !== 'undefined') {
        return new TextDecoder('utf-8', { fatal: false }).decode(bytes)
      }
      let out = ''
      for (let i = 0; i < bytes.length; i++) out += String.fromCharCode(bytes[i])
      return out
    } catch {
      return ''
    }
  }

  const resolveMd5Any = (index, md5) => {
    const key = String(md5 || '').trim().toLowerCase()
    if (!key) return ''
    const maps = [
      index && index.images,
      index && index.emojis,
      index && index.videos,
      index && index.videoThumbs,
    ]
    for (const m of maps) {
      try {
        if (m && m[key]) return String(m[key] || '')
      } catch {}
    }
    return ''
  }

  const resolveServerMd5 = (index, serverId) => {
    const key = String(serverId || '').trim()
    if (!key) return ''
    try {
      const v = index && index.serverMd5 && index.serverMd5[key]
      return isMaybeMd5(v) ? String(v || '').trim().toLowerCase() : ''
    } catch {}
    return ''
  }

  const resolveRemoteAny = (index, ...urls) => {
    for (const u0 of urls) {
      const u = normalizeChatHistoryUrl(u0)
      if (!u) continue
      try {
        const local = index && index.remote && index.remote[u]
        if (local) return String(local || '')
      } catch {}
      if (/^https?:\\/\\//i.test(u)) return u
    }
    return ''
  }

  const parseChatHistoryRecord = (recordItemXml) => {
    const xml = String(recordItemXml || '').trim()
    if (!xml) return { info: null, items: [] }

    const normalized = xml
      .replace(/&#x20;/g, ' ')
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
      .replace(/&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[\da-fA-F]+;)/g, '&amp;')

    let doc
    try {
      doc = new DOMParser().parseFromString(normalized, 'text/xml')
    } catch {
      return { info: null, items: [] }
    }

    const parserErrors = doc.getElementsByTagName('parsererror')
    if (parserErrors && parserErrors.length) return { info: null, items: [] }

    const getText = (node, tag) => {
      try {
        const el = node.getElementsByTagName(tag)?.[0]
        return String(el?.textContent || '').trim()
      } catch {
        return ''
      }
    }

    const root = doc?.documentElement
    const isChatRoom = String(getText(root, 'isChatRoom') || '').trim() === '1'
    const title = getText(root, 'title')
    const desc = getText(root, 'desc') || getText(root, 'info')

    const items = Array.from(doc.getElementsByTagName('dataitem') || [])
    const parsed = items.map((node, idx) => {
      const datatype = String(node.getAttribute('datatype') || '').trim()
      const dataid = String(node.getAttribute('dataid') || '').trim() || String(idx)

      const sourcename = getText(node, 'sourcename')
      const sourcetime = getText(node, 'sourcetime')
      const sourceheadurl = normalizeChatHistoryUrl(getText(node, 'sourceheadurl'))
      const datatitle = getText(node, 'datatitle')
      const datadesc = getText(node, 'datadesc')
      const datafmt = getText(node, 'datafmt')
      const duration = getText(node, 'duration')

      const fullmd5 = getText(node, 'fullmd5')
      const thumbfullmd5 = getText(node, 'thumbfullmd5')
      const md5 = getText(node, 'md5') || getText(node, 'emoticonmd5') || getText(node, 'emojiMd5')
      const cdnurlstring = normalizeChatHistoryUrl(getText(node, 'cdnurlstring'))
      const encrypturlstring = normalizeChatHistoryUrl(getText(node, 'encrypturlstring'))
      const externurl = normalizeChatHistoryUrl(getText(node, 'externurl'))
      const aeskey = getText(node, 'aeskey')
      const fromnewmsgid = getText(node, 'fromnewmsgid')
      const srcMsgLocalid = getText(node, 'srcMsgLocalid')
      const srcMsgCreateTime = getText(node, 'srcMsgCreateTime')

      let content = datatitle || datadesc
      if (!content) {
        if (datatype === '4') content = '[视频]'
        else if (datatype === '2' || datatype === '3') content = '[图片]'
        else if (datatype === '47' || datatype === '37') content = '[表情]'
        else if (datatype) content = `[消息 ${datatype}]`
        else content = '[消息]'
      }

      const fmt = String(datafmt || '').trim().toLowerCase().replace(/^\./, '')
      const imageFormats = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'heic', 'heif'])

      let renderType = 'text'
      if (datatype === '4' || String(duration || '').trim() || fmt === 'mp4') {
        renderType = 'video'
      } else if (datatype === '47' || datatype === '37') {
        renderType = 'emoji'
      } else if (
        datatype === '2'
        || datatype === '3'
        || imageFormats.has(fmt)
        || (datatype !== '1' && isMaybeMd5(fullmd5))
      ) {
        renderType = 'image'
      } else if (isMaybeMd5(md5) && /表情/.test(String(content || ''))) {
        renderType = 'emoji'
      }

      return {
        id: dataid,
        datatype,
        sourcename,
        sourcetime,
        sourceheadurl,
        datafmt,
        duration,
        fullmd5,
        thumbfullmd5,
        md5,
        cdnurlstring,
        encrypturlstring,
        externurl,
        aeskey,
        fromnewmsgid,
        srcMsgLocalid,
        srcMsgCreateTime,
        renderType,
        content
      }
    })

    return {
      info: { isChatRoom, title, desc },
      items: parsed
    }
  }

  const initChatHistoryModal = () => {
    const modal = document.getElementById('chatHistoryModal')
    const titleEl = document.getElementById('chatHistoryModalTitle')
    const closeBtn = document.getElementById('chatHistoryModalClose')
    const emptyEl = document.getElementById('chatHistoryModalEmpty')
    const listEl = document.getElementById('chatHistoryModalList')
    if (!modal || !titleEl || !closeBtn || !emptyEl || !listEl) return

    const mediaIndex = readMediaIndex()

    const close = () => {
      try { modal.classList.add('hidden') } catch {}
      try { modal.style.display = 'none' } catch {}
      try { modal.setAttribute('aria-hidden', 'true') } catch {}
      try { document.body.style.overflow = '' } catch {}
      try { titleEl.textContent = '合并消息' } catch {}
      try { listEl.textContent = '' } catch {}
      try { emptyEl.style.display = '' } catch {}
    }

    const renderRecordRow = (rec, info) => {
      const row = document.createElement('div')
      row.className = 'px-4 py-3 flex gap-3 border-b border-gray-100'

      const avatarWrap = document.createElement('div')
      avatarWrap.className = 'w-9 h-9 rounded-md overflow-hidden bg-gray-200 flex-shrink-0'
      const name0 = String(rec?.sourcename || '').trim() || '?'
      const avatarUrlRaw = normalizeChatHistoryUrl(rec?.sourceheadurl)
      const avatarLocal = (mediaIndex && mediaIndex.remote && mediaIndex.remote[avatarUrlRaw]) ? String(mediaIndex.remote[avatarUrlRaw] || '') : ''
      const avatarUrl = avatarLocal || ((avatarUrlRaw && /^https?:\\/\\//i.test(avatarUrlRaw)) ? avatarUrlRaw : '')
      if (avatarUrl) {
        const img = document.createElement('img')
        img.src = avatarUrl
        img.alt = '头像'
        img.className = 'w-full h-full object-cover'
        try { img.referrerPolicy = 'no-referrer' } catch {}
        img.onerror = () => {
          try { avatarWrap.textContent = '' } catch {}
          const fb = document.createElement('div')
          fb.className = 'w-full h-full flex items-center justify-center text-xs font-bold text-gray-600'
          fb.textContent = String(name0.charAt(0) || '?')
          avatarWrap.appendChild(fb)
        }
        avatarWrap.appendChild(img)
      } else {
        const fb = document.createElement('div')
        fb.className = 'w-full h-full flex items-center justify-center text-xs font-bold text-gray-600'
        fb.textContent = String(name0.charAt(0) || '?')
        avatarWrap.appendChild(fb)
      }

      const main = document.createElement('div')
      main.className = 'min-w-0 flex-1'

      const header = document.createElement('div')
      header.className = 'flex items-start gap-2'

      const headerLeft = document.createElement('div')
      headerLeft.className = 'min-w-0 flex-1'
      const senderName = String(rec?.sourcename || '').trim()
      if (info && info.isChatRoom && senderName) {
        const sn = document.createElement('div')
        sn.className = 'text-xs text-gray-500 leading-none truncate mb-1'
        sn.textContent = senderName
        headerLeft.appendChild(sn)
      }

      const headerRight = document.createElement('div')
      headerRight.className = 'text-xs text-gray-400 flex-shrink-0 leading-none'
      const timeText = String(rec?.sourcetime || '').trim()
      headerRight.textContent = timeText

      header.appendChild(headerLeft)
      if (timeText) header.appendChild(headerRight)

      const body = document.createElement('div')
      body.className = 'mt-1'

      const rt = String(rec?.renderType || 'text')
      const content = String(rec?.content || '').trim()
      const serverId = String(rec?.fromnewmsgid || '').trim()
      const serverMd5 = resolveServerMd5(mediaIndex, serverId)

      if (rt === 'video') {
        const videoMd5 = pickFirstMd5(rec?.fullmd5, rec?.md5)
        const thumbMd5 = pickFirstMd5(rec?.thumbfullmd5) || videoMd5
        let videoUrl = resolveMd5Any(mediaIndex, videoMd5)
        if (!videoUrl && serverMd5) videoUrl = resolveMd5Any(mediaIndex, serverMd5)
        if (!videoUrl) videoUrl = resolveRemoteAny(mediaIndex, rec?.externurl, rec?.cdnurlstring, rec?.encrypturlstring)

        let thumbUrl = resolveMd5Any(mediaIndex, thumbMd5)
        if (!thumbUrl && serverMd5) thumbUrl = resolveMd5Any(mediaIndex, serverMd5)
        if (!thumbUrl) thumbUrl = resolveRemoteAny(mediaIndex, rec?.externurl, rec?.cdnurlstring, rec?.encrypturlstring)

        const wrap = document.createElement('div')
        wrap.className = 'msg-radius overflow-hidden relative bg-black/5 inline-block'

        if (thumbUrl) {
          const img = document.createElement('img')
          img.src = thumbUrl
          img.alt = '视频'
          img.className = 'block w-[220px] max-w-[260px] h-auto max-h-[260px] object-cover'
          wrap.appendChild(img)
        } else {
          const t = document.createElement('div')
          t.className = 'px-3 py-2 text-sm text-gray-700'
          t.textContent = content || '[视频]'
          wrap.appendChild(t)
        }

        if (thumbUrl) {
          const overlay = document.createElement(videoUrl ? 'a' : 'div')
          if (videoUrl) {
            overlay.href = videoUrl
            overlay.target = '_blank'
            overlay.rel = 'noreferrer noopener'
          }
          overlay.className = 'absolute inset-0 flex items-center justify-center'
          const btn = document.createElement('div')
          btn.className = 'w-12 h-12 rounded-full bg-black/45 flex items-center justify-center'
          btn.innerHTML = '<svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'
          overlay.appendChild(btn)
          wrap.appendChild(overlay)
        }

        body.appendChild(wrap)
      } else if (rt === 'image') {
        const imageMd5 = pickFirstMd5(rec?.fullmd5, rec?.thumbfullmd5, rec?.md5)
        let imgUrl = resolveMd5Any(mediaIndex, imageMd5)
        if (!imgUrl && serverMd5) imgUrl = resolveMd5Any(mediaIndex, serverMd5)
        if (!imgUrl) imgUrl = resolveRemoteAny(mediaIndex, rec?.externurl, rec?.cdnurlstring, rec?.encrypturlstring)
        if (imgUrl) {
          const outer = document.createElement('div')
          outer.className = 'msg-radius overflow-hidden cursor-pointer inline-block'
          const a = document.createElement('a')
          a.href = imgUrl
          a.target = '_blank'
          a.rel = 'noreferrer noopener'
          const img = document.createElement('img')
          img.src = imgUrl
          img.alt = '图片'
          img.className = 'max-w-[240px] max-h-[240px] object-cover'
          a.appendChild(img)
          outer.appendChild(a)
          body.appendChild(outer)
        } else {
          const t = document.createElement('div')
          t.className = 'px-3 py-2 text-sm text-gray-700 whitespace-pre-wrap break-words'
          t.textContent = content || '[图片]'
          body.appendChild(t)
        }
      } else if (rt === 'emoji') {
        const emojiMd5 = pickFirstMd5(rec?.md5, rec?.fullmd5, rec?.thumbfullmd5)
        let emojiUrl = resolveMd5Any(mediaIndex, emojiMd5)
        if (!emojiUrl && serverMd5) emojiUrl = resolveMd5Any(mediaIndex, serverMd5)
        if (!emojiUrl) emojiUrl = resolveRemoteAny(mediaIndex, rec?.externurl, rec?.cdnurlstring, rec?.encrypturlstring)
        if (emojiUrl) {
          const img = document.createElement('img')
          img.src = emojiUrl
          img.alt = '表情'
          img.className = 'w-24 h-24 object-contain'
          body.appendChild(img)
        } else {
          const t = document.createElement('div')
          t.className = 'px-3 py-2 text-sm text-gray-700 whitespace-pre-wrap break-words'
          t.textContent = content || '[表情]'
          body.appendChild(t)
        }
      } else {
        const t = document.createElement('div')
        t.className = 'px-3 py-2 text-sm text-gray-700 whitespace-pre-wrap break-words'
        t.textContent = content || ''
        body.appendChild(t)
      }

      main.appendChild(header)
      main.appendChild(body)

      row.appendChild(avatarWrap)
      row.appendChild(main)
      return row
    }

    const openFromCard = (card) => {
      const title = String(card?.getAttribute('data-title') || '合并消息').trim() || '合并消息'
      const b64 = String(card?.getAttribute('data-record-item-b64') || '').trim()
      const xml = decodeBase64Utf8(b64)
      const parsed = parseChatHistoryRecord(xml)
      const info = (parsed && parsed.info) ? parsed.info : { isChatRoom: false }
      let records = (parsed && Array.isArray(parsed.items)) ? parsed.items : []

      if (!records.length) {
        const lines = Array.from(card.querySelectorAll('.wechat-chat-history-line') || [])
          .map((el) => String(el?.textContent || '').trim())
          .filter(Boolean)
        records = lines.map((line, idx) => ({ id: String(idx), renderType: 'text', content: line, sourcename: '', sourcetime: '' }))
      }

      try { titleEl.textContent = title } catch {}
      try { listEl.textContent = '' } catch {}

      if (!records.length) {
        try { emptyEl.style.display = '' } catch {}
      } else {
        try { emptyEl.style.display = 'none' } catch {}
        for (const rec of records) {
          try {
            listEl.appendChild(renderRecordRow(rec, info))
          } catch {}
        }
      }

      try { modal.classList.remove('hidden') } catch {}
      try { modal.style.display = 'flex' } catch {}
      try { modal.setAttribute('aria-hidden', 'false') } catch {}
      try { document.body.style.overflow = 'hidden' } catch {}
    }

    closeBtn.addEventListener('click', (ev) => {
      try { ev.preventDefault() } catch {}
      close()
    })
    modal.addEventListener('click', (ev) => {
      const t = ev && ev.target
      if (t === modal) close()
    })

    document.addEventListener('keydown', (ev) => {
      const key = String(ev?.key || '')
      if (key === 'Escape' && !modal.classList.contains('hidden')) close()
    })

    document.addEventListener('click', (ev) => {
      const target = ev && ev.target
      const card = target && target.closest ? target.closest('[data-wce-chat-history=\"1\"]') : null
      if (!card) return
      try { ev.preventDefault() } catch {}
      openFromCard(card)
    })
  }

  document.addEventListener('DOMContentLoaded', () => {
    updateDprVar()
    try {
      window.addEventListener('resize', updateDprVar)
    } catch {}

    initSessionSearch()
    initVoicePlayback()
    initChatHistoryModal()

    const select = document.getElementById('messageTypeFilter')
    if (select) {
      select.addEventListener('change', applyMessageTypeFilter)
      applyMessageTypeFilter()
    }

    updateSessionMessageCount()
    scrollToBottom()
    try {
      window.addEventListener('load', () => {
        updateSessionMessageCount()
        scrollToBottom()
        setTimeout(scrollToBottom, 60)
      })
    } catch {}
  })
})()
"""


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
        privacy_mode: bool,
        file_name: Optional[str],
    ) -> ExportJob:
        account_dir = _resolve_account_dir(account)
        export_id = uuid.uuid4().hex[:12]

        job = ExportJob(
            export_id=export_id,
            account=account_dir.name,
            status="queued",
            options={
                "scope": scope,
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
                "privacyMode": bool(privacy_mode),
                "fileName": str(file_name or "").strip(),
            },
        )

        with self._lock:
            self._jobs[export_id] = job

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

        opts = dict(job.options or {})
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

        target_usernames = _resolve_export_targets(
            account_dir=account_dir,
            scope=scope,
            usernames=list(opts.get("usernames") or []),
            include_hidden=include_hidden,
            include_official=include_official,
        )
        if not target_usernames:
            raise ValueError("No target conversations to export.")

        exports_root = _resolve_export_output_dir(account_dir, opts.get("outputDir"))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

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

        contact_db_path = account_dir / "contact.db"
        message_resource_db_path = account_dir / "message_resource.db"
        media_db_path = account_dir / "media_0.db"
        head_image_db_path = account_dir / "head_image.db"

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

        contact_cache: dict[str, str] = {}
        contact_row_cache: dict[str, sqlite3.Row] = {}

        def resolve_display_name(u: str) -> str:
            if not u:
                return ""
            if u in contact_cache:
                return contact_cache[u]
            rows = _load_contact_rows(contact_db_path, [u])
            row = rows.get(u)
            if row is not None:
                contact_row_cache[u] = row
            name = _pick_display_name(row, u)
            contact_cache[u] = name
            return name

        conv_rows = _load_contact_rows(contact_db_path, target_usernames)
        for k, v in conv_rows.items():
            contact_row_cache[k] = v
            contact_cache[k] = _pick_display_name(v, k)

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

        try:
            if tmp_zip.exists():
                try:
                    tmp_zip.unlink()
                except Exception:
                    pass

            with zipfile.ZipFile(tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                html_index_items: list[dict[str, Any]] = []
                self_avatar_path = ""
                session_items: list[dict[str, Any]] = []
                remote_written: dict[str, str] = {}
                remote_download_enabled = bool(download_remote_media) and (export_format == "html") and include_media and (not privacy_mode)
                if export_format == "html":
                    ui_public_dir = _resolve_ui_public_dir()
                    css_payload = _load_ui_css_bundle(ui_public_dir=ui_public_dir, report=report)
                    zf.writestr("assets/wechat-chat-export.css", css_payload)
                    zf.writestr("assets/wechat-chat-export.js", _HTML_EXPORT_JS)

                    # Bundle UI static assets so the HTML works offline.
                    repo_root = Path(__file__).resolve().parents[2]
                    static_written: set[str] = {
                        "assets/wechat-chat-export.css",
                        "assets/wechat-chat-export.js",
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

                    preview_by_username: dict[str, str] = {}
                    last_ts_by_username: dict[str, int] = {}

                    if not privacy_mode:
                        self_avatar_path = _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=account_dir.name,
                            avatar_written=avatar_written,
                        )

                        try:
                            preview_by_username = _load_latest_message_previews(account_dir, target_usernames)
                        except Exception:
                            preview_by_username = {}

                        session_db_path = Path(account_dir) / "session.db"
                        if session_db_path.exists():
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

                    for idx, conv_username in enumerate(target_usernames, start=1):
                        conv_row = contact_row_cache.get(conv_username)
                        conv_name = _pick_display_name(conv_row, conv_username)
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

                for idx, conv_username in enumerate(target_usernames, start=1):
                    if self._should_cancel(job):
                        raise _JobCancelled()

                    conv_row = contact_row_cache.get(conv_username)
                    conv_name = _pick_display_name(conv_row, conv_username)
                    conv_is_group = bool(conv_username.endswith("@chatroom"))

                    conv_dir = f"conversations/{_conversation_dir_name(idx, conv_name, conv_username, conv_is_group, privacy_mode)}"

                    with self._lock:
                        job.progress.current_conversation_index = idx
                        job.progress.current_conversation_username = conv_username
                        job.progress.current_conversation_name = conv_name
                        job.progress.current_conversation_messages_exported = 0
                        job.progress.current_conversation_messages_total = 0

                    try:
                        estimated_total = _estimate_conversation_message_count(
                            account_dir=account_dir,
                            conv_username=conv_username,
                            start_time=st,
                            end_time=et,
                            local_types=estimate_local_types,
                        )
                    except Exception:
                        estimated_total = 0

                    with self._lock:
                        job.progress.current_conversation_messages_total = int(estimated_total)

                    chat_id = None
                    try:
                        if resource_conn is not None:
                            chat_id = _resource_lookup_chat_id(resource_conn, conv_username)
                    except Exception:
                        chat_id = None

                    conv_avatar_path = ""
                    if not privacy_mode:
                        conv_avatar_path = _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=conv_username,
                            avatar_written=avatar_written,
                        )

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
                            start_time=st,
                            end_time=et,
                            want_types=want_types,
                            local_types=local_types,
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
                            job=job,
                            lock=self._lock,
                        )

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

                if export_format == "html":
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
                    parts.append('  <link rel="stylesheet" href="assets/wechat-chat-export.css" />\n')
                    parts.append('  <script defer src="assets/wechat-chat-export.js"></script>\n')
                    parts.append("</head>\n")
                    parts.append("<body>\n")
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
                    parts.append("</body>\n")
                    parts.append("</html>\n")
                    zf.writestr("index.html", "".join(parts))

                manifest = {
                    "schemaVersion": 1,
                    "exportedAt": _now_iso(),
                    "exportId": job.export_id,
                    "account": "hidden" if privacy_mode else account_dir.name,
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
                        "privacyMode": privacy_mode,
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

            if final_zip.exists():
                final_zip = (exports_root / f"{final_zip.stem}_{job.export_id}{final_zip.suffix}").resolve()
            tmp_zip.replace(final_zip)

            with self._lock:
                job.status = "done"
                job.zip_path = final_zip
                job.finished_at = time.time()
        except _JobCancelled:
            try:
                if tmp_zip.exists():
                    tmp_zip.unlink()
            except Exception:
                pass
            with self._lock:
                job.status = "cancelled"
                job.finished_at = time.time()
        finally:
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
) -> list[str]:
    if scope == "selected":
        uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
        return uniq

    session_db_path = account_dir / "session.db"
    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT username, is_hidden
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            """,
        ).fetchall()
    finally:
        conn.close()

    out: list[str] = []
    for r in rows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(u, include_official=include_official):
            continue
        if scope == "groups" and (not u.endswith("@chatroom")):
            continue
        if scope == "singles" and u.endswith("@chatroom"):
            continue
        out.append(u)
    return out


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


def _estimate_conversation_message_count(
    *,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
    local_types: Optional[set[int]] = None,
) -> int:
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


def _iter_rows_for_conversation(
    *,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
    local_types: Optional[set[int]] = None,
) -> Iterable[_Row]:
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

            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"{where_sql} "
                "ORDER BY m.create_time ASC, m.sort_seq ASC, m.local_id ASC "
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
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
    amount = ""
    cover_url = ""
    file_size = ""
    pay_sub_type = ""
    transfer_status = ""
    file_md5 = ""
    transfer_id = ""
    voip_type = ""

    if local_type == 10000:
        render_type = "system"
        content_text = _parse_system_message_content(raw_text)
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
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.json"
    exported = 0

    contact_conn: Optional[sqlite3.Connection] = None
    alias_cache: dict[str, str] = {}
    if conv_is_group:
        try:
            contact_db_path = account_dir / "contact.db"
            if contact_db_path.exists():
                contact_conn = sqlite3.connect(str(contact_db_path))
        except Exception:
            contact_conn = None

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
            ):
                scanned += 1

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

                msg = _parse_message_for_export(
                    row=row,
                    conv_username=conv_username,
                    is_group=conv_is_group,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    sender_alias=sender_alias,
                )
                if not _is_render_type_selected(msg.get("renderType"), want_types):
                    continue

                su = str(msg.get("senderUsername") or "").strip()
                if privacy_mode:
                    _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
                else:
                    msg["senderDisplayName"] = resolve_display_name(su) if su else ""
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

                if include_media:
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
                        lock=lock,
                        job=job,
                    )

                if not first:
                    tw.write(",\n")
                tw.write("    " + json.dumps(msg, ensure_ascii=False))
                first = False

                exported += 1
                with lock:
                    job.progress.messages_exported += 1
                    job.progress.current_conversation_messages_exported = exported

                if scanned % 500 == 0 and job.cancel_requested:
                    raise _JobCancelled()

            tw.write("\n  ]\n")
            tw.write("}\n")
            tw.flush()

        zf.write(str(tmp_path), arcname)
    if contact_conn is not None:
        try:
            contact_conn.close()
        except Exception:
            pass

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
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.txt"
    exported = 0

    contact_conn: Optional[sqlite3.Connection] = None
    alias_cache: dict[str, str] = {}
    if conv_is_group:
        try:
            contact_db_path = account_dir / "contact.db"
            if contact_db_path.exists():
                contact_conn = sqlite3.connect(str(contact_db_path))
        except Exception:
            contact_conn = None

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
            ):
                scanned += 1
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

                msg = _parse_message_for_export(
                    row=row,
                    conv_username=conv_username,
                    is_group=conv_is_group,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    sender_alias=sender_alias,
                )
                if not _is_render_type_selected(msg.get("renderType"), want_types):
                    continue

                su = str(msg.get("senderUsername") or "").strip()
                if privacy_mode:
                    _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
                else:
                    msg["senderDisplayName"] = resolve_display_name(su) if su else ""
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

                if include_media:
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
                        lock=lock,
                        job=job,
                    )

                tw.write(_format_message_line_txt(msg=msg) + "\n")

                exported += 1
                with lock:
                    job.progress.messages_exported += 1
                    job.progress.current_conversation_messages_exported = exported

                if scanned % 500 == 0 and job.cancel_requested:
                    raise _JobCancelled()

            tw.flush()

        zf.write(str(tmp_path), arcname)
    if contact_conn is not None:
        try:
            contact_conn.close()
        except Exception:
            pass

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
    start_time: Optional[int],
    end_time: Optional[int],
    want_types: Optional[set[str]],
    local_types: Optional[set[int]],
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
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.html"
    exported = 0

    rel_root = "../../"
    css_href = rel_root + "assets/wechat-chat-export.css"
    js_src = rel_root + "assets/wechat-chat-export.js"

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
                u = re.sub(r"\\s+", "", u)
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
        ("chatHistory", "合并消息"),
        ("transfer", "转账"),
        ("redPacket", "红包"),
        ("file", "文件"),
        ("link", "链接"),
        ("quote", "引用"),
        ("system", "系统"),
        ("voip", "通话"),
    ]

    # NOTE: write to a temp file first to avoid zip interleaving writes.
    with tempfile.TemporaryDirectory(prefix="wechat_chat_export_") as tmp_dir:
        tmp_path = Path(tmp_dir) / "messages.html"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as tw:
            tw.write("<!doctype html>\n")
            tw.write('<html lang="zh-CN">\n')
            tw.write("<head>\n")
            tw.write('  <meta charset="utf-8" />\n')
            tw.write('  <meta name="viewport" content="width=device-width, initial-scale=1" />\n')
            tw.write(f"  <title>{esc_text(page_title)}</title>\n")
            tw.write(f'  <link rel="stylesheet" href="{esc_attr(css_href)}" />\n')
            tw.write(f'  <script defer src="{esc_attr(js_src)}"></script>\n')
            tw.write("</head>\n")
            tw.write("<body>\n")

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

            tw.write('        <div class="chat-header wce-chat-header">\n')
            tw.write('          <div class="flex items-center gap-3 min-w-0">\n')
            tw.write(f'            <h2 class="wce-chat-title text-base font-medium text-gray-900">{esc_text(chat_title)}</h2>\n')
            tw.write("          </div>\n")
            tw.write('          <div class="ml-auto flex items-center gap-2">\n')
            tw.write(f'            <select id="messageTypeFilter" class="message-filter-select wce-filter-select" title="筛选消息类型">\n')
            for value, label in options:
                tw.write(f'              <option value="{esc_attr(value)}">{esc_text(label)}</option>\n')
            tw.write("            </select>\n")
            tw.write("          </div>\n")
            tw.write("        </div>\n")

            tw.write('        <div id="messageContainer" class="wce-message-container flex-1 overflow-y-auto p-4 min-h-0">\n')

            sender_alias_map: dict[str, int] = {}
            prev_ts = 0
            scanned = 0
            for row in _iter_rows_for_conversation(
                account_dir=account_dir,
                conv_username=conv_username,
                start_time=start_time,
                end_time=end_time,
                local_types=local_types,
            ):
                scanned += 1

                msg = _parse_message_for_export(
                    row=row,
                    conv_username=conv_username,
                    is_group=conv_is_group,
                    resource_conn=resource_conn,
                    resource_chat_id=resource_chat_id,
                    sender_alias="",
                )
                if not _is_render_type_selected(msg.get("renderType"), want_types):
                    continue

                sender_username = str(msg.get("senderUsername") or "").strip()
                if privacy_mode:
                    _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
                else:
                    msg["senderDisplayName"] = resolve_display_name(sender_username) if sender_username else ""
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

                if include_media:
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
                        lock=lock,
                        job=job,
                    )
                    _remember_offline_media(msg)

                rt = str(msg.get("renderType") or "text").strip() or "text"
                create_time_text = str(msg.get("createTimeText") or "").strip()
                try:
                    ts = int(msg.get("createTime") or 0)
                except Exception:
                    ts = 0

                show_divider = False
                if ts and ((prev_ts == 0) or (abs(ts - prev_ts) >= 300)):
                    show_divider = True

                if show_divider:
                    divider_text = _format_session_time(ts)
                    if divider_text:
                        tw.write('          <div class="flex justify-center mb-4" data-wce-time-divider="1">\n')
                        tw.write(f'            <div class="px-3 py-1 text-xs text-[#9e9e9e]">{esc_text(divider_text)}</div>\n')
                        tw.write("          </div>\n")

                # Wrapper (for filter)
                tw.write(f'          <div class="mb-6" data-render-type="{esc_attr(rt)}" title="{esc_attr(create_time_text)}">\n')

                if rt == "system":
                    tw.write('            <div class="wce-system flex justify-center">\n')
                    tw.write(f'              <div class="px-3 py-1 text-xs text-[#9e9e9e]">{esc_text(msg.get("content") or "")}</div>\n')
                    tw.write("            </div>\n")
                    tw.write("          </div>\n")
                    exported += 1
                    with lock:
                        job.progress.messages_exported += 1
                        job.progress.current_conversation_messages_exported = exported
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
                    if voice:
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
                        tw.write(f'                    <audio src="{esc_attr(voice)}" preload="none" class="hidden"></audio>\n')
                        tw.write("                  </div>\n")
                    else:
                        tw.write(f'                  <div class="{esc_attr(bubble_base_cls + " " + bubble_dir_cls)}">{render_text_with_emojis(msg.get("content") or "")}</div>\n')
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
                    title = str(msg.get("title") or "").strip() or "合并消息"
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
                    tw.write('                    <div class="wechat-chat-history-bottom"><span>合并消息</span></div>\n')
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

                exported += 1
                with lock:
                    job.progress.messages_exported += 1
                    job.progress.current_conversation_messages_exported = exported
                if ts:
                    prev_ts = ts

                if scanned % 500 == 0 and job.cancel_requested:
                    raise _JobCancelled()

            tw.write("        </div>\n")
            tw.write("      </div>\n")
            tw.write("    </div>\n")
            tw.write("  </div>\n")
            tw.write("</div>\n")
            tw.write("</div>\n")

            try:
                media_index_payload = json.dumps(page_media_index, ensure_ascii=False)
            except Exception:
                media_index_payload = "{}"
            media_index_payload = media_index_payload.replace("</", "<\\/")
            tw.write(f'<script type="application/json" id="wceMediaIndex">{media_index_payload}</script>\n')

            tw.write(
                '<div id="chatHistoryModal" class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center hidden" style="display:none" aria-hidden="true">\n'
            )
            tw.write('  <div class="w-[92vw] max-w-[560px] max-h-[80vh] bg-white rounded-xl shadow-xl overflow-hidden flex flex-col" role="dialog" aria-modal="true">\n')
            tw.write('    <div class="px-4 py-3 bg-neutral-100 border-b border-gray-200 flex items-center justify-between">\n')
            tw.write('      <div id="chatHistoryModalTitle" class="text-sm text-[#161616] truncate">合并消息</div>\n')
            tw.write('      <button type="button" id="chatHistoryModalClose" class="p-2 rounded hover:bg-black/5" aria-label="关闭" title="关闭">\n')
            tw.write('        <svg class="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">\n')
            tw.write('          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>\n')
            tw.write("        </svg>\n")
            tw.write("      </button>\n")
            tw.write("    </div>\n")
            tw.write('    <div class="flex-1 overflow-auto bg-white">\n')
            tw.write('      <div id="chatHistoryModalEmpty" class="text-sm text-gray-500 text-center py-10">没有可显示的合并消息</div>\n')
            tw.write('      <div id="chatHistoryModalList"></div>\n')
            tw.write("    </div>\n")
            tw.write("  </div>\n")
            tw.write("</div>\n")

            tw.write("</body>\n")
            tw.write("</html>\n")
            tw.flush()

        zf.write(str(tmp_path), arcname)

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
    lock: threading.Lock,
    job: ExportJob,
) -> None:
    # allow_process_key_extract is reserved; this project does not extract keys from process (use wx_key instead).
    _ = allow_process_key_extract

    rt = str(msg.get("renderType") or "")

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
    return arc


def _materialize_voice(
    *,
    zf: zipfile.ZipFile,
    media_db_path: Path,
    server_id: int,
    media_written: dict[str, str],
) -> tuple[str, bool]:
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

    wav = _convert_silk_to_wav(data)
    if wav != data and wav[:4] == b"RIFF":
        ext = "wav"
        payload = wav
    else:
        ext = "silk"
        payload = data

    arc = f"media/voices/voice_{int(server_id)}.{ext}"
    zf.writestr(arc, payload)
    media_written[key] = arc
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
) -> tuple[str, bool]:
    ident = md5 or file_id
    if not ident:
        return "", False

    key = f"{kind}:{ident}"
    existing = media_written.get(key)
    if existing:
        return existing, False

    src: Optional[Path] = None
    if md5 and _is_md5(md5):
        try:
            src = _try_find_decrypted_resource(account_dir, md5)
        except Exception:
            src = None

        if src is None:
            try:
                src = _resolve_media_path_for_kind(account_dir, kind=kind, md5=md5, username=conv_username)
            except Exception:
                src = None

    if src is None and file_id:
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

    if not src:
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
    return arc, True


CHAT_EXPORT_MANAGER = ChatExportManager()
