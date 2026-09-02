from __future__ import annotations

"""SNS (Moments) remote media download + decryption helpers.

This module centralizes the "remote URL -> download -> decrypt -> validate -> cache" pipeline
so it can be reused by:
- FastAPI endpoints (`routers/sns.py`)
- Offline export (`sns_export_service.py`)

Important notes (empirical, matches current repo behavior):
- SNS images: match WeFlow's Electron implementation by generating the WxIsaac64
  keystream from WASM and XORing the full payload in-memory.
- SNS videos: encrypted only for the first 128KB; decrypt via WeFlow's WxIsaac64 (WASM keystream)
  and XOR in-place.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit
import asyncio
import atexit
import base64
import hashlib
import html
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time

import httpx
from fastapi import HTTPException

from .logging_config import get_logger

logger = get_logger(__name__)
_PACKAGE_DIR = Path(__file__).resolve().parent
_NATIVE_DIR = _PACKAGE_DIR / "native"
_WEFLOW_WASM_DIR = _NATIVE_DIR / "weflow_wasm"


class SnsWasmRuntimeUnavailable(RuntimeError):
    """Raised when the authoritative WxIsaac64 WASM runtime cannot be started."""


class SnsRemoteMediaUpstreamError(RuntimeError):
    """Raised when Tencent CDN fails for a request that is not a real 404."""

    def __init__(self, message: str, *, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = int(status_code or 0)


class SnsRemoteMediaDecodeError(RuntimeError):
    """Raised when the CDN returned bytes but they cannot be decoded as requested media."""


def is_allowed_sns_media_host(host: str) -> bool:
    h = str(host or "").strip().lower()
    if not h:
        return False
    # Images: qpic/qlogo. Thumbs: *.tc.qq.com. Videos/live photos: *.video.qq.com.
    return h.endswith(".qpic.cn") or h.endswith(".qlogo.cn") or h.endswith(".tc.qq.com") or h.endswith(".video.qq.com")


def normalize_sns_cache_url(url: str) -> str:
    """Build WeFlow's stable cache identity without volatile token/idx parameters."""
    raw = html.unescape(str(url or "")).strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        query = urlencode(
            [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key.lower() not in {"token", "idx"}
            ],
            doseq=True,
        )
        base = f"{parsed.netloc}{parsed.path}"
        return f"{base}?{query}" if query else base
    except Exception:
        base, separator, query = raw.partition("?")
        stable_base = re.sub(r"^https?://", "", base, flags=re.I)
        if not separator:
            return stable_base
        params = [
            item
            for item in query.split("&")
            if item.partition("=")[0].strip().lower() not in {"token", "idx"}
        ]
        return f"{stable_base}?{'&'.join(params)}" if params else stable_base


def _sns_remote_diagnostic_log(
    event: str,
    *,
    url: str,
    diagnostic_id: str = "",
    key: str = "",
    token: str = "",
    error: Optional[BaseException] = None,
    **fields: object,
) -> None:
    raw_url = str(url or "").strip()
    try:
        host = str(urlparse(raw_url).hostname or "").strip().lower()
    except Exception:
        host = ""

    stable_url = normalize_sns_cache_url(raw_url)
    payload: dict[str, object] = {
        "diagnosticId": str(diagnostic_id or ""),
        "event": str(event or ""),
        "urlHost": host,
        "urlIdentity": (
            hashlib.sha256(stable_url.encode("utf-8", errors="ignore")).hexdigest()[:16]
            if stable_url
            else ""
        ),
        "sizeSuffix": _sns_cdn_size_suffix(raw_url),
        "mediaSource": _sns_cdn_media_source(raw_url),
        "tokenHash": (
            hashlib.sha256(str(token).encode("utf-8", errors="ignore")).hexdigest()[:16]
            if str(token or "")
            else ""
        ),
        "keyHash": (
            hashlib.sha256(str(key).encode("utf-8", errors="ignore")).hexdigest()[:16]
            if str(key or "")
            else ""
        ),
        **fields,
    }

    if error is not None:
        error_text = str(error).strip() or repr(error)
        for sensitive in (raw_url, str(key or ""), str(token or "")):
            if sensitive:
                error_text = error_text.replace(sensitive, "<redacted>")
        error_text = re.sub(r"https?://[^\s\"']+", "<url-redacted>", error_text, flags=re.I)
        payload["errorType"] = type(error).__name__
        payload["errorText"] = error_text[:500]

        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            try:
                payload["statusCode"] = int(status_code)
            except Exception:
                payload["statusCode"] = str(status_code)

    logger.info(
        "[sns_media] %s",
        json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True),
    )


def _sns_cdn_size_suffix(url: str) -> str:
    try:
        match = re.search(r"/(0|60|150|200|480)$", str(urlparse(str(url or "")).path or ""))
        return str(match.group(1) or "") if match else ""
    except Exception:
        return ""


def _sns_cdn_media_source(url: str) -> str:
    suffix = _sns_cdn_size_suffix(url)
    if suffix == "0":
        return "origin"
    if suffix in {"60", "150", "200", "480"}:
        return "thumbnail"
    return "video-or-unknown"


def fix_sns_cdn_url(
    url: str,
    *,
    token: str = "",
    is_video: bool = False,
    force_original: bool = False,
) -> str:
    """WeFlow-compatible SNS CDN URL normalization.

    - Force https for Tencent CDNs.
    - Preserve image size variants by default because Tencent binds `/60`, `/150`,
      `/200`, `/480`, and `/0` to their matching credentials.
    - Only an explicit original-image request may replace a size suffix with `/0`.
    - If token is provided, replace stale token/idx parameters with the current values.
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

    if force_original and not is_video:
        u = re.sub(r"/(?:60|150|200|480)(?=($|\?))", "/0", u)

    tok = str(token or "").strip()
    if tok:
        base, separator, query = u.partition("?")
        params = []
        if separator:
            params = [
                item
                for item in query.split("&")
                if item.partition("=")[0].strip().lower() not in {"token", "idx"}
            ]
        u = f"{base}?{'&'.join(params)}" if params else base
        if is_video:
            # Match WeFlow: place `token&idx=1` in front of existing query params.
            base, separator, query = u.partition("?")
            u = f"{base}?token={tok}&idx=1"
            if separator and query:
                u = f"{u}&{query}"
        else:
            connector = "&" if "?" in u else "?"
            u = f"{u}{connector}token={tok}&idx=1"

    return u


def _detect_mp4_ftyp(head: bytes) -> bool:
    return bool(head) and len(head) >= 8 and head[4:8] == b"ftyp"


@lru_cache(maxsize=1)
def _weflow_wxisaac64_script_path() -> str:
    """Locate the bundled Node helper that wraps the vendored wasm_video_decode.* assets."""
    bundled = _WEFLOW_WASM_DIR / "weflow_wasm_keystream.js"
    if bundled.exists() and bundled.is_file():
        return str(bundled)

    # Development fallback: allow the repo-level helper to proxy into the vendored assets.
    repo_root = _PACKAGE_DIR.parents[1]
    legacy = repo_root / "tools" / "weflow_wasm_keystream.js"
    if legacy.exists() and legacy.is_file():
        return str(legacy)
    return ""


class _WeflowWasmProcess:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._responses: queue.Queue[Optional[dict[str, object]]] = queue.Queue()
        self._request_id = 0
        self._runtime_signature: tuple[str, str, str] | None = None

    def _start_locked(
        self,
        script: str,
        executable: str,
        mode: str,
        provider: str,
    ) -> subprocess.Popen[str]:
        process = self._process
        signature = (executable, mode, script)
        if process is not None and process.poll() is None and self._runtime_signature == signature:
            return process
        if process is not None:
            self._stop_locked()

        responses: queue.Queue[Optional[dict[str, object]]] = queue.Queue()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        helper_env = os.environ.copy()
        if mode == "electron-run-as-node":
            helper_env["ELECTRON_RUN_AS_NODE"] = "1"
        else:
            # This variable is scoped to the Electron helper only. A global value
            # would turn the desktop main process itself into a Node process.
            helper_env.pop("ELECTRON_RUN_AS_NODE", None)
        process = subprocess.Popen(
            [executable, script, "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=helper_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        if process.stdin is None or process.stdout is None:
            process.kill()
            raise RuntimeError("Failed to open WeFlow WASM stdio pipes")

        def read_responses() -> None:
            try:
                for line in process.stdout:
                    try:
                        value = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(value, dict):
                        responses.put(value)
            finally:
                responses.put(None)

        threading.Thread(
            target=read_responses,
            name="sns-wasm-response-reader",
            daemon=True,
        ).start()
        self._responses = responses
        self._process = process
        self._runtime_signature = signature
        logger.info(
            "[sns_media] %s",
            json.dumps(
                {
                    "event": "keystream:helper-started",
                    "keystreamProvider": provider,
                    "runtimeMode": mode,
                    "runtimeIdentity": hashlib.sha256(
                        executable.encode("utf-8", errors="ignore")
                    ).hexdigest()[:16],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        return process

    def generate(
        self,
        script: str,
        key: str,
        size: int,
        *,
        executable: str,
        mode: str,
        provider: str,
    ) -> bytes:
        with self._lock:
            process = self._start_locked(script, executable, mode, provider)
            assert process.stdin is not None
            self._request_id += 1
            request_id = self._request_id
            request = json.dumps(
                {"id": request_id, "key": str(key), "size": int(size)},
                ensure_ascii=True,
                separators=(",", ":"),
            )
            try:
                process.stdin.write(request + "\n")
                process.stdin.flush()
                response = self._responses.get(timeout=30.0)
            except Exception:
                self._stop_locked()
                raise

            if response is None or int(response.get("id") or 0) != request_id:
                self._stop_locked()
                raise RuntimeError("WeFlow WASM process returned an invalid response")
            error = str(response.get("error") or "").strip()
            if error:
                raise RuntimeError(error)
            payload = str(response.get("data") or "").strip()
            if not payload:
                raise RuntimeError("WeFlow WASM process returned an empty keystream")
            return base64.b64decode(payload, validate=False)

    def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        self._runtime_signature = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=2.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        try:
            if process.stdout is not None:
                process.stdout.close()
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            self._stop_locked()


_WEFLOW_WASM_PROCESS = _WeflowWasmProcess()
atexit.register(_WEFLOW_WASM_PROCESS.close)


@lru_cache(maxsize=1)
def _resolve_weflow_node_runtime() -> tuple[str, str, str]:
    """Resolve the helper runtime without depending on a desktop user's shell PATH."""
    configured = str(os.environ.get("WECHAT_TOOL_NODE_EXECUTABLE") or "").strip()
    configured_mode = str(os.environ.get("WECHAT_TOOL_NODE_MODE") or "").strip().lower()
    if configured:
        executable = Path(configured)
        if not executable.is_absolute() or not executable.exists() or not executable.is_file():
            raise SnsWasmRuntimeUnavailable(
                "Configured Electron/Node runtime is unavailable."
            )
        mode = configured_mode or "node"
        if mode not in {"node", "electron-run-as-node"}:
            raise SnsWasmRuntimeUnavailable("Configured Electron/Node runtime mode is invalid.")
        provider = "electron-node-wasm" if mode == "electron-run-as-node" else "node-wasm"
        return str(executable), mode, provider

    # Source/dev mode is the only path allowed to consult PATH. Packaged desktop
    # launches always provide the absolute Electron executable above.
    executable = str(shutil.which("node") or "").strip()
    if not executable:
        raise SnsWasmRuntimeUnavailable(
            "WxIsaac64 requires the bundled Electron runtime or a source-mode Node executable."
        )
    return executable, "node", "node-wasm"


@lru_cache(maxsize=64)
def weflow_wxisaac64_keystream(key: str, size: int) -> bytes:
    """Generate the authoritative WxIsaac64 keystream through the vendored WASM."""
    key_text = str(key or "").strip()
    if not key_text or size <= 0:
        return b""

    script = _weflow_wxisaac64_script_path()
    if not script:
        raise SnsWasmRuntimeUnavailable("Vendored WxIsaac64 WASM helper is unavailable.")
    executable, mode, provider = _resolve_weflow_node_runtime()
    try:
        return _WEFLOW_WASM_PROCESS.generate(
            script,
            key_text,
            int(size),
            executable=executable,
            mode=mode,
            provider=provider,
        )
    except SnsWasmRuntimeUnavailable:
        raise
    except Exception as exc:
        raise SnsWasmRuntimeUnavailable("WxIsaac64 WASM helper failed.") from exc


_SNS_REMOTE_VIDEO_CACHE_EXTS = [
    ".mp4",
    ".bin",  # legacy/unknown
]


def _sns_remote_video_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    del key
    digest = hashlib.md5(normalize_sns_cache_url(url).encode("utf-8", errors="ignore")).hexdigest()
    cache_dir = account_dir / "sns_remote_video_cache" / digest[:2]
    return cache_dir, digest


def _legacy_sns_remote_video_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    digest = hashlib.md5(f"video|{url}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    return account_dir / "sns_remote_video_cache" / digest[:2], digest


def _sns_remote_video_cache_existing_path(cache_dir: Path, stem: str) -> Optional[Path]:
    for ext in _SNS_REMOTE_VIDEO_CACHE_EXTS:
        p = cache_dir / f"{stem}{ext}"
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return None


def get_cached_sns_remote_video(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
) -> Optional[Path]:
    """Return a stable remote-video cache entry without doing network I/O."""
    fixed_url = fix_sns_cdn_url(str(url or ""), token=str(token or ""), is_video=True)
    if not fixed_url:
        return None

    try:
        host = str(urlparse(fixed_url).hostname or "").strip().lower()
    except Exception:
        return None
    if not is_allowed_sns_media_host(host):
        return None

    cache_dir, cache_stem = _sns_remote_video_cache_dir_and_stem(
        account_dir,
        url=fixed_url,
        key=str(key or ""),
    )
    existing = _sns_remote_video_cache_existing_path(cache_dir, cache_stem)
    if existing is None:
        legacy_dir, legacy_stem = _legacy_sns_remote_video_cache_dir_and_stem(
            account_dir,
            url=fixed_url,
            key=str(key or ""),
        )
        legacy = _sns_remote_video_cache_existing_path(legacy_dir, legacy_stem)
        if legacy is not None:
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                migrated = cache_dir / f"{cache_stem}{legacy.suffix.lower()}"
                os.replace(str(legacy), str(migrated))
                existing = migrated
            except Exception:
                existing = legacy
    if existing is None:
        return None

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


async def _download_sns_remote_to_file(
    url: str,
    dest_path: Path,
    *,
    max_bytes: int,
    client: Optional[httpx.AsyncClient] = None,
    response_meta: Optional[dict[str, object]] = None,
) -> tuple[str, str]:
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

    async def download(http_client: httpx.AsyncClient) -> tuple[str, str]:
        dest_path.unlink(missing_ok=True)
        total = 0
        async with http_client.stream("GET", u, headers=base_headers, timeout=15.0) as resp:
            if resp.status_code not in {200, 206}:
                raise httpx.HTTPStatusError(
                    f"Unexpected SNS status {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
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
            if response_meta is not None:
                response_meta.update(
                    {
                        "upstreamStatus": int(resp.status_code),
                        "responseBytes": int(total),
                        "contentType": content_type,
                        "xEnc": x_enc,
                    }
                )
        return content_type, x_enc

    if client is not None:
        return await download(client)
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as owned_client:
        return await download(owned_client)


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
        raise SnsRemoteMediaDecodeError(
            "SNS video bytes are invalid after WASM decryption."
        )


async def materialize_sns_remote_video(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    use_cache: bool,
    client: Optional[httpx.AsyncClient] = None,
    diagnostic_id: str = "",
) -> Optional[Path]:
    """Download SNS video from CDN, decrypt (if needed), and return a local mp4 path."""
    fixed_url = fix_sns_cdn_url(str(url or ""), token=str(token or ""), is_video=True)
    if not fixed_url:
        return None

    cache_dir, cache_stem = _sns_remote_video_cache_dir_and_stem(account_dir, url=fixed_url, key=str(key or ""))

    if use_cache:
        existing = get_cached_sns_remote_video(
            account_dir=account_dir,
            url=fixed_url,
            key=key,
            token=token,
        )
        if existing is not None:
            return existing

    # Download to a temp file first.
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_dir / f"{cache_stem}.mp4.{time.time_ns()}.tmp"
    response_meta: dict[str, object] = {}
    try:
        await _download_sns_remote_to_file(
            fixed_url,
            tmp_path,
            max_bytes=200 * 1024 * 1024,
            client=client,
            response_meta=response_meta,
        )
    except Exception as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        response = getattr(exc, "response", None)
        upstream_status = int(getattr(response, "status_code", 0) or 0)
        _sns_remote_diagnostic_log(
            "video:download-error",
            url=fixed_url,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            error=exc,
            upstreamStatus=upstream_status,
            responseBytes=0,
        )
        if upstream_status == 404:
            return None
        if isinstance(exc, HTTPException):
            raise
        raise SnsRemoteMediaUpstreamError(
            "SNS video CDN request failed.",
            status_code=upstream_status,
        ) from exc

    # Decrypt in-place if the file isn't already a mp4.
    try:
        await asyncio.to_thread(maybe_decrypt_sns_video_file, tmp_path, str(key or ""))
    except Exception as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        _sns_remote_diagnostic_log(
            "video:decrypt-error",
            url=fixed_url,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            error=exc,
            upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
            responseBytes=int(response_meta.get("responseBytes") or 0),
            keystreamProvider=(
                "unavailable"
                if isinstance(exc, SnsWasmRuntimeUnavailable)
                else (
                    "electron-node-wasm"
                    if str(os.environ.get("WECHAT_TOOL_NODE_MODE") or "").strip().lower()
                    == "electron-run-as-node"
                    else "node-wasm"
                )
            ),
        )
        raise

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
        _sns_remote_diagnostic_log(
            "video:decode-rejected",
            url=fixed_url,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            reason="bytes-not-mp4",
            upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
            responseBytes=int(response_meta.get("responseBytes") or 0),
        )
        raise SnsRemoteMediaDecodeError("SNS CDN returned invalid video bytes.")

    final_path = cache_dir / f"{cache_stem}.mp4"
    try:
        os.replace(str(tmp_path), str(final_path))
    except Exception:
        final_path = tmp_path

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


def weflow_decrypt_sns_image_bytes(payload: bytes, key: str) -> bytes:
    """Decrypt a Moments image with the same full-file XOR flow that WeFlow uses."""
    raw = bytes(payload or b"")
    key_text = str(key or "").strip()
    if not raw or not key_text:
        return raw

    ks = weflow_wxisaac64_keystream(key_text, len(raw))
    if not ks:
        return raw

    out = bytearray(raw)
    n = min(len(out), len(ks))
    for i in range(n):
        out[i] ^= ks[i]
    return bytes(out)


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
    del key
    digest = hashlib.md5(normalize_sns_cache_url(url).encode("utf-8", errors="ignore")).hexdigest()
    cache_dir = account_dir / "sns_remote_cache" / digest[:2]
    return cache_dir, digest


def _legacy_sns_remote_cache_dir_and_stem(account_dir: Path, *, url: str, key: str) -> tuple[Path, str]:
    digest = hashlib.md5(f"{url}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    return account_dir / "sns_remote_cache" / digest[:2], digest


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


async def _download_sns_remote_bytes(
    url: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    response_meta: Optional[dict[str, object]] = None,
) -> tuple[bytes, str, str]:
    """Download SNS media bytes from Tencent CDN with a few safe header variants."""
    u = str(url or "").strip()
    if not u:
        return b"", "", ""

    max_bytes = 25 * 1024 * 1024

    base_headers = {
        "User-Agent": "MicroMessenger Client",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
    }

    async def download(http_client: httpx.AsyncClient) -> tuple[bytes, str, str]:
        resp = await http_client.get(u, headers=base_headers, timeout=15.0)
        if resp.status_code not in {200, 206}:
            raise httpx.HTTPStatusError(
                f"Unexpected SNS status {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        payload = bytes(resp.content or b"")
        if len(payload) > max_bytes:
            raise HTTPException(status_code=400, detail="SNS media too large (>25MB).")
        content_type = str(resp.headers.get("Content-Type") or "").strip()
        x_enc = str(resp.headers.get("x-enc") or "").strip()
        if response_meta is not None:
            response_meta.update(
                {
                    "upstreamStatus": int(resp.status_code),
                    "responseBytes": len(payload),
                    "contentType": content_type,
                    "xEnc": x_enc,
                }
            )
        return payload, content_type, x_enc

    if client is not None:
        return await download(client)
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as owned_client:
        return await download(owned_client)


@dataclass(frozen=True)
class SnsRemoteImageResult:
    payload: bytes
    media_type: str
    source: str
    x_enc: str = ""
    cache_path: Optional[Path] = None


def get_cached_sns_remote_image(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    force_original: bool = False,
) -> Optional[SnsRemoteImageResult]:
    """Return a validated remote-image cache entry without doing network I/O."""
    u_fixed = fix_sns_cdn_url(
        url,
        token=token,
        is_video=False,
        force_original=force_original,
    )
    if not u_fixed:
        return None

    try:
        host = str(urlparse(u_fixed).hostname or "").strip().lower()
    except Exception:
        return None
    if not is_allowed_sns_media_host(host):
        return None

    cache_dir, cache_stem = _sns_remote_cache_dir_and_stem(account_dir, url=u_fixed, key=str(key or ""))
    try:
        existing = _sns_remote_cache_existing_path(cache_dir, cache_stem)
        if existing is None:
            legacy_dir, legacy_stem = _legacy_sns_remote_cache_dir_and_stem(
                account_dir,
                url=u_fixed,
                key=str(key or ""),
            )
            legacy = _sns_remote_cache_existing_path(legacy_dir, legacy_stem)
            if legacy is not None:
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    migrated = cache_dir / f"{cache_stem}{legacy.suffix.lower()}"
                    os.replace(str(legacy), str(migrated))
                    existing = migrated
                except Exception:
                    existing = legacy
        if existing is None:
            return None

        mt = _ext_to_mime(existing.suffix)
        if (existing.suffix or "").lower() == ".bin" or not mt:
            mt = _sniff_image_mime_from_file(existing)
            if not mt:
                try:
                    existing.unlink(missing_ok=True)
                except Exception:
                    pass
                return None

            ext = _mime_to_ext(mt)
            if ext != ".bin":
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    desired = cache_dir / f"{cache_stem}{ext}"
                    if desired.exists():
                        existing.unlink(missing_ok=True)
                        existing = desired
                    else:
                        os.replace(str(existing), str(desired))
                        existing = desired
                except Exception:
                    pass

        payload = existing.read_bytes()
        if not payload:
            return None
        return SnsRemoteImageResult(
            payload=payload,
            media_type=mt,
            source="remote-cache",
            x_enc="",
            cache_path=existing,
        )
    except Exception:
        return None


async def try_fetch_and_decrypt_sns_image_remote(
    *,
    account_dir: Path,
    url: str,
    key: str,
    token: str,
    use_cache: bool,
    client: Optional[httpx.AsyncClient] = None,
    diagnostic_id: str = "",
    force_original: bool = False,
) -> Optional[SnsRemoteImageResult]:
    """Try WeFlow-style: download from CDN -> WxIsaac64 full-file XOR -> return bytes.

    Returns None only for a true miss (invalid/unsupported URL or upstream 404).
    Runtime, upstream, and invalid-content failures remain distinguishable to API callers.
    """
    raw_input_url = str(url or "")
    u_fixed = fix_sns_cdn_url(
        raw_input_url,
        token=token,
        is_video=False,
        force_original=force_original,
    )
    url_rewritten = u_fixed != html.unescape(raw_input_url).strip()
    if not u_fixed:
        if str(url or "").strip():
            _sns_remote_diagnostic_log(
                "remote:reject",
                url=str(url or ""),
                diagnostic_id=diagnostic_id,
                key=key,
                token=token,
                reason="url-normalization-empty",
                urlRewritten=url_rewritten,
            )
        return None

    try:
        p = urlparse(u_fixed)
        host = str(p.hostname or "").strip().lower()
    except Exception as exc:
        _sns_remote_diagnostic_log(
            "remote:reject",
            url=u_fixed,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            reason="url-parse-error",
            urlRewritten=url_rewritten,
            error=exc,
        )
        return None
    if not is_allowed_sns_media_host(host):
        _sns_remote_diagnostic_log(
            "remote:reject",
            url=u_fixed,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            reason="host-not-allowed",
            urlRewritten=url_rewritten,
        )
        return None

    cache_dir, cache_stem = _sns_remote_cache_dir_and_stem(account_dir, url=u_fixed, key=str(key or ""))

    if use_cache:
        cached = get_cached_sns_remote_image(
            account_dir=account_dir,
            url=u_fixed,
            key=key,
            token=token,
            force_original=force_original,
        )
        if cached is not None:
            return cached

    cache_path: Optional[Path] = None

    response_meta: dict[str, object] = {}
    try:
        raw, _content_type, x_enc = await _download_sns_remote_bytes(
            u_fixed,
            client=client,
            response_meta=response_meta,
        )
    except Exception as e:
        response = getattr(e, "response", None)
        upstream_status = int(getattr(response, "status_code", 0) or 0)
        _sns_remote_diagnostic_log(
            "remote:download-error",
            url=u_fixed,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            error=e,
            upstreamStatus=upstream_status,
            responseBytes=0,
            urlRewritten=url_rewritten,
        )
        if upstream_status == 404:
            return None
        if isinstance(e, HTTPException):
            raise
        raise SnsRemoteMediaUpstreamError(
            "SNS CDN request failed.",
            status_code=upstream_status,
        ) from e

    _sns_remote_diagnostic_log(
        "remote:downloaded",
        url=u_fixed,
        diagnostic_id=diagnostic_id,
        key=key,
        token=token,
        upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
        responseBytes=len(raw),
        urlRewritten=url_rewritten,
    )

    if not raw:
        _sns_remote_diagnostic_log(
            "remote:decode-rejected",
            url=u_fixed,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            reason="empty-download",
            upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
            responseBytes=0,
            urlRewritten=url_rewritten,
        )
        raise SnsRemoteMediaDecodeError("SNS CDN returned an empty media payload.")

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
            decoded2 = await asyncio.to_thread(weflow_decrypt_sns_image_bytes, raw, k)
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
                    _sns_remote_diagnostic_log(
                        "remote:decode-rejected",
                        url=u_fixed,
                        diagnostic_id=diagnostic_id,
                        key=key,
                        token=token,
                        reason="decrypted-bytes-not-image",
                        rawBytes=len(raw),
                        rawMediaType=str(mt_raw or ""),
                        xEnc=str(x_enc or ""),
                        upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
                        responseBytes=len(raw),
                        urlRewritten=url_rewritten,
                        keystreamProvider=(
                            "electron-node-wasm"
                            if str(os.environ.get("WECHAT_TOOL_NODE_MODE") or "").strip().lower()
                            == "electron-run-as-node"
                            else "node-wasm"
                        ),
                    )
                    raise SnsRemoteMediaDecodeError(
                        "SNS CDN media could not be decoded as an image."
                    )
        except SnsWasmRuntimeUnavailable as e:
            _sns_remote_diagnostic_log(
                "remote:runtime-unavailable",
                url=u_fixed,
                diagnostic_id=diagnostic_id,
                key=key,
                token=token,
                error=e,
                rawBytes=len(raw),
                xEnc=str(x_enc or ""),
                upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
                responseBytes=len(raw),
                urlRewritten=url_rewritten,
                keystreamProvider="unavailable",
            )
            raise
        except SnsRemoteMediaDecodeError:
            raise
        except Exception as e:
            _sns_remote_diagnostic_log(
                "remote:decrypt-error",
                url=u_fixed,
                diagnostic_id=diagnostic_id,
                key=key,
                token=token,
                error=e,
                rawBytes=len(raw),
                rawMediaType=str(mt_raw or ""),
                xEnc=str(x_enc or ""),
                upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
                responseBytes=len(raw),
                urlRewritten=url_rewritten,
            )
            if not mt_raw:
                raise SnsRemoteMediaDecodeError(
                    "SNS CDN media decryption failed."
                ) from e
            decoded = raw
            mt = mt_raw
            decrypted = False

    if not mt:
        _sns_remote_diagnostic_log(
            "remote:decode-rejected",
            url=u_fixed,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            reason="unsupported-image-bytes",
            rawBytes=len(raw),
            xEnc=str(x_enc or ""),
            upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
            responseBytes=len(raw),
            urlRewritten=url_rewritten,
        )
        raise SnsRemoteMediaDecodeError("SNS CDN returned unsupported image bytes.")

    try:
        ext = _mime_to_ext(mt)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{cache_stem}{ext}"

        tmp = cache_path.with_suffix(cache_path.suffix + f".{time.time_ns()}.tmp")
        tmp.write_bytes(decoded)
        os.replace(str(tmp), str(cache_path))

        for other_ext in _SNS_REMOTE_CACHE_EXTS:
            if other_ext.lower() == ext.lower():
                continue
            other = cache_dir / f"{cache_stem}{other_ext}"
            try:
                if other.exists() and other.is_file():
                    other.unlink(missing_ok=True)
            except Exception:
                continue
    except Exception as exc:
        _sns_remote_diagnostic_log(
            "remote:cache-write-error",
            url=u_fixed,
            diagnostic_id=diagnostic_id,
            key=key,
            token=token,
            error=exc,
            decodedBytes=len(decoded),
            mediaType=str(mt or ""),
        )
        cache_path = None

    _sns_remote_diagnostic_log(
        "remote:ready",
        url=u_fixed,
        diagnostic_id=diagnostic_id,
        key=key,
        token=token,
        upstreamStatus=int(response_meta.get("upstreamStatus") or 200),
        responseBytes=len(raw),
        decodedBytes=len(decoded),
        mediaType=str(mt or ""),
        urlRewritten=url_rewritten,
        keystreamProvider=(
            (
                "electron-node-wasm"
                if str(os.environ.get("WECHAT_TOOL_NODE_MODE") or "").strip().lower()
                == "electron-run-as-node"
                else "node-wasm"
            )
            if decrypted
            else "not-required"
        ),
    )

    return SnsRemoteImageResult(
        payload=decoded,
        media_type=mt,
        source="remote-decrypt" if decrypted else "remote",
        x_enc=str(x_enc or "").strip(),
        cache_path=cache_path,
    )
