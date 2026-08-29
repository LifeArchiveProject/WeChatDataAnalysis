from __future__ import annotations

import ctypes
import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock

from wechat_decrypt_tool import native_core_client, sns_realtime_autosync


def test_startup_refresh_is_async_once_and_uses_public_options(tmp_path) -> None:
    account = "wxid_refresh"
    account_dir = tmp_path.resolve()
    entered = threading.Event()
    release = threading.Event()
    calls: list[tuple[bytes, bytes, int, bytes | None]] = []

    def refresh(_handle, options_pointer) -> int:
        options = ctypes.cast(
            options_pointer,
            ctypes.POINTER(native_core_client._WceWechatMomentsRefreshOptions),
        ).contents
        calls.append(
            (
                bytes(options.account_utf8),
                bytes(options.account_directory_utf8),
                int(options.operation_nonce),
                options.target_username_utf8,
            )
        )
        entered.set()
        release.wait(timeout=2.0)
        return 0

    client = object.__new__(native_core_client.NativeCoreClient)
    client._supports_wechat_moments_refresh = True
    client._library = SimpleNamespace(wce_wechat_action_moments_refresh=refresh)
    client._lock = threading.RLock()
    client._closed = False
    client._handle = ctypes.c_void_p(1)

    service = sns_realtime_autosync.SnsRealtimeAutoSyncService()
    service._states[account] = sns_realtime_autosync._AccountState()
    context = SimpleNamespace(
        name=account,
        mode="direct",
        db_key_present=True,
        account_dir=account_dir,
    )
    safety_release = threading.Timer(2.0, release.set)
    safety_release.start()
    try:
        with (
            mock.patch.object(sns_realtime_autosync.sys, "platform", "win32"),
            mock.patch.object(
                sns_realtime_autosync,
                "resolve_chat_account_context",
                return_value=context,
            ),
            mock.patch(
                "wechat_decrypt_tool.native_core_broker.managed_native_core_operation",
                return_value=nullcontext(),
            ),
            mock.patch(
                "wechat_decrypt_tool.native_core_client.get_native_core_client",
                return_value=client,
            ),
            mock.patch.object(
                service,
                "_sync_with_bounded_retries",
                return_value=({"status": "ok", "changed": 0}, False),
            ),
            mock.patch.object(service, "_publish_sync_result"),
        ):
            service._schedule_sync(account, reason="startup")
            assert entered.wait(timeout=1.0)
            service._schedule_sync(account, reason="startup")
            assert service._states[account].worker is not None
            assert service._states[account].worker.is_alive()
            release.set()
            service._states[account].worker.join(timeout=2.0)
    finally:
        release.set()
        safety_release.cancel()

    assert ctypes.sizeof(native_core_client._WceWechatMomentsRefreshOptions) == 40
    assert native_core_client.NativeCoreFeature.WECHAT_MOMENTS_REFRESH == 1 << 6
    assert len(calls) == 1
    assert calls[0][:2] == (account.encode(), str(account_dir).encode())
    assert calls[0][2] != 0
    assert calls[0][3] is None


def test_refresh_accepts_target_username(tmp_path) -> None:
    captured: list[bytes | None] = []

    def refresh(_handle, options_pointer) -> int:
        options = ctypes.cast(
            options_pointer,
            ctypes.POINTER(native_core_client._WceWechatMomentsRefreshOptions),
        ).contents
        captured.append(options.target_username_utf8)
        return 0

    client = object.__new__(native_core_client.NativeCoreClient)
    client._supports_wechat_moments_refresh = True
    client._library = SimpleNamespace(wce_wechat_action_moments_refresh=refresh)
    client._lock = threading.RLock()
    client._closed = False
    client._handle = ctypes.c_void_p(1)

    client.refresh_wechat_moments(
        "wxid_refresh",
        tmp_path.resolve(),
        "wxid_puuxvtit46vm22",
    )

    assert captured == [b"wxid_puuxvtit46vm22"]


def test_publish_moments_accepts_text_without_images(tmp_path) -> None:
    client = object.__new__(native_core_client.NativeCoreClient)
    client.execute_wechat_action = mock.Mock()

    client.publish_wechat_moments(
        "wxid_refresh",
        tmp_path.resolve(),
        tmp_path.resolve(),
        "纯文字",
    )

    client.execute_wechat_action.assert_called_once_with(
        native_core_client.NativeCoreWechatAction.MOMENTS_PUBLISH,
        "wxid_refresh",
        tmp_path.resolve(),
        str(tmp_path.resolve()),
        "2\x1f纯文字\x1f\x1f\x1f",
    )
