import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_db_key_capture import (
    MacOSDBKeyCaptureFailure,
    _atomic_swap_paths,
    _build_lldb_capture_command,
    _has_compatible_debug_entitlements,
    _has_compatible_in_place_signature,
    _has_debug_copy_marker,
    _mark_debug_copy,
    _parse_passphrase,
    _quit_wechat,
    backup_original_wechat,
    capture_and_cache_macos_passphrase,
    cleanup_macos_passphrase_capture,
    ensure_wechat_debuggable,
    ensure_wechat_in_place_debuggable,
    restore_official_wechat_if_needed,
    save_passphrase,
)

OFFICIAL_SIGNATURE = {
    "valid": True,
    "ad_hoc": False,
    "hardened_runtime": True,
    "team_identifier": "5A4RE8SF68",
    "identifier": "com.tencent.xinWeChat",
    "cdhash": "abc123",
}
DEBUG_SIGNATURE = {
    "valid": True,
    "ad_hoc": True,
    "hardened_runtime": False,
    "team_identifier": "",
    "identifier": "com.tencent.xinWeChat",
    "cdhash": "debug123",
}


class TestMacOSDBKeyCapture(unittest.TestCase):
    def test_in_place_preparation_records_recovery_before_signing(self) -> None:
        official = Path("/tmp/WeChat.app")
        backup = Path("/Volumes/BackupVolume/backups/WeChat-original.zip")
        events: list[str] = []

        def record(payload):
            self.assertEqual(payload["backup_path"], str(backup))
            events.append("state")

        sign_commands: list[list[str]] = []

        def run(args, **_kwargs):
            if args[0] == "/usr/bin/codesign":
                events.append("sign")
                sign_commands.append(args)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with (
            patch(
                "wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature",
                side_effect=[OFFICIAL_SIGNATURE, DEBUG_SIGNATURE, DEBUG_SIGNATURE],
            ),
            patch("wechat_decrypt_tool.macos_db_key_capture.os.access", return_value=True),
            patch("wechat_decrypt_tool.macos_db_key_capture.backup_original_wechat", return_value=(backup, False)),
            patch(
                "wechat_decrypt_tool.macos_db_key_capture.verify_original_wechat_backup",
                return_value={"version": "4.1.12", "build": "269341", "cdhash": "abc123"},
            ),
            patch("wechat_decrypt_tool.macos_db_key_capture._wechat_version", return_value=("4.1.12", "269341")),
            patch("wechat_decrypt_tool.macos_db_key_capture._quit_wechat"),
            patch(
                "wechat_decrypt_tool.macos_db_key_capture._prepare_local_restore_staging",
                return_value=Path("/tmp/staged.app"),
            ),
            patch("wechat_decrypt_tool.macos_db_key_capture._has_compatible_in_place_signature", return_value=True),
            patch("wechat_decrypt_tool.macos_db_key_capture._atomic_swap_paths") as swap,
            patch("wechat_decrypt_tool.macos_db_key_capture._run", side_effect=run),
        ):
            result = ensure_wechat_in_place_debuggable(official, backup.parent, before_resign=record)

        self.assertEqual(events, ["state", "sign"])
        self.assertNotIn("--deep", sign_commands[0])
        self.assertIn("--preserve-metadata=entitlements", sign_commands[0])
        self.assertEqual(sign_commands[0][-1], "/tmp/staged.app")
        swap.assert_called_once_with(official, Path("/tmp/staged.app"))
        self.assertTrue(result["wechat_resigned"])
        self.assertTrue(result["backup_verified"])

    def test_in_place_preparation_rejects_backup_identity_mismatch_before_mutation(self) -> None:
        official = Path("/tmp/WeChat.app")
        backup = Path("/Volumes/BackupVolume/backups/WeChat-original.zip")
        with (
            patch("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE),
            patch("wechat_decrypt_tool.macos_db_key_capture.os.access", return_value=True),
            patch("wechat_decrypt_tool.macos_db_key_capture.backup_original_wechat", return_value=(backup, False)),
            patch(
                "wechat_decrypt_tool.macos_db_key_capture.verify_original_wechat_backup",
                return_value={"version": "4.1.12", "build": "269341", "cdhash": "different"},
            ),
            patch("wechat_decrypt_tool.macos_db_key_capture._wechat_version", return_value=("4.1.12", "269341")),
            patch("wechat_decrypt_tool.macos_db_key_capture._quit_wechat") as quit_wechat,
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                ensure_wechat_in_place_debuggable(official, backup.parent)

        self.assertEqual(context.exception.code, "official_backup_identity_mismatch")
        quit_wechat.assert_not_called()

    def test_sign_failure_restores_verified_official(self) -> None:
        official = Path("/tmp/WeChat.app")
        backup = Path("/Volumes/BackupVolume/backups/WeChat-original.zip")
        sign_failure = MacOSDBKeyCaptureFailure("command_failed", "sign failed")
        with (
            patch("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE),
            patch("wechat_decrypt_tool.macos_db_key_capture.os.access", return_value=True),
            patch("wechat_decrypt_tool.macos_db_key_capture.backup_original_wechat", return_value=(backup, False)),
            patch(
                "wechat_decrypt_tool.macos_db_key_capture.verify_original_wechat_backup",
                return_value={"version": "4.1.12", "build": "269341", "cdhash": "abc123"},
            ),
            patch("wechat_decrypt_tool.macos_db_key_capture._wechat_version", return_value=("4.1.12", "269341")),
            patch("wechat_decrypt_tool.macos_db_key_capture._quit_wechat"),
            patch("wechat_decrypt_tool.macos_db_key_capture._prepare_local_restore_staging"),
            patch("wechat_decrypt_tool.macos_db_key_capture._run", side_effect=sign_failure),
            patch("wechat_decrypt_tool.macos_db_key_capture._run_as_administrator", side_effect=sign_failure),
            patch(
                "wechat_decrypt_tool.macos_db_key_capture.restore_official_wechat_if_needed",
                return_value={"official_wechat_verified": True, "official_wechat_restored": True},
            ) as restore,
        ):
            with self.assertRaises(MacOSDBKeyCaptureFailure):
                ensure_wechat_in_place_debuggable(official, backup.parent)

        restore.assert_called_once()

    @unittest.skipUnless(sys.platform == "darwin", "renameatx_np is macOS-specific")
    def test_atomic_restore_exchange_has_no_missing_path_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            installed = root / "WeChat.app"
            staged = root / ".WeChat.restore.app"
            installed.mkdir()
            staged.mkdir()
            (installed / "marker").write_text("debug", encoding="utf-8")
            (staged / "marker").write_text("official", encoding="utf-8")

            _atomic_swap_paths(installed, staged)

            self.assertEqual((installed / "marker").read_text(encoding="utf-8"), "official")
            self.assertEqual((staged / "marker").read_text(encoding="utf-8"), "debug")

    def test_quit_timeout_falls_back_without_blocking_restore(self) -> None:
        official = Path("/Applications/WeChat.app")
        timeout = subprocess.TimeoutExpired(cmd="osascript", timeout=5)
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("wechat_decrypt_tool.macos_db_key_capture._find_wechat_main_pid", side_effect=[123, 123, None]),
            patch("wechat_decrypt_tool.macos_db_key_capture._find_wechat_bundle_pids", return_value=[]),
            patch("wechat_decrypt_tool.macos_db_key_capture.time.monotonic", side_effect=[0, 16, 16, 32, 32, 33]),
            patch("wechat_decrypt_tool.macos_db_key_capture.subprocess.run", side_effect=[timeout, completed]) as run,
        ):
            _quit_wechat(official)

        self.assertEqual(run.call_args_list[1].args[0], ["/bin/kill", "-TERM", "123"])

    def test_parses_exact_32_byte_lldb_memory_dump(self) -> None:
        output = "\n".join(
            [
                "0x1000: " + " ".join(f"0x{value:02x}" for value in range(16)),
                "0x1010: " + " ".join(f"0x{value:02x}" for value in range(16, 32)),
            ]
        )
        self.assertEqual(_parse_passphrase(output), bytes(range(32)).hex())

    def test_rejects_incomplete_lldb_memory_dump(self) -> None:
        self.assertEqual(_parse_passphrase("0x1000: 0x01 0x02"), "")

    def test_lldb_wrapper_stops_keepalive_when_debugger_exits(self) -> None:
        command = _build_lldb_capture_command(Path("/tmp/capture script.lldb"), 180)
        for expected in ("/usr/bin/mkfifo", "producer_pid", "watchdog_pid", "lldb_pid", "/bin/kill", "WEDATA_LLDB_EXIT"):
            self.assertIn(expected, command)

    def test_ad_hoc_debug_copy_must_not_claim_any_entitlements(self) -> None:
        incompatible = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="<key>com.apple.application-identifier</key><string>5A4RE8SF68.com.tencent.xinWeChat</string>", stderr="",
        )
        compatible = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="warning: blob data is NULL")
        debug_app = Path("/tmp/WeChat-Debug.app")
        with patch.object(Path, "exists", return_value=True), patch(
            "wechat_decrypt_tool.macos_db_key_capture._run", return_value=incompatible
        ):
            self.assertFalse(_has_compatible_debug_entitlements(debug_app))
        with patch.object(Path, "exists", return_value=True), patch(
            "wechat_decrypt_tool.macos_db_key_capture._run", return_value=compatible
        ):
            self.assertTrue(_has_compatible_debug_entitlements(debug_app))

    def test_in_place_signature_keeps_tencent_login_helper(self) -> None:
        app = Path("/Applications/WeChat.app")
        required_entitlements = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>com.apple.application-identifier</key><string>5A4RE8SF68.com.tencent.xinWeChat</string>
<key>com.apple.security.app-sandbox</key><true/>
<key>com.apple.security.application-groups</key><array><string>5A4RE8SF68.com.tencent.xinWeChat</string></array>
<key>com.apple.security.network.client</key><true/>
</dict></plist>""",
            stderr="",
        )
        helper_signature = {
            "valid": True,
            "ad_hoc": False,
            "team_identifier": "5A4RE8SF68",
            "identifier": "com.tencent.flue.WeChatAppEx",
        }
        with (
            patch("wechat_decrypt_tool.macos_db_key_capture._run", return_value=required_entitlements),
            patch.object(Path, "exists", return_value=True),
            patch("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", return_value=helper_signature),
        ):
            self.assertTrue(_has_compatible_in_place_signature(app))

    def test_in_place_signature_rejects_missing_outer_sandbox_entitlements(self) -> None:
        app = Path("/Applications/WeChat.app")
        missing_entitlements = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="warning: blob data is NULL"
        )
        with patch(
            "wechat_decrypt_tool.macos_db_key_capture._run", return_value=missing_entitlements
        ):
            self.assertFalse(_has_compatible_in_place_signature(app))

    @unittest.skipUnless(sys.platform == "darwin", "OpenStep InfoPlist.strings conversion requires plutil")
    def test_debug_copy_has_an_unambiguous_visible_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = Path(temp_dir) / "WeChat-Debug.app"
            info_path = app / "Contents/Info.plist"
            localized_path = app / "Contents/Resources/zh-Hans.lproj/InfoPlist.strings"
            info_path.parent.mkdir(parents=True)
            info_path.write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.tencent.xinWeChat"}))
            localized_path.parent.mkdir(parents=True)
            localized_path.write_text('"CFBundleDisplayName" = "微信";\n', encoding="utf-8")
            self.assertFalse(_has_debug_copy_marker(app))
            _mark_debug_copy(app)
            self.assertTrue(_has_debug_copy_marker(app))

    def test_saves_passphrase_atomically_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = save_passphrase("ab" * 32, home=Path(temp_dir))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["passphrase"], "ab" * 32)
            self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)

    def test_rejects_invalid_passphrase_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(MacOSDBKeyCaptureFailure) as context:
                save_passphrase("not-a-key", home=Path(temp_dir))
        self.assertEqual(context.exception.code, "invalid_passphrase")

    def test_nas_backup_is_a_metadata_preserving_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = root / "WeChat.app"
            contents = app / "Contents"
            contents.mkdir(parents=True)
            (contents / "Info.plist").write_bytes(
                plistlib.dumps({"CFBundleShortVersionString": "4.1.12", "CFBundleVersion": "269341"})
            )
            (contents / "marker.txt").write_text("original", encoding="utf-8")
            backup, created = backup_original_wechat(app, root / "backups")
            self.assertTrue(created)
            reused, created_again = backup_original_wechat(app, root / "backups")
            self.assertEqual(reused, backup)
            self.assertFalse(created_again)

    def test_debug_preparation_preserves_official_wechat(self) -> None:
        official = Path("/Applications/WeChat.app")
        backup = Path("/Volumes/BackupVolume/WeChat-original.zip")
        debug = Path("/Users/demo/Library/Caches/WeChatDataAnalysis/WeChat-Debug.app")
        with (
            patch("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE),
            patch("wechat_decrypt_tool.macos_db_key_capture.backup_original_wechat", return_value=(backup, False)),
            patch("wechat_decrypt_tool.macos_db_key_capture._prepare_debug_copy", return_value=(debug, True)),
        ):
            result = ensure_wechat_debuggable(official, backup.parent)
        self.assertFalse(result["wechat_modified"])
        self.assertTrue(result["official_wechat_preserved"])

    def test_official_restore_skips_already_valid_tencent_build(self) -> None:
        with patch("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", return_value=OFFICIAL_SIGNATURE), patch.object(
            Path, "exists", return_value=False
        ):
            result = restore_official_wechat_if_needed(Path("/tmp/WeChat.app"), Path("/tmp/original.zip"))
        self.assertTrue(result["official_wechat_verified"])
        self.assertFalse(result["official_wechat_restored"])

    def test_capture_delegates_to_recoverable_in_place_workflow(self) -> None:
        official = Path("/Applications/WeChat.app")
        expected = {"cache_path": "/tmp/key.json", "official_wechat_preserved": True}
        with (
            patch("wechat_decrypt_tool.macos_inplace_capture.prepare_in_place_capture") as prepare,
            patch("wechat_decrypt_tool.macos_inplace_capture.preflight_prepared_in_place_capture") as preflight,
            patch("wechat_decrypt_tool.macos_inplace_capture.capture_prepared_in_place", return_value=expected) as capture,
        ):
            result = capture_and_cache_macos_passphrase(
                official, backup_root=Path("/tmp/backups"), probe_db_path=Path("/tmp/message_0.db")
            )
        prepare.assert_called_once()
        preflight.assert_called_once()
        capture.assert_called_once()
        self.assertEqual(result, expected)

    def test_cleanup_delegates_to_in_place_recovery(self) -> None:
        official = Path("/Applications/WeChat.app")
        expected = {"official_wechat_verified": True, "wechat_modified": False}
        with patch("wechat_decrypt_tool.macos_inplace_capture.cleanup_in_place_capture", return_value=expected) as cleanup:
            result = cleanup_macos_passphrase_capture(official, backup_root=Path("/tmp/backups"))
        cleanup.assert_called_once()
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
