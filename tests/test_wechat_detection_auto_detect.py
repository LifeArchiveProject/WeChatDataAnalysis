import asyncio
import io
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWechatDetectionAutoDetect(unittest.TestCase):
    def test_detection_route_succeeds_when_backend_stdout_uses_cp950(self):
        from wechat_decrypt_tool import wechat_detection as wd
        from wechat_decrypt_tool.routers import wechat_detection as detection_router

        with TemporaryDirectory() as td:
            data_root = Path(td) / "xwechat_files"
            login_dir = data_root / "all_users" / "login" / "wxid_demo"
            login_dir.mkdir(parents=True)
            (login_dir / "key_info.db").write_bytes(b"demo")
            account_dir = data_root / "wxid_demo_suffix"
            db_storage = account_dir / "db_storage"
            db_storage.mkdir(parents=True)
            (db_storage / "contact.db").write_bytes(b"demo")

            cp950_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp950", errors="strict")
            with (
                patch.object(sys, "stdout", cp950_stdout),
                patch.object(wd, "get_process_list", return_value=[]),
            ):
                result = asyncio.run(detection_router.detect_wechat_detailed(str(data_root)))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["statistics"]["total_user_accounts"], 1)
        self.assertEqual(result["data"]["current_account"]["current_account"], "wxid_demo")

    def test_current_account_detection_does_not_write_chinese_debug_text_to_cp950_stdout(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            cp950_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp950", errors="strict")
            with (
                patch.object(sys, "stdout", cp950_stdout),
                patch.object(
                    wd,
                    "parse_global_config",
                    return_value={"wxid": "wxid_demo", "nickname": "demo", "avatar": None},
                ),
            ):
                result = wd.detect_current_logged_in_account(td)

        self.assertEqual(result["current_account"], "wxid_demo")

    def test_recent_key_info_activity_wins_over_stale_global_config(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            data_root = Path(td)
            login_root = data_root / "all_users" / "login"
            stale_dir = login_root / "wxid_stale"
            active_dir = login_root / "wxid_active"
            stale_dir.mkdir(parents=True)
            active_dir.mkdir(parents=True)
            stale_key = stale_dir / "key_info.db"
            active_key = active_dir / "key_info.db"
            stale_key.write_bytes(b"stale")
            active_key.write_bytes(b"active")
            os.utime(stale_key, (100, 100))
            os.utime(active_key, (200, 200))

            with patch.object(
                wd,
                "parse_global_config",
                return_value={"wxid": "wxid_stale", "nickname": "旧账号", "avatar": "old.png"},
            ):
                result = wd.detect_current_logged_in_account(str(data_root))

        self.assertEqual(result["current_account"], "wxid_active")
        self.assertEqual(result["source"], "key_info_mtime")
        self.assertEqual(result["confidence"], "medium")
        self.assertEqual(result["global_config_account"], "wxid_stale")
        self.assertIsNone(result.get("nickname"))
        self.assertIsNone(result.get("avatar"))

    def test_key_info_wal_counts_as_recent_account_activity(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            login_root = Path(td) / "all_users" / "login"
            first_dir = login_root / "wxid_first"
            active_dir = login_root / "wxid_active"
            first_dir.mkdir(parents=True)
            active_dir.mkdir(parents=True)
            first_key = first_dir / "key_info.db"
            active_key = active_dir / "key_info.db"
            active_wal = active_dir / "key_info.db-wal"
            first_key.write_bytes(b"first")
            active_key.write_bytes(b"active")
            active_wal.write_bytes(b"wal")
            os.utime(first_key, (300, 300))
            os.utime(active_key, (100, 100))
            os.utime(active_wal, (400, 400))

            with patch.object(wd, "parse_global_config", return_value=None):
                result = wd.detect_current_logged_in_account(td)

        self.assertEqual(result["current_account"], "wxid_active")
        self.assertEqual(result["latest_time"], 400)
        self.assertEqual(result["source"], "key_info_mtime")
        self.assertEqual(result["confidence"], "medium")
        self.assertIsNone(result["global_config_account"])

    def test_global_config_is_used_as_fallback_and_keeps_profile(self):
        from wechat_decrypt_tool import wechat_detection as wd

        with TemporaryDirectory() as td:
            parsed = {"wxid": "wxid_saved", "nickname": "已保存", "avatar": "saved.png"}
            with patch.object(wd, "parse_global_config", return_value=parsed):
                result = wd.detect_current_logged_in_account(td)

        self.assertEqual(result["current_account"], "wxid_saved")
        self.assertEqual(result["source"], "global_config")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["global_config_account"], "wxid_saved")
        self.assertEqual(result["nickname"], "已保存")
        self.assertEqual(result["avatar"], "saved.png")

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
