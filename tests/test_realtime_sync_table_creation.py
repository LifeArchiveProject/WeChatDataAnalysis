import hashlib
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestRealtimeSyncTableCreation(unittest.TestCase):
    def _touch_sqlite(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            # Ensure a valid sqlite file is created.
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
        finally:
            conn.close()

    def test_ensure_creates_msg_table_and_indexes_in_message_db(self):
        from wechat_decrypt_tool.routers import chat as chat_router

        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._touch_sqlite(account_dir / "message_0.db")

            username = "wxid_foo"
            md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
            expected_table = f"Msg_{md5_hex}"

            db_path, table_name = chat_router._ensure_decrypted_message_table(account_dir, username)
            self.assertEqual(table_name, expected_table)
            self.assertEqual(db_path.name, "message_0.db")

            conn = sqlite3.connect(str(db_path))
            try:
                r = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)",
                    (expected_table,),
                ).fetchone()
                self.assertIsNotNone(r, "Msg_<md5> table should be created")

                idx_names = [
                    f"{expected_table}_SENDERID",
                    f"{expected_table}_SERVERID",
                    f"{expected_table}_SORTSEQ",
                    f"{expected_table}_TYPE_SEQ",
                ]
                for idx in idx_names:
                    r = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='index' AND lower(name)=lower(?)",
                        (idx,),
                    ).fetchone()
                    self.assertIsNotNone(r, f"Index {idx} should be created")
            finally:
                conn.close()

    def test_ensure_prefers_biz_message_for_official_accounts(self):
        from wechat_decrypt_tool.routers import chat as chat_router

        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._touch_sqlite(account_dir / "message_0.db")
            self._touch_sqlite(account_dir / "biz_message_0.db")

            username = "gh_12345"
            db_path, _ = chat_router._ensure_decrypted_message_table(account_dir, username)
            self.assertEqual(db_path.name, "biz_message_0.db")

    def test_bulk_ensure_creates_missing_tables(self):
        from wechat_decrypt_tool.routers import chat as chat_router

        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._touch_sqlite(account_dir / "message_0.db")

            usernames = ["wxid_a", "wxid_b"]
            table_map = chat_router._ensure_decrypted_message_tables(account_dir, usernames)
            self.assertEqual(set(table_map.keys()), set(usernames))

            conn = sqlite3.connect(str(account_dir / "message_0.db"))
            try:
                for u in usernames:
                    md5_hex = hashlib.md5(u.encode("utf-8")).hexdigest()
                    expected_table = f"Msg_{md5_hex}"
                    r = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)",
                        (expected_table,),
                    ).fetchone()
                    self.assertIsNotNone(r, f"{expected_table} should be created for {u}")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

