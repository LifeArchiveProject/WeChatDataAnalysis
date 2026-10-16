from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from wechat_decrypt_tool import native_core_lease
from wechat_decrypt_tool import native_core_voice_asr as module
from wechat_decrypt_tool.native_core_client import (
    NativeCoreAsrPollResult,
    NativeCoreAsrReason,
    NativeCoreAsrRequestState,
    NativeCoreAsrStatus,
    NativeCoreError,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreStatus,
    NativeCoreUnavailableError,
)
from wechat_decrypt_tool.native_voice_transcription import (
    NativeVoiceTriggerCommand,
    NativeVoiceTriggerError,
)


class _Operation:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _ImmediateThread:
    def __init__(self, *, target, args, **_kwargs) -> None:
        self._target = target
        self._args = args

    def start(self) -> None:
        self._target(*self._args)


def _ready_status() -> NativeCoreAsrStatus:
    return NativeCoreAsrStatus(
        reason=NativeCoreAsrReason.READY,
        platform_supported=True,
        ready=True,
        wechat_process_id=1234,
        expected_wechat_version="4.1.12.26",
        actual_wechat_version="4.1.12.26",
        expected_weixin_sha256=b"a" * 32,
        actual_weixin_sha256=b"a" * 32,
    )


def test_status_maps_version_mismatch_to_product_reason(monkeypatch, tmp_path: Path):
    operation = _Operation()
    status = NativeCoreAsrStatus(
        reason=NativeCoreAsrReason.WECHAT_VERSION_MISMATCH,
        platform_supported=True,
        ready=False,
        wechat_process_id=4321,
        expected_wechat_version="4.1.12.26",
        actual_wechat_version="4.1.13.1",
        expected_weixin_sha256=b"a" * 32,
        actual_weixin_sha256=b"b" * 32,
    )
    client = SimpleNamespace(
        supports_native_asr=True,
        get_native_asr_status=lambda *_args: status,
    )
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: client)

    assert module.native_core_voice_asr_status(tmp_path / "wxid_test") == {
        "available": False,
        "reason": "weixin_version_unsupported",
        "version": "4.1.12.26",
        "pid": 4321,
    }
    assert operation.closed is True


def test_status_maps_policy_failure_to_protected_build_reason(monkeypatch, tmp_path: Path):
    operation = _Operation()

    def reject_policy(*_args):
        raise NativeCorePolicyError(
            "feature unavailable", status=NativeCoreStatus.FEATURE_DENIED
        )

    client = SimpleNamespace(
        supports_native_asr=True,
        get_native_asr_status=reject_policy,
    )
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: client)

    assert module.native_core_voice_asr_status(tmp_path / "wxid_test") == {
        "available": False,
        "reason": "protected_build_unavailable",
        "version": "4.1.12.26",
        "pid": None,
    }
    assert operation.closed is True


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (NativeCoreError("busy", status=NativeCoreStatus.BUSY), "native_transport_busy"),
        (
            NativeCoreError("timeout", status=NativeCoreStatus.TIMEOUT),
            "native_trigger_timeout",
        ),
        (
            NativeCorePolicyError(
                "build mismatch", status=NativeCoreStatus.BUILD_MISMATCH
            ),
            "native_transport_unavailable",
        ),
        (
            NativeCorePolicyError(
                "tamper", status=NativeCoreStatus.TAMPER_DETECTED
            ),
            "native_transport_unavailable",
        ),
        (
            NativeCorePolicyError(
                "feature denied", status=NativeCoreStatus.FEATURE_DENIED
            ),
            "native_transport_unavailable",
        ),
        (NativeCoreUnavailableError("missing"), "native_transport_unavailable"),
        (
            NativeCoreUnavailableError("pipe", status=NativeCoreStatus.IO),
            "native_transport_unavailable",
        ),
        (NativeCoreProtocolError("protocol"), "native_transport_unavailable"),
        (NativeCorePolicyError("policy"), "native_transport_unavailable"),
    ],
)
def test_native_core_errors_preserve_machine_status(error, expected_code):
    assert module._native_core_error(error).code == expected_code


def test_terminal_status_overrides_only_security_and_transport_failures():
    lease_error = module._native_core_status_error(
        NativeCoreStatus.LEASE_EXPIRED,
        include_generic=False,
    ) or module._reason_error(NativeCoreAsrReason.CALLBACK_FAILED)
    assert lease_error.code == "native_transport_unavailable"
    assert "授权" not in lease_error.user_message

    provider_error = module._native_core_status_error(
        NativeCoreStatus.UNAVAILABLE,
        include_generic=False,
    ) or module._reason_error(NativeCoreAsrReason.PROVIDER_UNAVAILABLE)
    assert provider_error.code == "native_trigger_rejected"


def test_transport_polls_success_and_persists_without_logging_text(
    monkeypatch, tmp_path: Path
):
    operation = _Operation()
    stored: list[tuple[str, dict[str, object]]] = []

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            return 99

        def poll_native_asr(self, request_handle):
            assert request_handle == 99
            return NativeCoreAsrPollResult(
                state=NativeCoreAsrRequestState.SUCCEEDED,
                reason=NativeCoreAsrReason.READY,
                terminal_status=NativeCoreStatus.OK,
                server_id=1265681483748099968,
                local_id=342,
                text="private transcript",
            )

        def close_native_asr(self, request_handle):
            assert request_handle == 99

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(module.secrets, "token_urlsafe", lambda _size: "opaque")
    monkeypatch.setattr(module.threading, "Thread", _ImmediateThread)
    def store_pending(**kwargs):
        stored.append(("pending", kwargs))
        return SimpleNamespace(status="pending", request_id=kwargs["request_id"])

    monkeypatch.setattr(module, "mark_native_voice_transcript_pending", store_pending)
    monkeypatch.setattr(
        module,
        "mark_native_voice_transcript_success",
        lambda **kwargs: stored.append(("success", kwargs)),
    )

    transport = module.NativeCoreVoiceAsrTransport()
    receipt = transport.trigger(
        NativeVoiceTriggerCommand(
            account_dir=tmp_path / "wxid_test",
            account="wxid_test",
            conversation="wxid_peer",
            server_id=1265681483748099968,
            local_id=342,
        )
    )

    assert receipt.status == "accepted"
    assert receipt.request_id == "native-core:opaque"
    assert [kind for kind, _ in stored] == ["pending", "success"]
    assert stored[1][1]["text"] == "private transcript"
    assert operation.closed is True


def test_transport_fails_closed_on_account_mismatch(monkeypatch, tmp_path: Path):
    operation = _Operation()
    status = NativeCoreAsrStatus(
        reason=NativeCoreAsrReason.ACCOUNT_MISMATCH,
        platform_supported=True,
        ready=False,
        wechat_process_id=1234,
        expected_wechat_version="4.1.12.26",
        actual_wechat_version="4.1.12.26",
        expected_weixin_sha256=b"a" * 32,
        actual_weixin_sha256=b"a" * 32,
    )
    client = SimpleNamespace(
        supports_native_asr=True,
        get_native_asr_status=lambda *_args: status,
    )
    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: client)

    with pytest.raises(NativeVoiceTriggerError) as caught:
        module.NativeCoreVoiceAsrTransport().trigger(
            NativeVoiceTriggerCommand(
                account_dir=tmp_path / "wxid_test",
                account="wxid_test",
                conversation="wxid_peer",
                server_id=1,
                local_id=2,
            )
        )

    assert caught.value.code == "native_trigger_rejected"
    assert operation.closed is True


def test_trigger_reaches_native_begin_without_license_refresh_or_heartbeat(
    monkeypatch, tmp_path: Path
):
    operation = _Operation()
    begin_called = False

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            nonlocal begin_called
            begin_called = True
            raise NativeCoreUnavailableError("stop after begin")

    refresh = Mock(side_effect=AssertionError("ASR must not refresh a license"))

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(native_core_lease, "refresh_native_core_lease", refresh)

    with pytest.raises(NativeVoiceTriggerError) as caught:
        module.NativeCoreVoiceAsrTransport().trigger(
            NativeVoiceTriggerCommand(
                account_dir=tmp_path / "wxid_test",
                account="wxid_test",
                conversation="wxid_peer",
                server_id=1,
                local_id=2,
            )
        )

    assert caught.value.code == "native_transport_unavailable"
    assert "授权" not in caught.value.user_message
    assert begin_called is True
    refresh.assert_not_called()
    assert operation.closed is True


def test_thread_start_failure_releases_operation_and_active_slot(
    monkeypatch, tmp_path: Path
):
    operation = _Operation()
    closed: list[int] = []

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            return 99

        def close_native_asr(self, request_handle):
            closed.append(request_handle)

    class BrokenThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("thread unavailable")

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(module.secrets, "token_urlsafe", lambda _size: "opaque")
    monkeypatch.setattr(module.threading, "Thread", BrokenThread)
    monkeypatch.setattr(
        module,
        "mark_native_voice_transcript_pending",
        lambda **kwargs: SimpleNamespace(
            status="pending", request_id=kwargs["request_id"]
        ),
    )
    transport = module.NativeCoreVoiceAsrTransport()
    command = NativeVoiceTriggerCommand(
        account_dir=tmp_path / "wxid_test",
        account="wxid_test",
        conversation="wxid_peer",
        server_id=1,
        local_id=2,
    )

    with pytest.raises(NativeVoiceTriggerError) as caught:
        transport.trigger(command)

    assert caught.value.code == "native_transport_failed"
    assert operation.closed is True
    assert transport._active is None
    assert closed


def test_concurrent_cached_success_wins_and_new_native_handle_is_closed(
    monkeypatch, tmp_path: Path
):
    operation = _Operation()
    closed: list[int] = []

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            return 99

        def close_native_asr(self, request_handle):
            closed.append(request_handle)

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(module.secrets, "token_urlsafe", lambda _size: "new")
    monkeypatch.setattr(
        module,
        "mark_native_voice_transcript_pending",
        lambda **_kwargs: SimpleNamespace(status="success", request_id="winner"),
    )
    transport = module.NativeCoreVoiceAsrTransport()

    receipt = transport.trigger(
        NativeVoiceTriggerCommand(
            account_dir=tmp_path / "wxid_test",
            account="wxid_test",
            conversation="wxid_peer",
            server_id=1,
            local_id=2,
        )
    )

    assert receipt.status == "pending"
    assert receipt.request_id == "winner"
    assert closed == [99]
    assert operation.closed is True
    assert transport._active is None


def test_worker_retries_transient_close_failure(monkeypatch, tmp_path: Path):
    operation = _Operation()
    close_calls = 0

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            return 99

        def poll_native_asr(self, _request_handle):
            return NativeCoreAsrPollResult(
                state=NativeCoreAsrRequestState.SUCCEEDED,
                reason=NativeCoreAsrReason.READY,
                terminal_status=NativeCoreStatus.OK,
                server_id=1,
                local_id=2,
                text="result",
            )

        def close_native_asr(self, _request_handle):
            nonlocal close_calls
            close_calls += 1
            if close_calls == 1:
                raise NativeCoreUnavailableError("temporary pipe failure")

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(module, "_CLOSE_RETRY_DELAYS_SECONDS", (0.0,))
    monkeypatch.setattr(
        module,
        "mark_native_voice_transcript_pending",
        lambda **kwargs: SimpleNamespace(
            status="pending", request_id=kwargs["request_id"]
        ),
    )
    monkeypatch.setattr(module, "mark_native_voice_transcript_success", lambda **_k: None)
    transport = module.NativeCoreVoiceAsrTransport()

    receipt = transport.trigger(
        NativeVoiceTriggerCommand(
            account_dir=tmp_path / "wxid_test",
            account="wxid_test",
            conversation="wxid_peer",
            server_id=1,
            local_id=2,
        )
    )

    assert receipt.status == "accepted"
    assert close_calls == 2
    assert operation.closed is True
    assert transport.restart_required is False
    assert transport._active is None


def test_persistent_worker_close_failure_requires_restart(monkeypatch, tmp_path: Path):
    operation = _Operation()

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            return 99

        def poll_native_asr(self, _request_handle):
            return NativeCoreAsrPollResult(
                state=NativeCoreAsrRequestState.SUCCEEDED,
                reason=NativeCoreAsrReason.READY,
                terminal_status=NativeCoreStatus.OK,
                server_id=1,
                local_id=2,
                text="result",
            )

        def close_native_asr(self, _request_handle):
            raise NativeCoreUnavailableError("persistent pipe failure")

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(module, "_CLOSE_RETRY_DELAYS_SECONDS", ())
    monkeypatch.setattr(
        module,
        "mark_native_voice_transcript_pending",
        lambda **kwargs: SimpleNamespace(
            status="pending", request_id=kwargs["request_id"]
        ),
    )
    monkeypatch.setattr(module, "mark_native_voice_transcript_success", lambda **_k: None)
    transport = module.NativeCoreVoiceAsrTransport()
    command = NativeVoiceTriggerCommand(
        account_dir=tmp_path / "wxid_test",
        account="wxid_test",
        conversation="wxid_peer",
        server_id=1,
        local_id=2,
    )

    assert transport.trigger(command).status == "accepted"
    assert transport.restart_required is True
    assert operation.closed is False
    with pytest.raises(NativeVoiceTriggerError) as caught:
        transport.trigger(command)
    assert caught.value.code == "native_trigger_rejected"
    assert "完全退出微信" in caught.value.user_message
    assert "重启本应用" in caught.value.user_message


def test_pending_store_and_close_failure_retain_native_generation(
    monkeypatch, tmp_path: Path
):
    operation = _Operation()

    class Client:
        supports_native_asr = True

        def get_native_asr_status(self, *_args):
            return _ready_status()

        def begin_native_asr(self, *_args):
            return 99

        def close_native_asr(self, _request_handle):
            raise NativeCoreUnavailableError("persistent pipe failure")

    monkeypatch.setattr(module, "managed_native_core_operation", lambda: operation)
    monkeypatch.setattr(module, "get_native_core_client", lambda: Client())
    monkeypatch.setattr(module, "_CLOSE_RETRY_DELAYS_SECONDS", ())
    monkeypatch.setattr(
        module,
        "mark_native_voice_transcript_pending",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("cache unavailable")),
    )
    transport = module.NativeCoreVoiceAsrTransport()

    with pytest.raises(NativeVoiceTriggerError) as caught:
        transport.trigger(
            NativeVoiceTriggerCommand(
                account_dir=tmp_path / "wxid_test",
                account="wxid_test",
                conversation="wxid_peer",
                server_id=1,
                local_id=2,
            )
        )

    assert caught.value.code == "native_trigger_rejected"
    assert transport.restart_required is True
    assert operation.closed is False
