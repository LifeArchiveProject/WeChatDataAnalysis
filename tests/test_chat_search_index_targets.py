import hashlib
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


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


if __name__ == "__main__":
    unittest.main()
