import sys
import sqlite3
import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import sns_realtime_autosync
from wechat_decrypt_tool.routers import sns as sns_router


class TestSnsRealtimeAutosyncWiring(unittest.TestCase):
    def test_api_starts_and_stops_sns_autosync(self):
        api = (ROOT / "src" / "wechat_decrypt_tool" / "api.py").read_text(encoding="utf-8")

        self.assertIn(
            "from .sns_realtime_autosync import SNS_REALTIME_AUTOSYNC",
            api,
        )
        self.assertIn("SNS_REALTIME_AUTOSYNC.start()", api)
        self.assertIn("SNS_REALTIME_AUTOSYNC.stop()", api)

    def test_sync_state_write_is_atomic_and_never_regresses_highwater(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            state_path = account_dir / "_sns_realtime_sync_state.json"
            state_path.write_text(json.dumps({"maxId": "100"}), encoding="utf-8")
            before_text = state_path.read_text(encoding="utf-8")

            written = sns_router._write_sns_realtime_sync_state(
                account_dir,
                {"maxId": "90", "updatedAt": 999},
            )
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            after_text = state_path.read_text(encoding="utf-8")

        self.assertTrue(written)
        self.assertEqual(saved.get("maxId"), "100")
        self.assertEqual(after_text, before_text)

    def test_stop_waits_for_main_and_worker_threads(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        main_thread = mock.Mock()
        watcher_thread = mock.Mock()
        worker_thread = mock.Mock()
        service._thread = main_thread
        service._watchers["watch-key"] = sns_realtime_autosync._WatchState(
            path=Path("C:/db_storage/sns"),
            thread=watcher_thread,
        )
        service._states["wxid_test"] = sns_realtime_autosync._AccountState(worker=worker_thread)

        service.stop()

        main_thread.join.assert_called_once()
        watcher_thread.join.assert_called_once()
        worker_thread.join.assert_called_once()

    def test_sns_file_filter_only_accepts_source_database_files(self):
        self.assertTrue(sns_realtime_autosync._is_sns_source_path("C:/db_storage/sns/sns.db"))
        self.assertTrue(sns_realtime_autosync._is_sns_source_path("C:/db_storage/sns/sns.db-wal"))
        self.assertTrue(sns_realtime_autosync._is_sns_source_path("C:/db_storage/sns/sns.db-shm"))
        self.assertFalse(sns_realtime_autosync._is_sns_source_path("C:/db_storage/sns/other.db"))

    def test_watchfiles_is_forced_to_native_non_recursive_mode(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        watch_path = Path("C:/db_storage/sns")
        service._watchers["watch-key"] = sns_realtime_autosync._WatchState(path=watch_path)

        with mock.patch.object(sns_realtime_autosync, "watch", return_value=[]) as native_watch:
            service._watch_directory("watch-key")

        kwargs = native_watch.call_args.kwargs
        self.assertEqual(native_watch.call_args.args[0], str(watch_path))
        self.assertFalse(kwargs.get("force_polling"))
        self.assertFalse(kwargs.get("recursive"))
        self.assertFalse(kwargs.get("yield_on_timeout"))
        self.assertEqual(kwargs.get("debounce"), 300)
        self.assertTrue(kwargs["watch_filter"](None, str(watch_path / "sns.db-wal")))
        self.assertFalse(kwargs["watch_filter"](None, str(watch_path / "other.db")))

    def test_pure_shm_event_created_by_active_reader_is_suppressed(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        watch_path = Path("C:/db_storage/sns")
        watch_key = "watch-key"
        service._states["wxid_test"] = sns_realtime_autosync._AccountState(sync_running=True)
        service._watchers[watch_key] = sns_realtime_autosync._WatchState(
            path=watch_path,
            accounts={"wxid_test"},
        )
        changes = {(None, str(watch_path / "sns.db-shm"))}

        with (
            mock.patch.object(sns_realtime_autosync, "watch", return_value=[changes]),
            mock.patch.object(service, "_schedule_sync") as schedule_sync,
        ):
            service._watch_directory(watch_key)

        schedule_sync.assert_not_called()

    def test_nested_source_directory_is_selected_instead_of_snapshot_output(self):
        with TemporaryDirectory() as td:
            db_storage = Path(td) / "db_storage"
            source_sns = db_storage / "sns"
            source_sns.mkdir(parents=True)
            snapshot_output = Path(td) / "output" / "wxid_test"
            snapshot_output.mkdir(parents=True)

            resolved = sns_realtime_autosync._resolve_sns_watch_dir(db_storage)

        self.assertEqual(resolved, source_sns)
        self.assertNotEqual(resolved, snapshot_output)

    def test_empty_or_failed_event_sync_only_retries_twice(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        service._retry_delays = (0.0, 0.0)
        service._states["wxid_test"] = sns_realtime_autosync._AccountState(source_revision=1)
        with mock.patch.object(
            service,
            "_sync_account",
            side_effect=[
                {"status": "noop", "scanned": 0},
                {"status": "error", "error": "temporary"},
                {"status": "ok", "scanned": 20, "changed": 1},
            ],
        ) as sync_account:
            result, superseded = service._sync_with_bounded_retries("wxid_test", 1)

        self.assertFalse(superseded)
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(sync_account.call_count, 3)

    def test_file_events_during_sync_are_coalesced_into_one_trailing_sync(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        entered = threading.Event()
        release = threading.Event()
        revisions = []

        def run_sync(_account, revision):
            revisions.append(revision)
            if revision == 1:
                entered.set()
                release.wait(timeout=2.0)
            return {"status": "ok", "scanned": 20, "changed": 0}, False

        with mock.patch.object(service, "_sync_with_bounded_retries", side_effect=run_sync):
            service._schedule_sync("wxid_test", reason="file_event")
            self.assertTrue(entered.wait(timeout=1.0))
            service._schedule_sync("wxid_test", reason="file_event")
            service._schedule_sync("wxid_test", reason="file_event")
            release.set()
            deadline = time.time() + 2.0
            while service._states["wxid_test"].sync_running and time.time() < deadline:
                time.sleep(0.01)

        self.assertEqual(revisions, [1, 3])
        self.assertFalse(service._states["wxid_test"].sync_running)

    def test_subscriber_queue_keeps_only_latest_event(self):
        class ImmediateLoop:
            @staticmethod
            def call_soon_threadsafe(callback, *args):
                callback(*args)

        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        queue = __import__("asyncio").Queue(maxsize=1)
        service._states["wxid_test"] = sns_realtime_autosync._AccountState(
            subscribers={
                "token": sns_realtime_autosync._Subscriber(loop=ImmediateLoop(), queue=queue)
            }
        )

        service._publish_event("wxid_test", {"type": "change", "changed": 1})
        service._publish_event("wxid_test", {"type": "change", "changed": 2})

        latest = queue.get_nowait()
        self.assertEqual(latest.get("sequence"), 2)
        self.assertEqual(latest.get("changed"), 2)

    def test_real_file_notification_ignores_unrelated_file_and_detects_wal(self):
        with TemporaryDirectory() as td:
            watch_dir = Path(td)
            service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
            service._debounce_ms = 100
            watch_key = sns_realtime_autosync._normalize_watch_key(watch_dir)
            service._states["wxid_test"] = sns_realtime_autosync._AccountState(
                watch_key=watch_key,
                watcher_available=True,
            )
            watcher = sns_realtime_autosync._WatchState(
                path=watch_dir,
                accounts={"wxid_test"},
            )
            service._watchers[watch_key] = watcher
            synced = threading.Event()

            def sync_once(_account, _revision):
                synced.set()
                return {"status": "ok", "scanned": 20, "changed": 1}, False

            with mock.patch.object(service, "_sync_with_bounded_retries", side_effect=sync_once) as sync_call:
                watch_thread = threading.Thread(
                    target=service._watch_directory,
                    args=(watch_key,),
                    daemon=True,
                )
                watcher.thread = watch_thread
                watch_thread.start()
                time.sleep(0.2)

                (watch_dir / "other.db").write_bytes(b"ignored")
                self.assertFalse(synced.wait(timeout=0.35))

                wal_path = watch_dir / "sns.db-wal"
                for index in range(3):
                    wal_path.write_bytes(f"event-{index}".encode("ascii"))
                    time.sleep(0.02)
                self.assertTrue(synced.wait(timeout=2.0))
                time.sleep(0.25)
                service.stop()

        self.assertEqual(sync_call.call_count, 1)

    def test_service_source_contains_no_periodic_mtime_scanner(self):
        source = (ROOT / "src" / "wechat_decrypt_tool" / "sns_realtime_autosync.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("_scan_sns_db_mtime_ns", source)
        self.assertNotIn("WECHAT_TOOL_SNS_AUTOSYNC_INTERVAL_MS", source)
        self.assertIn("force_polling=False", source)

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        build = (ROOT / "desktop" / "scripts" / "build-backend.cjs").read_text(encoding="utf-8")
        entry = (ROOT / "src" / "wechat_decrypt_tool" / "backend_entry.py").read_text(encoding="utf-8")
        self.assertIn('"watchfiles>=1.1.0"', pyproject)
        self.assertIn('"watchfiles"', build)
        self.assertIn("runPackagedWatchfilesSmoke(packagedBackend)", build)
        self.assertIn('"--smoke-watchfiles"', entry)

    def test_mtime_sync_forces_existing_tid_refresh(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        with (
            mock.patch.object(sns_realtime_autosync, "_resolve_account_dir", return_value=Path("C:/output/wxid_test")),
            mock.patch.object(
                sns_realtime_autosync.WCDB_REALTIME,
                "get_status",
                return_value={"dll_present": True, "key_present": True, "db_storage_dir": "C:/db_storage"},
            ),
            mock.patch.object(
                sns_router,
                "sync_sns_realtime_timeline_latest",
                return_value={"status": "ok", "upserted": 1},
            ) as sync_latest,
        ):
            response = service._sync_account("wxid_test")

        self.assertEqual(response.get("status"), "ok")
        sync_latest.assert_called_once_with(account="wxid_test", max_scan=service._max_scan, force=1)

    def test_sync_state_is_not_advanced_when_snapshot_write_fails(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(
                    sns_router,
                    "_wcdb_get_sns_timeline",
                    return_value=[{"id": 42, "username": "wxid_friend", "rawXml": "<TimelineObject />"}],
                ),
                mock.patch.object(
                    sns_router,
                    "_wcdb_exec_query",
                    return_value=[{"tid": 42, "user_name": "wxid_friend", "content": "<TimelineObject />"}],
                ),
                mock.patch.object(sns_router, "_upsert_sns_timeline_rows_to_decrypted_db", return_value=0),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state") as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name)

        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("upserted"), 0)
        write_state.assert_not_called()

    def test_sync_state_is_not_advanced_when_a_new_row_cannot_be_materialized(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(
                    sns_router,
                    "_wcdb_get_sns_timeline",
                    return_value=[{"id": 43, "username": "wxid_friend", "rawXml": ""}],
                ),
                mock.patch.object(sns_router, "_wcdb_exec_query", return_value=[]),
                mock.patch.object(sns_router, "_upsert_sns_timeline_rows_to_decrypted_db", return_value=0),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state") as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name)

        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("missingRequired"), 1)
        write_state.assert_not_called()

    def test_force_sync_requires_existing_tids_to_be_materialized(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router, "_read_sns_realtime_sync_state", return_value={"maxId": "44"}),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(
                    sns_router,
                    "_wcdb_get_sns_timeline",
                    return_value=[
                        {"id": 44, "username": "wxid_friend", "rawXml": ""},
                        {"id": 43, "username": "wxid_friend", "rawXml": "<TimelineObject />"},
                    ],
                ),
                mock.patch.object(
                    sns_router,
                    "_wcdb_exec_query",
                    return_value=[{"tid": 43, "user_name": "wxid_friend", "content": "<TimelineObject />"}],
                ),
                mock.patch.object(sns_router, "_upsert_sns_timeline_rows_to_decrypted_db", return_value=1),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state") as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name, force=1)

        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("missingRequired"), 1)
        write_state.assert_not_called()

    def test_empty_realtime_read_retries_when_snapshot_has_posts(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()
            snapshot = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                snapshot.execute("CREATE TABLE SnsTimeLine (tid INTEGER PRIMARY KEY, user_name TEXT, content TEXT)")
                snapshot.execute(
                    "INSERT INTO SnsTimeLine VALUES (?, ?, ?)",
                    (42, "wxid_friend", "<TimelineObject><type>1</type></TimelineObject>"),
                )
                snapshot.commit()
            finally:
                snapshot.close()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(sns_router, "_wcdb_get_sns_timeline", return_value=[]),
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name, force=1)

        self.assertEqual(response.get("status"), "error")
        self.assertEqual(response.get("error"), "realtime_timeline_empty_with_existing_snapshot")
        self.assertEqual(response.get("snapshotCount"), 1)

    def test_backlog_is_paged_until_the_previous_highwater_is_reached(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )
            first_page = [
                {"id": tid, "username": "wxid_friend", "rawXml": f"<TimelineObject><id>{tid}</id></TimelineObject>"}
                for tid in range(400, 200, -1)
            ]
            second_page = [
                {"id": tid, "username": "wxid_friend", "rawXml": f"<TimelineObject><id>{tid}</id></TimelineObject>"}
                for tid in range(200, 99, -1)
            ]

            def timeline_page(_handle, *, limit, offset, usernames, keyword):
                del limit, usernames, keyword
                return first_page if offset == 0 else second_page

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router, "_read_sns_realtime_sync_state", return_value={"maxId": "100"}),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(sns_router, "_wcdb_get_sns_timeline", side_effect=timeline_page) as get_timeline,
                mock.patch.object(sns_router, "_wcdb_exec_query", return_value=[]),
                mock.patch.object(
                    sns_router,
                    "_upsert_sns_timeline_rows_to_decrypted_db",
                    side_effect=lambda _account, rows, **_kwargs: len(rows),
                ),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state", return_value=True) as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name, force=1)

        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("scanned"), 301)
        self.assertEqual(response.get("upserted"), 301)
        self.assertEqual(get_timeline.call_count, 2)
        self.assertEqual(write_state.call_args.args[1].get("maxId"), "400")

    def test_sync_state_advances_after_complete_snapshot_write(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(
                    sns_router,
                    "_wcdb_get_sns_timeline",
                    return_value=[{"id": 44, "username": "wxid_friend", "rawXml": "<TimelineObject />"}],
                ),
                mock.patch.object(
                    sns_router,
                    "_wcdb_exec_query",
                    return_value=[{"tid": 44, "user_name": "wxid_friend", "content": "<TimelineObject />"}],
                ),
                mock.patch.object(sns_router, "_upsert_sns_timeline_rows_to_decrypted_db", return_value=1),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state", return_value=True) as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name)

        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("upserted"), 1)
        self.assertEqual(write_state.call_args.args[1].get("maxId"), "44")

    def test_idempotent_upsert_does_not_change_snapshot_for_identical_rows(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            account_dir.mkdir()
            db_path = account_dir / "sns.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE SnsTimeLine ("
                    "tid INTEGER PRIMARY KEY, user_name TEXT, content TEXT, pack_info_buf TEXT)"
                )
                conn.execute(
                    "CREATE INDEX idx_sns_timeline_user_tid ON SnsTimeLine(user_name, tid DESC)"
                )
                conn.execute(
                    "INSERT INTO SnsTimeLine VALUES (?, ?, ?, ?)",
                    (42, "wxid_friend", "<TimelineObject />", "comment-v1"),
                )
                conn.commit()
            finally:
                conn.close()

            before_version = sns_router._build_sns_snapshot_status(account_dir).get("version")
            unchanged = sns_router._upsert_sns_timeline_rows_to_decrypted_db(
                account_dir,
                [(42, "wxid_friend", "<TimelineObject />", "comment-v1")],
                source="test",
            )
            after_version = sns_router._build_sns_snapshot_status(account_dir).get("version")

            self.assertTrue(unchanged.get("success"))
            self.assertEqual(unchanged.get("changed"), 0)
            self.assertEqual(unchanged.get("unchanged"), 1)
            self.assertEqual(after_version, before_version)

            changed = sns_router._upsert_sns_timeline_rows_to_decrypted_db(
                account_dir,
                [(42, "wxid_friend", "<TimelineObject />", "comment-v2")],
                source="test",
            )

        self.assertEqual(changed.get("changed"), 1)
        self.assertEqual(changed.get("unchanged"), 0)

    def test_idempotent_upsert_reads_non_utf8_pack_info_as_blob(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            account_dir.mkdir()
            db_path = account_dir / "sns.db"
            invalid_utf8_pack = b"\x0a\x11\x08\xff\xfe\x80\x01\x10\xf5\x06"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "CREATE TABLE SnsTimeLine ("
                    "tid INTEGER PRIMARY KEY, user_name TEXT, content TEXT, pack_info_buf TEXT)"
                )
                conn.execute(
                    "INSERT INTO SnsTimeLine VALUES (?, ?, ?, CAST(? AS TEXT))",
                    (42, "wxid_friend", "<TimelineObject />", invalid_utf8_pack),
                )
                conn.commit()
            finally:
                conn.close()

            result = sns_router._upsert_sns_timeline_rows_to_decrypted_db(
                account_dir,
                [(42, "wxid_friend", "<TimelineObject />", None)],
                source="test-non-utf8-pack",
            )

            conn = sqlite3.connect(str(db_path))
            try:
                stored_pack = conn.execute(
                    "SELECT CAST(pack_info_buf AS BLOB) FROM SnsTimeLine WHERE tid = 42"
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("changed"), 0)
        self.assertEqual(result.get("unchanged"), 1)
        self.assertEqual(stored_pack, invalid_utf8_pack)

    def test_force_sync_materializes_missing_tid_below_existing_highwater(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (source_dir / "sns.db").touch()

            snapshot = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                snapshot.execute(
                    "CREATE TABLE SnsTimeLine ("
                    "tid INTEGER PRIMARY KEY, user_name TEXT, content TEXT, pack_info_buf TEXT)"
                )
                snapshot.execute(
                    "CREATE INDEX idx_sns_timeline_user_tid ON SnsTimeLine(user_name, tid DESC)"
                )
                snapshot.executemany(
                    "INSERT INTO SnsTimeLine VALUES (?, ?, ?, ?)",
                    [
                        (300, "wxid_friend", "<TimelineObject><id>300</id></TimelineObject>", "p300"),
                        (100, "wxid_friend", "<TimelineObject><id>100</id></TimelineObject>", "p100"),
                    ],
                )
                snapshot.commit()
            finally:
                snapshot.close()

            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )
            live_rows = [
                {"id": tid, "username": "wxid_friend", "rawXml": f"<TimelineObject><id>{tid}</id></TimelineObject>"}
                for tid in (300, 200, 100)
            ]
            source_rows = [
                {
                    "tid": tid,
                    "user_name": "wxid_friend",
                    "content": f"<TimelineObject><id>{tid}</id></TimelineObject>",
                    "pack_info_buf": f"p{tid}",
                }
                for tid in (300, 200, 100)
            ]

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router, "_read_sns_realtime_sync_state", return_value={"maxId": "300"}),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(sns_router, "_wcdb_get_sns_timeline", return_value=live_rows),
                mock.patch.object(sns_router, "_wcdb_exec_query", return_value=source_rows),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state") as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(
                    account=account_dir.name,
                    max_scan=20,
                    force=1,
                )

            check = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                inserted = check.execute("SELECT content FROM SnsTimeLine WHERE tid = 200").fetchone()
            finally:
                check.close()

        self.assertEqual(response.get("status"), "ok")
        self.assertEqual(response.get("prepared"), 3)
        self.assertEqual(response.get("changed"), 1)
        self.assertEqual(response.get("unchanged"), 2)
        self.assertEqual(response.get("upserted"), 1)
        self.assertTrue(response.get("snapshotChanged"))
        self.assertTrue(response.get("snapshotVersion"))
        self.assertFalse(response.get("highwaterAdvanced"))
        self.assertIsNotNone(inserted)
        write_state.assert_not_called()

    def test_force_sync_reads_requested_floating_window_and_username(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            source_dir = Path(td) / "db_storage" / "sns"
            account_dir.mkdir()
            source_dir.mkdir(parents=True)
            (account_dir / "sns.db").touch()
            (source_dir / "sns.db").touch()
            realtime_conn = SimpleNamespace(
                handle=object(),
                lock=threading.Lock(),
                db_storage_dir=source_dir.parent,
            )
            live_rows = [
                {
                    "id": 400,
                    "username": "wxid_friend",
                    "rawXml": "<TimelineObject><id>400</id></TimelineObject>",
                }
            ]
            source_rows = [
                {
                    "tid": 400,
                    "user_name": "wxid_friend",
                    "content": "<TimelineObject><id>400</id></TimelineObject>",
                    "pack_info_buf": "p400",
                }
            ]

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router, "_read_sns_realtime_sync_state", return_value={"maxId": "500"}),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(source_dir.parent)},
                ),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected", return_value=realtime_conn),
                mock.patch.object(sns_router, "_wcdb_get_sns_timeline", return_value=live_rows) as get_timeline,
                mock.patch.object(sns_router, "_wcdb_exec_query", return_value=source_rows),
                mock.patch.object(
                    sns_router,
                    "_upsert_sns_timeline_rows_to_decrypted_db",
                    return_value={"success": True, "prepared": 1, "changed": 0, "unchanged": 1},
                ),
                mock.patch.object(sns_router, "_write_sns_realtime_sync_state") as write_state,
            ):
                response = sns_router.sync_sns_realtime_timeline_latest(
                    account=account_dir.name,
                    max_scan=40,
                    force=1,
                    scan_offset=80,
                    usernames="wxid_friend",
                )

        self.assertEqual(response.get("status"), "noop")
        self.assertEqual(response.get("scanOffset"), 80)
        self.assertEqual(response.get("scanLimit"), 40)
        get_timeline.assert_called_once_with(
            realtime_conn.handle,
            limit=40,
            offset=80,
            usernames=["wxid_friend"],
            keyword="",
        )
        write_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
