import ctypes
import base64
import binascii
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .key_store import get_account_keys_from_store
from .logging_config import get_logger
from .media_helpers import _resolve_account_db_storage_dir

logger = get_logger(__name__)


class WCDBRealtimeError(RuntimeError):
    pass


_NATIVE_DIR = Path(__file__).resolve().parent / "native"
_DEFAULT_WCDB_API_DLL = _NATIVE_DIR / "wcdb_api.dll"
_WCDB_API_DLL_SELECTED: Optional[Path] = None


def _iter_runtime_wcdb_api_dll_paths() -> tuple[Path, ...]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add_anchor(anchor: str | Path | None) -> None:
        if not anchor:
            return
        try:
            base = Path(anchor).resolve()
        except Exception:
            base = Path(anchor)
        candidate = base / "native" / "wcdb_api.dll"
        key = str(candidate).replace("/", "\\").rstrip("\\").lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    add_anchor(os.environ.get("WECHAT_TOOL_DATA_DIR", "").strip())
    add_anchor(Path.cwd())
    if getattr(sys, "frozen", False):
        add_anchor(Path(sys.executable).resolve().parent)

    return tuple(candidates)


def _is_project_wcdb_api_dll_path(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        resolved = path

    try:
        default_resolved = _DEFAULT_WCDB_API_DLL.resolve(strict=False)
    except Exception:
        default_resolved = _DEFAULT_WCDB_API_DLL

    if resolved == default_resolved:
        return True

    for candidate in _iter_runtime_wcdb_api_dll_paths():
        try:
            if resolved == candidate.resolve(strict=False):
                return True
        except Exception:
            if resolved == candidate:
                return True

    parts = tuple(str(part).lower() for part in resolved.parts)
    allowed_suffixes = (
        ("backend", "native", "wcdb_api.dll"),
        ("wechat_decrypt_tool", "native", "wcdb_api.dll"),
    )
    return any(parts[-len(suffix) :] == suffix for suffix in allowed_suffixes)


def _candidate_wcdb_api_dll_paths() -> list[Path]:
    """Return allowed locations for wcdb_api.dll."""
    cands: list[Path] = []

    env = str(os.environ.get("WECHAT_TOOL_WCDB_API_DLL_PATH", "") or "").strip()
    if env:
        env_path = Path(env)
        if _is_project_wcdb_api_dll_path(env_path):
            cands.append(env_path)
        else:
            logger.warning("[wcdb] ignore external wcdb_api.dll override: %s", env_path)

    for p in (_DEFAULT_WCDB_API_DLL,):
        if p not in cands:
            cands.append(p)

    return cands


def _resolve_wcdb_api_dll_path() -> Path:
    global _WCDB_API_DLL_SELECTED
    if _WCDB_API_DLL_SELECTED is not None:
        return _WCDB_API_DLL_SELECTED

    for p in _candidate_wcdb_api_dll_paths():
        try:
            if p.exists() and p.is_file():
                _WCDB_API_DLL_SELECTED = p
                return p
        except Exception:
            continue

    # Fall back to the default path even if it doesn't exist; caller will raise a clear error.
    _WCDB_API_DLL_SELECTED = _DEFAULT_WCDB_API_DLL
    return _WCDB_API_DLL_SELECTED

_lib_lock = threading.Lock()
_lib: Optional[ctypes.CDLL] = None
_initialized = False
_loaded_wcdb_api_dll: Optional[Path] = None
_preloaded_native_libs: list[ctypes.CDLL] = []
_protection_checked = False
_protection_result: Optional[tuple[int, str]] = None
_AUTO_SIDECAR_LOCK = threading.Lock()
_AUTO_SIDECAR_PROC: Optional[subprocess.Popen] = None
_AUTO_SIDECAR_URL = ""
_AUTO_SIDECAR_TOKEN = ""


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _iter_wcdb_resource_paths(wcdb_api_dll: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: str | Path | None) -> None:
        if not path:
            return
        try:
            resolved = Path(path).resolve()
        except Exception:
            resolved = Path(path)
        key = str(resolved).replace("/", "\\").rstrip("\\").lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(resolved)

    dll_dir = wcdb_api_dll.parent
    add(dll_dir)
    add(dll_dir.parent)
    add(_NATIVE_DIR)
    add(_NATIVE_DIR.parent)

    cwd = Path.cwd()
    add(cwd)
    add(cwd / "resources")

    data_dir = str(os.environ.get("WECHAT_TOOL_DATA_DIR", "") or "").strip()
    if data_dir:
        add(data_dir)
        add(Path(data_dir) / "resources")

    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).resolve().parent
        except Exception:
            exe_dir = Path(sys.executable).parent
        add(exe_dir)
        add(exe_dir / "resources")

    return tuple(candidates)


def _preload_wcdb_dependencies(wcdb_api_dll: Path) -> None:
    dll_dir = wcdb_api_dll.parent
    for name in ("WCDB.dll", "SDL2.dll", "VoipEngine.dll"):
        dep_path = dll_dir / name
        if not dep_path.exists():
            continue
        try:
            _preloaded_native_libs.append(ctypes.CDLL(str(dep_path)))
            logger.info("[wcdb] preloaded dependency: %s", dep_path)
        except Exception as exc:
            logger.warning("[wcdb] preload dependency failed: %s err=%s", dep_path, exc)


def _run_init_protection(lib: ctypes.CDLL, wcdb_api_dll: Path) -> None:
    global _protection_checked, _protection_result
    if _protection_checked:
        return
    _protection_checked = True

    fn = getattr(lib, "InitProtection", None)
    if not fn:
        logger.info("[wcdb] InitProtection not exported: %s", wcdb_api_dll)
        return

    try:
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_int32
    except Exception:
        pass

    best: Optional[tuple[int, str]] = None
    for resource_path in _iter_wcdb_resource_paths(wcdb_api_dll):
        try:
            rc = int(fn(str(resource_path).encode("utf-8")))
            logger.info("[wcdb] InitProtection rc=%s path=%s", rc, resource_path)
            if rc == 0:
                _protection_result = (rc, str(resource_path))
                return
            if best is None:
                best = (rc, str(resource_path))
        except Exception as exc:
            logger.warning("[wcdb] InitProtection exception path=%s err=%s", resource_path, exc)

    _protection_result = best


def _format_protection_hint() -> str:
    if not _protection_result:
        return ""
    rc, resource_path = _protection_result
    return f" protection_rc={rc} protection_path={resource_path}"


def _sidecar_url() -> str:
    return str(os.environ.get("WECHAT_TOOL_WCDB_SIDECAR_URL", "") or "").strip().rstrip("/")


def _sidecar_enabled() -> bool:
    return bool(_sidecar_url())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_sidecar_assets() -> tuple[Path, Path, Path] | None:
    if getattr(sys, "frozen", False):
        return None

    repo_root = _repo_root()
    electron_exe = repo_root / "desktop" / "node_modules" / "electron" / "dist" / "electron.exe"
    sidecar_script = repo_root / "desktop" / "src" / "wcdb-sidecar.cjs"
    koffi_dir = repo_root / "desktop" / "vendor" / "koffi"

    try:
        if electron_exe.is_file() and sidecar_script.is_file() and koffi_dir.exists():
            return electron_exe, sidecar_script, koffi_dir
    except Exception:
        return None
    return None


def _auto_sidecar_started_here() -> bool:
    with _AUTO_SIDECAR_LOCK:
        return bool(_AUTO_SIDECAR_URL and _AUTO_SIDECAR_TOKEN)


def _parse_port(value: object) -> Optional[int]:
    try:
        raw = str(value or "").strip()
        if not raw:
            return None
        port = int(raw, 10)
    except Exception:
        return None
    if 1 <= port <= 65535:
        return port
    return None


def _pick_free_port() -> int:
    requested = _parse_port(os.environ.get("WECHAT_TOOL_WCDB_SIDECAR_PORT"))
    if requested is not None:
        return requested

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _build_auto_sidecar_resource_paths(wcdb_api_dll: Path) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()

    def add(path: str | Path | None) -> None:
        if not path:
            return
        try:
            resolved = Path(path).resolve()
        except Exception:
            resolved = Path(path)
        key = str(resolved).replace("/", "\\").rstrip("\\").lower()
        if not key or key in seen:
            return
        seen.add(key)
        items.append(str(resolved))

    repo_root = _repo_root()
    dll_dir = wcdb_api_dll.parent
    add(dll_dir)
    add(dll_dir.parent)
    add(repo_root)
    add(repo_root / "resources")

    data_dir = str(os.environ.get("WECHAT_TOOL_DATA_DIR", "") or "").strip()
    if data_dir:
        add(data_dir)
        add(Path(data_dir) / "resources")
    else:
        add(Path.cwd())
        add(Path.cwd() / "resources")

    return items


def _stop_auto_sidecar() -> None:
    global _AUTO_SIDECAR_PROC, _AUTO_SIDECAR_URL, _AUTO_SIDECAR_TOKEN

    with _AUTO_SIDECAR_LOCK:
        proc = _AUTO_SIDECAR_PROC
        owned_url = _AUTO_SIDECAR_URL
        owned_token = _AUTO_SIDECAR_TOKEN
        _AUTO_SIDECAR_PROC = None
        _AUTO_SIDECAR_URL = ""
        _AUTO_SIDECAR_TOKEN = ""

    if owned_url and os.environ.get("WECHAT_TOOL_WCDB_SIDECAR_URL") == owned_url:
        os.environ.pop("WECHAT_TOOL_WCDB_SIDECAR_URL", None)
    if owned_token and os.environ.get("WECHAT_TOOL_WCDB_SIDECAR_TOKEN") == owned_token:
        os.environ.pop("WECHAT_TOOL_WCDB_SIDECAR_TOKEN", None)

    if proc is None:
        return

    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except Exception:
                proc.kill()
    except Exception:
        pass


def _maybe_start_auto_sidecar() -> bool:
    global _AUTO_SIDECAR_PROC, _AUTO_SIDECAR_URL, _AUTO_SIDECAR_TOKEN

    if _sidecar_enabled() or not _is_windows():
        return False

    assets = _source_sidecar_assets()
    if not assets:
        return False

    wcdb_api_dll = _resolve_wcdb_api_dll_path()
    try:
        if not wcdb_api_dll.exists():
            return False
    except Exception:
        return False

    electron_exe, sidecar_script, koffi_dir = assets
    repo_root = _repo_root()

    with _AUTO_SIDECAR_LOCK:
        proc = _AUTO_SIDECAR_PROC
        if proc is not None and proc.poll() is None and _AUTO_SIDECAR_URL and _AUTO_SIDECAR_TOKEN:
            os.environ["WECHAT_TOOL_WCDB_SIDECAR_URL"] = _AUTO_SIDECAR_URL
            os.environ["WECHAT_TOOL_WCDB_SIDECAR_TOKEN"] = _AUTO_SIDECAR_TOKEN
            return True

        if proc is not None and proc.poll() is not None:
            _AUTO_SIDECAR_PROC = None
            _AUTO_SIDECAR_URL = ""
            _AUTO_SIDECAR_TOKEN = ""

        port = _pick_free_port()
        token = os.urandom(24).hex()
        url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "ELECTRON_RUN_AS_NODE": "1",
                "WECHAT_TOOL_WCDB_SIDECAR_HOST": "127.0.0.1",
                "WECHAT_TOOL_WCDB_SIDECAR_PORT": str(port),
                "WECHAT_TOOL_WCDB_SIDECAR_TOKEN": token,
                "WECHAT_TOOL_WCDB_API_DLL_PATH": str(wcdb_api_dll),
                "WECHAT_TOOL_WCDB_DLL_DIR": str(wcdb_api_dll.parent),
                "WECHAT_TOOL_WCDB_RESOURCE_PATHS": json.dumps(
                    _build_auto_sidecar_resource_paths(wcdb_api_dll), ensure_ascii=False
                ),
                "WECHAT_TOOL_KOFFI_DIR": str(koffi_dir),
            }
        )

        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
        try:
            proc = subprocess.Popen(
                [str(electron_exe), str(sidecar_script)],
                cwd=str(repo_root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:
            logger.warning("[wcdb] auto sidecar start failed: %s", exc)
            return False

        _AUTO_SIDECAR_PROC = proc
        _AUTO_SIDECAR_URL = url
        _AUTO_SIDECAR_TOKEN = token
        os.environ["WECHAT_TOOL_WCDB_SIDECAR_URL"] = url
        os.environ["WECHAT_TOOL_WCDB_SIDECAR_TOKEN"] = token

    logger.info("[wcdb] auto-started electron sidecar url=%s dll=%s", _AUTO_SIDECAR_URL, wcdb_api_dll)
    return True


def _sidecar_call(action: str, payload: Optional[dict[str, Any]] = None, *, timeout: float = 30.0) -> dict[str, Any]:
    base_url = _sidecar_url()
    if not base_url:
        raise WCDBRealtimeError("WCDB sidecar is not configured.")

    token = str(os.environ.get("WECHAT_TOOL_WCDB_SIDECAR_TOKEN", "") or "").strip()
    body = json.dumps(
        {
            "action": str(action or "").strip(),
            "payload": payload or {},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    deadline = time.monotonic() + max(1.0, float(timeout or 30.0))
    last_err: Exception | None = None
    attempts = 20 if action == "init" else 3
    for attempt in range(attempts):
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        if token:
            headers["X-WCDB-Sidecar-Token"] = token
        req = urllib.request.Request(
            f"{base_url}/call",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            remaining = max(0.5, deadline - time.monotonic())
            with urllib.request.urlopen(req, timeout=min(remaining, max(0.5, timeout))) as resp:
                raw = resp.read()
            decoded = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            if not isinstance(decoded, dict):
                raise WCDBRealtimeError("WCDB sidecar returned invalid response.")
            if decoded.get("ok"):
                result = decoded.get("result")
                return result if isinstance(result, dict) else {}
            rc = decoded.get("rc")
            err = str(decoded.get("error") or "WCDB sidecar call failed")
            logs = decoded.get("logs")
            hint = ""
            if isinstance(logs, list) and logs:
                hint = f" logs={[str(x) for x in logs[:6]]}"
            raise WCDBRealtimeError(f"{err} rc={rc}.{hint}")
        except WCDBRealtimeError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt >= attempts - 1 or time.monotonic() >= deadline:
                break
            time.sleep(0.15)
        except Exception as exc:
            last_err = exc
            break

    raise WCDBRealtimeError(f"WCDB sidecar unavailable: {last_err}")


def _sidecar_payload(action: str, payload: Optional[dict[str, Any]] = None, *, timeout: float = 30.0) -> str:
    result = _sidecar_call(action, payload, timeout=timeout)
    return str(result.get("payload") or "")


def _load_wcdb_lib() -> ctypes.CDLL:
    global _lib, _loaded_wcdb_api_dll
    with _lib_lock:
        if _lib is not None:
            return _lib

        if not _is_windows():
            raise WCDBRealtimeError("WCDB realtime mode is only supported on Windows.")

        wcdb_api_dll = _resolve_wcdb_api_dll_path()
        if not wcdb_api_dll.exists():
            raise WCDBRealtimeError(f"Missing wcdb_api.dll at: {wcdb_api_dll}")

        # Ensure dependent DLLs (e.g. WCDB.dll) can be found.
        try:
            os.add_dll_directory(str(wcdb_api_dll.parent))
        except Exception:
            pass

        _preload_wcdb_dependencies(wcdb_api_dll)
        lib = ctypes.CDLL(str(wcdb_api_dll))
        logger.info("[wcdb] using wcdb_api.dll: %s", wcdb_api_dll)

        # Signatures
        lib.wcdb_init.argtypes = []
        lib.wcdb_init.restype = ctypes.c_int

        lib.wcdb_shutdown.argtypes = []
        lib.wcdb_shutdown.restype = ctypes.c_int

        lib.wcdb_open_account.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int64),
        ]
        lib.wcdb_open_account.restype = ctypes.c_int

        lib.wcdb_close_account.argtypes = [ctypes.c_int64]
        lib.wcdb_close_account.restype = ctypes.c_int

        # Optional: wcdb_set_my_wxid(handle, wxid)
        try:
            lib.wcdb_set_my_wxid.argtypes = [ctypes.c_int64, ctypes.c_char_p]
            lib.wcdb_set_my_wxid.restype = ctypes.c_int
        except Exception:
            pass

        lib.wcdb_get_sessions.argtypes = [ctypes.c_int64, ctypes.POINTER(ctypes.c_char_p)]
        lib.wcdb_get_sessions.restype = ctypes.c_int

        lib.wcdb_get_messages.argtypes = [
            ctypes.c_int64,
            ctypes.c_char_p,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_char_p),
        ]
        lib.wcdb_get_messages.restype = ctypes.c_int

        lib.wcdb_get_message_count.argtypes = [ctypes.c_int64, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32)]
        lib.wcdb_get_message_count.restype = ctypes.c_int

        lib.wcdb_get_display_names.argtypes = [ctypes.c_int64, ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
        lib.wcdb_get_display_names.restype = ctypes.c_int

        lib.wcdb_get_avatar_urls.argtypes = [ctypes.c_int64, ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
        lib.wcdb_get_avatar_urls.restype = ctypes.c_int

        lib.wcdb_get_group_member_count.argtypes = [ctypes.c_int64, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32)]
        lib.wcdb_get_group_member_count.restype = ctypes.c_int

        lib.wcdb_get_group_members.argtypes = [ctypes.c_int64, ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p)]
        lib.wcdb_get_group_members.restype = ctypes.c_int

        # Optional (newer DLLs): wcdb_get_group_nicknames(handle, chatroom_id, out_json)
        try:
            lib.wcdb_get_group_nicknames.argtypes = [
                ctypes.c_int64,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_char_p),
            ]
            lib.wcdb_get_group_nicknames.restype = ctypes.c_int
        except Exception:
            pass

        # Optional: execute arbitrary SQL on a selected database kind/path.
        # Signature: wcdb_exec_query(handle, kind, path, sql, out_json)
        try:
            lib.wcdb_exec_query.argtypes = [
                ctypes.c_int64,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_char_p),
            ]
            lib.wcdb_exec_query.restype = ctypes.c_int
        except Exception:
            pass

        # Optional (newer DLLs): update a single message content in message db.
        # Signature: wcdb_update_message(handle, sessionId, localId, createTime, newContent, outError)
        try:
            lib.wcdb_update_message.argtypes = [
                ctypes.c_int64,
                ctypes.c_char_p,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_char_p),
            ]
            lib.wcdb_update_message.restype = ctypes.c_int
        except Exception:
            pass

        # Optional (newer DLLs): delete a single message in message db.
        # Signature: wcdb_delete_message(handle, sessionId, localId, createTime, dbPathHint, outError)
        try:
            lib.wcdb_delete_message.argtypes = [
                ctypes.c_int64,
                ctypes.c_char_p,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_char_p),
            ]
            lib.wcdb_delete_message.restype = ctypes.c_int
        except Exception:
            pass

        # Optional (newer DLLs): wcdb_get_sns_timeline(handle, limit, offset, usernames_json, keyword, start_time, end_time, out_json)
        try:
            lib.wcdb_get_sns_timeline.argtypes = [
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.POINTER(ctypes.c_char_p),
            ]
            lib.wcdb_get_sns_timeline.restype = ctypes.c_int
        except Exception:
            # Older wcdb_api.dll may not expose this export.
            pass

        # Optional (newer DLLs): wcdb_decrypt_sns_image(encrypted_data, len, key, out_hex)
        # WeFlow uses this to decrypt Moments CDN images.
        try:
            lib.wcdb_decrypt_sns_image.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int32,
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_void_p),
            ]
            lib.wcdb_decrypt_sns_image.restype = ctypes.c_int32
        except Exception:
            pass

        lib.wcdb_get_logs.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        lib.wcdb_get_logs.restype = ctypes.c_int

        lib.wcdb_free_string.argtypes = [ctypes.c_char_p]
        lib.wcdb_free_string.restype = None

        _loaded_wcdb_api_dll = wcdb_api_dll
        _lib = lib
        return lib


def _ensure_initialized() -> None:
    global _initialized, _loaded_wcdb_api_dll, _protection_result
    _maybe_start_auto_sidecar()
    if _sidecar_enabled():
        with _lib_lock:
            if _initialized:
                return
        try:
            result = _sidecar_call("init", timeout=30.0)
            dll_path = str(result.get("dllPath") or "").strip()
            if dll_path:
                try:
                    _loaded_wcdb_api_dll = Path(dll_path)
                except Exception:
                    pass
            protection = result.get("protection")
            if isinstance(protection, list):
                for item in protection:
                    if isinstance(item, dict) and "rc" in item:
                        try:
                            _protection_result = (int(item.get("rc")), str(item.get("path") or ""))
                            if int(item.get("rc")) == 0:
                                break
                        except Exception:
                            continue
            with _lib_lock:
                _initialized = True
            return
        except Exception:
            if not _auto_sidecar_started_here():
                raise
            logger.warning("[wcdb] auto sidecar init failed, fallback to in-process wcdb")
            _stop_auto_sidecar()

    lib = _load_wcdb_lib()
    with _lib_lock:
        if _initialized:
            return
        wcdb_api_dll = _loaded_wcdb_api_dll or _resolve_wcdb_api_dll_path()
        _run_init_protection(lib, wcdb_api_dll)
        rc = int(lib.wcdb_init())
        if rc != 0:
            logs = get_native_logs(require_initialized=False)
            hint = _format_protection_hint()
            if logs:
                hint += f" logs={logs[:6]}"
            raise WCDBRealtimeError(f"wcdb_init failed: {rc}.{hint}")
        _initialized = True


def _safe_load_json(payload: str) -> Any:
    try:
        return json.loads(payload)
    except Exception:
        return None


def _call_out_json(fn, *args) -> str:
    lib = _load_wcdb_lib()
    out = ctypes.c_char_p()
    rc = int(fn(*args, ctypes.byref(out)))
    try:
        if rc != 0:
            logs = get_native_logs()
            hint = ""
            if logs:
                hint = f" logs={logs[:6]}"
            raise WCDBRealtimeError(f"wcdb api call failed: {rc}.{hint}")

        raw = out.value or b""
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""
    finally:
        try:
            if out.value:
                lib.wcdb_free_string(out)
        except Exception:
            pass


def _call_out_error(fn, *args) -> None:
    lib = _load_wcdb_lib()
    out = ctypes.c_char_p()
    rc = int(fn(*args, ctypes.byref(out)))
    try:
        if rc != 0:
            err = ""
            try:
                if out.value:
                    err = (out.value or b"").decode("utf-8", errors="replace")
            except Exception:
                err = ""

            logs = get_native_logs()
            hint = f" logs={logs[:6]}" if logs else ""
            if err:
                raise WCDBRealtimeError(f"wcdb api call failed: {rc}. error={err}.{hint}")
            raise WCDBRealtimeError(f"wcdb api call failed: {rc}.{hint}")
    finally:
        try:
            if out.value:
                lib.wcdb_free_string(out)
        except Exception:
            pass


def get_native_logs(*, require_initialized: bool = True) -> list[str]:
    if _sidecar_enabled():
        if require_initialized:
            try:
                _ensure_initialized()
            except Exception:
                return []
        try:
            result = _sidecar_call("get_logs", timeout=5.0)
            logs = result.get("logs")
            if isinstance(logs, list):
                return [str(x) for x in logs]
            return []
        except Exception:
            return []

    if require_initialized:
        try:
            _ensure_initialized()
        except Exception:
            return []
    lib = _load_wcdb_lib()
    out = ctypes.c_char_p()
    rc = int(lib.wcdb_get_logs(ctypes.byref(out)))
    try:
        if rc != 0 or not out.value:
            return []
        payload = out.value.decode("utf-8", errors="replace")
        decoded = _safe_load_json(payload)
        if isinstance(decoded, list):
            return [str(x) for x in decoded]
        return []
    except Exception:
        return []
    finally:
        try:
            if out.value:
                lib.wcdb_free_string(out)
        except Exception:
            pass


def open_account(session_db_path: Path, key_hex: str) -> int:
    _ensure_initialized()

    p = Path(session_db_path)
    if not p.exists():
        raise WCDBRealtimeError(f"session db not found: {p}")
    key = str(key_hex or "").strip()
    if len(key) != 64:
        raise WCDBRealtimeError("Invalid db key (must be 64 hex chars).")

    if _sidecar_enabled():
        result = _sidecar_call(
            "open_account",
            {
                "path": str(p),
                "key": key,
            },
            timeout=30.0,
        )
        handle = int(result.get("handle") or 0)
        if handle <= 0:
            raise WCDBRealtimeError("wcdb_open_account failed: invalid sidecar handle.")
        return handle

    lib = _load_wcdb_lib()
    out_handle = ctypes.c_int64(0)
    rc = int(lib.wcdb_open_account(str(p).encode("utf-8"), key.encode("utf-8"), ctypes.byref(out_handle)))
    if rc != 0 or int(out_handle.value) <= 0:
        logs = get_native_logs()
        hint = f" logs={logs[:6]}" if logs else ""
        raise WCDBRealtimeError(f"wcdb_open_account failed: {rc}.{hint}")
    return int(out_handle.value)


def set_my_wxid(handle: int, wxid: str) -> bool:
    """Best-effort set the "my wxid" context for some WCDB APIs."""
    try:
        _ensure_initialized()
    except Exception:
        return False

    w = str(wxid or "").strip()
    if not w:
        return False

    if _sidecar_enabled():
        try:
            result = _sidecar_call("set_my_wxid", {"handle": int(handle), "wxid": w}, timeout=10.0)
            return bool(result.get("success"))
        except Exception:
            return False

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_set_my_wxid", None)
    if not fn:
        return False

    try:
        rc = int(fn(ctypes.c_int64(int(handle)), w.encode("utf-8")))
    except Exception:
        return False

    return rc == 0


def close_account(handle: int) -> None:
    try:
        h = int(handle)
    except Exception:
        return
    if h <= 0:
        return
    try:
        _ensure_initialized()
    except Exception:
        return
    if _sidecar_enabled():
        try:
            _sidecar_call("close_account", {"handle": h}, timeout=5.0)
        except Exception:
            pass
        return
    lib = _load_wcdb_lib()
    try:
        lib.wcdb_close_account(ctypes.c_int64(h))
    except Exception:
        return


def get_sessions(handle: int) -> list[dict[str, Any]]:
    _ensure_initialized()
    if _sidecar_enabled():
        payload = _sidecar_payload("get_sessions", {"handle": int(handle)}, timeout=30.0)
        decoded = _safe_load_json(payload)
        if isinstance(decoded, list):
            return [x for x in decoded if isinstance(x, dict)]
        return []

    lib = _load_wcdb_lib()
    payload = _call_out_json(lib.wcdb_get_sessions, ctypes.c_int64(int(handle)))
    decoded = _safe_load_json(payload)
    if isinstance(decoded, list):
        out: list[dict[str, Any]] = []
        for x in decoded:
            if isinstance(x, dict):
                out.append(x)
        return out
    return []


def get_messages(handle: int, username: str, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    _ensure_initialized()
    u = str(username or "").strip()
    if not u:
        return []
    if _sidecar_enabled():
        payload = _sidecar_payload(
            "get_messages",
            {
                "handle": int(handle),
                "username": u,
                "limit": int(limit),
                "offset": int(offset),
            },
            timeout=30.0,
        )
        decoded = _safe_load_json(payload)
        if isinstance(decoded, list):
            return [x for x in decoded if isinstance(x, dict)]
        return []

    lib = _load_wcdb_lib()
    payload = _call_out_json(
        lib.wcdb_get_messages,
        ctypes.c_int64(int(handle)),
        u.encode("utf-8"),
        ctypes.c_int32(int(limit)),
        ctypes.c_int32(int(offset)),
    )
    decoded = _safe_load_json(payload)
    if isinstance(decoded, list):
        out: list[dict[str, Any]] = []
        for x in decoded:
            if isinstance(x, dict):
                out.append(x)
        return out
    return []


def get_message_count(handle: int, username: str) -> int:
    _ensure_initialized()
    u = str(username or "").strip()
    if not u:
        return 0
    if _sidecar_enabled():
        result = _sidecar_call(
            "get_message_count",
            {"handle": int(handle), "username": u},
            timeout=30.0,
        )
        try:
            return int(result.get("count") or 0)
        except Exception:
            return 0

    lib = _load_wcdb_lib()
    out_count = ctypes.c_int32(0)
    rc = int(lib.wcdb_get_message_count(ctypes.c_int64(int(handle)), u.encode("utf-8"), ctypes.byref(out_count)))
    if rc != 0:
        return 0
    return int(out_count.value)


def get_display_names(handle: int, usernames: list[str]) -> dict[str, str]:
    _ensure_initialized()
    uniq = [str(u or "").strip() for u in usernames if str(u or "").strip()]
    uniq = list(dict.fromkeys(uniq))
    if not uniq:
        return {}
    if _sidecar_enabled():
        out_json = _sidecar_payload(
            "get_display_names",
            {"handle": int(handle), "usernames": uniq},
            timeout=30.0,
        )
        decoded = _safe_load_json(out_json)
        if isinstance(decoded, dict):
            return {str(k): str(v) for k, v in decoded.items()}
        return {}

    lib = _load_wcdb_lib()
    payload = json.dumps(uniq, ensure_ascii=False).encode("utf-8")
    out_json = _call_out_json(lib.wcdb_get_display_names, ctypes.c_int64(int(handle)), payload)
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, dict):
        return {str(k): str(v) for k, v in decoded.items()}
    return {}


def get_avatar_urls(handle: int, usernames: list[str]) -> dict[str, str]:
    _ensure_initialized()
    uniq = [str(u or "").strip() for u in usernames if str(u or "").strip()]
    uniq = list(dict.fromkeys(uniq))
    if not uniq:
        return {}
    if _sidecar_enabled():
        out_json = _sidecar_payload(
            "get_avatar_urls",
            {"handle": int(handle), "usernames": uniq},
            timeout=30.0,
        )
        decoded = _safe_load_json(out_json)
        if isinstance(decoded, dict):
            return {str(k): str(v) for k, v in decoded.items()}
        return {}

    lib = _load_wcdb_lib()
    payload = json.dumps(uniq, ensure_ascii=False).encode("utf-8")
    out_json = _call_out_json(lib.wcdb_get_avatar_urls, ctypes.c_int64(int(handle)), payload)
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, dict):
        return {str(k): str(v) for k, v in decoded.items()}
    return {}


def get_group_members(handle: int, chatroom_id: str) -> list[dict[str, Any]]:
    _ensure_initialized()
    cid = str(chatroom_id or "").strip()
    if not cid:
        return []
    if _sidecar_enabled():
        out_json = _sidecar_payload(
            "get_group_members",
            {"handle": int(handle), "chatroom_id": cid},
            timeout=30.0,
        )
        decoded = _safe_load_json(out_json)
        if isinstance(decoded, list):
            return [x for x in decoded if isinstance(x, dict)]
        return []

    lib = _load_wcdb_lib()
    out_json = _call_out_json(lib.wcdb_get_group_members, ctypes.c_int64(int(handle)), cid.encode("utf-8"))
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, list):
        out: list[dict[str, Any]] = []
        for x in decoded:
            if isinstance(x, dict):
                out.append(x)
        return out
    return []


def get_group_nicknames(handle: int, chatroom_id: str) -> dict[str, str]:
    _ensure_initialized()
    cid = str(chatroom_id or "").strip()
    if not cid:
        return {}

    if _sidecar_enabled():
        try:
            out_json = _sidecar_payload(
                "get_group_nicknames",
                {"handle": int(handle), "chatroom_id": cid},
                timeout=30.0,
            )
        except Exception:
            return {}
        decoded = _safe_load_json(out_json)
        if isinstance(decoded, dict):
            return {str(k): str(v) for k, v in decoded.items()}
        return {}

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_get_group_nicknames", None)
    if not fn:
        return {}

    out_json = _call_out_json(fn, ctypes.c_int64(int(handle)), cid.encode("utf-8"))
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, dict):
        return {str(k): str(v) for k, v in decoded.items()}
    return {}


def exec_query(handle: int, *, kind: str, path: Optional[str], sql: str) -> list[dict[str, Any]]:
    """Execute raw SQL on a specific db kind/path via WCDB.

    This is primarily used for SNS/other dbs that are not directly exposed by dedicated APIs.
    """
    _ensure_initialized()
    k = str(kind or "").strip()
    if not k:
        raise WCDBRealtimeError("Missing kind for exec_query.")

    s = str(sql or "").strip()
    if not s:
        return []

    p = None if path is None else str(path or "").strip()

    if _sidecar_enabled():
        out_json = _sidecar_payload(
            "exec_query",
            {
                "handle": int(handle),
                "kind": k,
                "path": p,
                "sql": s,
            },
            timeout=60.0,
        )
        decoded = _safe_load_json(out_json)
        if isinstance(decoded, list):
            return [x for x in decoded if isinstance(x, dict)]
        return []

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_exec_query", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support exec_query.")

    out_json = _call_out_json(
        fn,
        ctypes.c_int64(int(handle)),
        k.encode("utf-8"),
        None if p is None else p.encode("utf-8"),
        s.encode("utf-8"),
    )
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, list):
        out: list[dict[str, Any]] = []
        for x in decoded:
            if isinstance(x, dict):
                out.append(x)
        return out
    return []


def update_message(handle: int, *, session_id: str, local_id: int, create_time: int, new_content: str) -> None:
    """Update a single message content in the live encrypted db_storage via WCDB.

    Requires wcdb_update_message export in wcdb_api.dll.
    """
    _ensure_initialized()
    sid = str(session_id or "").strip()
    if not sid:
        raise WCDBRealtimeError("Missing session_id for update_message.")

    if _sidecar_enabled():
        _sidecar_call(
            "update_message",
            {
                "handle": int(handle),
                "session_id": sid,
                "local_id": int(local_id or 0),
                "create_time": int(create_time or 0),
                "new_content": str(new_content or ""),
            },
            timeout=30.0,
        )
        return

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_update_message", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support update_message.")

    _call_out_error(
        fn,
        ctypes.c_int64(int(handle)),
        sid.encode("utf-8"),
        ctypes.c_int64(int(local_id or 0)),
        ctypes.c_int32(int(create_time or 0)),
        str(new_content or "").encode("utf-8"),
    )


def delete_message(
    handle: int,
    *,
    session_id: str,
    local_id: int,
    create_time: int,
    db_path_hint: str | None = None,
) -> None:
    """Delete a single message in the live encrypted db_storage via WCDB.

    Requires wcdb_delete_message export in wcdb_api.dll.
    """
    _ensure_initialized()
    sid = str(session_id or "").strip()
    if not sid:
        raise WCDBRealtimeError("Missing session_id for delete_message.")

    hint = str(db_path_hint or "").strip()
    if _sidecar_enabled():
        _sidecar_call(
            "delete_message",
            {
                "handle": int(handle),
                "session_id": sid,
                "local_id": int(local_id or 0),
                "create_time": int(create_time or 0),
                "db_path_hint": hint,
            },
            timeout=30.0,
        )
        return

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_delete_message", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support delete_message.")

    _call_out_error(
        fn,
        ctypes.c_int64(int(handle)),
        sid.encode("utf-8"),
        ctypes.c_int64(int(local_id or 0)),
        ctypes.c_int32(int(create_time or 0)),
        hint.encode("utf-8"),
    )


def get_sns_timeline(
    handle: int,
    *,
    limit: int = 20,
    offset: int = 0,
    usernames: Optional[list[str]] = None,
    keyword: str | None = None,
    start_time: int = 0,
    end_time: int = 0,
) -> list[dict[str, Any]]:
    """Read Moments (SnsTimeLine) from the live encrypted db_storage via WCDB.

    Requires a newer wcdb_api.dll export: wcdb_get_sns_timeline.
    """
    _ensure_initialized()
    lim = max(0, int(limit or 0))
    off = max(0, int(offset or 0))

    users = [str(u or "").strip() for u in (usernames or []) if str(u or "").strip()]
    users = list(dict.fromkeys(users))
    users_json = json.dumps(users, ensure_ascii=False) if users else ""

    kw = str(keyword or "").strip()

    if _sidecar_enabled():
        payload = _sidecar_payload(
            "get_sns_timeline",
            {
                "handle": int(handle),
                "limit": lim,
                "offset": off,
                "usernames": users,
                "keyword": kw,
                "start_time": int(start_time or 0),
                "end_time": int(end_time or 0),
            },
            timeout=60.0,
        )
        decoded = _safe_load_json(payload)
        if isinstance(decoded, list):
            return [x for x in decoded if isinstance(x, dict)]
        return []

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_get_sns_timeline", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support sns timeline.")

    payload = _call_out_json(
        fn,
        ctypes.c_int64(int(handle)),
        ctypes.c_int32(lim),
        ctypes.c_int32(off),
        users_json.encode("utf-8"),
        kw.encode("utf-8"),
        ctypes.c_int32(int(start_time or 0)),
        ctypes.c_int32(int(end_time or 0)),
    )
    decoded = _safe_load_json(payload)
    if isinstance(decoded, list):
        out: list[dict[str, Any]] = []
        for x in decoded:
            if isinstance(x, dict):
                out.append(x)
        return out
    return []


def decrypt_sns_image(encrypted_data: bytes, key: str) -> bytes:
    """Decrypt Moments CDN image bytes using WCDB DLL (WeFlow compatible).

    Notes:
    - Requires a newer wcdb_api.dll export: wcdb_decrypt_sns_image.
    - On failure, returns the original encrypted_data (best-effort behavior like WeFlow).
    """
    _ensure_initialized()
    raw = bytes(encrypted_data or b"")
    if not raw:
        return b""

    k = str(key or "").strip()
    if not k:
        return raw

    if _sidecar_enabled():
        result = _sidecar_call(
            "decrypt_sns_image",
            {
                "data_b64": base64.b64encode(raw).decode("ascii"),
                "key": k,
            },
            timeout=60.0,
        )
        data_b64 = str(result.get("data_b64") or "")
        if not data_b64:
            return raw
        try:
            return base64.b64decode(data_b64)
        except Exception:
            return raw

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_decrypt_sns_image", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support sns image decryption.")

    out_ptr = ctypes.c_void_p()
    buf = ctypes.create_string_buffer(raw, len(raw))
    rc = 0
    try:
        rc = int(
            fn(
                ctypes.cast(buf, ctypes.c_void_p),
                ctypes.c_int32(len(raw)),
                k.encode("utf-8"),
                ctypes.byref(out_ptr),
            )
        )

        if rc != 0 or not out_ptr.value:
            return raw

        hex_bytes = ctypes.cast(out_ptr, ctypes.c_char_p).value or b""
        if not hex_bytes:
            return raw

        # Defensive: keep only hex chars (some builds may include whitespace).
        hex_clean = re.sub(rb"[^0-9a-fA-F]", b"", hex_bytes)
        if not hex_clean:
            return raw
        try:
            return binascii.unhexlify(hex_clean)
        except Exception:
            return raw
    finally:
        try:
            if out_ptr.value:
                lib.wcdb_free_string(ctypes.cast(out_ptr, ctypes.c_char_p))
        except Exception:
            pass


def shutdown() -> None:
    global _initialized
    if _sidecar_enabled():
        with _lib_lock:
            should_shutdown = bool(_initialized)
        try:
            if should_shutdown:
                _sidecar_call("shutdown", timeout=5.0)
        finally:
            with _lib_lock:
                _initialized = False
            if _auto_sidecar_started_here():
                _stop_auto_sidecar()
        return

    lib = _load_wcdb_lib()
    with _lib_lock:
        if not _initialized:
            return
        try:
            lib.wcdb_shutdown()
        finally:
            _initialized = False
    if _auto_sidecar_started_here():
        _stop_auto_sidecar()


def _resolve_session_db_path(db_storage_dir: Path) -> Path:
    # Prefer current WeChat 4.x naming/layout:
    # - db_storage/session/session.db
    # - (fallback) db_storage/session.db
    candidates = [
        db_storage_dir / "session" / "session.db",
        db_storage_dir / "session.db",
        db_storage_dir / "Session.db",
        db_storage_dir / "MicroMsg.db",
    ]
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return c
        except Exception:
            continue

    # Fallback: recursive search (some installs keep DBs in subfolders).
    try:
        for p in db_storage_dir.rglob("session.db"):
            try:
                if p.exists() and p.is_file():
                    return p
            except Exception:
                continue
    except Exception:
        pass

    try:
        for p in db_storage_dir.rglob("MicroMsg.db"):
            try:
                if p.exists() and p.is_file():
                    return p
            except Exception:
                continue
    except Exception:
        pass

    raise WCDBRealtimeError(f"Cannot find session db in: {db_storage_dir}")


@dataclass(frozen=True)
class WCDBRealtimeConnection:
    account: str
    handle: int
    db_storage_dir: Path
    session_db_path: Path
    connected_at: float
    lock: threading.Lock


class WCDBRealtimeManager:
    _FAILED_TTL = 60.0  # seconds before retrying a failed connection

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._conns: dict[str, WCDBRealtimeConnection] = {}
        self._connecting: dict[str, threading.Event] = {}
        # Negative cache: accounts that failed to connect recently (avoids repeated timeouts).
        self._failed: dict[str, float] = {}  # account -> monotonic timestamp of failure

    def get_status(self, account_dir: Path) -> dict[str, Any]:
        account = str(account_dir.name)
        key_item = get_account_keys_from_store(account)
        key_hex = str((key_item or {}).get("db_key") or "").strip()
        key_ok = len(key_hex) == 64

        db_storage_dir = None
        session_db_path = None
        err = ""
        try:
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            if db_storage_dir is not None:
                session_db_path = _resolve_session_db_path(db_storage_dir)
        except Exception as e:
            err = str(e)

        dll_path = _resolve_wcdb_api_dll_path()
        try:
            dll_ok = bool(dll_path.exists())
        except Exception:
            dll_ok = False
        connected = self.is_connected(account)
        return {
            "account": account,
            "dll_present": bool(dll_ok),
            "wcdb_api_dll": str(dll_path),
            "key_present": bool(key_ok),
            "db_storage_dir": str(db_storage_dir) if db_storage_dir else "",
            "session_db_path": str(session_db_path) if session_db_path else "",
            "connected": bool(connected),
            "error": err,
        }

    def is_connected(self, account: str) -> bool:
        with self._mu:
            conn = self._conns.get(str(account))
            return bool(conn and conn.handle > 0)

    def ensure_connected(
        self, account_dir: Path, *, key_hex: Optional[str] = None, timeout: float = 5.0
    ) -> WCDBRealtimeConnection:
        account = str(account_dir.name)

        # Fast-reject if this account failed recently to avoid repeated timeouts.
        with self._mu:
            failed_at = self._failed.get(account)
            if failed_at is not None and (time.monotonic() - failed_at) < self._FAILED_TTL:
                logger.warning("[wcdb] recent failure cache hit account=%s ttl=%ss", account, int(self._FAILED_TTL))
                raise WCDBRealtimeError("WCDB connection recently failed; retry after 60s.")

        deadline = time.monotonic() + timeout

        while True:
            with self._mu:
                existing = self._conns.get(account)
                if existing is not None and existing.handle > 0:
                    return existing

                waiter = self._connecting.get(account)
                if waiter is None:
                    waiter = threading.Event()
                    self._connecting[account] = waiter
                    break

            # Another thread is connecting; wait a bit and retry.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WCDBRealtimeError("Timed out waiting for WCDB connection.")
            waiter.wait(timeout=min(remaining, 10.0))
            if time.monotonic() >= deadline:
                raise WCDBRealtimeError("Timed out waiting for WCDB connection.")

        key = str(key_hex or "").strip()
        if not key:
            key_item = get_account_keys_from_store(account)
            key = str((key_item or {}).get("db_key") or "").strip()

        try:
            if len(key) != 64:
                with self._mu:
                    self._failed[account] = time.monotonic()
                logger.warning("[wcdb] missing/invalid db key account=%s key_len=%s", account, len(key))
                raise WCDBRealtimeError("Missing db key for this account (call /api/keys or decrypt first).")
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            if db_storage_dir is None:
                logger.warning("[wcdb] db_storage resolve failed account=%s account_dir=%s", account, account_dir)
                raise WCDBRealtimeError("Cannot resolve db_storage directory for this account.")

            session_db_path = _resolve_session_db_path(db_storage_dir)

            # Run open_account in a daemon thread with a timeout to avoid
            # blocking indefinitely when the native library hangs (locked DB).
            _handle_box: list[int] = []
            _open_err: list[Exception] = []

            def _do_open() -> None:
                try:
                    _handle_box.append(open_account(session_db_path, key))
                except Exception as exc:
                    _open_err.append(exc)

            remaining = max(0.1, deadline - time.monotonic())
            open_thread = threading.Thread(target=_do_open, daemon=True)
            open_thread.start()
            open_thread.join(timeout=remaining)

            if open_thread.is_alive():
                with self._mu:
                    self._failed[account] = time.monotonic()
                logger.warning(
                    "[wcdb] open_account timeout account=%s timeout=%ss session_db=%s",
                    account,
                    int(timeout),
                    session_db_path,
                )
                raise WCDBRealtimeError(
                    f"open_account timed out after {timeout:.0f}s for {session_db_path}"
                )
            if _open_err:
                with self._mu:
                    self._failed[account] = time.monotonic()
                logger.warning(
                    "[wcdb] open_account failed account=%s session_db=%s error=%s",
                    account,
                    session_db_path,
                    _open_err[0],
                )
                raise _open_err[0]
            if not _handle_box:
                logger.warning("[wcdb] open_account returned no handle account=%s session_db=%s", account, session_db_path)
                raise WCDBRealtimeError("open_account returned no handle.")

            handle = _handle_box[0]
            # Some WCDB APIs (e.g. exec_query on non-session DBs) may require this context.
            try:
                set_my_wxid(handle, account)
            except Exception:
                pass

            conn = WCDBRealtimeConnection(
                account=account,
                handle=handle,
                db_storage_dir=db_storage_dir,
                session_db_path=session_db_path,
                connected_at=time.time(),
                lock=threading.Lock(),
            )

            with self._mu:
                self._conns[account] = conn
                self._failed.pop(account, None)
            logger.info("[wcdb] connected account=%s handle=%s session_db=%s", account, int(handle), session_db_path)
            return conn
        finally:
            with self._mu:
                ev = self._connecting.pop(account, None)
                if ev is not None:
                    ev.set()

    def disconnect(self, account: str) -> None:
        a = str(account or "").strip()
        if not a:
            return
        with self._mu:
            conn = self._conns.pop(a, None)
            self._failed.pop(a, None)  # clear negative cache on explicit disconnect
        if conn is None:
            return
        try:
            with conn.lock:
                close_account(conn.handle)
        except Exception:
            pass

    def close_all(self, *, lock_timeout_s: float | None = None) -> bool:
        """Close all known WCDB realtime connections.

        When `lock_timeout_s` is None, this waits indefinitely for per-connection locks.
        When provided, this will skip busy connections after the timeout and return False.
        """
        with self._mu:
            conns = list(self._conns.values())
            self._conns.clear()
        ok = True
        for conn in conns:
            try:
                if lock_timeout_s is None:
                    with conn.lock:
                        close_account(conn.handle)
                    continue

                acquired = conn.lock.acquire(timeout=float(lock_timeout_s))
                if not acquired:
                    ok = False
                    logger.warning("[wcdb] close_all skip busy conn account=%s", conn.account)
                    continue
                try:
                    close_account(conn.handle)
                finally:
                    conn.lock.release()
            except Exception:
                ok = False
                continue
        return ok


WCDB_REALTIME = WCDBRealtimeManager()
