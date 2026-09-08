"""Synthetic encrypted pages and fake LLDB only; never touches WeChat."""

import hashlib
import hmac
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_clone_capture import build_lldb_salt_capture_script
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure
from wechat_decrypt_tool.macos_capture_validation import (
    normalize_account_probe_pages,
    read_account_probe_pages,
    resolve_account_probe_paths,
    validate_account_candidate,
)
from wechat_decrypt_tool.wechat_decrypt import validate_realtime_database_key


def encrypted_page(candidate, salt, *, raw=False):
    enc_key = candidate if raw else hashlib.pbkdf2_hmac("sha512", candidate, salt, 256000, 32)
    mac_salt = bytes(value ^ 0x3A for value in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, 32)
    page = bytearray(salt + b"\x5a" * (4096 - 16))
    page[4032:] = hmac.new(mac_key, page[16:4032] + b"\x01\x00\x00\x00", hashlib.sha512).digest()
    return bytes(page)


class TestMacOSCaptureValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.passphrase = bytes(range(32))
        cls.message_salt = bytes(range(16))
        cls.session_salt = bytes(range(16, 32))
        cls.pages = {
            "message": encrypted_page(cls.passphrase, cls.message_salt),
            "session": encrypted_page(cls.passphrase, cls.session_salt),
        }
        cls.message_raw = hashlib.pbkdf2_hmac("sha512", cls.passphrase, cls.message_salt, 256000, 32)

    def namespace(self, **kwargs):
        script = build_lldb_salt_capture_script(
            Path("/tmp/synthetic-unused-result.json"),
            [self.message_salt, self.session_salt],
            probe_page1=self.pages["message"],
            **kwargs,
        )
        namespace = {"__name__": "synthetic_wedata_capture"}
        with patch.dict(sys.modules, {"lldb": types.SimpleNamespace()}):
            exec(compile(script, "<synthetic-capture>", "exec"), namespace)
        return namespace

    def test_single_database_raw_candidate_cannot_end_account_capture(self):
        namespace = self.namespace()
        # Establish the legacy failure: this raw key passes the message page,
        # but cannot validate the independently salted session database.
        self.assertTrue(namespace["_candidate_matches_page1"](self.message_raw))
        namespace["ACCOUNT_PROBE_PAGES"] = self.pages
        writes = []
        namespace["_write_result"] = lambda payload: writes.append(payload) or True
        process = types.SimpleNamespace(Kill=Mock())
        with patch.object(namespace["os"], "_exit") as exit_process:
            result = namespace["_save_valid_candidate"](
                self.message_raw, self.message_salt.hex(), "pbkdf_hmac_password", process
            )
        self.assertIs(result, False)
        process.Kill.assert_not_called()
        exit_process.assert_not_called()
        self.assertFalse(any("passphrase" in payload for payload in writes))
        self.assertEqual(namespace["DIAGNOSTICS"]["partial_candidates"], 1)

    def test_account_callback_keeps_waiting_until_shared_passphrase_arrives(self):
        namespace = self.namespace(account_probe_pages=self.pages)
        writes = []
        namespace["_write_result"] = lambda payload: writes.append(payload) or True
        process = types.SimpleNamespace(Kill=Mock())
        with patch.object(namespace["os"], "_exit") as exit_process:
            namespace["_save_valid_candidate"](
                self.message_raw, self.message_salt.hex(), "pbkdf_hmac_password", process
            )
            process.Kill.assert_not_called()
            namespace["_save_valid_candidate"](
                self.passphrase, self.session_salt.hex(), "pbkdf_database_password", process
            )
        process.Kill.assert_called_once()
        exit_process.assert_called_once_with(0)
        self.assertEqual(writes[-1]["passphrase"], self.passphrase.hex())
        self.assertEqual(writes[-1]["key_mode"], "sqlcipher_passphrase")
        self.assertEqual(writes[-1]["validated_roles"], ["message", "session"])
        self.assertEqual(writes[-1]["diagnostics"]["partial_candidates"], 1)
        diagnostics = json.dumps(writes[-1]["diagnostics"])
        self.assertNotIn(self.passphrase.hex(), diagnostics)
        self.assertNotIn(self.message_raw.hex(), diagnostics)

    def test_pbkdf_callback_ignores_single_role_raw_then_accepts_hex_passphrase(self):
        namespace = self.namespace(account_probe_pages=self.pages)
        namespace["lldb"] = types.SimpleNamespace(SBError=lambda: types.SimpleNamespace(Success=lambda: True))
        candidate = self.message_raw
        salt = bytes(value ^ 0x3A for value in self.message_salt)
        process = types.SimpleNamespace(
            ReadMemory=lambda address, length, error: (candidate if address == 100 else salt)[:length],
            Kill=Mock(),
        )
        registers = {"x0": 2, "x1": 100, "x2": 32, "x3": 200, "x4": 16, "x5": 5, "x6": 2}
        frame = types.SimpleNamespace(
            GetThread=lambda: types.SimpleNamespace(GetProcess=lambda: process),
            FindRegister=lambda name: types.SimpleNamespace(GetValueAsUnsigned=lambda: registers[name]),
        )
        writes = []
        namespace["_write_result"] = lambda payload: writes.append(payload) or True
        with patch.object(namespace["os"], "_exit") as exit_process:
            self.assertFalse(namespace["_pbkdf_callback"](frame, None, None))
            process.Kill.assert_not_called()
            self.assertEqual(namespace["DIAGNOSTICS"]["partial_candidates"], 1)
            candidate = self.passphrase.hex().encode("ascii")
            salt = self.session_salt
            registers.update(x2=64, x6=256000)
            namespace["_pbkdf_callback"](frame, None, None)
        process.Kill.assert_called_once()
        exit_process.assert_called_once_with(0)
        self.assertEqual(writes[-1]["validated_roles"], ["message", "session"])
        self.assertEqual(writes[-1]["passphrase"], self.passphrase.hex())

    def test_callback_does_not_kill_process_when_result_write_fails(self):
        namespace = self.namespace(account_probe_pages=self.pages)
        namespace["_write_result"] = lambda payload: False
        process = types.SimpleNamespace(Kill=Mock())
        with patch.object(namespace["os"], "_exit") as exit_process:
            self.assertFalse(namespace["_save_valid_candidate"](
                self.passphrase, self.message_salt.hex(), "pbkdf_database_password", process
            ))
        process.Kill.assert_not_called()
        exit_process.assert_not_called()

    def test_ready_and_result_include_transaction_id_without_secret_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ready = Path(temp_dir) / "ready.json"
            ready.touch(mode=0o600)
            result = Path(temp_dir) / "result.json"
            result.touch(mode=0o600)
            namespace = self.namespace(account_probe_pages=self.pages, ready_path=ready, transaction_id="synthetic-tx")
            namespace["RESULT_PATH"] = str(result)
            namespace["_write_ready"]({"status": "ready", "pid": 123})
            namespace["_write_result"]({"diagnostics": {"partial_candidates": 1}})
            self.assertEqual(json.loads(ready.read_text())["transaction_id"], "synthetic-tx")
            self.assertEqual(json.loads(result.read_text())["transaction_id"], "synthetic-tx")
            self.assertNotIn(self.passphrase.hex(), ready.read_text())

    def test_validator_rejects_per_database_raw_key_without_disclosing_it(self):
        with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
            validate_account_candidate(self.message_raw.hex(), self.pages)
        self.assertEqual(failure.exception.code, "account_key_validation_failed")
        self.assertIn("session", str(failure.exception))
        self.assertNotIn(self.message_raw.hex(), str(failure.exception))

    def test_validator_accepts_shared_passphrase(self):
        result = validate_account_candidate(self.passphrase.hex(), self.pages)
        self.assertEqual(result["key_mode"], "sqlcipher_passphrase")
        self.assertEqual(result["validated_roles"], ["message", "session"])
        self.assertNotIn(self.passphrase.hex(), json.dumps(result))

    def test_shared_raw_key_is_accepted_only_if_it_verifies_both_roles(self):
        pages = {
            "message": encrypted_page(self.passphrase, self.message_salt, raw=True),
            "session": encrypted_page(self.passphrase, self.session_salt, raw=True),
        }
        result = validate_account_candidate(self.passphrase.hex(), pages)
        self.assertEqual(result["key_mode"], "raw_enc_key")
        namespace = self.namespace(account_probe_pages=pages)
        for role in pages:
            self.assertEqual(namespace["_candidate_page1_mode"](self.passphrase, pages[role]), "raw_enc_key")

    def test_missing_short_and_plaintext_role_snapshots_fail_closed(self):
        for invalid_pages in (
            {},
            {"message": self.pages["message"]},
            {**self.pages, "session": b"short"},
            {**self.pages, "session": b"SQLite format 3\x00" + b"\0" * 4080},
        ):
            with self.subTest(roles=list(invalid_pages)):
                with self.assertRaises(MacOSDBKeyCaptureFailure):
                    normalize_account_probe_pages(invalid_pages)
                with self.assertRaises(MacOSDBKeyCaptureFailure):
                    self.namespace(account_probe_pages=invalid_pages)

    def test_invalid_candidate_errors_do_not_echo_input(self):
        for candidate in ("secret-invalid-key-text", "aa" * 31, b"tiny"):
            with self.subTest(candidate_type=type(candidate).__name__):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                    validate_account_candidate(candidate, self.pages)
                self.assertEqual(failure.exception.code, "account_key_invalid")
                self.assertNotIn(str(candidate), str(failure.exception))

    def test_read_account_snapshots_follow_realtime_layout_and_survive_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "db_storage"
            message = root / "message/message_0.db"
            session = root / "session/session.db"
            message.parent.mkdir(parents=True)
            session.parent.mkdir(parents=True)
            message.write_bytes(self.pages["message"])
            session.write_bytes(self.pages["session"])
            pages = read_account_probe_pages(message)
            self.assertEqual(pages, self.pages)
            self.assertTrue(validate_realtime_database_key(root, self.passphrase.hex())["valid"])
            self.assertEqual(validate_account_candidate(self.passphrase.hex(), pages)["modes"],
                             validate_realtime_database_key(root, self.passphrase.hex())["modes"])
            session.write_bytes(b"changed during relogin")
            self.assertEqual(pages, self.pages)
            self.assertTrue(validate_account_candidate(self.passphrase.hex(), pages)["valid"])

    def test_read_account_does_not_pick_a_neighbouring_accounts_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            selected = Path(temp_dir) / "account-a/db_storage/message/message_0.db"
            other = Path(temp_dir) / "account-b/db_storage/session/session.db"
            selected.parent.mkdir(parents=True)
            other.parent.mkdir(parents=True)
            selected.write_bytes(self.pages["message"])
            other.write_bytes(self.pages["session"])
            with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                read_account_probe_pages(selected)
            self.assertEqual(failure.exception.code, "account_probe_missing")

    def test_read_account_rejects_symlink_to_another_accounts_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "selected"
            root.mkdir()
            message = root / "message_0.db"
            message.write_bytes(self.pages["message"])
            other = Path(temp_dir) / "other-session.db"
            other.write_bytes(self.pages["session"])
            (root / "session.db").symlink_to(other)
            with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                read_account_probe_pages(message)
            self.assertEqual(failure.exception.code, "account_probe_path_invalid")

    def test_selected_probe_symlink_cannot_silently_select_another_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "selected/db_storage"
            other = Path(temp_dir) / "other/db_storage"
            root.mkdir(parents=True)
            other.mkdir(parents=True)
            (other / "message_0.db").write_bytes(self.pages["message"])
            (other / "session.db").write_bytes(self.pages["session"])
            selected = root / "message_0.db"
            selected.symlink_to(other / "message_0.db")
            with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                read_account_probe_pages(selected)
            self.assertEqual(failure.exception.code, "account_probe_path_invalid")

    def test_legacy_flat_and_combined_roles_follow_realtime_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            message = root / "msg0.db"
            message.write_bytes(self.pages["message"])
            (root / "Session.db").write_bytes(self.pages["session"])
            self.assertEqual(read_account_probe_pages(message, account_root=root), self.pages)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            combined = root / "MicroMsg.db"
            combined.write_bytes(self.pages["message"])
            paths = resolve_account_probe_paths(combined)
            self.assertEqual(paths, {"message": combined.resolve(), "session": combined.resolve()})

    def test_capture_wrapper_uses_snapshots_and_revalidates_structured_result(self):
        from wechat_decrypt_tool.macos_clone_capture import capture_salt_matched_passphrase

        def fake_lldb(command, *, timeout):
            command_path = Path(command)
            result_path = command_path.parent / "result.json"
            script_path = command_path.parent / "capture_callback.py"
            self.assertIn("ACCOUNT_PROBE_PAGES", script_path.read_text())
            result_path.write_text(json.dumps({
                "passphrase": self.passphrase.hex(), "salt": self.message_salt.hex(),
                "transaction_id": "synthetic-tx", "diagnostics": {"partial_candidates": 1},
            }))
            return ""

        with (
            patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
            patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/fake/lldb"),
            patch("wechat_decrypt_tool.macos_clone_capture._build_lldb_capture_command", side_effect=lambda path, timeout: str(path)),
            patch("wechat_decrypt_tool.macos_clone_capture._run_as_administrator", side_effect=fake_lldb),
        ):
            result = capture_salt_matched_passphrase(
                pid=123, expected_salts=[self.message_salt], probe_db_path="/nonexistent/not-read.db",
                account_probe_pages=self.pages, return_details=True, transaction_id="synthetic-tx",
            )
        self.assertEqual(result["passphrase"], self.passphrase.hex())
        self.assertEqual(result["key_mode"], "sqlcipher_passphrase")
        self.assertEqual(result["validated_roles"], ["message", "session"])

    def test_capture_wrapper_does_not_trust_raw_or_stale_lldb_result(self):
        from wechat_decrypt_tool.macos_clone_capture import capture_salt_matched_passphrase

        for candidate, transaction, expected_code in (
            (self.message_raw, "synthetic-tx", "account_key_validation_failed"),
            (self.passphrase, "stale-tx", "capture_transaction_mismatch"),
        ):
            def fake_lldb(command, *, timeout):
                (Path(command).parent / "result.json").write_text(json.dumps({
                    "passphrase": candidate.hex(), "salt": self.message_salt.hex(),
                    "transaction_id": transaction,
                }))
                return ""

            with (
                self.subTest(expected_code=expected_code),
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/fake/lldb"),
                patch("wechat_decrypt_tool.macos_clone_capture._build_lldb_capture_command", side_effect=lambda path, timeout: str(path)),
                patch("wechat_decrypt_tool.macos_clone_capture._run_as_administrator", side_effect=fake_lldb),
            ):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                    capture_salt_matched_passphrase(
                        pid=123, expected_salts=[self.message_salt], probe_db_path="/nonexistent/not-read.db",
                        account_probe_pages=self.pages, return_details=True, transaction_id="synthetic-tx",
                    )
            self.assertEqual(failure.exception.code, expected_code)
            self.assertNotIn(candidate.hex(), str(failure.exception))


if __name__ == "__main__":
    unittest.main()
