import json
import sqlite3
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import sns_full_sync
from wechat_decrypt_tool.routers import sns as sns_router


class _FakeConnection:
    def __init__(self, db_storage_dir: Path):
        self.handle = 1
        self.db_storage_dir = Path(db_storage_dir)
        self.lock = threading.RLock()


def _sqlite_query(_connection, source_path: Path, sql: str):
    conn = sqlite3.connect(str(source_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _wait_job(manager, account_dir: Path, *, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(account_dir)
        if job and job.get("status") not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"朋友圈全量同步任务未在 {timeout} 秒内结束: {manager.get(account_dir)}")


def _create_source_db(root: Path, rows, *, with_pack: bool = True, without_rowid: bool = False):
    source_dir = root / "sns"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "sns.db"
    conn = sqlite3.connect(str(source_path))
    try:
        pack_sql = ", pack_info_buf BLOB" if with_pack else ""
        suffix = " WITHOUT ROWID" if without_rowid else ""
        conn.execute(
            f"CREATE TABLE SnsTimeLine(tid INTEGER PRIMARY KEY, user_name TEXT, content TEXT{pack_sql}){suffix}"
        )
        if with_pack:
            conn.executemany(
                "INSERT INTO SnsTimeLine(tid, user_name, content, pack_info_buf) VALUES (?, ?, ?, ?)",
                rows,
            )
        else:
            conn.executemany(
                "INSERT INTO SnsTimeLine(tid, user_name, content) VALUES (?, ?, ?)",
                rows,
            )
        conn.commit()
    finally:
        conn.close()
    return source_path


class TestSnsFullSync(unittest.TestCase):
    def _run_with_source(self, manager, account_dir: Path, source_root: Path, *, events=None):
        connection = _FakeConnection(source_root)
        event_list = events if events is not None else []
        with (
            mock.patch.object(sns_full_sync.WCDB_REALTIME, "ensure_connected", return_value=connection),
            mock.patch.object(manager, "_query", side_effect=_sqlite_query),
            mock.patch.object(
                sns_full_sync.SNS_REALTIME_AUTOSYNC,
                "publish_external_event",
                side_effect=lambda _account, event: event_list.append(event),
            ),
        ):
            started, reused = manager.start(account_dir)
            self.assertFalse(reused)
            self.assertTrue(started.get("syncId"))
            return _wait_job(manager, account_dir), event_list

    def test_full_sync_reads_more_than_2000_rows_and_second_run_is_unchanged(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "decrypted" / "account-a"
            account_dir.mkdir(parents=True)
            source_root = root / "source-a"
            rows = []
            for tid in range(1, 2206):
                username = "friend-main" if tid <= 1600 else f"friend-{tid % 7}"
                rows.append((tid, username, f"<TimelineObject><type>1</type><id>{tid}</id></TimelineObject>", None))
            for tid in range(-5, 0):
                rows.append((tid, "friend-negative", f"<TimelineObject><type>1</type><id>{tid}</id></TimelineObject>", None))
            _create_source_db(source_root, rows, with_pack=True)

            manager = sns_full_sync.SnsFullSyncManager()
            events = []
            first, events = self._run_with_source(manager, account_dir, source_root, events=events)

            self.assertEqual(first["status"], "done")
            self.assertEqual(first["progress"]["sourceRowsTotal"], len(rows))
            self.assertEqual(first["progress"]["sourceRowsScanned"], len(rows))
            self.assertEqual(first["progress"]["prepared"], len(rows))
            self.assertEqual(first["progress"]["changed"], len(rows))
            self.assertEqual(first["progress"]["percent"], 100)
            self.assertGreater(first["progress"]["batchesCompleted"], 10)

            conn = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                count = conn.execute("SELECT COUNT(*) FROM SnsTimeLine").fetchone()[0]
                main_count = conn.execute(
                    "SELECT COUNT(*) FROM SnsTimeLine WHERE user_name = ?",
                    ("friend-main",),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, len(rows))
            self.assertGreater(main_count, 200)

            progress_events = [event["job"] for event in events if event.get("type") == "full_sync_progress"]
            changed_counts = [job["progress"]["changed"] for job in progress_events]
            percents = [job["progress"]["percent"] for job in progress_events]
            self.assertEqual(changed_counts, sorted(changed_counts))
            self.assertEqual(percents, sorted(percents))
            self.assertLessEqual(max(percents), 99)
            self.assertEqual(events[-1].get("type"), "full_sync_done")
            self.assertEqual(events[-1]["job"]["progress"]["percent"], 100)
            self.assertTrue(events[-1]["job"].get("snapshotVersion"))

            second, _ = self._run_with_source(manager, account_dir, source_root)
            self.assertEqual(second["status"], "done")
            self.assertEqual(second["progress"]["changed"], 0)
            self.assertEqual(second["progress"]["unchanged"], len(rows))

    def test_full_sync_ignores_highwater_and_supports_signed_tid_old_schema(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "decrypted" / "account-b"
            account_dir.mkdir(parents=True)
            (account_dir / "_sns_realtime_sync_state.json").write_text(
                json.dumps({"maxId": "999999"}),
                encoding="utf-8",
            )
            source_root = root / "source-b"
            rows = [
                (-2, "friend-a", "<TimelineObject><type>1</type></TimelineObject>"),
                (1, "friend-a", "<TimelineObject><type>7</type></TimelineObject>"),
                (2, "friend-b", "damaged-but-nonempty"),
                (3, "friend-b", "<TimelineObject><type>1</type></TimelineObject>"),
            ]
            _create_source_db(source_root, rows, with_pack=False, without_rowid=True)

            manager = sns_full_sync.SnsFullSyncManager()
            result, _ = self._run_with_source(manager, account_dir, source_root)

            self.assertEqual(result["status"], "done")
            self.assertEqual(result["progress"]["sourceRowsScanned"], 4)
            self.assertEqual(result["progress"]["prepared"], 2)
            self.assertEqual(result["progress"]["skipped"], 2)
            conn = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                tids = {row[0] for row in conn.execute("SELECT tid FROM SnsTimeLine")}
                columns = {row[1] for row in conn.execute("PRAGMA table_info(SnsTimeLine)")}
            finally:
                conn.close()
            self.assertEqual(tids, {-2, 3})
            self.assertNotIn("pack_info_buf", columns)
            state = json.loads((account_dir / "_sns_realtime_sync_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["maxId"], str((-2) & 0xFFFFFFFFFFFFFFFF))

    def test_full_sync_backfills_rows_below_existing_highwater_without_regressing_it(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "decrypted" / "account-low-history"
            account_dir.mkdir(parents=True)
            state_path = account_dir / "_sns_realtime_sync_state.json"
            state_path.write_text(json.dumps({"maxId": "999999"}), encoding="utf-8")
            source_root = root / "source-low-history"
            rows = [
                (tid, "friend-history", "<TimelineObject><type>1</type></TimelineObject>", None)
                for tid in range(1, 351)
            ]
            _create_source_db(source_root, rows)

            manager = sns_full_sync.SnsFullSyncManager()
            result, _ = self._run_with_source(manager, account_dir, source_root)

            self.assertEqual(result["status"], "done")
            self.assertEqual(result["progress"]["changed"], 350)
            conn = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM SnsTimeLine").fetchone()[0], 350)
            finally:
                conn.close()
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["maxId"], "999999")

    def test_duplicate_reuses_job_other_account_queues_and_cancel_keeps_batches(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_a = root / "decrypted" / "account-a"
            account_b = root / "decrypted" / "account-b"
            account_a.mkdir(parents=True)
            account_b.mkdir(parents=True)
            source_a = root / "source-a"
            source_b = root / "source-b"
            _create_source_db(
                source_a,
                [(tid, "friend-a", "<TimelineObject><type>1</type></TimelineObject>", None) for tid in range(1, 451)],
            )
            _create_source_db(
                source_b,
                [(tid, "friend-b", "<TimelineObject><type>1</type></TimelineObject>", None) for tid in range(1, 11)],
            )
            connections = {
                str(account_a.resolve()): _FakeConnection(source_a),
                str(account_b.resolve()): _FakeConnection(source_b),
            }
            first_batch_entered = threading.Event()
            release_first_batch = threading.Event()
            real_upsert = sns_router._upsert_sns_timeline_rows_to_decrypted_db
            events = []

            def slow_upsert(account_dir, rows, *, source):
                result = real_upsert(account_dir, rows, source=source)
                if Path(account_dir).resolve() == account_a.resolve() and not first_batch_entered.is_set():
                    first_batch_entered.set()
                    release_first_batch.wait(timeout=3)
                return result

            manager = sns_full_sync.SnsFullSyncManager()
            with (
                mock.patch.object(
                    sns_full_sync.WCDB_REALTIME,
                    "ensure_connected",
                    side_effect=lambda account_dir, timeout=15.0: connections[str(Path(account_dir).resolve())],
                ),
                mock.patch.object(manager, "_query", side_effect=_sqlite_query),
                mock.patch.object(sns_router, "_upsert_sns_timeline_rows_to_decrypted_db", side_effect=slow_upsert),
                mock.patch.object(
                    sns_full_sync.SNS_REALTIME_AUTOSYNC,
                    "publish_external_event",
                    side_effect=lambda account, event: events.append((account, event)),
                ),
            ):
                first, reused = manager.start(account_a)
                self.assertFalse(reused)
                self.assertTrue(first_batch_entered.wait(timeout=3))

                duplicate, reused = manager.start(account_a)
                self.assertTrue(reused)
                self.assertEqual(duplicate["syncId"], first["syncId"])

                queued, reused = manager.start(account_b)
                self.assertFalse(reused)
                self.assertEqual(queued["status"], "queued")

                current, accepted = manager.cancel(account_a, "stale-sync-id")
                self.assertFalse(accepted)
                self.assertEqual(current["syncId"], first["syncId"])
                self.assertFalse(current["cancelRequested"])

                cancelling, accepted = manager.cancel(account_a, first["syncId"])
                self.assertTrue(accepted)
                self.assertTrue(cancelling["cancelRequested"])
                release_first_batch.set()

                cancelled = _wait_job(manager, account_a)
                completed = _wait_job(manager, account_b)

            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["progress"]["batchesCompleted"], 1)
            self.assertFalse((account_a / "_sns_realtime_sync_state.json").exists())
            conn = sqlite3.connect(str(account_a / "sns.db"))
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM SnsTimeLine").fetchone()[0], 200)
            finally:
                conn.close()
            self.assertEqual(completed["status"], "done")
            self.assertEqual(completed["progress"]["changed"], 10)
            event_types = [event.get("type") for _account, event in events]
            self.assertIn("full_sync_cancelled", event_types)
            self.assertIn("full_sync_done", event_types)

    def test_failures_use_stable_public_errors(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "account"
            account_dir.mkdir()
            manager = sns_full_sync.SnsFullSyncManager()
            sentinel = "C:/private/path/account-secret"
            events = []
            with (
                mock.patch.object(
                    sns_full_sync.WCDB_REALTIME,
                    "ensure_connected",
                    side_effect=RuntimeError(sentinel),
                ),
                mock.patch.object(
                    sns_full_sync.SNS_REALTIME_AUTOSYNC,
                    "publish_external_event",
                    side_effect=lambda _account, event: events.append(event),
                ),
                mock.patch.object(sns_full_sync.logger, "error") as log_error,
            ):
                manager.start(account_dir)
                result = _wait_job(manager, account_dir)

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"]["code"], "realtime_not_available")
            self.assertEqual(events[-1].get("type"), "full_sync_error")
            rendered = "\n".join(" ".join(map(str, call.args)) for call in log_error.call_args_list)
            self.assertNotIn(sentinel, rendered)

    def test_batch_write_failure_does_not_advance_highwater(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "account"
            account_dir.mkdir()
            source_root = root / "source"
            _create_source_db(
                source_root,
                [(1, "friend", "<TimelineObject><type>1</type></TimelineObject>", None)],
            )
            manager = sns_full_sync.SnsFullSyncManager()
            connection = _FakeConnection(source_root)
            with (
                mock.patch.object(sns_full_sync.WCDB_REALTIME, "ensure_connected", return_value=connection),
                mock.patch.object(manager, "_query", side_effect=_sqlite_query),
                mock.patch.object(
                    sns_router,
                    "_upsert_sns_timeline_rows_to_decrypted_db",
                    return_value={"success": False, "prepared": 1, "changed": 0, "unchanged": 0},
                ),
                mock.patch.object(sns_full_sync.SNS_REALTIME_AUTOSYNC, "publish_external_event"),
            ):
                manager.start(account_dir)
                result = _wait_job(manager, account_dir)

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"]["code"], "snapshot_write_failed")
            self.assertFalse((account_dir / "_sns_realtime_sync_state.json").exists())

    def test_routes_expose_start_status_and_exact_cancel(self):
        methods_by_path = {
            (getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", ()) or ())))
            for route in sns_router.router.routes
        }
        self.assertIn(("/api/sns/realtime/full_sync", ("POST",)), methods_by_path)
        self.assertIn(("/api/sns/realtime/full_sync/status", ("GET",)), methods_by_path)
        self.assertIn(("/api/sns/realtime/full_sync", ("DELETE",)), methods_by_path)


if __name__ == "__main__":
    unittest.main()
