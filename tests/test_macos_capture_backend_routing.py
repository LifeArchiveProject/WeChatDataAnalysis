"""Isolated workflow checks: never attach to, launch, or restore a real app."""
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from wechat_decrypt_tool import macos_inplace_capture as workflow
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure


SYNTHETIC_PAGES = {"message": b"m" * 4096, "session": b"s" * 4096}


@pytest.fixture
def capture_case(tmp_path):
    app = tmp_path / "WeChat.app"
    (app / "Contents/Resources").mkdir(parents=True)
    (app / "Contents/Resources/wechat.dylib").write_bytes(b"synthetic dylib marker; never executed")
    state = {"transaction_id": "test-transaction", "version": "4.1.13", "build": "fixture", "official_cdhash": "fixture-hash"}
    probe = tmp_path / "db_storage/message/message_0.db"
    probe.parent.mkdir(parents=True)
    probe.write_bytes(SYNTHETIC_PAGES["message"])
    session = tmp_path / "db_storage/session/session.db"
    session.parent.mkdir(parents=True)
    session.write_bytes(SYNTHETIC_PAGES["session"])
    with ExitStack() as stack:
        # Real serialization stays enabled; OS/application side effects do not.
        stack.enter_context(patch("subprocess.run", side_effect=AssertionError("external process execution is forbidden in routing tests")))
        stack.enter_context(patch.object(workflow, "_acquire_installation_lock", return_value={"transaction_id": state["transaction_id"]}))
        stack.enter_context(patch.object(workflow, "_release_installation_lock"))
        stack.enter_context(patch.object(workflow.platform, "mac_ver", return_value=("26.0", (), "arm64")))
        stack.enter_context(patch.object(workflow, "normalize_wechat_app_path", return_value=app))
        stack.enter_context(patch.object(workflow, "_require_prepared_process", return_value=(state, 321)))
        stack.enter_context(patch.object(workflow, "_candidate_bundle_pids", return_value=[321]))
        restore = stack.enter_context(patch.object(workflow, "_restore_after_terminal_path", return_value={"official_wechat_verified": True, "official_wechat_restored": True}))
        stack.enter_context(patch.object(workflow, "has_pending_in_place_capture", return_value=True))
        yield app, state, probe, restore, stack


def test_macos27_preflight_selects_software_without_running_native(tmp_path, capture_case):
    app, state, _, _, stack = capture_case
    stack.enter_context(patch.object(workflow.platform, "mac_ver", return_value=("27.0", (), "arm64")))
    native = stack.enter_context(patch.object(workflow, "preflight_native_wcdb_capture"))
    software = stack.enter_context(patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints", return_value={"pid": 321, "pbkdf_locations": 1, "key_return_locations": 0}))
    result = workflow.preflight_prepared_in_place_capture(app, backup_root=tmp_path, debug_root=tmp_path)
    assert result["capture_backend"] == "lldb"
    assert state["preflight"]["transaction_id"] == state["transaction_id"]
    native.assert_not_called()
    software.assert_called_once()


def test_native_preflight_failure_routes_to_software(tmp_path, capture_case):
    app, state, _, restore, stack = capture_case
    stack.enter_context(patch.object(workflow, "_preferred_capture_backend", return_value="native"))
    stack.enter_context(patch.object(workflow, "preflight_native_wcdb_capture", side_effect=MacOSDBKeyCaptureFailure("native_breakpoint_shape_mismatch", "fixture")))
    software = stack.enter_context(patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints", return_value={"pid": 321, "pbkdf_locations": 1}))
    result = workflow.preflight_prepared_in_place_capture(app, backup_root=tmp_path, debug_root=tmp_path)
    assert result["capture_backend"] == "lldb"
    software.assert_called_once()
    restore.assert_not_called()


def test_cancelled_authorization_never_reprompts_via_fallback(tmp_path, capture_case):
    app, _, _, restore, stack = capture_case
    stack.enter_context(patch.object(workflow, "_preferred_capture_backend", return_value="native"))
    stack.enter_context(patch.object(workflow, "preflight_native_wcdb_capture", side_effect=MacOSDBKeyCaptureFailure("administrator_cancelled", "cancelled")))
    software = stack.enter_context(patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints"))
    with pytest.raises(MacOSDBKeyCaptureFailure, match="cancelled"):
        workflow.preflight_prepared_in_place_capture(app, backup_root=tmp_path, debug_root=tmp_path)
    software.assert_not_called()
    restore.assert_called_once()


def prepare_capture_mocks(stack, state, backend):
    state["preflight"] = {"pid": 321, "capture_backend": backend, "transaction_id": state["transaction_id"]}
    validate = stack.enter_context(patch("wechat_decrypt_tool.macos_capture_validation.validate_account_candidate", return_value={"key_mode": "sqlcipher_passphrase", "validated_roles": ["message", "session"]}))
    save = stack.enter_context(patch.object(workflow, "save_passphrase", return_value=Path("/fixture/key.json")))
    return SYNTHETIC_PAGES, validate, save


def test_capture_uses_software_chosen_by_preflight(tmp_path, capture_case):
    app, state, probe, restore, stack = capture_case
    pages, validate, save = prepare_capture_mocks(stack, state, "lldb")
    software = stack.enter_context(patch.object(workflow, "capture_salt_matched_passphrase", return_value={"passphrase": "ab" * 32, "key_mode": "sqlcipher_passphrase", "validated_roles": ["message", "session"]}))
    native = stack.enter_context(patch.object(workflow, "capture_native_wcdb_key"))
    result = workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path)
    native.assert_not_called()
    assert software.call_args.kwargs["account_probe_pages"] == pages
    assert software.call_args.kwargs["transaction_id"] == state["transaction_id"]
    assert result["account_roles_validated"] is True
    assert software.call_args.kwargs["expected_salts"] == [pages["message"][:16], pages["session"][:16]]
    validate.assert_called_once_with("ab" * 32, pages)
    save.assert_called_once_with("ab" * 32)
    restore.assert_called_once()


def test_native_partial_candidate_is_not_saved(tmp_path, capture_case):
    app, state, probe, restore, stack = capture_case
    pages, validate, save = prepare_capture_mocks(stack, state, "native")
    validate.side_effect = MacOSDBKeyCaptureFailure("account_key_validation_failed", "partial fixture")
    stack.enter_context(patch.object(workflow, "capture_native_wcdb_key", return_value={"db_key": "ab" * 32}))
    with pytest.raises(MacOSDBKeyCaptureFailure, match="partial fixture"):
        workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path)
    save.assert_not_called()
    validate.assert_called_once_with("ab" * 32, pages)
    restore.assert_called_once()


def test_native_timeout_remembers_software_for_next_login_not_empty_wait(tmp_path, capture_case):
    app, state, probe, restore, stack = capture_case
    prepare_capture_mocks(stack, state, "native")
    stack.enter_context(patch.object(workflow, "capture_native_wcdb_key", side_effect=MacOSDBKeyCaptureFailure("native_capture_timeout", "fixture timeout")))
    software = stack.enter_context(patch.object(workflow, "capture_salt_matched_passphrase"))
    with pytest.raises(MacOSDBKeyCaptureFailure) as error:
        workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path)
    assert error.value.code == "native_capture_timeout"
    assert "LLDB" in str(error.value)
    software.assert_not_called()
    restore.assert_called_once()
    # This is an older OS with a present native dylib: the stored preference,
    # not the macOS-27/missing-image default, must cause the next-run fallback.
    remembered = json.loads((tmp_path / "capture-backend-preference.json").read_text(encoding="utf-8"))
    assert remembered["backend"] == "lldb"
    assert remembered["identity"] == workflow._backend_identity(state)
    assert workflow._preferred_capture_backend(app, state, tmp_path) == "lldb"


def test_stale_preflight_cannot_target_another_transaction(tmp_path, capture_case):
    app, state, probe, _, stack = capture_case
    prepare_capture_mocks(stack, state, "native")
    state["preflight"]["transaction_id"] = "previous-transaction"
    native = stack.enter_context(patch.object(workflow, "capture_native_wcdb_key"))
    with pytest.raises(MacOSDBKeyCaptureFailure) as error:
        workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path)
    assert error.value.code == "capture_preflight_stale"
    native.assert_not_called()


UNCONFIRMED_NATIVE_CLEANUP = [
    ("native_cleanup_failed", "debug state cleanup failed"),
    ("native_capture_helper_terminated", "helper terminated"),
    ("native_breakpoint_install_failed", "partial breakpoint installation"),
    ("native_exception_port_failed", "exception port installation failed"),
    ("administrator_failed", "execution error (1009)"),
    ("administrator_failed", "SIGKILL"),
]


@pytest.mark.parametrize("code,message", UNCONFIRMED_NATIVE_CLEANUP)
def test_preflight_unconfirmed_cleanup_restores_without_attaching_lldb(tmp_path, capture_case, code, message):
    app, state, _, restore, stack = capture_case
    stack.enter_context(patch.object(workflow, "_preferred_capture_backend", return_value="native"))
    native = stack.enter_context(patch.object(workflow, "preflight_native_wcdb_capture", side_effect=MacOSDBKeyCaptureFailure(code, message)))
    software = stack.enter_context(patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints"))
    with pytest.raises(MacOSDBKeyCaptureFailure) as error:
        workflow.preflight_prepared_in_place_capture(app, backup_root=tmp_path, debug_root=tmp_path)
    assert error.value.code == code
    assert "新事务" in str(error.value)
    assert "LLDB" in str(error.value)
    native.assert_called_once()
    software.assert_not_called()
    restore.assert_called_once()
    remembered = json.loads((tmp_path / "capture-backend-preference.json").read_text(encoding="utf-8"))
    assert remembered == {"backend": "lldb", "identity": workflow._backend_identity(state)}


@pytest.mark.parametrize("code,message", UNCONFIRMED_NATIVE_CLEANUP)
def test_capture_unconfirmed_cleanup_restores_without_attaching_lldb(tmp_path, capture_case, code, message):
    app, state, probe, restore, stack = capture_case
    _, validate, save = prepare_capture_mocks(stack, state, "native")
    native = stack.enter_context(patch.object(workflow, "capture_native_wcdb_key", side_effect=MacOSDBKeyCaptureFailure(code, message)))
    software = stack.enter_context(patch.object(workflow, "capture_salt_matched_passphrase"))
    preflight = stack.enter_context(patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints"))
    with pytest.raises(MacOSDBKeyCaptureFailure) as error:
        workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path)
    assert error.value.code == code
    assert "新事务" in str(error.value)
    assert "LLDB" in str(error.value)
    native.assert_called_once()
    software.assert_not_called()
    preflight.assert_not_called()
    validate.assert_not_called()
    save.assert_not_called()
    restore.assert_called_once()
    assert workflow._preferred_capture_backend(app, state, tmp_path) == "lldb"


def test_attach_denial_is_not_blindly_retried(tmp_path, capture_case):
    app, _, _, restore, stack = capture_case
    stack.enter_context(patch.object(workflow, "_preferred_capture_backend", return_value="native"))
    stack.enter_context(patch.object(workflow, "preflight_native_wcdb_capture", side_effect=MacOSDBKeyCaptureFailure("native_attach_failed", "attach denied")))
    software = stack.enter_context(patch("wechat_decrypt_tool.macos_clone_capture.preflight_capture_breakpoints"))
    with pytest.raises(MacOSDBKeyCaptureFailure) as error:
        workflow.preflight_prepared_in_place_capture(app, backup_root=tmp_path, debug_root=tmp_path)
    assert error.value.code == "native_attach_failed"
    software.assert_not_called()
    restore.assert_called_once()
