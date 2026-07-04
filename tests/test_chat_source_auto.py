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
                patch.object(chat_router, "_wcdb_open_message_cursor", return_value=0),
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

    def test_sessions_decrypted_sort_uses_session_last_message_when_session_table_is_stale(self):
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
                    """
                    CREATE TABLE session_last_message (
                        username TEXT PRIMARY KEY,
                        sort_seq INTEGER NOT NULL DEFAULT 0,
                        local_id INTEGER NOT NULL DEFAULT 0,
                        create_time INTEGER NOT NULL DEFAULT 0,
                        local_type INTEGER NOT NULL DEFAULT 0,
                        sender_username TEXT NOT NULL DEFAULT '',
                        preview TEXT NOT NULL DEFAULT '',
                        db_stem TEXT NOT NULL DEFAULT '',
                        table_name TEXT NOT NULL DEFAULT '',
                        built_at INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                # stale_session looks old in SessionTable, but its message-table cache is newest.
                conn.execute(
                    "INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("stale_session", 0, 0, "old summary", "", 1747000000, 1747000000, 1, 1, 0, "", ""),
                )
                conn.execute(
                    "INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("fresh_session", 0, 0, "fresh summary", "", 1750000000, 1750000000, 1, 1, 0, "", ""),
                )
                conn.execute(
                    "INSERT INTO session_last_message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "stale_session",
                        1783180000000,
                        9,
                        1783180000,
                        1,
                        "wxid_sender",
                        "july preview",
                        "message_0",
                        "Msg_demo",
                        1783180100,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_avatar_url_unified", return_value="/avatar"),
            ):
                resp = chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=1,
                    include_hidden=True,
                    include_official=True,
                    preview="session",
                    source="decrypted",
                )

        sessions = resp.get("sessions") or []
        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].get("username"), "stale_session")
        self.assertEqual(sessions[0].get("lastMessage"), "july preview")

    def test_messages_auto_exec_query_merges_all_live_message_db_shards(self):
        with TemporaryDirectory() as td:
            account = "acc"
            username = "8042180652@chatroom"
            account_dir = Path(td) / account
            db_storage = Path(td) / "source" / "db_storage"
            message_dir = db_storage / "message"
            message_dir.mkdir(parents=True, exist_ok=True)
            old_db = message_dir / "message_0.db"
            new_db = message_dir / "message_1.db"
            old_db.write_bytes(b"placeholder-old")
            new_db.write_bytes(b"placeholder-new")
            account_dir.mkdir(parents=True, exist_ok=True)
            conn = _DummyConn()

            table_name = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                db_path = Path(path)
                if "sqlite_master" in sql:
                    return [{"name": table_name}]
                if "FROM Name2Id" in sql:
                    return [{"rowid": 1}]
                if f"FROM \"{table_name}\"" not in sql:
                    return []
                if db_path == old_db:
                    return [
                        {
                            "local_id": 1,
                            "server_id": 100,
                            "local_type": 1,
                            "sort_seq": 1747000000000,
                            "real_sender_id": 2,
                            "create_time": 1747000000,
                            "message_content": "old shard may message",
                            "compress_content": None,
                            "packed_info_data": None,
                            "sender_username": "wxid_sender",
                        }
                    ]
                if db_path == new_db:
                    return [
                        {
                            "local_id": 2,
                            "server_id": 200,
                            "local_type": 1,
                            "sort_seq": 1783180000000,
                            "real_sender_id": 2,
                            "create_time": 1783180000,
                            "message_content": "new shard july message",
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
                    limit=1,
                    offset=0,
                    order="asc",
                    source="auto",
                )

        messages = resp.get("messages") or []
        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "realtime")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].get("content"), "new shard july message")
        self.assertTrue(str(messages[0].get("id") or "").startswith("message_1:"))


if __name__ == "__main__":
    unittest.main()
