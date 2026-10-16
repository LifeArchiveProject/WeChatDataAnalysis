"""Progress-only fixtures: no debugger, real database, or application mutation."""
import json
import sys
import types
from unittest.mock import Mock

import pytest

from wechat_decrypt_tool import macos_inplace_capture as workflow
from wechat_decrypt_tool import macos_capture_validation as validation
from wechat_decrypt_tool.macos_clone_capture import build_lldb_salt_capture_script
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure


def write_progress(tmp_path, *, phase="waiting_authorization", status="ready", **marker_overrides):
    state = {
        "schema_version": 2, "stage": "capturing", "transaction_id": "fixture-tx",
        "debug_pid": 123, "capture_backend": "lldb", "capture_phase": phase,
    }
    workflow._write_state(tmp_path, state)
    marker = {"transaction_id": "fixture-tx", "pid": 123, "method": "macos_lldb_stub", "status": status}
    marker.update(marker_overrides)
    workflow._native_capture_ready_path(tmp_path).write_text(json.dumps(marker))
    return state


@pytest.mark.parametrize("status,phase,ready", [("ready", "monitoring", True), ("captured", "captured", False)])
def test_progress_tracks_validated_capture_without_exposing_result(tmp_path, status, phase, ready):
    write_progress(tmp_path, status=status, db_key="ab" * 32, path="/private/fixture")
    result = workflow.get_in_place_capture_status(debug_root=tmp_path)
    assert result["capture_phase"] == phase
    assert result["monitor_ready"] is ready
    assert "ab" * 32 not in str(result)
    assert "/private" not in str(result)


@pytest.mark.parametrize("overrides", [{"pid": 999}, {"transaction_id": "old-tx"}, {"method": "untrusted"}])
def test_stale_or_unbound_captured_marker_cannot_advance_progress(tmp_path, overrides):
    write_progress(tmp_path, status="captured", **overrides)
    result = workflow.get_in_place_capture_status(debug_root=tmp_path)
    assert result["capture_phase"] == "waiting_authorization"
    assert result["monitor_ready"] is False


@pytest.mark.parametrize("phase", ["validating", "captured", "restoring"])
def test_post_capture_phase_wins_over_old_ready_file(tmp_path, phase):
    write_progress(tmp_path, phase=phase)
    result = workflow.get_in_place_capture_status(debug_root=tmp_path)
    assert result["capture_phase"] == phase
    assert result["monitor_ready"] is False


def test_phase_is_whitelisted_and_idle_has_no_success_claim(tmp_path):
    state = write_progress(tmp_path, phase="ab" * 32, status="untrusted")
    result = workflow.get_in_place_capture_status(debug_root=tmp_path)
    assert result["capture_phase"] is None
    assert "ab" * 32 not in str(result)
    state["stage"] = "recovery_blocked"
    state["capture_phase"] = "captured"
    workflow._write_state(tmp_path, state)
    assert workflow.get_in_place_capture_status(debug_root=tmp_path)["capture_phase"] is None
    workflow._remove_state(tmp_path)
    assert workflow.get_in_place_capture_status(debug_root=tmp_path)["capture_phase"] is None


def test_stored_monitoring_phase_is_not_a_substitute_for_armed_signal(tmp_path):
    write_progress(tmp_path, phase="monitoring", status="untrusted")
    result = workflow.get_in_place_capture_status(debug_root=tmp_path)
    assert result["capture_phase"] == "waiting_authorization"
    assert result["monitor_ready"] is False


def test_progress_write_failure_keeps_recovery_state_and_allows_retry(tmp_path, monkeypatch):
    state = write_progress(tmp_path)
    before = workflow._state_path(tmp_path).read_bytes()
    with monkeypatch.context() as patcher:
        patcher.setattr(workflow.os, "write", Mock(side_effect=OSError("fixture disk error")))
        workflow._set_capture_phase(tmp_path, state, "validating")
    assert workflow._state_path(tmp_path).read_bytes() == before
    assert not list(tmp_path.glob(".prepared-in-place-capture.*.tmp"))
    workflow._set_capture_phase(tmp_path, state, "restoring")
    assert workflow.get_in_place_capture_status(debug_root=tmp_path)["capture_phase"] == "restoring"


class ScriptExit(Exception):
    pass


@pytest.mark.parametrize("marker_fails", [False, True])
def test_success_announces_capture_before_expected_shutdown(tmp_path, monkeypatch, marker_fails):
    script = build_lldb_salt_capture_script(tmp_path / "result.json", [b"s" * 16], transaction_id="fixture-tx")
    namespace = {"__name__": "fixture_callback"}
    monkeypatch.setitem(sys.modules, "lldb", types.SimpleNamespace())
    exec(compile(script, "<synthetic-callback>", "exec"), namespace)
    namespace["ACCOUNT_PROBE_PAGES"] = {"message": b"m" * 4096, "session": b"s" * 4096}
    namespace["_candidate_page1_mode"] = lambda *args: "sqlcipher_passphrase"
    events = []
    namespace["_write_result"] = lambda payload: events.append("validated_result") or True

    def progress(payload):
        events.append("captured_notice")
        assert payload == {"status": "captured", "method": "macos_lldb_stub", "pid": 123}
        if marker_fails:
            raise OSError("fixture progress file unavailable")
        return True

    namespace["_write_ready"] = progress
    namespace["os"] = types.SimpleNamespace(_exit=Mock(side_effect=ScriptExit))
    process = types.SimpleNamespace(GetProcessID=lambda: 123, Kill=lambda: events.append("planned_shutdown"))
    with pytest.raises(ScriptExit):
        namespace["_save_valid_candidate"](b"k" * 32, "s", "fixture", process)
    assert events == ["validated_result", "captured_notice", "planned_shutdown"]


@pytest.mark.parametrize("capture_fails", [False, True])
def test_workflow_reports_validation_and_restoration_without_leaking_key(tmp_path, monkeypatch, capture_fails):
    app = tmp_path / "WeChat.app"
    app.mkdir()
    probe = tmp_path / "message_0.db"
    probe.write_bytes(b"m" * 4096)
    state = {
        "schema_version": 2, "stage": "preflight_passed", "transaction_id": "fixture-tx",
        "debug_pid": 123,
        "preflight": {"pid": 123, "capture_backend": "lldb", "transaction_id": "fixture-tx"},
    }
    monkeypatch.setattr(workflow, "normalize_wechat_app_path", lambda *a: app)
    monkeypatch.setattr(workflow, "_require_prepared_process", lambda *a, **kw: (state, 123))
    monkeypatch.setattr(workflow, "_candidate_bundle_pids", lambda *a: [123])
    monkeypatch.setattr(validation, "read_account_probe_pages", lambda *a: {"message": b"m" * 4096, "session": b"s" * 4096})
    events = []

    def capture(**kwargs):
        assert workflow.get_in_place_capture_status(debug_root=tmp_path)["capture_phase"] == "waiting_authorization"
        if capture_fails:
            raise MacOSDBKeyCaptureFailure("fixture_failure", "fixture failure")
        return {"passphrase": "ab" * 32}

    def validate(*args):
        events.append("validate")
        assert workflow.get_in_place_capture_status(debug_root=tmp_path)["capture_phase"] == "validating"
        return {"key_mode": "sqlcipher_passphrase", "validated_roles": ["message", "session"]}

    def restore(*args, **kwargs):
        events.append("restore")
        status = workflow.get_in_place_capture_status(debug_root=tmp_path)
        assert status["capture_phase"] == "restoring"
        assert status["monitor_ready"] is False
        assert "ab" * 32 not in workflow._state_path(tmp_path).read_text()
        workflow._remove_state(tmp_path)
        return {"official_wechat_verified": True, "official_wechat_restored": True}

    monkeypatch.setattr(workflow, "capture_salt_matched_passphrase", capture)
    monkeypatch.setattr(validation, "validate_account_candidate", validate)
    monkeypatch.setattr(workflow, "_restore_after_terminal_path", restore)
    if capture_fails:
        with pytest.raises(MacOSDBKeyCaptureFailure, match="fixture failure"):
            workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path, save_result=False)
        assert events == ["restore"]
    else:
        result = workflow.capture_prepared_in_place(app, backup_root=tmp_path, probe_db_path=probe, debug_root=tmp_path, save_result=False)
        assert result["validated"] is True
        assert events == ["validate", "restore"]
    assert not workflow.has_pending_in_place_capture(debug_root=tmp_path)
