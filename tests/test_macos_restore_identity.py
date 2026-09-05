"""Synthetic bundles only: never inspect or operate on the installed WeChat."""

import tempfile
import json
import os
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from wechat_decrypt_tool import macos_db_key_capture as capture
from wechat_decrypt_tool import macos_inplace_capture as inplace


OFFICIAL = {
    "valid": True, "ad_hoc": False, "hardened_runtime": True,
    "team_identifier": "5A4RE8SF68", "identifier": "com.tencent.xinWeChat", "cdhash": "old",
}
DEBUG = {**OFFICIAL, "ad_hoc": True, "hardened_runtime": False, "cdhash": "debug"}


class TestRestoreIdentity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "WeChat.app"
        self.app.mkdir()
        self.staged = self.root / capture.LOCAL_RESTORE_STAGING_NAME
        self.staged.mkdir()
        self.backup = self.root / "WeChat-original.zip"
        self.addCleanup(patch.stopall)
        patch.object(capture, "DEFAULT_DEBUG_ROOT", self.root / "work").start()
        patch.object(inplace, "DEFAULT_CAPTURE_LOCK_ROOT", self.root / "user-locks").start()
        patch.object(capture, "_run", side_effect=AssertionError("external command forbidden in synthetic regression")).start()

    def identity(self, path=None):
        stat = (path or self.app).stat()
        return {"version": "4.1.7", "build": "100", "cdhash": "debug", "device": stat.st_dev, "inode": stat.st_ino}

    def test_other_official_version_is_conflict_and_preserves_staging(self):
        with (
            patch.object(capture, "inspect_wechat_signature", return_value={**OFFICIAL, "cdhash": "new"}),
            patch.object(capture, "_wechat_version", return_value=("4.1.13", "200")),
            patch.object(capture, "_remove_local_restore_staging") as remove,
            patch.object(capture, "_atomic_swap_paths") as swap,
        ):
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old")
        self.assertEqual(error.exception.code, "external_install_conflict")
        remove.assert_not_called()
        swap.assert_not_called()

    def test_same_version_different_cdhash_is_conflict(self):
        with patch.object(capture, "inspect_wechat_signature", return_value={**OFFICIAL, "cdhash": "new"}), patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")):
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old")
        self.assertEqual(error.exception.code, "external_install_conflict")

    def test_matching_official_does_not_delete_unidentified_staging(self):
        with patch.object(capture, "inspect_wechat_signature", return_value=OFFICIAL), patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")), patch.object(capture, "_remove_local_restore_staging") as remove:
            result = capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old")
        self.assertTrue(result["original_identity_verified"])
        remove.assert_not_called()

    def test_unidentified_nonofficial_app_is_not_overwritten(self):
        with patch.object(capture, "inspect_wechat_signature", return_value=DEBUG), patch.object(capture, "_quit_wechat") as quit_app, patch.object(capture, "_atomic_swap_paths") as swap:
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old")
        self.assertEqual(error.exception.code, "in_place_debug_identity_unknown")
        quit_app.assert_not_called()
        swap.assert_not_called()

    def test_debug_identity_must_match_inode_not_just_adhoc_hash(self):
        identity = {**self.identity(), "inode": -1}
        with patch.object(capture, "inspect_wechat_signature", return_value=DEBUG), patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")), patch.object(capture, "_atomic_swap_paths") as swap:
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old", expected_debug_identity=identity)
        self.assertEqual(error.exception.code, "in_place_debug_identity_unknown")
        swap.assert_not_called()

    def test_identity_checked_again_after_restore_swap(self):
        def signature(path):
            if path == self.app:
                return {**OFFICIAL, "cdhash": "changed"} if swapped[0] else DEBUG
            return OFFICIAL
        swapped = [False]
        def swap(*_):
            swapped[0] = not swapped[0]
        with patch.object(capture, "inspect_wechat_signature", side_effect=signature), patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")), patch.object(capture, "_quit_wechat"), patch.object(capture, "_atomic_swap_paths", side_effect=swap) as exchange:
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old", expected_debug_identity=self.identity())
        self.assertEqual(error.exception.code, "external_install_conflict")
        self.assertEqual(exchange.call_count, 1)
        self.assertTrue(self.staged.exists())

    def test_installation_lock_excludes_other_debug_roots(self):
        first = self.root / "one"
        second = self.root / "two"
        inplace._acquire_installation_lock(self.app, first)
        self.addCleanup(inplace._release_installation_lock, self.app, first)
        with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
            inplace._acquire_installation_lock(self.app, second)
        self.assertEqual(error.exception.code, "in_place_capture_busy")
        inplace._release_installation_lock(self.app, first)
        inplace._acquire_installation_lock(self.app, second)
        inplace._release_installation_lock(self.app, second)

    def test_lock_needs_no_write_to_installation_directory(self):
        applications = self.root / "Applications"
        applications.mkdir()
        app = applications / "WeChat.app"
        app.mkdir()
        applications.chmod(0o555)
        self.addCleanup(applications.chmod, 0o700)
        debug_root = self.root / "debug"
        inplace._acquire_installation_lock(app, debug_root)
        self.addCleanup(inplace._release_installation_lock, app, debug_root)
        locks = list((self.root / "user-locks").glob("*.lock"))
        self.assertEqual(len(locks), 1)
        self.assertEqual((self.root / "user-locks").stat().st_mode & 0o777, 0o700)
        self.assertEqual(locks[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(applications.iterdir()), [app])

    def test_legacy_state_remains_readable(self):
        inplace._write_state(self.root, {"schema_version": 1, "stage": "launched"})
        self.assertEqual(inplace._read_state(self.root)["schema_version"], 1)

    def prepare_fixture(self, state):
        debug_root = self.root / "debug"
        backup_root = self.root / "backups"
        backup_root.mkdir(exist_ok=True)
        state = {
            "schema_version": 1, "wechat_app_path": str(self.app),
            "backup_path": str(backup_root / "WeChat-4.1.13-original.zip"),
            "version": "4.1.13", "build": "200", "official_cdhash": "new", **state,
        }
        inplace._write_state(debug_root, state)
        self.addCleanup(inplace._release_installation_lock, self.app, debug_root)
        def ensure(app, backup_root, *, before_resign):
            before_resign({
                "wechat_app_path": str(app), "backup_path": str(backup_root / "WeChat-4.1.7-original.zip"),
                "version": "4.1.7", "build": "100", "official_cdhash": "old", "debug_identity": self.identity(),
            })
            return {"debug_identity": self.identity()}
        patch.object(inplace, "normalize_wechat_app_path", return_value=self.app).start()
        patch.object(inplace, "DEFAULT_WECHAT_APP", self.app).start()
        patch.object(inplace.platform, "system", return_value="darwin").start()
        patch.object(inplace, "inspect_wechat_signature", return_value=OFFICIAL).start()
        patch.object(capture, "inspect_wechat_signature", return_value=OFFICIAL).start()
        patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")).start()
        patch.object(inplace, "_terminate_native_capture_processes").start()
        patch.object(inplace, "_launch_wechat", return_value=123).start()
        prepared = patch.object(inplace, "ensure_wechat_in_place_debuggable", side_effect=ensure).start()
        return debug_root, backup_root, state, prepared

    def test_user_downgrade_before_new_transaction_supersedes_old_state_without_overwrite(self):
        debug_root, backup_root, _, prepared = self.prepare_fixture({})
        result = inplace.prepare_in_place_capture(self.app, backup_root=backup_root, debug_root=debug_root)
        self.assertTrue(result["previous_transaction_superseded"])
        current = inplace._read_state(debug_root)
        self.assertEqual(current["version"], "4.1.7")
        self.assertEqual(current["schema_version"], 2)
        self.assertTrue(current["transaction_id"])
        self.assertEqual(current["debug_identity"], self.identity())
        archives = list((debug_root / "recovery-history").glob("*/prepared-in-place-capture.json"))
        self.assertEqual(len(archives), 1)
        archived = json.loads(archives[0].read_text())
        self.assertEqual(archived["version"], "4.1.13")
        self.assertTrue(Path(archived["preserved_staging_path"]).is_dir())
        prepared.assert_called_once()

    def test_active_official_change_stops_then_next_explicit_retry_can_supersede(self):
        debug_root, backup_root, state, prepared = self.prepare_fixture({})
        lease = inplace._acquire_installation_lock(self.app, debug_root)
        state.update(schema_version=2, transaction_id=lease["transaction_id"], owner_pid=os.getpid(), owner_session=inplace._OWNER_SESSION)
        inplace._write_state(debug_root, state)
        with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
            inplace.prepare_in_place_capture(self.app, backup_root=backup_root, debug_root=debug_root)
        self.assertEqual(error.exception.code, "external_install_conflict")
        self.assertTrue(self.staged.exists())
        self.assertEqual(inplace._read_state(debug_root)["stage"], "external_install_conflict")
        prepared.assert_not_called()
        result = inplace.prepare_in_place_capture(self.app, backup_root=backup_root, debug_root=debug_root)
        self.assertTrue(result["previous_transaction_superseded"])
        prepared.assert_called_once()

    def test_legacy_unknown_debug_is_preserved_not_restored(self):
        debug_root, backup_root, _, prepared = self.prepare_fixture({})
        patch.object(inplace, "inspect_wechat_signature", return_value=DEBUG).start()
        patch.object(capture, "inspect_wechat_signature", return_value=DEBUG).start()
        with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
            inplace.prepare_in_place_capture(self.app, backup_root=backup_root, debug_root=debug_root)
        self.assertEqual(error.exception.code, "in_place_debug_identity_unknown")
        self.assertTrue(self.staged.exists())
        self.assertTrue(inplace._state_path(debug_root).exists())
        prepared.assert_not_called()

    def test_ready_requires_current_transaction_and_capturing_stage(self):
        state = {"schema_version": 2, "transaction_id": "current", "stage": "capturing", "capture_backend": "macos_native_mach", "debug_pid": 100, "preflight": {"pid": 123}}
        inplace._write_state(self.root, state)
        ready = {"status": "ready", "method": "macos_native_mach", "pid": 123, "transaction_id": "previous"}
        inplace._native_capture_ready_path(self.root).write_text(json.dumps(ready))
        self.assertFalse(inplace.native_capture_monitor_ready(debug_root=self.root))
        ready["transaction_id"] = "current"
        inplace._native_capture_ready_path(self.root).write_text(json.dumps(ready))
        self.assertTrue(inplace.native_capture_monitor_ready(debug_root=self.root))
        self.assertTrue(inplace.get_in_place_capture_status(debug_root=self.root)["monitor_ready"])
        state["stage"] = "launched"
        inplace._write_state(self.root, state)
        self.assertFalse(inplace.native_capture_monitor_ready(debug_root=self.root))

    def test_operation_mutex_rejects_other_thread_but_releases_for_next_request(self):
        patch.object(inplace, "normalize_wechat_app_path", return_value=self.app).start()
        entered, finish = threading.Event(), threading.Event()
        @inplace._serialized_installation_operation
        def operation(app, block=False):
            if block:
                entered.set()
                self.assertTrue(finish.wait(2))
            return "ok"
        worker = threading.Thread(target=operation, args=(self.app, True))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                operation(self.app)
            self.assertEqual(error.exception.code, "in_place_capture_busy")
        finally:
            finish.set()
            worker.join(2)
        self.assertEqual(operation(self.app), "ok")

    def test_successful_exact_debug_restore_is_verified_and_cleans_owned_staging(self):
        (self.app / "identity").write_text("debug")
        (self.staged / "identity").write_text("official")
        def signature(path):
            return DEBUG if (path / "identity").read_text() == "debug" else OFFICIAL
        def swap(first, second):
            temporary = self.root / "swap"
            first.rename(temporary)
            second.rename(first)
            temporary.rename(second)
        with patch.object(capture, "inspect_wechat_signature", side_effect=signature), patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")), patch.object(capture, "_quit_wechat"), patch.object(capture, "_atomic_swap_paths", side_effect=swap):
            result = capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old", expected_debug_identity=self.identity())
        self.assertTrue(result["original_identity_verified"])
        self.assertTrue(result["official_wechat_restored"])
        self.assertFalse(self.staged.exists())
        self.assertEqual((self.app / "identity").read_text(), "official")

    def test_prepare_records_exact_debug_identity_before_atomic_install(self):
        self.staged.rmdir()
        (self.app / "identity").write_text("official")
        records = []
        def signature(path):
            return DEBUG if (path / "identity").read_text() == "debug" else OFFICIAL
        def clone(*_, **__):
            self.staged.mkdir()
            (self.staged / "identity").write_text("official")
            return self.staged
        def sign(*_, **__):
            (self.staged / "identity").write_text("debug")
        def swap(first, second):
            self.assertEqual(len(records), 2)
            self.assertEqual(records[-1]["debug_identity"], self.identity(self.staged))
            temporary = self.root / "swap"
            first.rename(temporary)
            second.rename(first)
            temporary.rename(second)
        with (
            patch.object(capture, "inspect_wechat_signature", side_effect=signature),
            patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")),
            patch.object(capture, "backup_original_wechat", return_value=(self.backup, True)),
            patch.object(capture, "verify_original_wechat_backup", return_value={"version": "4.1.7", "build": "100", "cdhash": "old"}),
            patch.object(capture, "_quit_wechat"),
            patch.object(capture, "_prepare_local_restore_staging", side_effect=clone),
            patch.object(capture, "_run", side_effect=sign),
            patch.object(capture, "_has_compatible_in_place_signature", return_value=True),
            patch.object(capture, "_atomic_swap_paths", side_effect=swap),
        ):
            result = capture.ensure_wechat_in_place_debuggable(self.app, self.root, before_resign=records.append)
        self.assertEqual(result["debug_identity"], self.identity())
        self.assertEqual((self.staged / "identity").read_text(), "official")

    def test_wrong_original_staging_is_preserved_before_any_restore_mutation(self):
        def signature(path):
            return DEBUG if path == self.app else {**OFFICIAL, "cdhash": "other"}
        with patch.object(capture, "inspect_wechat_signature", side_effect=signature), patch.object(capture, "_wechat_version", return_value=("4.1.7", "100")), patch.object(capture, "_atomic_swap_paths") as swap:
            with self.assertRaises(capture.MacOSDBKeyCaptureFailure) as error:
                capture.restore_official_wechat_if_needed(self.app, self.backup, expected_version=("4.1.7", "100"), expected_cdhash="old", expected_debug_identity=self.identity())
        self.assertEqual(error.exception.code, "official_restore_staging_conflict")
        self.assertTrue(self.staged.exists())
        swap.assert_not_called()

    def test_ready_wrong_pid_and_legacy_transaction_are_not_ready(self):
        inplace._write_state(self.root, {"schema_version": 2, "stage": "capturing", "transaction_id": "current", "debug_pid": 100, "preflight": {"pid": 123}})
        inplace._native_capture_ready_path(self.root).write_text(json.dumps({"status": "ready", "method": "macos_native_mach", "pid": 100, "transaction_id": "current"}))
        self.assertFalse(inplace.native_capture_monitor_ready(debug_root=self.root))
        inplace._write_state(self.root, {"schema_version": 1, "stage": "capturing", "debug_pid": 100})
        self.assertFalse(inplace.native_capture_monitor_ready(debug_root=self.root))


if __name__ == "__main__":
    unittest.main()
