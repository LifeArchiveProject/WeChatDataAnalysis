import hashlib
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import chat as chat_router


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
