import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import key_service
from wechat_decrypt_tool.routers import keys as keys_router


V4_MODE_ERROR = "Linux 暂不支持 V4 内存扫描获取密钥（需要提权 attach 微信进程），请使用 hook 模式。"


def _as_linux(test_case) -> None:
    """把平台判定固定成 Linux，使断言不依赖跑测试的机器。"""
    for entry in (
        patch.object(key_service, "is_macos", return_value=False),
        patch.object(key_service, "is_linux", return_value=True),
        patch.object(key_service, "is_windows", return_value=False),
        patch.object(keys_router, "is_macos", return_value=False),
        # keys 路由没有导入 is_linux：它只区分「是不是 macOS」与「是不是 Windows」。
        patch.object(keys_router, "is_windows", return_value=False),
    ):
        test_case.enterContext(entry)


class TestLinuxDbKeyFlow(unittest.TestCase):
    def test_linux_key_v4_request_never_offers_a_hook_fallback_dialog(self) -> None:
        """Linux 没有 V4 内存扫描：不得回报 can_fallback_to_hook。

        该字段是前端「内存扫描失败，是否改用 Hook？」弹窗的唯一触发条件；Linux 的
        Hook（fork + TRACEME）并不需要这种两段式兜底，回报它会让用户看到一次
        永远不可能成功的引导。
        """
        _as_linux(self)
        with patch.object(keys_router, "get_db_key_workflow", side_effect=RuntimeError(V4_MODE_ERROR)):
            result = asyncio.run(
                keys_router.get_wechat_db_key(
                    request=None,
                    db_storage_path="/tmp/db_storage",
                    key_mode="key_v4",
                )
            )

        self.assertEqual(result["status"], -1)
        self.assertNotIn("can_fallback_to_hook", result["data"])
        self.assertIn("hook", result["errmsg"])

    def test_windows_key_v4_request_keeps_the_hook_fallback_dialog(self) -> None:
        """Windows 的两段式流程必须保持不变。"""
        with (
            patch.object(keys_router, "is_macos", return_value=False),
            patch.object(keys_router, "is_windows", return_value=True),
            patch.object(keys_router, "get_db_key_workflow", side_effect=RuntimeError("scan failed")),
        ):
            result = asyncio.run(
                keys_router.get_wechat_db_key(
                    request=None,
                    db_storage_path="D:/xwechat_files/wxid/db_storage",
                    key_mode="key_v4",
                )
            )

        self.assertEqual(result["status"], -2)
        self.assertTrue(result["data"]["can_fallback_to_hook"])
        self.assertEqual(result["data"]["method"], "key_v4")

    def test_linux_key_v4_mode_is_rejected_before_any_memory_scan(self) -> None:
        """core 层也必须拒绝 v4：Linux 只有 hook 一条路。"""
        _as_linux(self)
        with self.assertRaises(RuntimeError) as context:
            key_service.get_db_key_workflow(key_mode="key_v4")

        self.assertIn("hook", str(context.exception))

    def test_linux_auto_mode_goes_straight_to_hook(self) -> None:
        _as_linux(self)
        fetcher = MagicMock()
        fetcher.fetch_db_key.return_value = {"db_key": "a" * 64}
        with patch.object(key_service, "WeChatKeyFetcher", return_value=fetcher):
            result = key_service.get_db_key_workflow(key_mode="auto")

        fetcher.fetch_db_key.assert_called_once()
        self.assertEqual(result["method"], "hook")
        self.assertEqual(result["db_key"], "a" * 64)

    def test_linux_unknown_mode_is_rejected(self) -> None:
        _as_linux(self)
        with self.assertRaises(RuntimeError):
            key_service.get_db_key_workflow(key_mode="not-a-mode")


if __name__ == "__main__":
    unittest.main()
