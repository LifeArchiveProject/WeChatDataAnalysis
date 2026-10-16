from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .app_paths import get_data_dir
from .native_core_client import NativeCoreProtocolError, NativeCoreUnavailableError


_FILE_MAGIC = b"WCEDC001"
_LEGACY_SCHEMA_VERSION = 1
_SCHEMA_VERSION = 2
_MAX_FILE_BYTES = 16 * 1024
_MAX_PLAINTEXT_BYTES = 8 * 1024
_MAX_CREDENTIAL_BYTES = 4096
_LEASE_BYTES = 224
_LEGACY_ENTROPY_DOMAIN = b"WeChatDataAnalysis/native-core/device-credential/v1\0"
_ENTROPY_DOMAIN = b"WeChatDataAnalysis/native-core/device-credential/v2\0"
_MACOS_KEYCHAIN_MAGIC = b"WCEKC002"
_MACOS_KEYCHAIN_SERVICE = "com.lifearchive.wechatdataanalysis.native-core-credential.v2"

CredentialTransform = Callable[[bytes, bytes], bytes]
BytesLike = bytes | bytearray | memoryview


def _credential_path() -> Path:
    return get_data_dir() / ".native-core-license-v1" / "device-credential.bin"


def _binding_identifier(value: BytesLike, *, name: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise NativeCoreProtocolError(
            f"Native core device credential has an invalid {name} binding."
        )
    identifier = bytes(value)
    if len(identifier) != 32 or not any(identifier):
        raise NativeCoreProtocolError(
            f"Native core device credential has an invalid {name} binding."
        )
    return identifier


def _service_identifier(service_url: str) -> bytes:
    if not isinstance(service_url, str):
        raise NativeCoreProtocolError(
            "Native core device credential has an invalid service binding."
        )
    try:
        service = service_url.encode("ascii")
    except UnicodeEncodeError as exc:
        raise NativeCoreProtocolError(
            "Native core device credential has an invalid service binding."
        ) from exc
    if (
        not service
        or len(service) > 2048
        or any(byte < 0x21 or byte > 0x7E for byte in service)
    ):
        raise NativeCoreProtocolError(
            "Native core device credential has an invalid service binding."
        )
    return service


def _legacy_binding_entropy(*, device_id: bytes, service_url: str) -> bytes:
    identifier = _binding_identifier(device_id, name="device")
    service = _service_identifier(service_url)
    return hashlib.sha256(
        _LEGACY_ENTROPY_DOMAIN + identifier + b"\0" + service
    ).digest()


def _binding_entropy(
    *,
    device_id: bytes,
    build_id: bytes,
    service_url: str,
) -> bytes:
    device = _binding_identifier(device_id, name="device")
    build = _binding_identifier(build_id, name="build")
    service = _service_identifier(service_url)
    return hashlib.sha256(
        _ENTROPY_DOMAIN
        + device
        + build
        + len(service).to_bytes(4, "big")
        + service
    ).digest()


def _validate_credential(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise NativeCoreProtocolError("Native core device credential is invalid.")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise NativeCoreProtocolError("Native core device credential is invalid.") from exc
    if (
        len(encoded) < 32
        or len(encoded) > _MAX_CREDENTIAL_BYTES
        or any(byte < 0x21 or byte > 0x7E for byte in encoded)
    ):
        raise NativeCoreProtocolError("Native core device credential is invalid.")
    return value


def _validate_lease(value: object) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise NativeCoreProtocolError("Native core cached lease is invalid.")
    lease = bytes(value)
    if len(lease) != _LEASE_BYTES:
        raise NativeCoreProtocolError(
            f"Native core cached lease must be exactly {_LEASE_BYTES} bytes."
        )
    return lease


def _decode_lease(value: object) -> bytes:
    if not isinstance(value, str):
        raise NativeCoreProtocolError("Native core cached lease is invalid.")
    try:
        encoded = value.encode("ascii")
        lease = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise NativeCoreProtocolError("Native core cached lease is invalid.") from exc
    if base64.b64encode(lease) != encoded:
        raise NativeCoreProtocolError("Native core cached lease is invalid.")
    return _validate_lease(lease)


def _strict_json_object(plaintext: bytes) -> dict[str, object]:
    if not plaintext or len(plaintext) > _MAX_PLAINTEXT_BYTES:
        raise NativeCoreProtocolError("Native core device credential is invalid.")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError(f"duplicate field: {key}")
            payload[key] = value
        return payload

    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant: {value}")

    try:
        payload = json.loads(
            plaintext.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise NativeCoreProtocolError("Native core device credential is invalid.") from exc
    if not isinstance(payload, dict):
        raise NativeCoreProtocolError("Native core device credential is invalid.")
    return payload


@dataclass(frozen=True, slots=True)
class StoredDeviceCredential:
    """A decrypted credential record; schema 1 records require online migration."""

    credential: str
    lease: bytes | None
    schema_version: int

    @property
    def requires_migration(self) -> bool:
        return self.schema_version == _LEGACY_SCHEMA_VERSION


def _parse_record(plaintext: bytes, *, expected_schema: int) -> StoredDeviceCredential:
    payload = _strict_json_object(plaintext)
    schema_version = payload.get("schemaVersion")
    if type(schema_version) is not int or schema_version != expected_schema:
        raise NativeCoreProtocolError("Native core device credential is invalid.")

    if expected_schema == _LEGACY_SCHEMA_VERSION:
        if set(payload) != {"schemaVersion", "credential"}:
            raise NativeCoreProtocolError("Native core device credential is invalid.")
        return StoredDeviceCredential(
            credential=_validate_credential(payload.get("credential")),
            lease=None,
            schema_version=_LEGACY_SCHEMA_VERSION,
        )
    if expected_schema == _SCHEMA_VERSION:
        if set(payload) != {"schemaVersion", "credential", "leaseBase64"}:
            raise NativeCoreProtocolError("Native core device credential is invalid.")
        return StoredDeviceCredential(
            credential=_validate_credential(payload.get("credential")),
            lease=_decode_lease(payload.get("leaseBase64")),
            schema_version=_SCHEMA_VERSION,
        )
    raise NativeCoreProtocolError("Native core device credential is invalid.")


def _protect_current_user(payload: bytes, entropy: bytes) -> bytes:
    if sys.platform == "darwin":
        account_digest = hashlib.sha256(
            _ENTROPY_DOMAIN + b"macos-keychain\0" + entropy
        ).digest()
        account = base64.urlsafe_b64encode(account_digest).rstrip(b"=").decode("ascii")
        encoded = base64.b64encode(payload).decode("ascii")
        result = subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-a",
                account,
                "-s",
                _MACOS_KEYCHAIN_SERVICE,
                "-w",
                encoded,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise NativeCoreUnavailableError(
                "Cannot store the native core device credential in macOS Keychain."
            )
        return _MACOS_KEYCHAIN_MAGIC + account_digest
    if os.name == "nt":
        from .native_core_raw_key_cache import _dpapi_transform

        return _dpapi_transform(payload, entropy=entropy, protect=True)
    raise NativeCoreUnavailableError(
        "Native core device credentials require Windows DPAPI or macOS Keychain."
    )


def _unprotect_current_user(payload: bytes, entropy: bytes) -> bytes:
    if sys.platform == "darwin":
        account_digest = hashlib.sha256(
            _ENTROPY_DOMAIN + b"macos-keychain\0" + entropy
        ).digest()
        if (
            len(payload) != len(_MACOS_KEYCHAIN_MAGIC) + len(account_digest)
            or not payload.startswith(_MACOS_KEYCHAIN_MAGIC)
            or not hmac.compare_digest(payload[len(_MACOS_KEYCHAIN_MAGIC) :], account_digest)
        ):
            raise NativeCoreProtocolError(
                "Native core macOS Keychain credential binding is invalid."
            )
        account = base64.urlsafe_b64encode(account_digest).rstrip(b"=").decode("ascii")
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                account,
                "-s",
                _MACOS_KEYCHAIN_SERVICE,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise NativeCoreProtocolError(
                "Native core device credential is missing from macOS Keychain."
            )
        try:
            encoded = result.stdout.strip().encode("ascii")
            decoded = base64.b64decode(encoded, validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise NativeCoreProtocolError(
                "Native core macOS Keychain credential is invalid."
            ) from exc
        if base64.b64encode(decoded) != encoded:
            raise NativeCoreProtocolError(
                "Native core macOS Keychain credential is not canonical."
            )
        return decoded
    if os.name == "nt":
        from .native_core_raw_key_cache import _dpapi_transform

        return _dpapi_transform(payload, entropy=entropy, protect=False)
    raise NativeCoreUnavailableError(
        "Native core device credentials require Windows DPAPI or macOS Keychain."
    )


class DeviceCredentialStore:
    """Persist a signed lease with CurrentUser DPAPI or the login Keychain."""

    def __init__(
        self,
        *,
        path: Path | None = None,
        protect: CredentialTransform | None = None,
        unprotect: CredentialTransform | None = None,
    ) -> None:
        self._path = Path(path) if path is not None else _credential_path()
        self._protect = protect or _protect_current_user
        self._unprotect = unprotect or _unprotect_current_user

    @property
    def path(self) -> Path:
        return self._path

    def load(
        self,
        *,
        device_id: bytes,
        build_id: bytes,
        service_url: str,
    ) -> StoredDeviceCredential | None:
        try:
            encoded = self._path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise NativeCoreUnavailableError(
                "Cannot read the native core device credential."
            ) from exc
        if (
            len(encoded) <= len(_FILE_MAGIC)
            or len(encoded) > _MAX_FILE_BYTES
            or not encoded.startswith(_FILE_MAGIC)
        ):
            raise NativeCoreProtocolError("Native core device credential file is invalid.")
        protected = encoded[len(_FILE_MAGIC) :]
        entropy = _binding_entropy(
            device_id=device_id,
            build_id=build_id,
            service_url=service_url,
        )
        try:
            plaintext_value = self._unprotect(protected, entropy)
            if not isinstance(plaintext_value, (bytes, bytearray, memoryview)):
                raise TypeError("credential transform returned a non-bytes value")
            plaintext = bytes(plaintext_value)
        except NativeCoreUnavailableError:
            raise
        except Exception as current_error:
            legacy_entropy = _legacy_binding_entropy(
                device_id=device_id,
                service_url=service_url,
            )
            try:
                plaintext_value = self._unprotect(protected, legacy_entropy)
                if not isinstance(plaintext_value, (bytes, bytearray, memoryview)):
                    raise TypeError("credential transform returned a non-bytes value")
                plaintext = bytes(plaintext_value)
            except NativeCoreUnavailableError:
                raise
            except Exception as legacy_error:
                raise NativeCoreProtocolError(
                    "Native core device credential cannot be decrypted for this user, "
                    "device, build, or service."
                ) from legacy_error
            try:
                return _parse_record(
                    plaintext,
                    expected_schema=_LEGACY_SCHEMA_VERSION,
                )
            except NativeCoreProtocolError as exc:
                raise exc from current_error
        return _parse_record(plaintext, expected_schema=_SCHEMA_VERSION)

    def save(
        self,
        credential: str,
        lease: BytesLike,
        *,
        device_id: bytes,
        build_id: bytes,
        service_url: str,
    ) -> None:
        validated = _validate_credential(credential)
        validated_lease = _validate_lease(lease)
        entropy = _binding_entropy(
            device_id=device_id,
            build_id=build_id,
            service_url=service_url,
        )
        plaintext = json.dumps(
            {
                "schemaVersion": _SCHEMA_VERSION,
                "credential": validated,
                "leaseBase64": base64.b64encode(validated_lease).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        if len(plaintext) > _MAX_PLAINTEXT_BYTES:
            raise NativeCoreProtocolError("Native core device credential is too large.")
        try:
            protected_value = self._protect(plaintext, entropy)
            if not isinstance(protected_value, (bytes, bytearray, memoryview)):
                raise TypeError("credential transform returned a non-bytes value")
            protected = bytes(protected_value)
        except NativeCoreUnavailableError:
            raise
        except Exception as exc:
            raise NativeCoreUnavailableError(
                "Cannot protect the native core device credential."
            ) from exc
        encoded = _FILE_MAGIC + protected
        if len(encoded) > _MAX_FILE_BYTES:
            raise NativeCoreProtocolError("Native core device credential is too large.")

        temporary_path: Path | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                dir=self._path.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self._path)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise NativeCoreUnavailableError(
                "Cannot persist the native core device credential."
            ) from exc

    def delete(self) -> None:
        if self._protect is _protect_current_user and sys.platform == "darwin":
            try:
                encoded = self._path.read_bytes()
            except FileNotFoundError:
                encoded = b""
            except OSError as exc:
                raise NativeCoreUnavailableError(
                    "Cannot read the native core device credential."
                ) from exc
            protected = encoded[len(_FILE_MAGIC) :] if encoded.startswith(_FILE_MAGIC) else b""
            if (
                len(protected) == len(_MACOS_KEYCHAIN_MAGIC) + 32
                and protected.startswith(_MACOS_KEYCHAIN_MAGIC)
            ):
                account = base64.urlsafe_b64encode(
                    protected[len(_MACOS_KEYCHAIN_MAGIC) :]
                ).rstrip(b"=").decode("ascii")
                result = subprocess.run(
                    [
                        "/usr/bin/security",
                        "delete-generic-password",
                        "-a",
                        account,
                        "-s",
                        _MACOS_KEYCHAIN_SERVICE,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if result.returncode not in {0, 44}:
                    raise NativeCoreUnavailableError(
                        "Cannot remove the native core device credential from macOS Keychain."
                    )
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            raise NativeCoreUnavailableError(
                "Cannot remove the native core device credential."
            ) from exc


__all__ = ["DeviceCredentialStore", "StoredDeviceCredential"]
