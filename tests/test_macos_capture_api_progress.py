"""Public HTTP regressions: synthetic state, no WeChat process or real keys."""
import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wechat_decrypt_tool import macos_inplace_capture, wechat_decrypt
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure
from wechat_decrypt_tool.routers import keys


def local_request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


@pytest.fixture(autouse=True)
def isolated_routes(monkeypatch):
    monkeypatch.setattr(keys, "is_macos", lambda: True)
    monkeypatch.setattr(keys, "_macos_capture_active_operation", "")


def test_status_remains_readable_while_capture_waits(monkeypatch):
    release, entered = threading.Event(), threading.Event()
    event_loop_thread = threading.get_ident()

    def capture(*args, **kwargs):
        assert threading.get_ident() != event_loop_thread
        assert kwargs["save_result"] is False
        entered.set()
        assert release.wait(3), "test never released simulated capture"
        return {"db_key": "ab" * 32, "official_wechat_verified": True}

    def status():
        assert threading.get_ident() != event_loop_thread
        return {"transaction_id": "current-test", "monitor_ready": True}

    monkeypatch.setattr(keys, "capture_prepared_macos_passphrase", capture)
    monkeypatch.setattr(keys, "_resolve_v4_probe_db_file", lambda path: Path("/tmp/fixture/message_0.db"))
    monkeypatch.setattr(keys, "get_in_place_capture_status", status)
    monkeypatch.setattr(keys, "save_passphrase", Mock())
    monkeypatch.setattr(wechat_decrypt, "validate_realtime_database_key", lambda *args: {"valid": True})

    async def exercise():
        task = asyncio.create_task(keys.capture_macos_key(local_request(), keys.MacosKeyCaptureRequest()))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.005)
            assert entered.is_set()
            result = await asyncio.wait_for(keys.get_macos_key_capture_status(local_request()), 0.2)
            assert result["data"]["transaction_id"] == "current-test"
            assert result["data"]["active_operation"] == "capture"
            assert not task.done()
        finally:
            release.set()
            result = await asyncio.wait_for(task, 3)
        assert result["status"] == 0

    asyncio.run(exercise())


def test_status_never_returns_key_or_local_paths(monkeypatch):
    state = {
        "stage": "capturing", "transaction_id": "test-tx", "capture_backend": "lldb",
        "db_key": "ab" * 32, "probe_db_path": "/private/account/message.db",
        "backup_path": "/private/backup", "debug_pid": 4321,
        "recovery_error_code": "ab" * 32,
    }
    monkeypatch.setattr(macos_inplace_capture, "has_pending_in_place_capture", lambda **kw: True)
    monkeypatch.setattr(macos_inplace_capture, "_read_state", lambda root: state)
    monkeypatch.setattr(macos_inplace_capture, "native_capture_monitor_ready", lambda **kw: True)
    result = asyncio.run(keys.get_macos_key_capture_status(local_request()))["data"]
    assert set(result) == {
        "pending", "stage", "needs_cleanup", "monitor_ready", "capture_backend",
        "capture_phase", "prepared_process_exited", "transaction_id", "recovery_error_code",
        "method", "active_operation",
    }
    assert result["prepared_process_exited"] is None
    assert result["transaction_id"] == "test-tx"
    assert result["recovery_error_code"] is None
    assert "ab" * 32 not in str(result)
    assert "/private" not in str(result)


@pytest.mark.parametrize("valid", [True, False])
def test_capture_returns_only_fresh_account_validated_key(monkeypatch, valid):
    fresh = "ab" * 32
    monkeypatch.setattr(keys, "_resolve_v4_probe_db_file", lambda path: Path("/tmp/fixture/message_0.db"))
    capture = Mock(return_value={"db_key": fresh, "official_wechat_verified": True})
    monkeypatch.setattr(keys, "capture_prepared_macos_passphrase", capture)
    validate = Mock(return_value={"valid": valid})
    monkeypatch.setattr(wechat_decrypt, "validate_realtime_database_key", validate)
    save = Mock()
    monkeypatch.setattr(keys, "save_passphrase", save)
    from wechat_decrypt_tool import macos_db_key_discovery
    discover = Mock(side_effect=AssertionError("must not substitute cached key"))
    monkeypatch.setattr(macos_db_key_discovery, "discover_macos_db_key", discover)
    result = asyncio.run(keys.capture_macos_key(
        local_request(), keys.MacosKeyCaptureRequest(db_storage_path="/tmp/fixture/db_storage"),
    ))
    assert capture.call_args.kwargs["save_result"] is False
    validate.assert_called_once_with("/tmp/fixture/db_storage", fresh)
    discover.assert_not_called()
    if valid:
        assert result["status"] == 0
        assert result["data"]["db_key"] == fresh
        save.assert_called_once_with(fresh)
    else:
        assert result["status"] == -1
        assert fresh not in str(result)
        save.assert_not_called()


def test_preflight_returns_transaction_and_whitelisted_backend(monkeypatch):
    monkeypatch.setattr(keys, "preflight_prepared_macos_passphrase", lambda *a, **kw: {
        "transaction_id": "test-tx", "capture_backend": "lldb", "backup_path": "/private/backup",
    })
    result = asyncio.run(keys.preflight_macos_key_capture(local_request(), keys.MacosKeyCaptureRequest()))
    assert result["data"]["transaction_id"] == "test-tx"
    assert result["data"]["capture_backend"] == "lldb"
    assert "/private" not in str(result)


def test_concurrent_cancel_cannot_restore_under_active_capture(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    app = tmp_path / "WeChat.app"
    app.mkdir()
    monkeypatch.setattr(macos_inplace_capture, "normalize_wechat_app_path", lambda value: app)
    monkeypatch.setattr(macos_inplace_capture, "has_pending_in_place_capture", lambda **kw: False)
    restore = Mock(side_effect=AssertionError("a concurrent request must not restore the app"))
    monkeypatch.setattr(macos_inplace_capture, "_restore_after_terminal_path", restore)

    def pause(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        raise MacOSDBKeyCaptureFailure("test_finished", "synthetic capture finished")

    monkeypatch.setattr(macos_inplace_capture, "_require_prepared_process", pause)
    failures = []

    def worker():
        try:
            macos_inplace_capture.capture_prepared_in_place(
                app, backup_root=tmp_path, probe_db_path=None, debug_root=tmp_path,
            )
        except MacOSDBKeyCaptureFailure as exc:
            failures.append(exc.code)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(1)
        with pytest.raises(MacOSDBKeyCaptureFailure) as error:
            macos_inplace_capture.cleanup_in_place_capture(app, backup_root=tmp_path, debug_root=tmp_path)
        assert error.value.code == "in_place_capture_busy"
        restore.assert_not_called()
    finally:
        release.set()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert failures == ["test_finished"]
