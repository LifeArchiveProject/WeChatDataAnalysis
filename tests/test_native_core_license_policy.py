from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import (
    native_core_broker,
    native_core_client,
    native_core_dev_lease,
    native_core_lease,
)
from wechat_decrypt_tool.native_core_client import (
    ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
    ENV_NATIVE_CORE_ALLOW_STAGING_BUILD,
    NativeCoreBuildManifest,
    NativeCoreClient,
    NativeCoreDeviceAssurance,
    NativeCoreDeviceProof,
    NativeCoreFeature,
    NativeCoreLicenseState,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreRuntimeStatus,
    NativeCoreUnavailableError,
)
from wechat_decrypt_tool.native_core_lease import ENV_LICENSE_TOKEN, ENV_LICENSE_URL
from wechat_decrypt_tool.native_core_device_credential import StoredDeviceCredential


_PRODUCTION_BUILD_ISSUED_AT = int(time.time()) - 60
_PRODUCTION_BUILD_EXPIRES_AT = _PRODUCTION_BUILD_ISSUED_AT + 45 * 24 * 60 * 60


@pytest.fixture(autouse=True)
def _reset_license_runtime_state() -> None:
    native_core_lease._reset_native_core_lease_state_for_tests()
    yield
    native_core_lease._reset_native_core_lease_state_for_tests()


def _manifest(*, development: bool) -> NativeCoreBuildManifest:
    return NativeCoreBuildManifest(
        build_id="dev-local" if development else "release-2026.07.27",
        development_build=development,
        code_signature_enforced=not development,
        root_public_key_compiled=not development,
        test_hooks_enabled=development,
        staging_pinned_signer_trust=False,
        windows_client_signer_sha256=b"h" * 32,
        offline_bootstrap_feature_bits=(
            NativeCoreFeature(0)
            if development
            else NativeCoreFeature.DATABASE_READ | NativeCoreFeature.EXPORT
        ),
        offline_export_seal_format="none" if development else "WES2",
        build_issued_at_unix=0 if development else _PRODUCTION_BUILD_ISSUED_AT,
        build_expires_at_unix=0 if development else _PRODUCTION_BUILD_EXPIRES_AT,
    )


def _status() -> NativeCoreRuntimeStatus:
    return NativeCoreRuntimeStatus(
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


@pytest.mark.parametrize(
    "build_id",
    ("staging-security-12345678", "release.test.2026.07.27", "debug-build-123"),
)
def test_staging_and_development_labels_are_never_production(build_id: str) -> None:
    manifest = replace(_manifest(development=False), build_id=build_id)
    assert not native_core_client._is_production_native_core_build_manifest(manifest)


def test_staging_signer_trust_is_never_a_production_profile() -> None:
    manifest = replace(
        _manifest(development=False), staging_pinned_signer_trust=True
    )
    assert not native_core_client._is_production_native_core_build_manifest(manifest)


def test_development_manifest_accepts_an_empty_windows_signer_pin() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=True)
        manifest_path = component.with_name("wechatdb_native_build.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["windowsClientSignerSha256"] = ""
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        manifest = native_core_client._load_native_core_build_manifest(component)

    assert manifest.windows_client_signer_sha256 == bytes(32)


def test_license_required_status_is_reported_as_policy_error() -> None:
    client = object.__new__(NativeCoreClient)
    client._library = SimpleNamespace(
        wce_status_message=lambda status: b"license required"
    )

    with pytest.raises(NativeCorePolicyError) as caught:
        client._raise_for_status(-5, "authorize operation")

    assert caught.value.status == -5


class _FakeClient:
    def __init__(self, manifest: NativeCoreBuildManifest) -> None:
        self.build_manifest = manifest
        self._status = _status()
        self.installed: list[bytes] = []
        self.proof_calls: list[tuple[NativeCoreFeature, bytes, bytes]] = []
        self.device_proof = NativeCoreDeviceProof(
            device_assurance=self._status.device_assurance,
            requested_features=NativeCoreFeature.DATABASE_READ,
            build_id=self._status.build_id,
            device_id=self._status.device_id,
            startup_nonce=self._status.startup_nonce,
            device_public_key=b"p" * 64,
            signature=b"s" * 64,
        )

    def get_status(self) -> NativeCoreRuntimeStatus:
        return self._status

    def install_lease(self, lease: bytes) -> None:
        self.installed.append(bytes(lease))
        self._status = replace(
            self._status,
            license_state=NativeCoreLicenseState.ACTIVE,
            lease_expires_unix=int(time.time()) + 600,
            feature_bits=NativeCoreFeature.DATABASE_READ,
        )

    def create_device_proof(
        self,
        feature: NativeCoreFeature,
        challenge_id: bytes,
        challenge: bytes,
    ) -> NativeCoreDeviceProof:
        self.proof_calls.append((feature, bytes(challenge_id), bytes(challenge)))
        return self.device_proof


class _JsonResponse:
    def __init__(
        self,
        payload: object,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = {"Content-Type": content_type}

    def read(self, size: int = -1) -> bytes:
        return self.raw if size < 0 else self.raw[:size]

    def __enter__(self) -> _JsonResponse:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None


class _SequenceOpener:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[object, float]] = []

    def open(self, request, *, timeout: float):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("unexpected license service request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _write_component(
    root: Path, *, development: bool, build_id: str | None = None
) -> Path:
    component = root / "wechatdb_client.dll"
    component.write_bytes(b"client")
    manifest = _manifest(development=development)
    if build_id is not None:
        manifest = replace(manifest, build_id=build_id)
    (root / "wechatdb_native_build.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "buildId": manifest.build_id,
                "buildIssuedAtUnix": manifest.build_issued_at_unix,
                "buildExpiresAtUnix": manifest.build_expires_at_unix,
                "developmentBuild": manifest.development_build,
                "offlineBootstrapFeatureBits": int(
                    manifest.offline_bootstrap_feature_bits
                ),
                "offlineExportSealFormat": manifest.offline_export_seal_format,
                "codeSignatureEnforced": manifest.code_signature_enforced,
                "rootPublicKeyCompiled": manifest.root_public_key_compiled,
                "testHooksEnabled": manifest.test_hooks_enabled,
                "stagingPinnedSignerTrust": manifest.staging_pinned_signer_trust,
                "windowsClientSignerSha256": manifest.windows_client_signer_sha256.hex(),
            }
        ),
        encoding="utf-8",
    )
    return component


def _update_component_manifest(component: Path, **updates: object) -> None:
    manifest_path = component.with_name("wechatdb_native_build.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.update(updates)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")


def _controlled_capsule_payload(
    component: Path,
    *,
    artifact_id: uuid.UUID | None = None,
    artifact_sha256: bytes | None = None,
    signer_sha256: bytes = b"h" * 32,
    ticket_artifact_id: uuid.UUID | None = None,
) -> dict[str, object]:
    actual_artifact_id = artifact_id or uuid.UUID(
        "12345678-1234-5678-9abc-1234567890ab"
    )
    actual_ticket_id = ticket_artifact_id or actual_artifact_id
    return {
        "schemaVersion": 1,
        "artifactId": str(actual_artifact_id),
        "artifactSha256": native_core_lease._base64url(
            artifact_sha256
            if artifact_sha256 is not None
            else hashlib.sha256(component.read_bytes()).digest()
        ),
        "authenticodeSignerSha256": native_core_lease._base64url(signer_sha256),
        "distributionTicket": f"wct1.{actual_ticket_id.hex}.{'t' * 43}",
    }


def _encode_capsule(payload: dict[str, object], *, canonical: bool = True) -> str:
    if canonical:
        raw = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    else:
        raw = json.dumps(payload, indent=2).encode("ascii")
    return native_core_lease._base64url(raw)


def test_distribution_manifest_defaults_to_public_for_backward_compatibility() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        manifest = native_core_client._load_native_core_build_manifest(component)

    assert manifest.distribution_mode == "public"
    assert manifest.distribution_capsule is None


@pytest.mark.parametrize("expiry_delta", [None, 45 * 24 * 60 * 60 - 1])
def test_production_manifest_requires_an_exact_45_day_build_window(
    expiry_delta: int | None,
) -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        manifest_path = component.with_name("wechatdb_native_build.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if expiry_delta is None:
            payload.pop("buildIssuedAtUnix")
            payload.pop("buildExpiresAtUnix")
        else:
            payload["buildExpiresAtUnix"] = (
                payload["buildIssuedAtUnix"] + expiry_delta
            )
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(NativeCoreProtocolError, match="exact 45-day"):
            native_core_client._load_native_core_build_manifest(component)


@pytest.mark.parametrize(
    ("development", "updates", "message"),
    [
        (False, {"offlineBootstrapFeatureBits": 0}, "features 3"),
        (False, {"offlineExportSealFormat": "WES1"}, "format WES2"),
        (True, {"offlineBootstrapFeatureBits": 3}, "features 0"),
        (True, {"offlineExportSealFormat": "WES2"}, "format none"),
    ],
)
def test_native_manifest_rejects_mismatched_offline_bootstrap_contract(
    development: bool,
    updates: dict[str, object],
    message: str,
) -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=development)
        _update_component_manifest(component, **updates)

        with pytest.raises(NativeCoreProtocolError, match=message):
            native_core_client._load_native_core_build_manifest(component)


@pytest.mark.parametrize(
    "missing_field",
    ["offlineBootstrapFeatureBits", "offlineExportSealFormat"],
)
def test_native_manifest_requires_explicit_offline_bootstrap_fields(
    missing_field: str,
) -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        manifest_path = component.with_name("wechatdb_native_build.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload.pop(missing_field)
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(NativeCoreProtocolError, match="offline bootstrap fields"):
            native_core_client._load_native_core_build_manifest(component)


def test_expired_production_manifest_fails_closed_before_native_loading() -> None:
    now = int(time.time())
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        _update_component_manifest(
            component,
            buildIssuedAtUnix=now - 45 * 24 * 60 * 60,
            buildExpiresAtUnix=now,
        )

        with pytest.raises(NativeCorePolicyError, match="fixed expiration"):
            native_core_client._load_native_core_build_manifest(component)


@pytest.mark.parametrize("development", [True, False])
def test_development_and_staging_manifests_allow_legacy_missing_build_window(
    development: bool,
) -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=development)
        manifest_path = component.with_name("wechatdb_native_build.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload.pop("buildIssuedAtUnix")
        payload.pop("buildExpiresAtUnix")
        if not development:
            payload["buildId"] = "staging-security-0123456789abcdef0123456789abcdef"
            payload["stagingPinnedSignerTrust"] = True
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        manifest = native_core_client._load_native_core_build_manifest(component)

    assert manifest.build_issued_at_unix == 0
    assert manifest.build_expires_at_unix == 0


def test_controlled_manifest_accepts_a_canonical_capsule_bound_to_the_client() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        capsule = _encode_capsule(_controlled_capsule_payload(component))
        _update_component_manifest(
            component,
            distributionMode="controlled",
            distributionCapsule=capsule,
        )

        manifest = native_core_client._load_native_core_build_manifest(component)

    assert manifest.distribution_mode == "controlled"
    assert manifest.distribution_capsule == capsule


def test_controlled_client_revalidation_does_not_rehash_the_loaded_artifact() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        capsule = _encode_capsule(_controlled_capsule_payload(component))
        _update_component_manifest(
            component,
            distributionMode="controlled",
            distributionCapsule=capsule,
        )
        manifest = native_core_client._load_native_core_build_manifest(component)
        runtime_build_id = hashlib.sha256(manifest.build_id.encode("utf-8")).digest()
        client = object.__new__(NativeCoreClient)
        client._path = component
        client._build_manifest = manifest
        client._client_build_id = runtime_build_id
        client.get_status = Mock(
            return_value=replace(_status(), build_id=runtime_build_id)
        )

        with (
            patch.dict(
                os.environ,
                {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
                clear=True,
            ),
            patch.object(
                native_core_client,
                "_sha256_file",
                side_effect=AssertionError("artifact was rehashed"),
            ),
            patch.object(native_core_client.sys, "frozen", True, create=True),
        ):
            client._validate_required_build()


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"distributionMode": "controlled"}, "require a distribution capsule"),
        (
            {
                "distributionMode": "public",
                "distributionCapsule": "not-allowed",
            },
            "must not contain a distribution capsule",
        ),
        (
            {
                "distributionMode": "public",
                "distributionCapsule": None,
            },
            "must not contain a distribution capsule",
        ),
        ({"distributionMode": None}, "invalid distributionMode"),
        ({"distributionMode": "private"}, "invalid distributionMode"),
    ),
)
def test_distribution_manifest_rejects_invalid_mode_and_presence_rules(
    updates: dict[str, object], message: str
) -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        _update_component_manifest(component, **updates)

        with pytest.raises(NativeCoreProtocolError, match=message):
            native_core_client._load_native_core_build_manifest(component)


def test_controlled_manifest_rejects_noncanonical_or_unknown_capsule_fields() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        payload = _controlled_capsule_payload(component)
        _update_component_manifest(
            component,
            distributionMode="controlled",
            distributionCapsule=_encode_capsule(payload, canonical=False),
        )
        with pytest.raises(NativeCoreProtocolError, match="not canonical"):
            native_core_client._load_native_core_build_manifest(component)

        payload["recipientId"] = "must-not-be-embedded"
        _update_component_manifest(
            component,
            distributionCapsule=_encode_capsule(payload),
        )
        with pytest.raises(NativeCoreProtocolError, match="invalid structure"):
            native_core_client._load_native_core_build_manifest(component)


@pytest.mark.parametrize(
    ("payload_changes", "message"),
    (
        ({"artifact_sha256": b"x" * 32}, "client artifact SHA-256"),
        ({"signer_sha256": b"s" * 32}, "client signer"),
        (
            {
                "ticket_artifact_id": uuid.UUID(
                    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                )
            },
            "ticket does not match",
        ),
    ),
)
def test_controlled_manifest_rejects_capsule_identity_mismatches(
    payload_changes: dict[str, object], message: str
) -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        capsule = _encode_capsule(
            _controlled_capsule_payload(component, **payload_changes)
        )
        _update_component_manifest(
            component,
            distributionMode="controlled",
            distributionCapsule=capsule,
        )

        with pytest.raises(NativeCoreProtocolError, match=message):
            native_core_client._load_native_core_build_manifest(component)


def test_source_staging_manifest_uses_production_license_policy_when_opted_in() -> None:
    build_id = "staging-security-0123456789abcdef0123456789abcdef"
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False, build_id=build_id)
        manifest_path = Path(td) / "wechatdb_native_build.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["stagingPinnedSignerTrust"] = True
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with (
            patch.dict(
                os.environ,
                {
                    ENV_NATIVE_CORE_ALLOW_STAGING_BUILD: "1",
                    ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                    ENV_LICENSE_TOKEN: "production-token",
                },
                clear=True,
            ),
            patch.object(sys, "frozen", False, create=True),
        ):
            manifest = native_core_client._required_native_core_build_manifest(
                component
            )
            profile = native_core_lease.validate_native_core_authorization_policy(
                manifest
            )

    assert manifest.build_id == build_id
    assert profile == "production"


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
        {
            ENV_LICENSE_URL: "https://license.example.test/v1/leases",
            ENV_LICENSE_TOKEN: "staging-token",
        },
    ),
)
def test_production_policy_does_not_require_user_configuration(
    environment: dict[str, str],
) -> None:
    with patch.dict(os.environ, environment, clear=True):
        assert (
            native_core_lease.validate_native_core_authorization_policy(
                _manifest(development=False)
            )
            == "production"
        )


def test_production_policy_still_rejects_insecure_overrides() -> None:
    with patch.dict(
        os.environ,
        {
            ENV_LICENSE_URL: "http://127.0.0.1:8080/v1/leases",
            ENV_LICENSE_TOKEN: "token",
            "WECHAT_TOOL_NATIVE_CORE_ALLOW_INSECURE_LICENSE_URL": "1",
        },
        clear=True,
    ):
        with pytest.raises(NativeCoreProtocolError, match="must use HTTPS"):
            native_core_lease.validate_native_core_authorization_policy(
                _manifest(development=False)
            )


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("https://license.example.test/v1/lease", "path must end with /v1/leases"),
        (
            "https://license.example.test/v1/leases?tenant=1",
            "must not contain a query",
        ),
        (
            "https://license.example.test/v1/leases#fragment",
            "must not contain a query or fragment",
        ),
    ],
)
def test_production_policy_rejects_ambiguous_license_endpoint(
    url: str,
    message: str,
) -> None:
    with patch.dict(
        os.environ,
        {ENV_LICENSE_URL: url, ENV_LICENSE_TOKEN: "production-token"},
        clear=True,
    ):
        with pytest.raises(NativeCoreProtocolError, match=message):
            native_core_lease.validate_native_core_authorization_policy(
                _manifest(development=False)
            )


def test_challenge_url_replaces_only_the_parsed_lease_path_suffix() -> None:
    assert native_core_lease._challenge_url(
        "https://license.example.test/product/v1/leases"
    ) == "https://license.example.test/product/v1/challenges"


def test_native_client_creates_fixed_size_device_proof() -> None:
    public_key = bytes(range(64))
    signature = bytes(reversed(range(64)))
    captured: dict[str, object] = {}

    def prove_license_challenge(
        handle,
        challenge_id,
        challenge_id_size,
        challenge,
        challenge_size,
        requested_features,
        out_proof,
    ):
        captured.update(
            handle=handle.value,
            challenge_id=bytes(challenge_id),
            challenge_id_size=challenge_id_size.value,
            challenge=bytes(challenge),
            challenge_size=challenge_size.value,
            requested_features=requested_features.value,
        )
        proof = ctypes.cast(
            out_proof,
            ctypes.POINTER(native_core_client._WceLicenseChallengeProof),
        ).contents
        captured["struct_size"] = proof.struct_size
        proof.device_assurance = int(NativeCoreDeviceAssurance.SOFTWARE)
        proof.requested_features = int(NativeCoreFeature.DATABASE_READ)
        for field_name, value in (
            ("build_id", b"b" * 32),
            ("device_id", b"d" * 32),
            ("startup_nonce", b"n" * 32),
        ):
            field = getattr(proof, field_name)
            for index, item in enumerate(value):
                field[index] = item
        for index, value in enumerate(public_key):
            proof.device_public_key[index] = value
        for index, value in enumerate(signature):
            proof.signature[index] = value
        return 0

    client = object.__new__(NativeCoreClient)
    client._lock = threading.RLock()
    client._closed = False
    client._handle = ctypes.c_void_p(7)
    client._library = SimpleNamespace(
        wce_client_prove_license_challenge=prove_license_challenge
    )

    result = client.create_device_proof(
        NativeCoreFeature.DATABASE_READ,
        b"i" * 16,
        b"c" * 32,
    )

    assert result == NativeCoreDeviceProof(
        device_assurance=NativeCoreDeviceAssurance.SOFTWARE,
        requested_features=NativeCoreFeature.DATABASE_READ,
        build_id=b"b" * 32,
        device_id=b"d" * 32,
        startup_nonce=b"n" * 32,
        device_public_key=public_key,
        signature=signature,
    )
    assert captured == {
        "handle": 7,
        "challenge_id": b"i" * 16,
        "challenge_id_size": 16,
        "challenge": b"c" * 32,
        "challenge_size": 32,
        "requested_features": int(NativeCoreFeature.DATABASE_READ),
        "struct_size": ctypes.sizeof(
            native_core_client._WceLicenseChallengeProof
        ),
    }
    assert ctypes.sizeof(native_core_client._WceLicenseChallengeProof) == 240


@pytest.mark.parametrize(
    "feature",
    [NativeCoreFeature.DATABASE_READ, NativeCoreFeature.EXPORT],
)
def test_first_run_build_active_uses_offline_baseline_without_network(
    feature: NativeCoreFeature,
) -> None:
    client = _FakeClient(_manifest(development=False))
    client._status = replace(
        client._status,
        license_state=NativeCoreLicenseState.BUILD_ACTIVE,
        lease_expires_unix=_PRODUCTION_BUILD_EXPIRES_AT,
        feature_bits=NativeCoreFeature.DATABASE_READ | NativeCoreFeature.EXPORT,
    )

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(native_core_lease, "DeviceCredentialStore") as credential_store,
        patch.object(native_core_lease, "_request_lease") as network,
        patch.object(native_core_lease, "_schedule_heartbeat") as heartbeat,
    ):
        result = native_core_lease.refresh_native_core_lease(client, feature)

    assert not result.refreshed
    assert result.status == client._status
    credential_store.assert_not_called()
    network.assert_not_called()
    heartbeat.assert_called_once_with(
        client,
        feature,
        delay_seconds=60 * 60,
    )


@pytest.mark.parametrize(
    "feature",
    [NativeCoreFeature.DATABASE_READ, NativeCoreFeature.EXPORT],
)
def test_near_expiry_online_lease_does_not_mask_offline_baseline(
    feature: NativeCoreFeature,
) -> None:
    client = _FakeClient(_manifest(development=False))
    client._status = replace(
        client._status,
        license_state=NativeCoreLicenseState.ACTIVE,
        lease_expires_unix=int(time.time()) + 5,
        feature_bits=NativeCoreFeature.DATABASE_READ | NativeCoreFeature.EXPORT,
    )

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(native_core_lease, "DeviceCredentialStore") as credential_store,
        patch.object(
            native_core_lease,
            "_request_lease",
            side_effect=NativeCoreUnavailableError("offline"),
        ) as network,
        patch.object(native_core_lease, "_schedule_heartbeat") as heartbeat,
    ):
        result = native_core_lease.refresh_native_core_lease(client, feature)

    assert not result.refreshed
    assert result.status == client._status
    credential_store.assert_not_called()
    network.assert_not_called()
    heartbeat.assert_called_once_with(
        client,
        feature,
        delay_seconds=60 * 60,
    )


def test_production_refresh_uses_challenge_and_device_proof() -> None:
    client = _FakeClient(_manifest(development=False))
    challenge_id = b"i" * 16
    challenge = b"c" * 32
    lease = b"l" * 224
    opener = _SequenceOpener(
        _JsonResponse(
            {
                "challengeId": native_core_lease._base64url(challenge_id),
                "challenge": native_core_lease._base64url(challenge),
                "expiresAt": int(time.time()) + 30,
            }
        ),
        _JsonResponse(
            {"leaseBase64": base64.b64encode(lease).decode("ascii")}
        ),
    )
    with (
        patch.dict(
            os.environ,
            {
                ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                ENV_LICENSE_TOKEN: "production-token",
            },
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
    ):
        result = native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert result.refreshed
    assert client.installed == [lease]
    assert client.proof_calls == [
        (NativeCoreFeature.DATABASE_READ, challenge_id, challenge)
    ]
    assert len(opener.requests) == 2
    challenge_request, challenge_timeout = opener.requests[0]
    lease_request, lease_timeout = opener.requests[1]
    assert challenge_request.full_url == "https://license.example.test/v1/challenges"
    assert lease_request.full_url == "https://license.example.test/v1/leases"
    assert challenge_timeout == lease_timeout == 10
    assert challenge_request.get_header("Authorization") == "Bearer production-token"
    assert lease_request.get_header("Authorization") == "Bearer production-token"
    assert json.loads(challenge_request.data) == {
        "protocolVersion": 2,
        "deviceAssurance": int(NativeCoreDeviceAssurance.SOFTWARE),
        "requestedFeatures": int(NativeCoreFeature.DATABASE_READ),
        "buildId": native_core_lease._base64url(b"b" * 32),
        "deviceId": native_core_lease._base64url(b"d" * 32),
        "startupNonce": native_core_lease._base64url(b"n" * 32),
    }
    assert json.loads(lease_request.data) == {
        "challengeId": native_core_lease._base64url(challenge_id),
        "devicePublicKey": native_core_lease._base64url(b"p" * 64),
        "deviceSignature": native_core_lease._base64url(b"s" * 64),
    }


def test_production_first_use_registers_anonymously_and_persists_credential_after_install() -> None:
    client = _FakeClient(_manifest(development=False))
    challenge_id = b"i" * 16
    challenge = b"c" * 32
    lease = b"l" * 224
    credential = "device_" + "a" * 48
    opener = _SequenceOpener(
        _JsonResponse(
            {
                "challengeId": native_core_lease._base64url(challenge_id),
                "challenge": native_core_lease._base64url(challenge),
                "expiresAt": int(time.time()) + 30,
            }
        ),
        _JsonResponse(
            {
                "leaseBase64": base64.b64encode(lease).decode("ascii"),
                "deviceCredential": credential,
            }
        ),
    )
    store = Mock()
    store.load.return_value = None

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
        patch.object(native_core_lease, "_schedule_heartbeat") as heartbeat,
        patch.object(
            native_core_lease,
            "configure_product_telemetry",
        ) as telemetry,
    ):
        result = native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert result.refreshed
    assert client.installed == [lease]
    assert [request.get_header("Authorization") for request, _ in opener.requests] == [
        None,
        None,
    ]
    assert json.loads(opener.requests[1][0].data)["registration"] is True
    registration_challenge = json.loads(opener.requests[0][0].data)
    assert registration_challenge["appId"] == "wechat-data-analysis.windows"
    assert registration_challenge["hostSignerId"] == native_core_lease._base64url(
        b"h" * 32
    )
    assert "distributionCapsule" not in registration_challenge
    store.save.assert_called_once_with(
        credential,
        lease,
        device_id=b"d" * 32,
        build_id=b"b" * 32,
        service_url="https://license.example.test/v1/leases",
    )
    heartbeat.assert_called_once_with(
        client,
        NativeCoreFeature.DATABASE_READ,
        delay_seconds=60 * 60,
    )
    telemetry.assert_called_once_with(
        license_url="https://license.example.test/v1/leases",
        credential=credential,
        device_id=b"d" * 32,
        build_id=b"b" * 32,
    )


def test_new_process_installs_cached_lease_without_waiting_for_network() -> None:
    client = _FakeClient(_manifest(development=False))
    cached_lease = b"c" * 224
    credential = "device_" + "c" * 48
    store = Mock()
    store.load.return_value = StoredDeviceCredential(credential, cached_lease, 2)

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
        patch.object(native_core_lease, "_request_lease") as network,
        patch.object(native_core_lease, "_schedule_heartbeat") as heartbeat,
        patch.object(
            native_core_lease,
            "configure_product_telemetry",
        ) as telemetry,
    ):
        result = native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert result.refreshed
    assert client.installed == [cached_lease]
    network.assert_not_called()
    store.save.assert_not_called()
    heartbeat.assert_called_once_with(
        client,
        NativeCoreFeature.DATABASE_READ,
        delay_seconds=0,
    )
    connectivity = native_core_lease.get_native_core_connectivity_status()
    assert connectivity.state == "unknown"
    assert connectivity.cached_lease_active
    telemetry.assert_called_once_with(
        license_url="https://license.example.test/v1/leases",
        credential=credential,
        device_id=b"d" * 32,
        build_id=b"b" * 32,
    )


def test_expired_cached_lease_is_deleted_before_synchronous_online_refresh() -> None:
    client = _FakeClient(_manifest(development=False))
    cached_lease = b"c" * 224
    fresh_lease = b"f" * 224
    credential = "device_" + "e" * 48
    store = Mock()
    store.load.return_value = StoredDeviceCredential(credential, cached_lease, 2)
    original_install = client.install_lease
    install_count = 0

    def install(lease: bytes) -> None:
        nonlocal install_count
        install_count += 1
        if install_count == 1:
            raise NativeCorePolicyError(
                "cached lease expired",
                status=int(native_core_client.NativeCoreStatus.LEASE_EXPIRED),
            )
        original_install(lease)

    with (
        patch.dict(
            os.environ,
            {
                ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                ENV_LICENSE_TOKEN: "production-token",
            },
            clear=True,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
        patch.object(client, "install_lease", side_effect=install),
        patch.object(
            native_core_lease,
            "_request_lease",
            return_value=fresh_lease,
        ) as network,
        patch.object(native_core_lease, "_schedule_heartbeat"),
    ):
        result = native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert result.refreshed
    assert client.installed == [fresh_lease]
    store.delete.assert_called_once_with()
    network.assert_called_once()


def test_no_cached_lease_requires_network_and_retries_fail_fast_during_backoff() -> None:
    client = _FakeClient(_manifest(development=False))
    store = Mock()
    store.load.return_value = None

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
        patch.object(
            native_core_lease,
            "_request_lease",
            side_effect=NativeCoreUnavailableError("offline"),
        ) as network,
    ):
        with pytest.raises(NativeCoreUnavailableError, match="offline"):
            native_core_lease.refresh_native_core_lease(
                client,
                NativeCoreFeature.DATABASE_READ,
            )
        started = time.monotonic()
        with pytest.raises(NativeCoreUnavailableError, match="retry is delayed"):
            native_core_lease.refresh_native_core_lease(
                client,
                NativeCoreFeature.DATABASE_READ,
            )
        elapsed = time.monotonic() - started

    assert network.call_count == 1
    assert elapsed < 0.2
    connectivity = native_core_lease.get_native_core_connectivity_status()
    assert connectivity.state == "offline"
    assert not connectivity.cached_lease_active
    assert connectivity.next_attempt_unix is not None


def test_background_heartbeat_failure_keeps_current_signed_lease_active() -> None:
    client = _FakeClient(_manifest(development=False))
    client._status = replace(
        client._status,
        license_state=NativeCoreLicenseState.ACTIVE,
        lease_expires_unix=int(time.time()) + 600,
        feature_bits=NativeCoreFeature.DATABASE_READ,
    )
    credential = "device_" + "h" * 48
    store = Mock()
    store.load.return_value = StoredDeviceCredential(
        credential,
        b"h" * 224,
        2,
    )

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
        patch.object(
            native_core_lease,
            "_request_lease",
            side_effect=NativeCoreUnavailableError("offline"),
        ),
        pytest.raises(NativeCoreUnavailableError, match="offline"),
    ):
        native_core_lease._refresh_native_core_lease_internal(
            client,
            NativeCoreFeature.DATABASE_READ,
            minimum_validity_seconds=0,
            force_online=True,
            background=True,
        )

    assert client.get_status().lease_expires_unix > int(time.time())
    store.delete.assert_not_called()
    connectivity = native_core_lease.get_native_core_connectivity_status()
    assert connectivity.state == "offline"
    assert connectivity.cached_lease_active


def test_valid_lease_path_never_waits_for_the_background_refresh_lock() -> None:
    client = _FakeClient(_manifest(development=False))
    client._status = replace(
        client._status,
        license_state=NativeCoreLicenseState.ACTIVE,
        lease_expires_unix=int(time.time()) + 600,
        feature_bits=NativeCoreFeature.DATABASE_READ,
    )

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease,
            "_refresh_native_core_lease_internal",
        ) as synchronized_refresh,
        patch.object(native_core_lease, "_schedule_heartbeat") as heartbeat,
    ):
        result = native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert not result.refreshed
    synchronized_refresh.assert_not_called()
    heartbeat.assert_called_once_with(
        client,
        NativeCoreFeature.DATABASE_READ,
        delay_seconds=60 * 60,
    )


def test_heartbeat_worker_runs_online_refresh_in_the_background() -> None:
    client = _FakeClient(_manifest(development=False))
    attempted = threading.Event()

    def refresh(*_args, **_kwargs) -> native_core_lease.LeaseRefreshResult:
        attempted.set()
        return native_core_lease.LeaseRefreshResult(
            status=client.get_status(),
            refreshed=True,
        )

    with patch.object(
        native_core_lease,
        "_refresh_native_core_lease_internal",
        side_effect=refresh,
    ) as background_refresh:
        native_core_lease._schedule_heartbeat(
            client,
            NativeCoreFeature.DATABASE_READ,
            delay_seconds=0,
        )
        assert attempted.wait(1.0)

    _, kwargs = background_refresh.call_args
    assert kwargs == {
        "minimum_validity_seconds": 0,
        "force_online": True,
        "background": True,
    }


def test_controlled_capsule_is_sent_only_with_an_anonymous_registration_challenge() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        capsule = _encode_capsule(_controlled_capsule_payload(component))
        _update_component_manifest(
            component,
            distributionMode="controlled",
            distributionCapsule=capsule,
        )
        controlled_manifest = native_core_client._load_native_core_build_manifest(
            component
        )
    client = _FakeClient(controlled_manifest)
    credential = "device_" + "c" * 48
    opener = _SequenceOpener(
        _JsonResponse(
            {
                "challengeId": native_core_lease._base64url(b"i" * 16),
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": int(time.time()) + 30,
            }
        ),
        _JsonResponse(
            {
                "leaseBase64": base64.b64encode(b"l" * 224).decode("ascii"),
                "deviceCredential": credential,
            }
        ),
    )
    store = Mock()
    store.load.return_value = None

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
    ):
        native_core_lease._request_lease(
            client,
            client.get_status(),
            NativeCoreFeature.DATABASE_READ,
        )

    challenge_body = json.loads(opener.requests[0][0].data)
    assert challenge_body["distributionCapsule"] == capsule
    assert json.loads(opener.requests[1][0].data)["registration"] is True


def test_production_renewal_uses_saved_device_credential_without_user_input() -> None:
    capsule = "controlled-capsule-not-forwarded-during-renewal"
    client = _FakeClient(
        replace(
            _manifest(development=False),
            distribution_mode="controlled",
            distribution_capsule=capsule,
        )
    )
    lease = b"r" * 224
    credential = "device_" + "b" * 48
    opener = _SequenceOpener(
        _JsonResponse(
            {
                "challengeId": native_core_lease._base64url(b"i" * 16),
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": int(time.time()) + 30,
            }
        ),
        _JsonResponse({"leaseBase64": base64.b64encode(lease).decode("ascii")}),
    )
    store = Mock()
    store.load.return_value = StoredDeviceCredential(credential, None, 1)

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
    ):
        native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert client.installed == [lease]
    assert [request.get_header("Authorization") for request, _ in opener.requests] == [
        f"Bearer {credential}",
        f"Bearer {credential}",
    ]
    assert "distributionCapsule" not in json.loads(opener.requests[0][0].data)
    store.load.assert_called_once_with(
        device_id=b"d" * 32,
        build_id=b"b" * 32,
        service_url="https://license.example.test/v1/leases",
    )
    store.save.assert_called_once_with(
        credential,
        lease,
        device_id=b"d" * 32,
        build_id=b"b" * 32,
        service_url="https://license.example.test/v1/leases",
    )


def test_rejected_saved_credential_is_authoritative_and_disables_cache() -> None:
    client = _FakeClient(_manifest(development=False))
    lease = b"n" * 224
    old_credential = "device_" + "o" * 48
    opener = _SequenceOpener(
        urllib.error.HTTPError(
            "https://license.example.test/v1/challenges",
            401,
            "Unauthorized",
            {},
            None,
        ),
    )
    store = Mock()
    store.load.return_value = old_credential

    with (
        patch.dict(
            os.environ,
            {ENV_LICENSE_URL: "https://license.example.test/v1/leases"},
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
        patch.object(
            native_core_lease,
            "DeviceCredentialStore",
            return_value=store,
        ),
        patch.object(
            native_core_lease,
            "_invalidate_authoritatively_denied_runtime",
        ) as invalidate,
        patch.object(
            native_core_lease,
            "clear_product_telemetry_context",
        ) as clear_telemetry,
        pytest.raises(native_core_lease._LicenseRequestRejected),
    ):
        native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert [request.get_header("Authorization") for request, _ in opener.requests] == [
        f"Bearer {old_credential}",
    ]
    assert store.delete.call_count >= 1
    store.save.assert_not_called()
    invalidate.assert_called_once_with(client)
    clear_telemetry.assert_called_once_with()
    assert native_core_lease.get_native_core_connectivity_status().state == "denied"


def test_production_refresh_rejects_broker_restart_after_challenge() -> None:
    client = _FakeClient(_manifest(development=False))
    initial_status = client._status
    restarted_status = replace(initial_status, startup_nonce=b"r" * 32)
    challenge_id = b"i" * 16
    challenge = b"c" * 32
    opener = _SequenceOpener(
        _JsonResponse(
            {
                "challengeId": native_core_lease._base64url(challenge_id),
                "challenge": native_core_lease._base64url(challenge),
                "expiresAt": int(time.time()) + 30,
            }
        )
    )
    with (
        patch.dict(
            os.environ,
            {
                ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                ENV_LICENSE_TOKEN: "production-token",
            },
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
        patch.object(
            client,
            "get_status",
            side_effect=[initial_status, restarted_status],
        ),
        pytest.raises(NativeCorePolicyError, match="identity changed"),
    ):
        native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert len(opener.requests) == 1
    assert client.proof_calls == []
    assert client.installed == []


def test_production_refresh_rejects_proof_for_a_different_broker_state() -> None:
    client = _FakeClient(_manifest(development=False))
    client.device_proof = replace(client.device_proof, device_id=b"x" * 32)
    opener = _SequenceOpener(
        _JsonResponse(
            {
                "challengeId": native_core_lease._base64url(b"i" * 16),
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": int(time.time()) + 30,
            }
        )
    )
    with (
        patch.dict(
            os.environ,
            {
                ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                ENV_LICENSE_TOKEN: "production-token",
            },
            clear=True,
        ),
        patch.object(
            native_core_lease.urllib.request,
            "build_opener",
            return_value=opener,
        ),
        pytest.raises(NativeCorePolicyError, match="challenged broker state"),
    ):
        native_core_lease.refresh_native_core_lease(
            client,
            NativeCoreFeature.DATABASE_READ,
        )

    assert len(opener.requests) == 1
    assert client.installed == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "challengeId": native_core_lease._base64url(b"i" * 16) + "==",
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": 1,
            },
            "challengeId",
        ),
        (
            {
                "challengeId": native_core_lease._base64url(b"i" * 15),
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": 1,
            },
            "challengeId",
        ),
        (
            {
                "challengeId": native_core_lease._base64url(bytes(16)),
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": 1,
            },
            "challengeId",
        ),
        (
            {
                "challengeId": native_core_lease._base64url(b"i" * 16),
                "challenge": "*" * 43,
                "expiresAt": 1,
            },
            "challenge",
        ),
        (
            {
                "challengeId": native_core_lease._base64url(b"i" * 16),
                "challenge": native_core_lease._base64url(b"c" * 32),
                "expiresAt": True,
            },
            "expiresAt",
        ),
    ],
)
def test_challenge_response_is_strictly_validated(
    payload: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(NativeCoreProtocolError, match=message):
        native_core_lease._parse_challenge(payload)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_JsonResponse({}, content_type="text/plain"), "non-JSON"),
        (_JsonResponse(b"not-json"), "invalid JSON"),
        (
            _JsonResponse(b"x" * (native_core_lease._MAX_RESPONSE_BYTES + 1)),
            "too large",
        ),
    ],
)
def test_license_http_response_is_strictly_validated(
    response: _JsonResponse,
    message: str,
) -> None:
    opener = _SequenceOpener(response)
    with (
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(NativeCoreProtocolError, match=message),
    ):
        native_core_lease._post_json(
            opener,
            url="https://license.example.test/v1/challenges",
            token="token",
            body={},
            operation="challenge",
        )


def test_production_refresh_never_calls_development_issuer() -> None:
    client = _FakeClient(_manifest(development=False))
    lease = b"p" * 224
    with (
        patch.dict(
            os.environ,
            {
                ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                ENV_LICENSE_TOKEN: "production-token",
            },
            clear=True,
        ),
        patch.object(native_core_lease, "_request_lease", return_value=lease) as request,
        patch.object(
            native_core_dev_lease,
            "issue_development_lease",
            return_value=b"d" * 224,
        ) as development_issuer,
    ):
        result = native_core_lease.refresh_native_core_lease(
            client, NativeCoreFeature.DATABASE_READ
        )

    assert result.refreshed
    assert client.installed == [lease]
    request.assert_called_once()
    development_issuer.assert_not_called()


def test_development_refresh_requires_explicit_local_lease_opt_in() -> None:
    client = _FakeClient(_manifest(development=True))
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(native_core_lease, "_request_lease") as request,
        patch.object(native_core_dev_lease, "issue_development_lease") as issue,
        pytest.raises(NativeCoreProtocolError, match="explicit .*ALLOW_DEVELOPMENT_BUILD=1"),
    ):
        native_core_lease.refresh_native_core_lease(
            client, NativeCoreFeature.DATABASE_READ
        )
    request.assert_not_called()
    issue.assert_not_called()


def test_development_profile_rejects_license_service_configuration() -> None:
    with patch.dict(
        os.environ,
        {
            ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1",
            ENV_LICENSE_URL: "https://license.example.test/v1/leases",
            ENV_LICENSE_TOKEN: "production-token",
        },
        clear=True,
    ):
        with pytest.raises(NativeCoreProtocolError, match="only accepts.*development lease"):
            native_core_lease.validate_native_core_authorization_policy(
                _manifest(development=True)
            )


def test_development_refresh_uses_only_explicit_local_issuer() -> None:
    client = _FakeClient(_manifest(development=True))
    lease = b"d" * 224
    with (
        patch.dict(
            os.environ,
            {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
            clear=True,
        ),
        patch.object(native_core_lease, "_request_lease") as request,
        patch.object(
            native_core_dev_lease,
            "issue_development_lease",
            return_value=lease,
        ) as issue,
    ):
        result = native_core_lease.refresh_native_core_lease(
            client, NativeCoreFeature.DATABASE_READ
        )

    assert result.refreshed
    assert client.installed == [lease]
    request.assert_not_called()
    issue.assert_called_once()


def test_production_client_manifest_accepts_empty_user_license_environment() -> None:
    with TemporaryDirectory() as td:
        component = _write_component(Path(td), development=False)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(sys, "frozen", True, create=True),
        ):
            manifest = native_core_client._required_native_core_build_manifest(component)

    assert manifest == _manifest(development=False)


def test_production_broker_never_prepares_development_trust() -> None:
    manifest = _manifest(development=False)
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(native_core_dev_lease, "prepare_development_trust") as prepare,
    ):
        trust_key = native_core_broker._resolve_broker_trust_key(
            manifest, Path("wechatdb_broker.exe")
        )

    assert trust_key == ""
    prepare.assert_not_called()


def test_production_broker_rejects_external_development_trust() -> None:
    with patch.dict(
        os.environ,
        {native_core_broker.ENV_NATIVE_CORE_TRUST_KEY: "external-root.hex"},
        clear=True,
    ):
        with pytest.raises(NativeCoreProtocolError, match="rejects external"):
            native_core_broker._resolve_broker_trust_key(
                _manifest(development=False), Path("wechatdb_broker.exe")
            )


def test_broker_child_environment_does_not_inherit_license_client_configuration() -> None:
    values = {
        ENV_LICENSE_URL: "https://license.example.test/v1/leases",
        ENV_LICENSE_TOKEN: "secret-token",
        "WECHAT_TOOL_NATIVE_CORE_LICENSE_TIMEOUT_SECONDS": "15",
        "WECHAT_TOOL_NATIVE_CORE_ALLOW_INSECURE_LICENSE_URL": "1",
        "WECHAT_TOOL_NATIVE_CORE_MODE": "required",
    }
    with patch.dict(os.environ, values, clear=True):
        child_environment = native_core_broker._broker_child_environment()

    assert child_environment == {"WECHAT_TOOL_NATIVE_CORE_MODE": "required"}
