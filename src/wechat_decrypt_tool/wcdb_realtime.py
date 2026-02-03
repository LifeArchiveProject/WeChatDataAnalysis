import ctypes
import json
import os
import sys
import threading
import time
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
_WCDB_API_DLL = _NATIVE_DIR / "wcdb_api.dll"

_lib_lock = threading.Lock()
_lib: Optional[ctypes.CDLL] = None
_initialized = False


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _load_wcdb_lib() -> ctypes.CDLL:
    global _lib
    with _lib_lock:
        if _lib is not None:
            return _lib

        if not _is_windows():
            raise WCDBRealtimeError("WCDB realtime mode is only supported on Windows.")

        if not _WCDB_API_DLL.exists():
            raise WCDBRealtimeError(f"Missing wcdb_api.dll at: {_WCDB_API_DLL}")

        # Ensure dependent DLLs (e.g. WCDB.dll) can be found.
        try:
            os.add_dll_directory(str(_NATIVE_DIR))
        except Exception:
            pass

        lib = ctypes.CDLL(str(_WCDB_API_DLL))

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

        lib.wcdb_get_logs.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        lib.wcdb_get_logs.restype = ctypes.c_int

        lib.wcdb_free_string.argtypes = [ctypes.c_char_p]
        lib.wcdb_free_string.restype = None

        _lib = lib
        return lib


def _ensure_initialized() -> None:
    global _initialized
    lib = _load_wcdb_lib()
    with _lib_lock:
        if _initialized:
            return
        rc = int(lib.wcdb_init())
        if rc != 0:
            raise WCDBRealtimeError(f"wcdb_init failed: {rc}")
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


def get_native_logs() -> list[str]:
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

    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_set_my_wxid", None)
    if not fn:
        return False

    w = str(wxid or "").strip()
    if not w:
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
    lib = _load_wcdb_lib()
    try:
        lib.wcdb_close_account(ctypes.c_int64(h))
    except Exception:
        return


def get_sessions(handle: int) -> list[dict[str, Any]]:
    _ensure_initialized()
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
    lib = _load_wcdb_lib()
    u = str(username or "").strip()
    if not u:
        return []
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
    lib = _load_wcdb_lib()
    u = str(username or "").strip()
    if not u:
        return 0
    out_count = ctypes.c_int32(0)
    rc = int(lib.wcdb_get_message_count(ctypes.c_int64(int(handle)), u.encode("utf-8"), ctypes.byref(out_count)))
    if rc != 0:
        return 0
    return int(out_count.value)


def get_display_names(handle: int, usernames: list[str]) -> dict[str, str]:
    _ensure_initialized()
    lib = _load_wcdb_lib()
    uniq = [str(u or "").strip() for u in usernames if str(u or "").strip()]
    uniq = list(dict.fromkeys(uniq))
    if not uniq:
        return {}
    payload = json.dumps(uniq, ensure_ascii=False).encode("utf-8")
    out_json = _call_out_json(lib.wcdb_get_display_names, ctypes.c_int64(int(handle)), payload)
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, dict):
        return {str(k): str(v) for k, v in decoded.items()}
    return {}


def get_avatar_urls(handle: int, usernames: list[str]) -> dict[str, str]:
    _ensure_initialized()
    lib = _load_wcdb_lib()
    uniq = [str(u or "").strip() for u in usernames if str(u or "").strip()]
    uniq = list(dict.fromkeys(uniq))
    if not uniq:
        return {}
    payload = json.dumps(uniq, ensure_ascii=False).encode("utf-8")
    out_json = _call_out_json(lib.wcdb_get_avatar_urls, ctypes.c_int64(int(handle)), payload)
    decoded = _safe_load_json(out_json)
    if isinstance(decoded, dict):
        return {str(k): str(v) for k, v in decoded.items()}
    return {}


def exec_query(handle: int, *, kind: str, path: Optional[str], sql: str) -> list[dict[str, Any]]:
    """Execute raw SQL on a specific db kind/path via WCDB.

    This is primarily used for SNS/other dbs that are not directly exposed by dedicated APIs.
    """
    _ensure_initialized()
    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_exec_query", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support exec_query.")

    k = str(kind or "").strip()
    if not k:
        raise WCDBRealtimeError("Missing kind for exec_query.")

    s = str(sql or "").strip()
    if not s:
        return []

    p = None if path is None else str(path or "").strip()

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
    lib = _load_wcdb_lib()
    fn = getattr(lib, "wcdb_get_sns_timeline", None)
    if not fn:
        raise WCDBRealtimeError("Current wcdb_api.dll does not support sns timeline.")

    lim = max(0, int(limit or 0))
    off = max(0, int(offset or 0))

    users = [str(u or "").strip() for u in (usernames or []) if str(u or "").strip()]
    users = list(dict.fromkeys(users))
    users_json = json.dumps(users, ensure_ascii=False) if users else ""

    kw = str(keyword or "").strip()

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


def shutdown() -> None:
    global _initialized
    lib = _load_wcdb_lib()
    with _lib_lock:
        if not _initialized:
            return
        try:
            lib.wcdb_shutdown()
        finally:
            _initialized = False


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
    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._conns: dict[str, WCDBRealtimeConnection] = {}
        self._connecting: dict[str, threading.Event] = {}

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

        dll_ok = _WCDB_API_DLL.exists()
        connected = self.is_connected(account)
        return {
            "account": account,
            "dll_present": bool(dll_ok),
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

    def ensure_connected(self, account_dir: Path, *, key_hex: Optional[str] = None) -> WCDBRealtimeConnection:
        account = str(account_dir.name)

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
            waiter.wait(timeout=10.0)

        key = str(key_hex or "").strip()
        if not key:
            key_item = get_account_keys_from_store(account)
            key = str((key_item or {}).get("db_key") or "").strip()
        if len(key) != 64:
            raise WCDBRealtimeError("Missing db key for this account (call /api/keys or decrypt first).")

        try:
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            if db_storage_dir is None:
                raise WCDBRealtimeError("Cannot resolve db_storage directory for this account.")

            session_db_path = _resolve_session_db_path(db_storage_dir)
            handle = open_account(session_db_path, key)
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
            logger.info(f"[wcdb] connected account={account} session_db={session_db_path}")
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
