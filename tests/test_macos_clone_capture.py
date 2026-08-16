import ast
import ctypes
import errno
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_clone_capture import (
    _clone_path_force,
    _materialize_private_xwechat_files,
    _normalize_salts,
    _remove_clone_profile,
    _require_local_apfs_clone,
    build_lldb_breakpoint_preflight_script,
    build_lldb_salt_capture_script,
    capture_prepared_clone,
    preflight_capture_breakpoints,
    preflight_prepared_clone,
)
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure


class TestMacOSCloneCapture(unittest.TestCase):
    def test_clone_profile_cleanup_retries_transient_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            debug_root = Path(temporary_dir)
            profile = debug_root / "profile-clone-test"
            profile.mkdir()
            with (
                patch(
                    "wechat_decrypt_tool.macos_clone_capture.shutil.rmtree",
                    side_effect=[OSError("busy"), None],
                ) as remove,
                patch("wechat_decrypt_tool.macos_clone_capture.time.sleep") as wait,
            ):
                _remove_clone_profile(profile, debug_root)

            self.assertEqual(remove.call_count, 2)
            wait.assert_called_once_with(0.4)

    def test_clone_permission_error_requests_full_disk_access(self) -> None:
        class DeniedCloneFile:
            argtypes = None
            restype = None

            def __call__(self, _source, _destination, _flags):
                ctypes.set_errno(errno.EPERM)
                return -1

        class FakeLibC:
            clonefile = DeniedCloneFile()

        with (
            patch("wechat_decrypt_tool.macos_clone_capture._require_local_apfs_clone"),
            patch("wechat_decrypt_tool.macos_clone_capture.ctypes.CDLL", return_value=FakeLibC()),
            patch("wechat_decrypt_tool.macos_clone_capture.os.path.lexists", return_value=False),
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                _clone_path_force(
                    Path.home() / "Library/Containers/com.tencent.xinWeChat",
                    Path("/private/clone"),
                )

        self.assertEqual(context.exception.code, "database_permission_denied")
        self.assertIn("完全磁盘访问权限", str(context.exception))
        self.assertIn("重启", str(context.exception))

    def test_clone_permission_error_outside_wechat_container_keeps_generic_failure(self) -> None:
        class DeniedCloneFile:
            argtypes = None
            restype = None

            def __call__(self, _source, _destination, _flags):
                ctypes.set_errno(errno.EPERM)
                return -1

        class FakeLibC:
            clonefile = DeniedCloneFile()

        with (
            patch("wechat_decrypt_tool.macos_clone_capture._require_local_apfs_clone"),
            patch("wechat_decrypt_tool.macos_clone_capture.ctypes.CDLL", return_value=FakeLibC()),
            patch("wechat_decrypt_tool.macos_clone_capture.os.path.lexists", return_value=False),
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                _clone_path_force(Path("/Applications/WeChat.app"), Path("/private/clone"))

        self.assertEqual(context.exception.code, "clonefile_failed")

    def test_clone_source_stat_permission_error_requests_full_disk_access(self) -> None:
        source = Path.home() / "Library/Containers/com.tencent.xinWeChat"

        with patch.object(Path, "stat", side_effect=PermissionError(errno.EPERM, "Operation not permitted")):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                _require_local_apfs_clone(source, Path("/private"))

        self.assertEqual(context.exception.code, "database_permission_denied")

    def test_breakpoint_preflight_requires_a_loaded_executable_address(self) -> None:
        script = build_lldb_breakpoint_preflight_script(Path("/tmp/preflight.json"))

        ast.parse(script)
        self.assertIn('BreakpointCreateByName("CCKeyDerivationPBKDF")', script)
        self.assertIn("ResolveFileAddress(offset)", script)
        self.assertIn("lldb.ePermissionsExecutable", script)
        self.assertIn("lldb.LLDB_INVALID_ADDRESS", script)
        self.assertIn("process.Detach()", script)
        self.assertIn("WEDATA_BREAKPOINT_PREFLIGHT", script)

    def test_system_pbkdf_capture_can_disable_internal_return_fallback(self) -> None:
        script = build_lldb_salt_capture_script(
            Path("/tmp/result.json"),
            ["12" * 16],
            probe_page1=b"x" * 4096,
            enable_key_return_fallback=False,
        )

        ast.parse(script)
        self.assertIn("ENABLE_KEY_RETURN_FALLBACK = False", script)
        self.assertIn("if ENABLE_KEY_RETURN_FALLBACK:", script)
        self.assertIn('BreakpointCreateByName("CCKeyDerivationPBKDF")', script)

    def test_prepared_capture_arms_resolved_internal_return_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            debug_root = Path(temporary_dir)
            debug_app = debug_root / "WeChat-Debug.app"
            profile = debug_root / "profile-clone-test"
            (debug_root / "breakpoint-preflight.json").write_text(
                json.dumps({"pid": 321, "pbkdf_locations": 1, "key_return_locations": 1}),
                encoding="utf-8",
            )
            with (
                patch("wechat_decrypt_tool.macos_clone_capture.normalize_wechat_app_path", return_value=Path("/Applications/WeChat.app")),
                patch("wechat_decrypt_tool.macos_clone_capture.inspect_wechat_signature", return_value={}),
                patch("wechat_decrypt_tool.macos_clone_capture._is_tencent_official_signature", return_value=True),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._read_state",
                    return_value={
                        "debug_app_path": str(debug_app),
                        "profile_path": str(profile),
                        "debug_pid": 321,
                        "database_salts": ["12" * 16],
                    },
                ),
                patch("wechat_decrypt_tool.macos_clone_capture._is_safe_clone_profile", return_value=True),
                patch("wechat_decrypt_tool.macos_clone_capture._debug_copy_is_ready", return_value=True),
                patch("wechat_decrypt_tool.macos_clone_capture._find_wechat_main_pid", return_value=321),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture.capture_salt_matched_passphrase",
                    return_value="ab" * 32,
                ) as capture,
                patch("wechat_decrypt_tool.macos_clone_capture._validate_captured_passphrase"),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture.save_passphrase",
                    return_value=debug_root / "key.json",
                ),
                patch("wechat_decrypt_tool.macos_clone_capture._cleanup_prepared_clone"),
            ):
                capture_prepared_clone(
                    "/Applications/WeChat.app",
                    backup_root=debug_root / "backups",
                    probe_db_path=debug_root / "message_0.db",
                    debug_root=debug_root,
                )

            self.assertTrue(capture.call_args.kwargs["enable_key_return_fallback"])

    def test_breakpoint_preflight_persists_only_non_secret_readiness_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            debug_root = Path(temporary_dir)

            def write_preflight(_command, *, timeout):
                self.assertEqual(timeout, 90)
                (debug_root / "breakpoint-preflight.json").write_text(
                    json.dumps(
                        {
                            "pid": 321,
                            "pbkdf_locations": 2,
                            "key_return_locations": 1,
                            "matched_modules": [{"module": "wechat.dylib"}],
                            "rejected_points": [],
                        }
                    ),
                    encoding="utf-8",
                )
                return "WEDATA_BREAKPOINT_PREFLIGHT 2 1"

            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/usr/bin/lldb"),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._run_as_administrator",
                    side_effect=write_preflight,
                ),
            ):
                result = preflight_capture_breakpoints(pid=321, debug_root=debug_root)

            self.assertEqual(result["pbkdf_locations"], 2)
            self.assertEqual(result["key_return_locations"], 1)
            self.assertTrue(result["ready_for_monitoring"])
            self.assertTrue(result["process_detached"])
            saved = json.loads((debug_root / "breakpoint-preflight.json").read_text(encoding="utf-8"))
            self.assertNotIn("passphrase", saved)
            self.assertNotIn("key", saved)

    def test_breakpoint_preflight_rejects_zero_resolved_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            debug_root = Path(temporary_dir)

            def write_preflight(_command, *, timeout):
                (debug_root / "breakpoint-preflight.json").write_text(
                    json.dumps({"pid": 321, "pbkdf_locations": 0, "key_return_locations": 0}),
                    encoding="utf-8",
                )
                return "WEDATA_BREAKPOINT_PREFLIGHT 0 0"

            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/usr/bin/lldb"),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._run_as_administrator",
                    side_effect=write_preflight,
                ),
            ):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                    preflight_capture_breakpoints(pid=321, debug_root=debug_root)

            self.assertEqual(context.exception.code, "capture_breakpoints_unavailable")
            self.assertFalse((debug_root / "breakpoint-preflight.json").exists())

    def test_prepared_preflight_cleans_private_clone_after_failure(self) -> None:
        debug_root = Path("/tmp/wcda-test-debug")
        debug_app = debug_root / "WeChat-Debug.app"
        profile = debug_root / "profile-clone-test"
        failure = MacOSDBKeyCaptureFailure("capture_breakpoints_unavailable", "no breakpoints")
        with (
            patch("wechat_decrypt_tool.macos_clone_capture.normalize_wechat_app_path", return_value=Path("/Applications/WeChat.app")),
            patch("wechat_decrypt_tool.macos_clone_capture.inspect_wechat_signature", return_value={}),
            patch("wechat_decrypt_tool.macos_clone_capture._is_tencent_official_signature", return_value=True),
            patch(
                "wechat_decrypt_tool.macos_clone_capture._read_state",
                return_value={"debug_app_path": str(debug_app), "profile_path": str(profile), "debug_pid": 321},
            ),
            patch("wechat_decrypt_tool.macos_clone_capture._is_safe_clone_profile", return_value=True),
            patch("wechat_decrypt_tool.macos_clone_capture._debug_copy_is_ready", return_value=True),
            patch("wechat_decrypt_tool.macos_clone_capture._find_wechat_main_pid", return_value=321),
            patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints", side_effect=failure),
            patch("wechat_decrypt_tool.macos_clone_capture._cleanup_prepared_clone") as cleanup,
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                preflight_prepared_clone(
                    "/Applications/WeChat.app",
                    backup_root=Path("/tmp/backups"),
                    debug_root=debug_root,
                )

        self.assertEqual(context.exception.code, "capture_breakpoints_unavailable")
        cleanup.assert_called_once_with(debug_root)

    def test_lldb_callback_requires_database_specific_pbkdf2_call(self) -> None:
        salt = "12" * 16
        script = build_lldb_salt_capture_script(
            Path("/tmp/result.json"),
            [salt],
            probe_page1=b"x" * 4096,
        )

        ast.parse(script)
        self.assertIn("algorithm != 2", script)
        self.assertIn("password_len != 32", script)
        self.assertIn("salt_len != 16", script)
        self.assertIn("prf != 5", script)
        self.assertIn("rounds != 256000", script)
        self.assertIn(salt, script)
        self.assertIn("salt.hex() not in EXPECTED_SALTS", script)
        self.assertIn("os.fsync", script)
        self.assertNotIn('print(password.hex()', script)
        self.assertLess(script.index("salt = process.ReadMemory"), script.index("password = process.ReadMemory"))
        self.assertIn("0xB8", script)
        self.assertIn("wechat_key_return", script)
        self.assertIn("_candidate_matches_page1", script)
        self.assertIn("WEDATA_MATCHED_VALIDATED_DATABASE_KEY", script)
        self.assertIn("os._exit(24)", script)
        self.assertIn("lldb.ePermissionsExecutable", script)
        self.assertIn("lldb.LLDB_INVALID_ADDRESS", script)

    def test_salt_normalization_rejects_non_database_values(self) -> None:
        self.assertEqual(_normalize_salts(["AB" * 16, bytes.fromhex("cd" * 16), "bad"]), ["ab" * 16, "cd" * 16])

    @unittest.skipUnless(sys.platform == "darwin", "APFS clonefile is macOS-specific")
    def test_private_snapshot_replaces_external_xwechat_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source_documents = root / "source/Documents"
            local_source = source_documents / "app_data/xwechat_files"
            local_source.mkdir(parents=True)
            (local_source / "marker").write_text("private-copy", encoding="utf-8")
            external = root / "external"
            external.mkdir()
            cloned_documents = root / "clone/Documents"
            cloned_documents.mkdir(parents=True)
            os.symlink(external, cloned_documents / "xwechat_files")

            _materialize_private_xwechat_files(source_documents, cloned_documents)

            result = cloned_documents / "xwechat_files"
            self.assertTrue(result.is_dir())
            self.assertFalse(result.is_symlink())
            self.assertEqual((result / "marker").read_text(encoding="utf-8"), "private-copy")
            self.assertFalse((external / "marker").exists())

    @unittest.skipUnless(sys.platform == "darwin", "APFS clonefile is macOS-specific")
    def test_private_snapshot_refuses_xwechat_source_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source_documents = root / "source/Documents"
            (source_documents / "app_data").mkdir(parents=True)
            external = root / "mounted-nas"
            external.mkdir()
            (external / "marker").write_text("must-not-copy", encoding="utf-8")
            os.symlink(external, source_documents / "app_data/xwechat_files")
            cloned_documents = root / "clone/Documents"
            cloned_documents.mkdir(parents=True)

            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                _materialize_private_xwechat_files(source_documents, cloned_documents)

            self.assertEqual(context.exception.code, "wechat_data_snapshot_source_missing")
            self.assertFalse((cloned_documents / "xwechat_files").exists())

    @unittest.skipUnless(sys.platform == "darwin", "APFS clonefile is macOS-specific")
    def test_force_clone_preserves_nested_symlink_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "source"
            source.mkdir()
            (source / "marker").write_text("private", encoding="utf-8")
            os.symlink("/Volumes/BackupVolume/xwechat_files", source / "external-link")
            destination = root / "destination"

            _clone_path_force(source, destination)

            self.assertEqual((destination / "marker").read_text(encoding="utf-8"), "private")
            self.assertTrue((destination / "external-link").is_symlink())
            self.assertEqual(os.readlink(destination / "external-link"), "/Volumes/BackupVolume/xwechat_files")


if __name__ == "__main__":
    unittest.main()
