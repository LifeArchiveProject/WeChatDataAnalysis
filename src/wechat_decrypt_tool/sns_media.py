from __future__ import annotations

"""SNS (Moments) remote media download + decryption helpers.

This module centralizes the "remote URL -> download -> decrypt -> validate -> cache" pipeline
so it can be reused by:
- FastAPI endpoints (`routers/sns.py`)
- Offline export (`sns_export_service.py`)

Important notes (empirical, matches current repo behavior):
- SNS images: prefer `wcdb_api.dll` export `wcdb_decrypt_sns_image` (black-box). Pure ISAAC64
  keystream XOR is NOT reliable for images across versions.
- SNS videos: encrypted only for the first 128KB; decrypt via WeFlow's WxIsaac64 (WASM keystream)
  and XOR in-place.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import base64
import hashlib
import html
import os
import re
import subprocess
import time

import httpx
from fastapi import HTTPException

from .logging_config import get_logger
from .wcdb_realtime import decrypt_sns_image as _wcdb_decrypt_sns_image

logger = get_logger(__name__)


def is_allowed_sns_media_host(host: str) -> bool:
    h = str(host or "").strip().lower()
    if not h:
        return False
    # Images: qpic/qlogo. Thumbs: *.tc.qq.com. Videos/live photos: *.video.qq.com.
    return h.endswith(".qpic.cn") or h.endswith(".qlogo.cn") or h.endswith(".tc.qq.com") or h.endswith(".video.qq.com")


def fix_sns_cdn_url(url: str, *, token: str = "", is_video: bool = False) -> str:
    """WeFlow-compatible SNS CDN URL normalization.

    - Force https for Tencent CDNs.
    - For images, replace `/150` with `/0` to request the original.
    - If token is provided and url doesn't contain it, append `token=<token>&idx=1`.
    """
    u = html.unescape(str(url or "")).strip()
    if not u:
        return ""

    # Only touch Tencent CDNs; keep other URLs intact.
    try:
        p = urlparse(u)
        host = str(p.hostname or "").lower()
        if not is_allowed_sns_media_host(host):
            return u
    except Exception:
        return u

    # http -> https
    u = re.sub(r"^http://", "https://", u, flags=re.I)

    # /150 -> /0 (image only)
    if not is_video:
        u = re.sub(r"/150(?=($|\\?))", "/0", u)

    tok = str(token or "").strip()
    if tok and ("token=" not in u):
        if is_video:
            # Match WeFlow: place `token&idx=1` in front of existing query params.
            base, sep, qs = u.partition("?")
            if sep:
                qs = qs.lstrip("&")
                u = f"{base}?token={tok}&idx=1"
                if qs:
                    u = f"{u}&{qs}"
            else:
                u = f"{u}?token={tok}&idx=1"
        else:
            connector = "&" if "?" in u else "?"
            u = f"{u}{connector}token={tok}&idx=1"

    return u


def _detect_mp4_ftyp(head: bytes) -> bool:
    return bool(head) and len(head) >= 8 and head[4:8] == b"ftyp"


@lru_cache(maxsize=1)
def _weflow_wxisaac64_script_path() -> str:
    """Locate the Node helper that wraps WeFlow's wasm_video_decode.* assets."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "tools" / "weflow_wasm_keystream.js"
    if script.exists() and script.is_file():
        return str(script)
    return ""


@lru_cache(maxsize=64)
def weflow_wxisaac64_keystream(key: str, size: int) -> bytes:
    """Generate keystream via WeFlow's WASM (preferred; matches real video decryption)."""
    key_text = str(key or "").strip()
    if not key_text or size <= 0:
        return b""

    # WeFlow is the source-of-truth; use its WASM first, then fall back to our pure-python ISAAC64.
    script = _weflow_wxisaac64_script_path()
    if script:
        try:
            # The JS helper prints ONLY base64 bytes to stdout; keep stderr for debugging.
            proc = subprocess.run(
                ["node", script, key_text, str(int(size))],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            if proc.returncode == 0:
                out_b64 = (proc.stdout or b"").strip()
                if out_b64:
                    return base64.b64decode(out_b64, validate=False)
        except Exception:
            pass

    # Fallback: pure python ISAAC64 (best-effort; may not match WxIsaac64 for all versions).
    from .isaac64 import Isaac64  # pylint: disable=import-outside-toplevel

    want = int(size)
    # ISAAC64 generates 8-byte words; generate enough and slice.
    size8 = ((want + 7) // 8) * 8
    return Isaac64(key_text).generate_keystream(size8)[:want]


_SNS_REMOTE_VIDEO_CACHE_EXTS = [
    ".mp4",
    ".bin",  # legacy/unknown
]


def _sns_remote_video_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    digest = hashlib.md5(f"video|{url}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    cache_dir = account_dir / "sns_remote_video_cache" / digest[:2]
    return cache_dir, digest


def _sns_remote_video_cache_existing_path(cache_dir: Path, stem: str) -> Optional[Path]:
    for ext in _SNS_REMOTE_VIDEO_CACHE_EXTS:
        p = cache_dir / f"{stem}{ext}"
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return None


async def _download_sns_remote_to_file(url: str, dest_path: Path, *, max_bytes: int) -> tuple[str, str]:
    """Download SNS media to file (streaming) from Tencent CDN.

    Returns: (content_type, x_enc)
    """
    u = str(url or "").strip()
    if not u:
        return "", ""

    # Safety: only allow Tencent CDN hosts.
    try:
        p = urlparse(u)
        host = str(p.hostname or "").lower()
        if not is_allowed_sns_media_host(host):
            raise HTTPException(status_code=400, detail="SNS media host not allowed.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid SNS media URL.")

    base_headers = {
        "User-Agent": "MicroMessenger Client",
        "Accept": "*/*",
        # Do not request compression for video streams.
        "Connection": "keep-alive",
    }

    header_variants = [
        {},
        # WeFlow/Electron: MicroMessenger UA + servicewechat.com referer passes some CDN anti-hotlink checks.
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090719) XWEB/8351",
            "Referer": "https://servicewechat.com/",
            "Origin": "https://servicewechat.com",
        },
        {"Referer": "https://wx.qq.com/", "Origin": "https://wx.qq.com"},
        {"Referer": "https://mp.weixin.qq.com/", "Origin": "https://mp.weixin.qq.com"},
    ]

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for extra in header_variants:
            headers = dict(base_headers)
            headers.update(extra)
            try:
                if dest_path.exists():
                    try:
                        dest_path.unlink(missing_ok=True)
                    except Exception:
                        pass

                total = 0
                async with client.stream("GET", u, headers=headers) as resp:
                    resp.raise_for_status()
                    content_type = str(resp.headers.get("Content-Type") or "").strip()
                    x_enc = str(resp.headers.get("x-enc") or "").strip()
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with dest_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > max_bytes:
                                raise HTTPException(status_code=400, detail="SNS video too large.")
                            f.write(chunk)
                return content_type, x_enc
            except HTTPException:
                raise
            except Exception as e:
                last_err = e
                continue

    raise last_err or RuntimeError("sns remote download failed")


def maybe_decrypt_sns_video_file(path: Path, key: str) -> bool:
    """Decrypt the first 128KB of an encrypted mp4 file in-place (WeFlow/Isaac64).

    Returns True if decryption was performed, False otherwise.
    """
    key_text = str(key or "").strip()
    if not key_text:
        return False

    try:
        size = int(path.stat().st_size)
    except Exception:
        return False

    if size <= 8:
        return False

    decrypt_size = min(131072, size)
    if decrypt_size <= 0:
        return False

    try:
        with path.open("r+b") as f:
            head = f.read(8)
            if _detect_mp4_ftyp(head):
                return False

            f.seek(0)
            buf = bytearray(f.read(decrypt_size))
            if not buf:
                return False

            ks = weflow_wxisaac64_keystream(key_text, decrypt_size)
            n = min(len(buf), len(ks))
            for i in range(n):
                buf[i] ^= ks[i]

            f.seek(0)
            f.write(buf)
            f.flush()

            f.seek(0)
            head2 = f.read(8)
            if _detect_mp4_ftyp(head2):
                return True
            # Still return True to indicate we mutated bytes; caller may treat as failure if desired.
            return True
    except Exception:
        return False


async def materialize_sns_remote_video(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    use_cache: bool,
) -> Optional[Path]:
    """Download SNS video from CDN, decrypt (if needed), and return a local mp4 path."""
    fixed_url = fix_sns_cdn_url(str(url or ""), token=str(token or ""), is_video=True)
    if not fixed_url:
        return None

    cache_dir, cache_stem = _sns_remote_video_cache_dir_and_stem(account_dir, url=fixed_url, key=str(key or ""))

    if use_cache:
        existing = _sns_remote_video_cache_existing_path(cache_dir, cache_stem)
        if existing is not None:
            # Best-effort migrate legacy `.bin` -> `.mp4` when it's already decrypted.
            try:
                if existing.suffix.lower() == ".bin":
                    with existing.open("rb") as f:
                        head = f.read(8)
                    if _detect_mp4_ftyp(head):
                        target = cache_dir / f"{cache_stem}.mp4"
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        os.replace(str(existing), str(target))
                        existing = target
            except Exception:
                pass
            return existing

    # Download to a temp file first.
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_dir / f"{cache_stem}.mp4.{time.time_ns()}.tmp"
    try:
        await _download_sns_remote_to_file(fixed_url, tmp_path, max_bytes=200 * 1024 * 1024)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None

    # Decrypt in-place if the file isn't already a mp4.
    maybe_decrypt_sns_video_file(tmp_path, str(key or ""))

    # Validate: mp4 must have `ftyp` at offset 4.
    ok_mp4 = False
    try:
        with tmp_path.open("rb") as f:
            head = f.read(8)
        ok_mp4 = _detect_mp4_ftyp(head)
    except Exception:
        ok_mp4 = False

    if not ok_mp4:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None

    if use_cache:
        final_path = cache_dir / f"{cache_stem}.mp4"
        try:
            os.replace(str(tmp_path), str(final_path))
        except Exception:
            # If rename fails, keep tmp_path as fallback.
            final_path = tmp_path

        # Remove other extensions for the same cache key.
        for other_ext in _SNS_REMOTE_VIDEO_CACHE_EXTS:
            if other_ext.lower() == ".mp4":
                continue
            other = cache_dir / f"{cache_stem}{other_ext}"
            try:
                if other.exists() and other.is_file():
                    other.unlink(missing_ok=True)
            except Exception:
                continue

        return final_path

    # Cache disabled: keep the decrypted tmp_path (caller should delete it).
    return tmp_path


def best_effort_unlink(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


def detect_image_mime(data: bytes) -> str:
    """Sniff image mime type by magic bytes.

    IMPORTANT: Do NOT trust HTTP Content-Type as a fallback here. We use this for
    validating decrypted bytes. If we blindly trust `image/*`, a failed decrypt
    would poison the disk cache and the frontend would keep showing broken images.
    """
    if not data:
        return ""

    if data.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        # ISO BMFF based image formats (HEIF/HEIC/AVIF).
        brand = data[8:12]
        if brand == b"avif":
            return "image/avif"
        if brand in (b"heic", b"heix", b"hevc", b"hevx"):
            return "image/heic"
        if brand in (b"heif", b"mif1", b"msf1"):
            return "image/heif"
    if data.startswith(b"BM"):
        return "image/bmp"

    return ""


_SNS_REMOTE_CACHE_EXTS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".avif",
    ".heic",
    ".heif",
    ".bin",  # legacy/unknown
]


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


def _ext_to_mime(ext: str) -> str:
    e = str(ext or "").strip().lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "avif": "image/avif",
        "heic": "image/heic",
        "heif": "image/heif",
    }.get(e, "")


def _sns_remote_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    digest = hashlib.md5(f"{url}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    cache_dir = account_dir / "sns_remote_cache" / digest[:2]
    return cache_dir, digest


def _sns_remote_cache_existing_path(cache_dir: Path, stem: str) -> Optional[Path]:
    for ext in _SNS_REMOTE_CACHE_EXTS:
        p = cache_dir / f"{stem}{ext}"
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return None


def _sniff_image_mime_from_file(path: Path) -> str:
    try:
        with path.open("rb") as f:
            head = f.read(64)
        return detect_image_mime(head)
    except Exception:
        return ""


async def _download_sns_remote_bytes(url: str) -> tuple[bytes, str, str]:
    """Download SNS media bytes from Tencent CDN with a few safe header variants."""
    u = str(url or "").strip()
    if not u:
        return b"", "", ""

    max_bytes = 25 * 1024 * 1024

    base_headers = {
        "User-Agent": "MicroMessenger Client",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        # Avoid brotli dependency issues; images are already compressed anyway.
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    # Some CDN endpoints return a small placeholder image for certain UA/Referer
    # combinations but still respond 200. Try the simplest (base headers only)
    # first to maximize the chance of getting the real media in one request.
    header_variants = [
        {},
        # WeFlow/Electron: MicroMessenger UA + servicewechat.com referer passes some CDN anti-hotlink checks.
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090719) XWEB/8351",
            "Referer": "https://servicewechat.com/",
            "Origin": "https://servicewechat.com",
        },
        {"Referer": "https://wx.qq.com/", "Origin": "https://wx.qq.com"},
        {"Referer": "https://mp.weixin.qq.com/", "Origin": "https://mp.weixin.qq.com"},
    ]

    last_err: Exception | None = None
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for extra in header_variants:
            headers = dict(base_headers)
            headers.update(extra)
            try:
                resp = await client.get(u, headers=headers)
                resp.raise_for_status()
                payload = bytes(resp.content or b"")
                if len(payload) > max_bytes:
                    raise HTTPException(status_code=400, detail="SNS media too large (>25MB).")
                content_type = str(resp.headers.get("Content-Type") or "").strip()
                x_enc = str(resp.headers.get("x-enc") or "").strip()
                return payload, content_type, x_enc
            except HTTPException:
                raise
            except Exception as e:
                last_err = e
                continue

    raise last_err or RuntimeError("sns remote download failed")


@dataclass(frozen=True)
class SnsRemoteImageResult:
    payload: bytes
    media_type: str
    source: str
    x_enc: str = ""
    cache_path: Optional[Path] = None


async def try_fetch_and_decrypt_sns_image_remote(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    use_cache: bool,
) -> Optional[SnsRemoteImageResult]:
    """Try WeFlow-style: download from CDN -> decrypt via wcdb_decrypt_sns_image -> return bytes.

    Returns a SnsRemoteImageResult on success, or None on failure so caller can fall back to
    local cache matching logic.
    """
    u_fixed = fix_sns_cdn_url(url, token=token, is_video=False)
    if not u_fixed:
        return None

    try:
        p = urlparse(u_fixed)
        host = str(p.hostname or "").strip().lower()
    except Exception:
        return None
    if not is_allowed_sns_media_host(host):
        return None

    cache_dir, cache_stem = _sns_remote_cache_dir_and_stem(account_dir, url=u_fixed, key=str(key or ""))

    cache_path: Optional[Path] = None
    if use_cache:
        try:
            existing = _sns_remote_cache_existing_path(cache_dir, cache_stem)
            if existing is not None:
                mt = _ext_to_mime(existing.suffix)

                # Upgrade legacy `.bin` cache to a proper image extension once.
                if (existing.suffix or "").lower() == ".bin" or (not mt):
                    mt2 = _sniff_image_mime_from_file(existing)
                    if not mt2:
                        try:
                            existing.unlink(missing_ok=True)
                        except Exception:
                            pass
                        existing = None
                    else:
                        ext2 = _mime_to_ext(mt2)
                        if ext2 != ".bin":
                            try:
                                cache_dir.mkdir(parents=True, exist_ok=True)
                                desired = cache_dir / f"{cache_stem}{ext2}"
                                if desired.exists():
                                    # Another process/version already wrote the real file; drop legacy bin.
                                    existing.unlink(missing_ok=True)
                                    existing = desired
                                else:
                                    os.replace(str(existing), str(desired))
                                    existing = desired
                            except Exception:
                                pass
                        mt = mt2

                if existing is not None and mt:
                    try:
                        payload = existing.read_bytes()
                    except Exception:
                        payload = b""
                    if payload:
                        return SnsRemoteImageResult(
                            payload=payload,
                            media_type=mt,
                            source="remote-cache",
                            x_enc="",
                            cache_path=existing,
                        )
        except Exception:
            pass

    try:
        raw, _content_type, x_enc = await _download_sns_remote_bytes(u_fixed)
    except Exception as e:
        logger.info("[sns_media] remote download failed: %s", e)
        return None

    if not raw:
        return None

    # First, validate whether the CDN already returned a real image.
    mt_raw = detect_image_mime(raw)

    decoded = raw
    mt = mt_raw
    decrypted = False
    k = str(key or "").strip()

    # Only attempt decryption when bytes do NOT look like an image, or when CDN explicitly
    # signals encryption (x-enc). Some endpoints return already-decoded PNG/JPEG even when
    # urlAttrs.enc_idx == 1, and decrypting those would corrupt the bytes.
    need_decrypt = bool(k) and (not mt_raw) and bool(raw)
    if k and x_enc and str(x_enc).strip() not in ("0", "false", "False"):
        need_decrypt = True

    if need_decrypt:
        try:
            decoded2 = _wcdb_decrypt_sns_image(raw, k)
            mt2 = detect_image_mime(decoded2)
            if mt2:
                decoded = decoded2
                mt = mt2
                decrypted = decoded2 != raw
            else:
                # Decrypt failed; if raw is a real image, keep it. Otherwise treat as failure.
                if mt_raw:
                    decoded = raw
                    mt = mt_raw
                    decrypted = False
                else:
                    return None
        except Exception as e:
            logger.info("[sns_media] remote decrypt failed: %s", e)
            if not mt_raw:
                return None
            decoded = raw
            mt = mt_raw
            decrypted = False

    if not mt:
        return None

    if use_cache:
        try:
            ext = _mime_to_ext(mt)
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / f"{cache_stem}{ext}"

            tmp = cache_path.with_suffix(cache_path.suffix + f".{time.time_ns()}.tmp")
            tmp.write_bytes(decoded)
            os.replace(str(tmp), str(cache_path))

            # Remove other extensions for the same cache key to avoid stale duplicates.
            for other_ext in _SNS_REMOTE_CACHE_EXTS:
                if other_ext.lower() == ext.lower():
                    continue
                other = cache_dir / f"{cache_stem}{other_ext}"
                try:
                    if other.exists() and other.is_file():
                        other.unlink(missing_ok=True)
                except Exception:
                    continue
        except Exception:
            cache_path = None

    return SnsRemoteImageResult(
        payload=decoded,
        media_type=mt,
        source="remote-decrypt" if decrypted else "remote",
        x_enc=str(x_enc or "").strip(),
        cache_path=cache_path,
    )

