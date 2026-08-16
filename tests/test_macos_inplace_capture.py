import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure
from wechat_decrypt_tool.macos_inplace_capture import (
    _read_state,
    _safe_backup_from_state,
    _write_state,
    capture_prepared_in_place,
    cleanup_in_place_capture,
    recover_stale_in_place_capture,
)

OFFICIAL_SIGNATURE = {
    "valid": True,
    "ad_hoc": False,
    "team_identifier": "5A4RE8SF68",
    "identifier": "com.tencent.xinWeChat",
}


class TestMacOSInPlaceCapture(unittest.TestCase):
    def test_state_is_atomic_private_and_non_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = _write_state(
                root,
                {
                    "schema_version": 1,
                    "wechat_app_path": "/Applications/WeChat.app",
                    "backup_path": "/Volumes/BackupVolume/backups/WeChat-original.zip",
                },
            )
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertNotIn("passphrase", payload)
            self.assertNotIn("key", payload)
            self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
            self.assertEqual(_read_state(root), payload)

    def test_backup_path_validation_does_not_require_nas_online(self) -> None:
        root = Path("/Volumes/BackupVolume/WCDA/output/wechat-app-backups")
        expected = root / "WeChat-4.1.12-269341-original.zip"
        self.assertEqual(_safe_backup_from_state({"backup_path": str(expected)}, root), expected)

    def test_backup_path_escape_is_rejected(self) -> None:
        root = Path("/Volumes/BackupVolume/WCDA/output/wechat-app-backups")
        with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
            _safe_backup_from_state({"backup_path": "/tmp/WeChat-original.zip"}, root)
        self.assertEqual(context.exception.code, "official_backup_path_unsafe")

    def test_stale_state_restores_then_removes_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            debug_root = Path(temp_dir)
            backup_root = debug_root / "backups"
            backup_root.mkdir()
            backup = backup_root / "WeChat-4.1.12-original.zip"
            backup.touch()
            _write_state(
                debug_root,
                {
                    "schema_version": 1,
                    "wechat_app_path": "/Applications/WeChat.app",
                    "backup_path": str(backup),
                    "version": "4.1.12",
                    "build": "269341",
                    "official_cdhash": "abc123",
                },
            )
            with (
                patch("wechat_decrypt_tool.macos_inplace_capture.normalize_wechat_app_path", return_value=Path("/Applications/WeChat.app")),
                patch(
                    "wechat_decrypt_tool.macos_inplace_capture.restore_official_wechat_if_needed",
                    return_value={"official_wechat_verified": True, "official_wechat_restored": True},
                ) as restore,
                patch("wechat_decrypt_tool.macos_inplace_capture.inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE),
            ):
                result = recover_stale_in_place_capture(
                    "/Applications/WeChat.app", backup_root=backup_root, debug_root=debug_root
                )
            self.assertTrue(result["official_wechat_restored"])
            self.assertFalse((debug_root / "prepared-in-place-capture.json").exists())
            restore.assert_called_once()

    def test_cancel_without_state_verifies_official_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "wechat_decrypt_tool.macos_inplace_capture.normalize_wechat_app_path", return_value=Path("/Applications/WeChat.app")
        ), patch("wechat_decrypt_tool.macos_inplace_capture.inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE):
            result = cleanup_in_place_capture(
                "/Applications/WeChat.app", backup_root=Path(temp_dir) / "backups", debug_root=Path(temp_dir)
            )
        self.assertTrue(result["official_wechat_verified"])
        self.assertFalse(result["official_wechat_restored"])

    def test_capture_failure_always_requests_restore(self) -> None:
        debug_root = Path("/tmp/wcda-inplace-test")
        official = Path("/Applications/WeChat.app")
        failure = MacOSDBKeyCaptureFailure("debug_wechat_not_running", "closed", wechat_modified=True)
        with (
            patch("wechat_decrypt_tool.macos_inplace_capture.normalize_wechat_app_path", return_value=official),
            patch("wechat_decrypt_tool.macos_inplace_capture._require_prepared_process", side_effect=failure),
            patch("wechat_decrypt_tool.macos_inplace_capture.has_pending_in_place_capture", return_value=True),
            patch("wechat_decrypt_tool.macos_inplace_capture._restore_after_terminal_path") as restore,
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure):
                capture_prepared_in_place(
                    official,
                    backup_root=Path("/Volumes/BackupVolume/backups"),
                    probe_db_path=Path("/tmp/message_0.db"),
                    debug_root=debug_root,
                )
        restore.assert_called_once()

    def test_capture_arms_resolved_internal_return_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            debug_root = Path(temp_dir)
            probe = debug_root / "message_0.db"
            probe.write_bytes(bytes(range(256)) * 16)
            (debug_root / "breakpoint-preflight.json").write_text(
                json.dumps({"pid": 321, "pbkdf_locations": 1, "key_return_locations": 1}),
                encoding="utf-8",
            )
            with (
                patch(
                    "wechat_decrypt_tool.macos_inplace_capture.normalize_wechat_app_path",
                    return_value=Path("/Applications/WeChat.app"),
                ),
                patch(
                    "wechat_decrypt_tool.macos_inplace_capture._require_prepared_process",
                    return_value=({}, 321),
                ),
                patch(
                    "wechat_decrypt_tool.macos_inplace_capture.capture_salt_matched_passphrase",
                    return_value="ab" * 32,
                ) as capture,
                patch("wechat_decrypt_tool.macos_inplace_capture._validate_captured_passphrase"),
                patch(
                    "wechat_decrypt_tool.macos_inplace_capture.save_passphrase",
                    return_value=debug_root / "key.json",
                ),
                patch(
                    "wechat_decrypt_tool.macos_inplace_capture._restore_after_terminal_path",
                    return_value={"official_wechat_verified": True, "official_wechat_restored": True},
                ),
            ):
                capture_prepared_in_place(
                    "/Applications/WeChat.app",
                    backup_root=debug_root / "backups",
                    probe_db_path=probe,
                    debug_root=debug_root,
                )

            self.assertTrue(capture.call_args.kwargs["enable_key_return_fallback"])


if __name__ == "__main__":
    unittest.main()
