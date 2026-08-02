from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from wechat_decrypt_tool.native_core_broker import managed_native_core_operation
from wechat_decrypt_tool.native_core_client import (
    NativeCoreError,
    NativeCoreClient,
    NativeCoreFeature,
    NativeCoreLicenseState,
    NativeCoreProtocolError,
    NativeCoreStatus,
    get_native_core_client,
)
from wechat_decrypt_tool.native_core_export import seal_export_manifest
from wechat_decrypt_tool.native_core_lease import refresh_native_core_lease


def test_build_active_license_state_matches_native_protocol_value() -> None:
    assert NativeCoreLicenseState.BUILD_ACTIVE == 4


@pytest.mark.parametrize(
    ("magic", "envelope_size"),
    [(b"WES2", 273), (b"WES1", 624)],
)
def test_verifier_forwards_supported_envelope_boundaries_to_native_abi(
    magic: bytes,
    envelope_size: int,
) -> None:
    verifier = Mock(side_effect=RuntimeError("native verifier called"))
    client = object.__new__(NativeCoreClient)
    client._supports_export_verification = True
    client._library = SimpleNamespace(wce_export_verify_seal=verifier)

    with pytest.raises(RuntimeError, match="native verifier called"):
        client.verify_export_seal(
            magic + bytes(envelope_size - len(magic)),
            b"{}",
        )

    verifier.assert_called_once()


@pytest.mark.parametrize("envelope_size", [272, 625])
def test_verifier_rejects_envelopes_outside_supported_range(
    envelope_size: int,
) -> None:
    verifier = Mock()
    client = object.__new__(NativeCoreClient)
    client._supports_export_verification = True
    client._library = SimpleNamespace(wce_export_verify_seal=verifier)

    with pytest.raises(NativeCoreProtocolError, match="invalid size"):
        client.verify_export_seal(bytes(envelope_size), b"{}")

    verifier.assert_not_called()


def test_dev_local_wes1_verifier_refuses_to_accept_a_runtime_root() -> None:
    manifest = b'{"exportId":"dev-verifier"}'
    with managed_native_core_operation(export_only=True):
        client = get_native_core_client()
        envelope = seal_export_manifest("dev-verifier", manifest).envelope

        with pytest.raises(NativeCoreError) as caught:
            client.verify_export_seal(
                envelope,
                manifest,
                expected_export_id="dev-verifier",
            )

    assert caught.value.status == int(NativeCoreStatus.UNSUPPORTED)


def test_root_compiled_build_verifies_before_returning_a_new_seal() -> None:
    manifest = b'{"exportId":"formal-verifier"}'
    with managed_native_core_operation(export_only=True):
        client = get_native_core_client()
        refresh_native_core_lease(client, NativeCoreFeature.EXPORT)
        production_like_manifest = replace(
            client.build_manifest,
            root_public_key_compiled=True,
        )
        with (
            patch.object(client, "_build_manifest", production_like_manifest),
            patch.object(client, "verify_export_seal") as verify,
        ):
            envelope = seal_export_manifest("formal-verifier", manifest).envelope

    assert envelope.startswith(b"WES1")
    verify.assert_called_once_with(
        envelope,
        manifest,
        expected_export_id="formal-verifier",
    )
