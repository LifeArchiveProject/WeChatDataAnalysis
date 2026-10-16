"""Manual launch authorization uses fake bundles only; no OS policy changes."""
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wechat_decrypt_tool import macos_inplace_capture as workflow
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "macos-key-extractor"))
from key_extractor.app import KeyExtractorApp
from key_extractor.core import prepare_capture


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    app, debug, backup = tmp_path / "WeChat.app", tmp_path / "debug", tmp_path / "backups"
    app.mkdir()
    monkeypatch.setattr(workflow, "DEFAULT_WECHAT_APP", app)
    monkeypatch.setattr(workflow, "normalize_wechat_app_path", lambda _: app)
    monkeypatch.setattr(workflow, "_acquire_installation_lock", lambda *a: {"transaction_id": "fixture-tx"})
    monkeypatch.setattr(workflow, "_release_installation_lock", Mock())
    monkeypatch.setattr(workflow, "inspect_wechat_signature", Mock(return_value={}))
    monkeypatch.setattr(workflow, "_is_tencent_official_signature", lambda _: True)
    monkeypatch.setattr(workflow, "_transaction_is_active", lambda *a: True)
    monkeypatch.setattr(workflow, "_prepared_signature_is_valid", lambda *a: True)
    monkeypatch.setattr(workflow, "_debug_identity_matches", lambda *a: True)
    monkeypatch.setattr(workflow.time, "sleep", Mock())
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("No external processes allowed")))

    def prepare(*args, before_resign):
        before_resign({"wechat_app_path": str(app), "backup_path": str(backup / "WeChat-fixture.zip"),
                       "debug_identity": {"fixture": True}})
        return {}

    monkeypatch.setattr(workflow, "ensure_wechat_in_place_debuggable", prepare)
    launch = Mock(side_effect=AssertionError("manual mode must not launch"))
    monkeypatch.setattr(workflow, "_launch_wechat", launch)
    result = workflow.prepare_in_place_capture(app, backup_root=backup, debug_root=debug, defer_launch=True)
    return app, debug, backup, result


def test_manual_prepare_is_not_reported_as_running(prepared):
    app, debug, backup, result = prepared
    assert result["requires_manual_launch"] is True
    assert result["ready_for_preflight"] is False
    assert result["debug_pid"] is None
    assert workflow.get_in_place_capture_status(debug_root=debug)["stage"] == "awaiting_manual_launch"


@pytest.mark.parametrize("pids,ready", [([123, 123], True), ([None], False), ([123, None], False), ([123, 456], False)])
def test_only_stable_user_started_process_can_continue(prepared, monkeypatch, pids, ready):
    app, debug, backup, result = prepared
    monkeypatch.setattr(workflow, "_find_wechat_main_pid", Mock(side_effect=pids))
    resumed = workflow.confirm_manual_in_place_launch(app, backup_root=backup, debug_root=debug,
                                                     transaction_id=result["transaction_id"])
    assert resumed["ready_for_preflight"] is ready
    assert workflow._read_state(debug)["stage"] == ("launched" if ready else "awaiting_manual_launch")


@pytest.mark.parametrize("cause", ["transaction", "owner", "signature", "identity"])
def test_manual_confirmation_cannot_adopt_another_app_or_transaction(prepared, monkeypatch, cause):
    app, debug, backup, result = prepared
    transaction = result["transaction_id"]
    if cause == "transaction":
        transaction = "old-transaction"
    else:
        function = {"owner": "_transaction_is_active", "signature": "_prepared_signature_is_valid",
                    "identity": "_debug_identity_matches"}[cause]
        monkeypatch.setattr(workflow, function, lambda *a: False)
    probe = Mock(side_effect=AssertionError("must reject before checking processes"))
    monkeypatch.setattr(workflow, "_find_wechat_main_pid", probe)
    with pytest.raises(MacOSDBKeyCaptureFailure):
        workflow.confirm_manual_in_place_launch(app, backup_root=backup, debug_root=debug, transaction_id=transaction)
    probe.assert_not_called()


def ui():
    app = KeyExtractorApp.__new__(KeyExtractorApp)
    app.root = Mock()
    app.status_var, app.detail_var = Mock(), Mock()
    app.primary_button, app.cancel_button, app.progress = Mock(), Mock(), Mock()
    app._handle_error = Mock()
    return app


def test_standalone_opts_into_deferred_launch(monkeypatch):
    prepare = Mock(return_value={})
    monkeypatch.setattr(workflow, "prepare_in_place_capture", prepare)
    prepare_capture("/fixture/WeChat.app", "/fixture/work")
    assert prepare.call_args.kwargs["defer_launch"] is True


def test_waiting_ui_never_opens_app_or_enables_preflight_automatically():
    app = ui()
    app._prepared({"transaction_id": "fixture-tx", "requires_manual_launch": True})
    assert app.stage == "system_approval"
    app.root.after.assert_not_called()
    text = app.detail_var.set.call_args.args[0]
    assert "不是 Apple 公证" in text and "请取消并恢复" in text
    app._set_busy(False)
    app.cancel_button.configure.assert_called_with(state="normal")
    app._manual_launch_checked({"transaction_id": "fixture-tx", "ready_for_preflight": False})
    assert app.stage == "system_approval"
    app.root.after.assert_not_called()
    app._manual_launch_checked({"transaction_id": "fixture-tx", "ready_for_preflight": True})
    assert app.stage == "prepared"


def test_stale_confirmation_cannot_advance_ui():
    app = ui()
    app._prepared({"transaction_id": "fixture-tx", "requires_manual_launch": True})
    app._manual_launch_checked({"transaction_id": "old-tx", "ready_for_preflight": True})
    assert app.stage == "system_approval"
    app._handle_error.assert_called_once()


def test_settings_button_only_opens_settings_app(monkeypatch):
    popen = Mock()
    monkeypatch.setattr("key_extractor.app.subprocess.Popen", popen)
    KeyExtractorApp._open_security_settings()
    popen.assert_called_once_with(["/usr/bin/open", "-b", "com.apple.systempreferences"])
