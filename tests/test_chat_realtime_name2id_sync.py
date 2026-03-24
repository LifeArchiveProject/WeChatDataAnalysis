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


class _DummyConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


class TestChatRealtimeName2IdSync(unittest.TestCase):
    def test_sync_repairs_name2id_even_without_new_messages(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_friend"
            table_name = f"Msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
            msg_db_path = account_dir / "message_0.db"

            conn = sqlite3.connect(str(msg_db_path))
            try:
                conn.execute("CREATE TABLE Name2Id (user_name TEXT, is_session INTEGER DEFAULT 1)")
                conn.execute(
                    """
                    CREATE TABLE "{table_name}" (
                        local_id INTEGER PRIMARY KEY,
                        server_id INTEGER,
                        local_type INTEGER,
                        sort_seq INTEGER,
                        real_sender_id INTEGER,
                        create_time INTEGER,
                        message_content TEXT,
                        compress_content BLOB,
                        packed_info_data BLOB
                    )
                    """.format(table_name=table_name)
                )
                conn.execute("INSERT INTO Name2Id(rowid, user_name, is_session) VALUES (1, ?, 1)", ("acc",))
                conn.execute("INSERT INTO Name2Id(rowid, user_name, is_session) VALUES (2, ?, 1)", ("wxid_old",))
                conn.execute("INSERT INTO Name2Id(rowid, user_name, is_session) VALUES (5, ?, 1)", ("wxid_gap_tail",))
                conn.execute(
                    f'INSERT INTO "{table_name}" '
                    "(local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content, packed_info_data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (10, 10010, 1, 10, 3, 1710000010, "hello", None, None),
                )
                conn.commit()
            finally:
                conn.close()

            live_rows = [
                {"rowid": 1, "user_name": "acc", "is_session": 1},
                {"rowid": 2, "user_name": "wxid_old", "is_session": 1},
                {"rowid": 3, "user_name": "wxid_missing_a", "is_session": 1},
                {"rowid": 4, "user_name": "wxid_missing_b", "is_session": 1},
                {"rowid": 5, "user_name": "wxid_gap_tail", "is_session": 1},
            ]

            def _fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertTrue(str(path).endswith("message_0.db"))
                if "COUNT(1)" in sql:
                    return [{"c": len(live_rows), "mx": 5}]
                if "ORDER BY rowid ASC" in sql:
                    return list(live_rows)
                raise AssertionError(f"Unexpected SQL: {sql}")

            with (
                patch.object(chat_router, "_resolve_db_storage_message_paths", return_value=(Path(td) / "live_message_0.db", Path(td) / "message_resource.db")),
                patch.object(chat_router, "_wcdb_exec_query", side_effect=_fake_exec_query),
                patch.object(chat_router, "_wcdb_get_messages", return_value=[]),
            ):
                result = chat_router._sync_chat_realtime_messages_for_table(
                    account_dir=account_dir,
                    rt_conn=_DummyConn(),
                    username=username,
                    msg_db_path=msg_db_path,
                    table_name=table_name,
                    max_scan=50,
                    backfill_limit=0,
                )

            self.assertEqual(result.get("inserted"), 0)

            conn = sqlite3.connect(str(msg_db_path))
            try:
                rows = conn.execute("SELECT rowid, user_name FROM Name2Id ORDER BY rowid ASC").fetchall()
            finally:
                conn.close()

            self.assertEqual(
                rows,
                [
                    (1, "acc"),
                    (2, "wxid_old"),
                    (3, "wxid_missing_a"),
                    (4, "wxid_missing_b"),
                    (5, "wxid_gap_tail"),
                ],
            )

    def test_sync_still_inserts_new_messages_when_name2id_is_up_to_date(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            username = "wxid_friend"
            table_name = f"Msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
            msg_db_path = account_dir / "message_0.db"

            conn = sqlite3.connect(str(msg_db_path))
            try:
                conn.execute("CREATE TABLE Name2Id (user_name TEXT, is_session INTEGER DEFAULT 1)")
                conn.execute(
                    """
                    CREATE TABLE "{table_name}" (
                        local_id INTEGER PRIMARY KEY,
                        server_id INTEGER,
                        local_type INTEGER,
                        sort_seq INTEGER,
                        real_sender_id INTEGER,
                        create_time INTEGER,
                        message_content TEXT,
                        compress_content BLOB,
                        packed_info_data BLOB
                    )
                    """.format(table_name=table_name)
                )
                conn.execute("INSERT INTO Name2Id(rowid, user_name, is_session) VALUES (1, ?, 1)", ("acc",))
                conn.execute("INSERT INTO Name2Id(rowid, user_name, is_session) VALUES (2, ?, 1)", (username,))
                conn.execute(
                    f'INSERT INTO "{table_name}" '
                    "(local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content, packed_info_data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (10, 10010, 1, 10, 2, 1710000010, "old", None, None),
                )
                conn.commit()
            finally:
                conn.close()

            session_conn = sqlite3.connect(str(account_dir / "session.db"))
            try:
                session_conn.execute(
                    """
                    CREATE TABLE SessionTable (
                        username TEXT PRIMARY KEY,
                        summary TEXT DEFAULT '',
                        last_timestamp INTEGER DEFAULT 0,
                        sort_timestamp INTEGER DEFAULT 0,
                        last_msg_locald_id INTEGER DEFAULT 0,
                        last_msg_type INTEGER DEFAULT 0,
                        last_msg_sub_type INTEGER DEFAULT 0,
                        last_msg_sender TEXT DEFAULT ''
                    )
                    """
                )
                session_conn.commit()
            finally:
                session_conn.close()

            def _fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertTrue(str(path).endswith("message_0.db"))
                if "COUNT(1)" in sql:
                    return [{"c": 2, "mx": 2}]
                raise AssertionError(f"Unexpected SQL: {sql}")

            live_messages = [
                {
                    "local_id": 11,
                    "server_id": 10011,
                    "local_type": 1,
                    "sort_seq": 11,
                    "real_sender_id": 2,
                    "create_time": 1710000011,
                    "message_content": "new message",
                    "compress_content": None,
                    "sender_username": username,
                }
            ]

            with (
                patch.object(
                    chat_router,
                    "_resolve_db_storage_message_paths",
                    return_value=(Path(td) / "live_message_0.db", Path(td) / "message_resource.db"),
                ),
                patch.object(chat_router, "_wcdb_exec_query", side_effect=_fake_exec_query),
                patch.object(chat_router, "_wcdb_get_messages", side_effect=[list(live_messages)]),
                patch.object(chat_router, "_best_effort_upsert_output_name2id_rows") as mock_upsert_name2id,
            ):
                result = chat_router._sync_chat_realtime_messages_for_table(
                    account_dir=account_dir,
                    rt_conn=_DummyConn(),
                    username=username,
                    msg_db_path=msg_db_path,
                    table_name=table_name,
                    max_scan=50,
                    backfill_limit=0,
                )

            self.assertEqual(result.get("inserted"), 1)
            mock_upsert_name2id.assert_not_called()

            conn = sqlite3.connect(str(msg_db_path))
            try:
                rows = conn.execute(
                    f'SELECT local_id, server_id, real_sender_id, create_time, message_content FROM "{table_name}" ORDER BY local_id ASC'
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(
                rows,
                [
                    (10, 10010, 2, 1710000010, "old"),
                    (11, 10011, 2, 1710000011, "new message"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
