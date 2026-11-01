"""No real applications, signing, debugger, or databases are used here."""
import sys
import queue
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wechat_decrypt_tool import macos_db_key_capture as capture
from wechat_decrypt_tool import macos_inplace_capture as workflow
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "macos-key-extractor"))
from key_extractor.app import KeyExtractorApp


@pytest.mark.parametrize("second_pid", [None, 456])
def test_launch_does_not_accept_exit_or_replacement(monkeypatch, second_pid):
    monkeypatch.setattr(capture, "_run", Mock())
    monkeypatch.setattr(capture.time, "sleep", Mock())
    monkeypatch.setattr(capture, "_find_wechat_main_pid", Mock(side_effect=[123, second_pid]))
    with pytest.raises(capture.MacOSDBKeyCaptureFailure) as error:
        capture._launch_wechat(Path("/fixture/WeChat.app"))
    assert error.value.code == "wechat_launch_exited"


def test_launch_failure_enters_existing_transactional_recovery(tmp_path, monkeypatch):
    app = tmp_path / "WeChat.app"
    app.mkdir()
    debug = tmp_path / "debug"
    monkeypatch.setattr(workflow, "DEFAULT_WECHAT_APP", app)
    monkeypatch.setattr(workflow, "normalize_wechat_app_path", lambda path: app)
    monkeypatch.setattr(workflow, "_acquire_installation_lock", lambda *a: {"transaction_id": "fixture-tx"})
    monkeypatch.setattr(workflow, "_release_installation_lock", Mock())
    monkeypatch.setattr(workflow, "inspect_wechat_signature", Mock(return_value={}))
    monkeypatch.setattr(workflow, "_is_tencent_official_signature", lambda signature: True)

    def prepare(*args, before_resign):
        before_resign({"wechat_app_path": str(app), "debug_identity": {"fixture": True}})
        return {}

    monkeypatch.setattr(workflow, "ensure_wechat_in_place_debuggable", prepare)
    error = capture.MacOSDBKeyCaptureFailure("wechat_launch_exited", "synthetic exit")
    monkeypatch.setattr(workflow, "_launch_wechat", Mock(side_effect=error))
    recover = Mock()
    monkeypatch.setattr(workflow, "_restore_after_terminal_path", recover)
    with pytest.raises(capture.MacOSDBKeyCaptureFailure):
        workflow.prepare_in_place_capture(app, backup_root=tmp_path / "backups", debug_root=debug)
    recover.assert_called_once_with(app, backup_root=tmp_path / "backups", debug_root=debug, original_error=error)
    assert workflow._read_state(debug)["stage"] != "launched"


@pytest.mark.parametrize("stage", ["launched", "preflight_passed"])
@pytest.mark.parametrize("pid,exited", [(123, False), (None, True), (456, True)])
def test_prepared_status_reports_liveness_without_restoring(tmp_path, monkeypatch, stage, pid, exited):
    workflow._write_state(tmp_path, {
        "schema_version": 2, "stage": stage, "transaction_id": "fixture-tx",
        "wechat_app_path": "/Applications/WeChat.app", "debug_pid": 123,
    })
    monkeypatch.setattr(workflow, "_find_wechat_main_pid", Mock(return_value=pid))
    restore = Mock(side_effect=AssertionError("status must remain read-only"))
    monkeypatch.setattr(workflow, "restore_official_wechat_if_needed", restore)
    assert workflow.get_in_place_capture_status(debug_root=tmp_path)["prepared_process_exited"] is exited
    restore.assert_not_called()


def test_capture_or_unknown_probe_is_not_treated_as_idle_exit(tmp_path, monkeypatch):
    state = {"schema_version": 2, "stage": "capturing", "transaction_id": "fixture-tx",
             "wechat_app_path": "/Applications/WeChat.app", "debug_pid": 123}
    workflow._write_state(tmp_path, state)
    probe = Mock(side_effect=OSError("process list unavailable"))
    monkeypatch.setattr(workflow, "_find_wechat_main_pid", probe)
    assert workflow.get_in_place_capture_status(debug_root=tmp_path).get("prepared_process_exited") is None
    probe.assert_not_called()
    state["stage"] = "launched"
    workflow._write_state(tmp_path, state)
    assert workflow.get_in_place_capture_status(debug_root=tmp_path).get("prepared_process_exited") is None


def fake_ui():
    app = KeyExtractorApp.__new__(KeyExtractorApp)
    app._closed = app._busy = app._closing_after_cleanup = False
    app.stage = "prepared"
    app._capture_transaction_id = "fixture-tx"
    app._prepared_exit_attempted_transaction = ""
    app.detail_var = Mock()
    app.wechat_var = Mock(get=lambda: "/fixture/WeChat.app")
    app.work_root_var = Mock(get=lambda: "/fixture/work")
    app._run_task = Mock()
    return app


def test_idle_exit_requests_existing_recovery_once(monkeypatch):
    app = fake_ui()
    cancel = Mock(return_value={"official_wechat_verified": True})
    monkeypatch.setattr("key_extractor.app.cancel_capture", cancel)
    status = {"transaction_id": "fixture-tx", "stage": "launched", "prepared_process_exited": True}
    app._apply_prepared_health("fixture-tx", status)
    app._run_task.assert_called_once()
    cancel.assert_not_called()  # Must run on the existing background task queue.
    operation, callback = app._run_task.call_args.args
    operation()
    cancel.assert_called_once_with("/fixture/WeChat.app", "/fixture/work")
    assert callback == app._prepared_exit_recovered
    app._apply_prepared_health("fixture-tx", status)
    app._run_task.assert_called_once()  # No endless recovery/authorization loop.


@pytest.mark.parametrize("change", ["busy", "closed", "capturing", "stale", "unknown", "restoring"])
def test_idle_recovery_ignores_active_capture_and_stale_or_unknown_state(change):
    app = fake_ui()
    status = {"transaction_id": "fixture-tx", "stage": "launched", "prepared_process_exited": True}
    if change == "busy":
        app._busy = True
    elif change == "closed":
        app._closed = True
    elif change == "capturing":
        app.stage = "capturing"
    elif change == "stale":
        status["transaction_id"] = "old-tx"
    elif change == "unknown":
        status["prepared_process_exited"] = None
    else:
        status["stage"] = "capturing"
        status["capture_phase"] = "restoring"
    app._apply_prepared_health("fixture-tx", status)
    app._run_task.assert_not_called()


def test_idle_health_reader_is_async_single_flight_and_stops_when_closed(monkeypatch):
    app = fake_ui()
    app._prepared_health_results = queue.Queue()
    app._prepared_health_inflight = False
    app.root = Mock()
    workers = []
    monkeypatch.setattr("key_extractor.app.threading.Thread", lambda target, **kw: Mock(start=lambda: workers.append(target)))
    reader = Mock(return_value={"transaction_id": "fixture-tx", "stage": "launched", "prepared_process_exited": False})
    monkeypatch.setattr("key_extractor.app.capture_status", reader)
    app._poll_prepared_health()
    app._poll_prepared_health()
    reader.assert_not_called()
    assert len(workers) == 1
    workers.pop()()
    reader.assert_called_once()
    app._poll_prepared_health()
    assert len(workers) == 1
    app._closed = True
    app.root.reset_mock()
    app._poll_prepared_health()
    app.root.after.assert_not_called()
