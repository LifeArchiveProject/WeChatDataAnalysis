from __future__ import annotations

import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .account_identity import resolve_account_self_username
from .native_core_broker import NativeCoreManagedOperation, managed_native_core_operation
from .native_core_client import (
    NativeCoreAsrReason,
    NativeCoreAsrRequestState,
    NativeCoreClient,
    NativeCoreError,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreStatus,
    NativeCoreUnavailableError,
    get_native_core_client,
)
from .native_voice_transcription import (
    NativeVoiceTriggerCommand,
    NativeVoiceTriggerError,
    NativeVoiceTriggerReceipt,
    mark_native_voice_transcript_error,
    mark_native_voice_transcript_pending,
    mark_native_voice_transcript_success,
)


_POLL_INTERVAL_SECONDS = 1.0
_POLL_TIMEOUT_SECONDS = 100.0
_EXPECTED_WECHAT_VERSION = "4.1.12.26"
_CLOSE_RETRY_DELAYS_SECONDS = (0.05, 0.15)


_STATUS_REASON_KEYS: dict[NativeCoreAsrReason, str] = {
    NativeCoreAsrReason.READY: "",
    NativeCoreAsrReason.UNSUPPORTED_PLATFORM: "unsupported_platform",
    NativeCoreAsrReason.UNSUPPORTED_ARCHITECTURE: "unsupported_architecture",
    NativeCoreAsrReason.RUNTIME_UNAVAILABLE: "bridge_manager_unavailable",
    NativeCoreAsrReason.WECHAT_NOT_RUNNING: "weixin_main_ui_not_found",
    NativeCoreAsrReason.WECHAT_NOT_LOGGED_IN: "weixin_main_ui_not_found",
    NativeCoreAsrReason.ACCOUNT_UNVERIFIED: "active_account_unverified",
    NativeCoreAsrReason.ACCOUNT_MISMATCH: "active_account_mismatch",
    NativeCoreAsrReason.WECHAT_VERSION_MISMATCH: "weixin_version_unsupported",
    NativeCoreAsrReason.WEIXIN_SHA256_MISMATCH: "weixin_version_unsupported",
    NativeCoreAsrReason.BRIDGE_RESTART_REQUIRED: "bridge_restart_required",
    NativeCoreAsrReason.BUSY: "bridge_manager_unavailable",
}


_ERROR_DETAILS: dict[NativeCoreAsrReason, tuple[str, str]] = {
    NativeCoreAsrReason.UNSUPPORTED_PLATFORM: (
        "native_transport_unavailable",
        "微信原生语音转文字目前仅支持 64 位 Windows。",
    ),
    NativeCoreAsrReason.UNSUPPORTED_ARCHITECTURE: (
        "native_transport_unavailable",
        "微信原生语音转文字需要 64 位 Windows。",
    ),
    NativeCoreAsrReason.RUNTIME_UNAVAILABLE: (
        "native_transport_unavailable",
        "微信原生语音转文字服务尚未就绪。",
    ),
    NativeCoreAsrReason.WECHAT_NOT_RUNNING: (
        "native_weixin_not_running",
        "请先登录并打开微信，再使用微信原生语音转文字。",
    ),
    NativeCoreAsrReason.WECHAT_NOT_LOGGED_IN: (
        "native_weixin_not_running",
        "请先登录并进入微信，再使用微信原生语音转文字。",
    ),
    NativeCoreAsrReason.ACCOUNT_UNVERIFIED: (
        "native_trigger_rejected",
        "无法确认当前项目账号与已登录微信账号一致。",
    ),
    NativeCoreAsrReason.ACCOUNT_MISMATCH: (
        "native_trigger_rejected",
        "当前项目账号与已登录微信账号不一致。",
    ),
    NativeCoreAsrReason.WECHAT_VERSION_MISMATCH: (
        "native_weixin_version_unsupported",
        "当前微信版本不受支持。请使用微信 4.1.12.26，并完全退出、重新启动微信后再试。",
    ),
    NativeCoreAsrReason.WEIXIN_SHA256_MISMATCH: (
        "native_weixin_version_unsupported",
        "当前微信版本不受支持。请使用微信 4.1.12.26，并完全退出、重新启动微信后再试。",
    ),
    NativeCoreAsrReason.BRIDGE_RESTART_REQUIRED: (
        "native_trigger_rejected",
        "微信原生语音转文字桥接状态已失效。请完全退出微信，重启本应用（开发模式下同时重启后端）后，再重新打开并登录微信。",
    ),
    NativeCoreAsrReason.BUSY: (
        "native_transport_busy",
        "已有微信原生语音转文字任务正在处理，请稍后再试。",
    ),
    NativeCoreAsrReason.MESSAGE_NOT_FOUND: (
        "voice_message_not_found",
        "微信未找到指定的语音消息。",
    ),
    NativeCoreAsrReason.MESSAGE_AMBIGUOUS: (
        "voice_message_ambiguous",
        "微信内部匹配到多条语音消息，已停止转写。",
    ),
    NativeCoreAsrReason.NOT_VOICE: (
        "native_trigger_rejected",
        "指定消息不是可转写的微信语音。",
    ),
    NativeCoreAsrReason.PROVIDER_UNAVAILABLE: (
        "native_trigger_rejected",
        "微信原生语音转文字服务当前不可用。",
    ),
    NativeCoreAsrReason.DISPATCH_FAILED: (
        "native_trigger_rejected",
        "微信未能提交原生语音转文字任务。",
    ),
    NativeCoreAsrReason.CALLBACK_FAILED: (
        "native_transcript_failed",
        "微信原生语音转文字未能返回结果。",
    ),
    NativeCoreAsrReason.TIMEOUT: (
        "native_trigger_timeout",
        "等待微信原生语音转文字结果超时。",
    ),
    NativeCoreAsrReason.CANCELLED: (
        "native_transcript_failed",
        "微信原生语音转文字任务已取消。",
    ),
    NativeCoreAsrReason.INTERNAL: (
        "native_transport_failed",
        "微信原生语音转文字内部调用失败。",
    ),
}


def _reason_error(reason: NativeCoreAsrReason) -> NativeVoiceTriggerError:
    code, message = _ERROR_DETAILS.get(
        reason,
        ("native_transport_failed", "微信原生语音转文字调用失败。"),
    )
    return NativeVoiceTriggerError(code, message)


_NATIVE_ASR_POLICY_STATUSES = {
    NativeCoreStatus.LICENSE_REQUIRED,
    NativeCoreStatus.LEASE_INVALID,
    NativeCoreStatus.LEASE_EXPIRED,
    NativeCoreStatus.FEATURE_DENIED,
}
_NATIVE_ASR_INTEGRITY_STATUSES = {
    NativeCoreStatus.BUILD_MISMATCH,
    NativeCoreStatus.DEVICE_MISMATCH,
    NativeCoreStatus.TAMPER_DETECTED,
}


def _native_core_status_error(
    status: int | NativeCoreStatus | None,
    *,
    include_generic: bool,
) -> NativeVoiceTriggerError | None:
    try:
        known = NativeCoreStatus(status) if status is not None else None
    except (TypeError, ValueError):
        known = None
    if known is None:
        return None
    if known is NativeCoreStatus.BUSY:
        return NativeVoiceTriggerError(
            "native_transport_busy",
            "已有微信原生语音转文字任务正在处理，请稍后再试。",
        )
    if known is NativeCoreStatus.TIMEOUT:
        return NativeVoiceTriggerError(
            "native_trigger_timeout",
            "等待微信原生语音转文字结果超时。",
        )
    if known in _NATIVE_ASR_POLICY_STATUSES:
        return NativeVoiceTriggerError(
            "native_transport_unavailable",
            "当前受保护 DLL 或构建中的微信原生语音转文字功能不可用。",
        )
    if known in _NATIVE_ASR_INTEGRITY_STATUSES:
        return NativeVoiceTriggerError(
            "native_transport_unavailable",
            "受保护的微信原生语音转文字组件与当前构建或设备不匹配。",
        )
    if known in {NativeCoreStatus.PROTOCOL, NativeCoreStatus.INVALID_ARGUMENT}:
        return NativeVoiceTriggerError(
            "native_transport_invalid_response",
            "受保护的微信原生语音转文字组件返回了无效响应。",
        )
    if not include_generic:
        return None
    if known in {
        NativeCoreStatus.UNAVAILABLE,
        NativeCoreStatus.IO,
        NativeCoreStatus.UNSUPPORTED,
    }:
        return NativeVoiceTriggerError(
            "native_transport_unavailable",
            "当前构建中的受保护微信原生语音转文字组件不可用。",
        )
    return NativeVoiceTriggerError(
        "native_transport_failed",
        "受保护的微信原生语音转文字调用失败。",
    )


def _native_core_error(exc: BaseException) -> NativeVoiceTriggerError:
    if isinstance(exc, NativeCoreError):
        mapped = _native_core_status_error(exc.status, include_generic=True)
        if mapped is not None:
            return mapped
    if isinstance(exc, NativeCorePolicyError):
        return NativeVoiceTriggerError(
            "native_transport_unavailable",
            "当前受保护 DLL 或构建中的微信原生语音转文字功能不可用。",
        )
    if isinstance(exc, (NativeCoreUnavailableError, NativeCoreProtocolError)):
        return NativeVoiceTriggerError(
            "native_transport_unavailable",
            "当前构建中的受保护微信原生语音转文字组件不可用。",
        )
    return NativeVoiceTriggerError(
        "native_transport_failed",
        "微信原生语音转文字调用失败。",
    )


def native_core_voice_asr_status(account_dir: Optional[Path] = None) -> dict[str, object]:
    """Passively inspect readiness through the protected native-core broker."""

    result: dict[str, object] = {
        "available": False,
        "reason": "",
        "version": _EXPECTED_WECHAT_VERSION,
        "pid": None,
    }
    if os.name != "nt" or not sys.platform.startswith("win"):
        result["reason"] = "unsupported_platform"
        return result
    if account_dir is None:
        result["reason"] = "active_account_unverified"
        return result
    if _TRANSPORT.restart_required:
        result["reason"] = "bridge_restart_required"
        return result
    operation: NativeCoreManagedOperation | None = None
    try:
        operation = managed_native_core_operation()
        client = get_native_core_client()
        if not client.supports_native_asr:
            result["reason"] = "bridge_manager_unavailable"
            return result
        account_path = Path(account_dir)
        status = client.get_native_asr_status(
            resolve_account_self_username(account_path),
            account_path,
        )
        reason = _STATUS_REASON_KEYS.get(status.reason, "bridge_manager_unavailable")
        result.update(
            {
                "available": bool(status.ready and status.reason is NativeCoreAsrReason.READY),
                "reason": reason,
                "version": status.expected_wechat_version or _EXPECTED_WECHAT_VERSION,
                "pid": status.wechat_process_id or None,
            }
        )
        return result
    except NativeCorePolicyError:
        result["reason"] = "protected_build_unavailable"
        return result
    except (NativeCoreError, OSError, ValueError):
        result["reason"] = "inspection_failed"
        return result
    finally:
        if operation is not None:
            operation.close()


@dataclass
class _ActiveRequest:
    command: NativeVoiceTriggerCommand
    request_id: str
    request_handle: int
    client: NativeCoreClient
    operation: NativeCoreManagedOperation
    cleanup_failed: bool = False


class NativeCoreVoiceAsrTransport:
    """One-at-a-time native-core ASR transport with a bounded poll worker."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: _ActiveRequest | None = None

    @property
    def restart_required(self) -> bool:
        with self._lock:
            return bool(self._active is not None and self._active.cleanup_failed)

    @staticmethod
    def _key(command: NativeVoiceTriggerCommand) -> tuple[str, str, int, int]:
        return (
            os.path.normcase(os.path.abspath(os.fspath(command.account_dir))),
            command.conversation,
            int(command.server_id),
            int(command.local_id),
        )

    @staticmethod
    def _close_native_handle(client: NativeCoreClient, request_handle: int) -> bool:
        for attempt in range(len(_CLOSE_RETRY_DELAYS_SECONDS) + 1):
            try:
                client.close_native_asr(request_handle)
                return True
            except Exception:
                if attempt < len(_CLOSE_RETRY_DELAYS_SECONDS):
                    time.sleep(_CLOSE_RETRY_DELAYS_SECONDS[attempt])
        return False

    def _finish_active(self, active: _ActiveRequest) -> bool:
        if not self._close_native_handle(active.client, active.request_handle):
            with self._lock:
                active.cleanup_failed = True
                if self._active is None:
                    self._active = active
            return False
        with self._lock:
            if self._active is active:
                self._active = None
        active.operation.close()
        return True

    @staticmethod
    def _cleanup_failure_error() -> NativeVoiceTriggerError:
        return NativeVoiceTriggerError(
            "native_trigger_rejected",
            "微信原生语音转文字桥接清理失败。请完全退出微信，重启本应用（开发模式下同时重启后端）后，再重新打开并登录微信。",
        )

    def trigger(self, command: NativeVoiceTriggerCommand) -> NativeVoiceTriggerReceipt:
        with self._lock:
            if self._active is not None:
                if self._active.cleanup_failed:
                    raise self._cleanup_failure_error()
                if self._key(self._active.command) == self._key(command):
                    return NativeVoiceTriggerReceipt(
                        status="pending", request_id=self._active.request_id
                    )
                raise _reason_error(NativeCoreAsrReason.BUSY)

            operation: NativeCoreManagedOperation | None = None
            request_handle = 0
            client: NativeCoreClient | None = None
            request_id = ""
            active: _ActiveRequest | None = None
            try:
                operation = managed_native_core_operation()
                client = get_native_core_client()
                if not client.supports_native_asr:
                    raise NativeVoiceTriggerError(
                        "native_transport_unavailable",
                        "当前受保护的 native-core 运行时不包含微信原生语音转文字功能。",
                    )
                status = client.get_native_asr_status(
                    command.account, command.account_dir
                )
                if not status.ready or status.reason is not NativeCoreAsrReason.READY:
                    raise _reason_error(status.reason)
                request_handle = client.begin_native_asr(
                    command.account,
                    command.account_dir,
                    command.conversation,
                    command.server_id,
                    command.local_id,
                )
                request_id = "native-core:" + secrets.token_urlsafe(24)
                active = _ActiveRequest(
                    command=command,
                    request_id=request_id,
                    request_handle=request_handle,
                    client=client,
                    operation=operation,
                )
                request_handle = 0
                cached = mark_native_voice_transcript_pending(
                    account_dir=command.account_dir,
                    conversation=command.conversation,
                    server_id=command.server_id,
                    local_id=command.local_id,
                    request_id=request_id,
                )
                if cached.status != "pending" or cached.request_id != request_id:
                    if not self._finish_active(active):
                        operation = None
                        active = None
                        raise self._cleanup_failure_error()
                    operation = None
                    active = None
                    if cached.request_id and cached.status in {"pending", "success"}:
                        return NativeVoiceTriggerReceipt(
                            status="pending", request_id=cached.request_id
                        )
                    raise NativeVoiceTriggerError(
                        "native_transport_invalid_response",
                        "微信原生语音转文字缓存代际发生冲突。",
                    )
                self._active = active
                operation = None
                worker = threading.Thread(
                    target=self._poll_worker,
                    args=(active,),
                    name="wechat-native-asr-poll",
                    daemon=True,
                )
                worker.start()
                return NativeVoiceTriggerReceipt(
                    status="accepted", request_id=request_id
                )
            except NativeVoiceTriggerError as exc:
                if active is not None:
                    if not self._finish_active(active):
                        operation = None
                        raise self._cleanup_failure_error() from exc
                    operation = None
                elif client is not None and request_handle:
                    if not self._close_native_handle(client, request_handle):
                        retained = _ActiveRequest(
                            command=command,
                            request_id=request_id or "native-core:cleanup-failed",
                            request_handle=request_handle,
                            client=client,
                            operation=operation,
                            cleanup_failed=True,
                        )
                        self._active = retained
                        operation = None
                        raise self._cleanup_failure_error() from exc
                raise
            except Exception as exc:
                if active is not None:
                    if not self._finish_active(active):
                        operation = None
                        raise self._cleanup_failure_error() from exc
                    operation = None
                elif client is not None and request_handle:
                    if not self._close_native_handle(client, request_handle):
                        retained = _ActiveRequest(
                            command=command,
                            request_id=request_id or "native-core:cleanup-failed",
                            request_handle=request_handle,
                            client=client,
                            operation=operation,
                            cleanup_failed=True,
                        )
                        self._active = retained
                        operation = None
                        raise self._cleanup_failure_error() from exc
                raise _native_core_error(exc) from exc
            finally:
                if operation is not None:
                    operation.close()

    def _store_error(
        self,
        active: _ActiveRequest,
        error: NativeVoiceTriggerError,
    ) -> None:
        mark_native_voice_transcript_error(
            account_dir=active.command.account_dir,
            conversation=active.command.conversation,
            server_id=active.command.server_id,
            local_id=active.command.local_id,
            request_id=active.request_id,
            error_code=error.code,
            error_message=error.user_message,
        )

    def _poll_worker(self, active: _ActiveRequest) -> None:
        deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
        try:
            while True:
                poll = active.client.poll_native_asr(active.request_handle)
                if (
                    poll.server_id != active.command.server_id
                    or poll.local_id != active.command.local_id
                ):
                    raise NativeVoiceTriggerError(
                        "native_transport_invalid_response",
                        "微信原生语音转文字返回的消息身份不匹配。",
                    )
                if poll.state is NativeCoreAsrRequestState.SUCCEEDED:
                    mark_native_voice_transcript_success(
                        account_dir=active.command.account_dir,
                        conversation=active.command.conversation,
                        server_id=active.command.server_id,
                        local_id=active.command.local_id,
                        request_id=active.request_id,
                        text=poll.text,
                    )
                    return
                if poll.state in {
                    NativeCoreAsrRequestState.FAILED,
                    NativeCoreAsrRequestState.CANCELLED,
                }:
                    error = _native_core_status_error(
                        poll.terminal_status,
                        include_generic=False,
                    ) or _reason_error(poll.reason)
                    self._store_error(active, error)
                    return
                if time.monotonic() >= deadline:
                    self._store_error(active, _reason_error(NativeCoreAsrReason.TIMEOUT))
                    return
                time.sleep(_POLL_INTERVAL_SECONDS)
        except NativeVoiceTriggerError as exc:
            self._store_error(active, exc)
        except Exception as exc:
            self._store_error(active, _native_core_error(exc))
        finally:
            self._finish_active(active)


_TRANSPORT = NativeCoreVoiceAsrTransport()


def build_native_core_voice_asr_transport() -> NativeCoreVoiceAsrTransport:
    return _TRANSPORT


__all__ = [
    "NativeCoreVoiceAsrTransport",
    "build_native_core_voice_asr_transport",
    "native_core_voice_asr_status",
]
