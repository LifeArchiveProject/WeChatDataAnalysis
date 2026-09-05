"""Workflow contracts with synthetic pages and a temporary, fake application."""

import json
import os
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import macos_inplace_capture as workflow
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure

OFFICIAL_SIGNATURE = {
    "valid": True, "ad_hoc": False, "team_identifier": "5A4RE8SF68",
    "identifier": "com.tencent.xinWeChat", "cdhash": "abc123",
}
SYNTHETIC_PAGES = {"message": b"m" * 4096, "session": b"s" * 4096}
VALIDATION = {"key_mode": "sqlcipher_passphrase", "validated_roles": ["message", "session"]}
RECOVERY = {"official_wechat_verified": True, "official_wechat_restored": True}


class TestMacOSInPlaceCapture(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.app = self.root / "WeChat.app"
        (self.app / "Contents").mkdir(parents=True)
        (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleShortVersionString": "4.1.12", "CFBundleVersion": "269341",
        }))
        self.debug = self.root / "debug"
        self.debug.mkdir()
        self.backups = self.root / "backups"
        self.backups.mkdir()
        self.enterContext(patch.object(workflow, "normalize_wechat_app_path", return_value=self.app))
        self.acquire = self.enterContext(patch.object(workflow, "_acquire_installation_lock", return_value={"transaction_id": "test-transaction"}))
        self.release = self.enterContext(patch.object(workflow, "_release_installation_lock"))
        self.terminate = self.enterContext(patch.object(workflow, "_terminate_native_capture_processes"))
        self.enterContext(patch.object(workflow, "_candidate_bundle_pids", return_value=[321]))
        # A missed mock must fail here, never inspect/launch/sign/attach a real app.
        self.enterContext(patch("subprocess.run", side_effect=AssertionError("external process execution is forbidden in workflow tests")))
        self.enterContext(patch.object(workflow, "capture_native_wcdb_key", side_effect=AssertionError("native capture must be mocked")))
        self.enterContext(patch.object(workflow, "capture_salt_matched_passphrase", side_effect=AssertionError("LLDB capture must be mocked")))
        self.enterContext(patch.object(workflow, "save_passphrase", side_effect=AssertionError("credential persistence must be mocked")))

    def write_probes(self) -> Path:
        account = self.root / "db_storage"
        for role, page in SYNTHETIC_PAGES.items():
            directory = account / role
            directory.mkdir(parents=True)
            (directory / ("message_0.db" if role == "message" else "session.db")).write_bytes(page)
        return account / "message/message_0.db"

    def capture_state(self, *, sidecar: bool = True) -> dict:
        preflight = {
            "pid": 321, "pbkdf_locations": 1, "key_return_locations": 0,
            "capture_backend": "native", "transaction_id": "test-transaction",
        }
        if sidecar:
            (self.debug / "breakpoint-preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
        return {"transaction_id": "test-transaction", "preflight": preflight}

    def test_state_is_atomic_private_and_non_secret(self) -> None:
        target = workflow._write_state(self.debug, {
            "schema_version": 1, "wechat_app_path": str(self.app),
            "backup_path": str(self.backups / "WeChat-original.zip"),
        })
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertNotIn("passphrase", payload)
        self.assertNotIn("key", payload)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        self.assertEqual(workflow._read_state(self.debug), payload)

    def test_backup_path_validation_does_not_require_nas_online(self) -> None:
        offline = self.root / "offline-volume/backups"
        expected = offline / "WeChat-4.1.12-269341-original.zip"
        self.assertFalse(offline.exists())
        self.assertEqual(workflow._safe_backup_from_state({"backup_path": str(expected)}, offline), expected)

    def test_backup_path_escape_is_rejected(self) -> None:
        with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
            workflow._safe_backup_from_state({"backup_path": str(self.root / "WeChat-original.zip")}, self.backups)
        self.assertEqual(context.exception.code, "official_backup_path_unsafe")

    def test_stale_state_restores_then_removes_state(self) -> None:
        backup = self.backups / "WeChat-4.1.12-original.zip"
        backup.touch()
        workflow._write_state(self.debug, {
            "schema_version": 1, "wechat_app_path": str(self.app), "backup_path": str(backup),
            "version": "4.1.12", "build": "269341", "official_cdhash": "abc123",
        })
        with (
            patch.object(workflow, "restore_official_wechat_if_needed", return_value=RECOVERY) as restore,
            patch.object(workflow, "inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE),
        ):
            result = workflow.recover_stale_in_place_capture(self.app, backup_root=self.backups, debug_root=self.debug)
        self.assertTrue(result["official_wechat_restored"])
        self.assertFalse((self.debug / "prepared-in-place-capture.json").exists())
        restore.assert_called_once_with(self.app, backup, expected_version=("4.1.12", "269341"), expected_cdhash="abc123", expected_debug_identity=None)
        self.acquire.assert_called_once_with(self.app, self.debug)
        self.release.assert_called_once_with(self.app, self.debug)
        self.terminate.assert_called_once_with(self.debug)

    def test_cancel_without_state_verifies_official_without_mutation(self) -> None:
        with (
            patch.object(workflow, "inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE),
            patch.object(workflow, "restore_official_wechat_if_needed") as restore,
        ):
            result = workflow.cleanup_in_place_capture(self.app, backup_root=self.backups, debug_root=self.debug)
        self.assertTrue(result["official_wechat_verified"])
        self.assertFalse(result["official_wechat_restored"])
        restore.assert_not_called()
        self.acquire.assert_not_called()
        self.release.assert_called_once_with(self.app, self.debug)

    def test_capture_failure_always_requests_restore(self) -> None:
        failure = MacOSDBKeyCaptureFailure("debug_wechat_not_running", "closed", wechat_modified=True)
        with (
            patch.object(workflow, "_require_prepared_process", side_effect=failure),
            patch.object(workflow, "has_pending_in_place_capture", return_value=True),
            patch.object(workflow, "_restore_after_terminal_path") as restore,
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as error:
                workflow.capture_prepared_in_place(self.app, backup_root=self.backups, probe_db_path=self.root / "message_0.db", debug_root=self.debug)
        self.assertEqual(error.exception.code, "debug_wechat_not_running")
        restore.assert_called_once_with(self.app, backup_root=self.backups, debug_root=self.debug, original_error=failure)

    def test_capture_uses_preflight_target_validates_both_roles_and_restores_before_save(self) -> None:
        probe = self.write_probes()
        state = self.capture_state()
        events = []
        with (
            patch.object(workflow, "_require_prepared_process", return_value=(state, 321)),
            patch.object(workflow, "capture_native_wcdb_key", return_value={"db_key": "ab" * 32, "method": "macos_native_mach"}) as capture,
            patch("wechat_decrypt_tool.macos_capture_validation.validate_account_candidate", side_effect=lambda *_: events.append("validate") or VALIDATION) as validate,
            patch.object(workflow, "_restore_after_terminal_path", side_effect=lambda *a, **kw: events.append("restore") or RECOVERY),
            patch.object(workflow, "save_passphrase", side_effect=lambda *_: events.append("save") or self.debug / "key.json") as save,
        ):
            result = workflow.capture_prepared_in_place(self.app, backup_root=self.backups, probe_db_path=probe, debug_root=self.debug)
        self.assertEqual(events, ["validate", "restore", "save"])
        self.assertEqual(capture.call_args.kwargs["pid"], 321)
        self.assertEqual(capture.call_args.kwargs["transaction_id"], "test-transaction")
        validate.assert_called_once_with("ab" * 32, SYNTHETIC_PAGES)
        save.assert_called_once_with("ab" * 32)
        self.assertTrue(result["account_roles_validated"])
        self.assertEqual(result["validated_roles"], ["message", "session"])

    def test_capture_can_defer_cache_until_full_account_validation(self) -> None:
        probe = self.write_probes()
        state = self.capture_state()
        with (
            patch.object(workflow, "_require_prepared_process", return_value=(state, 321)),
            patch.object(workflow, "capture_native_wcdb_key", return_value={"db_key": "ab" * 32, "method": "macos_native_mach"}),
            patch("wechat_decrypt_tool.macos_capture_validation.validate_account_candidate", return_value=VALIDATION) as validate,
            patch.object(workflow, "save_passphrase") as save,
            patch.object(workflow, "_restore_after_terminal_path", return_value=RECOVERY) as restore,
        ):
            result = workflow.capture_prepared_in_place(self.app, backup_root=self.backups, probe_db_path=probe, save_result=False, debug_root=self.debug)
        self.assertEqual(result["db_key"], "ab" * 32)
        self.assertEqual(result["cache_path"], "")
        validate.assert_called_once_with("ab" * 32, SYNTHETIC_PAGES)
        restore.assert_called_once()
        save.assert_not_called()

    def test_capture_uses_preflight_metadata_from_recovery_state_when_sidecar_file_is_missing(self) -> None:
        probe = self.write_probes()
        state = self.capture_state(sidecar=False)
        with (
            patch.object(workflow, "_require_prepared_process", return_value=(state, 321)),
            patch.object(workflow, "capture_native_wcdb_key", return_value={"db_key": "ab" * 32, "method": "macos_native_mach"}) as capture,
            patch("wechat_decrypt_tool.macos_capture_validation.validate_account_candidate", return_value=VALIDATION) as validate,
            patch.object(workflow, "save_passphrase") as save,
            patch.object(workflow, "_restore_after_terminal_path", return_value=RECOVERY),
        ):
            result = workflow.capture_prepared_in_place(self.app, backup_root=self.backups, probe_db_path=probe, save_result=False, debug_root=self.debug)
        self.assertEqual(result["db_key"], "ab" * 32)
        self.assertEqual(result["cache_path"], "")
        self.assertFalse((self.debug / "breakpoint-preflight.json").exists())
        self.assertEqual(capture.call_args.kwargs["pid"], 321)
        self.assertEqual(capture.call_args.kwargs["transaction_id"], state["transaction_id"])
        validate.assert_called_once_with("ab" * 32, SYNTHETIC_PAGES)
        save.assert_not_called()

    def test_missing_session_snapshot_never_starts_capture(self) -> None:
        probe = self.root / "message_0.db"
        probe.write_bytes(SYNTHETIC_PAGES["message"])
        state = self.capture_state()
        with (
            patch.object(workflow, "_require_prepared_process", return_value=(state, 321)),
            patch.object(workflow, "capture_native_wcdb_key") as capture,
            patch.object(workflow, "save_passphrase") as save,
            patch.object(workflow, "has_pending_in_place_capture", return_value=True),
            patch.object(workflow, "_restore_after_terminal_path", return_value=RECOVERY) as restore,
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as error:
                workflow.capture_prepared_in_place(self.app, backup_root=self.backups, probe_db_path=probe, debug_root=self.debug)
        self.assertEqual(error.exception.code, "account_probe_missing")
        capture.assert_not_called()
        save.assert_not_called()
        restore.assert_called_once()


if __name__ == "__main__":
    unittest.main()
