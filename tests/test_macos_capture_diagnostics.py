"""Capture diagnostics tests: mocked orchestration only, never attach to WeChat."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from unittest.mock import Mock

import pytest

from wechat_decrypt_tool import macos_native_capture as native
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure


SOURCE = Path(native.__file__).parent / "native/macos/source/wcdb_native_capture.c"
SECRET = "d9" * 32


@pytest.fixture
def helper_call(monkeypatch):
    """Every operation that could build, inspect, authorize, or attach is mocked."""
    monkeypatch.setattr(native, "ensure_native_capture_helper", Mock(return_value=Path("/mock/helper")))
    monkeypatch.setattr(native, "_resolve_wechat_dylib", Mock(return_value=Path("/mock/wechat.dylib")))
    monkeypatch.setattr(native, "_resolve_pbkdf_stub_address", Mock(return_value=4096))
    monkeypatch.setattr(native, "_resolve_runtime_breakpoint_address", Mock(return_value=8192))
    administrator = Mock()
    monkeypatch.setattr(native, "_run_as_administrator", administrator)
    monkeypatch.setattr(native, "get_logger", Mock(return_value=Mock()))

    def invoke(payload=None, *, failure=None, **kwargs):
        administrator.side_effect = failure
        administrator.return_value = json.dumps(payload or {})
        return native.capture_native_wcdb_key(
            pid=123, wechat_app=Path("/mock/WeChat.app"),
            debug_root=Path("/mock/debug"), probe_db_path=Path("/mock/encrypted.db"),
            **kwargs,
        )

    return invoke, administrator


def successful_payload(**extra):
    return {
        "status": "ok", "mode": "capture", "method": "macos_native_mach",
        "pid": 123, "stub_file_address": 4096, "validated": True,
        "db_key": SECRET, **extra,
    }


def test_diagnostics_accept_only_bounded_integer_counters_and_known_stages():
    payload = {
        "diagnostics": {
            "pbkdf_calls": 7, "wcdb_profile_hits": True, "rounds2_hits": "3",
            "rounds256000_hits": -1, "salt_matches": 2**64,
            "candidate_rejects": 1.5, "salt_read_failures": [],
            "candidate_read_failures": {"db_key": SECRET},
            "last_stage": "rounds2_seen", "db_key": SECRET, "salt": SECRET,
            "page1": SECRET, "raw_payload": SECRET,
        }
    }
    assert native._parse_capture_diagnostics(payload) == {
        "pbkdf_calls": 7, "last_stage": "rounds2_seen",
    }
    payload["diagnostics"]["last_stage"] = SECRET
    assert native._parse_capture_diagnostics(payload) == {"pbkdf_calls": 7}


@pytest.mark.parametrize("invalid", [None, [], SECRET, 5])
def test_non_object_diagnostics_allow_only_legacy_counter(invalid):
    assert native._parse_capture_diagnostics({"diagnostics": invalid, "pbkdf_calls": 9}) == {"pbkdf_calls": 9}


def test_native_error_exposes_safe_counters_but_no_secret_or_raw_message(helper_call):
    invoke, _ = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke({
            "status": "error", "code": "native_capture_timeout", "message": SECRET,
            "db_key": SECRET, "salt": SECRET, "page1": SECRET,
            "diagnostics": {
                "pbkdf_calls": 4, "wcdb_profile_hits": 4, "rounds2_hits": 4,
                "rounds256000_hits": 0, "candidate_rejects": 0,
                "last_stage": "rounds2_seen", "raw_payload": SECRET,
            },
        })
    assert raised.value.code == "native_capture_timeout"
    assert "rounds2_hits=4" in str(raised.value)
    assert "last_stage=rounds2_seen" in str(raised.value)
    assert "不能将单库派生密钥作为账号密钥" in str(raised.value)
    assert SECRET not in str(raised.value)


def test_unknown_code_and_stage_are_not_echoed(helper_call):
    invoke, _ = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke({"status": "error", "code": SECRET, "message": SECRET, "diagnostics": {"last_stage": SECRET}})
    assert raised.value.code == "native_capture_failed"
    assert SECRET not in str(raised.value)


def test_failure_logger_receives_only_fixed_code_and_whitelisted_diagnostics(helper_call):
    invoke, _ = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure):
        invoke({
            "status": "error", "code": "native_capture_timeout", "message": SECRET,
            "db_key": SECRET, "salt": SECRET, "page1": SECRET, "path": "/private/secret-account",
            "diagnostics": {"pbkdf_calls": 3, "rounds2_hits": 3, "last_stage": "rounds2_seen", "payload": SECRET},
        })
    native.get_logger.assert_called_once_with(native.__name__)
    warning = native.get_logger.return_value.warning
    warning.assert_called_once_with(
        "native capture failed: code=%s diagnostics=%s", "native_capture_timeout",
        {"pbkdf_calls": 3, "rounds2_hits": 3, "last_stage": "rounds2_seen"},
    )
    assert SECRET not in str(warning.call_args)
    assert "/private/secret-account" not in str(warning.call_args)


@pytest.mark.parametrize("code", [
    "native_capture_target_exited", "native_capture_interrupted", "native_capture_wait_failed", "native_cleanup_failed",
])
def test_early_terminal_results_are_not_reported_as_timeouts(helper_call, code):
    invoke, administrator = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke({"status": "error", "code": code, "diagnostics": {"pbkdf_calls": 2}})
    assert raised.value.code == code
    assert "超时" not in str(raised.value)
    assert "pbkdf_calls=2" in str(raised.value)
    administrator.assert_called_once()


def test_embedded_administrator_error_preserves_safe_diagnostics(helper_call):
    invoke, _ = helper_call
    payload = {"status": "error", "code": "native_capture_timeout", "message": SECRET, "diagnostics": {"pbkdf_calls": 0}}
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke(failure=MacOSDBKeyCaptureFailure("administrator_failed", f"admin error: {json.dumps(payload)} (1)"))
    assert raised.value.code == "native_capture_timeout"
    assert "未命中 PBKDF 断点" in str(raised.value)
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize("error", ["execution error (1009)", "Killed: 9", "SIGKILL", "terminated"])
def test_helper_termination_without_json_is_explicit_and_redacted(helper_call, error):
    invoke, _ = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke(failure=MacOSDBKeyCaptureFailure("administrator_failed", f"{error} {SECRET}"))
    assert raised.value.code == "native_capture_helper_terminated"
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize("code", ["administrator_cancelled", "administrator_timeout", "administrator_failed"])
def test_administrator_failures_are_redacted_and_not_retried(helper_call, code):
    invoke, administrator = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke(failure=MacOSDBKeyCaptureFailure(code, SECRET))
    assert raised.value.code == code
    assert SECRET not in str(raised.value)
    administrator.assert_called_once()


def test_success_returns_only_expected_fields_and_filtered_diagnostics(helper_call):
    invoke, _ = helper_call
    payload = invoke(successful_payload(
        salt=SECRET, page1=SECRET, raw_payload=SECRET,
        diagnostics={"pbkdf_calls": 3, "last_stage": "validated", "salt": SECRET},
    ))
    assert payload["db_key"] == SECRET
    assert payload["diagnostics"] == {"pbkdf_calls": 3, "last_stage": "validated"}
    assert payload["pbkdf_calls"] == 3
    assert not {"salt", "page1", "raw_payload"} & payload.keys()


@pytest.mark.parametrize("validated", ["true", "false", 1, None])
def test_validation_requires_a_real_boolean(helper_call, validated):
    invoke, _ = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke(successful_payload(validated=validated))
    assert raised.value.code == "native_capture_unvalidated"


def test_transaction_id_is_forwarded_to_native_ready_protocol(helper_call):
    invoke, administrator = helper_call
    invoke(successful_payload(), ready_file=Path("/mock/ready.json"), transaction_id="tx-123_abc")
    command = shlex.split(administrator.call_args.args[0])
    assert command[command.index("--transaction-id") + 1] == "tx-123_abc"
    assert command[command.index("--ready-file") + 1] == "/mock/ready.json"


@pytest.mark.parametrize("transaction_id", [None, ""])
def test_missing_transaction_id_is_backward_compatible(helper_call, transaction_id):
    invoke, administrator = helper_call
    invoke(successful_payload(), transaction_id=transaction_id)
    assert "--transaction-id" not in shlex.split(administrator.call_args.args[0])


@pytest.mark.parametrize("transaction_id", ['tx"bad', "x" * 129, "a/b", "line\n"])
def test_invalid_transaction_never_starts_helper(helper_call, transaction_id):
    invoke, administrator = helper_call
    with pytest.raises(MacOSDBKeyCaptureFailure) as raised:
        invoke(successful_payload(), transaction_id=transaction_id)
    assert raised.value.code == "native_capture_invalid_transaction"
    administrator.assert_not_called()


def test_native_source_emits_diagnostics_on_error_and_keeps_account_key_gate():
    source = SOURCE.read_text(encoding="utf-8")
    error = source[source.index("static void json_error"):source.index("static void on_signal")]
    assert "json_diagnostics();" in error
    diagnostics = source[source.index("static void json_diagnostics"):source.index("static void json_success_preflight")]
    for name in native._DIAGNOSTIC_COUNTERS:
        assert name in diagnostics
    assert "db_key_hex" not in diagnostics
    assert "g_ctx.page1" not in diagnostics
    operands = source[source.index("static bool breakpoint_operands_match"):source.index("static bool salt_matches_expected")]
    assert "state->__x[6] == 256000" in operands
    callback = source[source.index("static kern_return_t handle_breakpoint"):source.index("kern_return_t catch_exception_raise(")]
    assert callback.index("g_ctx.rounds2_hits += 1") < callback.index("!breakpoint_operands_match(&state)")
    assert callback.index("!breakpoint_operands_match(&state)") < callback.index("uint8_t candidate[KEY_SIZE]")
    # The existing successful disposal strategy remains unchanged.
    assert "(void)kill(g_ctx.target_pid, SIGKILL);" in callback


def test_native_source_checks_dead_target_before_timeout_and_marks_ready_transaction():
    source = SOURCE.read_text(encoding="utf-8")
    wait = source[source.index("static kern_return_t wait_for_breakpoint"):source.index("static int run_preflight")]
    assert wait.index("MACH_PORT_TYPE_DEAD_NAME") < wait.index("return KERN_OPERATION_TIMED_OUT")
    assert "kill(g_ctx.target_pid, 0)" in wait
    ready = source[source.index("static bool write_ready_file"):source.index("static bool streq")]
    assert 'transaction_id\\\":\\\"' in ready
    assert "macos_native_mach" in ready
    assert 'pid\\\":%d' in ready


def test_native_preflight_requires_suspend_install_rollback_and_resume_success():
    source = SOURCE.read_text(encoding="utf-8")
    preflight = source[source.index("static int run_preflight"):source.index("static int run_capture")]
    suspend = preflight.index("kr = task_suspend(g_ctx.task);")
    install = preflight.index("kr = install_hardware_breakpoints(g_ctx.task);")
    restore = preflight.index("kern_return_t restore_kr = restore_hardware_breakpoints();")
    resume = preflight.index("kern_return_t resume_kr = task_resume(g_ctx.task);")
    gate = preflight.index("if (g_ctx.cleanup_failed || restore_kr != KERN_SUCCESS || resume_kr != KERN_SUCCESS)")
    success = preflight.index("json_success_preflight(options);")
    assert suspend < install < restore < resume < gate < success
    assert 'json_error("native_cleanup_failed"' in preflight[suspend:install]
    assert "return 1;" in preflight[suspend:install]
    assert 'json_error("native_cleanup_failed"' in preflight[gate:success]
    assert 'json_error("native_breakpoint_install_failed"' in preflight[gate:success]
    assert "(void)restore_hardware_breakpoints();" not in preflight
    assert "(void)task_resume(g_ctx.task);" not in preflight


def test_native_rollback_only_writes_valid_states_that_were_modified():
    source = SOURCE.read_text(encoding="utf-8")
    restore = source[source.index("static kern_return_t restore_hardware_breakpoints"):source.index("static kern_return_t install_hardware_breakpoints")]
    install = source[source.index("static kern_return_t install_hardware_breakpoints"):source.index("static bool thread_set_matches")]
    guard = "if (thread == MACH_PORT_NULL || !g_ctx.saved_debug_valid[index] || !g_ctx.debug_state_modified[index])"
    assert restore.index(guard) < restore.index("kern_return_t kr = thread_set_state(")
    assert "continue;" in restore[restore.index(guard):restore.index("kern_return_t kr = thread_set_state(")]
    assert install.index("saved_states[index] = debug_state;") < install.index("saved_valid[index] = true;")
    set_state = install.index("kr = thread_set_state(")
    mark_modified = install.index("modified[index] = true;")
    assert set_state < mark_modified
    # Both read and write failures must leave the current/unvisited entry false.
    assert "return kr;" in install[install.index("kr = thread_get_state("):install.index("saved_valid[index] = true;")]
    assert "return kr;" in install[set_state:mark_modified]
    assert "bool *saved_valid = calloc(thread_count, sizeof(*saved_valid));" in install
    assert "bool *modified = calloc(thread_count, sizeof(*modified));" in install


def test_native_cleanup_failure_survives_state_release_and_stops_capture():
    source = SOURCE.read_text(encoding="utf-8")
    release = source[source.index("static void release_debug_threads"):source.index("static kern_return_t restore_hardware_breakpoints")]
    restore = source[source.index("static kern_return_t restore_hardware_breakpoints"):source.index("static kern_return_t install_hardware_breakpoints")]
    refresh = source[source.index("static kern_return_t refresh_hardware_breakpoints_if_needed"):source.index("static kern_return_t install_exception_port")]
    capture = source[source.index("static int run_capture"):source.index("int main(")]
    assert "cleanup_failed = false" not in release
    assert "free(g_ctx.saved_debug_valid);" in release
    assert "free(g_ctx.debug_state_modified);" in release
    assert "g_ctx.cleanup_failed = true;" in restore
    assert restore.index("g_ctx.cleanup_failed = true;") < restore.index("    release_debug_threads();", restore.index("g_ctx.cleanup_failed = true;"))
    assert "if (kr == KERN_SUCCESS) {\n        kr = install_hardware_breakpoints(g_ctx.task);" in refresh
    assert 'if (g_ctx.cleanup_failed && !g_ctx.captured) {\n        json_error("native_cleanup_failed"' in capture
    assert capture.index("if (g_ctx.cleanup_failed && !g_ctx.captured)") < capture.index("json_success_capture(options);")
