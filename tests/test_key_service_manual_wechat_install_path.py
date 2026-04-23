import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


import wechat_decrypt_tool.key_service as key_service


class _FakeWxKey:
    def __init__(self, key: str) -> None:
        self.key = key
        self.initialize_calls: list[int] = []
        self.cleanup_calls = 0

    def initialize_hook(self, pid: int) -> bool:
        self.initialize_calls.append(pid)
        return True

    def get_last_error_msg(self) -> str:
        return ""

    def poll_key_data(self):
        return {"key": self.key}

    def get_status_message(self):
        return None, None

    def cleanup_hook(self) -> None:
        self.cleanup_calls += 1


class TestKeyServiceManualWechatInstallPath(unittest.TestCase):
    def test_get_db_key_workflow_can_use_manual_install_directory(self) -> None:
        fake_wx_key = _FakeWxKey("a" * 64)

        with TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir)
            exe_path = install_dir / "WeChat.exe"
            exe_path.write_bytes(b"")

            with mock.patch.object(
                key_service,
                "wx_key",
                fake_wx_key,
            ), mock.patch.object(
                key_service,
                "detect_wechat_installation",
                side_effect=AssertionError("should not auto-detect when manual path is provided"),
            ), mock.patch.object(
                key_service,
                "_read_wechat_version_from_exe",
                return_value="",
            ), mock.patch.object(
                key_service.WeChatKeyFetcher,
                "kill_wechat",
                autospec=True,
            ) as kill_mock, mock.patch.object(
                key_service.WeChatKeyFetcher,
                "launch_wechat",
                autospec=True,
                return_value=4321,
            ) as launch_mock:
                result = key_service.get_db_key_workflow(wechat_install_path=str(install_dir))

        self.assertEqual(result["db_key"], "a" * 64)
        kill_mock.assert_called_once()
        launch_mock.assert_called_once()
        _, used_exe_path = launch_mock.call_args.args
        self.assertEqual(used_exe_path, str(exe_path))
        self.assertEqual(fake_wx_key.initialize_calls, [4321])
        self.assertEqual(fake_wx_key.cleanup_calls, 1)

    def test_get_db_key_workflow_does_not_require_detected_version(self) -> None:
        fake_wx_key = _FakeWxKey("b" * 64)

        with TemporaryDirectory() as temp_dir:
            exe_path = Path(temp_dir) / "Weixin.exe"
            exe_path.write_bytes(b"")

            with mock.patch.object(
                key_service,
                "wx_key",
                fake_wx_key,
            ), mock.patch.object(
                key_service,
                "detect_wechat_installation",
                return_value={
                    "wechat_exe_path": str(exe_path),
                    "wechat_version": "",
                },
            ), mock.patch.object(
                key_service.WeChatKeyFetcher,
                "kill_wechat",
                autospec=True,
            ), mock.patch.object(
                key_service.WeChatKeyFetcher,
                "launch_wechat",
                autospec=True,
                return_value=2468,
            ):
                result = key_service.get_db_key_workflow()

        self.assertEqual(result["db_key"], "b" * 64)
        self.assertEqual(fake_wx_key.initialize_calls, [2468])
        self.assertEqual(fake_wx_key.cleanup_calls, 1)


if __name__ == "__main__":
    unittest.main()
