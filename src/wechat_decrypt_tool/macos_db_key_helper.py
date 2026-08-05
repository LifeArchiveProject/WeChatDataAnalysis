from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from .platform_support import mac_db_key_bundle_dir


_CONTRACT_PATH = Path(__file__).resolve().parent / "resources" / "macos_db_key_contract.json"
_MAX_JSON_FILE_BYTES = 64 * 1024
_MAX_STDERR_BYTES = 16 * 1024
_MAX_STDOUT_BYTES = 66
_BUILD_LIFETIME_SECONDS = 45 * 24 * 60 * 60
_CLOCK_SKEW_SECONDS = 5 * 60
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_BUILD_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}")
_DNS_REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_KEY_LINE_RE = re.compile(rb"[0-9a-f]{64}\n")
_SECRET_HEX_RE = re.compile(rb"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")


class MacosDbKeyError(RuntimeError):
    def __init__(self, message: str, *, code: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class MacosDbKeyUnavailableError(MacosDbKeyError):
    pass


class MacosDbKeyIntegrityError(MacosDbKeyError):
    pass


class MacosDbKeyAuthorizationError(MacosDbKeyError):
    pass


class MacosDbKeyTimeoutError(TimeoutError, MacosDbKeyError):
    def __init__(self, message: str = "macOS 数据库密钥获取超时，请确认微信仍在运行后重试。") -> None:
        MacosDbKeyError.__init__(self, message, code="TIMEOUT", retryable=True)


class MacosDbKeyReloginRequiredError(TimeoutError, MacosDbKeyError):
    def __init__(self) -> None:
        MacosDbKeyError.__init__(
            self,
            (
                "微信当前会话已完成数据库密钥初始化，本次没有产生新的密钥派生调用。"
                "请重新点击获取，并在按钮显示“获取中”后的 60 秒内仅退出当前微信账号再重新登录；"
                "不要退出微信程序或关闭 WCDA。"
            ),
            code="WECHAT_RELOGIN_REQUIRED",
            retryable=True,
        )


class MacosDbKeyCancelledError(MacosDbKeyError):
    def __init__(self) -> None:
        super().__init__("macOS 数据库密钥获取已停止。", code="CANCELLED", retryable=True)


def _reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def _strict_json_bytes(raw: bytes, *, label: str) -> dict[str, object]:
    if not raw or len(raw) > _MAX_JSON_FILE_BYTES:
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}无效，请重新安装正式版本。",
            code="INVALID_SCHEMA",
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}格式错误，请重新安装正式版本。",
            code="INVALID_SCHEMA",
        ) from exc
    if not isinstance(value, dict):
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}格式错误，请重新安装正式版本。",
            code="INVALID_SCHEMA",
        )
    return value


def _read_json_file(path: Path, *, label: str) -> tuple[bytes, dict[str, object]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MacosDbKeyUnavailableError(
            f"macOS 数据库密钥组件缺少{label}，请重新安装完整发行包。",
            code="MISSING_RESOURCE",
        ) from exc
    return raw, _strict_json_bytes(raw, label=label)


def _exact_keys(value: object, expected: set[str], *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}字段不匹配，请更新正式版本。",
            code="INVALID_SCHEMA",
        )
    return value


def _text(value: object, *, label: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}无效。", code="INVALID_SCHEMA"
        )
    if pattern is not None and pattern.fullmatch(value) is None:
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}格式错误。", code="INVALID_SCHEMA"
        )
    return value


def _integer(value: object, *, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise MacosDbKeyIntegrityError(
            f"macOS 数据库密钥组件的{label}无效。", code="INVALID_SCHEMA"
        )
    return value


_contract_raw, CONTRACT = _read_json_file(_CONTRACT_PATH, label="公共调用契约")
_exact_keys(
    CONTRACT,
    {
        "schemaVersion",
        "artifactName",
        "appId",
        "bundleRelativePath",
        "helperFileName",
        "manifestFileName",
        "trustFileName",
        "checksumsFileName",
        "provenanceFileName",
        "thirdPartyNoticeFileName",
        "bundleId",
        "hostSigningIdentifier",
        "requiredArchitectures",
        "minimumTimeoutMs",
        "maximumTimeoutMs",
    },
    label="公共调用契约",
)
if CONTRACT.get("schemaVersion") != 2:
    raise MacosDbKeyIntegrityError(
        "macOS 数据库密钥公共调用契约版本不受支持。", code="CONTRACT_MISMATCH"
    )

ARTIFACT_NAME = str(CONTRACT["artifactName"])
SOURCE_PUBLIC_ARTIFACT_NAME = "wda-xkey-macos-universal-source-public"
APP_ID = str(CONTRACT["appId"])
HELPER_FILE_NAME = str(CONTRACT["helperFileName"])
MANIFEST_FILE_NAME = str(CONTRACT["manifestFileName"])
TRUST_FILE_NAME = str(CONTRACT["trustFileName"])
CHECKSUMS_FILE_NAME = str(CONTRACT["checksumsFileName"])
PROVENANCE_FILE_NAME = str(CONTRACT["provenanceFileName"])
THIRD_PARTY_NOTICE_FILE_NAME = str(CONTRACT["thirdPartyNoticeFileName"])
HELPER_BUNDLE_ID = str(CONTRACT["bundleId"])
HOST_SIGNING_IDENTIFIER = str(CONTRACT["hostSigningIdentifier"])
REQUIRED_ARCHITECTURES = frozenset(str(item) for item in CONTRACT["requiredArchitectures"])
MINIMUM_TIMEOUT_MS = int(CONTRACT["minimumTimeoutMs"])
MAXIMUM_TIMEOUT_MS = int(CONTRACT["maximumTimeoutMs"])
BUILD_LIFETIME_SECONDS = _BUILD_LIFETIME_SECONDS


@dataclass(frozen=True)
class MacosCodeSignatureInfo:
    identifier: str
    leaf_sha256: str
    architectures: frozenset[str]


@dataclass(frozen=True)
class ValidatedMacosDbKeyBundle:
    root: Path
    helper_path: Path
    manifest_path: Path
    trust_path: Path
    build_id: str
    source_revision: str
    producer_workflow_run_id: int
    build_issued_at_unix: int
    build_expires_at_unix: int
    development_build: bool
    signature_mode: str
    helper_signer_sha256: str
    host_signer_sha256: str
    helper_bundle_id: str
    host_signing_identifier: str
    manifest: Mapping[str, object]
    source_runtime: bool = False


@dataclass(frozen=True)
class MacosDbKeyBundleStatus:
    available: bool
    note: str
    build_id: str = ""
    build_expires_at_unix: int | None = None
    error_code: str = ""

    def as_capability(self) -> dict[str, object]:
        return {
            "available": self.available,
            "note": self.note,
            "build_id": self.build_id,
            "build_expires_at_unix": self.build_expires_at_unix,
            "error_code": self.error_code,
        }


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise MacosDbKeyUnavailableError(
            "macOS 数据库密钥本地组件不可读取，请重新安装完整发行包。",
            code="MISSING_RESOURCE",
        ) from exc
    return digest.hexdigest(), size


def _default_code_signature_verifier(helper_path: Path) -> MacosCodeSignatureInfo:
    if sys.platform != "darwin":
        raise MacosDbKeyUnavailableError(
            "macOS 数据库密钥组件只能在 macOS 上校验。", code="UNSUPPORTED_PLATFORM"
        )
    try:
        verified = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", "--verbose=2", str(helper_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        if verified.returncode != 0:
            raise OSError("codesign verify failed")
        details = subprocess.run(
            ["/usr/bin/codesign", "-d", "--verbose=4", str(helper_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        detail_text = (details.stdout + details.stderr)[:_MAX_STDERR_BYTES].decode(
            "utf-8", errors="replace"
        )
        identifier_match = re.search(r"(?m)^Identifier=([^\r\n]+)$", detail_text)
        if details.returncode != 0 or not identifier_match:
            raise OSError("codesign details failed")
        with tempfile.TemporaryDirectory(prefix="wda-xkey-cert-") as temp_dir:
            extracted = subprocess.run(
                ["/usr/bin/codesign", "--display", "--extract-certificates", str(helper_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=temp_dir,
                timeout=15,
                check=False,
            )
            cert_path = Path(temp_dir) / "codesign0"
            if extracted.returncode != 0 or not cert_path.is_file():
                raise OSError("codesign certificate extraction failed")
            certificate = x509.load_der_x509_certificate(cert_path.read_bytes())
            leaf_sha256 = certificate.fingerprint(hashes.SHA256()).hex()
        archs = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(helper_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        if archs.returncode != 0:
            raise OSError("lipo failed")
        architectures = frozenset(archs.stdout.decode("ascii", errors="ignore").split())
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的代码签名无效，请重新安装正式版本。",
            code="INVALID_CODE_SIGNATURE",
        ) from exc
    return MacosCodeSignatureInfo(
        identifier=identifier_match.group(1).strip(),
        leaf_sha256=leaf_sha256,
        architectures=architectures,
    )


def _parse_checksums(path: Path) -> dict[str, str]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > _MAX_JSON_FILE_BYTES:
            raise OSError("invalid size")
        lines = raw.decode("ascii").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的校验和清单无效。", code="INVALID_CHECKSUMS"
        ) from exc
    result: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
        if match is None or match.group(2) in result or ".." in Path(match.group(2)).parts:
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件的校验和清单格式错误。", code="INVALID_CHECKSUMS"
            )
        result[match.group(2)] = match.group(1)
    if list(result) != sorted(result):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的校验和清单顺序无效。", code="INVALID_CHECKSUMS"
        )
    return result


def validate_macos_db_key_bundle(
    root: Path | None = None,
    *,
    now_unix: int | None = None,
    code_signature_verifier: Callable[[Path], MacosCodeSignatureInfo] | None = None,
) -> ValidatedMacosDbKeyBundle:
    bundle_root = Path(root or mac_db_key_bundle_dir()).expanduser().resolve()
    helper_path = bundle_root / HELPER_FILE_NAME
    manifest_path = bundle_root / MANIFEST_FILE_NAME
    trust_path = bundle_root / TRUST_FILE_NAME
    expected_files = {
        HELPER_FILE_NAME,
        MANIFEST_FILE_NAME,
        TRUST_FILE_NAME,
        CHECKSUMS_FILE_NAME,
        PROVENANCE_FILE_NAME,
        THIRD_PARTY_NOTICE_FILE_NAME,
    }
    try:
        actual_files: set[str] = set()
        for candidate in bundle_root.rglob("*"):
            if candidate.is_symlink():
                raise OSError("symlink")
            if candidate.is_file():
                actual_files.add(candidate.relative_to(bundle_root).as_posix())
        if actual_files != expected_files:
            raise OSError("file allowlist mismatch")
    except OSError as exc:
        raise MacosDbKeyUnavailableError(
            "macOS 数据库密钥组件安装不完整，请重新安装正式版本。",
            code="MISSING_RESOURCE",
        ) from exc

    manifest_raw, manifest = _read_json_file(manifest_path, label="构建清单")
    trust_raw, trust = _read_json_file(trust_path, label="打包信任配置")
    _provenance_raw, provenance = _read_json_file(
        bundle_root / PROVENANCE_FILE_NAME, label="生产溯源"
    )
    base_manifest_keys = {
        "schemaVersion", "artifactType", "artifactName", "distributionMode",
        "platform", "architecture", "architectures", "appId", "sourceRevision",
        "build", "authorizationMode", "onlineRequired", "signing", "files",
    }
    source_field_names = {
        name for name in ("sourceRuntime", "hostVerification") if name in manifest
    }
    source_runtime = bool(source_field_names)
    if source_runtime:
        _exact_keys(
            manifest,
            base_manifest_keys | {"sourceRuntime", "hostVerification"},
            label="构建清单",
        )
        if (
            getattr(sys, "frozen", False)
            or manifest.get("sourceRuntime") is not True
            or manifest.get("hostVerification") != "same-user-direct-parent"
        ):
            raise MacosDbKeyIntegrityError(
                "macOS 源码数据库密钥组件的宿主校验策略无效。",
                code="MANIFEST_MISMATCH",
            )
        expected_artifact_name = SOURCE_PUBLIC_ARTIFACT_NAME
    else:
        _exact_keys(manifest, base_manifest_keys, label="构建清单")
        expected_artifact_name = ARTIFACT_NAME
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("artifactType") != "wda-xkey-macos-key-capture"
        or manifest.get("artifactName") != expected_artifact_name
        or manifest.get("distributionMode") != "public"
        or manifest.get("platform") != "macos"
        or manifest.get("architecture") != "universal2"
        or manifest.get("architectures") != ["arm64", "x86_64"]
        or manifest.get("appId") != APP_ID
        or manifest.get("authorizationMode") != "embedded-private"
        or manifest.get("onlineRequired") is not True
    ):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的构建清单与当前应用不匹配。", code="MANIFEST_MISMATCH"
        )
    source_revision = _text(
        manifest.get("sourceRevision"), label="sourceRevision", pattern=_SOURCE_REVISION_RE
    )
    build = _exact_keys(
        manifest.get("build"),
        {"id", "issuedAtUnix", "expiresAtUnix", "validitySeconds", "development"},
        label="build",
    )
    build_id = _text(build.get("id"), label="build.id", pattern=_BUILD_ID_RE)
    issued_at = _integer(build.get("issuedAtUnix"), label="build.issuedAtUnix", minimum=1)
    expires_at = _integer(build.get("expiresAtUnix"), label="build.expiresAtUnix", minimum=1)
    development = build.get("development")
    if (
        build.get("validitySeconds") != _BUILD_LIFETIME_SECONDS
        or expires_at != issued_at + _BUILD_LIFETIME_SECONDS
        or type(development) is not bool
    ):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的固定有效期不是 45 天。", code="INVALID_BUILD_WINDOW"
        )
    allow_development = (
        not getattr(sys, "frozen", False)
        and os.environ.get("WCE_MACOS_XKEY_ALLOW_DEVELOPMENT_ARTIFACTS", "").strip() == "1"
        and not os.environ.get("CI", "").strip()
    )
    if development and not allow_development:
        raise MacosDbKeyIntegrityError(
            "正式应用拒绝加载开发版 macOS 数据库密钥组件。",
            code="DEVELOPMENT_BUILD_REJECTED",
        )
    if source_runtime and development:
        raise MacosDbKeyIntegrityError(
            "macOS 源码数据库密钥组件必须保留正式生产安全配置。",
            code="DEVELOPMENT_BUILD_REJECTED",
        )
    current_time = int(time.time()) if now_unix is None else int(now_unix)
    if current_time < issued_at - _CLOCK_SKEW_SECONDS:
        raise MacosDbKeyIntegrityError(
            "本机时间早于组件签发时间，请校准系统时间后重试。", code="CLOCK_ROLLBACK"
        )
    if current_time >= expires_at:
        raise MacosDbKeyUnavailableError(
            "当前版本的 macOS 数据库密钥组件已过期，请更新到最新正式版本。",
            code="BUILD_EXPIRED",
        )

    signing = _exact_keys(
        manifest.get("signing"),
        {
            "mode", "helperLeafCertificateSha256", "hostLeafCertificateSha256",
            "teamId", "hardenedRuntime", "timestamped", "notarized",
        },
        label="signing",
    )
    signature_mode = _text(signing.get("mode"), label="signing.mode")
    allowed_modes = {"adhoc"} if development else {"self-signed", "developer-id"}
    helper_signer = _text(
        signing.get("helperLeafCertificateSha256"),
        label="signing.helperLeafCertificateSha256",
        pattern=_SHA256_RE,
    )
    host_signer = _text(
        signing.get("hostLeafCertificateSha256"),
        label="signing.hostLeafCertificateSha256",
        pattern=_SHA256_RE,
    )
    if (
        signature_mode not in allowed_modes
        or helper_signer == "0" * 64
        or host_signer == "0" * 64
        or helper_signer == host_signer
        or signing.get("hardenedRuntime") is not True
        or type(signing.get("timestamped")) is not bool
        or type(signing.get("notarized")) is not bool
        or (signature_mode == "self-signed" and signing.get("timestamped") is not False)
        or (signature_mode == "self-signed" and signing.get("notarized") is not False)
        or (signature_mode == "developer-id" and signing.get("timestamped") is not True)
        or (signature_mode == "developer-id" and not str(signing.get("teamId") or "").strip())
    ):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的签名声明无效。", code="SIGNER_MISMATCH"
        )

    files = _exact_keys(
        manifest.get("files"), {HELPER_FILE_NAME, THIRD_PARTY_NOTICE_FILE_NAME}, label="files"
    )
    expected_payload_files = {HELPER_FILE_NAME, THIRD_PARTY_NOTICE_FILE_NAME}
    checksums_path = bundle_root / CHECKSUMS_FILE_NAME
    checksums = _parse_checksums(checksums_path)
    expected_checksum_files = expected_payload_files | {MANIFEST_FILE_NAME, TRUST_FILE_NAME}
    if set(checksums) != expected_checksum_files:
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的校验和覆盖范围不匹配。", code="INVALID_CHECKSUMS"
        )
    for name in sorted(expected_payload_files):
        metadata = _exact_keys(files.get(name), {"sha256", "size"}, label=f"files.{name}")
        expected_sha = _text(metadata.get("sha256"), label=f"files.{name}.sha256", pattern=_SHA256_RE)
        expected_size = _integer(metadata.get("size"), label=f"files.{name}.size", minimum=1)
        actual_sha, actual_size = _sha256_file(bundle_root / name)
        if actual_sha != expected_sha or actual_size != expected_size or checksums.get(name) != actual_sha:
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件已被修改，请重新安装正式版本。",
                code="HELPER_TAMPERED" if name == HELPER_FILE_NAME else "RESOURCE_TAMPERED",
            )
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    trust_sha = hashlib.sha256(trust_raw).hexdigest()
    if checksums.get(MANIFEST_FILE_NAME) != manifest_sha or checksums.get(TRUST_FILE_NAME) != trust_sha:
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的构建信任元数据已被修改。", code="RESOURCE_TAMPERED"
        )

    _exact_keys(
        trust,
        {
            "schemaVersion", "artifactName", "sourceRevision", "buildId", "appId",
            "producerRepository", "producerWorkflowRunId", "helperIdentifier",
            "helperLeafCertificateSha256", "hostIdentifier", "hostLeafCertificateSha256",
            "signingMode", "manifestSha256",
        },
        label="打包信任配置",
    )
    producer_repository = _text(
        trust.get("producerRepository"), label="producerRepository", pattern=_DNS_REPOSITORY_RE
    )
    producer_run_id = _integer(
        trust.get("producerWorkflowRunId"), label="producerWorkflowRunId", minimum=1
    )
    if (
        trust.get("schemaVersion") != 1
        or trust.get("artifactName") != expected_artifact_name
        or trust.get("appId") != APP_ID
        or trust.get("sourceRevision") != source_revision
        or trust.get("buildId") != build_id
        or trust.get("manifestSha256") != manifest_sha
        or trust.get("helperIdentifier") != HELPER_BUNDLE_ID
        or trust.get("hostIdentifier") != HOST_SIGNING_IDENTIFIER
        or trust.get("helperLeafCertificateSha256") != helper_signer
        or trust.get("hostLeafCertificateSha256") != host_signer
        or trust.get("signingMode") != signature_mode
    ):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的生产信任配置不匹配。", code="TRUST_MISMATCH"
        )

    _exact_keys(
        provenance,
        {
            "schemaVersion", "producer", "workflow", "repository", "runId", "runAttempt",
            "sourceRevision", "buildId", "artifactName", "manifestSha256",
            "trustSha256", "checksumsSha256",
        },
        label="生产溯源",
    )
    checksums_sha, _ = _sha256_file(checksums_path)
    if (
        provenance.get("schemaVersion") != 1
        or provenance.get("producer") != "github-actions"
        or provenance.get("workflow") != ".github/workflows/macos-key-capture-production.yml"
        or provenance.get("repository") != producer_repository
        or provenance.get("runId") != producer_run_id
        or type(provenance.get("runAttempt")) is not int
        or int(provenance.get("runAttempt", 0)) <= 0
        or provenance.get("sourceRevision") != source_revision
        or provenance.get("buildId") != build_id
        or provenance.get("artifactName") != expected_artifact_name
        or provenance.get("manifestSha256") != manifest_sha
        or provenance.get("trustSha256") != trust_sha
        or provenance.get("checksumsSha256") != checksums_sha
    ):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件与固定生产构建溯源不一致。",
            code="PRODUCER_PIN_MISMATCH",
        )

    signature = (code_signature_verifier or _default_code_signature_verifier)(helper_path)
    if (
        signature.identifier != HELPER_BUNDLE_ID
        or signature.leaf_sha256 != helper_signer
        or not REQUIRED_ARCHITECTURES.issubset(signature.architectures)
    ):
        raise MacosDbKeyIntegrityError(
            "macOS 数据库密钥组件的代码签名或 Universal2 架构不匹配。",
            code="INVALID_CODE_SIGNATURE",
        )
    return ValidatedMacosDbKeyBundle(
        root=bundle_root,
        helper_path=helper_path,
        manifest_path=manifest_path,
        trust_path=trust_path,
        build_id=build_id,
        source_revision=source_revision,
        producer_workflow_run_id=producer_run_id,
        build_issued_at_unix=issued_at,
        build_expires_at_unix=expires_at,
        development_build=bool(development),
        signature_mode=signature_mode,
        helper_signer_sha256=helper_signer,
        host_signer_sha256=host_signer,
        helper_bundle_id=HELPER_BUNDLE_ID,
        host_signing_identifier=HOST_SIGNING_IDENTIFIER,
        manifest=manifest,
        source_runtime=source_runtime,
    )


def inspect_macos_db_key_bundle() -> MacosDbKeyBundleStatus:
    try:
        bundle = validate_macos_db_key_bundle()
    except MacosDbKeyError as exc:
        return MacosDbKeyBundleStatus(False, str(exc), error_code=exc.code)
    except Exception:
        return MacosDbKeyBundleStatus(
            False,
            "macOS 数据库密钥本地组件校验失败，请更新或重新安装正式版本。",
            error_code="INTERNAL_VALIDATION_ERROR",
        )
    return MacosDbKeyBundleStatus(
        True,
        "macOS 数据库密钥获取组件已就绪；获取时需要联网完成安全校验。",
        build_id=bundle.build_id,
        build_expires_at_unix=bundle.build_expires_at_unix,
    )


def _sanitized_helper_environment() -> dict[str, str]:
    source = os.environ
    environment: dict[str, str] = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": str(source.get("LANG", "en_US.UTF-8") or "en_US.UTF-8"),
    }
    for name in ("HOME", "TMPDIR", "LC_ALL"):
        value = str(source.get(name, "") or "").strip()
        if value and "\x00" not in value:
            environment[name] = value
    return environment


@dataclass
class _BoundedPipe:
    limit: int
    secret_scan: bool = False
    data: bytearray = None  # type: ignore[assignment]
    overflow: bool = False
    secret_found: bool = False
    total: int = 0

    def __post_init__(self) -> None:
        self.data = bytearray()

    def read(self, stream: object) -> None:
        tail = b""
        try:
            while True:
                chunk = stream.read(4096)  # type: ignore[attr-defined]
                if not chunk:
                    return
                self.total += len(chunk)
                if self.total > self.limit:
                    self.overflow = True
                if len(self.data) < self.limit + 1:
                    remaining = self.limit + 1 - len(self.data)
                    self.data.extend(chunk[:remaining])
                if self.secret_scan:
                    window = tail + chunk
                    if _SECRET_HEX_RE.search(window):
                        self.secret_found = True
                    tail = window[-63:]
        except Exception:
            self.overflow = True


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if sys.platform != "win32":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=1)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=1)
        except Exception:
            pass


def _run_capture_helper(
    bundle: ValidatedMacosDbKeyBundle,
    *,
    pid: int,
    timeout_ms: int,
    cancel_event: threading.Event | None,
    deadline_monotonic: float,
    popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> str:
    argv = [
        str(bundle.helper_path),
        "--capture",
        "--pid",
        str(pid),
        "--timeout-ms",
        str(timeout_ms),
    ]
    try:
        process = popen_factory(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_sanitized_helper_environment(),
            cwd=str(bundle.root),
            start_new_session=True,
            bufsize=0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MacosDbKeyUnavailableError(
            "无法启动 macOS 数据库密钥组件，请重新安装正式版本。",
            code="HELPER_START_FAILED",
        ) from exc
    stdout = _BoundedPipe(_MAX_STDOUT_BYTES)
    stderr = _BoundedPipe(_MAX_STDERR_BYTES, secret_scan=True)
    stdout_thread = threading.Thread(target=stdout.read, args=(process.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=stderr.read, args=(process.stderr,), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process(process)
                raise MacosDbKeyCancelledError()
            if time.monotonic() >= deadline_monotonic:
                _terminate_process(process)
                raise MacosDbKeyTimeoutError()
            time.sleep(0.05)
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            _terminate_process(process)
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件输出未能正常结束。", code="PROTOCOL_ERROR"
            )
        if stderr.secret_found or stderr.overflow:
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件违反了安全输出约束。", code="SECRET_OUTPUT_VIOLATION"
            )
        output = bytes(stdout.data)
        return_code = int(process.returncode or 0)
        if return_code == 0:
            if stdout.overflow or _KEY_LINE_RE.fullmatch(output) is None:
                raise MacosDbKeyIntegrityError(
                    "macOS 数据库密钥组件返回了无效结果。", code="PROTOCOL_ERROR"
                )
            return output[:-1].decode("ascii")
        if output or stdout.overflow:
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件失败时返回了意外数据。", code="PROTOCOL_ERROR"
            )
        if return_code == 20:
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件完整性校验失败，请更新或重新安装正式版本。",
                code="HELPER_INTEGRITY_FAILURE",
            )
        if return_code == 21:
            raise MacosDbKeyIntegrityError(
                "macOS 数据库密钥组件调用参数无效。", code="HELPER_ARGUMENT_ERROR"
            )
        if return_code == 22:
            raise MacosDbKeyAuthorizationError(
                "macOS 数据库密钥在线安全校验未完成，请检查网络或联系开发者。",
                code="AUTHORIZATION_UNAVAILABLE",
                retryable=True,
            )
        if return_code == 23:
            raise MacosDbKeyUnavailableError(
                "当前微信进程未能获取数据库密钥，请保持微信运行后重试。",
                code="CAPTURE_FAILED",
                retryable=True,
            )
        if return_code == 24:
            raise MacosDbKeyTimeoutError()
        if return_code == 25:
            raise MacosDbKeyReloginRequiredError()
        raise MacosDbKeyUnavailableError(
            "macOS 数据库密钥组件意外退出。", code="HELPER_EXITED", retryable=True
        )
    finally:
        _terminate_process(process)
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass


def capture_macos_database_key(
    *,
    timeout_seconds: float = 120.0,
    cancel_event: threading.Event | None = None,
    pid_provider: Callable[[], tuple[int, ...]] | None = None,
    bundle: ValidatedMacosDbKeyBundle | None = None,
    helper_runner: Callable[..., str] = _run_capture_helper,
) -> dict[str, object]:
    if sys.platform != "darwin" and bundle is None:
        raise MacosDbKeyUnavailableError(
            "当前平台不支持 macOS 数据库密钥获取。", code="UNSUPPORTED_PLATFORM"
        )
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be numeric") from exc
    if timeout < 1 or timeout > MAXIMUM_TIMEOUT_MS / 1000:
        raise ValueError(f"timeout_seconds must be between 1 and {MAXIMUM_TIMEOUT_MS / 1000:g}")
    validated = bundle or validate_macos_db_key_bundle()
    deadline = time.monotonic() + timeout
    if pid_provider is None:
        from .image_key_memory_scan import find_wechat_pids

        pid_provider = find_wechat_pids
    pids = tuple(sorted({int(pid) for pid in pid_provider() if int(pid) > 0}))
    if not pids:
        raise MacosDbKeyUnavailableError(
            "未找到运行中的微信，请先登录微信后重试。",
            code="PROCESS_NOT_FOUND",
            retryable=True,
        )
    last_capture_error: MacosDbKeyUnavailableError | None = None
    for pid in pids:
        remaining_ms = min(
            MAXIMUM_TIMEOUT_MS,
            int(max(0.0, deadline - time.monotonic()) * 1000),
        )
        if remaining_ms < MINIMUM_TIMEOUT_MS:
            raise MacosDbKeyTimeoutError()
        try:
            key = helper_runner(
                validated,
                pid=pid,
                timeout_ms=remaining_ms,
                cancel_event=cancel_event,
                deadline_monotonic=deadline,
            )
            if re.fullmatch(r"[0-9a-f]{64}", key) is None:
                raise MacosDbKeyIntegrityError(
                    "macOS 数据库密钥组件返回了无效结果。", code="PROTOCOL_ERROR"
                )
            return {
                "db_key": key,
                "method": "macos_private_helper",
                "pid": pid,
                "build_id": validated.build_id,
            }
        except MacosDbKeyUnavailableError as exc:
            if exc.code == "CAPTURE_FAILED" and len(pids) > 1:
                last_capture_error = exc
                continue
            raise
    if last_capture_error is not None:
        raise last_capture_error
    raise MacosDbKeyUnavailableError(
        "macOS 数据库密钥组件未找到可用的微信进程。",
        code="PROCESS_NOT_FOUND",
        retryable=True,
    )


__all__ = [
    "APP_ID",
    "ARTIFACT_NAME",
    "SOURCE_PUBLIC_ARTIFACT_NAME",
    "CONTRACT",
    "HELPER_BUNDLE_ID",
    "HOST_SIGNING_IDENTIFIER",
    "MacosCodeSignatureInfo",
    "MacosDbKeyAuthorizationError",
    "MacosDbKeyBundleStatus",
    "MacosDbKeyCancelledError",
    "MacosDbKeyError",
    "MacosDbKeyIntegrityError",
    "MacosDbKeyReloginRequiredError",
    "MacosDbKeyTimeoutError",
    "MacosDbKeyUnavailableError",
    "ValidatedMacosDbKeyBundle",
    "capture_macos_database_key",
    "inspect_macos_db_key_bundle",
    "validate_macos_db_key_bundle",
]
