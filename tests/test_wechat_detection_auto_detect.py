import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWechatDetectionAutoDetect(unittest.TestCase):
    def test_macos_process_probe_accepts_wechat_process_name(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            process_cwd = Path(td) / "runtime"
            data_root = process_cwd / "xwechat_files"
            db_storage = data_root / "wxid_process_demo" / "db_storage"
            db_storage.mkdir(parents=True)

            process = unittest.mock.Mock()
            process.cwd.return_value = str(process_cwd)
            with (
                patch.object(wd.sys, "platform", "darwin"),
                patch.object(wd, "_build_auto_detect_scan_paths", return_value=[]),
                patch.object(wd, "get_process_list", return_value=[(42, "WeChat")]),
                patch.object(wd.psutil, "Process", return_value=process),
            ):
                detected_dirs = wd.auto_detect_wechat_data_dirs()

            self.assertEqual(detected_dirs, [str(data_root)])
            process.cwd.assert_called_once_with()

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

    def test_macos_detects_accounts_nested_under_xwechat_files(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            version_root = Path(td) / "2.0b4.0.9"
            account_dir = version_root / "xwechat_files" / "wxid_demo_abcd"
            db_storage = account_dir / "db_storage"
            db_storage.mkdir(parents=True)
            (db_storage / "contact.db").write_bytes(b"demo")

            with (
                patch.object(wd.sys, "platform", "darwin"),
                patch.object(wd, "_build_auto_detect_scan_paths", return_value=[str(version_root)]),
                patch.object(wd, "get_process_list", return_value=[]),
            ):
                detected_dirs = wd.auto_detect_wechat_data_dirs()
                accounts = wd.detect_wechat_accounts_from_data_root(str(version_root))

            self.assertEqual(detected_dirs, [str(version_root)])
            self.assertEqual([item["account_name"] for item in accounts], ["wxid_demo_abcd"])
            self.assertEqual(accounts[0]["data_dir"], str(account_dir))
            self.assertEqual(accounts[0]["database_count"], 1)


if __name__ == "__main__":
    unittest.main()
