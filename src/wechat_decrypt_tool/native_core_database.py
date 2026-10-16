from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .key_store import get_account_keys_from_store
from .media_helpers import _resolve_account_db_storage_dir
from .native_core_broker import (
    NativeCoreManagedOperation,
    managed_native_core_operation,
)
from .native_core_client import (
    NativeCoreClient,
    NativeCoreDatabase,
    NativeCoreDatabaseKeyMode,
    NativeCoreFeature,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreStatus,
    NativeCoreUnavailableError,
    get_native_core_client,
)
from .native_core_lease import refresh_native_core_lease
from .native_core_telemetry import record_product_event


_DATABASE_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
_QUERY_PAGE_ROWS = 512
_QUERY_PAGE_BYTES = 512 * 1024
_QUERY_MAX_ROWS = 10_000
_QUERY_MAX_PAGES = 128


class NativeCoreRow(dict[str, Any]):
    """A dict row with the integer indexing used by sqlite3.Row callers."""

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)
        self._ordered_keys = tuple(values)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            key = self._ordered_keys[key]
        return super().__getitem__(key)


class NativeCoreRowsCursor:
    def __init__(self, rows: list[NativeCoreRow]) -> None:
        self._rows = rows

    def fetchall(self) -> list[NativeCoreRow]:
        return list(self._rows)

    def fetchone(self) -> NativeCoreRow | None:
        return self._rows[0] if self._rows else None


class NativeCoreDatabaseSource:
    source = "realtime"
    native_core = True

    def __init__(
        self,
        database: NativeCoreDatabase,
        database_path: Path,
        *,
        requested_source: str,
        managed_operation: NativeCoreManagedOperation | None = None,
    ) -> None:
        self._database: NativeCoreDatabase | None = database
        self._managed_operation = managed_operation
        self.db_path = Path(database_path)
        self.requested_source = str(requested_source or "auto")
        self.fallback_reason = ""
        self.retry_after_seconds = 0

    def __enter__(self) -> NativeCoreDatabaseSource:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        database = self._database
        self._database = None
        managed_operation = self._managed_operation
        self._managed_operation = None
        try:
            if database is not None:
                database.close()
        finally:
            if managed_operation is not None:
                managed_operation.close()

    def execute(self, sql: str, params: Any = None) -> NativeCoreRowsCursor:
        if params:
            raise NativeCoreProtocolError(
                "wechatdb native v1 queries do not support bound parameters."
            )
        database = self._database
        if database is None:
            raise NativeCoreUnavailableError("wechatdb native database source is closed.")

        rows: list[NativeCoreRow] = []
        with database.open_query(str(sql or "")) as query:
            for _page_index in range(_QUERY_MAX_PAGES):
                page = query.fetch(
                    max_rows=_QUERY_PAGE_ROWS,
                    max_bytes=_QUERY_PAGE_BYTES,
                )
                records = page.records()
                if len(rows) + len(records) > _QUERY_MAX_ROWS:
                    raise NativeCoreProtocolError(
                        "wechatdb native query exceeded the application row limit."
                    )
                rows.extend(NativeCoreRow(dict(record)) for record in records)
                if not page.has_more:
                    return NativeCoreRowsCursor(rows)
        raise NativeCoreProtocolError(
            "wechatdb native query exceeded the application page limit."
        )


def _database_path(account_dir: Path, database_group: str, database_name: str) -> Path:
    if not _DATABASE_COMPONENT_PATTERN.fullmatch(database_group) or not _DATABASE_COMPONENT_PATTERN.fullmatch(
        database_name
    ):
        raise NativeCoreProtocolError("Invalid native core database path component.")

    storage = _resolve_account_db_storage_dir(Path(account_dir))
    if storage is None:
        raise NativeCoreUnavailableError(
            "Cannot resolve db_storage for the native core database."
        )
    try:
        storage = storage.resolve(strict=True)
        database_path = (storage / database_group / database_name).resolve(strict=True)
    except OSError as exc:
        raise NativeCoreUnavailableError(
            f"Native core database is unavailable: {database_group}/{database_name}"
        ) from exc
    if storage not in database_path.parents or not database_path.is_file():
        raise NativeCoreProtocolError("Native core database path escaped db_storage.")
    return database_path


def _database_key(account_dir: Path) -> bytearray:
    account = Path(account_dir).name
    encoded = str(get_account_keys_from_store(account).get("db_key") or "").strip()
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", encoded):
        raise NativeCoreUnavailableError(
            "A valid 32-byte database key is required by the native core."
        )
    return bytearray.fromhex(encoded)


def _open_database_with_lease(
    client: NativeCoreClient,
    database_path: Path,
    key: bytes | bytearray | memoryview,
) -> NativeCoreDatabase:
    try:
        return client.open_database(
            os.fspath(database_path),
            key=key,
            key_mode=NativeCoreDatabaseKeyMode.AUTO,
        )
    except NativeCorePolicyError as policy_error:
        if policy_error.status not in {
            int(NativeCoreStatus.LICENSE_REQUIRED),
            int(NativeCoreStatus.LEASE_EXPIRED),
            int(NativeCoreStatus.FEATURE_DENIED),
        }:
            raise
        try:
            refresh_native_core_lease(client, NativeCoreFeature.DATABASE_READ)
        except Exception as refresh_error:
            raise policy_error from refresh_error
        return client.open_database(
            os.fspath(database_path),
            key=key,
            key_mode=NativeCoreDatabaseKeyMode.AUTO,
        )


def open_native_core_database_source(
    account_dir: Path,
    *,
    database_group: str,
    database_name: str,
    requested_source: str = "auto",
) -> NativeCoreDatabaseSource:
    database_path = _database_path(Path(account_dir), database_group, database_name)
    key = _database_key(Path(account_dir))
    try:
        # _database_path proves the fixed storage/group/name layout, so the
        # grandparent is the exact db_storage root injected into the broker.
        managed_operation = managed_native_core_operation(
            database_root=database_path.parent.parent
        )
        try:
            client = get_native_core_client()
            database = _open_database_with_lease(client, database_path, key)
            record_product_event("database_open")
        except BaseException:
            managed_operation.close()
            raise
    finally:
        key[:] = b"\x00" * len(key)
    return NativeCoreDatabaseSource(
        database,
        database_path,
        requested_source=requested_source,
        managed_operation=managed_operation,
    )


__all__ = [
    "NativeCoreDatabaseSource",
    "NativeCoreRow",
    "NativeCoreRowsCursor",
    "open_native_core_database_source",
]
