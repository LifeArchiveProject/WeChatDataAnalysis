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


class TestChatSourceAuto(unittest.TestCase):
    def test_sessions_auto_prefers_realtime_when_available(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            conn = _DummyConn()

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(
                    chat_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(account_dir)},
                ),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(
                    chat_router,
                    "_wcdb_get_sessions",
                    return_value=[
                        {
                            "username": "wxid_realtime",
                            "summary": "from realtime",
                            "draft": "",
                            "unread_count": 0,
                            "is_hidden": 0,
                            "last_timestamp": 123,
                            "sort_timestamp": 123,
                            "last_msg_type": 1,
                            "last_msg_sub_type": 0,
                        }
                    ],
                ),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_avatar_url_unified", return_value=""),
            ):
                resp = chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=50,
                    include_hidden=True,
                    include_official=True,
                    preview="session",
                    source="auto",
                )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "realtime")
        self.assertEqual((resp.get("sessions") or [])[0].get("username"), "wxid_realtime")
        self.assertEqual((resp.get("sessions") or [])[0].get("lastMessage"), "from realtime")

    def test_sessions_auto_falls_back_to_decrypted_when_realtime_unavailable(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(account_dir / "session.db"))
            try:
                conn.execute(
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
                conn.execute(
                    "INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("wxid_local", 0, 0, "from decrypted", "", 100, 100, 1, 1, 0, "", ""),
                )
                conn.commit()
            finally:
                conn.close()

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", return_value={}),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", side_effect=AssertionError("should not connect")),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_avatar_url_unified", return_value=""),
            ):
                resp = chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=50,
                    include_hidden=True,
                    include_official=True,
                    preview="session",
                    source="auto",
                )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "decrypted")
        self.assertEqual((resp.get("sessions") or [])[0].get("username"), "wxid_local")
        self.assertEqual((resp.get("sessions") or [])[0].get("lastMessage"), "from decrypted")

    def test_messages_auto_reads_realtime_rows_when_available(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            conn = _DummyConn()

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(
                    chat_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(account_dir)},
                ),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(
                    chat_router,
                    "_wcdb_get_messages",
                    return_value=[
                        {
                            "localId": 7,
                            "serverId": 700,
                            "localType": 1,
                            "sortSeq": 1700000000000,
                            "realSenderId": 1,
                            "createTime": 1700000000,
                            "messageContent": "hello from live wcdb",
                            "compressContent": None,
                            "packedInfoData": None,
                            "senderUsername": "wxid_live",
                        }
                    ],
                ),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                resp = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username="wxid_live",
                    account="acc",
                    limit=50,
                    offset=0,
                    order="asc",
                    source="auto",
                )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "realtime")
        self.assertEqual((resp.get("messages") or [])[0].get("content"), "hello from live wcdb")


if __name__ == "__main__":
    unittest.main()
