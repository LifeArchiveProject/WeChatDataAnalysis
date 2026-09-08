import ast
import ctypes
import errno
import hashlib
import hmac
import json
import os
import sys
import tempfile
import types
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
    capture_salt_matched_passphrase,
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
                self.assertEqual(timeout, 180)
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

    def test_breakpoint_preflight_rejects_deferred_system_symbol_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            debug_root = Path(temporary_dir)

            def write_preflight(_command, *, timeout):
                self.assertEqual(timeout, 180)
                (debug_root / "breakpoint-preflight.json").write_text(
                    json.dumps(
                        {
                            "pid": 321,
                            "pbkdf_locations": 0,
                            "pbkdf_total_locations": 1,
                            "pbkdf_deferred": True,
                            "key_return_locations": 0,
                        }
                    ),
                    encoding="utf-8",
                )
                return "WEDATA_BREAKPOINT_PREFLIGHT 0 1 0"

            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/usr/bin/lldb"),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._run_as_administrator",
                    side_effect=write_preflight,
                ),
            ):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                    preflight_capture_breakpoints(pid=321, debug_root=debug_root)

            self.assertEqual(failure.exception.code, "capture_breakpoints_unavailable")
            self.assertFalse((debug_root / "breakpoint-preflight.json").exists())

    def test_breakpoint_preflight_rejects_verified_binary_import_when_lldb_reports_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            debug_root = Path(temporary_dir)

            def write_preflight(_command, *, timeout):
                (debug_root / "breakpoint-preflight.json").write_text(
                    json.dumps(
                        {
                            "pid": 321,
                            "pbkdf_locations": 0,
                            "pbkdf_total_locations": 0,
                            "key_return_locations": 0,
                        }
                    ),
                    encoding="utf-8",
                )
                return "WEDATA_BREAKPOINT_PREFLIGHT 0 0 0"

            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/usr/bin/lldb"),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._run_as_administrator",
                    side_effect=write_preflight,
                ),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._wechat_binary_imports_pbkdf",
                    return_value=True,
                ),
            ):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                    preflight_capture_breakpoints(
                        pid=321,
                        debug_root=debug_root,
                        wechat_app=debug_root / "synthetic-missing-WeChat.app",
                    )

            self.assertEqual(failure.exception.code, "capture_breakpoints_unavailable")
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
        self.assertIn("password_len not in (32, 64)", script)
        self.assertIn("salt_len != 16", script)
        self.assertIn("pbkdf_profiles", script)
        self.assertIn("EXPECTED_HMAC_SALTS", script)
        self.assertIn('source = "pbkdf_hmac_password"', script)
        self.assertIn('source = "pbkdf_database_password"', script)
        self.assertIn(salt, script)
        self.assertIn("database_salt = EXPECTED_HMAC_SALTS.get", script)
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
        self.assertIn("WEDATA_DEBUG_PROCESS_EXIT", script)
        self.assertIn("process.GetExitStatus()", script)
        self.assertIn("process.GetExitDescription()", script)

    def test_rounds_two_hmac_profile_yields_only_database_verified_master_key(self) -> None:
        salt = bytes(range(16))
        passphrase = bytes(range(32))
        encryption_key = hashlib.pbkdf2_hmac("sha512", passphrase, salt, 256000, dklen=32)
        hmac_salt = bytes(value ^ 0x3A for value in salt)
        hmac_key = hashlib.pbkdf2_hmac("sha512", encryption_key, hmac_salt, 2, dklen=32)
        page = bytearray(4096)
        page[:16] = salt
        page[16:4032] = bytes([0x5A]) * (4032 - 16)
        digest = hmac.new(hmac_key, digestmod=hashlib.sha512)
        digest.update(page[16:4032])
        digest.update((1).to_bytes(4, "little"))
        page[4032:4096] = digest.digest()
        script = build_lldb_salt_capture_script(
            Path("/tmp/result.json"),
            [salt],
            probe_page1=bytes(page),
        )

        class FakeError:
            def Success(self) -> bool:
                return True

        fake_lldb = types.SimpleNamespace(SBError=FakeError)
        namespace = {"__name__": "test_wedata_capture"}
        with patch.dict(sys.modules, {"lldb": fake_lldb}):
            exec(compile(script, "<capture-script>", "exec"), namespace)

        self.assertTrue(namespace["_candidate_matches_page1"](encryption_key))
        self.assertFalse(namespace["_candidate_matches_page1"](b"x" * 32))

        class FakeProcess:
            def ReadMemory(self, address, length, _error):
                values = {0x1000: encryption_key, 0x2000: hmac_salt}
                return values[address][:length]

        process = FakeProcess()
        registers = {"x0": 2, "x1": 0x1000, "x2": 32, "x3": 0x2000, "x4": 16, "x5": 5, "x6": 2}

        class FakeFrame:
            def GetThread(self):
                return types.SimpleNamespace(GetProcess=lambda: process)

            def FindRegister(self, name):
                return types.SimpleNamespace(GetValueAsUnsigned=lambda: registers[name])

        captured = []
        namespace["_write_result"] = lambda _payload: True
        namespace["_record_diagnostic"] = lambda _name: None
        namespace["_save_valid_candidate"] = lambda candidate, database_salt, source, _process: captured.append(
            (candidate, database_salt, source)
        )
        namespace["_pbkdf_callback"](FakeFrame(), None, None)

        self.assertEqual(captured, [(encryption_key, salt.hex(), "pbkdf_hmac_password")])
        registers["x0"] = 99
        registers["x5"] = 99
        registers["x6"] = 3
        namespace["_pbkdf_callback"](FakeFrame(), None, None)
        self.assertEqual(len(captured), 2)
        registers["x2"] = 31
        namespace["_pbkdf_callback"](FakeFrame(), None, None)
        self.assertEqual(len(captured), 2)

    def test_capture_reports_debug_process_exit_without_waiting_for_generic_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            probe = root / "message_0.db"
            probe.write_bytes(bytes(range(256)) * 16)

            class FixedTemporaryDirectory:
                def __init__(self, *args, **kwargs):
                    pass

                def __enter__(self):
                    return str(root)

                def __exit__(self, exc_type, exc, traceback):
                    return False

            def report_exit(_command, *, timeout):
                self.assertEqual(timeout, 285.0)
                command_source = (root / "capture.lldb").read_text(encoding="utf-8")
                self.assertIn("process handle SIGTRAP -n false -p false -s false", command_source)
                (root / "result.json").write_text(
                    json.dumps(
                        {
                            "diagnostics": {
                                "pbkdf_calls": 18,
                                "pbkdf_shape_hits": 4,
                                "pbkdf_rounds_2_hits": 4,
                            },
                            "process_exit": {
                                "pid": 321,
                                "state": "exited",
                                "exit_status": 0,
                                "exit_description": "",
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return 'WEDATA_DEBUG_PROCESS_EXIT {"pid": 321, "state": "exited"}'

            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/usr/bin/lldb"),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture.tempfile.TemporaryDirectory",
                    FixedTemporaryDirectory,
                ),
                patch(
                    "wechat_decrypt_tool.macos_clone_capture._run_as_administrator",
                    side_effect=report_exit,
                ),
            ):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                    capture_salt_matched_passphrase(
                        pid=321,
                        expected_salts=[bytes(range(16))],
                        probe_db_path=probe,
                    )

        self.assertEqual(context.exception.code, "debug_wechat_exited_during_capture")
        self.assertIn("PID 321", str(context.exception))
        self.assertIn("rounds=2 命中 4", str(context.exception))
        self.assertIn("未保存任何未经数据库校验的候选", str(context.exception))

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
