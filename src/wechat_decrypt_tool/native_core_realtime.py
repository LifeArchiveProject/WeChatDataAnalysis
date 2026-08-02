from __future__ import annotations

import hashlib
import itertools
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from . import native_core_raw_key_cache
from .logging_config import get_logger
from .native_core_broker import managed_native_core_operation
from .native_core_client import (
    NativeCoreClient,
    NativeCoreDatabase,
    NativeCoreDatabaseAccess,
    NativeCoreDatabaseKeyMode,
    NativeCoreError,
    NativeCoreFeature,
    NativeCorePolicyError,
    NativeCoreStatus,
    NativeCoreUnavailableError,
    get_native_core_client,
)
from .native_core_lease import refresh_native_core_lease
from .native_core_telemetry import record_product_event


logger = get_logger(__name__)


_MAX_QUERY_PAGES = 512
_MAX_QUERY_ROWS = 200_000
_PAGE_ROWS = 2048
_PAGE_BYTES = 768 * 1024
_HANDLE_START = 1 << 60
_CURSOR_START = 1 << 59
_READ_PREFIXES = {"SELECT", "PRAGMA", "EXPLAIN", "WITH"}
_READ_DATABASE_CACHE_LIMIT = 10
_SQLCIPHER_SALT_BYTES = 16
_SQLCIPHER_RAW_KEY_BYTES = 32
_SQLCIPHER_KDF_ITERATIONS = 256_000
_RAW_KEY_DERIVATION_WORKERS = 12
_REFRESHABLE_POLICY_STATUSES = {
    int(NativeCoreStatus.LICENSE_REQUIRED),
    int(NativeCoreStatus.LEASE_EXPIRED),
    int(NativeCoreStatus.FEATURE_DENIED),
}


class NativeCoreRealtimeError(RuntimeError):
    pass


@dataclass
class _DatabaseRawKey:
    salt: bytes
    key: bytearray = field(repr=False)


@dataclass
class _AccountContext:
    handle: int
    account: str
    native_wxid: str
    db_storage_dir: Path
    session_db_path: Path
    key: bytearray = field(repr=False)
    raw_database_keys: dict[str, _DatabaseRawKey] = field(
        default_factory=dict, repr=False
    )
    rejected_raw_database_salts: dict[str, bytes] = field(
        default_factory=dict, repr=False
    )
    raw_database_keys_lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False
    )
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    closed: bool = False

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                _close_cached_read_databases(self.handle)
            finally:
                with self.raw_database_keys_lock:
                    raw_keys = list(self.raw_database_keys.values())
                    self.raw_database_keys.clear()
                    self.rejected_raw_database_salts.clear()
                for raw_key in raw_keys:
                    raw_key.key[:] = b"\0" * len(raw_key.key)
                self.key[:] = b"\0" * len(self.key)


@dataclass
class _MessageCursor:
    cursor: int
    account_handle: int
    username: str
    batch_size: int
    ascending: bool
    begin_timestamp: int
    end_timestamp: int
    tables: tuple[tuple[Path, str], ...]
    last_by_path: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    exhausted: bool = False


@dataclass
class _ReadDatabaseEntry:
    client: NativeCoreClient
    database: NativeCoreDatabase
    generation: int
    borrowers: int = 0
    retired: bool = False
    closed: bool = False


_registry_lock = threading.RLock()
_handles = itertools.count(_HANDLE_START)
_cursors = itertools.count(_CURSOR_START)
_accounts: dict[int, _AccountContext] = {}
_message_cursors: dict[int, _MessageCursor] = {}
_read_database_cache_condition = threading.Condition(threading.RLock())
_read_database_cache: OrderedDict[tuple[int, str], _ReadDatabaseEntry] = OrderedDict()
_read_database_cache_client: NativeCoreClient | None = None
_read_database_cache_generation = 0
_read_database_handle_count = 0
_read_database_pending_opens = 0
_read_database_pending_keys: set[tuple[int, str]] = set()


def _read_database_cache_key(context: _AccountContext, database_path: Path) -> tuple[int, str]:
    return context.handle, os.path.normcase(os.fspath(database_path))


def _close_database_quietly(database: NativeCoreDatabase) -> None:
    try:
        database.close()
    except Exception:
        pass


def _retire_read_database_entry_locked(entry: _ReadDatabaseEntry) -> NativeCoreDatabase | None:
    global _read_database_handle_count
    entry.retired = True
    if entry.borrowers > 0 or entry.closed:
        return None
    entry.closed = True
    _read_database_handle_count -= 1
    if _read_database_handle_count < 0:
        raise RuntimeError("native-core read database cache handle count underflow")
    return entry.database


def _retire_cached_read_databases_locked(
    *,
    account_handle: int | None = None,
    client: NativeCoreClient | None = None,
) -> list[NativeCoreDatabase]:
    stale: list[NativeCoreDatabase] = []
    for key, entry in tuple(_read_database_cache.items()):
        if account_handle is not None and key[0] != int(account_handle):
            continue
        if client is not None and entry.client is not client:
            continue
        _read_database_cache.pop(key, None)
        database = _retire_read_database_entry_locked(entry)
        if database is not None:
            stale.append(database)
    return stale


def _close_cached_read_databases(
    account_handle: int | None = None,
    *,
    client: NativeCoreClient | None = None,
) -> None:
    global _read_database_cache_client, _read_database_cache_generation
    stale: list[NativeCoreDatabase]
    with _read_database_cache_condition:
        invalidate_generation = account_handle is None and (
            client is None or _read_database_cache_client is client
        )
        if invalidate_generation:
            _read_database_cache_generation += 1
        stale = _retire_cached_read_databases_locked(
            account_handle=account_handle,
            client=client,
        )
        if account_handle is None and client is None:
            _read_database_cache_client = None
        _read_database_cache_condition.notify_all()
    for database in stale:
        _close_database_quietly(database)


def _release_read_database_entry(entry: _ReadDatabaseEntry) -> None:
    stale: NativeCoreDatabase | None = None
    with _read_database_cache_condition:
        if entry.borrowers <= 0:
            raise RuntimeError("native-core read database cache borrower count underflow")
        entry.borrowers -= 1
        if entry.retired:
            stale = _retire_read_database_entry_locked(entry)
        _read_database_cache_condition.notify_all()
    if stale is not None:
        _close_database_quietly(stale)


def _acquire_cached_read_database(
    client: NativeCoreClient,
    context: _AccountContext,
    database_path: Path,
) -> _ReadDatabaseEntry:
    global _read_database_cache_client, _read_database_cache_generation
    global _read_database_handle_count, _read_database_pending_opens
    key = _read_database_cache_key(context, database_path)
    while True:
        stale: list[NativeCoreDatabase] = []
        reserved = False
        open_generation = -1
        with _read_database_cache_condition:
            if _read_database_cache_client is not client:
                stale.extend(_retire_cached_read_databases_locked())
                _read_database_cache_client = client
                _read_database_cache_generation += 1

            cached = _read_database_cache.pop(key, None)
            if cached is not None:
                if (
                    cached.client is client
                    and cached.generation == _read_database_cache_generation
                    and not cached.retired
                    and not cached.closed
                    and not cached.database.closed
                ):
                    cached.borrowers += 1
                    _read_database_cache[key] = cached
                    return cached
                database = _retire_read_database_entry_locked(cached)
                if database is not None:
                    stale.append(database)

            if not stale and key in _read_database_pending_keys:
                _read_database_cache_condition.wait()
                continue

            if not stale and (
                _read_database_handle_count + _read_database_pending_opens
                >= _READ_DATABASE_CACHE_LIMIT
            ):
                for oldest_key, oldest in tuple(_read_database_cache.items()):
                    if oldest.borrowers == 0:
                        _read_database_cache.pop(oldest_key, None)
                        database = _retire_read_database_entry_locked(oldest)
                        if database is not None:
                            stale.append(database)
                        break
                if not stale:
                    _read_database_cache_condition.wait()
                    continue

            if not stale:
                _read_database_pending_opens += 1
                _read_database_pending_keys.add(key)
                open_generation = _read_database_cache_generation
                reserved = True

        for database in stale:
            _close_database_quietly(database)
        if not reserved:
            continue

        try:
            database = _open_database(client, context, database_path)
        except BaseException:
            with _read_database_cache_condition:
                _read_database_pending_opens -= 1
                _read_database_pending_keys.discard(key)
                _read_database_cache_condition.notify_all()
            raise

        discard = False
        with _read_database_cache_condition:
            _read_database_pending_opens -= 1
            _read_database_pending_keys.discard(key)
            if (
                _read_database_cache_client is not client
                or _read_database_cache_generation != open_generation
                or context.closed
                or database.closed
            ):
                discard = True
            else:
                entry = _ReadDatabaseEntry(
                    client=client,
                    database=database,
                    generation=open_generation,
                    borrowers=1,
                )
                _read_database_cache[key] = entry
                _read_database_handle_count += 1
            _read_database_cache_condition.notify_all()
        if discard:
            _close_database_quietly(database)
            raise NativeCoreUnavailableError(
                "wechatdb native database generation changed while opening a cached handle."
            )
        return entry


@contextmanager
def _borrow_cached_read_database(
    client: NativeCoreClient,
    context: _AccountContext,
    database_path: Path,
) -> Iterator[NativeCoreDatabase]:
    entry = _acquire_cached_read_database(client, context, database_path)
    try:
        yield entry.database
    finally:
        _release_read_database_entry(entry)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return "X'" + bytes(value).hex() + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + str(value or "").replace('"', '""') + '"'


def _first_sql_keyword(sql: str) -> str:
    remaining = str(sql or "")
    while True:
        remaining = remaining.lstrip()
        if remaining.startswith("--"):
            newline = remaining.find("\n")
            remaining = "" if newline < 0 else remaining[newline + 1 :]
            continue
        if remaining.startswith("/*"):
            end = remaining.find("*/", 2)
            remaining = "" if end < 0 else remaining[end + 2 :]
            continue
        break
    match = re.match(r"[A-Za-z]+", remaining)
    return match.group(0).upper() if match else ""


def _context(handle: int) -> _AccountContext:
    try:
        value = int(handle)
    except Exception as exc:
        raise NativeCoreRealtimeError("Invalid native-core account handle.") from exc
    with _registry_lock:
        context = _accounts.get(value)
    if context is None or context.closed:
        raise NativeCoreRealtimeError("Native-core account handle is closed.")
    return context


def is_native_core_handle(handle: int) -> bool:
    try:
        value = int(handle)
    except Exception:
        return False
    with _registry_lock:
        return value in _accounts


def _canonical_database_path(context: _AccountContext, value: Path | str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise NativeCoreRealtimeError(f"Native-core database does not exist: {value}") from exc
    root = context.db_storage_dir
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise NativeCoreRealtimeError("Native-core database path escaped db_storage.") from exc
    if not relative.parts or not path.is_file():
        raise NativeCoreRealtimeError("Native-core database path is not a file under db_storage.")
    return path


def _default_database_path(context: _AccountContext, kind: str) -> Path:
    normalized = str(kind or "").strip().lower()
    candidates = {
        "contact": ("contact/contact.db", "contact.db"),
        "session": ("session/session.db", "session.db"),
        "media": ("sns/sns.db", "sns.db"),
        "sns": ("sns/sns.db", "sns.db"),
        "favorite": ("favorite/favorite.db", "favorite.db"),
        "general": ("general/general.db", "general.db"),
        "hardlink": ("hardlink/hardlink.db", "hardlink.db"),
    }.get(normalized, ())
    for relative in candidates:
        candidate = context.db_storage_dir / relative
        try:
            if candidate.is_file():
                return _canonical_database_path(context, candidate)
        except OSError:
            continue
    raise NativeCoreRealtimeError(
        f"An explicit database path is required for native-core kind {normalized!r}."
    )


def _raw_database_cache_key(database_path: Path) -> str:
    return native_core_raw_key_cache.database_cache_key(database_path)


def _read_database_salt(database_path: Path) -> bytes | None:
    try:
        with Path(database_path).open("rb", buffering=0) as stream:
            salt = stream.read(_SQLCIPHER_SALT_BYTES)
    except OSError:
        return None
    if len(salt) != _SQLCIPHER_SALT_BYTES or salt == b"SQLite format 3\0":
        return None
    return bytes(salt)


def _derive_database_raw_key(key: bytearray, salt: bytes) -> bytearray:
    return bytearray(
        hashlib.pbkdf2_hmac(
            "sha512",
            key,
            salt,
            _SQLCIPHER_KDF_ITERATIONS,
            dklen=_SQLCIPHER_RAW_KEY_BYTES,
        )
    )


def _prime_database_raw_keys(
    context: _AccountContext,
    database_paths: Iterator[Path] | list[Path] | tuple[Path, ...],
) -> None:
    started = time.perf_counter()
    candidates: list[tuple[str, Path, bytes]] = []
    stale: list[_DatabaseRawKey] = []
    seen: set[str] = set()
    for value in database_paths:
        path = Path(value)
        cache_key = _raw_database_cache_key(path)
        if cache_key in seen:
            continue
        seen.add(cache_key)
        salt = _read_database_salt(path)
        if salt is None:
            continue
        with context.raw_database_keys_lock:
            existing = context.raw_database_keys.get(cache_key)
            if existing is not None and existing.salt == salt:
                continue
            if context.rejected_raw_database_salts.get(cache_key) == salt:
                continue
            if existing is not None:
                context.raw_database_keys.pop(cache_key, None)
                stale.append(existing)
            context.rejected_raw_database_salts.pop(cache_key, None)
        candidates.append((cache_key, path, salt))

    for raw_key in stale:
        raw_key.key[:] = b"\0" * len(raw_key.key)
    if not candidates or context.closed:
        return

    try:
        persisted = native_core_raw_key_cache.load_cached_raw_keys(
            context.db_storage_dir,
            context.key,
            [path for _cache_key, path, _salt in candidates],
        )
    except Exception:
        persisted = {}

    pending: list[tuple[str, Path, bytes]] = []
    cache_hits = 0
    for cache_key, path, salt in candidates:
        entry = persisted.pop(cache_key, None)
        if entry is None or entry.salt != salt or _read_database_salt(path) != salt:
            if entry is not None:
                entry.key[:] = b"\0" * len(entry.key)
            pending.append((cache_key, path, salt))
            continue

        installed = False
        replaced: _DatabaseRawKey | None = None
        with context.raw_database_keys_lock:
            existing = context.raw_database_keys.get(cache_key)
            if not context.closed and (existing is None or existing.salt != salt):
                replaced = existing
                context.raw_database_keys[cache_key] = _DatabaseRawKey(
                    salt=salt,
                    key=entry.key,
                )
                installed = True
        if replaced is not None:
            replaced.key[:] = b"\0" * len(replaced.key)
        if not installed:
            entry.key[:] = b"\0" * len(entry.key)
        else:
            cache_hits += 1

    for entry in persisted.values():
        entry.key[:] = b"\0" * len(entry.key)
    if not pending or context.closed:
        if cache_hits:
            logger.info(
                "[native-core] raw-key preparation cache_hits=%s derived=0 elapsed_ms=%.1f",
                cache_hits,
                (time.perf_counter() - started) * 1000.0,
            )
        return

    def derive(candidate: tuple[str, Path, bytes]) -> tuple[str, Path, bytes, bytearray]:
        cache_key, path, salt = candidate
        return cache_key, path, salt, _derive_database_raw_key(context.key, salt)

    if len(pending) == 1:
        derived = [derive(pending[0])]
    else:
        workers = min(_RAW_KEY_DERIVATION_WORKERS, len(pending))
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="wechatdb-kdf",
        ) as pool:
            futures = [pool.submit(derive, candidate) for candidate in pending]
            derived = []
            first_error: BaseException | None = None
            for future in as_completed(futures):
                try:
                    derived.append(future.result())
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
            if first_error is not None:
                for _cache_key, _path, _salt, raw_key in derived:
                    raw_key[:] = b"\0" * len(raw_key)
                raise first_error

    cache_updates: dict[Path, tuple[bytes, bytes | bytearray]] = {}
    for cache_key, path, salt, raw_key in derived:
        if context.closed or _read_database_salt(path) != salt:
            raw_key[:] = b"\0" * len(raw_key)
            continue
        replaced: _DatabaseRawKey | None = None
        with context.raw_database_keys_lock:
            existing = context.raw_database_keys.get(cache_key)
            if existing is None or existing.salt != salt:
                replaced = existing
                context.raw_database_keys[cache_key] = _DatabaseRawKey(
                    salt=salt,
                    key=raw_key,
                )
                cache_updates[path] = (salt, raw_key)
            else:
                raw_key[:] = b"\0" * len(raw_key)
        if replaced is not None:
            replaced.key[:] = b"\0" * len(replaced.key)

    if cache_updates and not context.closed:
        try:
            native_core_raw_key_cache.merge_cached_raw_keys(
                context.db_storage_dir,
                context.key,
                cache_updates,
            )
        except Exception:
            pass
    logger.info(
        "[native-core] raw-key preparation cache_hits=%s derived=%s elapsed_ms=%.1f",
        cache_hits,
        len(derived),
        (time.perf_counter() - started) * 1000.0,
    )


def _cached_database_raw_key(
    context: _AccountContext, database_path: Path
) -> bytearray | None:
    cache_key = _raw_database_cache_key(database_path)
    salt = _read_database_salt(database_path)
    stale: _DatabaseRawKey | None = None
    with context.raw_database_keys_lock:
        entry = context.raw_database_keys.get(cache_key)
        if entry is not None and entry.salt == salt:
            return entry.key
        if entry is not None:
            stale = context.raw_database_keys.pop(cache_key, None)
    if stale is not None:
        stale.key[:] = b"\0" * len(stale.key)
    return None


def _reject_cached_database_raw_key(
    context: _AccountContext, database_path: Path
) -> None:
    cache_key = _raw_database_cache_key(database_path)
    salt = _read_database_salt(database_path)
    with context.raw_database_keys_lock:
        entry = context.raw_database_keys.pop(cache_key, None)
        if salt is not None:
            context.rejected_raw_database_salts[cache_key] = salt
    if entry is not None:
        entry.key[:] = b"\0" * len(entry.key)
    try:
        native_core_raw_key_cache.remove_cached_raw_key(
            context.db_storage_dir,
            context.key,
            database_path,
        )
    except Exception:
        pass


def _open_database(
    client: NativeCoreClient,
    context: _AccountContext,
    database_path: Path,
    *,
    access: NativeCoreDatabaseAccess = NativeCoreDatabaseAccess.READ_ONLY,
) -> NativeCoreDatabase:
    _prime_database_raw_keys(context, [database_path])
    raw_key = _cached_database_raw_key(context, database_path)
    if raw_key is not None:
        try:
            return client.open_database(
                database_path,
                key=raw_key,
                key_mode=NativeCoreDatabaseKeyMode.RAW,
                access=access,
            )
        except NativeCoreError as exc:
            if int(getattr(exc, "status", 0) or 0) != int(
                NativeCoreStatus.DATABASE
            ):
                raise
            _reject_cached_database_raw_key(context, database_path)
    return client.open_database(
        database_path,
        key=context.key,
        key_mode=NativeCoreDatabaseKeyMode.AUTO,
        access=access,
    )


def _query_once(
    context: _AccountContext,
    database_path: Path,
    sql: str,
) -> list[dict[str, Any]]:
    def read_all(database: NativeCoreDatabase) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with database.open_query(sql) as query:
            for _ in range(_MAX_QUERY_PAGES):
                page = query.fetch(max_rows=_PAGE_ROWS, max_bytes=_PAGE_BYTES)
                records = page.records()
                if len(rows) + len(records) > _MAX_QUERY_ROWS:
                    raise NativeCoreRealtimeError(
                        "Native-core query exceeded the application row limit."
                    )
                rows.extend(dict(record) for record in records)
                if not page.has_more:
                    return rows
        raise NativeCoreRealtimeError("Native-core query exceeded the application page limit.")

    with managed_native_core_operation(database_root=context.db_storage_dir):
        for attempt in range(2):
            client = get_native_core_client()
            try:
                with _borrow_cached_read_database(client, context, database_path) as database:
                    return read_all(database)
            except NativeCoreError as exc:
                stale_handle = isinstance(exc, NativeCoreUnavailableError) or int(
                    getattr(exc, "status", 0) or 0
                ) == int(NativeCoreStatus.NOT_FOUND)
                if not stale_handle or attempt > 0:
                    raise
                _close_cached_read_databases(client=client)
    raise NativeCoreRealtimeError("Native-core query retry loop ended unexpectedly.")


def _query(context: _AccountContext, database_path: Path, sql: str) -> list[dict[str, Any]]:
    with context.lock:
        if context.closed:
            raise NativeCoreRealtimeError("Native-core account handle is closed.")
        try:
            return _query_once(context, database_path, sql)
        except NativeCorePolicyError as policy_error:
            if policy_error.status not in _REFRESHABLE_POLICY_STATUSES:
                raise
            with managed_native_core_operation(database_root=context.db_storage_dir):
                client = get_native_core_client()
                _close_cached_read_databases(client=client)
                refresh_native_core_lease(client, NativeCoreFeature.DATABASE_READ)
            return _query_once(context, database_path, sql)


def _initial_raw_key_database_paths(context: _AccountContext) -> tuple[Path, ...]:
    paths = [context.session_db_path]
    for relative in ("contact/contact.db", "contact.db"):
        candidate = context.db_storage_dir / relative
        if candidate.is_file():
            paths.append(_canonical_database_path(context, candidate))
            break
    paths.extend(_message_database_paths(context, context.native_wxid))
    return tuple(paths)


def prepare_account_raw_key_cache(
    db_storage_dir: Path,
    key_hex: str,
    *,
    account: str = "",
    native_wxid: str = "",
) -> int:
    encoded = str(key_hex or "").strip()
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", encoded):
        raise NativeCoreRealtimeError("A 32-byte database key is required.")
    root = Path(db_storage_dir).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NativeCoreRealtimeError("Invalid native-core account database root.")

    session_path: Path | None = None
    for candidate in (
        root / "session" / "session.db",
        root / "session.db",
        root / "Session.db",
        root / "MicroMsg.db",
    ):
        if candidate.is_file():
            session_path = candidate.resolve(strict=True)
            break
    if session_path is None:
        raise NativeCoreRealtimeError("Cannot find the account session database.")

    context = _AccountContext(
        handle=next(_handles),
        account=str(account or root.parent.name).strip(),
        native_wxid=str(native_wxid or account or root.parent.name).strip(),
        db_storage_dir=root,
        session_db_path=session_path,
        key=bytearray.fromhex(encoded),
    )
    try:
        _prime_database_raw_keys(
            context,
            _initial_raw_key_database_paths(context),
        )
        with context.raw_database_keys_lock:
            return len(context.raw_database_keys)
    finally:
        context.close()


def open_account(
    *,
    account: str,
    native_wxid: str,
    db_storage_dir: Path,
    session_db_path: Path,
    key_hex: str,
) -> int:
    encoded = str(key_hex or "").strip()
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", encoded):
        raise NativeCoreRealtimeError("A 32-byte database key is required.")
    root = Path(db_storage_dir).expanduser().resolve(strict=True)
    session_path = Path(session_db_path).expanduser().resolve(strict=True)
    if not root.is_dir() or root not in session_path.parents or not session_path.is_file():
        raise NativeCoreRealtimeError("Invalid native-core account database root.")

    key = bytearray.fromhex(encoded)
    handle = next(_handles)
    context = _AccountContext(
        handle=handle,
        account=str(account or "").strip(),
        native_wxid=str(native_wxid or "").strip(),
        db_storage_dir=root,
        session_db_path=session_path,
        key=key,
    )
    try:
        _prime_database_raw_keys(
            context,
            _initial_raw_key_database_paths(context),
        )
        probe = _query(context, session_path, "SELECT 1 AS native_core_probe")
        if not probe or int(probe[0].get("native_core_probe") or 0) != 1:
            raise NativeCoreRealtimeError("Native-core session database probe failed.")
        with _registry_lock:
            _accounts[handle] = context
        record_product_event("database_open")
        return handle
    except BaseException:
        context.close()
        raise


def close_account(handle: int) -> None:
    try:
        value = int(handle)
    except Exception:
        return
    with _registry_lock:
        context = _accounts.pop(value, None)
        stale = [key for key, cursor in _message_cursors.items() if cursor.account_handle == value]
        for key in stale:
            _message_cursors.pop(key, None)
    if context is not None:
        context.close()


def close_all() -> None:
    with _registry_lock:
        contexts = list(_accounts.values())
        _accounts.clear()
        _message_cursors.clear()
    for context in contexts:
        context.close()
    _close_cached_read_databases()


def exec_query(
    handle: int,
    *,
    kind: str,
    path: str | None,
    sql: str,
) -> list[dict[str, Any]]:
    context = _context(handle)
    statement = str(sql or "").strip()
    if not statement:
        return []
    database_path = (
        _default_database_path(context, kind)
        if path is None or not str(path).strip()
        else _canonical_database_path(context, path)
    )
    keyword = _first_sql_keyword(statement)
    if keyword in _READ_PREFIXES:
        return _query(context, database_path, statement)
    raise NativeCoreRealtimeError("Native-core raw SQL is read-only.")


def get_sessions(handle: int) -> list[dict[str, Any]]:
    context = _context(handle)
    return _query(
        context,
        context.session_db_path,
        "SELECT * FROM SessionTable ORDER BY sort_timestamp DESC",
    )


def _message_database_paths(context: _AccountContext, username: str) -> tuple[Path, ...]:
    message_dir = context.db_storage_dir / "message"
    try:
        paths = [path for path in message_dir.iterdir() if path.is_file()]
    except OSError:
        return ()
    normal = sorted(
        (path for path in paths if re.fullmatch(r"message(?:_\d+)?\.db", path.name, re.I)),
        key=lambda value: value.name.lower(),
    )
    business = sorted(
        (path for path in paths if re.fullmatch(r"biz_message(?:_\d+)?\.db", path.name, re.I)),
        key=lambda value: value.name.lower(),
    )
    other = sorted(
        (
            path
            for path in paths
            if path.suffix.lower() == ".db"
            and "message" in path.name.lower()
            and path not in normal
            and path not in business
            and path.name.lower() not in {"message_fts.db", "message_resource.db"}
        ),
        key=lambda value: value.name.lower(),
    )
    ordered = business + normal + other if str(username).startswith("gh_") else normal + business + other
    return tuple(_canonical_database_path(context, path) for path in ordered)


def _message_tables(context: _AccountContext, username: str) -> tuple[tuple[Path, str], ...]:
    expected = "Msg_" + hashlib.md5(str(username).encode("utf-8")).hexdigest()
    lookup = (
        "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower("
        + _sql_literal(expected)
        + ") LIMIT 1"
    )
    found: list[tuple[Path, str]] = []
    for path in _message_database_paths(context, username):
        try:
            rows = _query(context, path, lookup)
        except Exception:
            continue
        if rows and str(rows[0].get("name") or "").strip():
            found.append((path, str(rows[0]["name"])))
    return tuple(found)


def _message_select_sql(
    table: str,
    *,
    ascending: bool,
    limit: int,
    begin_timestamp: int = 0,
    end_timestamp: int = 0,
    last: tuple[int, int, int] | None = None,
) -> str:
    direction = "ASC" if ascending else "DESC"
    where: list[str] = []
    if begin_timestamp > 0:
        where.append(f"m.create_time >= {int(begin_timestamp)}")
    if end_timestamp > 0:
        where.append(f"m.create_time <= {int(end_timestamp)}")
    if last is not None:
        create_time, sort_seq, local_id = (int(value) for value in last)
        comparator = ">" if ascending else "<"
        where.append(
            "(m.create_time {cmp} {ct} OR "
            "(m.create_time = {ct} AND COALESCE(m.sort_seq, 0) {cmp} {ss}) OR "
            "(m.create_time = {ct} AND COALESCE(m.sort_seq, 0) = {ss} "
            "AND m.local_id {cmp} {lid}))".format(
                cmp=comparator, ct=create_time, ss=sort_seq, lid=local_id
            )
        )
    suffix = " WHERE " + " AND ".join(where) if where else ""
    quoted = _quote_identifier(table)
    return (
        "SELECT m.local_id, m.server_id, m.local_type, m.sort_seq, "
        "m.real_sender_id, m.create_time, m.message_content, m.compress_content, "
        "m.packed_info_data AS packed_info_data, m.source AS msg_source, "
        "n.user_name AS sender_username "
        f"FROM {quoted} m LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid"
        f"{suffix} ORDER BY m.sort_seq {direction}, m.local_id {direction} "
        f"LIMIT {max(1, int(limit))}"
    )


def _message_rows_for_table(
    context: _AccountContext,
    path: Path,
    table: str,
    **options: Any,
) -> list[dict[str, Any]]:
    statements = [_message_select_sql(table, **options)]
    statements.append(statements[0].replace("m.source AS msg_source", "NULL AS msg_source"))
    statements.append(statements[-1].replace("m.packed_info_data AS packed_info_data", "NULL AS packed_info_data"))
    last_error: Exception | None = None
    for statement in statements:
        try:
            rows = _query(context, path, statement)
            for row in rows:
                row["_db_path"] = str(path)
                row["db_name"] = path.name
                row["table_name"] = table
            return rows
        except Exception as exc:
            last_error = exc
    raise NativeCoreRealtimeError(
        f"Cannot query native-core message table {path.name}/{table}: {last_error}"
    )


def open_message_cursor(
    handle: int,
    username: str,
    *,
    batch_size: int,
    ascending: bool = False,
    begin_timestamp: int = 0,
    end_timestamp: int = 0,
) -> int:
    context = _context(handle)
    user = str(username or "").strip()
    if not user:
        return 0
    tables = _message_tables(context, user)
    cursor_id = next(_cursors)
    state = _MessageCursor(
        cursor=cursor_id,
        account_handle=context.handle,
        username=user,
        batch_size=max(1, min(int(batch_size or 1), 4096)),
        ascending=bool(ascending),
        begin_timestamp=max(0, int(begin_timestamp or 0)),
        end_timestamp=max(0, int(end_timestamp or 0)),
        tables=tables,
    )
    with _registry_lock:
        _message_cursors[cursor_id] = state
    return cursor_id


def fetch_message_batch(handle: int, cursor: int) -> tuple[list[dict[str, Any]], bool]:
    context = _context(handle)
    with _registry_lock:
        state = _message_cursors.get(int(cursor or 0))
    if state is None or state.account_handle != context.handle or state.exhausted:
        return [], False

    candidates: list[dict[str, Any]] = []
    probe = state.batch_size + 1
    for path, table in state.tables:
        key = os.path.normcase(os.fspath(path))
        rows = _message_rows_for_table(
            context,
            path,
            table,
            ascending=state.ascending,
            limit=probe,
            begin_timestamp=state.begin_timestamp,
            end_timestamp=state.end_timestamp,
            last=state.last_by_path.get(key),
        )
        candidates.extend(rows)

    candidates.sort(
        key=lambda row: (
            int(row.get("create_time") or 0),
            int(row.get("sort_seq") or 0),
            int(row.get("local_id") or 0),
            os.path.normcase(str(row.get("_db_path") or "")),
        ),
        reverse=not state.ascending,
    )
    has_more = len(candidates) > state.batch_size
    selected = candidates[: state.batch_size]
    for row in selected:
        path_key = os.path.normcase(str(row.get("_db_path") or ""))
        state.last_by_path[path_key] = (
            int(row.get("create_time") or 0),
            int(row.get("sort_seq") or 0),
            int(row.get("local_id") or 0),
        )
    if not has_more:
        state.exhausted = True
    return selected, has_more


def close_message_cursor(handle: int, cursor: int) -> None:
    context = _context(handle)
    with _registry_lock:
        state = _message_cursors.get(int(cursor or 0))
        if state is not None and state.account_handle == context.handle:
            _message_cursors.pop(state.cursor, None)


def get_messages(
    handle: int,
    username: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    wanted = max(0, int(limit or 0))
    skipped = max(0, int(offset or 0))
    if wanted <= 0:
        return []
    cursor = open_message_cursor(
        handle,
        username,
        batch_size=min(4096, max(1, skipped + wanted)),
    )
    collected: list[dict[str, Any]] = []
    try:
        while len(collected) < skipped + wanted:
            rows, has_more = fetch_message_batch(handle, cursor)
            collected.extend(rows)
            if not has_more:
                break
        return collected[skipped : skipped + wanted]
    finally:
        close_message_cursor(handle, cursor)


def get_message_count(handle: int, username: str) -> int:
    context = _context(handle)
    total = 0
    for path, table in _message_tables(context, str(username or "").strip()):
        rows = _query(
            context,
            path,
            f"SELECT COUNT(*) AS message_count FROM {_quote_identifier(table)}",
        )
        if rows:
            total += int(rows[0].get("message_count") or 0)
    return total


def _contact_rows(context: _AccountContext, usernames: list[str] | None) -> list[dict[str, Any]]:
    database_path = _default_database_path(context, "contact")
    targets = list(dict.fromkeys(str(value or "").strip() for value in (usernames or []) if str(value or "").strip()))
    where = ""
    if targets:
        where = " WHERE username IN (" + ",".join(_sql_literal(value) for value in targets) + ")"
    result: dict[str, dict[str, Any]] = {}
    for table in ("contact", "stranger"):
        try:
            rows = _query(context, database_path, f"SELECT * FROM {table}{where}")
        except Exception:
            continue
        for row in rows:
            username = str(row.get("username") or row.get("user_name") or "").strip()
            if username and username not in result:
                result[username] = row
        if not targets:
            break
    return list(result.values())


def get_contact(handle: int, username: str) -> dict[str, Any]:
    context = _context(handle)
    rows = _contact_rows(context, [username])
    return rows[0] if rows else {}


def get_contacts_compact(handle: int, usernames: list[str] | None = None) -> list[dict[str, Any]]:
    return _contact_rows(_context(handle), usernames)


def _display_name(row: dict[str, Any], fallback: str) -> str:
    for key in ("remark", "nick_name", "nickname", "alias"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return fallback


def get_display_names(handle: int, usernames: list[str]) -> dict[str, str]:
    context = _context(handle)
    rows = _contact_rows(context, usernames)
    result: dict[str, str] = {}
    for row in rows:
        username = str(row.get("username") or row.get("user_name") or "").strip()
        if username:
            result[username] = _display_name(row, username)
    return result


def get_avatar_urls(handle: int, usernames: list[str]) -> dict[str, str]:
    context = _context(handle)
    result: dict[str, str] = {}
    for row in _contact_rows(context, usernames):
        username = str(row.get("username") or row.get("user_name") or "").strip()
        url = str(row.get("big_head_url") or row.get("small_head_url") or "").strip()
        if username and url:
            result[username] = url
    return result


def get_group_members(handle: int, chatroom_id: str) -> list[dict[str, Any]]:
    context = _context(handle)
    room = str(chatroom_id or "").strip()
    if not room:
        return []
    database_path = _default_database_path(context, "contact")
    room_literal = _sql_literal(room)
    statements = (
        "SELECT nm.username AS username FROM chatroom_member cm "
        "JOIN name2id nm ON nm.rowid=cm.member_id "
        "JOIN chat_room cr ON cr.id=cm.room_id "
        f"WHERE cr.username={room_literal} ORDER BY cm.rowid",
        "SELECT nm.user_name AS username FROM chatroom_member cm "
        "JOIN name2id nm ON nm.rowid=cm.member_id "
        "JOIN chat_room cr ON cr.id=cm.room_id "
        f"WHERE cr.username={room_literal} ORDER BY cm.rowid",
    )
    for statement in statements:
        try:
            rows = _query(context, database_path, statement)
        except Exception:
            continue
        members = [
            {"username": str(row.get("username") or "").strip()}
            for row in rows
            if str(row.get("username") or "").strip()
        ]
        if members:
            return members
    return []


def get_group_nicknames(handle: int, chatroom_id: str) -> dict[str, str]:
    members = get_group_members(handle, chatroom_id)
    usernames = [str(item.get("username") or "") for item in members]
    return get_display_names(handle, usernames)


def _sns_database_path(context: _AccountContext) -> Path:
    return _default_database_path(context, "sns")


def get_sns_timeline(
    handle: int,
    *,
    limit: int = 20,
    offset: int = 0,
    usernames: list[str] | None = None,
    keyword: str | None = None,
    start_time: int = 0,
    end_time: int = 0,
) -> list[dict[str, Any]]:
    context = _context(handle)
    wanted = max(0, min(int(limit or 0), 5000))
    skipped = max(0, int(offset or 0))
    if wanted <= 0:
        return []
    filters = ["content IS NOT NULL", "content != ''"]
    users = list(dict.fromkeys(str(value or "").strip() for value in (usernames or []) if str(value or "").strip()))
    if users:
        filters.append("user_name IN (" + ",".join(_sql_literal(value) for value in users) + ")")
    if str(keyword or "").strip():
        escaped = str(keyword).replace("'", "''")
        filters.append(f"content LIKE '%{escaped}%'")
    where = " WHERE " + " AND ".join(filters)
    probe = min(20_000, skipped + wanted + 2048)
    base = (
        "SELECT tid, user_name, content, pack_info_buf FROM SnsTimeLine"
        f"{where} ORDER BY tid DESC LIMIT {probe}"
    )
    try:
        rows = _query(context, _sns_database_path(context), base)
    except Exception:
        rows = _query(
            context,
            _sns_database_path(context),
            base.replace(", pack_info_buf", ""),
        )

    from .routers.sns import _decode_sns_text_blob, _parse_timeline_xml

    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        try:
            tid = int(row.get("tid") or 0)
        except Exception:
            continue
        username = str(row.get("user_name") or "").strip()
        raw_xml = _decode_sns_text_blob(row.get("content"))
        parsed = _parse_timeline_xml(raw_xml, username)
        created = int(parsed.get("createTime") or 0)
        if start_time and created < int(start_time):
            continue
        if end_time and created > int(end_time):
            continue
        parsed_rows.append(
            {
                "id": str(tid & ((1 << 64) - 1)),
                "tid": str(tid & ((1 << 64) - 1)),
                "username": str(parsed.get("username") or username),
                "nickname": "",
                "createTime": created,
                "contentDesc": str(parsed.get("contentDesc") or ""),
                "location": str(parsed.get("location") or ""),
                "sourceName": str(parsed.get("sourceName") or ""),
                "media": parsed.get("media") or [],
                "likes": parsed.get("likes") or [],
                "comments": parsed.get("comments") or [],
                "type": int(parsed.get("type") or 1),
                "title": str(parsed.get("title") or ""),
                "contentUrl": str(parsed.get("contentUrl") or ""),
                "finderFeed": parsed.get("finderFeed") or {},
                "rawXml": raw_xml,
            }
        )
    names = get_display_names(handle, [str(row.get("username") or "") for row in parsed_rows])
    for row in parsed_rows:
        username = str(row.get("username") or "")
        row["nickname"] = names.get(username, username)
    return parsed_rows[skipped : skipped + wanted]


def decrypt_sns_image(encrypted_data: bytes, key: str) -> bytes:
    from .sns_media import weflow_decrypt_sns_image_bytes

    return weflow_decrypt_sns_image_bytes(bytes(encrypted_data or b""), str(key or ""))


def account_snapshot(handle: int) -> dict[str, Any]:
    context = _context(handle)
    return {
        "account": context.account,
        "native_wxid": context.native_wxid,
        "db_storage_dir": str(context.db_storage_dir),
        "session_db_path": str(context.session_db_path),
        "connected": not context.closed,
        "connected_at": time.time(),
    }


__all__ = [
    "NativeCoreRealtimeError",
    "close_account",
    "close_all",
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
    "is_native_core_handle",
    "open_account",
    "open_message_cursor",
]
