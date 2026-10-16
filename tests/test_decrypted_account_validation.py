import importlib
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _seed_sqlite(path: Path, table_name: str) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(f"CREATE TABLE {table_name}(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute(f"INSERT INTO {table_name}(value) VALUES ('ok')")
        conn.commit()
    finally:
        conn.close()


class TestDecryptedAccountValidation(unittest.TestCase):
    def test_invalid_header_only_databases_are_ignored(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.media_helpers as media_helpers

                importlib.reload(app_paths)
                importlib.reload(chat_helpers)
                importlib.reload(media_helpers)

                output_dir = root / "output" / "databases"
                bad_dir = output_dir / "wxid_bad"
                bad_dir.mkdir(parents=True, exist_ok=True)
                (bad_dir / "session.db").write_bytes(b"SQLite format 3\x00")
                (bad_dir / "contact.db").write_bytes(b"SQLite format 3\x00")

                good_dir = output_dir / "wxid_good"
                good_dir.mkdir(parents=True, exist_ok=True)
                _seed_sqlite(good_dir / "session.db", "SessionTable")
                _seed_sqlite(good_dir / "contact.db", "contact")

                self.assertEqual(chat_helpers._list_decrypted_accounts(), ["wxid_good"])
                self.assertEqual(media_helpers._list_decrypted_accounts(), ["wxid_good"])
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir


if __name__ == "__main__":
    unittest.main()
