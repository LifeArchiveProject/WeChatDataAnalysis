from __future__ import annotations

import ctypes
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from wechat_decrypt_tool import native_core_client as native
from wechat_decrypt_tool.native_core_client import (
    NativeCoreAsrReason,
    NativeCoreAsrRequestState,
    NativeCoreClient,
    NativeCoreFeature,
    NativeCoreProtocolError,
    NativeCoreStatus,
)


_REQUIRED_SYMBOLS = (
    "wce_client_abi_version",
    "wce_client_build_id",
    "wce_client_create",
    "wce_client_destroy",
    "wce_client_get_status",
    "wce_client_prove_license_challenge",
    "wce_client_install_lease",
    "wce_client_authorize",
    "wce_database_open",
    "wce_database_close",
    "wce_query_open",
    "wce_query_fetch",
    "wce_query_close",
    "wce_export_begin",
    "wce_export_write",
    "wce_export_finish",
    "wce_export_abort",
    "wce_export_encrypt_begin",
    "wce_export_encrypt_write",
    "wce_export_encrypt_finish",
    "wce_export_encrypt_abort",
    "wce_buffer_release",
    "wce_status_message",
)
_NATIVE_ASR_SYMBOLS = (
    "wce_native_asr_get_status",
    "wce_native_asr_begin",
    "wce_native_asr_poll",
    "wce_native_asr_close",
)
_NATIVE_ASR_WEIXIN_SHA256 = (
    "4914a621a810ecbc0a132b6ff8f612658cfce323d3989b3e5fe32d4ff343ba46"
)


class _FakeFunction:
    def __init__(self, callback: Callable[..., Any] | None = None) -> None:
        self.callback = callback or (lambda *_args: 0)
        self.argtypes: list[Any] | None = None
        self.restype: Any = None

    def __call__(self, *args: Any) -> Any:
        return self.callback(*args)


def _abi_library(*, native_asr_symbols: tuple[str, ...] = ()) -> SimpleNamespace:
    functions = {name: _FakeFunction() for name in _REQUIRED_SYMBOLS}
    functions.update({name: _FakeFunction() for name in native_asr_symbols})
    return SimpleNamespace(**functions)


def _configure_client(
    library: SimpleNamespace,
    *,
    platform: str = "windows",
    development_build: bool = False,
    native_asr_abi_version: int = 1,
    native_asr_feature_bit: int = 16,
    native_asr_authorization: str = "database-read",
    native_asr_target_wechat_version: str = "4.1.12.26",
    native_asr_target_weixin_sha256: str = _NATIVE_ASR_WEIXIN_SHA256,
) -> NativeCoreClient:
    client = object.__new__(NativeCoreClient)
    client._library = library
    client._build_manifest = SimpleNamespace(
        root_public_key_compiled=False,
        platform=platform,
        development_build=development_build,
        native_asr_abi_version=native_asr_abi_version,
        native_asr_feature_bit=native_asr_feature_bit,
        native_asr_authorization=native_asr_authorization,
        native_asr_target_wechat_version=native_asr_target_wechat_version,
        native_asr_target_weixin_sha256=native_asr_target_weixin_sha256,
    )
    client._configure_abi()
    return client


def _dereference(pointer: Any, value_type: type[ctypes.Structure]) -> Any:
    return ctypes.cast(pointer, ctypes.POINTER(value_type)).contents


def _write_fixed_utf8(
    value: native._WceNativeAsrStatus,
    field_name: str,
    payload: bytes,
) -> None:
    field = getattr(type(value), field_name)
    assert len(payload) <= 32
    ctypes.memmove(ctypes.addressof(value) + field.offset, payload, len(payload))


class _AsrStub:
    def __init__(self, *, poll_payload: bytes = "转写完成".encode()) -> None:
        self.poll_payload = poll_payload
        self.close_status = NativeCoreStatus.OK
        self.poll_buffers: list[Any] = []
        self.releases: list[tuple[int, bool]] = []
        self.status_calls: list[tuple[bytes, bytes]] = []
        self.begin_calls: list[tuple[bytes, bytes, bytes, int, int, int]] = []
        self.poll_calls: list[tuple[int, int]] = []
        self.close_calls: list[tuple[int, int]] = []
        self.library = SimpleNamespace(
            wce_native_asr_get_status=_FakeFunction(self._get_status),
            wce_native_asr_begin=_FakeFunction(self._begin),
            wce_native_asr_poll=_FakeFunction(self._poll),
            wce_native_asr_close=_FakeFunction(self._close),
            wce_buffer_release=_FakeFunction(self._release),
            wce_status_message=_FakeFunction(lambda _status: b"status"),
        )

    def _get_status(self, _client: Any, options_pointer: Any, status_pointer: Any) -> int:
        options = _dereference(options_pointer, native._WceNativeAsrStatusOptions)
        status = _dereference(status_pointer, native._WceNativeAsrStatus)
        self.status_calls.append((bytes(options.account_utf8), bytes(options.account_directory_utf8)))
        assert options.struct_size == ctypes.sizeof(native._WceNativeAsrStatusOptions)
        assert options.reserved == 0
        status.reason = int(NativeCoreAsrReason.READY)
        status.platform_supported = 1
        status.ready = 1
        status.wechat_process_id = 4321
        status.reserved = 0
        _write_fixed_utf8(status, "expected_wechat_version", b"4.1.12.26\0")
        _write_fixed_utf8(status, "actual_wechat_version", b"4.1.12.26\0")
        status.expected_weixin_sha256[:] = bytes(range(32))
        status.actual_weixin_sha256[:] = bytes(reversed(range(32)))
        return int(NativeCoreStatus.OK)

    def _begin(self, _client: Any, options_pointer: Any, output_pointer: Any) -> int:
        options = _dereference(options_pointer, native._WceNativeAsrBeginOptions)
        self.begin_calls.append(
            (
                bytes(options.account_utf8),
                bytes(options.account_directory_utf8),
                bytes(options.conversation_utf8),
                int(options.server_id),
                int(options.local_id),
                int(options.operation_nonce),
            )
        )
        output = ctypes.cast(output_pointer, ctypes.POINTER(ctypes.c_uint64))
        output[0] = 73
        return int(NativeCoreStatus.OK)

    def _poll(
        self,
        _client: Any,
        options_pointer: Any,
        result_pointer: Any,
        output_pointer: Any,
    ) -> int:
        options = _dereference(options_pointer, native._WceNativeAsrPollOptions)
        result = _dereference(result_pointer, native._WceNativeAsrPollResult)
        output = _dereference(output_pointer, native._WceOwnedBuffer)
        self.poll_calls.append((int(options.request_handle), int(options.operation_nonce)))
        result.state = int(NativeCoreAsrRequestState.SUCCEEDED)
        result.reason = int(NativeCoreAsrReason.READY)
        result.terminal_status = int(NativeCoreStatus.OK)
        result.server_id = 1_265_681_483_748_099_968
        result.local_id = 342
        result.reserved = 0
        buffer = (ctypes.c_uint8 * len(self.poll_payload)).from_buffer_copy(
            self.poll_payload
        )
        self.poll_buffers.append(buffer)
        output.flags = 0
        output.data = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8))
        output.size = len(self.poll_payload)
        return int(NativeCoreStatus.OK)

    def _close(self, _client: Any, options_pointer: Any) -> int:
        options = _dereference(options_pointer, native._WceNativeAsrCloseOptions)
        self.close_calls.append(
            (int(options.request_handle), int(options.operation_nonce))
        )
        return int(self.close_status)

    def _release(self, output_pointer: Any) -> None:
        output = _dereference(output_pointer, native._WceOwnedBuffer)
        self.releases.append((int(output.size), bool(output.data)))
        output.data = ctypes.POINTER(ctypes.c_uint8)()
        output.size = 0


def _asr_client(stub: _AsrStub) -> NativeCoreClient:
    client = object.__new__(NativeCoreClient)
    client._supports_native_asr = True
    client._library = stub.library
    client._lock = threading.RLock()
    client._closed = False
    client._handle = ctypes.c_void_p(0x1234)
    client._native_asr_handles = set()
    return client


def test_native_asr_ctypes_layout_matches_public_abi() -> None:
    assert ctypes.sizeof(native._WceNativeAsrStatusOptions) == 24
    assert ctypes.sizeof(native._WceNativeAsrStatus) == 152
    assert ctypes.sizeof(native._WceNativeAsrBeginOptions) == 56
    assert ctypes.sizeof(native._WceNativeAsrPollOptions) == 24
    assert ctypes.sizeof(native._WceNativeAsrPollResult) == 32
    assert ctypes.sizeof(native._WceNativeAsrCloseOptions) == 24
    assert NativeCoreFeature.NATIVE_ASR == 1 << 4


@pytest.mark.parametrize("authorization", ["", "none"])
@pytest.mark.parametrize(
    "native_asr_symbols",
    [(), _NATIVE_ASR_SYMBOLS],
    ids=["legacy-no-exports", "generic-exports"],
)
def test_formal_non_fused_manifest_keeps_core_abi_usable(
    authorization: str,
    native_asr_symbols: tuple[str, ...],
) -> None:
    library = _abi_library(native_asr_symbols=native_asr_symbols)

    client = _configure_client(
        library,
        native_asr_abi_version=0,
        native_asr_feature_bit=0,
        native_asr_authorization=authorization,
        native_asr_target_wechat_version="",
        native_asr_target_weixin_sha256="",
    )

    assert client.supports_native_asr is False
    assert library.wce_database_open.argtypes is not None
    if native_asr_symbols:
        assert library.wce_native_asr_get_status.argtypes is None
    with pytest.raises(NativeCoreProtocolError, match="does not implement"):
        client.get_native_asr_status("wxid_example", Path.cwd().resolve())


def test_partial_native_asr_exports_are_rejected_as_incomplete_abi() -> None:
    library = _abi_library(native_asr_symbols=("wce_native_asr_get_status",))

    with pytest.raises(NativeCoreProtocolError, match="incomplete native ASR ABI") as caught:
        _configure_client(
            library,
            development_build=True,
            native_asr_abi_version=0,
            native_asr_feature_bit=0,
            native_asr_authorization="none",
            native_asr_target_wechat_version="",
            native_asr_target_weixin_sha256="",
        )

    assert "wce_native_asr_begin" in str(caught.value)
    assert "wce_native_asr_poll" in str(caught.value)
    assert "wce_native_asr_close" in str(caught.value)


def test_complete_native_asr_exports_are_bound_as_one_optional_feature() -> None:
    library = _abi_library(native_asr_symbols=_NATIVE_ASR_SYMBOLS)

    client = _configure_client(library, native_asr_authorization="database-read")

    assert client.supports_native_asr is True
    assert library.wce_native_asr_get_status.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(native._WceNativeAsrStatusOptions),
        ctypes.POINTER(native._WceNativeAsrStatus),
    ]
    assert library.wce_native_asr_poll.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(native._WceNativeAsrPollOptions),
        ctypes.POINTER(native._WceNativeAsrPollResult),
        ctypes.POINTER(native._WceOwnedBuffer),
    ]


def test_windows_development_exports_do_not_enable_non_fused_native_asr() -> None:
    library = _abi_library(native_asr_symbols=_NATIVE_ASR_SYMBOLS)

    client = _configure_client(
        library,
        development_build=True,
        native_asr_abi_version=0,
        native_asr_feature_bit=0,
        native_asr_authorization="none",
        native_asr_target_wechat_version="",
        native_asr_target_weixin_sha256="",
    )

    assert client.supports_native_asr is False
    assert library.wce_native_asr_get_status.argtypes is None
    with pytest.raises(NativeCoreProtocolError, match="does not implement"):
        client.get_native_asr_status("wxid_example", Path.cwd().resolve())


@pytest.mark.parametrize("authorization", ["", "none"])
def test_macos_exports_do_not_enable_or_require_windows_native_asr_contract(
    authorization: str,
) -> None:
    library = _abi_library(native_asr_symbols=_NATIVE_ASR_SYMBOLS)

    client = _configure_client(
        library,
        platform="macos",
        native_asr_abi_version=0,
        native_asr_feature_bit=0,
        native_asr_authorization=authorization,
        native_asr_target_wechat_version="",
        native_asr_target_weixin_sha256="",
    )

    assert client.supports_native_asr is False
    assert library.wce_native_asr_get_status.argtypes is None


@pytest.mark.parametrize("authorization", ["", "native-asr"])
def test_complete_native_asr_exports_require_database_read_manifest_contract(
    authorization: str,
) -> None:
    library = _abi_library(native_asr_symbols=_NATIVE_ASR_SYMBOLS)

    with pytest.raises(
        NativeCoreProtocolError,
        match="nativeAsrAuthorization must equal database-read",
    ):
        _configure_client(library, native_asr_authorization=authorization)


def test_formal_windows_legacy_manifest_fails_closed() -> None:
    library = _abi_library(native_asr_symbols=_NATIVE_ASR_SYMBOLS)

    with pytest.raises(
        NativeCoreProtocolError,
        match="nativeAsrAuthorization must equal database-read",
    ):
        _configure_client(
            library,
            native_asr_authorization="",
        )


def test_formal_fused_manifest_without_asr_exports_is_rejected() -> None:
    library = _abi_library()

    with pytest.raises(
        NativeCoreProtocolError,
        match="manifest declares fused support.*missing all native ASR ABI symbols",
    ):
        _configure_client(library)


def test_native_asr_status_begin_poll_and_close_round_trip(tmp_path: Path) -> None:
    stub = _AsrStub()
    client = _asr_client(stub)
    account_directory = tmp_path.resolve()

    status = client.get_native_asr_status("wxid_测试", account_directory)
    request_handle = client.begin_native_asr(
        "wxid_测试",
        account_directory,
        "wxid_hh0lft94go3y22",
        1_265_681_483_748_099_968,
        342,
    )
    result = client.poll_native_asr(request_handle)
    client.close_native_asr(request_handle)

    assert status.reason is NativeCoreAsrReason.READY
    assert status.platform_supported is True
    assert status.ready is True
    assert status.wechat_process_id == 4321
    assert status.expected_wechat_version == "4.1.12.26"
    assert status.actual_wechat_version == "4.1.12.26"
    assert status.expected_weixin_sha256 == bytes(range(32))
    assert status.actual_weixin_sha256 == bytes(reversed(range(32)))
    assert request_handle == 73
    assert result.state is NativeCoreAsrRequestState.SUCCEEDED
    assert result.reason is NativeCoreAsrReason.READY
    assert result.terminal_status is NativeCoreStatus.OK
    assert result.server_id == 1_265_681_483_748_099_968
    assert result.local_id == 342
    assert result.text == "转写完成"
    assert stub.status_calls == [
        ("wxid_测试".encode(), str(account_directory).encode())
    ]
    assert stub.begin_calls[0][:5] == (
        "wxid_测试".encode(),
        str(account_directory).encode(),
        b"wxid_hh0lft94go3y22",
        1_265_681_483_748_099_968,
        342,
    )
    assert stub.begin_calls[0][5] != 0
    assert stub.poll_calls[0][0] == 73
    assert stub.poll_calls[0][1] != 0
    assert stub.close_calls[0][0] == 73
    assert stub.close_calls[0][1] != 0
    assert stub.releases == [(len("转写完成".encode()), True)]
    assert client._native_asr_handles == set()


@pytest.mark.parametrize(
    "status",
    [
        NativeCoreStatus.NOT_FOUND,
        NativeCoreStatus.LICENSE_REQUIRED,
        NativeCoreStatus.LEASE_INVALID,
        NativeCoreStatus.LEASE_EXPIRED,
        NativeCoreStatus.FEATURE_DENIED,
        NativeCoreStatus.BUILD_MISMATCH,
        NativeCoreStatus.DEVICE_MISMATCH,
        NativeCoreStatus.TAMPER_DETECTED,
        NativeCoreStatus.LIMIT,
    ],
)
def test_native_asr_close_discards_handle_after_broker_cleanup_status(
    status: NativeCoreStatus,
) -> None:
    stub = _AsrStub()
    stub.close_status = status
    client = _asr_client(stub)
    client._native_asr_handles.add(73)

    client.close_native_asr(73)

    assert client._native_asr_handles == set()


def test_native_asr_poll_rejects_non_utf8_text_and_releases_owned_buffer() -> None:
    stub = _AsrStub(poll_payload=b"\xff")
    client = _asr_client(stub)
    client._native_asr_handles.add(73)

    with pytest.raises(NativeCoreProtocolError, match="non-UTF-8 text"):
        client.poll_native_asr(73)

    assert stub.releases == [(1, True)]
    assert client._native_asr_handles == {73}


@pytest.mark.parametrize("corruption", ["struct_size", "flags", "oversize"])
def test_native_asr_poll_rejects_malformed_owned_buffer_and_releases_it(
    corruption: str,
) -> None:
    stub = _AsrStub(poll_payload=b"ok")
    original_poll = stub._poll

    def malformed_poll(
        client_pointer: Any,
        options_pointer: Any,
        result_pointer: Any,
        output_pointer: Any,
    ) -> int:
        rc = original_poll(
            client_pointer,
            options_pointer,
            result_pointer,
            output_pointer,
        )
        output = _dereference(output_pointer, native._WceOwnedBuffer)
        if corruption == "struct_size":
            output.struct_size = 0
        elif corruption == "flags":
            output.flags = 1
        else:
            output.size = 64 * 1024 + 1
        return rc

    stub.library.wce_native_asr_poll = _FakeFunction(malformed_poll)
    client = _asr_client(stub)
    client._native_asr_handles.add(73)

    with pytest.raises(NativeCoreProtocolError, match="invalid owned buffer"):
        client.poll_native_asr(73)

    assert len(stub.releases) == 1


def test_native_asr_status_rejects_non_canonical_fixed_utf8() -> None:
    stub = _AsrStub()

    def malformed_status(_client: Any, options_pointer: Any, status_pointer: Any) -> int:
        rc = stub._get_status(_client, options_pointer, status_pointer)
        status = _dereference(status_pointer, native._WceNativeAsrStatus)
        _write_fixed_utf8(status, "actual_wechat_version", b"4.1\0garbage")
        return rc

    stub.library.wce_native_asr_get_status = _FakeFunction(malformed_status)
    client = _asr_client(stub)

    with pytest.raises(NativeCoreProtocolError, match="actual_wechat_version"):
        client.get_native_asr_status("wxid_example", Path.cwd().resolve())


@pytest.mark.parametrize(
    ("account", "directory", "conversation", "server_id", "local_id"),
    [
        ("wxid\0bad", Path.cwd().resolve(), "friend", 1, 0),
        ("wxid", Path("relative"), "friend", 1, 0),
        ("wxid", Path.cwd().resolve(), "friend\0bad", 1, 0),
        ("wxid", Path.cwd().resolve(), "friend", 0, 0),
        ("wxid", Path.cwd().resolve(), "friend", 1, -1),
    ],
)
def test_native_asr_begin_validates_utf8_paths_and_integer_ranges(
    account: str,
    directory: Path,
    conversation: str,
    server_id: int,
    local_id: int,
) -> None:
    client = _asr_client(_AsrStub())

    with pytest.raises(ValueError):
        client.begin_native_asr(
            account,
            directory,
            conversation,
            server_id,
            local_id,
        )
