import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import chat as chat_router


class _DummyRequest:
    base_url = "http://testserver/"


class _DummyConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


def _seed_session_db(session_db_path: Path) -> None:
    conn = sqlite3.connect(str(session_db_path))
    try:
        conn.execute(
            """
            CREATE TABLE SessionTable (
                username TEXT PRIMARY KEY,
                unread_count INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0,
                summary TEXT DEFAULT '',
                draft TEXT DEFAULT '',
                last_timestamp INTEGER DEFAULT 0,
                sort_timestamp INTEGER DEFAULT 0,
                last_msg_locald_id INTEGER DEFAULT 0,
                last_msg_type INTEGER DEFAULT 0,
                last_msg_sub_type INTEGER DEFAULT 0,
                last_msg_sender TEXT DEFAULT '',
                last_sender_display_name TEXT DEFAULT ''
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


class TestChatRealtimeSyncAllUpdatesSenderDisplayName(unittest.TestCase):
    def test_sync_all_upserts_last_sender_display_name(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            _seed_session_db(account_dir / "session.db")

            conn = _DummyConn()
            sessions_rows = [
                {
                    "username": "demo@chatroom",
                    "unread_count": 0,
                    "is_hidden": 0,
                    "summary": "hello",
                    "draft": "",
                    "last_timestamp": 123,
                    "sort_timestamp": 123,
                    "last_msg_type": 1,
                    "last_msg_sub_type": 0,
                    "last_msg_sender": "wxid_demo",
                    "last_sender_display_name": "群名片A",
                    "last_msg_locald_id": 777,
                }
            ]

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(chat_router, "_wcdb_get_sessions", return_value=sessions_rows),
                patch.object(chat_router, "_ensure_decrypted_message_tables", return_value={}),
                patch.object(chat_router, "_should_keep_session", return_value=True),
            ):
                resp = chat_router.sync_chat_realtime_messages_all(
                    _DummyRequest(),
                    account="acc",
                    max_scan=20,
                    include_hidden=True,
                    include_official=True,
                )

            self.assertEqual(resp.get("status"), "success")

            db = sqlite3.connect(str(account_dir / "session.db"))
            try:
                row = db.execute(
                    "SELECT last_sender_display_name, last_msg_sender, last_msg_locald_id FROM SessionTable WHERE username = ? LIMIT 1",
                    ("demo@chatroom",),
                ).fetchone()
            finally:
                db.close()

            self.assertIsNotNone(row)
            self.assertEqual(str(row[0] or ""), "群名片A")
            self.assertEqual(str(row[1] or ""), "wxid_demo")
            self.assertEqual(int(row[2] or 0), 777)


if __name__ == "__main__":
    unittest.main()

