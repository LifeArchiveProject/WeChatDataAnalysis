import sys
import threading
import sqlite3
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


class TestChatSessionsRealtimeSenderPreview(unittest.TestCase):
    def _run(self, sessions_rows: list[dict]) -> dict:
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            conn = _DummyConn()
            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(chat_router, "_wcdb_get_sessions", return_value=sessions_rows),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_should_keep_session", return_value=True),
                patch.object(chat_router, "_avatar_url_unified", return_value="/avatar"),
            ):
                return chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=50,
                    include_hidden=True,
                    include_official=True,
                    preview="latest",
                    source="realtime",
                )

    def test_realtime_sessions_group_summary_prefixed_by_sender_display_name(self):
        resp = self._run(
            [
                {
                    "username": "demo@chatroom",
                    "summary": "hello",
                    "draft": "",
                    "unread_count": 0,
                    "is_hidden": 0,
                    "last_timestamp": 123,
                    "sort_timestamp": 123,
                    "last_msg_type": 1,
                    "last_msg_sub_type": 0,
                    "last_msg_sender": "wxid_demo",
                    "last_sender_display_name": "群名片A",
                }
            ]
        )
        self.assertEqual(resp.get("status"), "success")
        sessions = resp.get("sessions") or []
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].get("lastMessage"), "群名片A: hello")

    def test_realtime_sessions_group_url_summary_keeps_scheme(self):
        resp = self._run(
            [
                {
                    "username": "url@chatroom",
                    "summary": "https://example.com/x",
                    "draft": "",
                    "unread_count": 0,
                    "is_hidden": 0,
                    "last_timestamp": 123,
                    "sort_timestamp": 123,
                    "last_msg_type": 1,
                    "last_msg_sub_type": 0,
                    "last_msg_sender": "wxid_demo",
                    "last_sender_display_name": "群名片B",
                }
            ]
        )
        self.assertEqual(resp.get("status"), "success")
        sessions = resp.get("sessions") or []
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].get("lastMessage"), "群名片B: https://example.com/x")

    def test_sessions_ignore_invalid_utf8_avatar_url(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            session_conn = sqlite3.connect(str(account_dir / "session.db"))
            try:
                session_conn.execute(
                    """
                    CREATE TABLE SessionTable (
                        username TEXT,
                        unread_count INTEGER,
                        is_hidden INTEGER,
                        summary TEXT,
                        draft TEXT,
                        last_timestamp INTEGER,
                        sort_timestamp INTEGER,
                        last_msg_locald_id INTEGER,
                        last_msg_type INTEGER,
                        last_msg_sub_type INTEGER,
                        last_msg_sender TEXT,
                        last_sender_display_name TEXT
                    )
                    """
                )
                session_conn.execute(
                    "INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("wxid_bad_avatar", 0, 0, "hello", "", 100, 100, 1, 1, 0, "", ""),
                )
                session_conn.commit()
            finally:
                session_conn.close()

            contact_conn = sqlite3.connect(str(account_dir / "contact.db"))
            try:
                contact_conn.execute(
                    """
                    CREATE TABLE contact (
                        username TEXT,
                        remark TEXT,
                        nick_name TEXT,
                        alias TEXT,
                        flag INTEGER,
                        big_head_url TEXT,
                        small_head_url TEXT
                    )
                    """
                )
                contact_conn.execute(
                    """
                    CREATE TABLE stranger (
                        username TEXT,
                        remark TEXT,
                        nick_name TEXT,
                        alias TEXT,
                        flag INTEGER,
                        big_head_url TEXT,
                        small_head_url TEXT
                    )
                    """
                )
                contact_conn.execute(
                    """
                    INSERT INTO contact
                    (username, remark, nick_name, alias, flag, big_head_url, small_head_url)
                    VALUES (?, ?, ?, ?, ?, CAST(x'fffe687474703a2f2f6578616d706c652e746573742f612e706e67' AS TEXT), ?)
                    """,
                    ("wxid_bad_avatar", "", "坏头像好友", "", 0, ""),
                )
                contact_conn.commit()
            finally:
                contact_conn.close()

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", return_value={}),
                patch.object(chat_router, "load_session_last_messages", return_value={}),
                patch.object(chat_router, "_load_latest_message_previews", return_value={}),
            ):
                resp = chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=50,
                    include_hidden=True,
                    include_official=True,
                    preview="session",
                )

            self.assertEqual(resp.get("status"), "success")
            sessions = resp.get("sessions") or []
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].get("name"), "坏头像好友")
            self.assertEqual(sessions[0].get("lastMessage"), "hello")
            self.assertIn("/api/chat/avatar", sessions[0].get("avatar") or "")


if __name__ == "__main__":
    unittest.main()
