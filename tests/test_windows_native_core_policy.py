from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_client, native_core_lease


def windows_manifest(*, source_runtime: bool = False) -> dict[str, object]:
    issued = int(time.time()) - 60
    manifest: dict[str, object] = {
        "schemaVersion": 2,
        "distributionMode": "public",
        "buildId": "wcdb-windows-20260808-abcd1234",
        "buildIssuedAtUnix": issued,
        "buildExpiresAtUnix": issued + 45 * 24 * 60 * 60,
        "developmentBuild": False,
        "offlineBootstrapFeatureBits": 3,
        "offlineExportSealFormat": "WES2",
        "nativeAsrAbiVersion": 1,
        "nativeAsrFeatureBit": 16,
        "nativeAsrAuthorization": "database-read",
        "nativeAsrTarget": {
            "wechatVersion": "4.1.12.26",
            "weixinSha256": (
                "4914a621a810ecbc0a132b6ff8f612658cfce323d3989b3e5fe32d4ff343ba46"
            ),
        },
        "codeSignatureEnforced": True,
        "rootPublicKeyCompiled": True,
        "testHooksEnabled": False,
        "stagingPinnedSignerTrust": False,
        "windowsSignerTrustMode": "private-pki",
        "windowsPrivatePkiLeafRevocation": "build-and-lease-only",
        "windowsClientSignerSha256": "11" * 32,
        "windowsBrokerSignerSha256": "22" * 32,
        "windowsPrivateRootSha256": "33" * 32,
        "securityNoticeId": "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
        "securityNoticeSha256": "44" * 32,
        "securityCheckpointSetId": "WCE-AI-CHECKPOINT-SET-V3",
        "securityCheckpointCount": 7,
        "securityCheckpointSetSha256": "55" * 32,
    }
    if source_runtime:
        manifest["sourceRuntime"] = True
        manifest["windowsHostVerification"] = "same-user-direct-parent"
    return manifest


def write_component(tmp_path: Path, payload: dict[str, object]) -> Path:
    component = tmp_path / "wechatdb_client.dll"
    component.write_bytes(b"client")
    component.with_name("wechatdb_native_build.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return component


def test_windows_source_public_manifest_retains_production_security(
    tmp_path: Path,
) -> None:
    manifest = native_core_client._load_native_core_build_manifest(
        write_component(tmp_path, windows_manifest(source_runtime=True))
    )

    assert manifest.platform == "windows"
    assert manifest.source_runtime is True
    assert manifest.windows_host_verification == "same-user-direct-parent"
    assert manifest.native_asr_abi_version == 1
    assert manifest.native_asr_feature_bit == 16
    assert manifest.native_asr_authorization == "database-read"
    assert manifest.native_asr_target_wechat_version == "4.1.12.26"
    assert native_core_client._is_source_public_native_core_build_manifest(manifest)
    assert not native_core_client._is_production_native_core_build_manifest(manifest)
    assert native_core_lease.validate_native_core_authorization_policy(manifest) == "production"


def test_windows_runtime_profile_is_bound_to_frozen_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component = write_component(tmp_path, windows_manifest(source_runtime=True))
    monkeypatch.setattr(native_core_client.sys, "platform", "win32")
    monkeypatch.setattr(
        native_core_lease,
        "validate_native_core_authorization_policy",
        lambda _manifest: None,
    )

    monkeypatch.setattr(native_core_client.sys, "frozen", False, raising=False)
    selected = native_core_client._required_native_core_build_manifest(component)
    assert selected.source_runtime is True

    monkeypatch.setattr(native_core_client.sys, "frozen", True, raising=False)
    with pytest.raises(
        native_core_client.NativeCoreProtocolError,
        match="rejects the source-public Windows native core",
    ):
        native_core_client._required_native_core_build_manifest(component)

    component.with_name("wechatdb_native_build.json").write_text(
        json.dumps(windows_manifest()), encoding="utf-8"
    )
    monkeypatch.setattr(native_core_client.sys, "frozen", False, raising=False)
    with pytest.raises(
        native_core_client.NativeCoreProtocolError,
        match="requires the exact restricted source-public",
    ):
        native_core_client._required_native_core_build_manifest(component)


def test_windows_source_entrypoint_consumes_verified_bootstrap_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_dir = tmp_path / "verified-source-runtime" / "native-core"
    runtime_dir.mkdir(parents=True)
    monkeypatch.setattr(native_core_client.sys, "platform", "win32")
    monkeypatch.setattr(native_core_client.sys, "frozen", False, raising=False)
    monkeypatch.setenv(
        native_core_client.ENV_SOURCE_NATIVE_CORE_DIR,
        str(runtime_dir),
    )

    assert native_core_client._native_core_entrypoint_directory() == runtime_dir.resolve()
