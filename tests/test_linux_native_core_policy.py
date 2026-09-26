from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_client, native_core_lease


ZERO = "0" * 64


def linux_manifest(
    *,
    development: bool = False,
    source_runtime: bool = False,
    host_verification: str | None = None,
) -> dict[str, object]:
    """Linux 的 schema v4 清单（与 WCDB producer 的 CMake 模板同字段集）。"""
    issued = int(time.time()) - 60
    manifest: dict[str, object] = {
        "schemaVersion": 4,
        "platform": "linux",
        "distributionMode": "public",
        "buildId": "dev-local" if development else "linux-x64-20260915-abcd1234",
        "buildIssuedAtUnix": 0 if development else issued,
        "buildExpiresAtUnix": 0 if development else issued + 45 * 24 * 60 * 60,
        "developmentBuild": development,
        "offlineBootstrapFeatureBits": 0 if development else 3,
        "offlineExportSealFormat": "none" if development else "WES2",
        "codeSignatureEnforced": not development,
        "rootPublicKeyCompiled": not development,
        "testHooksEnabled": development,
        "stagingPinnedSignerTrust": False,
        "linuxIntegrityMode": "development" if development else "content-hash-pin",
        "linuxClientSha256": ZERO if development else "aa" * 32,
        "linuxBrokerSha256": ZERO if development else "bb" * 32,
        "linuxPeerVerification": "same-user-peer-credentials",
        "linuxHostVerification": host_verification
        or ("same-user-direct-parent" if source_runtime else "content-hash-pin"),
        "securityNoticeId": "WCE-AUTOMATED-ANALYSIS-NOTICE-V2",
        "securityNoticeSha256": "55" * 32,
        "securityCheckpointSetId": "WCE-AI-CHECKPOINT-SET-V3",
        "securityCheckpointCount": 7,
        "securityCheckpointSetSha256": "66" * 32,
    }
    if source_runtime:
        manifest["sourceRuntime"] = True
    return manifest


def load_manifest(tmp_path: Path, payload: dict[str, object]):
    component = tmp_path / "libwechatdb_client.so"
    component.write_bytes(b"client")
    component.with_name("wechatdb_native_build.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return native_core_client._load_native_core_build_manifest(component)


def authorize(tmp_path: Path, payload: dict[str, object], monkeypatch: pytest.MonkeyPatch, *, frozen: bool):
    component = tmp_path / "libwechatdb_client.so"
    component.write_bytes(b"client")
    component.with_name("wechatdb_native_build.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    monkeypatch.setattr(native_core_client.sys, "platform", "linux")
    monkeypatch.setattr(
        native_core_lease,
        "validate_native_core_authorization_policy",
        lambda _manifest: None,
    )
    monkeypatch.setattr(native_core_client.sys, "frozen", frozen, raising=False)
    return native_core_client._required_native_core_build_manifest(component)


def test_linux_production_manifest_uses_content_hash_pins(tmp_path: Path) -> None:
    manifest = load_manifest(tmp_path, linux_manifest())

    assert manifest.platform == "linux"
    assert manifest.linux_integrity_mode == "content-hash-pin"
    assert manifest.linux_peer_verification == "same-user-peer-credentials"
    # Linux 没有签名者证书，client_signer_sha256 就是 client 的内容哈希。
    assert manifest.client_signer_sha256 == bytes.fromhex("aa" * 32)
    assert manifest.linux_broker_sha256 == bytes.fromhex("bb" * 32)
    assert native_core_client._is_production_native_core_build_manifest(manifest)
    assert not native_core_client._is_source_public_native_core_build_manifest(manifest)


def test_linux_source_public_manifest_retains_production_security(tmp_path: Path) -> None:
    manifest = load_manifest(tmp_path, linux_manifest(source_runtime=True))

    assert manifest.source_runtime is True
    assert manifest.linux_host_verification == "same-user-direct-parent"
    assert native_core_client._is_source_public_native_core_build_manifest(manifest)
    assert not native_core_client._is_production_native_core_build_manifest(manifest)


def test_linux_development_manifest_has_no_production_pins(tmp_path: Path) -> None:
    manifest = load_manifest(tmp_path, linux_manifest(development=True))

    assert manifest.linux_integrity_mode == "development"
    assert manifest.client_signer_sha256 == bytes(32)
    assert native_core_client._is_development_native_core_build_manifest(manifest)


def test_linux_release_ships_source_public_and_the_frozen_app_consumes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """发布工作流只发 source-public，冻结应用必须能消费它（与 Windows 同一原则）。"""
    payload = linux_manifest(source_runtime=True)

    frozen = authorize(tmp_path, payload, monkeypatch, frozen=True)
    assert frozen.source_runtime is True

    source = authorize(tmp_path, payload, monkeypatch, frozen=False)
    assert source.source_runtime is True


def test_linux_runtime_authorization_matrix_is_bound_to_frozen_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # production 只在冻结态被授权：源码 checkout 必须用受限 source-public。
    with pytest.raises(
        native_core_client.NativeCoreProtocolError,
        match="requires the exact restricted source-public",
    ):
        authorize(tmp_path, linux_manifest(), monkeypatch, frozen=False)

    # 冻结态接受 production（第二条签发路径）。
    assert authorize(tmp_path, linux_manifest(), monkeypatch, frozen=True) is not None

    # dev-local 在两种状态下都不授权（与 macOS 同一原则）。
    with pytest.raises(
        native_core_client.NativeCoreProtocolError,
        match="requires the exact restricted source-public",
    ):
        authorize(tmp_path, linux_manifest(development=True), monkeypatch, frozen=False)
    with pytest.raises(
        native_core_client.NativeCoreProtocolError,
        match="requires a production wechatdb native core",
    ):
        authorize(tmp_path, linux_manifest(development=True), monkeypatch, frozen=True)


def test_linux_manifest_platform_cannot_cross_runtime_boundaries(tmp_path: Path) -> None:
    linux = load_manifest(tmp_path, linux_manifest())

    assert native_core_client._manifest_matches_runtime_platform(linux, "linux")
    assert not native_core_client._manifest_matches_runtime_platform(linux, "darwin")
    assert not native_core_client._manifest_matches_runtime_platform(linux, "win32")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        # 宿主校验强度必须与 sourceRuntime 配对。
        ("linuxHostVerification", "content-hash-pin"),
        # 内容哈希不得为零，也不得让 client 与 broker 撞哈希。
        ("linuxClientSha256", ZERO),
        ("linuxBrokerSha256", "aa" * 32),
        # Linux 清单不得夹带 Windows / macOS 的签名身份字段。
        ("windowsClientSignerSha256", "11" * 32),
        ("macosClientSignerSha256", "11" * 32),
        ("platform", "macos"),
    ),
)
def test_linux_source_public_manifest_rejects_identity_substitution(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = linux_manifest(source_runtime=True)
    payload[field] = value
    with pytest.raises(native_core_client.NativeCoreProtocolError):
        load_manifest(tmp_path, payload)


def test_linux_manifest_rejects_development_integrity_with_production_pins(
    tmp_path: Path,
) -> None:
    payload = linux_manifest(development=True)
    payload["linuxClientSha256"] = "aa" * 32
    with pytest.raises(native_core_client.NativeCoreProtocolError):
        load_manifest(tmp_path, payload)
