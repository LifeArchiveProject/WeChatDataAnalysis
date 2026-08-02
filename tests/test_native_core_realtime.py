import hashlib
import sqlite3
import sys
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import (
    chat_realtime_reader,
    native_core_raw_key_cache,
    native_core_realtime,
)
from wechat_decrypt_tool.native_core_client import NativeCoreDatabaseKeyMode


class _RowsPage:
    has_more = False

    def __init__(self, rows):
        self._rows = [dict(row) for row in rows]

    def records(self):
        return [dict(row) for row in self._rows]


class _RowsQuery:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def fetch(self, *, max_rows: int, max_bytes: int):
        if max_rows <= 0 or max_bytes <= 0:
            raise AssertionError("query limits must be positive")
        return _RowsPage(self._rows)


class _TrackedDatabase:
    def __init__(self, label: str):
        self.label = label
        self.closed = False
        self.close_count = 0
        self.query_count = 0

    def open_query(self, _sql: str):
        if self.closed:
            raise AssertionError(f"database {self.label} was closed while still in use")
        self.query_count += 1
        return _RowsQuery([{"database": self.label}])

    def close(self):
        if not self.closed:
            self.closed = True
            self.close_count += 1


class _SQLiteReadDatabase:
    def __init__(self, path: Path):
        self._connection = sqlite3.connect(
            f"{path.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        self._connection.row_factory = sqlite3.Row
        self.closed = False
        self.close_count = 0

    def open_query(self, sql: str):
        if self.closed:
            raise AssertionError("SQLite read database was closed while still cached")
        connection = self._connection

        class _SQLiteQuery:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def fetch(*, max_rows: int, max_bytes: int):
                if max_rows <= 0 or max_bytes <= 0:
                    raise AssertionError("query limits must be positive")
                cursor = connection.execute(sql)
                try:
                    return _RowsPage(dict(row) for row in cursor.fetchall())
                finally:
                    cursor.close()

        return _SQLiteQuery()

    def close(self):
        if not self.closed:
            self.closed = True
            self.close_count += 1
            self._connection.close()


def _make_context(root: Path, handle: int) -> native_core_realtime._AccountContext:
    session_path = root / f"session_{handle}.db"
    session_path.write_bytes(b"fixture")
    return native_core_realtime._AccountContext(
        handle=handle,
        account=f"wxid_account_{handle}",
        native_wxid=f"wxid_native_{handle}",
        db_storage_dir=root,
        session_db_path=session_path,
        key=bytearray(b"1" * 32),
    )


def _reset_native_read_cache() -> None:
    chat_realtime_reader._clear_realtime_reader_caches()
    native_core_realtime.close_all()
    native_core_realtime._close_cached_read_databases()
    with native_core_realtime._read_database_cache_condition:
        if native_core_realtime._read_database_pending_opens != 0:
            raise AssertionError("native read cache still has pending opens")
        if native_core_realtime._read_database_handle_count != 0:
            raise AssertionError("native read cache still has live handles")
        if native_core_realtime._read_database_cache:
            raise AssertionError("native read cache was not emptied")
        native_core_realtime._read_database_cache_client = None


class TestNativeCoreRealtime(unittest.TestCase):
    def setUp(self) -> None:
        _reset_native_read_cache()

    def tearDown(self) -> None:
        _reset_native_read_cache()

    def test_initial_message_queries_follow_the_sort_seq_index(self) -> None:
        for sql in chat_realtime_reader._select_candidates("Msg_fixture", 51):
            self.assertIn(
                "ORDER BY m.sort_seq DESC, m.local_id DESC",
                sql,
            )
            self.assertNotIn("ORDER BY m.create_time", sql)

        ascending = native_core_realtime._message_select_sql(
            "Msg_fixture",
            ascending=True,
            limit=51,
        )
        descending = native_core_realtime._message_select_sql(
            "Msg_fixture",
            ascending=False,
            limit=51,
        )
        self.assertIn("ORDER BY m.sort_seq ASC, m.local_id ASC", ascending)
        self.assertIn("ORDER BY m.sort_seq DESC, m.local_id DESC", descending)
        self.assertNotIn("ORDER BY m.create_time", ascending)
        self.assertNotIn("ORDER BY m.create_time", descending)

    def test_raw_database_keys_are_derived_from_each_salt_and_zeroized(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            context = _make_context(root, 101)
            database_path = root / "message_0.db"
            first_salt = bytes(range(16))
            database_path.write_bytes(first_salt + b"encrypted-page")

            native_core_realtime._prime_database_raw_keys(context, [database_path])
            first = native_core_realtime._cached_database_raw_key(
                context, database_path
            )
            self.assertIsNotNone(first)
            self.assertEqual(
                bytes(first),
                hashlib.pbkdf2_hmac(
                    "sha512", context.key, first_salt, 256_000, dklen=32
                ),
            )

            old_reference = first
            second_salt = bytes(range(16, 32))
            database_path.write_bytes(second_salt + b"replacement-page")
            native_core_realtime._prime_database_raw_keys(context, [database_path])
            second = native_core_realtime._cached_database_raw_key(
                context, database_path
            )
            self.assertIsNotNone(second)
            self.assertNotEqual(bytes(second), bytes(first))
            self.assertEqual(bytes(old_reference), b"\0" * 32)

            second_reference = second
            context.close()
            self.assertEqual(bytes(second_reference), b"\0" * 32)
            self.assertEqual(context.raw_database_keys, {})

    def test_raw_database_keys_survive_process_context_through_encrypted_cache(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            root.mkdir()
            database_path = root / "message_0.db"
            salt = bytes(range(16))
            database_path.write_bytes(salt + b"encrypted-page")
            cache_dir = Path(td) / "cache"
            first_context = _make_context(root, 111)

            with patch.object(
                native_core_raw_key_cache,
                "_cache_directory",
                return_value=cache_dir,
            ):
                native_core_realtime._prime_database_raw_keys(
                    first_context, [database_path]
                )
                expected = bytes(
                    native_core_realtime._cached_database_raw_key(
                        first_context, database_path
                    )
                )
                first_context.close()

                second_context = _make_context(root, 112)
                with patch.object(
                    native_core_realtime,
                    "_derive_database_raw_key",
                    side_effect=AssertionError("persistent cache miss"),
                ) as derive:
                    native_core_realtime._prime_database_raw_keys(
                        second_context, [database_path]
                    )
                try:
                    loaded = native_core_realtime._cached_database_raw_key(
                        second_context, database_path
                    )
                    self.assertIsNotNone(loaded)
                    self.assertEqual(bytes(loaded), expected)
                    derive.assert_not_called()
                finally:
                    second_context.close()

    def test_raw_database_key_cache_rederives_after_database_salt_change(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            root.mkdir()
            database_path = root / "message_0.db"
            database_path.write_bytes(b"a" * 16 + b"encrypted-page")
            cache_dir = Path(td) / "cache"
            first_context = _make_context(root, 113)

            with patch.object(
                native_core_raw_key_cache,
                "_cache_directory",
                return_value=cache_dir,
            ):
                native_core_realtime._prime_database_raw_keys(
                    first_context, [database_path]
                )
                first_context.close()
                database_path.write_bytes(b"b" * 16 + b"replacement-page")

                second_context = _make_context(root, 114)
                replacement = bytearray(b"z" * 32)
                with patch.object(
                    native_core_realtime,
                    "_derive_database_raw_key",
                    return_value=replacement,
                ) as derive:
                    native_core_realtime._prime_database_raw_keys(
                        second_context, [database_path]
                    )
                try:
                    derive.assert_called_once_with(second_context.key, b"b" * 16)
                    loaded = native_core_realtime._cached_database_raw_key(
                        second_context, database_path
                    )
                    self.assertEqual(bytes(loaded), b"z" * 32)
                finally:
                    second_context.close()

    def test_open_database_uses_derived_raw_key_and_falls_back_to_auto(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            context = _make_context(root, 102)
            database_path = root / "message_0.db"
            salt = bytes(reversed(range(16)))
            database_path.write_bytes(salt + b"encrypted-page")
            native_core_realtime._prime_database_raw_keys(context, [database_path])
            expected_raw = hashlib.pbkdf2_hmac(
                "sha512", context.key, salt, 256_000, dklen=32
            )

            class _Client:
                def __init__(self):
                    self.calls = []

                def open_database(self, path, **options):
                    captured = dict(options)
                    captured["key"] = bytes(captured["key"])
                    self.calls.append((Path(path), captured))
                    if len(self.calls) == 1:
                        raise native_core_realtime.NativeCoreError(
                            "wrong raw key",
                            status=int(native_core_realtime.NativeCoreStatus.DATABASE),
                        )
                    return _TrackedDatabase("fallback")

            client = _Client()
            database = native_core_realtime._open_database(
                client, context, database_path
            )

            self.assertEqual(database.label, "fallback")
            self.assertEqual(
                [call[1]["key_mode"] for call in client.calls],
                [NativeCoreDatabaseKeyMode.RAW, NativeCoreDatabaseKeyMode.AUTO],
            )
            self.assertEqual(bytes(client.calls[0][1]["key"]), expected_raw)
            self.assertEqual(bytes(client.calls[1][1]["key"]), bytes(context.key))
            self.assertIsNone(
                native_core_realtime._cached_database_raw_key(
                    context, database_path
                )
            )

    def test_open_account_primes_initial_database_keys_in_parallel(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            session_path = root / "session" / "session.db"
            contact_path = root / "contact" / "contact.db"
            message_path = root / "message" / "message_0.db"
            business_path = root / "message" / "biz_message_0.db"
            excluded_paths = (
                root / "message" / "message_fts.db",
                root / "message" / "message_resource.db",
            )
            candidates = (session_path, contact_path, message_path, business_path)
            for index, path in enumerate((*candidates, *excluded_paths), start=1):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bytes([index]) * 16 + b"encrypted-page")

            derivation_gate = threading.Event()
            derivation_lock = threading.Lock()
            active_derivations = 0
            max_active_derivations = 0

            def fake_derive(key: bytearray, salt: bytes) -> bytearray:
                nonlocal active_derivations, max_active_derivations
                with derivation_lock:
                    active_derivations += 1
                    max_active_derivations = max(
                        max_active_derivations, active_derivations
                    )
                    if active_derivations >= 2:
                        derivation_gate.set()
                try:
                    if not derivation_gate.wait(2.0):
                        raise AssertionError("initial raw keys were derived serially")
                    return bytearray(hashlib.sha256(bytes(key) + salt).digest())
                finally:
                    with derivation_lock:
                        active_derivations -= 1

            with (
                patch.object(
                    native_core_realtime,
                    "_derive_database_raw_key",
                    side_effect=fake_derive,
                ),
                patch.object(
                    native_core_realtime,
                    "_query",
                    return_value=[{"native_core_probe": 1}],
                ) as query,
            ):
                handle = native_core_realtime.open_account(
                    account="wxid_account",
                    native_wxid="wxid_native",
                    db_storage_dir=root,
                    session_db_path=session_path,
                    key_hex="31" * 32,
                )

            try:
                context = native_core_realtime._context(handle)
                self.assertGreaterEqual(max_active_derivations, 2)
                self.assertEqual(len(context.raw_database_keys), len(candidates))
                for path in candidates:
                    self.assertIsNotNone(
                        native_core_realtime._cached_database_raw_key(context, path)
                    )
                for path in excluded_paths:
                    self.assertIsNone(
                        native_core_realtime._cached_database_raw_key(context, path)
                    )
                query.assert_called_once_with(
                    context,
                    session_path.resolve(),
                    "SELECT 1 AS native_core_probe",
                )
            finally:
                native_core_realtime.close_account(handle)

    def test_open_account_propagates_parallel_derivation_failure(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            session_path = root / "session" / "session.db"
            message_path = root / "message" / "message_0.db"
            session_path.parent.mkdir(parents=True)
            message_path.parent.mkdir(parents=True)
            session_path.write_bytes(b"s" * 16 + b"encrypted-page")
            message_path.write_bytes(b"m" * 16 + b"encrypted-page")
            successful_keys: list[bytearray] = []

            def fake_derive(_key: bytearray, salt: bytes) -> bytearray:
                if salt == b"m" * 16:
                    raise RuntimeError("parallel KDF failed")
                raw_key = bytearray(b"r" * 32)
                successful_keys.append(raw_key)
                return raw_key

            with (
                patch.object(
                    native_core_realtime,
                    "_derive_database_raw_key",
                    side_effect=fake_derive,
                ),
                patch.object(native_core_realtime, "_query") as query,
            ):
                with self.assertRaisesRegex(RuntimeError, "parallel KDF failed"):
                    native_core_realtime.open_account(
                        account="wxid_account",
                        native_wxid="wxid_native",
                        db_storage_dir=root,
                        session_db_path=session_path,
                        key_hex="31" * 32,
                    )

            query.assert_not_called()
            self.assertTrue(successful_keys)
            self.assertTrue(
                all(bytes(raw_key) == b"\0" * 32 for raw_key in successful_keys)
            )

    def test_live_shard_discovery_remains_authoritative_when_a_new_shard_appears(self) -> None:
        class _Connection:
            handle = 7
            native_wxid = "wxid_me"
            lock = threading.Lock()

        probed_paths: list[str] = []

        def fake_exec(_handle, *, kind: str, path: str, sql: str):
            self.assertEqual(kind, "message")
            if "sqlite_master" in sql:
                probed_paths.append(Path(path).name)
                return [{"name": table_name}]
            local_id = 10 if path.endswith("message_1.db") else 9
            return [
                {
                    "local_id": local_id,
                    "server_id": local_id * 10,
                    "local_type": 1,
                    "sort_seq": local_id * 100,
                    "real_sender_id": 1,
                    "create_time": local_id,
                    "message_content": "hello",
                    "compress_content": None,
                    "packed_info_data": None,
                    "msg_source": None,
                    "sender_username": "wxid_me",
                    "__my_rowid": 1,
                }
            ]

        with TemporaryDirectory() as td:
            db_storage = Path(td) / "db_storage"
            message_dir = db_storage / "message"
            message_dir.mkdir(parents=True)
            for name in (
                "message_0.db",
                "message_1.db",
                "message_fts.db",
                "message_resource.db",
            ):
                (message_dir / name).write_bytes(b"fixture")
            table_name = "Msg_" + hashlib.md5(b"wxid_friend").hexdigest()
            batch = chat_realtime_reader.fetch_rows_via_exec(
                rt_conn=_Connection(),
                account_dir=Path(td) / "wxid_me",
                username="wxid_friend",
                take=1,
                db_storage_dir=db_storage,
                exec_query=fake_exec,
                normalize_item=lambda item: dict(item),
            )

        self.assertEqual(len(batch.rows), 1)
        self.assertEqual(batch.rows[0]["local_id"], 10)
        self.assertEqual(batch.db_path, message_dir / "message_1.db")
        self.assertEqual(probed_paths, ["message_0.db", "message_1.db"])
        self.assertTrue(batch.authoritative)
        self.assertEqual(batch.databases_probed, 2)
        self.assertEqual(batch.tables_found, 2)

    def test_message_table_resolution_cache_reuses_probes_and_tracks_new_shards(self) -> None:
        class _Connection:
            handle = 17
            lock = threading.Lock()

        probed_paths: list[str] = []
        table_name = "Msg_" + hashlib.md5(b"wxid_friend").hexdigest()

        def fake_exec(_handle, *, kind: str, path: str, sql: str):
            self.assertEqual(kind, "message")
            self.assertIn("sqlite_master", sql)
            probed_paths.append(Path(path).name)
            return [{"name": table_name}]

        with TemporaryDirectory() as td:
            db_storage = Path(td) / "db_storage"
            message_dir = db_storage / "message"
            message_dir.mkdir(parents=True)
            (message_dir / "message_0.db").write_bytes(b"fixture")

            first = chat_realtime_reader._resolve_tables(
                rt_conn=_Connection(),
                db_storage_dir=db_storage,
                username="wxid_friend",
                exec_query=fake_exec,
            )
            second = chat_realtime_reader._resolve_tables(
                rt_conn=_Connection(),
                db_storage_dir=db_storage,
                username="wxid_friend",
                exec_query=fake_exec,
            )
            self.assertEqual(first[:3], second[:3])
            self.assertEqual(probed_paths, ["message_0.db"])

            (message_dir / "message_1.db").write_bytes(b"fixture")
            third = chat_realtime_reader._resolve_tables(
                rt_conn=_Connection(),
                db_storage_dir=db_storage,
                username="wxid_friend",
                exec_query=fake_exec,
            )

        self.assertEqual([path.name for path, _table in third[0]], ["message_0.db", "message_1.db"])
        self.assertEqual(
            probed_paths,
            ["message_0.db", "message_0.db", "message_1.db"],
        )

    def test_supported_message_projection_is_reused_after_the_first_fallback(self) -> None:
        class _Connection:
            handle = 19
            lock = threading.Lock()

        calls: list[str] = []

        def fake_exec(_handle, *, kind: str, path: str, sql: str):
            self.assertEqual(kind, "message")
            calls.append(sql)
            if "missing_column" in sql:
                raise RuntimeError("no such column: missing_column")
            return [{"local_id": 1}]

        statements = (
            'SELECT m.missing_column FROM "Msg_fixture" m',
            'SELECT m.local_id FROM "Msg_fixture" m',
        )
        with TemporaryDirectory() as td:
            db_path = Path(td) / "message_0.db"
            db_path.write_bytes(b"fixture")
            first = chat_realtime_reader._query_first_supported(
                rt_conn=_Connection(),
                db_path=db_path,
                statements=statements,
                exec_query=fake_exec,
            )
            second = chat_realtime_reader._query_first_supported(
                rt_conn=_Connection(),
                db_path=db_path,
                statements=statements,
                exec_query=fake_exec,
            )

        self.assertEqual(first, [{"local_id": 1}])
        self.assertEqual(second, first)
        self.assertEqual(
            calls,
            [statements[0], statements[1], statements[1]],
        )

    def test_read_queries_reuse_database_handle_until_account_close(self) -> None:
        class _Page:
            has_more = False

            @staticmethod
            def records():
                return [{"value": 1}]

        class _Query:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def fetch(*, max_rows: int, max_bytes: int):
                self.assertGreater(max_rows, 0)
                self.assertGreater(max_bytes, 0)
                return _Page()

        class _Database:
            closed = False
            close_count = 0
            query_count = 0

            def open_query(self, _sql: str):
                self.query_count += 1
                return _Query()

            def close(self):
                if not self.closed:
                    self.closed = True
                    self.close_count += 1

        with TemporaryDirectory() as td:
            root = Path(td)
            database_path = root / "message_0.db"
            database_path.write_bytes(b"fixture")
            context = native_core_realtime._AccountContext(
                handle=123,
                account="wxid_me",
                native_wxid="wxid_me",
                db_storage_dir=root,
                session_db_path=database_path,
                key=bytearray(b"1" * 32),
            )
            database = _Database()
            with (
                patch.object(native_core_realtime, "managed_native_core_operation", return_value=nullcontext()),
                patch.object(native_core_realtime, "get_native_core_client", return_value=object()),
                patch.object(native_core_realtime, "_open_database", return_value=database) as open_database,
            ):
                first = native_core_realtime._query_once(context, database_path, "SELECT 1")
                second = native_core_realtime._query_once(context, database_path, "SELECT 1")

            self.assertEqual(first, [{"value": 1}])
            self.assertEqual(second, first)
            self.assertEqual(open_database.call_count, 1)
            self.assertEqual(database.query_count, 2)
            self.assertFalse(database.closed)

            context.close()
            self.assertTrue(database.closed)
            self.assertEqual(database.close_count, 1)
            self.assertFalse(
                any(key[0] == context.handle for key in native_core_realtime._read_database_cache)
            )

    def test_borrowed_handle_is_not_evicted_or_closed_by_another_account(self) -> None:
        wait_entered = threading.Event()

        class _ObservedCondition(threading.Condition):
            def wait(self, timeout=None):
                wait_entered.set()
                return super().wait(timeout)

        with TemporaryDirectory() as td:
            root = Path(td)
            first_context = _make_context(root, 201)
            second_context = _make_context(root, 202)
            first_path = root / "message_first.db"
            second_path = root / "message_second.db"
            first_path.write_bytes(b"first")
            second_path.write_bytes(b"second")
            client = object()
            databases: dict[Path, _TrackedDatabase] = {}
            opened_paths: list[Path] = []
            worker_started = threading.Event()
            worker_acquired = threading.Event()
            worker_errors: list[BaseException] = []

            def fake_open(_client, _context, database_path, **_kwargs):
                path = Path(database_path)
                opened_paths.append(path)
                database = _TrackedDatabase(path.name)
                databases[path] = database
                return database

            def borrow_second():
                worker_started.set()
                try:
                    with native_core_realtime._borrow_cached_read_database(
                        client,
                        second_context,
                        second_path,
                    ):
                        worker_acquired.set()
                except BaseException as exc:
                    worker_errors.append(exc)

            condition = _ObservedCondition(threading.RLock())
            worker = threading.Thread(target=borrow_second, daemon=True)
            with (
                patch.object(native_core_realtime, "_READ_DATABASE_CACHE_LIMIT", 1),
                patch.object(native_core_realtime, "_read_database_cache_condition", condition),
                patch.object(native_core_realtime, "_open_database", side_effect=fake_open),
            ):
                try:
                    with native_core_realtime._borrow_cached_read_database(
                        client,
                        first_context,
                        first_path,
                    ) as first_database:
                        worker.start()
                        self.assertTrue(worker_started.wait(1.0))
                        self.assertTrue(wait_entered.wait(1.0))
                        self.assertFalse(worker_acquired.is_set())
                        self.assertEqual(opened_paths, [first_path])
                        self.assertFalse(first_database.closed)
                        self.assertEqual(first_database.close_count, 0)

                    self.assertTrue(worker_acquired.wait(2.0))
                    worker.join(2.0)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(worker_errors, [])
                    self.assertEqual(opened_paths, [first_path, second_path])
                    self.assertTrue(databases[first_path].closed)
                    self.assertEqual(databases[first_path].close_count, 1)
                finally:
                    worker.join(2.0)
                    native_core_realtime._close_cached_read_databases()

    def test_new_native_client_invalidates_the_entire_cached_generation(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            contexts = [_make_context(root, handle) for handle in (301, 302, 303)]
            paths = [root / f"message_{index}.db" for index in range(3)]
            for path in paths:
                path.write_bytes(b"fixture")
            old_client = object()
            new_client = object()
            old_databases: list[_TrackedDatabase] = []

            def fake_open(client, _context, database_path, **_kwargs):
                if client is new_client:
                    self.assertEqual(len(old_databases), 2)
                    self.assertTrue(all(database.closed for database in old_databases))
                database = _TrackedDatabase(Path(database_path).name)
                if client is old_client:
                    old_databases.append(database)
                return database

            with (
                patch.object(native_core_realtime, "managed_native_core_operation", return_value=nullcontext()),
                patch.object(
                    native_core_realtime,
                    "get_native_core_client",
                    side_effect=(old_client, old_client, new_client),
                ) as get_client,
                patch.object(native_core_realtime, "_open_database", side_effect=fake_open) as open_database,
            ):
                for context, path in zip(contexts, paths):
                    native_core_realtime._query_once(context, path, "SELECT 1")

            self.assertEqual(get_client.call_count, 3)
            self.assertEqual(open_database.call_count, 3)
            self.assertTrue(all(database.closed for database in old_databases))
            self.assertTrue(all(database.close_count == 1 for database in old_databases))
            with native_core_realtime._read_database_cache_condition:
                self.assertIs(native_core_realtime._read_database_cache_client, new_client)
                self.assertEqual(len(native_core_realtime._read_database_cache), 1)
                self.assertEqual(
                    tuple(native_core_realtime._read_database_cache)[0][0],
                    contexts[-1].handle,
                )
                self.assertEqual(native_core_realtime._read_database_handle_count, 1)

    def test_policy_refresh_closes_old_generation_before_single_reopen(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            context = _make_context(root, 401)
            old_path = root / "message_old.db"
            new_path = root / "message_new.db"
            old_path.write_bytes(b"old")
            new_path.write_bytes(b"new")
            old_database = _TrackedDatabase("old")
            new_database = _TrackedDatabase("new")
            open_paths: list[Path] = []

            class _LeaseClient:
                def open_database(self, database_path, **_kwargs):
                    path = Path(database_path)
                    open_paths.append(path)
                    if len(open_paths) == 1:
                        return old_database
                    if len(open_paths) == 2:
                        raise native_core_realtime.NativeCorePolicyError(
                            "lease expired",
                            status=int(native_core_realtime.NativeCoreStatus.LEASE_EXPIRED),
                        )
                    if len(open_paths) == 3:
                        return new_database
                    raise AssertionError("policy retry opened the database more than once")

            client = _LeaseClient()

            def fake_refresh(refresh_client, feature):
                self.assertIs(refresh_client, client)
                self.assertEqual(feature, native_core_realtime.NativeCoreFeature.DATABASE_READ)
                self.assertTrue(old_database.closed)
                self.assertEqual(old_database.close_count, 1)
                with native_core_realtime._read_database_cache_condition:
                    self.assertEqual(len(native_core_realtime._read_database_cache), 0)
                    self.assertEqual(native_core_realtime._read_database_handle_count, 0)

            with (
                patch.object(native_core_realtime, "managed_native_core_operation", return_value=nullcontext()),
                patch.object(native_core_realtime, "get_native_core_client", return_value=client),
                patch.object(native_core_realtime, "refresh_native_core_lease", side_effect=fake_refresh) as refresh,
            ):
                first = native_core_realtime._query(context, old_path, "SELECT 1")
                second = native_core_realtime._query(context, new_path, "SELECT 1")

            self.assertEqual(first, [{"database": "old"}])
            self.assertEqual(second, [{"database": "new"}])
            self.assertEqual(open_paths, [old_path, new_path, new_path])
            self.assertEqual(refresh.call_count, 1)
            self.assertFalse(new_database.closed)

    def test_concurrent_cache_misses_reserve_no_more_than_cache_limit(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            limit = native_core_realtime._READ_DATABASE_CACHE_LIMIT
            worker_count = limit + 4
            contexts = [_make_context(root, 500 + index) for index in range(worker_count)]
            paths = [root / f"message_{index}.db" for index in range(worker_count)]
            for path in paths:
                path.write_bytes(b"fixture")

            client = object()
            start = threading.Barrier(worker_count + 1)
            release_opens = threading.Event()
            slots_full = threading.Event()
            overflow = threading.Event()
            metrics_lock = threading.Lock()
            opened = 0
            active_opens = 0
            max_active_opens = 0
            max_reserved = 0
            worker_errors: list[BaseException] = []

            def fake_open(_client, _context, database_path, **_kwargs):
                nonlocal opened, active_opens, max_active_opens, max_reserved
                with metrics_lock:
                    opened += 1
                    active_opens += 1
                    max_active_opens = max(max_active_opens, active_opens)
                    if opened == limit:
                        slots_full.set()
                    if opened > limit:
                        overflow.set()
                with native_core_realtime._read_database_cache_condition:
                    reserved = (
                        native_core_realtime._read_database_handle_count
                        + native_core_realtime._read_database_pending_opens
                    )
                with metrics_lock:
                    max_reserved = max(max_reserved, reserved)
                if not release_opens.wait(5.0):
                    raise TimeoutError("test did not release pending database opens")
                with metrics_lock:
                    active_opens -= 1
                return _TrackedDatabase(Path(database_path).name)

            def borrow(index: int):
                try:
                    start.wait(3.0)
                    with native_core_realtime._borrow_cached_read_database(
                        client,
                        contexts[index],
                        paths[index],
                    ):
                        pass
                except BaseException as exc:
                    with metrics_lock:
                        worker_errors.append(exc)

            threads = [
                threading.Thread(target=borrow, args=(index,), daemon=True)
                for index in range(worker_count)
            ]
            with patch.object(native_core_realtime, "_open_database", side_effect=fake_open):
                try:
                    for thread in threads:
                        thread.start()
                    start.wait(3.0)
                    self.assertTrue(slots_full.wait(3.0))
                    self.assertFalse(overflow.wait(0.2))
                    with native_core_realtime._read_database_cache_condition:
                        reserved = (
                            native_core_realtime._read_database_handle_count
                            + native_core_realtime._read_database_pending_opens
                        )
                    self.assertEqual(reserved, limit)
                    self.assertEqual(opened, limit)
                    self.assertLessEqual(max_active_opens, limit)
                    self.assertLessEqual(max_reserved, limit)
                finally:
                    release_opens.set()
                    for thread in threads:
                        thread.join(5.0)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(worker_errors, [])
            self.assertEqual(opened, worker_count)
            with native_core_realtime._read_database_cache_condition:
                self.assertLessEqual(
                    native_core_realtime._read_database_handle_count
                    + native_core_realtime._read_database_pending_opens,
                    limit,
                )
                self.assertLessEqual(len(native_core_realtime._read_database_cache), limit)

    def test_cached_read_connection_observes_committed_wal_rows(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            database_path = root / "message_wal.db"
            writer = sqlite3.connect(database_path)
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("CREATE TABLE messages (local_id INTEGER PRIMARY KEY, content TEXT)")
            writer.execute("INSERT INTO messages VALUES (1, 'first')")
            writer.commit()
            context = _make_context(root, 601)
            database = _SQLiteReadDatabase(database_path)

            try:
                with (
                    patch.object(native_core_realtime, "managed_native_core_operation", return_value=nullcontext()),
                    patch.object(native_core_realtime, "get_native_core_client", return_value=object()),
                    patch.object(native_core_realtime, "_open_database", return_value=database) as open_database,
                ):
                    first = native_core_realtime._query_once(
                        context,
                        database_path,
                        "SELECT local_id, content FROM messages ORDER BY local_id",
                    )
                    writer.execute("INSERT INTO messages VALUES (2, 'second')")
                    writer.commit()
                    second = native_core_realtime._query_once(
                        context,
                        database_path,
                        "SELECT local_id, content FROM messages ORDER BY local_id",
                    )

                self.assertEqual(first, [{"local_id": 1, "content": "first"}])
                self.assertEqual(
                    second,
                    [
                        {"local_id": 1, "content": "first"},
                        {"local_id": 2, "content": "second"},
                    ],
                )
                self.assertEqual(open_database.call_count, 1)
                self.assertFalse(database.closed)
            finally:
                context.close()
                writer.close()

            self.assertTrue(database.closed)
            self.assertEqual(database.close_count, 1)

    def test_database_path_escape_is_rejected_and_handle_close_zeroizes_state(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            db_storage = root / "db_storage"
            session_db = db_storage / "session" / "session.db"
            inside_db = db_storage / "contact" / "contact.db"
            outside_db = root / "outside.db"
            session_db.parent.mkdir(parents=True)
            inside_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"session")
            inside_db.write_bytes(b"contact")
            outside_db.write_bytes(b"outside")

            def fake_query(_context, database_path: Path, sql: str):
                if "native_core_probe" in sql:
                    return [{"native_core_probe": 1}]
                return [{"database": database_path.name}]

            with patch.object(native_core_realtime, "_query", side_effect=fake_query) as query:
                handle = native_core_realtime.open_account(
                    account="wxid_demo_1234",
                    native_wxid="wxid_demo",
                    db_storage_dir=db_storage,
                    session_db_path=session_db,
                    key_hex="23" * 32,
                )

                self.assertGreaterEqual(handle, native_core_realtime._HANDLE_START)
                self.assertTrue(native_core_realtime.is_native_core_handle(handle))
                context = native_core_realtime._context(handle)
                self.assertEqual(bytes(context.key), bytes.fromhex("23" * 32))

                escaped = db_storage / ".." / outside_db.name
                with self.assertRaisesRegex(
                    native_core_realtime.NativeCoreRealtimeError,
                    "escaped db_storage",
                ):
                    native_core_realtime.exec_query(
                        handle,
                        kind="contact",
                        path=str(escaped),
                        sql="SELECT 1",
                    )
                self.assertEqual(query.call_count, 1)

                rows = native_core_realtime.exec_query(
                    handle,
                    kind="contact",
                    path=str(inside_db),
                    sql="SELECT 1",
                )
                self.assertEqual(rows, [{"database": "contact.db"}])

                cursor = native_core_realtime.open_message_cursor(
                    handle, "wxid_friend", batch_size=20
                )
                self.assertIn(cursor, native_core_realtime._message_cursors)

                native_core_realtime.close_account(handle)
                self.assertFalse(native_core_realtime.is_native_core_handle(handle))
                self.assertNotIn(cursor, native_core_realtime._message_cursors)
                self.assertTrue(context.closed)
                self.assertEqual(bytes(context.key), b"\0" * 32)
                with self.assertRaisesRegex(
                    native_core_realtime.NativeCoreRealtimeError,
                    "handle is closed",
                ):
                    native_core_realtime._context(handle)

                native_core_realtime.close_account(handle)

    def test_raw_sql_and_realtime_api_do_not_expose_database_mutations(self) -> None:
        with TemporaryDirectory() as td:
            db_storage = Path(td) / "db_storage"
            session_db = db_storage / "session" / "session.db"
            message_db = db_storage / "message" / "message_0.db"
            session_db.parent.mkdir(parents=True)
            message_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"session")
            message_db.write_bytes(b"message")

            def fake_query(_context, _database_path: Path, sql: str):
                if "native_core_probe" in sql:
                    return [{"native_core_probe": 1}]
                return []

            with patch.object(native_core_realtime, "_query", side_effect=fake_query) as query:
                handle = native_core_realtime.open_account(
                    account="wxid_demo_1234",
                    native_wxid="wxid_demo",
                    db_storage_dir=db_storage,
                    session_db_path=session_db,
                    key_hex="42" * 32,
                )

                self.assertEqual(
                    native_core_realtime.exec_query(
                        handle,
                        kind="message",
                        path=str(message_db),
                        sql="SELECT 1",
                    ),
                    [],
                )
                read_call_count = query.call_count

                for statement in (
                    "UPDATE Msg_fixture SET message_content='updated' WHERE local_id=7",
                    "INSERT INTO Msg_fixture(local_id) VALUES(7)",
                    "DELETE FROM Msg_fixture WHERE local_id=7",
                    "DROP TABLE Msg_fixture",
                ):
                    with self.subTest(statement=statement), self.assertRaisesRegex(
                        native_core_realtime.NativeCoreRealtimeError,
                        "raw SQL is read-only",
                    ):
                        native_core_realtime.exec_query(
                            handle,
                            kind="message",
                            path=str(message_db),
                            sql=statement,
                        )

                self.assertEqual(query.call_count, read_call_count)
                self.assertFalse(hasattr(native_core_realtime, "_execute"))
                self.assertFalse(hasattr(native_core_realtime, "update_message"))
                self.assertFalse(hasattr(native_core_realtime, "delete_message"))

                native_core_realtime.close_account(handle)


if __name__ == "__main__":
    unittest.main()
