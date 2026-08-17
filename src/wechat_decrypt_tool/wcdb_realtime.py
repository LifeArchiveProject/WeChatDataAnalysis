from __future__ import annotations

import re
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypeVar

from . import native_core_realtime
from .key_store import get_account_keys_from_store
from .logging_config import get_logger
from .media_helpers import _resolve_account_db_storage_dir
from .native_core_broker import resolve_native_core_broker, stop_native_core_broker
from .native_core_client import native_core_mode, resolve_native_core_library


logger = get_logger(__name__)
_T = TypeVar("_T")


class WCDBRealtimeError(RuntimeError):
    pass


def _native_call(
    operation: str,
    function: Callable[..., _T],
    /,
    *args: Any,
    **kwargs: Any,
) -> _T:
    try:
        return function(*args, **kwargs)
    except WCDBRealtimeError:
        raise
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise WCDBRealtimeError(f"Native core {operation} failed: {detail}") from exc


def _normalize_native_account_name(dir_name: str) -> str:
    trimmed = str(dir_name or "").strip()
    if not trimmed:
        return trimmed

    # WeFlow appends a four-hex collision suffix to its output directory.
    # Strip only that final segment; a native wxid may contain underscores.
    # Requiring another segment before the suffix keeps values such as
    # ``wxid_dead`` intact while normalizing ``wxid_real_user_a73c``.
    if trimmed.lower().startswith("wxid_"):
        suffix_match = re.match(r"^(wxid_.+)_([0-9a-fA-F]{4})$", trimmed, flags=re.IGNORECASE)
        return suffix_match.group(1) if suffix_match else trimmed

    suffix_match = re.match(r"^(.+)_([0-9a-fA-F]{4})$", trimmed)
    return suffix_match.group(1) if suffix_match else trimmed


def _derive_native_wxid(account: str, db_storage_dir: Optional[Path] = None) -> str:
    candidates: list[str] = []
    if db_storage_dir is not None:
        try:
            parent_name = Path(db_storage_dir).parent.name
            if parent_name:
                candidates.append(parent_name)
        except Exception:
            pass
    candidates.append(str(account or ""))

    for candidate in candidates:
        normalized = _normalize_native_account_name(candidate)
        if normalized:
            return normalized
    return str(account or "").strip()


def _native_core_mode_value() -> str:
    return native_core_mode().value


def _is_native_core_handle(handle: int) -> bool:
    return native_core_realtime.is_native_core_handle(handle)


def _infer_db_storage_dir(session_db_path: Path) -> Path:
    session_path = Path(session_db_path).expanduser().resolve(strict=True)
    for parent in session_path.parents:
        if parent.name.lower() == "db_storage":
            return parent
    if session_path.parent.name.lower() == "session":
        return session_path.parent.parent
    return session_path.parent


def open_account(
    session_db_path: Path,
    key_hex: str,
    *,
    timeout: float = 30.0,
    account: str | None = None,
    native_wxid: str | None = None,
    db_storage_dir: Path | None = None,
) -> int:
    del timeout
    session_path = Path(session_db_path).expanduser().resolve(strict=True)
    storage = (
        Path(db_storage_dir).expanduser().resolve(strict=True)
        if db_storage_dir is not None
        else _infer_db_storage_dir(session_path)
    )
    account_name = str(account or storage.parent.name).strip()
    wxid = str(native_wxid or _derive_native_wxid(account_name, storage)).strip()
    return _native_call(
        "open account",
        native_core_realtime.open_account,
        account=account_name,
        native_wxid=wxid,
        db_storage_dir=storage,
        session_db_path=session_path,
        key_hex=str(key_hex or "").strip(),
    )


def close_account(handle: int) -> None:
    native_core_realtime.close_account(handle)


def get_sessions(handle: int) -> list[dict[str, Any]]:
    return _native_call("get sessions", native_core_realtime.get_sessions, handle)


def get_messages(
    handle: int,
    username: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return _native_call(
        "get messages",
        native_core_realtime.get_messages,
        handle,
        username,
        limit=limit,
        offset=offset,
    )


def get_message_count(handle: int, username: str) -> int:
    return _native_call(
        "get message count", native_core_realtime.get_message_count, handle, username
    )


def get_display_names(handle: int, usernames: list[str]) -> dict[str, str]:
    return _native_call(
        "get display names", native_core_realtime.get_display_names, handle, usernames
    )


def get_avatar_urls(handle: int, usernames: list[str]) -> dict[str, str]:
    return _native_call(
        "get avatar URLs", native_core_realtime.get_avatar_urls, handle, usernames
    )


def get_contact(handle: int, username: str) -> dict[str, Any]:
    return _native_call("get contact", native_core_realtime.get_contact, handle, username)


def get_contacts_compact(
    handle: int, usernames: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    return _native_call(
        "get contacts", native_core_realtime.get_contacts_compact, handle, usernames
    )


def get_group_members(handle: int, chatroom_id: str) -> list[dict[str, Any]]:
    return _native_call(
        "get group members",
        native_core_realtime.get_group_members,
        handle,
        chatroom_id,
    )


def get_group_nicknames(handle: int, chatroom_id: str) -> dict[str, str]:
    return _native_call(
        "get group nicknames",
        native_core_realtime.get_group_nicknames,
        handle,
        chatroom_id,
    )


def exec_query(
    handle: int,
    *,
    kind: str,
    path: Optional[str],
    sql: str,
) -> list[dict[str, Any]]:
    return _native_call(
        "execute query",
        native_core_realtime.exec_query,
        handle,
        kind=kind,
        path=path,
        sql=sql,
    )


def open_message_cursor(
    handle: int,
    session_id: str,
    *,
    batch_size: int,
    ascending: bool = False,
    begin_timestamp: int = 0,
    end_timestamp: int = 0,
    lite: bool = False,
) -> int:
    del lite
    return _native_call(
        "open message cursor",
        native_core_realtime.open_message_cursor,
        handle,
        session_id,
        batch_size=batch_size,
        ascending=ascending,
        begin_timestamp=begin_timestamp,
        end_timestamp=end_timestamp,
    )


def fetch_message_batch(
    handle: int, cursor: int
) -> tuple[list[dict[str, Any]], bool]:
    return _native_call(
        "fetch message batch",
        native_core_realtime.fetch_message_batch,
        handle,
        cursor,
    )


def close_message_cursor(handle: int, cursor: int) -> None:
    _native_call(
        "close message cursor",
        native_core_realtime.close_message_cursor,
        handle,
        cursor,
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
    return _native_call(
        "get SNS timeline",
        native_core_realtime.get_sns_timeline,
        handle,
        limit=limit,
        offset=offset,
        usernames=usernames,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
    )


def decrypt_sns_image(encrypted_data: bytes, key: str) -> bytes:
    return _native_call(
        "decrypt SNS image",
        native_core_realtime.decrypt_sns_image,
        encrypted_data,
        key,
    )


def _resolve_session_db_path(db_storage_dir: Path) -> Path:
    root = Path(db_storage_dir)
    candidates = (
        root / "session" / "session.db",
        root / "session.db",
        root / "Session.db",
        root / "MicroMsg.db",
    )
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue

    for name in ("session.db", "MicroMsg.db"):
        try:
            for candidate in root.rglob(name):
                try:
                    if candidate.is_file():
                        return candidate
                except OSError:
                    continue
        except OSError:
            continue
    raise WCDBRealtimeError(f"Cannot find session db in: {root}")


@dataclass(frozen=True)
class WCDBRealtimeConnection:
    account: str
    native_wxid: str
    handle: int
    db_storage_dir: Path
    session_db_path: Path
    connected_at: float
    lock: threading.Lock


def resolve_account_native_wxid(
    account_dir: Path,
    connection: Any | None = None,
) -> str:
    """Resolve the native WeChat username behind a possibly suffixed account directory."""
    if isinstance(connection, Mapping):
        native_value = connection.get("native_wxid") or connection.get("nativeWxid")
        db_storage_dir = connection.get("db_storage_dir") or connection.get("dbStorageDir")
    else:
        native_value = getattr(connection, "native_wxid", "")
        db_storage_dir = getattr(connection, "db_storage_dir", None)

    native_wxid = str(native_value or "").strip()
    if native_wxid:
        return native_wxid

    account_path = Path(account_dir)
    if db_storage_dir is None:
        try:
            db_storage_dir = _resolve_account_db_storage_dir(account_path)
        except Exception:
            db_storage_dir = None
    try:
        storage_path = Path(db_storage_dir) if db_storage_dir is not None else None
    except Exception:
        storage_path = None
    return _derive_native_wxid(account_path.name, storage_path)


class WCDBRealtimeManager:
    _FAILED_TTL = 60.0

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._conns: dict[str, WCDBRealtimeConnection] = {}
        self._connecting: dict[str, threading.Event] = {}
        self._connecting_roots: dict[str, threading.Event] = {}
        self._failed: dict[str, tuple[float, str]] = {}
        self._prime_stop = threading.Event()
        self._prime_thread: threading.Thread | None = None

    @staticmethod
    def _database_root_key(path: Path) -> str:
        resolved = Path(path).expanduser().resolve(strict=False)
        return "root:" + os.path.normcase(str(resolved))

    @staticmethod
    def _unique_connections(
        connections: list[WCDBRealtimeConnection],
    ) -> list[WCDBRealtimeConnection]:
        unique: list[WCDBRealtimeConnection] = []
        seen: set[int] = set()
        for connection in connections:
            identity = id(connection)
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(connection)
        return unique

    def _connection_for_root_locked(
        self, root_key: str
    ) -> WCDBRealtimeConnection | None:
        for connection in self._unique_connections(list(self._conns.values())):
            if self._database_root_key(connection.db_storage_dir) != root_key:
                continue
            if connection.handle > 0 and _is_native_core_handle(connection.handle):
                return connection
            for alias, cached in tuple(self._conns.items()):
                if cached is connection:
                    self._conns.pop(alias, None)
        return None

    def _recent_failure_locked(self, account: str) -> dict[str, Any]:
        cached = self._failed.get(str(account or ""))
        if cached is None:
            return {"active": False, "reason": "", "retry_after_seconds": 0}
        if isinstance(cached, tuple):
            failed_at, reason = float(cached[0]), str(cached[1] or "").strip()
        else:
            failed_at = float(cached)
            reason = "Native-core realtime connection failed."
        remaining = self._FAILED_TTL - (time.monotonic() - failed_at)
        if remaining <= 0:
            self._failed.pop(str(account or ""), None)
            return {"active": False, "reason": "", "retry_after_seconds": 0}
        return {
            "active": True,
            "reason": reason,
            "retry_after_seconds": max(1, int(remaining + 0.999)),
        }

    def get_recent_failure(self, account: str) -> dict[str, Any]:
        with self._mu:
            return dict(self._recent_failure_locked(str(account or "")))

    def _record_failure(self, account: str, reason: Any) -> None:
        with self._mu:
            self._failed[str(account or "")] = (
                time.monotonic(),
                str(reason or "").strip(),
            )

    def get_connection(self, account: str) -> WCDBRealtimeConnection | None:
        name = str(account or "").strip()
        with self._mu:
            connection = self._conns.get(name)
            if connection is None:
                return None
            if connection.handle > 0 and _is_native_core_handle(connection.handle):
                return connection
            for alias, cached in tuple(self._conns.items()):
                if cached is connection:
                    self._conns.pop(alias, None)
            return None

    def is_connected(self, account: str) -> bool:
        return self.get_connection(account) is not None

    def get_status(self, account_dir: Path) -> dict[str, Any]:
        account_path = Path(account_dir)
        account = str(account_path.name)
        key_item = get_account_keys_from_store(account)
        key_hex = str((key_item or {}).get("db_key") or "").strip()

        db_storage_dir: Path | None = None
        session_db_path: Path | None = None
        native_wxid = ""
        errors: list[str] = []
        try:
            db_storage_dir = _resolve_account_db_storage_dir(account_path)
            if db_storage_dir is not None:
                native_wxid = _derive_native_wxid(account, db_storage_dir)
                session_db_path = _resolve_session_db_path(db_storage_dir)
        except Exception as exc:
            errors.append(str(exc))
            native_wxid = _derive_native_wxid(account, db_storage_dir)

        try:
            client_path = resolve_native_core_library()
            broker_path = resolve_native_core_broker()
        except Exception as exc:
            errors.append(str(exc))
            native_dir = Path(__file__).resolve().parent / "native"
            if sys.platform.startswith("win"):
                client_path = native_dir / "wechatdb_client.dll"
                broker_path = native_dir / "wechatdb_broker.exe"
            else:
                client_path = native_dir / "libwechatdb_client.dylib"
                broker_path = native_dir / "wechatdb_broker"
        manifest_path = client_path.with_name("wechatdb_native_build.json")
        components_present = all(
            path.is_file() for path in (client_path, broker_path, manifest_path)
        )
        recent_failure = self.get_recent_failure(account)
        return {
            "account": account,
            "dll_present": components_present,
            "wcdb_api_dll": str(client_path),
            "native_core": True,
            "native_core_mode": _native_core_mode_value(),
            "native_core_client": str(client_path),
            "native_core_broker": str(broker_path),
            "native_core_manifest": str(manifest_path),
            "key_present": bool(re.fullmatch(r"[0-9a-fA-F]{64}", key_hex)),
            "native_wxid": native_wxid,
            "db_storage_dir": str(db_storage_dir) if db_storage_dir else "",
            "session_db_path": str(session_db_path) if session_db_path else "",
            "connected": self.is_connected(account),
            "error": "; ".join(error for error in errors if error),
            "recent_failure": bool(recent_failure.get("active")),
            "failure_reason": str(recent_failure.get("reason") or ""),
            "retry_after_seconds": int(
                recent_failure.get("retry_after_seconds") or 0
            ),
        }

    def invalidate_runtime(self, *, reason: str = "") -> None:
        with self._mu:
            connections = self._unique_connections(list(self._conns.values()))
            waiters = list(
                {
                    id(waiter): waiter
                    for waiter in (
                        *self._connecting.values(),
                        *self._connecting_roots.values(),
                    )
                }.values()
            )
            self._conns.clear()
            self._connecting.clear()
            self._connecting_roots.clear()
            self._failed.clear()
        for connection in connections:
            try:
                close_account(connection.handle)
            except Exception:
                pass
        native_core_realtime.close_all()
        for waiter in waiters:
            waiter.set()
        logger.warning(
            "[native-core] invalidated cached handles connections=%s reason=%s",
            len(connections),
            str(reason or "runtime unavailable")[:500],
        )

    def ensure_connected(
        self,
        account_dir: Path,
        *,
        key_hex: Optional[str] = None,
        timeout: float = 5.0,
    ) -> WCDBRealtimeConnection:
        account_path = Path(account_dir)
        account = str(account_path.name)
        deadline = time.monotonic() + max(0.0, float(timeout))

        db_storage_dir = _resolve_account_db_storage_dir(account_path)
        if db_storage_dir is None:
            raise WCDBRealtimeError(
                "Cannot resolve db_storage directory for this account."
            )
        db_storage_dir = Path(db_storage_dir).expanduser().resolve(strict=True)
        root_key = self._database_root_key(db_storage_dir)
        session_db_path = _resolve_session_db_path(db_storage_dir)
        native_wxid = _derive_native_wxid(account, db_storage_dir)
        _native_core_mode_value()

        while True:
            with self._mu:
                recent_failure = self._recent_failure_locked(account)
                root_failure = self._recent_failure_locked(root_key)
                if not recent_failure.get("active") and root_failure.get("active"):
                    recent_failure = root_failure
                if recent_failure.get("active"):
                    retry_after = int(
                        recent_failure.get("retry_after_seconds") or self._FAILED_TTL
                    )
                    original_reason = str(recent_failure.get("reason") or "").strip()
                    message = (
                        f"WCDB connection recently failed; retry after {retry_after}s."
                    )
                    if original_reason:
                        message += f" Last error: {original_reason}"
                    raise WCDBRealtimeError(message)

                existing = self._conns.get(account)
                if existing is not None:
                    if existing.handle > 0 and _is_native_core_handle(existing.handle):
                        return existing
                    self._conns.pop(account, None)

                existing = self._connection_for_root_locked(root_key)
                if existing is not None:
                    self._conns[account] = existing
                    self._failed.pop(account, None)
                    return existing

                waiter = self._connecting_roots.get(root_key)
                if waiter is None:
                    waiter = threading.Event()
                    self._connecting[account] = waiter
                    self._connecting_roots[root_key] = waiter
                    break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WCDBRealtimeError("Timed out waiting for native-core connection.")
            waiter.wait(timeout=min(remaining, 10.0))

        cache_failure = False
        try:
            key = str(key_hex or "").strip()
            if not key:
                key_item = get_account_keys_from_store(account)
                key = str((key_item or {}).get("db_key") or "").strip()
            if not re.fullmatch(r"[0-9a-fA-F]{64}", key):
                raise WCDBRealtimeError(
                    "Missing db key for this account (call /api/keys or decrypt first)."
                )

            cache_failure = True
            handle = _native_call(
                "open account",
                native_core_realtime.open_account,
                account=account,
                native_wxid=native_wxid,
                db_storage_dir=db_storage_dir,
                session_db_path=session_db_path,
                key_hex=key,
            )
            connection = WCDBRealtimeConnection(
                account=account,
                native_wxid=native_wxid,
                handle=handle,
                db_storage_dir=db_storage_dir,
                session_db_path=session_db_path,
                connected_at=time.time(),
                lock=threading.Lock(),
            )
            with self._mu:
                self._conns[account] = connection
                self._failed.pop(account, None)
            logger.info(
                "[native-core] connected account=%s native_wxid=%s handle=%s session_db=%s",
                account,
                native_wxid,
                int(handle),
                session_db_path,
            )
            return connection
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, WCDBRealtimeError)
                else WCDBRealtimeError(str(exc).strip() or exc.__class__.__name__)
            )
            if cache_failure:
                self._record_failure(account, error)
                self._record_failure(root_key, error)
            if error is exc:
                raise
            raise error from exc
        finally:
            with self._mu:
                event = self._connecting.pop(account, None)
                if self._connecting_roots.get(root_key) is event:
                    self._connecting_roots.pop(root_key, None)
                if event is not None:
                    event.set()

    def disconnect(self, account: str) -> None:
        name = str(account or "").strip()
        if not name:
            return
        with self._mu:
            connection = self._conns.pop(name, None)
            self._failed.pop(name, None)
            if connection is not None:
                root_key = self._database_root_key(connection.db_storage_dir)
                self._failed.pop(root_key, None)
                for alias, cached in tuple(self._conns.items()):
                    if cached is connection:
                        self._conns.pop(alias, None)
        if connection is None:
            return
        try:
            with connection.lock:
                close_account(connection.handle)
        except Exception:
            pass

    def close_all(self, *, lock_timeout_s: float | None = None) -> bool:
        with self._mu:
            connections = self._unique_connections(list(self._conns.values()))
            waiters = list(
                {
                    id(waiter): waiter
                    for waiter in (
                        *self._connecting.values(),
                        *self._connecting_roots.values(),
                    )
                }.values()
            )
            self._conns.clear()
            self._connecting.clear()
            self._connecting_roots.clear()
            self._failed.clear()
        for waiter in waiters:
            waiter.set()

        ok = True
        for connection in connections:
            acquired = False
            try:
                if lock_timeout_s is None:
                    connection.lock.acquire()
                    acquired = True
                else:
                    acquired = connection.lock.acquire(timeout=float(lock_timeout_s))
                if not acquired:
                    ok = False
                    with self._mu:
                        self._conns.setdefault(connection.account, connection)
                    continue
                close_account(connection.handle)
            except Exception:
                ok = False
            finally:
                if acquired:
                    connection.lock.release()
        return ok

    def _prime_available_accounts_once(self) -> None:
        from .chat_accounts import list_chat_account_contexts

        for context in list_chat_account_contexts():
            if self._prime_stop.is_set():
                return
            if context.mode != "direct" or not context.db_key_present:
                continue
            started = time.perf_counter()
            try:
                self.ensure_connected(context.account_dir, timeout=30.0)
            except Exception as exc:
                logger.warning(
                    "[native-core] background account preparation failed account=%s error=%s",
                    context.name,
                    str(exc).strip() or exc.__class__.__name__,
                )
                continue
            logger.info(
                "[native-core] background account prepared account=%s elapsed_ms=%.1f",
                context.name,
                (time.perf_counter() - started) * 1000.0,
            )

    def start_background_prime(self) -> None:
        enabled = str(
            os.environ.get("WECHAT_TOOL_NATIVE_CORE_BACKGROUND_PRIME", "1") or ""
        ).strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return
        with self._mu:
            if self._prime_thread is not None and self._prime_thread.is_alive():
                return
            self._prime_stop.clear()
            thread = threading.Thread(
                target=self._prime_available_accounts_once,
                name="native-core-account-prime",
                daemon=True,
            )
            self._prime_thread = thread
            thread.start()

    def stop_background_prime(self, *, timeout: float = 5.0) -> bool:
        with self._mu:
            thread = self._prime_thread
        if thread is None:
            return True
        self._prime_stop.set()
        if thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        stopped = not thread.is_alive()
        if stopped:
            with self._mu:
                if self._prime_thread is thread:
                    self._prime_thread = None
        return stopped


WCDB_REALTIME = WCDBRealtimeManager()


def shutdown() -> None:
    WCDB_REALTIME.stop_background_prime()
    WCDB_REALTIME.close_all()
    native_core_realtime.close_all()
    try:
        stop_native_core_broker()
    except Exception:
        pass


__all__ = [
    "WCDB_REALTIME",
    "WCDBRealtimeConnection",
    "WCDBRealtimeError",
    "WCDBRealtimeManager",
    "close_account",
    "close_message_cursor",
    "decrypt_sns_image",
    "exec_query",
    "fetch_message_batch",
    "get_avatar_urls",
    "get_contact",
    "get_contacts_compact",
    "get_display_names",
    "get_group_members",
    "get_group_nicknames",
    "get_message_count",
    "get_messages",
    "get_sessions",
    "get_sns_timeline",
    "open_account",
    "open_message_cursor",
    "resolve_account_native_wxid",
    "shutdown",
]
