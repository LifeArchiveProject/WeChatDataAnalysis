from __future__ import annotations

import base64
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_device_credential
from wechat_decrypt_tool.native_core_client import NativeCoreProtocolError
from wechat_decrypt_tool.native_core_device_credential import (
    DeviceCredentialStore,
    StoredDeviceCredential,
)


class _BoundTransform:
    def __init__(self) -> None:
        self.protected: list[tuple[bytes, bytes]] = []

    def protect(self, payload: bytes, entropy: bytes) -> bytes:
        self.protected.append((bytes(payload), bytes(entropy)))
        return b"protected:" + bytes(entropy) + bytes(payload)[::-1]

    def unprotect(self, payload: bytes, entropy: bytes) -> bytes:
        prefix = b"protected:" + bytes(entropy)
        if not payload.startswith(prefix):
            raise ValueError("entropy mismatch")
        return payload.removeprefix(prefix)[::-1]


DEVICE_ID = b"d" * 32
BUILD_ID = b"b" * 32
SERVICE_URL = "https://license.example.test/v1/leases"
CREDENTIAL = "device_" + "a" * 48
LEASE = bytes(range(224))


def _store(tmp_path: Path, transform: _BoundTransform) -> DeviceCredentialStore:
    return DeviceCredentialStore(
        path=tmp_path / "device.bin",
        protect=transform.protect,
        unprotect=transform.unprotect,
    )


def _write_protected(
    path: Path,
    transform: _BoundTransform,
    plaintext: bytes,
    *,
    entropy: bytes,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        native_core_device_credential._FILE_MAGIC
        + transform.protect(plaintext, entropy)
    )


def test_schema2_round_trips_immutable_credential_and_lease(
    tmp_path: Path,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)
    mutable_lease = bytearray(LEASE)

    store.save(
        CREDENTIAL,
        mutable_lease,
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )
    mutable_lease[0] ^= 0xFF

    record = store.load(
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )

    assert record == StoredDeviceCredential(
        credential=CREDENTIAL,
        lease=LEASE,
        schema_version=2,
    )
    assert record is not None
    assert not record.requires_migration
    assert CREDENTIAL.encode("ascii") not in store.path.read_bytes()
    assert LEASE not in store.path.read_bytes()
    assert transform.protected[0][1] not in {DEVICE_ID, BUILD_ID}
    with pytest.raises(FrozenInstanceError):
        record.credential = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("device_id", "build_id", "service_url"),
    [
        (b"x" * 32, BUILD_ID, SERVICE_URL),
        (DEVICE_ID, b"x" * 32, SERVICE_URL),
        (DEVICE_ID, BUILD_ID, "https://other.example.test/v1/leases"),
    ],
)
def test_schema2_cannot_be_decrypted_across_binding_dimensions(
    tmp_path: Path,
    device_id: bytes,
    build_id: bytes,
    service_url: str,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)
    store.save(
        CREDENTIAL,
        LEASE,
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )

    with pytest.raises(NativeCoreProtocolError, match="device credential"):
        store.load(
            device_id=device_id,
            build_id=build_id,
            service_url=service_url,
        )


def test_schema1_loads_with_legacy_entropy_and_requires_online_migration(
    tmp_path: Path,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)
    legacy_plaintext = json.dumps(
        {"schemaVersion": 1, "credential": CREDENTIAL},
        separators=(",", ":"),
    ).encode("utf-8")
    legacy_entropy = native_core_device_credential._legacy_binding_entropy(
        device_id=DEVICE_ID,
        service_url=SERVICE_URL,
    )
    _write_protected(
        store.path,
        transform,
        legacy_plaintext,
        entropy=legacy_entropy,
    )

    record = store.load(
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )

    assert record == StoredDeviceCredential(
        credential=CREDENTIAL,
        lease=None,
        schema_version=1,
    )
    assert record is not None
    assert record.requires_migration

    store.save(
        record.credential,
        LEASE,
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )
    migrated = store.load(
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )
    assert migrated is not None
    assert migrated.schema_version == 2
    assert migrated.lease == LEASE
    assert not migrated.requires_migration


@pytest.mark.parametrize(
    ("device_id", "service_url"),
    [
        (b"x" * 32, SERVICE_URL),
        (DEVICE_ID, "https://other.example.test/v1/leases"),
    ],
)
def test_schema1_remains_bound_to_its_legacy_device_and_service(
    tmp_path: Path,
    device_id: bytes,
    service_url: str,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)
    plaintext = json.dumps(
        {"schemaVersion": 1, "credential": CREDENTIAL},
        separators=(",", ":"),
    ).encode("utf-8")
    _write_protected(
        store.path,
        transform,
        plaintext,
        entropy=native_core_device_credential._legacy_binding_entropy(
            device_id=DEVICE_ID,
            service_url=SERVICE_URL,
        ),
    )

    with pytest.raises(NativeCoreProtocolError, match="device credential"):
        store.load(
            device_id=device_id,
            build_id=BUILD_ID,
            service_url=service_url,
        )


@pytest.mark.parametrize(
    "plaintext",
    [
        (
            b'{"schemaVersion":2,"schemaVersion":2,'
            b'"credential":"device_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            b'"leaseBase64":"x"}'
        ),
        (
            b'{"schemaVersion":true,'
            b'"credential":"device_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            b'"leaseBase64":"x"}'
        ),
        (
            b'{"schemaVersion":2,'
            b'"credential":"device_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
            b'"leaseBase64":"***"}'
        ),
        json.dumps(
            {
                "schemaVersion": 2,
                "credential": CREDENTIAL,
                "leaseBase64": base64.b64encode(b"short").decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        json.dumps(
            {
                "schemaVersion": 2,
                "credential": CREDENTIAL,
                "leaseBase64": base64.b64encode(LEASE).decode("ascii"),
                "unexpected": True,
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        b"\xff",
        b" " * (native_core_device_credential._MAX_PLAINTEXT_BYTES + 1),
    ],
)
def test_schema2_rejects_invalid_json_schema_and_lease(
    tmp_path: Path,
    plaintext: bytes,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)
    entropy = native_core_device_credential._binding_entropy(
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )
    _write_protected(store.path, transform, plaintext, entropy=entropy)

    with pytest.raises(NativeCoreProtocolError):
        store.load(
            device_id=DEVICE_ID,
            build_id=BUILD_ID,
            service_url=SERVICE_URL,
        )


@pytest.mark.parametrize(
    ("schema_version", "use_legacy_entropy"),
    [(1, False), (2, True)],
)
def test_record_schema_must_match_its_encryption_domain(
    tmp_path: Path,
    schema_version: int,
    use_legacy_entropy: bool,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)
    payload: dict[str, object] = {
        "schemaVersion": schema_version,
        "credential": CREDENTIAL,
    }
    if schema_version == 2:
        payload["leaseBase64"] = base64.b64encode(LEASE).decode("ascii")
    entropy = (
        native_core_device_credential._legacy_binding_entropy(
            device_id=DEVICE_ID,
            service_url=SERVICE_URL,
        )
        if use_legacy_entropy
        else native_core_device_credential._binding_entropy(
            device_id=DEVICE_ID,
            build_id=BUILD_ID,
            service_url=SERVICE_URL,
        )
    )
    _write_protected(
        store.path,
        transform,
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        entropy=entropy,
    )

    with pytest.raises(NativeCoreProtocolError):
        store.load(
            device_id=DEVICE_ID,
            build_id=BUILD_ID,
            service_url=SERVICE_URL,
        )


@pytest.mark.parametrize("lease", [b"x" * 223, b"x" * 225, "x" * 224])
def test_save_rejects_invalid_lease_length_or_type(
    tmp_path: Path,
    lease: object,
) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)

    with pytest.raises(NativeCoreProtocolError, match="lease"):
        store.save(  # type: ignore[arg-type]
            CREDENTIAL,
            lease,
            device_id=DEVICE_ID,
            build_id=BUILD_ID,
            service_url=SERVICE_URL,
        )


def test_load_rejects_invalid_or_oversized_file(tmp_path: Path) -> None:
    transform = _BoundTransform()
    store = _store(tmp_path, transform)

    for encoded in (
        b"invalid",
        native_core_device_credential._FILE_MAGIC,
        native_core_device_credential._FILE_MAGIC + b"x" * (16 * 1024),
    ):
        store.path.write_bytes(encoded)
        with pytest.raises(NativeCoreProtocolError, match="file is invalid"):
            store.load(
                device_id=DEVICE_ID,
                build_id=BUILD_ID,
                service_url=SERVICE_URL,
            )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_device_credential_uses_current_user_dpapi_without_ui(tmp_path: Path) -> None:
    store = DeviceCredentialStore(path=tmp_path / "device.bin")
    credential = "device_" + "b" * 48

    store.save(
        credential,
        LEASE,
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    )

    assert store.load(
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    ) == StoredDeviceCredential(credential, LEASE, 2)
    assert credential.encode("ascii") not in store.path.read_bytes()
    assert LEASE not in store.path.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_current_user_dpapi_reads_existing_schema1_record(tmp_path: Path) -> None:
    store = DeviceCredentialStore(path=tmp_path / "device.bin")
    plaintext = json.dumps(
        {"schemaVersion": 1, "credential": CREDENTIAL},
        separators=(",", ":"),
    ).encode("utf-8")
    entropy = native_core_device_credential._legacy_binding_entropy(
        device_id=DEVICE_ID,
        service_url=SERVICE_URL,
    )
    protected = native_core_device_credential._protect_current_user(
        plaintext,
        entropy,
    )
    store.path.write_bytes(native_core_device_credential._FILE_MAGIC + protected)

    assert store.load(
        device_id=DEVICE_ID,
        build_id=BUILD_ID,
        service_url=SERVICE_URL,
    ) == StoredDeviceCredential(CREDENTIAL, None, 1)
