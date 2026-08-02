import json
import os
import struct
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_dev_lease
from wechat_decrypt_tool.native_core_client import (
    ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
    NativeCoreDeviceAssurance,
    NativeCoreFeature,
    NativeCoreLicenseState,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreRuntimeStatus,
)


def _verify_development_lease_signature(
    public_key: bytes, unsigned: bytes, signature: bytes
) -> None:
    if len(public_key) != 64 or len(signature) != 64:
        raise ValueError("development lease signature material has an invalid size")
    verifier = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b"\x04" + public_key
    )
    verifier.verify(
        encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        ),
        unsigned,
        ec.ECDSA(hashes.SHA256()),
    )


def _write_component(
    root: Path,
    *,
    development: bool,
    build_id: str | None = None,
) -> Path:
    component = root / "wechatdb_broker.exe"
    component.write_bytes(b"test-component")
    if development:
        manifest = {
            "schemaVersion": 2,
            "buildId": build_id or "dev-local",
            "developmentBuild": True,
            "offlineBootstrapFeatureBits": 0,
            "offlineExportSealFormat": "none",
            "codeSignatureEnforced": False,
            "rootPublicKeyCompiled": False,
            "testHooksEnabled": True,
            "stagingPinnedSignerTrust": False,
        }
    else:
        build_issued_at = int(time.time()) - 60
        manifest = {
            "schemaVersion": 2,
            "buildId": "release-2026.07.27",
            "buildIssuedAtUnix": build_issued_at,
            "buildExpiresAtUnix": build_issued_at + 45 * 24 * 60 * 60,
            "developmentBuild": False,
            "offlineBootstrapFeatureBits": 3,
            "offlineExportSealFormat": "WES2",
            "codeSignatureEnforced": True,
            "rootPublicKeyCompiled": True,
            "testHooksEnabled": False,
            "stagingPinnedSignerTrust": False,
            "windowsClientSignerSha256": (b"h" * 32).hex(),
        }
    (root / "wechatdb_native_build.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return component


class TestNativeCoreDevelopmentLease(unittest.TestCase):
    def setUp(self) -> None:
        native_core_dev_lease._cleanup()

    def tearDown(self) -> None:
        native_core_dev_lease._cleanup()

    def test_development_trust_requires_the_exact_explicit_switch(self) -> None:
        with TemporaryDirectory() as td:
            component = _write_component(Path(td), development=True)

            for value in ("", "true", "yes", "on"):
                with self.subTest(value=value), patch.dict(
                    os.environ,
                    {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: value},
                    clear=False,
                ):
                    with self.assertRaises(NativeCorePolicyError):
                        native_core_dev_lease.prepare_development_trust(component)

            with patch.dict(
                os.environ,
                {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
                clear=False,
            ):
                trust_path = native_core_dev_lease.prepare_development_trust(component)

            self.assertTrue(trust_path.is_file())
            self.assertEqual(len(bytes.fromhex(trust_path.read_text(encoding="ascii").strip())), 64)

    def test_production_manifest_is_rejected_even_with_development_switch(self) -> None:
        with TemporaryDirectory() as td:
            component = _write_component(Path(td), development=False)
            with patch.dict(
                os.environ,
                {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
                clear=False,
            ):
                with self.assertRaisesRegex(
                    NativeCorePolicyError, "restricted to development artifacts"
                ):
                    native_core_dev_lease.prepare_development_trust(component)

    def test_alternate_development_build_and_frozen_runtime_are_rejected(self) -> None:
        with TemporaryDirectory() as td, patch.dict(
            os.environ,
            {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
            clear=False,
        ):
            component = _write_component(
                Path(td), development=True, build_id="dev-local-copy"
            )
            with self.assertRaisesRegex(NativeCorePolicyError, "buildId=dev-local"):
                native_core_dev_lease.prepare_development_trust(component)

            component = _write_component(Path(td), development=True)
            with (
                patch.object(sys, "frozen", True, create=True),
                self.assertRaisesRegex(NativeCorePolicyError, "disabled in frozen"),
            ):
                native_core_dev_lease.prepare_development_trust(component)

    def test_ephemeral_root_signed_lease_has_a_valid_signature(self) -> None:
        status = NativeCoreRuntimeStatus(
            protocol_version=2,
            broker_process_id=1234,
            license_state=NativeCoreLicenseState.UNLICENSED,
            device_assurance=NativeCoreDeviceAssurance.SOFTWARE,
            lease_expires_unix=0,
            feature_bits=NativeCoreFeature(0),
            build_id=b"b" * 32,
            device_id=b"d" * 32,
            startup_nonce=b"n" * 32,
        )
        with TemporaryDirectory() as td, patch.dict(
            os.environ,
            {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
            clear=False,
        ):
            component = _write_component(Path(td), development=True)
            trust_path = native_core_dev_lease.prepare_development_trust(component)
            public_key = bytes.fromhex(trust_path.read_text(encoding="ascii").strip())
            lease = native_core_dev_lease.issue_development_lease(
                status, NativeCoreFeature.DATABASE_READ
            )

        native_core_dev_lease._cleanup()
        self.assertFalse(trust_path.exists())
        self.assertEqual(len(lease), 224)
        magic, version, reserved, issued_at, not_before, expires_at, counter, features = (
            struct.unpack_from("<4sHHQQQQQ", lease)
        )
        self.assertEqual((magic, version, reserved), (b"WCL1", 1, 0))
        self.assertLessEqual(not_before, issued_at)
        self.assertGreater(expires_at, issued_at)
        self.assertGreater(counter, 0)
        self.assertTrue(features & int(NativeCoreFeature.DATABASE_READ))
        self.assertEqual(lease[64:96], status.device_id)
        self.assertEqual(lease[96:128], status.build_id)
        self.assertEqual(lease[128:160], status.startup_nonce)

        _verify_development_lease_signature(public_key, lease[:160], lease[160:224])

        tampered = bytearray(lease)
        tampered[100] ^= 1
        with self.assertRaises(InvalidSignature):
            _verify_development_lease_signature(
                public_key, bytes(tampered[:160]), bytes(tampered[160:224])
            )


if __name__ == "__main__":
    unittest.main()
