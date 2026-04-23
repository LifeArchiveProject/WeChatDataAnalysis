import asyncio
import importlib
import logging
import os
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


class TestSavedDbKeySourceValidation(unittest.TestCase):
    def test_get_saved_keys_blocks_legacy_db_key_for_suffixed_wxid_dir(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            db_storage = root / "xwechat_files" / "wxid_demo_abcd" / "db_storage"
            db_storage.mkdir(parents=True, exist_ok=True)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.routers.keys as keys_router

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(keys_router)

                key_store.upsert_account_keys_in_store("wxid_demo", db_key="A" * 64)
                result = asyncio.run(
                    keys_router.get_saved_keys(account="wxid_demo", db_storage_path=str(db_storage))
                )

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["keys"]["db_key"], "")
                self.assertIn("Legacy saved db key is ambiguous", result["keys"]["db_key_blocked_reason"])
            finally:
                _close_logging_handlers()
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir

    def test_get_saved_keys_accepts_source_matched_db_key(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            db_storage = root / "xwechat_files" / "wxid_demo_abcd" / "db_storage"
            db_storage.mkdir(parents=True, exist_ok=True)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.routers.keys as keys_router

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(keys_router)

                key_store.upsert_account_keys_in_store(
                    "wxid_demo",
                    db_key="B" * 64,
                    aliases=["wxid_demo_abcd"],
                    db_key_source_wxid_dir=str(db_storage.parent),
                    db_key_source_db_storage_path=str(db_storage),
                )
                result = asyncio.run(
                    keys_router.get_saved_keys(account="wxid_demo", db_storage_path=str(db_storage))
                )

                self.assertEqual(result["status"], "success")
                self.assertEqual(result["keys"]["db_key"], "B" * 64)
                self.assertEqual(result["keys"]["db_key_store_account"], "wxid_demo_abcd")
                self.assertEqual(result["keys"]["db_key_source_wxid_dir"], str(db_storage.parent))
                self.assertEqual(result["keys"]["db_key_source_db_storage_path"], str(db_storage))
                self.assertEqual(result["keys"]["db_key_blocked_reason"], "")
            finally:
                _close_logging_handlers()
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir


if __name__ == "__main__":
    unittest.main()
