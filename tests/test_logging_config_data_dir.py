import os
import sys
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close_logging_handlers() -> None:
    # Close handlers to avoid Windows temp dir cleanup failures (FileHandler holds a lock).
    import logging

    for logger_name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(logger_name)
        for h in lg.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            try:
                lg.removeHandler(h)
            except Exception:
                pass


class TestLoggingConfigDataDir(unittest.TestCase):
    def setUp(self):
        self._prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
        self._td = TemporaryDirectory()
        os.environ["WECHAT_TOOL_DATA_DIR"] = self._td.name

        import wechat_decrypt_tool.app_paths as app_paths
        import wechat_decrypt_tool.logging_config as logging_config

        importlib.reload(app_paths)
        importlib.reload(logging_config)

        self.logging_config = logging_config

    def tearDown(self):
        _close_logging_handlers()

        if self._prev_data_dir is None:
            os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
        else:
            os.environ["WECHAT_TOOL_DATA_DIR"] = self._prev_data_dir
        self._td.cleanup()

    def test_setup_logging_uses_wechat_tool_data_dir(self):
        log_file = self.logging_config.setup_logging()

        base = Path(self._td.name) / "output" / "logs"
        self.assertTrue(log_file.is_relative_to(base))
        self.assertTrue(log_file.exists())


if __name__ == "__main__":
    unittest.main()

