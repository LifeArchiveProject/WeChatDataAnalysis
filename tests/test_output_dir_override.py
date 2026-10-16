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


class TestOutputDirOverride(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
        self._prev_output_dir = os.environ.get("WECHAT_TOOL_OUTPUT_DIR")
        self._data_dir = TemporaryDirectory()
        self._output_dir = TemporaryDirectory()
        os.environ["WECHAT_TOOL_DATA_DIR"] = self._data_dir.name
        os.environ["WECHAT_TOOL_OUTPUT_DIR"] = self._output_dir.name

        import wechat_decrypt_tool.app_paths as app_paths
        import wechat_decrypt_tool.key_store as key_store
        import wechat_decrypt_tool.logging_config as logging_config
        import wechat_decrypt_tool.runtime_settings as runtime_settings

        importlib.reload(app_paths)
        importlib.reload(logging_config)
        importlib.reload(runtime_settings)
        importlib.reload(key_store)

        self.app_paths = app_paths
        self.key_store = key_store
        self.logging_config = logging_config
        self.runtime_settings = runtime_settings

    def tearDown(self) -> None:
        _close_logging_handlers()
        if self._prev_data_dir is None:
            os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
        else:
            os.environ["WECHAT_TOOL_DATA_DIR"] = self._prev_data_dir

        if self._prev_output_dir is None:
            os.environ.pop("WECHAT_TOOL_OUTPUT_DIR", None)
        else:
            os.environ["WECHAT_TOOL_OUTPUT_DIR"] = self._prev_output_dir

        self._data_dir.cleanup()
        self._output_dir.cleanup()

    def test_app_paths_prefers_output_dir_override(self) -> None:
        self.assertEqual(self.app_paths.get_output_dir(), Path(self._output_dir.name))
        self.assertEqual(
            self.app_paths.get_output_databases_dir(),
            Path(self._output_dir.name) / "databases",
        )

    def test_logging_runtime_settings_and_key_store_use_output_override(self) -> None:
        log_file = self.logging_config.setup_logging()
        self.assertTrue(log_file.is_relative_to(Path(self._output_dir.name) / "logs"))

        self.runtime_settings.write_backend_port_setting(12001)
        runtime_settings_path = Path(self._output_dir.name) / "runtime_settings.json"
        self.assertTrue(runtime_settings_path.exists())
        self.assertEqual(self.runtime_settings.read_backend_port_setting(), 12001)

        self.key_store.upsert_account_keys_in_store("wxid_test", db_key="abc123")
        key_store_path = Path(self._output_dir.name) / "account_keys.json"
        self.assertTrue(key_store_path.exists())
        self.assertEqual(
            self.key_store.get_account_keys_from_store("wxid_test").get("db_key"),
            "abc123",
        )


if __name__ == "__main__":
    unittest.main()
