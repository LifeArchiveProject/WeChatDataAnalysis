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

            written = sns_router._write_sns_realtime_sync_state(account_dir, {"maxId": "90"})
            saved = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertTrue(written)
        self.assertEqual(saved.get("maxId"), "100")

    def test_stop_waits_for_main_and_worker_threads(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        main_thread = mock.Mock()
        worker_thread = mock.Mock()
        service._thread = main_thread
        service._states["wxid_test"] = sns_realtime_autosync._AccountState(thread=worker_thread)

        service.stop()

        main_thread.join.assert_called_once()
        worker_thread.join.assert_called_once()

    def test_sns_mtime_signal_ignores_reader_shm_updates(self):
        root = Path("C:/db_storage")
        mtimes = {
            root / "sns" / "sns.db": 100,
            root / "sns" / "sns.db-wal": 200,
            root / "sns" / "sns.db-shm": 999,
        }
        with mock.patch.object(
            sns_realtime_autosync,
            "_mtime_ns",
            side_effect=lambda path: mtimes.get(path, 0),
        ) as mtime_ns:
            observed = sns_realtime_autosync._scan_sns_db_mtime_ns(root)

        self.assertEqual(observed, 200)
        self.assertFalse(any(str(call.args[0]).endswith("-shm") for call in mtime_ns.call_args_list))

    def test_failed_sync_is_retried_without_consuming_source_mtime(self):
        service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
        state = sns_realtime_autosync._AccountState(last_mtime_ns=123, due_at=0.0)
        service._states["wxid_test"] = state

        with mock.patch.object(
            service,
            "_sync_account",
            return_value={"status": "error", "error": "temporary"},
        ):
            before = time.time()
            service._sync_account_runner("wxid_test")

        self.assertEqual(state.last_mtime_ns, 123)
        self.assertGreater(state.due_at, before)
        self.assertEqual(state.retry_count, 1)

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


if __name__ == "__main__":
    unittest.main()
