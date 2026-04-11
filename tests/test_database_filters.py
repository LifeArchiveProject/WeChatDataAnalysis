import importlib
import logging
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close_logging_handlers() -> None:
    for logger_name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(logger_name)
        for handler in lg.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            try:
                lg.removeHandler(handler)
            except Exception:
                pass


def _seed_sqlite(path: Path, table_name: str = "demo") -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(f"CREATE TABLE {table_name}(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute(f"INSERT INTO {table_name}(value) VALUES ('ok')")
        conn.commit()
    finally:
        conn.close()


class TestDatabaseFilters(unittest.TestCase):
    def test_scan_account_databases_skips_index_databases(self):
        from wechat_decrypt_tool.wechat_decrypt import scan_account_databases_from_path

        with TemporaryDirectory() as td:
            db_storage = Path(td) / "xwechat_files" / "wxid_demo_user" / "db_storage"
            db_storage.mkdir(parents=True, exist_ok=True)

            _seed_sqlite(db_storage / "MSG0.db")
            _seed_sqlite(db_storage / "contact_fts.db")
            _seed_sqlite(db_storage / "favorite_fts.db")
            _seed_sqlite(db_storage / "message_fts.db")
            _seed_sqlite(db_storage / "key_info.db")

            result = scan_account_databases_from_path(str(db_storage))

            self.assertEqual(result["status"], "success")
            self.assertEqual(list(result["account_databases"].keys()), ["wxid_demo"])
            db_names = sorted(db["name"] for db in result["account_databases"]["wxid_demo"])
            self.assertEqual(db_names, ["MSG0.db"])

    def test_collect_account_databases_skips_index_databases(self):
        from wechat_decrypt_tool.wechat_detection import collect_account_databases

        with TemporaryDirectory() as td:
            data_dir = Path(td) / "wxid_demo_user"
            data_dir.mkdir(parents=True, exist_ok=True)

            _seed_sqlite(data_dir / "contact.db", "contact")
            _seed_sqlite(data_dir / "contact_fts.db")
            _seed_sqlite(data_dir / "favorite_fts.db")
            _seed_sqlite(data_dir / "message_fts.db")

            databases = collect_account_databases(str(data_dir), "wxid_demo")
            db_names = sorted(db["name"] for db in databases)
            self.assertEqual(db_names, ["contact.db"])

    def test_chat_account_info_hides_index_and_internal_databases(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.routers.chat as chat_router

                importlib.reload(app_paths)
                importlib.reload(chat_router)

                account_dir = root / "output" / "databases" / "wxid_demo"
                account_dir.mkdir(parents=True, exist_ok=True)

                _seed_sqlite(account_dir / "contact.db", "contact")
                _seed_sqlite(account_dir / "session.db", "session_table")
                _seed_sqlite(account_dir / "message_fts.db")
                _seed_sqlite(account_dir / "chat_search_index.db")
                _seed_sqlite(account_dir / "session_last_message.db")

                result = chat_router.get_chat_account_info("wxid_demo")

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["database_count"], 2)
                self.assertEqual(result["databases"], ["contact.db", "session.db"])
            finally:
                _close_logging_handlers()
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir


if __name__ == "__main__":
    unittest.main()
