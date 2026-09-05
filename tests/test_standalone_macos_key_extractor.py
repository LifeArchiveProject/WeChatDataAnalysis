from __future__ import annotations

import sys
import plistlib
import pytest
from pathlib import Path
from unittest.mock import Mock, patch


TOOL_ROOT = Path(__file__).resolve().parents[1] / "macos-key-extractor"
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from key_extractor.core import (  # noqa: E402
    default_work_root,
    default_backup_root,
    capture_status,
    discover_default_probe_databases,
    mask_database_key,
    merge_fresh_capture_result,
    prefer_active_probe_database,
    resolve_probe_database,
)
from key_extractor.app import KeyExtractorApp  # noqa: E402
from release_audit import audit_directory, audit_zip  # noqa: E402


def test_login_instructions_require_actual_readiness_not_a_fixed_delay() -> None:
    source = (TOOL_ROOT / "key_extractor/app.py").read_text(encoding="utf-8")
    capture_dialog = source[source.index("    def _run_capture("):source.index("    def _wait_for_monitor_ready(")]
    assert "等待约 5 秒" not in capture_dialog
    assert "监测已就绪，可以重新登录" in capture_dialog


def test_build_includes_native_capture_source_and_uses_separate_test_output() -> None:
    script = (TOOL_ROOT / "build-macos.sh").read_text(encoding="utf-8")
    assert 'wcdb_native_capture.c:wechat_decrypt_tool/native/macos/source' in script
    assert 'WEDATA_KEY_EXTRACTOR_DIST_DIR' in script


def test_resolve_probe_database_prefers_message_database(tmp_path: Path) -> None:
    storage = tmp_path / "wxid_demo" / "db_storage"
    storage.mkdir(parents=True)
    (storage / "session.db").write_bytes(b"s" * 4096)
    (storage / "message_0.db").write_bytes(b"m" * 4096)
    (storage / "msg0.db").write_bytes(b"p" * 4096)

    assert resolve_probe_database(storage) == storage / "msg0.db"


def test_resolve_probe_database_accepts_a_database_file(tmp_path: Path) -> None:
    database = tmp_path / "contact.db"
    database.write_bytes(b"x" * 4096)

    assert resolve_probe_database(database) == database


def test_discover_default_probe_databases_finds_each_account(tmp_path: Path) -> None:
    base = (
        tmp_path
        / "Library"
        / "Containers"
        / "com.tencent.xinWeChat"
        / "Data"
        / "Documents"
        / "app_data"
        / "xwechat_files"
    )
    first = base / "wxid_first_ab12" / "db_storage"
    second = base / "wxid_second_cd34" / "db_storage"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / "message_0.db").write_bytes(b"a" * 4096)
    (second / "session.db").write_bytes(b"b" * 4096)

    discovered = discover_default_probe_databases(home=tmp_path)

    assert discovered == [first / "message_0.db", second / "session.db"]


def test_discover_default_probe_databases_supports_legacy_documents_layout(tmp_path: Path) -> None:
    storage = tmp_path / "Documents" / "xwechat_files" / "wxid_legacy" / "db_storage"
    storage.mkdir(parents=True)
    database = storage / "message_0.db"
    database.write_bytes(b"d" * 4096)

    assert discover_default_probe_databases(home=tmp_path) == [database]


def test_active_app_data_database_wins_over_legacy_duplicate(tmp_path: Path) -> None:
    documents = tmp_path / "Library/Containers/com.tencent.xinWeChat/Data/Documents"
    active = documents / "app_data/xwechat_files/wxid_same/db_storage/message/message_0.db"
    legacy = documents / "xwechat_files/wxid_same/db_storage/message/message_0.db"
    active.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    active.write_bytes(b"a" * 4096)
    legacy.write_bytes(b"b" * 4096)

    assert discover_default_probe_databases(home=tmp_path) == [active]
    assert prefer_active_probe_database(legacy, home=tmp_path) == active


def test_wechat_v4_never_falls_back_to_visible_legacy_database(tmp_path: Path) -> None:
    wechat = tmp_path / "WeChat.app"
    info_plist = wechat / "Contents/Info.plist"
    info_plist.parent.mkdir(parents=True)
    with info_plist.open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": "4.1.12"}, handle)
    documents = tmp_path / "Library/Containers/com.tencent.xinWeChat/Data/Documents"
    legacy = documents / "xwechat_files/wxid_same/db_storage/message/message_0.db"
    active = documents / "app_data/xwechat_files/wxid_same/db_storage/message/message_0.db"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"b" * 4096)

    assert prefer_active_probe_database(legacy, home=tmp_path, wechat_app=wechat) == active


def test_active_selected_database_does_not_rescan_all_accounts(tmp_path: Path) -> None:
    active = (
        tmp_path
        / "Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/xwechat_files"
        / "wxid_same/db_storage/message/message_0.db"
    )
    active.parent.mkdir(parents=True)
    active.write_bytes(b"a" * 4096)

    with patch(
        "key_extractor.core.discover_default_probe_databases",
        side_effect=AssertionError("active database must not trigger a recursive account rescan"),
    ):
        assert prefer_active_probe_database(active, home=tmp_path) == active


def test_database_key_is_masked_until_user_copies_it() -> None:
    key = "ab" * 32

    assert mask_database_key(key) == "abababab……abababab"
    assert mask_database_key("") == "尚未提取"


def test_default_backup_root_is_inside_selected_work_root(tmp_path: Path) -> None:
    assert default_backup_root(tmp_path) == tmp_path / "wechat-app-backups"


def test_default_work_root_does_not_read_another_apps_machine_settings(tmp_path: Path) -> None:
    configured_output = tmp_path / "someone-elses-output"
    configured_output.mkdir()
    settings = (
        tmp_path
        / "Library"
        / "Application Support"
        / "wechat-data-analysis-desktop"
        / "desktop-settings.json"
    )
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{"outputDir":' + repr(str(configured_output)).replace("'", '"') + "}",
        encoding="utf-8",
    )

    assert default_work_root(tmp_path) == (
        tmp_path / "Library" / "Application Support" / "WeDataKeyExtractor" / "work"
    )


def test_fresh_capture_result_cannot_be_mistaken_for_old_cache() -> None:
    key = "cd" * 32

    result = merge_fresh_capture_result(
        {"method": "macos_inplace_lldb_passphrase", "process_attached": True},
        {"method": "safe_local_cache", "db_key": key, "validated": True},
    )

    assert result["db_key"] == key
    assert result["method"] == "macos_inplace_lldb_passphrase"
    assert result["fresh_capture"] is True


def test_standalone_ui_does_not_short_circuit_through_existing_cache() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            TOOL_ROOT / "key_extractor" / "app.py",
            TOOL_ROOT / "key_extractor" / "core.py",
        )
    )

    assert "正在校验已有密钥缓存" not in source
    assert "_cached_key_found" not in source
    assert "本次不会读取旧密钥缓存" in source
    assert "discovered = discover_cached_key(database)" not in source
    assert "显示微信窗口" in source
    assert "self._wait_for_monitor_ready" in source
    assert "监测已就绪，可以重新登录" in source


class _FakeValue:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _FakeButton:
    def __init__(self) -> None:
        self.options: dict[str, str] = {}

    def configure(self, **options: str) -> None:
        self.options.update(options)


class _FakeCaptureRoot:
    def __init__(self) -> None:
        self.callbacks = {}
        self.next_id = 0
        self.destroy = Mock()

    def after(self, _delay, callback):
        self.next_id += 1
        self.callbacks[self.next_id] = callback
        return self.next_id

    def after_cancel(self, callback_id):
        self.callbacks.pop(callback_id, None)

    def run_next(self):
        callback_id = next(iter(self.callbacks))
        self.callbacks.pop(callback_id)()


def _capture_progress_ui(monkeypatch):
    app = object.__new__(KeyExtractorApp)
    app.root = _FakeCaptureRoot()
    app.wechat_var = _FakeValue("/synthetic/WeChat.app")
    app.database_var, app.work_root_var = _FakeValue(), _FakeValue()
    app.status_var, app.detail_var = _FakeValue(), _FakeValue()
    app.key_var = _FakeValue("尚未提取")
    app.current_key = ""
    app.primary_button, app.cancel_button, app.copy_button = _FakeButton(), _FakeButton(), _FakeButton()
    app._busy = False
    app._closing_after_cleanup = False
    app.stage = "preflight"
    app._capture_transaction_id = "transaction-current"
    app._hide_wechat = Mock(return_value=True)
    app._show_wechat = Mock()
    app._show_success = Mock()
    app._run_task = Mock(side_effect=lambda *_args, **_kwargs: setattr(app, "_busy", True))
    threads = []
    monkeypatch.setattr("key_extractor.app.threading.Thread", lambda *, target, daemon: Mock(start=lambda: threads.append(target)))
    monkeypatch.setattr("key_extractor.app.messagebox.askokcancel", lambda *_args: True)
    monkeypatch.setattr("key_extractor.app.messagebox.showerror", lambda *_args: None)
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: {"pending": False})
    app._run_capture()
    return app, threads


def _deliver_capture_status(monkeypatch, app, threads, phase, *, ready=False, transaction="transaction-current", pending=True):
    status = {
        "pending": pending,
        "capture_phase": phase,
        "monitor_ready": ready,
        "transaction_id": transaction,
    }
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: status)
    if not threads:
        app.root.run_next()
    assert len(threads) == 1, "status reads must be asynchronous and single-flight"
    threads.pop(0)()
    app.root.run_next()


def test_capture_progress_continues_after_ready_and_explains_expected_wechat_close(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    assert "自动关闭" in app.detail_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "waiting_authorization")
    assert "授权" in app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True)
    app._show_wechat.assert_called_once()
    assert "可以重新登录" in app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "captured", ready=True)
    assert "捕获" in app.status_var.get() and "校验" in app.status_var.get()
    assert "自动关闭" in app.detail_var.get() and "无需重新登录" in app.detail_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "validating")
    assert "复验" in app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "restoring")
    assert "正在恢复" in app.status_var.get()
    assert "已恢复" not in app.detail_var.get()
    app._show_wechat.assert_called_once()
    app._show_success.assert_not_called()
    assert app.current_key == ""


def test_capture_ready_requires_current_transaction_and_cannot_regress_a_later_phase(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True, transaction="transaction-old")
    app._show_wechat.assert_not_called()
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=False)
    assert "可以重新登录" not in app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True)
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True)
    app._show_wechat.assert_called_once()
    _deliver_capture_status(monkeypatch, app, threads, "restoring")
    restoring_text = app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True)
    assert app.status_var.get() == restoring_text
    app._show_wechat.assert_called_once()


@pytest.mark.parametrize("phase", ["captured", "validating", "restoring"])
def test_capture_can_skip_ready_without_reopening_wechat(monkeypatch, phase) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    _deliver_capture_status(monkeypatch, app, threads, phase, ready=True)
    app._show_wechat.assert_not_called()
    assert "重新登录" not in app.status_var.get()
    app._show_success.assert_not_called()


def test_cleared_capture_state_does_not_report_success_before_finish_result(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    _deliver_capture_status(monkeypatch, app, threads, "restoring")
    _deliver_capture_status(monkeypatch, app, threads, None, transaction=None, pending=False)
    app._show_success.assert_not_called()
    assert "正在恢复" in app.status_var.get()
    app._capture_finished({"fresh_capture": True, "process_attached": True, "official_wechat_verified": True, "db_key": "ab" * 32})
    app._show_success.assert_called_once_with("ab" * 32)
    assert not app.root.callbacks


@pytest.mark.parametrize("terminal", ["finish", "failure", "close"])
def test_capture_terminal_state_ignores_late_status_threads_and_callbacks(monkeypatch, terminal) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    app.root.run_next()
    late_thread = threads.pop(0)
    late_callback = next(iter(app.root.callbacks.values()))
    if terminal == "finish":
        app._capture_finished({"fresh_capture": True, "process_attached": True, "official_wechat_verified": True, "db_key": "ab" * 32})
    elif terminal == "failure":
        app._handle_error(RuntimeError("synthetic failure"))
    else:
        app._busy = False
        app._on_close()
        app.root.destroy.assert_called_once()
    terminal_text = (app.status_var.get(), app.detail_var.get())
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: {
        "pending": True, "capture_phase": "monitoring", "monitor_ready": True,
        "transaction_id": "transaction-current",
    })
    late_thread()
    late_callback()
    assert not app.root.callbacks
    assert (app.status_var.get(), app.detail_var.get()) == terminal_text
    app._show_wechat.assert_not_called()


def test_capture_confirmations_explain_successful_automatic_close(monkeypatch) -> None:
    app, _threads = _capture_progress_ui(monkeypatch)
    prompts = []
    monkeypatch.setattr("key_extractor.app.messagebox.askokcancel", lambda title, text: prompts.append(text) or False)
    app._busy = False
    app._confirm_fresh_capture()
    app._run_capture()
    assert len(prompts) == 2
    for prompt in prompts:
        assert "自动关闭" in prompt and "恢复" in prompt and "无需重新登录" in prompt


def test_slow_capture_status_does_not_block_tk_or_start_parallel_reads(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    status_reader = Mock(return_value={"pending": False})
    monkeypatch.setattr("key_extractor.app.capture_status", status_reader)
    for _ in range(5):
        app.root.run_next()
    status_reader.assert_not_called()
    assert len(threads) == 1
    threads.pop(0)()
    status_reader.assert_called_once()
    app.root.run_next()
    assert len(threads) == 1


def test_capture_polling_recovers_from_status_read_error(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    app.root.run_next()
    monkeypatch.setattr("key_extractor.app.capture_status", Mock(side_effect=OSError("synthetic unavailable")))
    threads.pop(0)()
    app.root.run_next()
    assert "synthetic unavailable" not in app.detail_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True)
    app._show_wechat.assert_called_once()


def test_stale_capture_run_cannot_update_or_complete_a_new_run(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    app.root.run_next()
    old_reader = threads.pop(0)
    old_poll_callback = next(iter(app.root.callbacks.values()))
    old_finish_callback = app._run_task.call_args.args[1]
    app._stop_capture_polling()
    app._busy = False
    app._run_capture()
    new_callbacks = dict(app.root.callbacks)
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: {
        "pending": True, "capture_phase": "monitoring", "monitor_ready": True,
        "transaction_id": "transaction-current",
    })
    old_reader()
    old_poll_callback()
    old_finish_callback({"fresh_capture": True, "process_attached": True, "official_wechat_verified": True, "db_key": "ab" * 32})
    assert app.root.callbacks == new_callbacks
    app._show_wechat.assert_not_called()
    app._show_success.assert_not_called()
    _deliver_capture_status(monkeypatch, app, threads, "restoring")
    assert "正在恢复" in app.status_var.get()
    app._show_wechat.assert_not_called()


def test_readiness_is_not_trusted_without_preflight_transaction(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    app._capture_transaction_id = ""
    _deliver_capture_status(monkeypatch, app, threads, "monitoring", ready=True)
    app._show_wechat.assert_not_called()
    app._preflight_ready({"transaction_id": "transaction-current", "method": "native"})
    assert app._capture_transaction_id == "transaction-current"


def test_busy_close_keeps_live_capture_polling_until_operation_finishes(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    callbacks = dict(app.root.callbacks)
    monkeypatch.setattr("key_extractor.app.messagebox.showinfo", Mock())
    app._on_close()
    assert app._capture_poll_active
    assert app.root.callbacks == callbacks
    app.root.destroy.assert_not_called()
    _deliver_capture_status(monkeypatch, app, threads, "restoring")
    assert "正在恢复" in app.status_var.get()


def test_native_capture_can_validate_before_reporting_a_validated_capture(monkeypatch) -> None:
    app, threads = _capture_progress_ui(monkeypatch)
    _deliver_capture_status(monkeypatch, app, threads, "validating")
    assert "复验" in app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "captured")
    assert "捕获" in app.status_var.get() and "校验" in app.status_var.get()
    _deliver_capture_status(monkeypatch, app, threads, "restoring")
    _deliver_capture_status(monkeypatch, app, threads, "validating")
    assert "正在恢复" in app.status_var.get()
    app._show_wechat.assert_not_called()


@pytest.mark.parametrize("verified", [None, False])
def test_capture_finish_requires_official_wechat_verification(monkeypatch, verified) -> None:
    app, _threads = _capture_progress_ui(monkeypatch)
    app._handle_error = Mock()
    result = {"fresh_capture": True, "process_attached": True, "db_key": "ab" * 32}
    if verified is not None:
        result["official_wechat_verified"] = verified
    app._capture_finished(result)
    app._show_success.assert_not_called()
    app._handle_error.assert_called_once()
    assert "腾讯官方微信" in str(app._handle_error.call_args.args[0])
    assert not app.root.callbacks


def test_failed_capture_without_pending_state_resets_retry_button(monkeypatch) -> None:
    app = object.__new__(KeyExtractorApp)
    app.wechat_var = _FakeValue("/synthetic/WeChat.app")
    app.stage = "preflight"
    app.status_var = _FakeValue()
    app.detail_var = _FakeValue()
    app.primary_button = _FakeButton()
    app.cancel_button = _FakeButton()
    app._closing_after_cleanup = False
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: {"pending": False, "stage": "idle"})
    monkeypatch.setattr("key_extractor.app.messagebox.showerror", lambda *_args: None)

    app._handle_error(RuntimeError("capture failed"))

    assert app.stage == "idle"
    assert app.primary_button.options == {"state": "normal", "text": "重新开始"}
    assert app.cancel_button.options == {"state": "disabled"}


def test_failed_capture_with_pending_state_requires_restore(monkeypatch) -> None:
    app = object.__new__(KeyExtractorApp)
    app.wechat_var = _FakeValue("/synthetic/WeChat.app")
    app.stage = "preflight"
    app.status_var = _FakeValue()
    app.detail_var = _FakeValue()
    app.primary_button = _FakeButton()
    app.cancel_button = _FakeButton()
    app._closing_after_cleanup = False
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: {"pending": True, "stage": "launched"})
    monkeypatch.setattr("key_extractor.app.messagebox.showerror", lambda *_args: None)

    app._handle_error(RuntimeError("capture failed"))

    assert app.stage == "prepared"
    assert app.primary_button.options == {"state": "disabled", "text": "等待恢复"}
    assert app.cancel_button.options == {"state": "normal"}


def _pending_ui(monkeypatch, stage: str) -> KeyExtractorApp:
    app = object.__new__(KeyExtractorApp)
    app.wechat_var = _FakeValue("/synthetic/WeChat.app")
    app.stage = "idle"
    app.status_var, app.detail_var = _FakeValue(), _FakeValue()
    app.primary_button, app.cancel_button = _FakeButton(), _FakeButton()
    app._busy = False
    app._closing_after_cleanup = False
    app.last_error = ""
    app.root = Mock()
    app._run_task = Mock()
    monkeypatch.setattr("key_extractor.app.capture_status", lambda _path: {"pending": True, "stage": stage})
    monkeypatch.setattr("key_extractor.app.messagebox.showerror", lambda *_args: None)
    return app


def test_startup_official_conflict_allows_explicit_new_baseline(monkeypatch) -> None:
    app = _pending_ui(monkeypatch, "external_install_conflict")
    app._check_pending_capture()
    assert app.stage == "external_install_conflict"
    assert app.primary_button.options == {"state": "normal", "text": "以当前版本重新开始"}
    assert app.cancel_button.options == {"state": "disabled"}
    assert "保留" in app.detail_var.get()
    assert "已恢复" not in app.status_var.get()
    app._run_task.assert_not_called()


def test_conflict_error_does_not_strand_retry_or_claim_restore(monkeypatch) -> None:
    app = _pending_ui(monkeypatch, "external_install_conflict")
    app._handle_error(RuntimeError("official build changed"))
    assert app.primary_button.options["state"] == "normal"
    assert app.primary_button.options["text"] == "以当前版本重新开始"
    assert "已恢复" not in app.status_var.get()
    assert app.cancel_button.options["state"] == "disabled"


def test_unknown_debug_identity_blocks_automatic_actions(monkeypatch) -> None:
    app = _pending_ui(monkeypatch, "recovery_blocked")
    app._check_pending_capture()
    assert app.stage == "recovery_blocked"
    assert app.primary_button.options == {"state": "disabled", "text": "需要手动处理"}
    assert app.cancel_button.options == {"state": "disabled"}
    assert "未覆盖" in app.detail_var.get()


def test_close_conflict_preserves_install_without_requesting_restore(monkeypatch) -> None:
    app = _pending_ui(monkeypatch, "external_install_conflict")
    prompts = []
    monkeypatch.setattr("key_extractor.app.messagebox.askokcancel", lambda title, text: prompts.append(text) or True)
    app._on_close()
    assert "保留" in prompts[0]
    app._run_task.assert_not_called()
    app.root.destroy.assert_called_once()
    assert not app._closing_after_cleanup


def test_conflict_restart_confirmation_explains_preserved_backup(monkeypatch) -> None:
    app = _pending_ui(monkeypatch, "external_install_conflict")
    app.stage = "external_install_conflict"
    prompts = []
    monkeypatch.setattr("key_extractor.app.messagebox.askokcancel", lambda title, text: prompts.append((title, text)) or True)
    app._confirm_fresh_capture()
    assert prompts[0][0] == "以当前版本重新开始"
    assert "旧备份" in prompts[0][1]
    assert "保留" in prompts[0][1]
    app._run_task.assert_called_once()


def test_cancel_without_replacement_reports_verification_not_restore(monkeypatch) -> None:
    app = _pending_ui(monkeypatch, "idle")
    app._cancelled({"official_wechat_verified": True, "official_wechat_restored": False})
    assert "已恢复" not in app.status_var.get()
    assert "未替换" in app.detail_var.get()


def test_safe_status_unlocks_manual_official_reinstall_without_restoring(monkeypatch) -> None:
    monkeypatch.setattr("wechat_decrypt_tool.macos_inplace_capture.get_in_place_capture_status", lambda: {"pending": True, "stage": "recovery_blocked"})
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.normalize_wechat_app_path", lambda _path: Path("/synthetic/WeChat.app"))
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", lambda _path: {
        "valid": True, "ad_hoc": False, "team_identifier": "5A4RE8SF68", "identifier": "com.tencent.xinWeChat",
    })
    restore = Mock(side_effect=AssertionError("status must not mutate the application"))
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.restore_official_wechat_if_needed", restore)
    status = capture_status()
    assert status["stage"] == "external_install_conflict"
    assert status["restart_allowed"] is True
    restore.assert_not_called()


def test_safe_status_does_not_trust_a_stale_official_conflict(monkeypatch) -> None:
    monkeypatch.setattr("wechat_decrypt_tool.macos_inplace_capture.get_in_place_capture_status", lambda: {"pending": True, "stage": "external_install_conflict"})
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.normalize_wechat_app_path", lambda _path: Path("/synthetic/WeChat.app"))
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", lambda _path: {"valid": True, "ad_hoc": True})
    status = capture_status()
    assert status["stage"] == "recovery_blocked"
    assert status["restart_allowed"] is False


def test_safe_status_verifies_selected_app_not_default_installation(monkeypatch) -> None:
    monkeypatch.setattr("wechat_decrypt_tool.macos_inplace_capture.get_in_place_capture_status", lambda: {"pending": True, "stage": "external_install_conflict"})
    selected = Path("/synthetic/selected/WeChat.app")
    normalize = Mock(return_value=selected)
    inspect = Mock(return_value={"valid": True, "ad_hoc": True})
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.normalize_wechat_app_path", normalize)
    monkeypatch.setattr("wechat_decrypt_tool.macos_db_key_capture.inspect_wechat_signature", inspect)
    status = capture_status(selected)
    normalize.assert_called_once_with(selected)
    inspect.assert_called_once_with(selected)
    assert status["restart_allowed"] is False


def test_account_discovery_preserves_saved_active_path_when_access_is_temporarily_missing(monkeypatch) -> None:
    active = "/private/current/app_data/xwechat_files/wxid_same/db_storage/message/message_0.db"
    legacy = Path("/private/legacy/xwechat_files/wxid_same/db_storage/message/message_0.db")
    app = object.__new__(KeyExtractorApp)
    app.wechat_var = _FakeValue("/Applications/WeChat.app")
    app.database_var = _FakeValue(active)
    app.database_choice_var = _FakeValue()
    app.account_combo = {}
    app.db_choices = {}
    monkeypatch.setattr("key_extractor.app.discover_default_probe_databases", lambda: [legacy])
    monkeypatch.setattr(
        "key_extractor.app.prefer_active_probe_database",
        lambda path, **_kwargs: path,
    )

    app._discover_accounts()

    assert app.database_var.get() == active
    assert active in app.db_choices.values()
    assert "已保存路径" in app.database_choice_var.get()


def test_distribution_sources_do_not_contain_machine_specific_assumptions() -> None:
    source_files = [
        TOOL_ROOT / "README.md",
        TOOL_ROOT / "key_extractor" / "app.py",
        TOOL_ROOT / "key_extractor" / "core.py",
        TOOL_ROOT.parent / "src" / "wechat_decrypt_tool" / "macos_db_key_capture.py",
        TOOL_ROOT.parent / "src" / "wechat_decrypt_tool" / "macos_db_key_discovery.py",
        TOOL_ROOT.parent / "src" / "wechat_decrypt_tool" / "macos_inplace_capture.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    for forbidden in (
        "/Users/",
        "/Volumes/",
        str(Path.home()),
        "绿联",
        "NAS",
        "wechat-data-analysis-desktop",
        "主程序",
    ):
        assert forbidden not in combined


def test_release_audit_rejects_personal_paths_and_runtime_secrets(tmp_path: Path) -> None:
    app = tmp_path / "Example.app"
    app.mkdir()
    (app / "binary").write_bytes(b"built from /Users/demo/private/source.py")
    (app / "wechat-passphrase.json").write_text("{}", encoding="utf-8")

    violations = audit_directory(app)

    assert any("用户主目录绝对路径" in item for item in violations)
    assert any("私密文件" in item for item in violations)


def test_release_audit_accepts_clean_app_and_rejects_database_in_zip(tmp_path: Path) -> None:
    import zipfile

    app = tmp_path / "Clean.app"
    app.mkdir()
    (app / "binary").write_bytes(b"portable executable content")
    assert audit_directory(app) == []

    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("Clean.app/Contents/MacOS/binary", b"clean")
        output.writestr("Clean.app/user/message_0.db", b"private")
    assert any("私密文件" in item for item in audit_zip(archive))
