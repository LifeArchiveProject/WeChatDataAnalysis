from __future__ import annotations

import atexit
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .native_core_client import (
    ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
    NativeCoreFeature,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreRuntimeStatus,
    _is_development_native_core_build_manifest,
    _load_native_core_build_manifest,
)


_LEASE_TTL_SECONDS = 10 * 60
_ALLOWED_FEATURES = int(
    NativeCoreFeature.DATABASE_READ
    | NativeCoreFeature.EXPORT
    | NativeCoreFeature.MEDIA_DECRYPT
)
_lock = threading.RLock()
_private_key: ec.EllipticCurvePrivateKey | None = None
_trust_directory: Path | None = None
_trust_path: Path | None = None
_license_id = uuid.uuid4().bytes
_counter = 0
_startup_nonce = b""
_granted_features = 0


def _development_allowed() -> bool:
    return (
        str(os.environ.get(ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD, "") or "").strip()
        == "1"
    )


def _validate_development_component(component_path: Path) -> None:
    if getattr(sys, "frozen", False):
        raise NativeCorePolicyError(
            "Local native-core lease issuance is disabled in frozen applications."
        )
    if not _development_allowed():
        raise NativeCorePolicyError(
            "Local native-core lease issuance requires the explicit development-build override."
        )
    manifest = _load_native_core_build_manifest(Path(component_path))
    if not _is_development_native_core_build_manifest(manifest):
        raise NativeCorePolicyError(
            "Local native-core lease issuance is restricted to development artifacts "
            "with buildId=dev-local."
        )


def prepare_development_trust(component_path: Path) -> Path:
    """Create an ephemeral development root key and expose only its public key."""

    global _private_key, _trust_directory, _trust_path
    _validate_development_component(Path(component_path))
    with _lock:
        if _private_key is not None and _trust_path is not None and _trust_path.is_file():
            return _trust_path

        private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = private_key.public_key().public_numbers()
        public_hex = (
            numbers.x.to_bytes(32, "big").hex()
            + numbers.y.to_bytes(32, "big").hex()
        )
        directory = Path(tempfile.mkdtemp(prefix="wce-dev-trust-"))
        trust_path = directory / "root-public-key.hex"
        trust_path.write_text(public_hex + "\n", encoding="ascii")

        _private_key = private_key
        _trust_directory = directory
        _trust_path = trust_path
        return trust_path


def issue_development_lease(
    status: NativeCoreRuntimeStatus,
    feature: NativeCoreFeature,
) -> bytes:
    """Sign a short lease in memory for an already prepared development broker."""

    global _counter, _startup_nonce, _granted_features
    requested = int(feature)
    if requested <= 0 or requested & ~_ALLOWED_FEATURES:
        raise NativeCoreProtocolError("Unsupported development native-core feature request.")
    if requested & (requested - 1):
        raise NativeCoreProtocolError("Development lease requests must contain one feature bit.")

    with _lock:
        if not _development_allowed() or _private_key is None or _trust_path is None:
            raise NativeCorePolicyError(
                "The local development lease issuer is not prepared for this broker."
            )
        if bytes(status.startup_nonce) != _startup_nonce:
            _startup_nonce = bytes(status.startup_nonce)
            _granted_features = 0
        _granted_features |= requested
        _counter += 1

        now = int(time.time())
        unsigned = (
            struct.pack(
                "<4sHHQQQQQ",
                b"WCL1",
                1,
                0,
                now,
                now - 1,
                now + _LEASE_TTL_SECONDS,
                _counter,
                _granted_features,
            )
            + _license_id
            + bytes(status.device_id)
            + bytes(status.build_id)
            + bytes(status.startup_nonce)
        )
        signature = _private_key.sign(unsigned, ec.ECDSA(hashes.SHA256()))
        r_value, s_value = decode_dss_signature(signature)
        encoded = (
            unsigned
            + r_value.to_bytes(32, "big")
            + s_value.to_bytes(32, "big")
        )
        if len(encoded) != 224:
            raise NativeCoreProtocolError("Development lease encoding has an invalid size.")
        return encoded


def _cleanup() -> None:
    global _private_key, _trust_directory, _trust_path
    with _lock:
        directory = _trust_directory
        _private_key = None
        _trust_directory = None
        _trust_path = None
    if directory is not None:
        shutil.rmtree(directory, ignore_errors=True)


atexit.register(_cleanup)


__all__ = ["issue_development_lease", "prepare_development_trust"]
