import hashlib
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
        self.native_wxid = "acc"
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

    def test_sessions_auto_reports_realtime_error_when_unavailable(self):
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
                patch.object(
                    chat_router.WCDB_REALTIME,
                    "ensure_connected",
                    side_effect=chat_router.WCDBRealtimeError("Cannot resolve db_storage directory for this account."),
                ),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_avatar_url_unified", return_value=""),
            ):
                with self.assertRaises(chat_router.HTTPException) as cm:
                    chat_router.list_chat_sessions(
                        _DummyRequest(),
                        account="acc",
                        limit=50,
                        include_hidden=True,
                        include_official=True,
                        preview="session",
                        source="auto",
                    )

        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Cannot resolve db_storage", str(cm.exception.detail))

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

    def test_messages_auto_reads_live_message_db_via_exec_query_when_get_messages_is_empty(self):
        with TemporaryDirectory() as td:
            account = "acc"
            username = "8042180652@chatroom"
            account_dir = Path(td) / account
            db_storage = Path(td) / "source" / "db_storage"
            message_dir = db_storage / "message"
            message_dir.mkdir(parents=True, exist_ok=True)
            live_db = message_dir / "message_0.db"
            live_db.write_bytes(b"placeholder")
            account_dir.mkdir(parents=True, exist_ok=True)
            conn = _DummyConn()

            table_name = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertEqual(Path(path), live_db)
                if "sqlite_master" in sql:
                    return [{"name": table_name}]
                if "FROM Name2Id" in sql:
                    return [{"rowid": 1}]
                if f"FROM \"{table_name}\"" in sql:
                    return [
                        {
                            "local_id": 7,
                            "server_id": 700,
                            "local_type": 1,
                            "sort_seq": 1700000000000,
                            "real_sender_id": 2,
                            "create_time": 1700000000,
                            "message_content": "hello from live message db",
                            "compress_content": None,
                            "packed_info_data": None,
                            "sender_username": "wxid_sender",
                        }
                    ]
                return []

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router, "_resolve_account_db_storage_dir", return_value=db_storage),
                patch.object(
                    chat_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(db_storage)},
                ),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(chat_router, "_wcdb_exec_query", side_effect=fake_exec_query),
                patch.object(chat_router, "_wcdb_get_messages", return_value=[]),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                resp = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username=username,
                    account=account,
                    limit=50,
                    offset=0,
                    order="asc",
                    source="auto",
                )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "realtime")
        self.assertEqual((resp.get("messages") or [])[0].get("content"), "hello from live message db")


if __name__ == "__main__":
    unittest.main()
