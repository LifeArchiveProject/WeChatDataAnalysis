from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_client, native_core_lease


def macos_manifest(*, development: bool = False) -> dict[str, object]:
    issued = int(time.time()) - 60
    zero = "0" * 64
    return {
        "schemaVersion": 3,
        "platform": "macos",
        "distributionMode": "public",
        "buildId": "dev-local" if development else "wcdb-macos-20260804-abcd1234",
        "buildIssuedAtUnix": 0 if development else issued,
        "buildExpiresAtUnix": 0 if development else issued + 45 * 24 * 60 * 60,
        "developmentBuild": development,
        "offlineBootstrapFeatureBits": 0 if development else 3,
        "offlineExportSealFormat": "none" if development else "WES2",
        "codeSignatureEnforced": not development,
        "rootPublicKeyCompiled": not development,
        "testHooksEnabled": development,
        "stagingPinnedSignerTrust": False,
        "macosSigningMode": "self-signed",
        "macosSignerTrustMode": "development" if development else "private-pki",
        "macosPrivatePkiLeafRevocation": (
            "not-applicable" if development else "build-and-lease-only"
        ),
        "macosClientSigningIdentifier": "com.lifearchive.wechatdb.client",
        "macosBrokerSigningIdentifier": "com.lifearchive.wechatdb.broker",
        "macosHostSigningIdentifier": "com.lifearchive.wechatdataanalysis.backend",
        "macosClientSignerSha256": zero if development else "11" * 32,
        "macosBrokerSignerSha256": zero if development else "22" * 32,
        "macosHostSignerSha256": zero if development else "33" * 32,
        "macosPrivateRootSha256": zero if development else "44" * 32,
        "securityNoticeId": "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
        "securityNoticeSha256": "55" * 32,
        "securityCheckpointSetId": "WCE-AI-CHECKPOINT-SET-V3",
        "securityCheckpointCount": 7,
        "securityCheckpointSetSha256": "66" * 32,
    }


def load_manifest(tmp_path: Path, payload: dict[str, object]):
    component = tmp_path / "libwechatdb_client.dylib"
    component.write_bytes(b"client")
    component.with_name("wechatdb_native_build.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return native_core_client._load_native_core_build_manifest(component)


def test_macos_production_manifest_uses_native_client_signer(tmp_path: Path) -> None:
    manifest = load_manifest(tmp_path, macos_manifest())
    assert manifest.platform == "macos"
    assert manifest.client_signer_sha256 == bytes.fromhex("11" * 32)
    assert manifest.windows_client_signer_sha256 == bytes(32)
    assert native_core_client._is_production_native_core_build_manifest(manifest)
    assert (
        native_core_lease._production_app_id(manifest)
        == "wechat-data-analysis.macos"
    )


def test_macos_development_manifest_has_no_production_pins(tmp_path: Path) -> None:
    manifest = load_manifest(tmp_path, macos_manifest(development=True))
    assert manifest.client_signer_sha256 == bytes(32)
    assert native_core_client._is_development_native_core_build_manifest(manifest)


def test_native_manifest_platforms_cannot_cross_runtime_boundaries(tmp_path: Path) -> None:
    macos = load_manifest(tmp_path, macos_manifest())
    windows = replace(macos, platform="windows")

    assert native_core_client._manifest_matches_runtime_platform(macos, "darwin")
    assert not native_core_client._manifest_matches_runtime_platform(macos, "win32")
    assert native_core_client._manifest_matches_runtime_platform(windows, "win32")
    assert not native_core_client._manifest_matches_runtime_platform(windows, "darwin")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("macosHostSignerSha256", "11" * 32),
        ("macosSigningMode", "developer-id"),
        ("macosHostSigningIdentifier", "com.lifearchive.wechatdb.broker"),
        ("platform", "windows"),
    ),
)
def test_macos_manifest_rejects_identity_substitution(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = macos_manifest()
    payload[field] = value
    with pytest.raises(native_core_client.NativeCoreProtocolError):
        load_manifest(tmp_path, payload)
