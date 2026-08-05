from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import struct
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum, IntFlag
from pathlib import Path
from typing import Any, Callable


WCE_CLIENT_ABI_VERSION = 1
WCE_PROTOCOL_VERSION = 2

ENV_NATIVE_CORE_MODE = "WECHAT_TOOL_NATIVE_CORE_MODE"
ENV_NATIVE_CORE_LIBRARY = "WECHAT_TOOL_NATIVE_CORE_LIBRARY"
ENV_NATIVE_CORE_ENDPOINT = "WECHAT_TOOL_NATIVE_CORE_ENDPOINT"
ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD = (
    "WECHAT_TOOL_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD"
)
ENV_NATIVE_CORE_ALLOW_STAGING_BUILD = (
    "WECHAT_TOOL_NATIVE_CORE_ALLOW_STAGING_BUILD_FOR_TESTS"
)
ENV_SOURCE_NATIVE_CORE_DIR = "WCE_NATIVE_CORE_SOURCE_DIR"

_NATIVE_CORE_BUILD_MANIFEST_NAME = "wechatdb_native_build.json"
_NATIVE_CORE_BUILD_MANIFEST_MAX_BYTES = 16 * 1024
_NATIVE_CORE_BUILD_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
_NATIVE_CORE_NON_PRODUCTION_BUILD_ID_PATTERN = re.compile(
    r"(^|[._-])(dev|debug|test|local|snapshot|staging)([._-]|$)", re.IGNORECASE
)
_NATIVE_CORE_STAGING_BUILD_ID_PATTERN = re.compile(r"staging-security-[0-9a-f]{32}")
_NATIVE_CORE_DISTRIBUTION_MODES = frozenset({"public", "controlled"})
_NATIVE_CORE_DISTRIBUTION_CAPSULE_FIELDS = frozenset(
    {
        "schemaVersion",
        "artifactId",
        "artifactSha256",
        "authenticodeSignerSha256",
        "distributionTicket",
    }
)
_NATIVE_CORE_DISTRIBUTION_TICKET_PATTERN = re.compile(
    r"wct1\.([0-9a-f]{32})\.([A-Za-z0-9_-]{43,128})"
)
_NATIVE_CORE_BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60
_MAX_ENCRYPTED_EXPORT_PLAINTEXT_SIZE = 256 * 1024 * 1024 * 1024
_ENV_NATIVE_CORE_BROKER = "WECHAT_TOOL_NATIVE_CORE_BROKER"
_ENV_NATIVE_CORE_TRUST_KEY = "WECHAT_TOOL_NATIVE_CORE_TRUST_KEY_PATH"
_LEGACY_WCDB_ENVIRONMENT = (
    "WECHAT_TOOL_WCDB_API_DLL_PATH",
    "WECHAT_TOOL_WCDB_DLL_DIR",
    "WECHAT_TOOL_WCDB_RESOURCE_PATHS",
    "WECHAT_TOOL_WCDB_SIDECAR",
    "WECHAT_TOOL_WCDB_SIDECAR_HOST",
    "WECHAT_TOOL_WCDB_SIDECAR_PORT",
    "WECHAT_TOOL_WCDB_SIDECAR_TOKEN",
    "WECHAT_TOOL_WCDB_SIDECAR_URL",
)


class NativeCoreMode(str, Enum):
    REQUIRED = "required"


class NativeCoreStatus(IntEnum):
    OK = 0
    INVALID_ARGUMENT = -1
    UNAVAILABLE = -2
    PROTOCOL = -3
    IO = -4
    LICENSE_REQUIRED = -5
    LEASE_INVALID = -6
    LEASE_EXPIRED = -7
    FEATURE_DENIED = -8
    BUILD_MISMATCH = -9
    DEVICE_MISMATCH = -10
    TAMPER_DETECTED = -11
    INTERNAL = -12
    NOT_FOUND = -13
    BUSY = -14
    DATABASE = -15
    LIMIT = -16
    UNSUPPORTED = -17
    TIMEOUT = -18


class NativeCoreFeature(IntFlag):
    DATABASE_READ = 1 << 0
    EXPORT = 1 << 1
    MEDIA_DECRYPT = 1 << 2


_NATIVE_CORE_OFFLINE_BOOTSTRAP_FEATURES = (
    NativeCoreFeature.DATABASE_READ | NativeCoreFeature.EXPORT
)


class NativeCoreDatabaseKeyMode(IntEnum):
    AUTO = 0
    PASSPHRASE = 1
    RAW = 2
    PLAINTEXT = 3


class NativeCoreDatabaseAccess(IntEnum):
    READ_ONLY = 0


class NativeCoreLicenseState(IntEnum):
    UNLICENSED = 0
    ACTIVE = 1
    EXPIRED = 2
    TAMPERED = 3
    BUILD_ACTIVE = 4


class NativeCoreDeviceAssurance(IntEnum):
    EPHEMERAL = 0
    SOFTWARE = 1
    HARDWARE = 2


class NativeCoreError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NativeCoreUnavailableError(NativeCoreError):
    """The optional native runtime is absent or its broker cannot be reached."""


class NativeCoreComponentMissingError(NativeCoreUnavailableError):
    """A required native runtime component is missing."""


class NativeCoreProtocolError(NativeCoreError):
    """The loaded library does not implement the expected stable ABI."""


class NativeCorePolicyError(NativeCoreError):
    """A signed licensing or integrity policy rejected the operation."""


class _WceClientConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("endpoint_utf8", ctypes.c_char_p),
        ("connect_timeout_ms", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class _WceRuntimeStatus(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("protocol_version", ctypes.c_uint32),
        ("broker_process_id", ctypes.c_uint32),
        ("license_state", ctypes.c_uint32),
        ("device_assurance", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("lease_expires_unix", ctypes.c_uint64),
        ("feature_bits", ctypes.c_uint64),
        ("build_id", ctypes.c_uint8 * 32),
        ("device_id", ctypes.c_uint8 * 32),
        ("startup_nonce", ctypes.c_uint8 * 32),
    ]


class _WceLicenseChallengeProof(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("device_assurance", ctypes.c_uint32),
        ("requested_features", ctypes.c_uint64),
        ("build_id", ctypes.c_uint8 * 32),
        ("device_id", ctypes.c_uint8 * 32),
        ("startup_nonce", ctypes.c_uint8 * 32),
        ("device_public_key", ctypes.c_uint8 * 64),
        ("signature", ctypes.c_uint8 * 64),
    ]


class _WceDatabaseOpenOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("key_mode", ctypes.c_uint32),
        ("path_utf8", ctypes.c_char_p),
        ("key", ctypes.POINTER(ctypes.c_uint8)),
        ("key_size", ctypes.c_size_t),
        ("operation_nonce", ctypes.c_uint64),
        ("busy_timeout_ms", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("access", ctypes.c_uint32),
        ("reserved2", ctypes.c_uint32),
    ]


class _WceQueryOpenOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("database_handle", ctypes.c_uint64),
        ("sql_utf8", ctypes.c_char_p),
        ("operation_nonce", ctypes.c_uint64),
    ]


class _WceQueryFetchOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("max_rows", ctypes.c_uint32),
        ("max_bytes", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("query_handle", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
    ]


class _WceOwnedBuffer(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("size", ctypes.c_size_t),
    ]


class _WceExportBeginOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("manifest_format", ctypes.c_uint32),
        ("export_id_utf8", ctypes.c_char_p),
        ("expected_manifest_size", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
    ]


class _WceExportWriteOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("export_handle", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("size", ctypes.c_size_t),
    ]


class _WceExportFinishOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("export_handle", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
    ]


class _WceExportEncryptBeginOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("chunk_size", ctypes.c_uint32),
        ("export_id_utf8", ctypes.c_char_p),
        ("content_key", ctypes.POINTER(ctypes.c_uint8)),
        ("content_key_size", ctypes.c_size_t),
        ("plaintext_size", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
    ]


class _WceExportEncryptWriteOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("export_handle", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("size", ctypes.c_size_t),
    ]


class _WceExportDecryptBeginOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("header", ctypes.POINTER(ctypes.c_uint8)),
        ("header_size", ctypes.c_size_t),
        ("content_key", ctypes.POINTER(ctypes.c_uint8)),
        ("content_key_size", ctypes.c_size_t),
        ("operation_nonce", ctypes.c_uint64),
    ]


class _WceExportDecryptInfo(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("chunk_size", ctypes.c_uint32),
        ("plaintext_size", ctypes.c_uint64),
        ("chunk_count", ctypes.c_uint64),
        ("header_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]


class _WceExportDecryptWriteOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("export_handle", ctypes.c_uint64),
        ("operation_nonce", ctypes.c_uint64),
        ("record", ctypes.POINTER(ctypes.c_uint8)),
        ("record_size", ctypes.c_size_t),
    ]


class _WceExportVerifyOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("envelope", ctypes.POINTER(ctypes.c_uint8)),
        ("envelope_size", ctypes.c_size_t),
        ("manifest", ctypes.POINTER(ctypes.c_uint8)),
        ("manifest_size", ctypes.c_size_t),
    ]


class _WceExportVerifyResult(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("manifest_format", ctypes.c_uint32),
        ("sealed_at_unix", ctypes.c_uint64),
        ("lease_expires_unix", ctypes.c_uint64),
        ("feature_bits", ctypes.c_uint64),
        ("manifest_sha256", ctypes.c_uint8 * 32),
        ("build_id", ctypes.c_uint8 * 32),
        ("device_id", ctypes.c_uint8 * 32),
        ("export_id_size", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("export_id_utf8", ctypes.c_char * 129),
    ]


@dataclass(frozen=True)
class NativeCoreRuntimeStatus:
    protocol_version: int
    broker_process_id: int
    license_state: NativeCoreLicenseState
    device_assurance: NativeCoreDeviceAssurance
    lease_expires_unix: int
    feature_bits: NativeCoreFeature
    build_id: bytes = field(repr=False)
    device_id: bytes = field(repr=False)
    startup_nonce: bytes = field(repr=False)


@dataclass(frozen=True)
class NativeCoreDeviceProof:
    device_assurance: NativeCoreDeviceAssurance
    requested_features: NativeCoreFeature
    build_id: bytes = field(repr=False)
    device_id: bytes = field(repr=False)
    startup_nonce: bytes = field(repr=False)
    device_public_key: bytes = field(repr=False)
    signature: bytes = field(repr=False)


@dataclass(frozen=True)
class NativeCoreBuildManifest:
    build_id: str
    development_build: bool
    code_signature_enforced: bool
    root_public_key_compiled: bool
    test_hooks_enabled: bool
    staging_pinned_signer_trust: bool
    windows_client_signer_sha256: bytes = field(repr=False)
    offline_bootstrap_feature_bits: NativeCoreFeature
    offline_export_seal_format: str
    build_issued_at_unix: int = 0
    build_expires_at_unix: int = 0
    distribution_mode: str = "public"
    distribution_capsule: str | None = field(default=None, repr=False)
    platform: str = "windows"
    macos_client_signer_sha256: bytes = field(default=b"\0" * 32, repr=False)
    macos_broker_signer_sha256: bytes = field(default=b"\0" * 32, repr=False)
    macos_host_signer_sha256: bytes = field(default=b"\0" * 32, repr=False)
    macos_private_root_sha256: bytes = field(default=b"\0" * 32, repr=False)
    macos_client_signing_identifier: str = ""
    macos_broker_signing_identifier: str = ""
    macos_host_signing_identifier: str = ""
    source_runtime: bool = False
    macos_host_verification: str = ""

    @property
    def client_signer_sha256(self) -> bytes:
        if self.platform == "macos":
            return self.macos_client_signer_sha256
        return self.windows_client_signer_sha256


NativeCoreCell = None | int | float | str | bytes


@dataclass(frozen=True)
class NativeCoreQueryPage:
    columns: tuple[str, ...]
    rows: tuple[tuple[NativeCoreCell, ...], ...]
    has_more: bool

    def records(self) -> tuple[dict[str, NativeCoreCell], ...]:
        if len(set(self.columns)) != len(self.columns):
            raise NativeCoreProtocolError(
                "wechatdb query contains duplicate column names; use rows and columns directly."
            )
        return tuple(dict(zip(self.columns, row, strict=True)) for row in self.rows)


@dataclass(frozen=True)
class NativeCoreVerifiedExportSeal:
    export_id: str
    manifest_format: int
    sealed_at_unix: int
    lease_expires_unix: int
    feature_bits: NativeCoreFeature
    manifest_sha256: bytes
    build_id: bytes
    device_id: bytes


@dataclass(frozen=True)
class NativeCoreEncryptedExportHeader:
    export_id: str
    plaintext_size: int
    chunk_size: int
    chunk_count: int
    salt: bytes = field(repr=False)
    encoded: bytes = field(repr=False)


def parse_native_encrypted_export_header(
    payload: bytes,
    *,
    expected_export_id: str | None = None,
    expected_plaintext_size: int | None = None,
) -> NativeCoreEncryptedExportHeader:
    raw = bytes(payload)
    if len(raw) < 65 or len(raw) > 192:
        raise NativeCoreProtocolError("wechatdb encrypted export header has an invalid size.")
    (
        magic,
        version,
        algorithm,
        header_size,
        chunk_size,
        plaintext_size,
        chunk_count,
        export_id_size,
        reserved,
        salt,
    ) = struct.unpack_from("<4sHHIIQQII24s", raw, 0)
    if (
        magic != b"WEC1"
        or version != 1
        or algorithm != 1
        or header_size != len(raw)
        or header_size != 64 + export_id_size
        or not 1 <= export_id_size <= 128
        or reserved != 0
        or not 64 * 1024 <= chunk_size <= 768 * 1024
        or plaintext_size <= 0
        or plaintext_size > _MAX_ENCRYPTED_EXPORT_PLAINTEXT_SIZE
    ):
        raise NativeCoreProtocolError("wechatdb encrypted export header is invalid.")
    expected_chunks = (plaintext_size + chunk_size - 1) // chunk_size
    if chunk_count != expected_chunks:
        raise NativeCoreProtocolError("wechatdb encrypted export chunk count is invalid.")
    try:
        export_id = raw[64:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NativeCoreProtocolError("wechatdb encrypted export id is not UTF-8.") from exc
    if not export_id or any(ord(value) < 0x20 or ord(value) == 0x7F for value in export_id):
        raise NativeCoreProtocolError("wechatdb encrypted export id contains control characters.")
    if expected_export_id is not None and export_id != expected_export_id:
        raise NativeCoreProtocolError("wechatdb encrypted export id does not match the request.")
    if expected_plaintext_size is not None and plaintext_size != int(expected_plaintext_size):
        raise NativeCoreProtocolError("wechatdb encrypted export size does not match the request.")
    return NativeCoreEncryptedExportHeader(
        export_id=export_id,
        plaintext_size=int(plaintext_size),
        chunk_size=int(chunk_size),
        chunk_count=int(chunk_count),
        salt=bytes(salt),
        encoded=raw,
    )


class _RowsetReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = memoryview(payload)
        self._offset = 0

    @property
    def remaining(self) -> int:
        return len(self._payload) - self._offset

    def take(self, size: int) -> memoryview:
        if size < 0 or size > self.remaining:
            raise NativeCoreProtocolError("wechatdb query page is truncated.")
        start = self._offset
        self._offset += size
        return self._payload[start : start + size]

    def u8(self) -> int:
        return int(self.take(1)[0])

    def u16(self) -> int:
        return int.from_bytes(self.take(2), "little")

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "little")

    def sized(self) -> bytes:
        return bytes(self.take(self.u32()))


def parse_native_query_page(payload: bytes, *, has_more: bool) -> NativeCoreQueryPage:
    raw = bytes(payload)
    if len(raw) < 16 or len(raw) > 768 * 1024:
        raise NativeCoreProtocolError("wechatdb query page has an invalid size.")
    reader = _RowsetReader(raw)
    if bytes(reader.take(4)) != b"WQR1" or reader.u16() != 1 or reader.u16() != 0:
        raise NativeCoreProtocolError("wechatdb query page has an invalid WQR1 header.")
    column_count = reader.u32()
    row_count = reader.u32()
    if not 1 <= column_count <= 256 or row_count > 4096:
        raise NativeCoreProtocolError("wechatdb query page exceeds row or column limits.")

    columns: list[str] = []
    for _ in range(column_count):
        encoded = reader.sized()
        if len(encoded) > 4096:
            raise NativeCoreProtocolError("wechatdb query column name is too large.")
        try:
            columns.append(encoded.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise NativeCoreProtocolError("wechatdb query column name is not UTF-8.") from exc

    rows: list[tuple[NativeCoreCell, ...]] = []
    for _ in range(row_count):
        row: list[NativeCoreCell] = []
        for _ in range(column_count):
            cell_type = reader.u8()
            if cell_type == 0:
                value: NativeCoreCell = None
            elif cell_type == 1:
                value = int.from_bytes(reader.take(8), "little", signed=True)
            elif cell_type == 2:
                value = struct.unpack("<d", reader.take(8))[0]
            elif cell_type in {3, 4}:
                encoded = reader.sized()
                if cell_type == 4:
                    value = encoded
                else:
                    try:
                        value = encoded.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise NativeCoreProtocolError("wechatdb query text cell is not UTF-8.") from exc
            else:
                raise NativeCoreProtocolError(
                    f"wechatdb query page contains unknown cell type {cell_type}."
                )
            row.append(value)
        rows.append(tuple(row))
    if reader.remaining:
        raise NativeCoreProtocolError("wechatdb query page contains trailing data.")
    return NativeCoreQueryPage(tuple(columns), tuple(rows), bool(has_more))


_POLICY_STATUSES = {
    NativeCoreStatus.LICENSE_REQUIRED,
    NativeCoreStatus.LEASE_INVALID,
    NativeCoreStatus.LEASE_EXPIRED,
    NativeCoreStatus.FEATURE_DENIED,
    NativeCoreStatus.BUILD_MISMATCH,
    NativeCoreStatus.DEVICE_MISMATCH,
    NativeCoreStatus.TAMPER_DETECTED,
}
_UNAVAILABLE_STATUSES = {
    NativeCoreStatus.UNAVAILABLE,
    NativeCoreStatus.IO,
    NativeCoreStatus.TIMEOUT,
}


def native_core_mode() -> NativeCoreMode:
    raw = str(os.environ.get(ENV_NATIVE_CORE_MODE, "") or "").strip().lower()
    if raw in {"", NativeCoreMode.REQUIRED.value}:
        return NativeCoreMode.REQUIRED
    raise NativeCoreProtocolError(
        f"{ENV_NATIVE_CORE_MODE} must be required after native-core migration."
    )


def _decode_distribution_capsule_digest(value: object, *, field_name: str) -> bytes:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None
    ):
        raise NativeCoreProtocolError(
            f"wechatdb native distribution capsule contains an invalid {field_name}."
        )
    try:
        decoded = base64.b64decode(
            value + ("=" * (-len(value) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise NativeCoreProtocolError(
            f"wechatdb native distribution capsule contains an invalid {field_name}."
        ) from exc
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != 32 or not any(decoded) or canonical != value:
        raise NativeCoreProtocolError(
            f"wechatdb native distribution capsule contains an invalid {field_name}."
        )
    return decoded


def _sha256_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise NativeCoreProtocolError(
            f"Cannot hash wechatdb native client component: {path}"
        ) from exc
    return digest.digest()


def _validate_distribution_capsule(
    value: object,
    *,
    component_path: Path,
    client_signer_sha256: bytes,
    verify_component_digest: bool,
) -> str:
    if (
        not isinstance(value, str)
        or not 32 <= len(value) <= 2048
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule is malformed."
        )
    try:
        raw = base64.b64decode(
            value + ("=" * (-len(value) % 4)),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as exc:
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule is malformed."
        ) from exc

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for key, item in pairs:
            if key in parsed:
                raise ValueError(f"duplicate JSON field: {key}")
            parsed[key] = item
        return parsed

    def reject_constant(constant: str) -> object:
        raise ValueError(f"invalid JSON constant: {constant}")

    try:
        capsule = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule is malformed."
        ) from exc
    if (
        not isinstance(capsule, dict)
        or frozenset(capsule) != _NATIVE_CORE_DISTRIBUTION_CAPSULE_FIELDS
        or type(capsule.get("schemaVersion")) is not int
        or capsule.get("schemaVersion") != 1
    ):
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule has an invalid structure."
        )

    artifact_id_text = capsule.get("artifactId")
    if not isinstance(artifact_id_text, str):
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule contains an invalid artifactId."
        )
    try:
        artifact_id = uuid.UUID(artifact_id_text)
    except (AttributeError, ValueError) as exc:
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule contains an invalid artifactId."
        ) from exc
    if str(artifact_id) != artifact_id_text:
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule contains a non-canonical artifactId."
        )

    artifact_sha256 = _decode_distribution_capsule_digest(
        capsule.get("artifactSha256"),
        field_name="artifactSha256",
    )
    signer_sha256 = _decode_distribution_capsule_digest(
        capsule.get("authenticodeSignerSha256"),
        field_name="authenticodeSignerSha256",
    )
    distribution_ticket = capsule.get("distributionTicket")
    if not isinstance(distribution_ticket, str):
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule contains an invalid distributionTicket."
        )
    ticket_match = _NATIVE_CORE_DISTRIBUTION_TICKET_PATTERN.fullmatch(
        distribution_ticket
    )
    if ticket_match is None or bytes.fromhex(ticket_match.group(1)) != artifact_id.bytes:
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule ticket does not match its artifactId."
        )

    canonical_raw = json.dumps(
        capsule,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    canonical = base64.urlsafe_b64encode(canonical_raw).decode("ascii").rstrip("=")
    if not hmac.compare_digest(canonical, value):
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule is not canonical."
        )
    if verify_component_digest:
        actual_artifact_sha256 = _sha256_file(component_path)
        if not hmac.compare_digest(artifact_sha256, actual_artifact_sha256):
            raise NativeCoreProtocolError(
                "wechatdb native distribution capsule does not match the client artifact SHA-256."
            )
    if not hmac.compare_digest(signer_sha256, client_signer_sha256):
        raise NativeCoreProtocolError(
            "wechatdb native distribution capsule does not match the client signer."
        )
    return value


def _load_native_core_build_manifest(
    component_path: Path,
    *,
    verify_distribution_artifact: bool = True,
) -> NativeCoreBuildManifest:
    manifest_path = Path(component_path).with_name(_NATIVE_CORE_BUILD_MANIFEST_NAME)
    try:
        size = manifest_path.stat().st_size
        if size <= 0 or size > _NATIVE_CORE_BUILD_MANIFEST_MAX_BYTES:
            raise NativeCoreProtocolError(
                f"wechatdb native build manifest has an invalid size: {manifest_path}"
            )
        raw = manifest_path.read_text(encoding="utf-8")
    except NativeCoreProtocolError:
        raise
    except (OSError, UnicodeError) as exc:
        raise NativeCoreProtocolError(
            f"Cannot read wechatdb native build manifest: {manifest_path}"
        ) from exc

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise NativeCoreProtocolError(
            f"wechatdb native build manifest is not valid JSON: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise NativeCoreProtocolError("wechatdb native build manifest must be a JSON object.")

    schema_version = payload.get("schemaVersion")
    build_id = payload.get("buildId")
    build_issued_at_unix_value = payload.get("buildIssuedAtUnix")
    build_expires_at_unix_value = payload.get("buildExpiresAtUnix")
    development_build = payload.get("developmentBuild")
    code_signature_enforced = payload.get("codeSignatureEnforced")
    root_public_key_compiled = payload.get("rootPublicKeyCompiled")
    test_hooks_enabled = payload.get("testHooksEnabled")
    staging_pinned_signer_trust = payload.get("stagingPinnedSignerTrust")
    manifest_platform = "macos" if schema_version == 3 else "windows"
    windows_client_signer_sha256 = payload.get("windowsClientSignerSha256")
    offline_bootstrap_feature_bits_value = payload.get(
        "offlineBootstrapFeatureBits"
    )
    offline_export_seal_format = payload.get("offlineExportSealFormat")
    distribution_mode_value = payload.get("distributionMode")
    distribution_capsule_value = payload.get("distributionCapsule")
    if type(schema_version) is not int or schema_version not in {2, 3}:
        raise NativeCoreProtocolError(
            "wechatdb native build manifest has an unsupported schemaVersion."
        )
    if schema_version == 3 and payload.get("platform") != "macos":
        raise NativeCoreProtocolError(
            "wechatdb native schemaVersion 3 requires platform macos."
        )
    if schema_version == 2 and "platform" in payload:
        raise NativeCoreProtocolError(
            "wechatdb native schemaVersion 2 must not declare a platform."
        )
    source_runtime_fields = {
        name for name in ("sourceRuntime", "macosHostVerification") if name in payload
    }
    source_runtime = False
    macos_host_verification = ""
    if schema_version == 2 and source_runtime_fields:
        raise NativeCoreProtocolError(
            "Windows wechatdb native manifests must not declare macOS source-runtime fields."
        )
    if schema_version == 3 and source_runtime_fields:
        if source_runtime_fields != {"sourceRuntime", "macosHostVerification"}:
            raise NativeCoreProtocolError(
                "macOS source-runtime fields must be declared together."
            )
        if (
            payload.get("sourceRuntime") is not True
            or payload.get("macosHostVerification") != "same-user-direct-parent"
        ):
            raise NativeCoreProtocolError(
                "macOS source-runtime host verification policy is invalid."
            )
        source_runtime = True
        macos_host_verification = "same-user-direct-parent"
    if (
        not isinstance(build_id, str)
        or not _NATIVE_CORE_BUILD_ID_PATTERN.fullmatch(build_id)
    ):
        raise NativeCoreProtocolError(
            "wechatdb native build manifest contains an invalid buildId."
        )
    if any(
        type(value) is not bool
        for value in (
            development_build,
            code_signature_enforced,
            root_public_key_compiled,
            test_hooks_enabled,
            staging_pinned_signer_trust,
        )
    ):
        raise NativeCoreProtocolError(
            "wechatdb native build manifest security fields must be booleans."
        )
    if source_runtime and (
        development_build
        or not code_signature_enforced
        or not root_public_key_compiled
        or test_hooks_enabled
        or staging_pinned_signer_trust
    ):
        raise NativeCoreProtocolError(
            "macOS source-runtime manifests must retain the production security profile."
        )
    macos_client_signer_digest = bytes(32)
    macos_broker_signer_digest = bytes(32)
    macos_host_signer_digest = bytes(32)
    macos_private_root_digest = bytes(32)
    macos_client_identifier = ""
    macos_broker_identifier = ""
    macos_host_identifier = ""
    if manifest_platform == "windows":
        if development_build and windows_client_signer_sha256 in {None, ""}:
            signer_digest = bytes(32)
        elif (
            not isinstance(windows_client_signer_sha256, str)
            or not re.fullmatch(r"[0-9A-Fa-f]{64}", windows_client_signer_sha256)
        ):
            raise NativeCoreProtocolError(
                "wechatdb native build manifest contains an invalid windowsClientSignerSha256."
            )
        else:
            signer_digest = bytes.fromhex(windows_client_signer_sha256)
        if not development_build and not any(signer_digest):
            raise NativeCoreProtocolError(
                "wechatdb native build manifest contains an invalid windowsClientSignerSha256."
            )
    else:
        signer_digest = bytes(32)
        macos_identifiers = (
            payload.get("macosClientSigningIdentifier"),
            payload.get("macosBrokerSigningIdentifier"),
            payload.get("macosHostSigningIdentifier"),
        )
        if (
            any(
                not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z0-9.-]+", value) is None
                for value in macos_identifiers
            )
            or len(set(macos_identifiers)) != 3
        ):
            raise NativeCoreProtocolError(
                "wechatdb native build manifest contains invalid macOS signing identifiers."
            )
        macos_client_identifier, macos_broker_identifier, macos_host_identifier = (
            macos_identifiers
        )
        macos_pin_values = (
            payload.get("macosClientSignerSha256"),
            payload.get("macosBrokerSignerSha256"),
            payload.get("macosHostSignerSha256"),
            payload.get("macosPrivateRootSha256"),
        )
        if any(
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in macos_pin_values
        ):
            raise NativeCoreProtocolError(
                "wechatdb native build manifest contains invalid macOS signer pins."
            )
        (
            macos_client_signer_digest,
            macos_broker_signer_digest,
            macos_host_signer_digest,
            macos_private_root_digest,
        ) = tuple(bytes.fromhex(value) for value in macos_pin_values)
        macos_pin_digests = (
            macos_client_signer_digest,
            macos_broker_signer_digest,
            macos_host_signer_digest,
            macos_private_root_digest,
        )
        if development_build:
            if any(any(value) for value in macos_pin_digests):
                raise NativeCoreProtocolError(
                    "Development macOS native builds must not carry production signer pins."
                )
            expected_trust_mode = "development"
            expected_revocation = "not-applicable"
        else:
            if any(not any(value) for value in macos_pin_digests) or len(
                set(macos_pin_digests)
            ) != 4:
                raise NativeCoreProtocolError(
                    "Production macOS signer and root pins must be non-zero and distinct."
                )
            expected_trust_mode = "private-pki"
            expected_revocation = "build-and-lease-only"
        if (
            payload.get("macosSigningMode") != "self-signed"
            or payload.get("macosSignerTrustMode") != expected_trust_mode
            or payload.get("macosPrivatePkiLeafRevocation") != expected_revocation
        ):
            raise NativeCoreProtocolError(
                "wechatdb native build manifest contains an invalid macOS private-PKI policy."
            )
    if (
        type(offline_bootstrap_feature_bits_value) is not int
        or offline_bootstrap_feature_bits_value < 0
        or not isinstance(offline_export_seal_format, str)
    ):
        raise NativeCoreProtocolError(
            "wechatdb native build manifest contains invalid offline bootstrap fields."
        )
    offline_bootstrap_feature_bits = NativeCoreFeature(
        offline_bootstrap_feature_bits_value
    )
    if development_build:
        if (
            offline_bootstrap_feature_bits != NativeCoreFeature(0)
            or offline_export_seal_format != "none"
        ):
            raise NativeCoreProtocolError(
                "Development wechatdb native builds must declare offline bootstrap "
                "features 0 and export seal format none."
            )
    elif (
        offline_bootstrap_feature_bits != _NATIVE_CORE_OFFLINE_BOOTSTRAP_FEATURES
        or offline_export_seal_format != "WES2"
    ):
        raise NativeCoreProtocolError(
            "Production and staging wechatdb native builds must declare offline "
            "bootstrap features 3 and export seal format WES2."
        )
    formal_production = not development_build and not staging_pinned_signer_trust
    if formal_production:
        if (
            type(build_issued_at_unix_value) is not int
            or type(build_expires_at_unix_value) is not int
            or build_issued_at_unix_value <= 0
            or build_expires_at_unix_value
            != build_issued_at_unix_value + _NATIVE_CORE_BUILD_LIFETIME_SECONDS
        ):
            raise NativeCoreProtocolError(
                "Production wechatdb native build manifest must contain an exact "
                "45-day build validity window."
            )
        build_issued_at_unix = build_issued_at_unix_value
        build_expires_at_unix = build_expires_at_unix_value
        if int(time.time()) >= build_expires_at_unix:
            raise NativeCorePolicyError(
                "This wechatdb native build has reached its fixed expiration time."
            )
    else:
        if build_issued_at_unix_value is None and build_expires_at_unix_value is None:
            build_issued_at_unix = 0
            build_expires_at_unix = 0
        elif (
            type(build_issued_at_unix_value) is not int
            or type(build_expires_at_unix_value) is not int
            or build_issued_at_unix_value < 0
            or build_expires_at_unix_value < 0
            or (
                (build_issued_at_unix_value == 0) != (build_expires_at_unix_value == 0)
            )
            or (
                build_issued_at_unix_value > 0
                and build_expires_at_unix_value
                != build_issued_at_unix_value + _NATIVE_CORE_BUILD_LIFETIME_SECONDS
            )
        ):
            raise NativeCoreProtocolError(
                "Non-production wechatdb native build manifest contains an invalid "
                "build validity window."
            )
        else:
            build_issued_at_unix = build_issued_at_unix_value
            build_expires_at_unix = build_expires_at_unix_value
    if "distributionMode" not in payload:
        distribution_mode = "public"
    elif (
        not isinstance(distribution_mode_value, str)
        or distribution_mode_value not in _NATIVE_CORE_DISTRIBUTION_MODES
    ):
        raise NativeCoreProtocolError(
            "wechatdb native build manifest contains an invalid distributionMode."
        )
    else:
        distribution_mode = distribution_mode_value
    if distribution_mode == "public":
        if "distributionCapsule" in payload:
            raise NativeCoreProtocolError(
                "Public wechatdb native builds must not contain a distribution capsule."
            )
        distribution_capsule = None
    else:
        if "distributionCapsule" not in payload:
            raise NativeCoreProtocolError(
                "Controlled wechatdb native builds require a distribution capsule."
            )
        distribution_capsule = _validate_distribution_capsule(
            distribution_capsule_value,
            component_path=Path(component_path),
            client_signer_sha256=signer_digest,
            verify_component_digest=verify_distribution_artifact,
        )
    return NativeCoreBuildManifest(
        build_id=build_id,
        development_build=development_build,
        code_signature_enforced=code_signature_enforced,
        root_public_key_compiled=root_public_key_compiled,
        test_hooks_enabled=test_hooks_enabled,
        staging_pinned_signer_trust=staging_pinned_signer_trust,
        windows_client_signer_sha256=signer_digest,
        offline_bootstrap_feature_bits=offline_bootstrap_feature_bits,
        offline_export_seal_format=offline_export_seal_format,
        build_issued_at_unix=build_issued_at_unix,
        build_expires_at_unix=build_expires_at_unix,
        distribution_mode=distribution_mode,
        distribution_capsule=distribution_capsule,
        platform=manifest_platform,
        macos_client_signer_sha256=macos_client_signer_digest,
        macos_broker_signer_sha256=macos_broker_signer_digest,
        macos_host_signer_sha256=macos_host_signer_digest,
        macos_private_root_sha256=macos_private_root_digest,
        macos_client_signing_identifier=macos_client_identifier,
        macos_broker_signing_identifier=macos_broker_identifier,
        macos_host_signing_identifier=macos_host_identifier,
        source_runtime=source_runtime,
        macos_host_verification=macos_host_verification,
    )


def _required_native_core_build_manifest(
    component_path: Path,
    *,
    verify_distribution_artifact: bool = True,
) -> NativeCoreBuildManifest:
    native_core_mode()
    manifest = _load_native_core_build_manifest(
        component_path,
        verify_distribution_artifact=verify_distribution_artifact,
    )
    if not _manifest_matches_runtime_platform(manifest):
        raise NativeCoreProtocolError(
            "wechatdb native build manifest does not match the current platform."
        )
    frozen = bool(getattr(sys, "frozen", False))
    if manifest.platform == "macos":
        if (
            frozen
            and _is_production_native_core_build_manifest(manifest)
            and not manifest.source_runtime
        ):
            from .native_core_lease import validate_native_core_authorization_policy

            validate_native_core_authorization_policy(manifest)
            return manifest
        if not frozen and _is_source_public_native_core_build_manifest(manifest):
            from .native_core_lease import validate_native_core_authorization_policy

            validate_native_core_authorization_policy(manifest)
            return manifest
        if frozen and manifest.source_runtime:
            raise NativeCoreProtocolError(
                "Frozen WeChatDataAnalysis rejects the source-public macOS native core."
            )
        if not frozen:
            raise NativeCoreProtocolError(
                "Source WeChatDataAnalysis on macOS requires the exact restricted "
                "source-public native core."
            )
        raise NativeCoreProtocolError(
            "Frozen WeChatDataAnalysis requires a production wechatdb native core."
        )
    if _is_production_native_core_build_manifest(manifest):
        from .native_core_lease import validate_native_core_authorization_policy

        validate_native_core_authorization_policy(manifest)
        return manifest
    staging_enabled = (
        not getattr(sys, "frozen", False)
        and str(os.environ.get(ENV_NATIVE_CORE_ALLOW_STAGING_BUILD, "") or "").strip()
        == "1"
    )
    if staging_enabled and _is_staging_native_core_build_manifest(manifest):
        from .native_core_lease import validate_native_core_authorization_policy

        validate_native_core_authorization_policy(manifest)
        return manifest
    if getattr(sys, "frozen", False):
        raise NativeCoreProtocolError(
            "Frozen WeChatDataAnalysis requires a production wechatdb native core."
        )
    development_enabled = (
        str(os.environ.get(ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD, "") or "").strip()
        == "1"
    )
    if development_enabled and _is_development_native_core_build_manifest(manifest):
        from .native_core_lease import validate_native_core_authorization_policy

        validate_native_core_authorization_policy(manifest)
        return manifest
    raise NativeCoreProtocolError(
        "Source WeChatDataAnalysis requires the exact dev-local native core and "
        f"an explicit {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD}=1 "
        "entrypoint-controlled development lease."
    )


def _is_production_native_core_build_manifest(manifest: NativeCoreBuildManifest) -> bool:
    return (
        not manifest.development_build
        and manifest.code_signature_enforced
        and manifest.root_public_key_compiled
        and not manifest.test_hooks_enabled
        and not manifest.staging_pinned_signer_trust
        and len(manifest.client_signer_sha256) == 32
        and any(manifest.client_signer_sha256)
        and manifest.build_issued_at_unix > 0
        and manifest.build_expires_at_unix
        == manifest.build_issued_at_unix + _NATIVE_CORE_BUILD_LIFETIME_SECONDS
        and manifest.offline_bootstrap_feature_bits
        == _NATIVE_CORE_OFFLINE_BOOTSTRAP_FEATURES
        and manifest.offline_export_seal_format == "WES2"
        and not _NATIVE_CORE_NON_PRODUCTION_BUILD_ID_PATTERN.search(manifest.build_id)
    )


def _is_development_native_core_build_manifest(manifest: NativeCoreBuildManifest) -> bool:
    return (
        manifest.build_id == "dev-local"
        and manifest.development_build
        and not manifest.code_signature_enforced
        and not manifest.root_public_key_compiled
        and manifest.test_hooks_enabled
        and not manifest.staging_pinned_signer_trust
        and manifest.offline_bootstrap_feature_bits == NativeCoreFeature(0)
        and manifest.offline_export_seal_format == "none"
    )


def _is_staging_native_core_build_manifest(manifest: NativeCoreBuildManifest) -> bool:
    return (
        manifest.platform == "windows"
        and not manifest.development_build
        and manifest.code_signature_enforced
        and manifest.root_public_key_compiled
        and not manifest.test_hooks_enabled
        and manifest.staging_pinned_signer_trust
        and len(manifest.windows_client_signer_sha256) == 32
        and any(manifest.windows_client_signer_sha256)
        and manifest.offline_bootstrap_feature_bits
        == _NATIVE_CORE_OFFLINE_BOOTSTRAP_FEATURES
        and manifest.offline_export_seal_format == "WES2"
        and _NATIVE_CORE_STAGING_BUILD_ID_PATTERN.fullmatch(manifest.build_id) is not None
    )


def _is_source_public_native_core_build_manifest(
    manifest: NativeCoreBuildManifest,
) -> bool:
    return (
        manifest.platform == "macos"
        and manifest.source_runtime
        and manifest.macos_host_verification == "same-user-direct-parent"
        and _is_production_native_core_build_manifest(manifest)
    )


def _manifest_matches_runtime_platform(
    manifest: NativeCoreBuildManifest,
    runtime_platform: str | None = None,
) -> bool:
    current = sys.platform if runtime_platform is None else runtime_platform
    return (current.startswith("win") and manifest.platform == "windows") or (
        current == "darwin" and manifest.platform == "macos"
    )


def _verify_native_core_runtime_build_id(
    manifest: NativeCoreBuildManifest,
    status: NativeCoreRuntimeStatus,
) -> None:
    expected = hashlib.sha256(manifest.build_id.encode("utf-8")).digest()
    if not hmac.compare_digest(expected, status.build_id):
        raise NativeCoreProtocolError(
            "wechatdb native runtime build ID does not match its build manifest."
        )


def _verify_native_core_component_build_ids(
    client_build_id: bytes,
    status: NativeCoreRuntimeStatus,
) -> None:
    if len(client_build_id) != 32 or not hmac.compare_digest(
        client_build_id, status.build_id
    ):
        raise NativeCoreProtocolError(
            "wechatdb native client and broker build IDs do not match."
        )


def _native_library_name() -> str:
    if sys.platform.startswith("win"):
        return "wechatdb_client.dll"
    if sys.platform == "darwin":
        return "libwechatdb_client.dylib"
    raise NativeCoreComponentMissingError("wechatdb native core supports Windows and macOS only.")


def _candidate_library_paths() -> tuple[Path, ...]:
    file_name = _native_library_name()
    package_dir = Path(__file__).resolve().parent
    repo_root = package_dir.parents[1]
    arch = "arm64" if (platform.machine() or "").lower() in {"arm64", "aarch64"} else "x64"
    candidates: list[Path] = []

    explicit = str(os.environ.get(ENV_NATIVE_CORE_LIBRARY, "") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "native" / file_name)

    candidates.extend(
        (
            package_dir / "native" / file_name,
            package_dir / "native" / "macos" / arch / file_name,
            repo_root.parent / "wechatdb-native" / "build" / "windows-vs" / "Release" / file_name,
            repo_root.parent / "wechatdb-native" / "build" / "windows-vs" / "Debug" / file_name,
            repo_root.parent / "wechatdb-native" / "build" / "windows-msvc-debug" / file_name,
            repo_root.parent / "wechatdb-native" / "build" / "macos-arm64-debug" / file_name,
        )
    )

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(str(candidate.resolve(strict=False)))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(candidate)
    return tuple(result)


def resolve_native_core_library() -> Path:
    for candidate in _candidate_library_paths():
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    searched = ", ".join(str(path) for path in _candidate_library_paths())
    raise NativeCoreComponentMissingError(
        f"wechatdb native client library was not found; searched: {searched}"
    )


def _native_core_broker_name() -> str:
    if sys.platform.startswith("win"):
        return "wechatdb_broker.exe"
    if sys.platform == "darwin":
        return "wechatdb_broker"
    raise NativeCoreComponentMissingError(
        "wechatdb native broker supports Windows and macOS only."
    )


def _native_core_entrypoint_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "native"
    if sys.platform == "darwin":
        configured = str(os.environ.get(ENV_SOURCE_NATIVE_CORE_DIR, "") or "").strip()
        if configured:
            try:
                return Path(configured).expanduser().resolve(strict=False)
            except (OSError, RuntimeError, ValueError) as exc:
                raise NativeCoreComponentMissingError(
                    f"Configured macOS source native-core directory is invalid: {configured}"
                ) from exc
    return Path(__file__).resolve().parent / "native"


def _require_native_core_entrypoint_file(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        stat = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise NativeCoreComponentMissingError(
            f"Required wechatdb native component is missing: {path}"
        ) from exc
    if not resolved.is_file() or stat.st_size <= 0:
        raise NativeCoreComponentMissingError(
            f"Required wechatdb native component is invalid: {resolved}"
        )
    return resolved


def _same_native_core_path(value: str, expected: Path) -> bool:
    try:
        actual = Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    return os.path.normcase(os.fspath(actual)) == os.path.normcase(os.fspath(expected))


def _lock_native_core_component_environment(name: str, expected: Path) -> None:
    configured = str(os.environ.get(name, "") or "").strip()
    if configured and not _same_native_core_path(configured, expected):
        raise NativeCoreProtocolError(
            f"External {name} overrides are disabled after native-core migration."
        )
    os.environ[name] = os.fspath(expected)


def _clear_legacy_wcdb_environment() -> None:
    for name in _LEGACY_WCDB_ENVIRONMENT:
        os.environ.pop(name, None)


def configure_native_core_entrypoint() -> NativeCoreBuildManifest:
    """Validate and handshake the fixed native runtime before serving requests."""

    _clear_legacy_wcdb_environment()
    native_core_mode()
    os.environ[ENV_NATIVE_CORE_MODE] = NativeCoreMode.REQUIRED.value

    for name in (ENV_NATIVE_CORE_ENDPOINT, _ENV_NATIVE_CORE_TRUST_KEY):
        if str(os.environ.get(name, "") or "").strip():
            raise NativeCoreProtocolError(
                f"External {name} overrides are disabled after native-core migration."
            )

    native_directory = _native_core_entrypoint_directory()
    library_path = _require_native_core_entrypoint_file(
        native_directory / _native_library_name()
    )
    broker_path = _require_native_core_entrypoint_file(
        native_directory / _native_core_broker_name()
    )
    _require_native_core_entrypoint_file(
        native_directory / _NATIVE_CORE_BUILD_MANIFEST_NAME
    )

    manifest = _required_native_core_build_manifest(library_path)
    if not manifest.development_build:
        os.environ.pop(ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD, None)

    _lock_native_core_component_environment(ENV_NATIVE_CORE_LIBRARY, library_path)
    _lock_native_core_component_environment(_ENV_NATIVE_CORE_BROKER, broker_path)

    from . import native_core_broker

    try:
        native_core_broker.ensure_native_core_broker(export_only=True)
    finally:
        native_core_broker.stop_native_core_broker(_force=True)
    return manifest


def _load_library(path: Path) -> Any:
    try:
        # The public ABI is explicitly __cdecl on Windows, so CDLL is required.
        return ctypes.CDLL(str(path))
    except OSError as exc:
        raise NativeCoreUnavailableError(f"Cannot load wechatdb native client library: {path}") from exc


def _operation_nonce() -> int:
    nonce = 0
    while nonce == 0:
        nonce = secrets.randbits(64)
    return nonce


class NativeCoreClient:
    def __init__(
        self,
        *,
        library_path: Path | None = None,
        endpoint: str | None = None,
        connect_timeout_ms: int = 5000,
        _library_loader: Callable[[Path], Any] = _load_library,
    ) -> None:
        timeout = int(connect_timeout_ms)
        if timeout <= 0 or timeout > 120_000:
            raise ValueError("connect_timeout_ms must be between 1 and 120000")

        self._lock = threading.RLock()
        self._closed = False
        self._path = Path(library_path) if library_path is not None else resolve_native_core_library()
        build_manifest = _required_native_core_build_manifest(self._path)
        self._build_manifest = build_manifest
        self._library = _library_loader(self._path)
        self._configure_abi()

        actual_abi = int(self._library.wce_client_abi_version())
        if actual_abi != WCE_CLIENT_ABI_VERSION:
            raise NativeCoreProtocolError(
                f"wechatdb native client ABI mismatch: expected {WCE_CLIENT_ABI_VERSION}, got {actual_abi}."
            )
        client_build_id = (ctypes.c_uint8 * 32)()
        rc = int(self._library.wce_client_build_id(client_build_id))
        self._raise_for_status(rc, "read client build ID")
        self._client_build_id = bytes(client_build_id)

        endpoint_value = endpoint
        if endpoint_value is None:
            endpoint_value = str(os.environ.get(ENV_NATIVE_CORE_ENDPOINT, "") or "").strip() or None
        endpoint_bytes = endpoint_value.encode("utf-8") if endpoint_value else None
        config = _WceClientConfig(
            struct_size=ctypes.sizeof(_WceClientConfig),
            abi_version=WCE_CLIENT_ABI_VERSION,
            endpoint_utf8=endpoint_bytes,
            connect_timeout_ms=timeout,
            reserved=0,
        )
        handle = ctypes.c_void_p()
        rc = int(self._library.wce_client_create(ctypes.byref(config), ctypes.byref(handle)))
        self._raise_for_status(rc, "create client")
        if not handle.value:
            raise NativeCoreProtocolError("wechatdb native client returned an empty handle.")
        self._handle = handle
        self._database_handles: set[int] = set()
        self._query_handles: dict[int, int] = {}
        self._export_handles: set[int] = set()
        self._encrypted_export_handles: set[int] = set()
        self._decrypted_export_handles: set[int] = set()
        try:
            runtime_status = self.get_status()
            _verify_native_core_component_build_ids(
                self._client_build_id, runtime_status
            )
            if build_manifest is not None:
                _verify_native_core_runtime_build_id(build_manifest, runtime_status)
        except Exception:
            self.close()
            raise

    def _validate_required_build(self) -> None:
        manifest = _required_native_core_build_manifest(
            self._path,
            verify_distribution_artifact=False,
        )
        if (
            manifest.distribution_mode != self._build_manifest.distribution_mode
            or manifest.distribution_capsule
            != self._build_manifest.distribution_capsule
        ):
            raise NativeCoreProtocolError(
                "wechatdb native distribution identity changed after client initialization."
            )
        runtime_status = self.get_status()
        _verify_native_core_component_build_ids(
            self._client_build_id, runtime_status
        )
        if manifest is not None:
            _verify_native_core_runtime_build_id(manifest, runtime_status)

    @property
    def build_manifest(self) -> NativeCoreBuildManifest:
        return self._build_manifest

    def _configure_abi(self) -> None:
        lib = self._library
        required = (
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
        missing = [name for name in required if not hasattr(lib, name)]
        if missing:
            raise NativeCoreProtocolError(
                "wechatdb native client is missing ABI symbols: " + ", ".join(missing)
            )

        decrypt_symbols = (
            "wce_export_decrypt_begin",
            "wce_export_decrypt_write",
            "wce_export_decrypt_finish",
            "wce_export_decrypt_abort",
        )
        available_decrypt_symbols = tuple(
            name for name in decrypt_symbols if hasattr(lib, name)
        )
        if available_decrypt_symbols and len(available_decrypt_symbols) != len(
            decrypt_symbols
        ):
            missing_decrypt_symbols = (
                name for name in decrypt_symbols if name not in available_decrypt_symbols
            )
            raise NativeCoreProtocolError(
                "wechatdb native client has an incomplete WEC1 decryption ABI: "
                + ", ".join(missing_decrypt_symbols)
            )
        self._supports_export_decryption = bool(available_decrypt_symbols)
        self._supports_export_verification = hasattr(lib, "wce_export_verify_seal")
        if (
            self._build_manifest.root_public_key_compiled
            and not self._supports_export_verification
        ):
            raise NativeCoreProtocolError(
                "wechatdb production native client is missing the WES1/WES2 "
                "verification ABI."
            )

        lib.wce_client_abi_version.argtypes = []
        lib.wce_client_abi_version.restype = ctypes.c_uint32
        lib.wce_client_build_id.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
        lib.wce_client_build_id.restype = ctypes.c_int32
        lib.wce_client_create.argtypes = [ctypes.POINTER(_WceClientConfig), ctypes.POINTER(ctypes.c_void_p)]
        lib.wce_client_create.restype = ctypes.c_int32
        lib.wce_client_destroy.argtypes = [ctypes.c_void_p]
        lib.wce_client_destroy.restype = None
        lib.wce_client_get_status.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WceRuntimeStatus)]
        lib.wce_client_get_status.restype = ctypes.c_int32
        lib.wce_client_prove_license_challenge.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
            ctypes.c_uint64,
            ctypes.POINTER(_WceLicenseChallengeProof),
        ]
        lib.wce_client_prove_license_challenge.restype = ctypes.c_int32
        lib.wce_client_install_lease.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        lib.wce_client_install_lease.restype = ctypes.c_int32
        lib.wce_client_authorize.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64]
        lib.wce_client_authorize.restype = ctypes.c_int32
        lib.wce_database_open.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceDatabaseOpenOptions),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        lib.wce_database_open.restype = ctypes.c_int32
        lib.wce_database_close.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64]
        lib.wce_database_close.restype = ctypes.c_int32
        lib.wce_query_open.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceQueryOpenOptions),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        lib.wce_query_open.restype = ctypes.c_int32
        lib.wce_query_fetch.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceQueryFetchOptions),
            ctypes.POINTER(_WceOwnedBuffer),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        lib.wce_query_fetch.restype = ctypes.c_int32
        lib.wce_query_close.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64]
        lib.wce_query_close.restype = ctypes.c_int32
        lib.wce_export_begin.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceExportBeginOptions),
            ctypes.POINTER(ctypes.c_uint64),
        ]
        lib.wce_export_begin.restype = ctypes.c_int32
        lib.wce_export_write.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceExportWriteOptions),
        ]
        lib.wce_export_write.restype = ctypes.c_int32
        lib.wce_export_finish.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceExportFinishOptions),
            ctypes.POINTER(_WceOwnedBuffer),
        ]
        lib.wce_export_finish.restype = ctypes.c_int32
        lib.wce_export_abort.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64]
        lib.wce_export_abort.restype = ctypes.c_int32
        lib.wce_export_encrypt_begin.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceExportEncryptBeginOptions),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(_WceOwnedBuffer),
        ]
        lib.wce_export_encrypt_begin.restype = ctypes.c_int32
        lib.wce_export_encrypt_write.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_WceExportEncryptWriteOptions),
            ctypes.POINTER(_WceOwnedBuffer),
        ]
        lib.wce_export_encrypt_write.restype = ctypes.c_int32
        lib.wce_export_encrypt_finish.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        lib.wce_export_encrypt_finish.restype = ctypes.c_int32
        lib.wce_export_encrypt_abort.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        lib.wce_export_encrypt_abort.restype = ctypes.c_int32
        if self._supports_export_decryption:
            lib.wce_export_decrypt_begin.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_WceExportDecryptBeginOptions),
                ctypes.POINTER(ctypes.c_uint64),
                ctypes.POINTER(_WceExportDecryptInfo),
            ]
            lib.wce_export_decrypt_begin.restype = ctypes.c_int32
            lib.wce_export_decrypt_write.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_WceExportDecryptWriteOptions),
                ctypes.POINTER(_WceOwnedBuffer),
            ]
            lib.wce_export_decrypt_write.restype = ctypes.c_int32
            lib.wce_export_decrypt_finish.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint64,
                ctypes.c_uint64,
            ]
            lib.wce_export_decrypt_finish.restype = ctypes.c_int32
            lib.wce_export_decrypt_abort.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint64,
                ctypes.c_uint64,
            ]
            lib.wce_export_decrypt_abort.restype = ctypes.c_int32
        if self._supports_export_verification:
            lib.wce_export_verify_seal.argtypes = [
                ctypes.POINTER(_WceExportVerifyOptions),
                ctypes.POINTER(_WceExportVerifyResult),
            ]
            lib.wce_export_verify_seal.restype = ctypes.c_int32
        lib.wce_buffer_release.argtypes = [ctypes.POINTER(_WceOwnedBuffer)]
        lib.wce_buffer_release.restype = None
        lib.wce_status_message.argtypes = [ctypes.c_int32]
        lib.wce_status_message.restype = ctypes.c_char_p

    def _status_message(self, status: int) -> str:
        try:
            raw = self._library.wce_status_message(int(status))
            if raw:
                return bytes(raw).decode("utf-8", errors="replace")
        except Exception:
            pass
        return f"status {status}"

    def _raise_for_status(self, status: int, operation: str) -> None:
        if status == NativeCoreStatus.OK:
            return
        message = f"wechatdb native {operation} failed: {self._status_message(status)} ({status})"
        try:
            known_status = NativeCoreStatus(status)
        except ValueError:
            raise NativeCoreProtocolError(message, status=status) from None
        if known_status in _POLICY_STATUSES:
            raise NativeCorePolicyError(message, status=status)
        if known_status in _UNAVAILABLE_STATUSES:
            raise NativeCoreUnavailableError(message, status=status)
        if known_status in {NativeCoreStatus.PROTOCOL, NativeCoreStatus.INVALID_ARGUMENT}:
            raise NativeCoreProtocolError(message, status=status)
        raise NativeCoreError(message, status=status)

    def _open_handle(self) -> ctypes.c_void_p:
        if self._closed or not self._handle.value:
            raise NativeCoreUnavailableError("wechatdb native client is closed.")
        return self._handle

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            handle = self._handle
            if handle.value:
                for export_handle in tuple(self._decrypted_export_handles):
                    try:
                        self._library.wce_export_decrypt_abort(
                            handle,
                            ctypes.c_uint64(export_handle),
                            ctypes.c_uint64(_operation_nonce()),
                        )
                    except Exception:
                        pass
                for export_handle in tuple(self._encrypted_export_handles):
                    try:
                        self._library.wce_export_encrypt_abort(
                            handle,
                            ctypes.c_uint64(export_handle),
                            ctypes.c_uint64(_operation_nonce()),
                        )
                    except Exception:
                        pass
                for export_handle in tuple(self._export_handles):
                    try:
                        self._library.wce_export_abort(
                            handle,
                            ctypes.c_uint64(export_handle),
                            ctypes.c_uint64(_operation_nonce()),
                        )
                    except Exception:
                        pass
                for query_handle in tuple(self._query_handles):
                    try:
                        self._library.wce_query_close(
                            handle,
                            ctypes.c_uint64(query_handle),
                            ctypes.c_uint64(_operation_nonce()),
                        )
                    except Exception:
                        pass
                for database_handle in tuple(self._database_handles):
                    try:
                        self._library.wce_database_close(
                            handle,
                            ctypes.c_uint64(database_handle),
                            ctypes.c_uint64(_operation_nonce()),
                        )
                    except Exception:
                        pass
            self._query_handles.clear()
            self._database_handles.clear()
            self._export_handles.clear()
            self._encrypted_export_handles.clear()
            self._decrypted_export_handles.clear()
            self._closed = True
            self._handle = ctypes.c_void_p()
            if handle.value:
                self._library.wce_client_destroy(handle)

    def __enter__(self) -> NativeCoreClient:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def get_status(self) -> NativeCoreRuntimeStatus:
        with self._lock:
            status = _WceRuntimeStatus()
            status.struct_size = ctypes.sizeof(_WceRuntimeStatus)
            rc = int(self._library.wce_client_get_status(self._open_handle(), ctypes.byref(status)))
            self._raise_for_status(rc, "get status")
            if int(status.protocol_version) != WCE_PROTOCOL_VERSION:
                raise NativeCoreProtocolError(
                    "wechatdb broker protocol mismatch: "
                    f"expected {WCE_PROTOCOL_VERSION}, got {int(status.protocol_version)}."
                )
            try:
                license_state = NativeCoreLicenseState(int(status.license_state))
                assurance = NativeCoreDeviceAssurance(int(status.device_assurance))
            except ValueError as exc:
                raise NativeCoreProtocolError("wechatdb broker returned an unknown runtime state.") from exc
            return NativeCoreRuntimeStatus(
                protocol_version=int(status.protocol_version),
                broker_process_id=int(status.broker_process_id),
                license_state=license_state,
                device_assurance=assurance,
                lease_expires_unix=int(status.lease_expires_unix),
                feature_bits=NativeCoreFeature(int(status.feature_bits)),
                build_id=bytes(status.build_id),
                device_id=bytes(status.device_id),
                startup_nonce=bytes(status.startup_nonce),
            )

    def install_lease(self, lease: bytes | bytearray | memoryview) -> None:
        payload = bytes(lease)
        if not payload:
            raise ValueError("lease must not be empty")
        buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        with self._lock:
            rc = int(
                self._library.wce_client_install_lease(
                    self._open_handle(), buffer, ctypes.c_size_t(len(payload))
                )
            )
            self._raise_for_status(rc, "install lease")

    def create_device_proof(
        self,
        feature: NativeCoreFeature | int,
        challenge_id: bytes | bytearray | memoryview,
        challenge: bytes | bytearray | memoryview,
    ) -> NativeCoreDeviceProof:
        feature_value = int(feature)
        if (
            feature_value <= 0
            or feature_value > 0xFFFF_FFFF_FFFF_FFFF
            or feature_value & (feature_value - 1)
        ):
            raise ValueError("feature must contain exactly one bit")
        challenge_id_value = bytes(challenge_id)
        challenge_value = bytes(challenge)
        if len(challenge_id_value) != 16:
            raise ValueError("challenge_id must contain exactly 16 bytes")
        if len(challenge_value) != 32:
            raise ValueError("challenge must contain exactly 32 bytes")
        challenge_id_buffer = (ctypes.c_uint8 * 16).from_buffer_copy(
            challenge_id_value
        )
        challenge_buffer = (ctypes.c_uint8 * 32).from_buffer_copy(challenge_value)
        proof = _WceLicenseChallengeProof()
        proof.struct_size = ctypes.sizeof(_WceLicenseChallengeProof)
        with self._lock:
            rc = int(
                self._library.wce_client_prove_license_challenge(
                    self._open_handle(),
                    challenge_id_buffer,
                    ctypes.c_size_t(len(challenge_id_value)),
                    challenge_buffer,
                    ctypes.c_size_t(len(challenge_value)),
                    ctypes.c_uint64(feature_value),
                    ctypes.byref(proof),
                )
            )
            self._raise_for_status(rc, "create device proof")
        try:
            device_assurance = NativeCoreDeviceAssurance(int(proof.device_assurance))
        except ValueError as exc:
            raise NativeCoreProtocolError(
                "wechatdb native client returned an invalid device assurance."
            ) from exc
        build_id = bytes(proof.build_id)
        device_id = bytes(proof.device_id)
        startup_nonce = bytes(proof.startup_nonce)
        public_key = bytes(proof.device_public_key)
        signature = bytes(proof.signature)
        if (
            len(build_id) != 32
            or len(device_id) != 32
            or len(startup_nonce) != 32
            or len(public_key) != 64
            or len(signature) != 64
        ):
            raise NativeCoreProtocolError(
                "wechatdb native client returned an invalid device proof."
            )
        return NativeCoreDeviceProof(
            device_assurance=device_assurance,
            requested_features=NativeCoreFeature(int(proof.requested_features)),
            build_id=build_id,
            device_id=device_id,
            startup_nonce=startup_nonce,
            device_public_key=public_key,
            signature=signature,
        )

    def authorize(self, feature: NativeCoreFeature | int) -> None:
        value = int(feature)
        if value <= 0 or value & (value - 1):
            raise ValueError("feature must contain exactly one bit")
        with self._lock:
            rc = int(
                self._library.wce_client_authorize(
                    self._open_handle(), ctypes.c_uint64(value), ctypes.c_uint64(_operation_nonce())
                )
            )
            self._raise_for_status(rc, "authorize operation")

    def open_database(
        self,
        path: str | os.PathLike[str],
        *,
        key: bytes | bytearray | memoryview = b"",
        key_mode: NativeCoreDatabaseKeyMode = NativeCoreDatabaseKeyMode.AUTO,
        busy_timeout_ms: int = 500,
        access: NativeCoreDatabaseAccess = NativeCoreDatabaseAccess.READ_ONLY,
    ) -> NativeCoreDatabase:
        encoded_path = os.fspath(path).encode("utf-8")
        if not encoded_path or b"\0" in encoded_path:
            raise ValueError("database path must be non-empty UTF-8 without NUL bytes")
        payload = bytearray(key)
        key_buffer = None
        try:
            try:
                mode = NativeCoreDatabaseKeyMode(int(key_mode))
            except ValueError as exc:
                raise ValueError("unknown database key mode") from exc
            try:
                selected_access = NativeCoreDatabaseAccess(int(access))
            except ValueError as exc:
                raise ValueError("unknown database access mode") from exc
            timeout = int(busy_timeout_ms)
            if timeout < 0 or timeout > 120_000:
                raise ValueError("busy_timeout_ms must be between 0 and 120000")
            if len(payload) > 256:
                raise ValueError("database key must not exceed 256 bytes")
            if mode is NativeCoreDatabaseKeyMode.RAW and len(payload) != 32:
                raise ValueError("raw database keys must be exactly 32 bytes")
            if mode is NativeCoreDatabaseKeyMode.PASSPHRASE and not payload:
                raise ValueError("database passphrase must not be empty")
            if mode is NativeCoreDatabaseKeyMode.PLAINTEXT and payload:
                raise ValueError("plaintext databases do not accept a key")

            key_buffer = (
                (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
                if payload
                else None
            )
            options = _WceDatabaseOpenOptions(
                struct_size=ctypes.sizeof(_WceDatabaseOpenOptions),
                key_mode=int(mode),
                path_utf8=encoded_path,
                key=(
                    ctypes.cast(key_buffer, ctypes.POINTER(ctypes.c_uint8))
                    if key_buffer
                    else None
                ),
                key_size=len(payload),
                operation_nonce=_operation_nonce(),
                busy_timeout_ms=timeout,
                reserved=0,
                access=int(selected_access),
                reserved2=0,
            )
            output = ctypes.c_uint64()
            with self._lock:
                rc = int(
                    self._library.wce_database_open(
                        self._open_handle(),
                        ctypes.byref(options),
                        ctypes.byref(output),
                    )
                )
                self._raise_for_status(rc, "open database")
                if not output.value:
                    raise NativeCoreProtocolError(
                        "wechatdb native client returned an empty database handle."
                    )
                database_handle = int(output.value)
                self._database_handles.add(database_handle)
            return NativeCoreDatabase(self, database_handle)
        finally:
            if key_buffer is not None:
                ctypes.memset(ctypes.addressof(key_buffer), 0, len(payload))
            payload[:] = b"\x00" * len(payload)

    def _close_database(self, database_handle: int) -> None:
        with self._lock:
            if self._closed:
                return
            rc = int(
                self._library.wce_database_close(
                    self._open_handle(),
                    ctypes.c_uint64(database_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            if rc in {
                int(NativeCoreStatus.OK),
                int(NativeCoreStatus.NOT_FOUND),
                int(NativeCoreStatus.LEASE_EXPIRED),
                int(NativeCoreStatus.TAMPER_DETECTED),
            }:
                self._database_handles.discard(database_handle)
                self._query_handles = {
                    query: database
                    for query, database in self._query_handles.items()
                    if database != database_handle
                }
                return
            self._raise_for_status(rc, "close database")

    def _open_query(self, database_handle: int, sql: str) -> NativeCoreQuery:
        encoded_sql = str(sql or "").encode("utf-8")
        if not encoded_sql or b"\0" in encoded_sql:
            raise ValueError("query must be non-empty UTF-8 without NUL bytes")
        options = _WceQueryOpenOptions(
            struct_size=ctypes.sizeof(_WceQueryOpenOptions),
            reserved=0,
            database_handle=database_handle,
            sql_utf8=encoded_sql,
            operation_nonce=_operation_nonce(),
        )
        output = ctypes.c_uint64()
        with self._lock:
            if database_handle not in self._database_handles:
                raise NativeCoreUnavailableError("wechatdb native database handle is closed.")
            rc = int(
                self._library.wce_query_open(
                    self._open_handle(), ctypes.byref(options), ctypes.byref(output)
                )
            )
            self._raise_for_status(rc, "open query")
            if not output.value:
                raise NativeCoreProtocolError("wechatdb native client returned an empty query handle.")
            query_handle = int(output.value)
            self._query_handles[query_handle] = database_handle
        return NativeCoreQuery(self, query_handle)

    def _fetch_query(self, query_handle: int, *, max_rows: int, max_bytes: int) -> NativeCoreQueryPage:
        rows = int(max_rows)
        size = int(max_bytes)
        if not 1 <= rows <= 4096:
            raise ValueError("max_rows must be between 1 and 4096")
        if not 32 <= size <= 768 * 1024:
            raise ValueError("max_bytes must be between 32 and 786432")
        options = _WceQueryFetchOptions(
            struct_size=ctypes.sizeof(_WceQueryFetchOptions),
            max_rows=rows,
            max_bytes=size,
            reserved=0,
            query_handle=query_handle,
            operation_nonce=_operation_nonce(),
        )
        output = _WceOwnedBuffer(struct_size=ctypes.sizeof(_WceOwnedBuffer))
        has_more = ctypes.c_uint32()
        with self._lock:
            if query_handle not in self._query_handles:
                raise NativeCoreUnavailableError("wechatdb native query handle is closed.")
            try:
                rc = int(
                    self._library.wce_query_fetch(
                        self._open_handle(),
                        ctypes.byref(options),
                        ctypes.byref(output),
                        ctypes.byref(has_more),
                    )
                )
                self._raise_for_status(rc, "fetch query")
                if int(has_more.value) not in {0, 1}:
                    raise NativeCoreProtocolError("wechatdb native query returned an invalid continuation flag.")
                if output.size > 768 * 1024 or (output.size and not output.data):
                    raise NativeCoreProtocolError("wechatdb native query returned an invalid buffer.")
                payload = ctypes.string_at(output.data, output.size) if output.size else b""
            finally:
                self._library.wce_buffer_release(ctypes.byref(output))
        return parse_native_query_page(payload, has_more=bool(has_more.value))

    def _close_query(self, query_handle: int) -> None:
        with self._lock:
            if self._closed:
                return
            rc = int(
                self._library.wce_query_close(
                    self._open_handle(),
                    ctypes.c_uint64(query_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            if rc in {
                int(NativeCoreStatus.OK),
                int(NativeCoreStatus.NOT_FOUND),
                int(NativeCoreStatus.LEASE_EXPIRED),
                int(NativeCoreStatus.TAMPER_DETECTED),
            }:
                self._query_handles.pop(query_handle, None)
                return
            self._raise_for_status(rc, "close query")

    def begin_export(
        self,
        export_id: str,
        *,
        expected_manifest_size: int,
    ) -> NativeCoreExportSession:
        encoded_id = str(export_id or "").encode("utf-8")
        expected_size = int(expected_manifest_size)
        if not encoded_id or len(encoded_id) > 128 or b"\0" in encoded_id:
            raise ValueError("export_id must be 1 to 128 UTF-8 bytes without NUL bytes")
        if not 1 <= expected_size <= 8 * 1024 * 1024:
            raise ValueError("expected_manifest_size must be between 1 and 8388608")
        options = _WceExportBeginOptions(
            struct_size=ctypes.sizeof(_WceExportBeginOptions),
            manifest_format=1,
            export_id_utf8=encoded_id,
            expected_manifest_size=expected_size,
            operation_nonce=_operation_nonce(),
        )
        output = ctypes.c_uint64()
        with self._lock:
            rc = int(
                self._library.wce_export_begin(
                    self._open_handle(), ctypes.byref(options), ctypes.byref(output)
                )
            )
            self._raise_for_status(rc, "begin export")
            if not output.value:
                raise NativeCoreProtocolError("wechatdb native client returned an empty export handle.")
            export_handle = int(output.value)
            self._export_handles.add(export_handle)
        return NativeCoreExportSession(self, export_handle, expected_size)

    def seal_export_manifest(self, export_id: str, manifest: bytes) -> bytes:
        payload = bytes(manifest)
        with self.begin_export(
            export_id, expected_manifest_size=len(payload)
        ) as export_session:
            for offset in range(0, len(payload), 512 * 1024):
                export_session.write(payload[offset : offset + 512 * 1024])
            envelope = export_session.finish()
        if self._build_manifest.root_public_key_compiled:
            self.verify_export_seal(
                envelope,
                payload,
                expected_export_id=str(export_id or ""),
            )
        return envelope

    def verify_export_seal(
        self,
        envelope: bytes | bytearray | memoryview,
        manifest: bytes | bytearray | memoryview,
        *,
        expected_export_id: str | None = None,
    ) -> NativeCoreVerifiedExportSeal:
        if not self._supports_export_verification:
            raise NativeCoreProtocolError(
                "wechatdb native client does not implement the WES1/WES2 "
                "verification ABI."
            )
        encoded_envelope = bytes(envelope)
        canonical_manifest = bytes(manifest)
        if not 273 <= len(encoded_envelope) <= 624:
            raise NativeCoreProtocolError(
                "wechatdb export envelope has an invalid size."
            )
        if not canonical_manifest or len(canonical_manifest) > 8 * 1024 * 1024:
            raise ValueError("export manifest must contain between 1 and 8388608 bytes")
        envelope_buffer = (ctypes.c_uint8 * len(encoded_envelope)).from_buffer_copy(
            encoded_envelope
        )
        manifest_buffer = (ctypes.c_uint8 * len(canonical_manifest)).from_buffer_copy(
            canonical_manifest
        )
        options = _WceExportVerifyOptions(
            struct_size=ctypes.sizeof(_WceExportVerifyOptions),
            reserved=0,
            envelope=ctypes.cast(envelope_buffer, ctypes.POINTER(ctypes.c_uint8)),
            envelope_size=len(encoded_envelope),
            manifest=ctypes.cast(manifest_buffer, ctypes.POINTER(ctypes.c_uint8)),
            manifest_size=len(canonical_manifest),
        )
        result = _WceExportVerifyResult(
            struct_size=ctypes.sizeof(_WceExportVerifyResult)
        )
        rc = int(
            self._library.wce_export_verify_seal(
                ctypes.byref(options), ctypes.byref(result)
            )
        )
        self._raise_for_status(rc, "verify export seal")
        export_id_size = int(result.export_id_size)
        if (
            result.reserved != 0
            or result.manifest_format != 1
            or not 1 <= export_id_size <= 128
            or result.sealed_at_unix > result.lease_expires_unix
            or not result.feature_bits & int(NativeCoreFeature.EXPORT)
        ):
            raise NativeCoreProtocolError(
                "wechatdb native WES1/WES2 verifier returned invalid metadata."
            )
        try:
            export_id = bytes(result.export_id_utf8)[:export_id_size].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NativeCoreProtocolError(
                "wechatdb native WES1/WES2 verifier returned a non-UTF-8 export ID."
            ) from exc
        if expected_export_id is not None and export_id != expected_export_id:
            raise NativeCoreProtocolError(
                "wechatdb verified export ID does not match the requested export."
            )
        manifest_digest = bytes(result.manifest_sha256)
        if not hmac.compare_digest(
            manifest_digest, hashlib.sha256(canonical_manifest).digest()
        ):
            raise NativeCoreProtocolError(
                "wechatdb native WES1/WES2 verifier returned a mismatched manifest digest."
            )
        build_id = bytes(result.build_id)
        if not hmac.compare_digest(build_id, self._client_build_id):
            raise NativeCoreProtocolError(
                "wechatdb native WES1/WES2 verifier returned a mismatched build ID."
            )
        return NativeCoreVerifiedExportSeal(
            export_id=export_id,
            manifest_format=int(result.manifest_format),
            sealed_at_unix=int(result.sealed_at_unix),
            lease_expires_unix=int(result.lease_expires_unix),
            feature_bits=NativeCoreFeature(int(result.feature_bits)),
            manifest_sha256=manifest_digest,
            build_id=build_id,
            device_id=bytes(result.device_id),
        )

    def _write_export(self, export_handle: int, data: bytes) -> None:
        payload = bytes(data)
        if not payload or len(payload) > 768 * 1024:
            raise ValueError("export chunks must be between 1 and 786432 bytes")
        buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        options = _WceExportWriteOptions(
            struct_size=ctypes.sizeof(_WceExportWriteOptions),
            reserved=0,
            export_handle=export_handle,
            operation_nonce=_operation_nonce(),
            data=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8)),
            size=len(payload),
        )
        with self._lock:
            if export_handle not in self._export_handles:
                raise NativeCoreUnavailableError("wechatdb native export handle is closed.")
            rc = int(
                self._library.wce_export_write(self._open_handle(), ctypes.byref(options))
            )
            self._raise_for_status(rc, "write export")

    def _finish_export(self, export_handle: int) -> bytes:
        options = _WceExportFinishOptions(
            struct_size=ctypes.sizeof(_WceExportFinishOptions),
            reserved=0,
            export_handle=export_handle,
            operation_nonce=_operation_nonce(),
        )
        output = _WceOwnedBuffer(struct_size=ctypes.sizeof(_WceOwnedBuffer))
        with self._lock:
            if export_handle not in self._export_handles:
                raise NativeCoreUnavailableError("wechatdb native export handle is closed.")
            try:
                rc = int(
                    self._library.wce_export_finish(
                        self._open_handle(), ctypes.byref(options), ctypes.byref(output)
                    )
                )
                self._raise_for_status(rc, "finish export")
                if not output.size or output.size > 1024 * 1024 or not output.data:
                    raise NativeCoreProtocolError("wechatdb native export returned an invalid envelope.")
                envelope = ctypes.string_at(output.data, output.size)
            finally:
                self._library.wce_buffer_release(ctypes.byref(output))
            self._export_handles.discard(export_handle)
            return envelope

    def _abort_export(self, export_handle: int) -> None:
        with self._lock:
            if self._closed:
                return
            rc = int(
                self._library.wce_export_abort(
                    self._open_handle(),
                    ctypes.c_uint64(export_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            if rc in {
                int(NativeCoreStatus.OK),
                int(NativeCoreStatus.NOT_FOUND),
                int(NativeCoreStatus.LEASE_EXPIRED),
                int(NativeCoreStatus.TAMPER_DETECTED),
            }:
                self._export_handles.discard(export_handle)
                return
            self._raise_for_status(rc, "abort export")

    def begin_encrypted_export(
        self,
        export_id: str,
        *,
        plaintext_size: int,
        content_key: bytes | bytearray | memoryview,
        chunk_size: int = 512 * 1024,
    ) -> NativeCoreEncryptedExportSession:
        encoded_id = str(export_id or "").encode("utf-8")
        total_size = int(plaintext_size)
        selected_chunk_size = int(chunk_size)
        if (
            not encoded_id
            or len(encoded_id) > 128
            or any(value < 0x20 or value == 0x7F for value in encoded_id)
        ):
            raise ValueError("export_id must be 1 to 128 UTF-8 bytes without control bytes")
        if not 1 <= total_size <= _MAX_ENCRYPTED_EXPORT_PLAINTEXT_SIZE:
            raise ValueError("plaintext_size must be between 1 and 274877906944")
        if not 64 * 1024 <= selected_chunk_size <= 768 * 1024:
            raise ValueError("chunk_size must be between 65536 and 786432")
        key = bytearray(content_key)
        if len(key) != 32:
            key[:] = b"\x00" * len(key)
            raise ValueError("content_key must contain exactly 32 bytes")

        key_buffer = (ctypes.c_uint8 * len(key)).from_buffer_copy(key)
        options = _WceExportEncryptBeginOptions(
            struct_size=ctypes.sizeof(_WceExportEncryptBeginOptions),
            chunk_size=selected_chunk_size,
            export_id_utf8=encoded_id,
            content_key=ctypes.cast(key_buffer, ctypes.POINTER(ctypes.c_uint8)),
            content_key_size=len(key),
            plaintext_size=total_size,
            operation_nonce=_operation_nonce(),
        )
        handle_output = ctypes.c_uint64()
        header_output = _WceOwnedBuffer(struct_size=ctypes.sizeof(_WceOwnedBuffer))
        with self._lock:
            export_handle = 0
            try:
                try:
                    rc = int(
                        self._library.wce_export_encrypt_begin(
                            self._open_handle(),
                            ctypes.byref(options),
                            ctypes.byref(handle_output),
                            ctypes.byref(header_output),
                        )
                    )
                    export_handle = int(handle_output.value)
                    self._raise_for_status(rc, "begin encrypted export")
                    if (
                        not export_handle
                        or not header_output.data
                        or not 65 <= header_output.size <= 192
                    ):
                        raise NativeCoreProtocolError(
                            "wechatdb native encrypted export returned an invalid handle or header."
                        )
                    header_bytes = ctypes.string_at(
                        header_output.data, header_output.size
                    )
                finally:
                    ctypes.memset(ctypes.addressof(key_buffer), 0, len(key))
                    key[:] = b"\x00" * len(key)
                    self._library.wce_buffer_release(ctypes.byref(header_output))

                header = parse_native_encrypted_export_header(
                    header_bytes,
                    expected_export_id=encoded_id.decode("utf-8"),
                    expected_plaintext_size=total_size,
                )
                if header.chunk_size != selected_chunk_size:
                    raise NativeCoreProtocolError(
                        "wechatdb encrypted export chunk size does not match the request."
                    )
            except BaseException:
                if export_handle:
                    self._encrypted_export_handles.add(export_handle)
                    try:
                        self._abort_encrypted_export(export_handle)
                    except Exception:
                        pass
                raise
            self._encrypted_export_handles.add(export_handle)
        return NativeCoreEncryptedExportSession(self, export_handle, header)

    def _write_encrypted_export(self, export_handle: int, data: bytes) -> bytes:
        payload = bytes(data)
        if not payload or len(payload) > 768 * 1024:
            raise ValueError("encrypted export chunks must be between 1 and 786432 bytes")
        data_buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        options = _WceExportEncryptWriteOptions(
            struct_size=ctypes.sizeof(_WceExportEncryptWriteOptions),
            reserved=0,
            export_handle=export_handle,
            operation_nonce=_operation_nonce(),
            data=ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_uint8)),
            size=len(payload),
        )
        output = _WceOwnedBuffer(struct_size=ctypes.sizeof(_WceOwnedBuffer))
        with self._lock:
            if export_handle not in self._encrypted_export_handles:
                raise NativeCoreUnavailableError(
                    "wechatdb native encrypted export handle is closed."
                )
            try:
                rc = int(
                    self._library.wce_export_encrypt_write(
                        self._open_handle(), ctypes.byref(options), ctypes.byref(output)
                    )
                )
                self._raise_for_status(rc, "write encrypted export")
                if output.size != len(payload) + 40 or not output.data:
                    raise NativeCoreProtocolError(
                        "wechatdb native encrypted export returned an invalid record."
                    )
                return ctypes.string_at(output.data, output.size)
            finally:
                self._library.wce_buffer_release(ctypes.byref(output))

    def _finish_encrypted_export(self, export_handle: int) -> None:
        with self._lock:
            if export_handle not in self._encrypted_export_handles:
                raise NativeCoreUnavailableError(
                    "wechatdb native encrypted export handle is closed."
                )
            rc = int(
                self._library.wce_export_encrypt_finish(
                    self._open_handle(),
                    ctypes.c_uint64(export_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            self._raise_for_status(rc, "finish encrypted export")
            self._encrypted_export_handles.discard(export_handle)

    def _abort_encrypted_export(self, export_handle: int) -> None:
        with self._lock:
            if self._closed:
                return
            rc = int(
                self._library.wce_export_encrypt_abort(
                    self._open_handle(),
                    ctypes.c_uint64(export_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            if rc in {
                int(NativeCoreStatus.OK),
                int(NativeCoreStatus.NOT_FOUND),
                int(NativeCoreStatus.LEASE_EXPIRED),
                int(NativeCoreStatus.TAMPER_DETECTED),
            }:
                self._encrypted_export_handles.discard(export_handle)
                return
            self._raise_for_status(rc, "abort encrypted export")

    def begin_decrypted_export(
        self,
        header: bytes | bytearray | memoryview,
        *,
        content_key: bytes | bytearray | memoryview,
    ) -> NativeCoreDecryptedExportSession:
        if not self._supports_export_decryption:
            raise NativeCoreProtocolError(
                "wechatdb native client does not implement the WEC1 decryption ABI."
            )
        parsed_header = parse_native_encrypted_export_header(bytes(header))
        key = bytearray(content_key)
        if len(key) != 32:
            key[:] = b"\x00" * len(key)
            raise ValueError("content_key must contain exactly 32 bytes")

        header_buffer = (ctypes.c_uint8 * len(parsed_header.encoded)).from_buffer_copy(
            parsed_header.encoded
        )
        key_buffer = (ctypes.c_uint8 * len(key)).from_buffer_copy(key)
        options = _WceExportDecryptBeginOptions(
            struct_size=ctypes.sizeof(_WceExportDecryptBeginOptions),
            reserved=0,
            header=ctypes.cast(header_buffer, ctypes.POINTER(ctypes.c_uint8)),
            header_size=len(parsed_header.encoded),
            content_key=ctypes.cast(key_buffer, ctypes.POINTER(ctypes.c_uint8)),
            content_key_size=len(key),
            operation_nonce=_operation_nonce(),
        )
        handle_output = ctypes.c_uint64()
        info = _WceExportDecryptInfo(
            struct_size=ctypes.sizeof(_WceExportDecryptInfo)
        )
        with self._lock:
            export_handle = 0
            try:
                try:
                    rc = int(
                        self._library.wce_export_decrypt_begin(
                            self._open_handle(),
                            ctypes.byref(options),
                            ctypes.byref(handle_output),
                            ctypes.byref(info),
                        )
                    )
                    export_handle = int(handle_output.value)
                    self._raise_for_status(rc, "begin decrypted export")
                finally:
                    ctypes.memset(ctypes.addressof(key_buffer), 0, len(key))
                    key[:] = b"\x00" * len(key)

                if (
                    not export_handle
                    or info.reserved != 0
                    or int(info.header_size) != len(parsed_header.encoded)
                    or int(info.plaintext_size) != parsed_header.plaintext_size
                    or int(info.chunk_size) != parsed_header.chunk_size
                    or int(info.chunk_count) != parsed_header.chunk_count
                ):
                    raise NativeCoreProtocolError(
                        "wechatdb native decrypted export metadata does not match the header."
                    )
            except BaseException:
                if export_handle:
                    self._decrypted_export_handles.add(export_handle)
                    try:
                        self._abort_decrypted_export(export_handle)
                    except Exception:
                        pass
                raise
            self._decrypted_export_handles.add(export_handle)
        return NativeCoreDecryptedExportSession(self, export_handle, parsed_header)

    def _write_decrypted_export(
        self,
        export_handle: int,
        record: bytes,
        *,
        expected_size: int,
    ) -> bytes:
        payload = bytes(record)
        if not 40 < len(payload) <= 768 * 1024 + 40:
            raise ValueError(
                "encrypted export records must be between 41 and 786472 bytes"
            )
        record_buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        options = _WceExportDecryptWriteOptions(
            struct_size=ctypes.sizeof(_WceExportDecryptWriteOptions),
            reserved=0,
            export_handle=export_handle,
            operation_nonce=_operation_nonce(),
            record=ctypes.cast(record_buffer, ctypes.POINTER(ctypes.c_uint8)),
            record_size=len(payload),
        )
        output = _WceOwnedBuffer(struct_size=ctypes.sizeof(_WceOwnedBuffer))
        with self._lock:
            if export_handle not in self._decrypted_export_handles:
                raise NativeCoreUnavailableError(
                    "wechatdb native decrypted export handle is closed."
                )
            try:
                rc = int(
                    self._library.wce_export_decrypt_write(
                        self._open_handle(), ctypes.byref(options), ctypes.byref(output)
                    )
                )
                if rc != int(NativeCoreStatus.OK):
                    try:
                        self._abort_decrypted_export(export_handle)
                    except Exception:
                        self._decrypted_export_handles.discard(export_handle)
                    self._raise_for_status(rc, "write decrypted export")
                if output.size != expected_size or not output.data:
                    try:
                        self._abort_decrypted_export(export_handle)
                    except Exception:
                        self._decrypted_export_handles.discard(export_handle)
                    raise NativeCoreProtocolError(
                        "wechatdb native decrypted export returned invalid plaintext."
                    )
                return ctypes.string_at(output.data, output.size)
            finally:
                self._library.wce_buffer_release(ctypes.byref(output))

    def _finish_decrypted_export(self, export_handle: int) -> None:
        with self._lock:
            if export_handle not in self._decrypted_export_handles:
                raise NativeCoreUnavailableError(
                    "wechatdb native decrypted export handle is closed."
                )
            rc = int(
                self._library.wce_export_decrypt_finish(
                    self._open_handle(),
                    ctypes.c_uint64(export_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            self._raise_for_status(rc, "finish decrypted export")
            self._decrypted_export_handles.discard(export_handle)

    def _abort_decrypted_export(self, export_handle: int) -> None:
        with self._lock:
            if self._closed:
                return
            rc = int(
                self._library.wce_export_decrypt_abort(
                    self._open_handle(),
                    ctypes.c_uint64(export_handle),
                    ctypes.c_uint64(_operation_nonce()),
                )
            )
            if rc in {
                int(NativeCoreStatus.OK),
                int(NativeCoreStatus.NOT_FOUND),
                int(NativeCoreStatus.LEASE_EXPIRED),
                int(NativeCoreStatus.TAMPER_DETECTED),
            }:
                self._decrypted_export_handles.discard(export_handle)
                return
            self._raise_for_status(rc, "abort decrypted export")


class NativeCoreDatabase:
    def __init__(self, client: NativeCoreClient, handle: int) -> None:
        self._client = client
        self._handle = int(handle)

    @property
    def closed(self) -> bool:
        return self._handle == 0

    def close(self) -> None:
        handle = self._handle
        if not handle:
            return
        self._handle = 0
        self._client._close_database(handle)

    def __enter__(self) -> NativeCoreDatabase:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def open_query(self, sql: str) -> NativeCoreQuery:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native database is closed.")
        return self._client._open_query(self._handle, sql)

class NativeCoreQuery:
    def __init__(self, client: NativeCoreClient, handle: int) -> None:
        self._client = client
        self._handle = int(handle)
        self._exhausted = False

    @property
    def closed(self) -> bool:
        return self._handle == 0

    def close(self) -> None:
        handle = self._handle
        if not handle:
            return
        self._handle = 0
        self._client._close_query(handle)

    def __enter__(self) -> NativeCoreQuery:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def fetch(self, *, max_rows: int = 256, max_bytes: int = 512 * 1024) -> NativeCoreQueryPage:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native query is closed.")
        if self._exhausted:
            raise NativeCoreProtocolError("wechatdb native query is already exhausted.")
        page = self._client._fetch_query(
            self._handle, max_rows=max_rows, max_bytes=max_bytes
        )
        self._exhausted = not page.has_more
        return page


class NativeCoreExportSession:
    def __init__(self, client: NativeCoreClient, handle: int, expected_size: int) -> None:
        self._client = client
        self._handle = int(handle)
        self._expected_size = int(expected_size)
        self._written = 0

    @property
    def closed(self) -> bool:
        return self._handle == 0

    def write(self, data: bytes | bytearray | memoryview) -> None:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native export is closed.")
        payload = bytes(data)
        if self._written + len(payload) > self._expected_size:
            raise ValueError("export chunks exceed the declared manifest size")
        self._client._write_export(self._handle, payload)
        self._written += len(payload)

    def finish(self) -> bytes:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native export is closed.")
        if self._written != self._expected_size:
            raise ValueError("export manifest size does not match the declared size")
        envelope = self._client._finish_export(self._handle)
        self._handle = 0
        return envelope

    def abort(self) -> None:
        handle = self._handle
        if not handle:
            return
        self._handle = 0
        self._client._abort_export(handle)

    def __enter__(self) -> NativeCoreExportSession:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.abort()


class NativeCoreEncryptedExportSession:
    def __init__(
        self,
        client: NativeCoreClient,
        handle: int,
        header: NativeCoreEncryptedExportHeader,
    ) -> None:
        self._client = client
        self._handle = int(handle)
        self.header = header
        self._written = 0
        self._next_chunk = 0

    @property
    def closed(self) -> bool:
        return self._handle == 0

    def write(self, data: bytes | bytearray | memoryview) -> bytes:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native encrypted export is closed.")
        payload = bytes(data)
        remaining = self.header.plaintext_size - self._written
        expected_size = min(self.header.chunk_size, remaining)
        if len(payload) != expected_size:
            raise ValueError(
                f"encrypted export chunk must contain exactly {expected_size} bytes"
            )
        record = self._client._write_encrypted_export(self._handle, payload)
        index, offset, encoded_size, reserved = struct.unpack_from("<QQII", record, 0)
        if (
            index != self._next_chunk
            or offset != self._written
            or encoded_size != len(payload)
            or reserved != 0
        ):
            raise NativeCoreProtocolError(
                "wechatdb native encrypted export returned an out-of-order record."
            )
        self._written += len(payload)
        self._next_chunk += 1
        return record

    def finish(self) -> None:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native encrypted export is closed.")
        if (
            self._written != self.header.plaintext_size
            or self._next_chunk != self.header.chunk_count
        ):
            raise ValueError("encrypted export size does not match the declared size")
        self._client._finish_encrypted_export(self._handle)
        self._handle = 0

    def abort(self) -> None:
        handle = self._handle
        if not handle:
            return
        self._handle = 0
        self._client._abort_encrypted_export(handle)

    def __enter__(self) -> NativeCoreEncryptedExportSession:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.abort()


class NativeCoreDecryptedExportSession:
    def __init__(
        self,
        client: NativeCoreClient,
        handle: int,
        header: NativeCoreEncryptedExportHeader,
    ) -> None:
        self._client = client
        self._handle = int(handle)
        self.header = header
        self._read = 0
        self._next_chunk = 0

    @property
    def closed(self) -> bool:
        return self._handle == 0

    def write(self, record: bytes | bytearray | memoryview) -> bytes:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native decrypted export is closed.")
        payload = bytes(record)
        remaining = self.header.plaintext_size - self._read
        expected_size = min(self.header.chunk_size, remaining)
        if expected_size <= 0 or len(payload) != expected_size + 40:
            raise NativeCoreProtocolError(
                "encrypted export record size does not match the header."
            )
        index, offset, encoded_size, reserved = struct.unpack_from("<QQII", payload, 0)
        if (
            index != self._next_chunk
            or offset != self._read
            or encoded_size != expected_size
            or reserved != 0
        ):
            raise NativeCoreProtocolError(
                "encrypted export record order does not match the header."
            )
        try:
            plaintext = self._client._write_decrypted_export(
                self._handle, payload, expected_size=expected_size
            )
        except BaseException:
            self._handle = 0
            raise
        self._read += len(plaintext)
        self._next_chunk += 1
        return plaintext

    def finish(self) -> None:
        if not self._handle:
            raise NativeCoreUnavailableError("wechatdb native decrypted export is closed.")
        if (
            self._read != self.header.plaintext_size
            or self._next_chunk != self.header.chunk_count
        ):
            raise ValueError("decrypted export size does not match the header")
        self._client._finish_decrypted_export(self._handle)
        self._handle = 0

    def abort(self) -> None:
        handle = self._handle
        if not handle:
            return
        self._handle = 0
        self._client._abort_decrypted_export(handle)

    def __enter__(self) -> NativeCoreDecryptedExportSession:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.abort()


_singleton_lock = threading.RLock()
_singleton: NativeCoreClient | None = None
_singleton_pid = 0


def get_native_core_client() -> NativeCoreClient:
    global _singleton, _singleton_pid
    current_pid = os.getpid()
    with _singleton_lock:
        if _singleton is not None and _singleton_pid == current_pid:
            _singleton._validate_required_build()
            return _singleton
        if _singleton is not None:
            _singleton.close()
        _singleton = NativeCoreClient()
        _singleton_pid = current_pid
        return _singleton


def close_native_core_client() -> None:
    global _singleton, _singleton_pid
    with _singleton_lock:
        client = _singleton
        _singleton = None
        _singleton_pid = 0
    if client is not None:
        client.close()


def authorize_native_operation(feature: NativeCoreFeature, *, purpose: str) -> bool:
    """Authorize one operation through the mandatory native runtime."""

    del purpose  # Purpose is intentionally excluded from logs and the v1 wire protocol.
    native_core_mode()
    # Import lazily to keep the C ABI binding usable without process
    # management and to avoid a module import cycle.
    from .native_core_broker import ensure_native_core_broker

    ensure_native_core_broker()
    client = get_native_core_client()
    try:
        client.authorize(feature)
    except NativeCorePolicyError as policy_error:
        if policy_error.status not in {
            int(NativeCoreStatus.LICENSE_REQUIRED),
            int(NativeCoreStatus.LEASE_EXPIRED),
            int(NativeCoreStatus.FEATURE_DENIED),
        }:
            raise
        try:
            from .native_core_lease import refresh_native_core_lease

            refresh_native_core_lease(client, feature)
        except Exception as refresh_error:
            # Once a signed policy has rejected the operation, a missing or
            # unreachable license service must never reopen the legacy path.
            raise policy_error from refresh_error
        client.authorize(feature)
    return True


__all__ = [
    "ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD",
    "ENV_NATIVE_CORE_ENDPOINT",
    "ENV_NATIVE_CORE_LIBRARY",
    "ENV_NATIVE_CORE_MODE",
    "ENV_SOURCE_NATIVE_CORE_DIR",
    "NativeCoreClient",
    "NativeCoreBuildManifest",
    "NativeCoreComponentMissingError",
    "NativeCoreDatabase",
    "NativeCoreDatabaseAccess",
    "NativeCoreDatabaseKeyMode",
    "NativeCoreDecryptedExportSession",
    "NativeCoreDeviceAssurance",
    "NativeCoreDeviceProof",
    "NativeCoreError",
    "NativeCoreEncryptedExportHeader",
    "NativeCoreEncryptedExportSession",
    "NativeCoreExportSession",
    "NativeCoreFeature",
    "NativeCoreLicenseState",
    "NativeCoreMode",
    "NativeCorePolicyError",
    "NativeCoreProtocolError",
    "NativeCoreQuery",
    "NativeCoreQueryPage",
    "NativeCoreRuntimeStatus",
    "NativeCoreStatus",
    "NativeCoreUnavailableError",
    "NativeCoreVerifiedExportSeal",
    "authorize_native_operation",
    "close_native_core_client",
    "configure_native_core_entrypoint",
    "get_native_core_client",
    "native_core_mode",
    "parse_native_query_page",
    "parse_native_encrypted_export_header",
    "resolve_native_core_library",
]
