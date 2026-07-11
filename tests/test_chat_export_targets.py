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


class _DummyRealtimeConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


class TestChatExportTargets(unittest.TestCase):
    def _seed_contact_db(self, path: Path, *, account: str) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE contact (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
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
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT
                )
                """
            )
            rows = [
                (account, "", "Me", "", 1, 0, "", ""),
                ("wxid_visible", "", "Visible friend", "", 1, 0, "", ""),
                ("wxid_no_session", "", "No session friend", "", 1, 0, "", ""),
                ("wxid_session_hidden", "", "Hidden session friend", "", 1, 0, "", ""),
                ("room_no_session@chatroom", "", "No session group", "", 1, 0, "", ""),
                ("room_hidden@chatroom", "", "Hidden session group", "", 1, 0, "", ""),
                ("gh_official_no_session", "", "Official account", "", 1, 24, "", ""),
                ("wxid_no_messages", "", "No messages friend", "", 1, 0, "", ""),
            ]
            conn.executemany("INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

    def _seed_session_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE SessionTable (
                    username TEXT,
                    is_hidden INTEGER,
                    sort_timestamp INTEGER
                )
                """
            )
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("wxid_visible", 0, 100))
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("wxid_session_hidden", 1, 200))
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("room_hidden@chatroom", 1, 250))
            conn.commit()
        finally:
            conn.close()

    def _seed_message_db(self, path: Path, *, account: str) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
            usernames = [
                account,
                "wxid_visible",
                "wxid_no_session",
                "wxid_session_hidden",
                "room_no_session@chatroom",
                "room_hidden@chatroom",
                "gh_official_no_session",
                "wxid_no_messages",
            ]
            for idx, username in enumerate(usernames, start=1):
                conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (idx, username))

            message_usernames = {
                "wxid_visible": 100,
                "wxid_no_session": 300,
                "wxid_session_hidden": 400,
                "room_no_session@chatroom": 350,
                "room_hidden@chatroom": 450,
                "gh_official_no_session": 360,
            }
            for username, create_time in message_usernames.items():
                table_name = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
                conn.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        local_id INTEGER,
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
                conn.execute(
                    f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (1, 1001, 1, 1, 2, create_time, f"message for {username}", None),
                )
            conn.commit()
        finally:
            conn.close()

    def _prepare_account(self, root: Path) -> Path:
        account = "wxid_account"
        account_dir = root / account
        account_dir.mkdir(parents=True, exist_ok=True)
        self._seed_contact_db(account_dir / "contact.db", account=account)
        self._seed_session_db(account_dir / "session.db")
        self._seed_message_db(account_dir / "message_0.db", account=account)
        return account_dir

    def test_all_scope_includes_contacts_with_messages_missing_from_session_list(self):
        import wechat_decrypt_tool.chat_export_service as svc

        with TemporaryDirectory() as td:
            account_dir = self._prepare_account(Path(td))

            targets = svc._resolve_export_targets(
                account_dir=account_dir,
                scope="all",
                usernames=[],
                include_hidden=False,
                include_official=False,
            )

            self.assertIn("wxid_visible", targets)
            self.assertIn("wxid_no_session", targets)
            self.assertIn("room_no_session@chatroom", targets)
            self.assertNotIn("wxid_session_hidden", targets)
            self.assertNotIn("room_hidden@chatroom", targets)
            self.assertNotIn("gh_official_no_session", targets)
            self.assertNotIn("wxid_no_messages", targets)

    def test_group_single_and_official_filters_apply_to_message_discovered_targets(self):
        import wechat_decrypt_tool.chat_export_service as svc

        with TemporaryDirectory() as td:
            account_dir = self._prepare_account(Path(td))

            groups = svc._resolve_export_targets(
                account_dir=account_dir,
                scope="groups",
                usernames=[],
                include_hidden=False,
                include_official=False,
            )
            singles = svc._resolve_export_targets(
                account_dir=account_dir,
                scope="singles",
                usernames=[],
                include_hidden=False,
                include_official=False,
            )
            with_official = svc._resolve_export_targets(
                account_dir=account_dir,
                scope="all",
                usernames=[],
                include_hidden=False,
                include_official=True,
            )

            self.assertEqual(groups, ["room_no_session@chatroom"])
            self.assertIn("wxid_no_session", singles)
            self.assertNotIn("room_no_session@chatroom", singles)
            self.assertIn("gh_official_no_session", with_official)

    def test_preview_counts_match_bulk_export_targets_including_hidden_sessions(self):
        import wechat_decrypt_tool.chat_export_service as svc

        with TemporaryDirectory() as td:
            account_dir = self._prepare_account(Path(td))

            preview = svc.build_chat_export_targets_preview(
                account_dir=account_dir,
                source="decrypted",
                include_hidden=True,
                include_official=False,
                base_url="http://example.test",
            )
            actual_targets = svc._resolve_export_targets(
                account_dir=account_dir,
                scope="all",
                usernames=[],
                include_hidden=True,
                include_official=False,
            )

            preview_targets = preview["targets"]
            preview_usernames = [item["username"] for item in preview_targets]
            by_username = {item["username"]: item for item in preview_targets}

            self.assertEqual(preview_usernames, actual_targets)
            self.assertEqual(preview["counts"], {"total": 5, "groups": 2, "singles": 3})
            self.assertTrue(by_username["room_hidden@chatroom"]["isHidden"])
            self.assertTrue(by_username["room_hidden@chatroom"]["inSessionList"])
            self.assertFalse(by_username["room_no_session@chatroom"]["inSessionList"])
            self.assertTrue(by_username["room_no_session@chatroom"]["avatar"].startswith("http://example.test/api/chat/avatar?"))

    def test_realtime_preview_does_not_require_decrypted_databases(self):
        import wechat_decrypt_tool.chat_export_service as svc

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            account_dir.mkdir(parents=True, exist_ok=True)
            rt_conn = _DummyRealtimeConn()
            sessions = [
                {"username": "wxid_visible", "is_hidden": 0, "sort_timestamp": 300},
                {"username": "room_visible@chatroom", "is_hidden": 0, "sort_timestamp": 200},
                {"username": "wxid_hidden", "is_hidden": 1, "sort_timestamp": 100},
                {"username": "gh_official", "is_hidden": 0, "sort_timestamp": 50},
            ]

            with (
                patch.object(svc, "_wcdb_get_sessions", return_value=sessions),
                patch.object(
                    svc,
                    "_wcdb_get_display_names",
                    return_value={
                        "wxid_visible": "Realtime friend",
                        "room_visible@chatroom": "Realtime group",
                    },
                ),
                patch.object(svc, "_load_contact_rows", return_value={}),
            ):
                preview = svc.build_chat_export_targets_preview(
                    account_dir=account_dir,
                    source="realtime",
                    rt_conn=rt_conn,
                    include_hidden=False,
                    include_official=False,
                    base_url="http://example.test",
                )

            self.assertFalse((account_dir / "session.db").exists())
            self.assertFalse((account_dir / "contact.db").exists())
            self.assertFalse((account_dir / "message_0.db").exists())
            self.assertEqual(preview["source"], "realtime")
            self.assertEqual(preview["counts"], {"total": 2, "groups": 1, "singles": 1})
            self.assertEqual([item["username"] for item in preview["targets"]], ["wxid_visible", "room_visible@chatroom"])
            self.assertEqual(preview["targets"][0]["displayName"], "Realtime friend")
            self.assertNotIn("wxid_hidden", [item["username"] for item in preview["targets"]])

    def test_realtime_message_iterator_does_not_require_message_databases(self):
        import wechat_decrypt_tool.chat_export_service as svc

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            account_dir.mkdir(parents=True, exist_ok=True)
            rt_conn = _DummyRealtimeConn()
            with patch.object(
                svc,
                "_wcdb_get_messages",
                side_effect=[
                    [
                        {
                            "localId": 7,
                            "serverId": 700,
                            "localType": 1,
                            "sortSeq": 1700000000000,
                            "createTime": 1700000000,
                            "messageContent": "hello from realtime",
                            "compressContent": None,
                            "senderUsername": "wxid_friend",
                        }
                    ],
                    [],
                ],
            ), patch.object(svc, "_wcdb_open_message_cursor", return_value=0):
                rows = list(
                    svc._iter_rows_for_conversation(
                        account_dir=account_dir,
                        conv_username="wxid_friend",
                        start_time=None,
                        end_time=None,
                        source="realtime",
                        rt_conn=rt_conn,
                    )
                )

            self.assertFalse(list(account_dir.glob("message_*.db")))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].raw_text, "hello from realtime")
            self.assertEqual(rows[0].sender_username, "wxid_friend")

    def test_realtime_message_iterator_reads_live_shards_when_native_cache_is_empty(self):
        import wechat_decrypt_tool.chat_export_service as svc

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_account"
            account_dir.mkdir(parents=True, exist_ok=True)
            db_storage = root / "source" / "db_storage"
            message_dir = db_storage / "message"
            message_dir.mkdir(parents=True, exist_ok=True)
            old_db = message_dir / "message_0.db"
            new_db = message_dir / "message_1.db"
            old_db.write_bytes(b"placeholder")
            new_db.write_bytes(b"placeholder")

            username = "wxid_friend"
            table_name = f"Msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
            rt_conn = _DummyRealtimeConn()
            rt_conn.db_storage_dir = db_storage
            rt_conn.native_wxid = account_dir.name

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                db_path = Path(path)
                if "sqlite_master" in sql:
                    return [{"name": table_name}]
                if "FROM Name2Id" in sql:
                    return [{"rowid": 1}]
                if "SELECT COUNT(*) AS count" in sql:
                    return [{"count": 1}]
                if f'FROM "{table_name}"' not in sql:
                    return []
                if db_path == old_db:
                    return [
                        {
                            "local_id": 7,
                            "server_id": 700,
                            "local_type": 1,
                            "sort_seq": 1700000000000,
                            "real_sender_id": 2,
                            "create_time": 1700000000,
                            "message_content": "old shard message",
                            "compress_content": None,
                            "packed_info_data": None,
                            "sender_username": username,
                        }
                    ]
                if db_path == new_db:
                    return [
                        {
                            "local_id": 8,
                            "server_id": 800,
                            "local_type": 1,
                            "sort_seq": 1800000000000,
                            "real_sender_id": 1,
                            "create_time": 1800000000,
                            "message_content": "new shard message",
                            "compress_content": None,
                            "packed_info_data": None,
                            "sender_username": account_dir.name,
                        }
                    ]
                return []

            with (
                patch.object(svc, "_wcdb_get_messages", return_value=[]),
                patch.object(svc, "_wcdb_exec_query", side_effect=fake_exec_query, create=True),
                patch.object(svc, "_resolve_account_db_storage_dir", return_value=db_storage),
            ):
                rows = list(
                    svc._iter_rows_for_conversation(
                        account_dir=account_dir,
                        conv_username=username,
                        start_time=None,
                        end_time=None,
                        source="realtime",
                        rt_conn=rt_conn,
                    )
                )

            self.assertEqual([row.raw_text for row in rows], ["old shard message", "new shard message"])
            self.assertFalse(rows[0].is_sent)
            self.assertTrue(rows[1].is_sent)
            with (
                patch.object(svc, "_wcdb_get_message_count", return_value=0),
                patch.object(svc, "_wcdb_exec_query", side_effect=fake_exec_query),
                patch.object(svc, "_resolve_account_db_storage_dir", return_value=db_storage),
            ):
                estimated = svc._estimate_conversation_message_count(
                    account_dir=account_dir,
                    conv_username=username,
                    start_time=None,
                    end_time=None,
                    source="realtime",
                    rt_conn=rt_conn,
                )
            self.assertEqual(estimated, 2)

    def test_realtime_message_iterator_rejects_unverified_empty_result(self):
        import wechat_decrypt_tool.chat_export_service as svc
        from wechat_decrypt_tool.chat_realtime_reader import RealtimeMessageReadError

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            account_dir.mkdir(parents=True, exist_ok=True)
            rt_conn = _DummyRealtimeConn()
            with (
                patch.object(svc, "_resolve_account_db_storage_dir", return_value=None),
                patch.object(svc, "_wcdb_open_message_cursor", return_value=0),
                patch.object(svc, "_wcdb_get_messages", return_value=[]),
            ):
                with self.assertRaises(RealtimeMessageReadError):
                    list(
                        svc._iter_rows_for_conversation(
                            account_dir=account_dir,
                            conv_username="wxid_friend",
                            start_time=None,
                            end_time=None,
                            source="realtime",
                            rt_conn=rt_conn,
                        )
                    )


if __name__ == "__main__":
    unittest.main()
