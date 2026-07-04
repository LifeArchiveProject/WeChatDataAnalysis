import hashlib
import asyncio
import os
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _DummyConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


class _DummyRequest:
    base_url = "http://testserver/"


class TestChatSearchIndexTargets(unittest.TestCase):
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
                ("gh_official_no_session", "", "Official account", "", 1, 24, "", ""),
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
                "gh_official_no_session",
            ]
            for idx, username in enumerate(usernames, start=1):
                conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (idx, username))

            message_usernames = {
                "wxid_visible": "visible searchable text",
                "wxid_no_session": "missing session searchable text",
                "wxid_session_hidden": "hidden searchable text",
                "gh_official_no_session": "official searchable text",
            }
            for username, content in message_usernames.items():
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
                    (1, 1001, 1, 1, 2, 300, content, None),
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

    def _prepare_single_char_account(self, root: Path) -> Path:
        account = "wxid_account"
        username = "wxid_friend"
        account_dir = root / account
        account_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(account_dir / "contact.db"))
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
            conn.execute("INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (account, "", "Me", "", 1, 0, "", ""))
            conn.execute("INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (username, "", "Friend", "", 1, 0, "", ""))
            conn.commit()
        finally:
            conn.close()

        conn = sqlite3.connect(str(account_dir / "session.db"))
        try:
            conn.execute("CREATE TABLE SessionTable (username TEXT, is_hidden INTEGER, sort_timestamp INTEGER)")
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", (username, 0, 1700000003))
            conn.commit()
        finally:
            conn.close()

        conn = sqlite3.connect(str(account_dir / "message_0.db"))
        try:
            conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (1, account))
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (2, username))
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
            rows = [
                (1, 7001, 1, 1, 2, 1700000001, "旧奶茶", None),
                (2, 7002, 1, 2, 2, 1700000002, "其他内容", None),
                (3, 7003, 1, 3, 2, 1700000003, "新奶酪", None),
            ]
            conn.executemany(f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            conn.commit()
        finally:
            conn.close()

        return account_dir

    def test_index_includes_message_backed_contacts_missing_from_session_list(self):
        import wechat_decrypt_tool.chat_search_index as idx
        from wechat_decrypt_tool.chat_helpers import _build_fts_query

        with TemporaryDirectory() as td:
            account_dir = self._prepare_account(Path(td))

            idx._build_worker(account_dir, rebuild=True)

            index_path = idx.get_chat_search_index_db_path(account_dir)
            conn = sqlite3.connect(str(index_path))
            try:
                rows = conn.execute(
                    """
                    SELECT username, is_hidden, is_official
                    FROM message_fts
                    ORDER BY username
                    """
                ).fetchall()
                fts_query = _build_fts_query("missing session")
                default_search_rows = conn.execute(
                    """
                    SELECT username
                    FROM message_fts
                    WHERE message_fts MATCH ?
                      AND CAST(is_hidden AS INTEGER) = 0
                      AND CAST(is_official AS INTEGER) = 0
                    """,
                    (fts_query,),
                ).fetchall()
            finally:
                conn.close()

            by_username = {str(r[0]): (int(r[1] or 0), int(r[2] or 0)) for r in rows}
            default_search_usernames = [str(r[0]) for r in default_search_rows]
            self.assertIn("wxid_visible", by_username)
            self.assertIn("wxid_no_session", by_username)
            self.assertIn("wxid_session_hidden", by_username)
            self.assertIn("gh_official_no_session", by_username)
            self.assertEqual(by_username["wxid_no_session"], (0, 0))
            self.assertEqual(by_username["wxid_session_hidden"], (1, 0))
            self.assertEqual(by_username["gh_official_no_session"], (0, 1))
            self.assertEqual(default_search_usernames, ["wxid_no_session"])

    def test_auto_index_requires_local_decrypted_databases_and_does_not_call_wcdb(self):
        import wechat_decrypt_tool.chat_search_index as idx

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            account_dir.mkdir(parents=True, exist_ok=True)

            self.assertFalse(hasattr(idx, "_wcdb_get_messages"))
            with idx._BUILD_LOCK:
                idx._BUILD_STATE[idx._account_key(account_dir)] = {"status": "building"}
            idx._build_worker(account_dir, rebuild=True, source="realtime")

            status = idx.get_chat_search_index_status(account_dir, source="realtime")
            self.assertFalse(status["index"]["ready"])
            self.assertEqual(status["index"]["desiredSource"], "decrypted")
            self.assertEqual(status["index"]["build"].get("status"), "error")
            self.assertIn("No sessions found", str(status["index"]["build"].get("error") or ""))

    def test_auto_search_uses_decrypted_index_for_single_character(self):
        import wechat_decrypt_tool.chat_search_index as idx
        from wechat_decrypt_tool.routers import chat as chat_router

        with TemporaryDirectory() as td:
            account_dir = self._prepare_single_char_account(Path(td))
            idx._build_worker(account_dir, rebuild=True, source="auto")

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router, "_wcdb_get_messages", side_effect=AssertionError("search must use decrypted index")),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                resp = asyncio.run(
                    chat_router.search_chat_messages(
                        _DummyRequest(),
                        q="奶",
                        account="wxid_account",
                        limit=10,
                        offset=0,
                        source="auto",
                    )
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("source"), "decrypted_index")
            self.assertEqual(len(resp.get("hits") or []), 2)
            self.assertIn("新奶酪", (resp.get("hits") or [])[0].get("content"))

    def test_high_frequency_single_character_search_uses_recent_probe(self):
        import wechat_decrypt_tool.chat_search_index as idx
        from wechat_decrypt_tool.routers import chat as chat_router

        with TemporaryDirectory() as td:
            account_dir = self._prepare_single_char_account(Path(td))
            idx._build_worker(account_dir, rebuild=True, source="auto")

            index_path = idx.get_chat_search_index_db_path(account_dir)
            conn = sqlite3.connect(str(index_path))
            try:
                token_row = conn.execute(
                    "SELECT doc_count FROM message_token_stats WHERE token=?",
                    ("奶",),
                ).fetchone()
                self.assertIsNotNone(token_row)
                self.assertEqual(int(token_row[0]), 2)
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM message_meta").fetchone()[0],
                    3,
                )
            finally:
                conn.close()

            with (
                patch.dict(os.environ, {"WECHAT_CHAT_SEARCH_SINGLE_CHAR_RECENT_MIN_DOCS": "1"}),
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router, "_wcdb_get_messages", side_effect=AssertionError("search must use decrypted index")),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                resp = asyncio.run(
                    chat_router.search_chat_messages(
                        _DummyRequest(),
                        q="奶",
                        account="wxid_account",
                        limit=10,
                        offset=0,
                        source="auto",
                    )
                )

            self.assertEqual(resp.get("status"), "success")
            self.assertEqual(resp.get("source"), "decrypted_index")
            self.assertEqual(resp.get("indexQueryMode"), "single_char_recent_probe")
            hits = resp.get("hits") or []
            self.assertEqual([h.get("localId") for h in hits], [3, 1])
            self.assertIn("新奶酪", hits[0].get("content"))


if __name__ == "__main__":
    unittest.main()
