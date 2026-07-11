import hashlib
import sqlite3
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import chat as chat_router


class _FakeRealtimeConnection:
    handle = 1

    def __init__(self) -> None:
        self.lock = threading.Lock()


def _msg_table_name(username: str) -> str:
    md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
    return f"Msg_{md5_hex}"


def _seed_message_db(path: Path, *, username: str, rows: list[tuple[int, int]]) -> None:
    """rows: [(create_time, sort_seq), ...]"""
    table = _msg_table_name(username)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            f"""
            CREATE TABLE "{table}"(
                local_id INTEGER PRIMARY KEY AUTOINCREMENT,
                create_time INTEGER,
                sort_seq INTEGER
            )
            """
        )
        for create_time, sort_seq in rows:
            conn.execute(
                f'INSERT INTO "{table}"(create_time, sort_seq) VALUES (?, ?)',
                (int(create_time), int(sort_seq)),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_message_db_full(path: Path, *, username: str, rows: list[tuple[int, int, str]]) -> None:
    """rows: [(create_time, sort_seq, text), ...] - minimal schema for /api/chat/messages/around."""

    table = _msg_table_name(username)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            f"""
            CREATE TABLE "{table}"(
                local_id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                local_type INTEGER,
                sort_seq INTEGER,
                real_sender_id INTEGER,
                create_time INTEGER,
                message_content TEXT,
                compress_content BLOB
            )
            """
        )
        for create_time, sort_seq, text in rows:
            conn.execute(
                f'INSERT INTO "{table}"(server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content) '
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (0, 1, int(sort_seq), 0, int(create_time), str(text), None),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_contact_db_minimal(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE contact (
                username TEXT,
                remark TEXT,
                nick_name TEXT,
                alias TEXT,
                big_head_url TEXT,
                small_head_url TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE stranger (
                username TEXT,
                remark TEXT,
                nick_name TEXT,
                alias TEXT,
                big_head_url TEXT,
                small_head_url TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


class TestChatMessageCalendarHeatmap(unittest.TestCase):
    def test_daily_counts_aggregates_per_day_and_respects_month_range(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_test_user"

            ts_jan31_23 = int(datetime(2026, 1, 31, 23, 0, 0).timestamp())
            ts_feb01_10 = int(datetime(2026, 2, 1, 10, 0, 0).timestamp())
            ts_feb14_12 = int(datetime(2026, 2, 14, 12, 0, 0).timestamp())

            _seed_message_db(
                account_dir / "message.db",
                username=username,
                rows=[
                    (ts_jan31_23, 0),
                    (ts_feb01_10, 5),
                    (ts_feb01_10, 2),
                    (ts_feb14_12, 0),
                ],
            )

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = chat_router.get_chat_message_daily_counts(
                    username=username,
                    year=2026,
                    month=2,
                    account="acc",
                    source="decrypted",
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("username"), username)
            self.assertEqual(resp.get("year"), 2026)
            self.assertEqual(resp.get("month"), 2)

            counts = resp.get("counts") or {}
            self.assertEqual(counts.get("2026-02-01"), 2)
            self.assertEqual(counts.get("2026-02-14"), 1)
            self.assertIsNone(counts.get("2026-01-31"))

            self.assertEqual(resp.get("total"), 3)
            self.assertEqual(resp.get("max"), 2)

    def test_anchor_day_picks_earliest_by_create_time_then_sort_seq_then_local_id(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_test_user"

            ts_jan31_23 = int(datetime(2026, 1, 31, 23, 0, 0).timestamp())
            ts_feb01_10 = int(datetime(2026, 2, 1, 10, 0, 0).timestamp())

            _seed_message_db(
                account_dir / "message.db",
                username=username,
                rows=[
                    (ts_jan31_23, 0),  # local_id = 1
                    (ts_feb01_10, 5),  # local_id = 2
                    (ts_feb01_10, 2),  # local_id = 3  <- expected (sort_seq smaller)
                ],
            )

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = chat_router.get_chat_message_anchor(
                    username=username,
                    kind="day",
                    account="acc",
                    date="2026-02-01",
                    source="decrypted",
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("kind"), "day")
            self.assertEqual(resp.get("date"), "2026-02-01")
            anchor_id = str(resp.get("anchorId") or "")
            self.assertTrue(anchor_id.startswith("message:"), anchor_id)
            self.assertTrue(anchor_id.endswith(":3"), anchor_id)

    def test_anchor_first_picks_global_earliest(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_test_user"

            ts_jan31_23 = int(datetime(2026, 1, 31, 23, 0, 0).timestamp())
            ts_feb01_10 = int(datetime(2026, 2, 1, 10, 0, 0).timestamp())

            _seed_message_db(
                account_dir / "message.db",
                username=username,
                rows=[
                    (ts_feb01_10, 2),  # local_id = 1
                    (ts_jan31_23, 0),  # local_id = 2, but earlier create_time -> should win even if local_id bigger
                ],
            )

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = chat_router.get_chat_message_anchor(
                    username=username,
                    kind="first",
                    account="acc",
                    source="decrypted",
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("kind"), "first")
            anchor_id = str(resp.get("anchorId") or "")
            self.assertTrue(anchor_id.startswith("message:"), anchor_id)
            self.assertTrue(anchor_id.endswith(":2"), anchor_id)

    def test_anchor_day_empty_returns_empty_status(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_test_user"
            ts_feb01_10 = int(datetime(2026, 2, 1, 10, 0, 0).timestamp())

            _seed_message_db(account_dir / "message.db", username=username, rows=[(ts_feb01_10, 0)])

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = chat_router.get_chat_message_anchor(
                    username=username,
                    kind="day",
                    account="acc",
                    date="2026-02-02",
                    source="decrypted",
                )

            self.assertEqual(resp.get("status"), "empty")
            self.assertEqual(resp.get("anchorId"), "")

    def test_around_can_span_multiple_message_dbs_for_pagination(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_test_user"
            table = _msg_table_name(username)

            # Anchor in message.db, next message in message_1.db
            _seed_message_db_full(
                account_dir / "message.db",
                username=username,
                rows=[(1000, 0, "A")],  # local_id=1
            )
            _seed_message_db_full(
                account_dir / "message_1.db",
                username=username,
                rows=[(2000, 0, "B")],  # local_id=1
            )
            _seed_contact_db_minimal(account_dir / "contact.db")

            app = FastAPI()
            app.include_router(chat_router.router)
            client = TestClient(app)

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = client.get(
                    "/api/chat/messages/around",
                    params={
                        "account": "acc",
                        "username": username,
                        "anchor_id": f"message:{table}:1",
                        "before": 0,
                        "after": 10,
                        "source": "decrypted",
                    },
                )

            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("username"), username)
            self.assertEqual(data.get("anchorId"), f"message:{table}:1")
            self.assertEqual(data.get("anchorIndex"), 0)

            msgs = data.get("messages") or []
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0].get("id"), f"message:{table}:1")
            self.assertEqual(msgs[1].get("id"), f"message_1:{table}:1")

    def test_realtime_daily_counts_uses_wcdb_rows(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            username = "wxid_test_user"

            ts_feb01_10 = int(datetime(2026, 2, 1, 10, 0, 0).timestamp())
            ts_feb01_11 = int(datetime(2026, 2, 1, 11, 0, 0).timestamp())
            ts_feb14_12 = int(datetime(2026, 2, 14, 12, 0, 0).timestamp())
            ts_mar01_00 = int(datetime(2026, 3, 1, 0, 0, 0).timestamp())
            rows = [
                {"local_id": 4, "create_time": ts_mar01_00},
                {"local_id": 3, "create_time": ts_feb14_12},
                {"local_id": 2, "create_time": ts_feb01_11},
                {"local_id": 1, "create_time": ts_feb01_10},
            ]

            def fake_get_messages(_handle, _username, *, limit=50, offset=0):
                return rows[int(offset) : int(offset) + int(limit)]

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=_FakeRealtimeConnection()),
                patch.object(chat_router, "_wcdb_get_messages", side_effect=fake_get_messages),
            ):
                resp = chat_router.get_chat_message_daily_counts(
                    username=username,
                    year=2026,
                    month=2,
                    account="acc",
                    source="realtime",
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("source"), "realtime")
            self.assertEqual(resp.get("counts"), {"2026-02-14": 1, "2026-02-01": 2})
            self.assertEqual(resp.get("total"), 3)
            self.assertEqual(resp.get("max"), 2)

    def test_realtime_anchor_day_and_around_use_wcdb_rows(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            _seed_contact_db_minimal(account_dir / "contact.db")
            username = "wxid_test_user"
            table = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
            ts_feb01_10 = int(datetime(2026, 2, 1, 10, 0, 0).timestamp())
            ts_feb01_11 = int(datetime(2026, 2, 1, 11, 0, 0).timestamp())
            ts_feb01_12 = int(datetime(2026, 2, 1, 12, 0, 0).timestamp())
            ts_feb01_13 = int(datetime(2026, 2, 1, 13, 0, 0).timestamp())

            rows = [
                {"local_id": 4, "server_id": 0, "local_type": 1, "sort_seq": 0, "real_sender_id": 0, "create_time": ts_feb01_13, "message_content": "D", "compress_content": None, "sender_username": ""},
                {"local_id": 3, "server_id": 0, "local_type": 1, "sort_seq": 0, "real_sender_id": 0, "create_time": ts_feb01_12, "message_content": "C", "compress_content": None, "sender_username": ""},
                {"local_id": 2, "server_id": 0, "local_type": 1, "sort_seq": 0, "real_sender_id": 0, "create_time": ts_feb01_11, "message_content": "B", "compress_content": None, "sender_username": ""},
                {"local_id": 1, "server_id": 0, "local_type": 1, "sort_seq": 0, "real_sender_id": 0, "create_time": ts_feb01_10, "message_content": "A", "compress_content": None, "sender_username": ""},
            ]

            def fake_get_messages(_handle, _username, *, limit=50, offset=0):
                return rows[int(offset) : int(offset) + int(limit)]

            fake_rt = _FakeRealtimeConnection()
            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=fake_rt),
                patch.object(chat_router, "_wcdb_get_messages", side_effect=fake_get_messages),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
            ):
                anchor = chat_router.get_chat_message_anchor(
                    username=username,
                    kind="day",
                    account="acc",
                    date="2026-02-01",
                    source="realtime",
                )

                app = FastAPI()
                app.include_router(chat_router.router)
                client = TestClient(app)
                resp = client.get(
                    "/api/chat/messages/around",
                    params={
                        "account": "acc",
                        "username": username,
                        "anchor_id": anchor.get("anchorId"),
                        "before": 1,
                        "after": 1,
                        "source": "realtime",
                    },
                )

            self.assertEqual(anchor.get("status"), "success")
            self.assertEqual(anchor.get("source"), "realtime")
            self.assertEqual(anchor.get("anchorId"), f"realtime_acc:{table}:1")
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()
            self.assertEqual(data.get("source"), "realtime")
            self.assertEqual(data.get("anchorId"), f"realtime_acc:{table}:1")
            self.assertEqual(data.get("anchorIndex"), 0)
            self.assertEqual([m.get("content") for m in data.get("messages") or []], ["A", "B"])

    def test_realtime_first_anchor_uses_exec_query_without_scanning_messages(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            db_storage_dir = Path(td) / "db_storage"
            message_dir = db_storage_dir / "message"
            message_dir.mkdir(parents=True, exist_ok=True)
            message_db_path = message_dir / "message.db"
            message_db_path.touch()

            username = "wxid_test_user"
            table = _msg_table_name(username)
            first_ts = int(datetime(2020, 1, 2, 3, 4, 5).timestamp())
            executed_sql: list[str] = []

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertEqual(Path(path), message_db_path)
                executed_sql.append(str(sql))
                if "sqlite_master" in sql:
                    return [{"name": table}]
                if "ORDER BY create_time ASC" in sql and "LIMIT 1" in sql:
                    return [{"local_id": 7, "create_time": first_ts, "sort_seq": 3}]
                raise AssertionError(f"unexpected SQL: {sql}")

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router, "_resolve_account_db_storage_dir", return_value=db_storage_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=_FakeRealtimeConnection()),
                patch.object(chat_router, "_wcdb_exec_query", side_effect=fake_exec_query),
                patch.object(
                    chat_router,
                    "_wcdb_get_messages",
                    side_effect=AssertionError("first anchor must not scan the conversation"),
                ),
            ):
                resp = chat_router.get_chat_message_anchor(
                    username=username,
                    kind="first",
                    account="acc",
                    source="realtime",
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("source"), "realtime")
            self.assertEqual(resp.get("anchorId"), f"message:{table}:7")
            self.assertEqual(resp.get("createTime"), first_ts)
            self.assertEqual(resp.get("scannedMessages"), 1)
            self.assertTrue(any("ORDER BY create_time ASC" in sql for sql in executed_sql))

    def test_realtime_first_context_uses_bounded_exec_queries_without_scanning_messages(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            db_storage_dir = Path(td) / "db_storage"
            message_dir = db_storage_dir / "message"
            message_dir.mkdir(parents=True, exist_ok=True)
            message_db_path = message_dir / "message.db"
            username = "wxid_test_user"
            table = _msg_table_name(username)
            _seed_message_db_full(
                message_db_path,
                username=username,
                rows=[
                    (1000, 0, "A"),
                    (2000, 0, "B"),
                    (3000, 0, "C"),
                    (4000, 0, "D"),
                ],
            )
            conn = sqlite3.connect(str(message_db_path))
            try:
                conn.execute("CREATE TABLE Name2Id (user_name TEXT)")
                conn.commit()
            finally:
                conn.close()
            _seed_contact_db_minimal(account_dir / "contact.db")

            executed_sql: list[str] = []

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertEqual(Path(path), message_db_path)
                executed_sql.append(str(sql))
                live = sqlite3.connect(str(path))
                live.row_factory = sqlite3.Row
                try:
                    return [dict(row) for row in live.execute(sql).fetchall()]
                finally:
                    live.close()

            fake_rt = _FakeRealtimeConnection()
            app = FastAPI()
            app.include_router(chat_router.router)
            client = TestClient(app)
            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router, "_resolve_account_db_storage_dir", return_value=db_storage_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=fake_rt),
                patch.object(chat_router, "_wcdb_exec_query", side_effect=fake_exec_query),
                patch.object(
                    chat_router,
                    "_wcdb_get_messages",
                    side_effect=AssertionError("bounded context must not scan the conversation"),
                ),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
            ):
                anchor = chat_router.get_chat_message_anchor(
                    username=username,
                    kind="first",
                    account="acc",
                    source="realtime",
                )
                resp = client.get(
                    "/api/chat/messages/around",
                    params={
                        "account": "acc",
                        "username": username,
                        "anchor_id": anchor.get("anchorId"),
                        "before": 2,
                        "after": 2,
                        "source": "realtime",
                    },
                )

            self.assertEqual(anchor.get("anchorId"), f"message:{table}:1")
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()
            self.assertEqual(data.get("anchorId"), f"message:{table}:1")
            self.assertEqual(data.get("anchorIndex"), 0)
            self.assertEqual([item.get("content") for item in data.get("messages") or []], ["A", "B", "C"])
            self.assertLessEqual(int(data.get("scannedMessages") or 0), 3)
            self.assertTrue(any("m.create_time > 1000" in sql and "LIMIT 2" in sql for sql in executed_sql))

    def test_realtime_search_uses_decrypted_index_rows(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            _seed_contact_db_minimal(account_dir / "contact.db")
            username = "wxid_test_user"

            conn = sqlite3.connect(str(account_dir / "session.db"))
            try:
                conn.execute("CREATE TABLE SessionTable (username TEXT, is_hidden INTEGER)")
                conn.execute("INSERT INTO SessionTable(username, is_hidden) VALUES (?, ?)", (username, 0))
                conn.commit()
            finally:
                conn.close()
            _seed_message_db_full(
                account_dir / "message_0.db",
                username=username,
                rows=[
                    (2000, 2, "newest needle message"),
                    (1000, 1, "older unrelated"),
                ],
            )

            import wechat_decrypt_tool.chat_search_index as idx

            idx._build_worker(account_dir, rebuild=True, source="realtime")

            app = FastAPI()
            app.include_router(chat_router.router)
            client = TestClient(app)
            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=_FakeRealtimeConnection()),
                patch.object(chat_router, "_wcdb_get_messages", side_effect=AssertionError("search must use decrypted index")),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
            ):
                resp = client.get(
                    "/api/chat/search",
                    params={
                        "account": "acc",
                        "username": username,
                        "q": "needle",
                        "source": "realtime",
                    },
                )

            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()
            self.assertEqual(data.get("source"), "decrypted_index")
            self.assertEqual(data.get("freshness", {}).get("kind"), "snapshot")
            hits = data.get("hits") or []
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].get("content"), "newest needle message")
