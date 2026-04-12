import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWechatDetectionAutoDetect(unittest.TestCase):
    def test_detect_wechat_installation_finds_nested_custom_data_root(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            nested_scan_root = Path(td) / "abc"
            wechat_parent = nested_scan_root / "wechatMSG"
            xwechat_root = wechat_parent / "xwechat_files"

            login_dir = xwechat_root / "all_users" / "login" / "wxid_demo"
            login_dir.mkdir(parents=True, exist_ok=True)
            (login_dir / "key_info.db").write_bytes(b"demo")

            account_dir = xwechat_root / "wxid_demo_nested"
            account_dir.mkdir(parents=True, exist_ok=True)
            (account_dir / "contact.db").write_bytes(b"demo")

            with (
                patch.object(wd, "_build_auto_detect_scan_paths", return_value=[str(nested_scan_root)]),
                patch.object(wd, "get_process_list", return_value=[]),
            ):
                detected_dirs = wd.auto_detect_wechat_data_dirs()
                result = wd.detect_wechat_installation()

            self.assertEqual(detected_dirs, [str(wechat_parent)])
            self.assertEqual(result["total_accounts"], 1)
            self.assertEqual(result["accounts"][0]["account_name"], "wxid_demo")
            self.assertEqual(result["accounts"][0]["data_dir"], str(account_dir))
            self.assertEqual(result["total_databases"], 1)


if __name__ == "__main__":
    unittest.main()
