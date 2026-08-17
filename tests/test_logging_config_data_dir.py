import os
import sys
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


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

    def test_setup_logging_records_runtime_summary(self):
        with (
            patch.object(self.logging_config.sys, "platform", "darwin"),
            patch.object(
                self.logging_config.platform,
                "mac_ver",
                return_value=("15.7.4", ("", "", ""), "arm64"),
            ),
            patch.object(self.logging_config.platform, "release", return_value="24.6.0"),
            patch.object(self.logging_config.platform, "machine", return_value="arm64"),
            patch.object(self.logging_config.platform, "python_version", return_value="3.11.9"),
            patch.object(self.logging_config.sys, "frozen", True, create=True),
        ):
            log_file = self.logging_config.setup_logging()

        from wechat_decrypt_tool import __version__

        text = log_file.read_text(encoding="utf-8")
        self.assertIn(
            "[runtime] "
            f"app_version={__version__} platform=macos os_version=15.7.4 "
            "kernel_release=24.6.0 architecture=arm64 process_bits=64 "
            "python_version=3.11.9 runtime_mode=frozen",
            text,
        )
        self.assertNotIn("hostname=", text)
        self.assertNotIn("serial", text.lower())

    def test_log_file_preserves_account_and_path_context(self):
        log_file = self.logging_config.setup_logging()
        logger = self.logging_config.get_logger("tests.context")
        logger.info(
            "request_account=wxid_private resolved_account=wxid_private "
            "account_dir=wxid_private_a1b2 "
            "mac_path=/Users/alice/Library/Application Support/WCDA "
            r"win_path=C:\Users\bob\Documents\WCDA"
        )
        for handler in logger.root.handlers:
            handler.flush()

        text = log_file.read_text(encoding="utf-8")
        self.assertIn("request_account=wxid_private", text)
        self.assertIn("resolved_account=wxid_private", text)
        self.assertIn("account_dir=wxid_private_a1b2", text)
        self.assertIn("mac_path=/Users/alice/Library/Application Support/WCDA", text)
        self.assertIn(r"win_path=C:\Users\bob\Documents\WCDA", text)

    def test_runtime_probe_failure_does_not_block_logging_or_leak_details(self):
        with (
            patch.object(self.logging_config.sys, "platform", "darwin"),
            patch.object(
                self.logging_config.platform,
                "mac_ver",
                side_effect=RuntimeError("private path: /Users/alice/Library"),
            ),
        ):
            log_file = self.logging_config.setup_logging()

        text = log_file.read_text(encoding="utf-8")
        self.assertIn("[runtime] unavailable error_type=RuntimeError", text)
        self.assertNotIn("private path", text)
        self.assertNotIn("/Users/alice", text)


if __name__ == "__main__":
    unittest.main()

