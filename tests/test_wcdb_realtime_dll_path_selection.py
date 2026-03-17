import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import wcdb_realtime


class TestWcdbRealtimeDllPathSelection(unittest.TestCase):
    def setUp(self) -> None:
        wcdb_realtime._WCDB_API_DLL_SELECTED = None

    def tearDown(self) -> None:
        wcdb_realtime._WCDB_API_DLL_SELECTED = None

    def test_resolve_prefers_project_dll_over_weflow(self) -> None:
        weflow_dll = ROOT / "WeFlow" / "resources" / "wcdb_api.dll"
        self.assertTrue(weflow_dll.exists())
        self.assertTrue(wcdb_realtime._DEFAULT_WCDB_API_DLL.exists())

        with patch.dict(os.environ, {"WECHAT_TOOL_WCDB_API_DLL_PATH": str(weflow_dll)}, clear=False):
            resolved = wcdb_realtime._resolve_wcdb_api_dll_path()

        self.assertEqual(
            resolved.resolve(),
            wcdb_realtime._DEFAULT_WCDB_API_DLL.resolve(),
        )

    def test_resolve_accepts_project_packaged_override(self) -> None:
        packaged_dll = ROOT / "desktop" / "resources" / "backend" / "native" / "wcdb_api.dll"
        self.assertTrue(packaged_dll.exists())

        with patch.dict(os.environ, {"WECHAT_TOOL_WCDB_API_DLL_PATH": str(packaged_dll)}, clear=False):
            resolved = wcdb_realtime._resolve_wcdb_api_dll_path()

        self.assertEqual(resolved.resolve(), packaged_dll.resolve())


if __name__ == "__main__":
    unittest.main()
