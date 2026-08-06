import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import macos_db_key_helper as helper


ISSUED_AT = 1_900_000_000
EXPIRES_AT = ISSUED_AT + helper.BUILD_LIFETIME_SECONDS
BUILD_NAME = "wda-xkey-20260803"
SOURCE_REVISION = "a" * 40
HELPER_SIGNER = "2" * 64
HOST_SIGNER = "3" * 64


def _metadata(path: Path) -> dict[str, object]:
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }


def _write_bundle(
    root: Path, *, source_runtime: bool = False
) -> tuple[Path, dict[str, object]]:
    root.mkdir(parents=True, exist_ok=True)
    helper_path = root / helper.HELPER_FILE_NAME
    helper_path.write_bytes(b"universal-macho-test-fixture")
    notice_path = root / helper.THIRD_PARTY_NOTICE_FILE_NAME
    notice_path.parent.mkdir(parents=True)
    notice_path.write_text("Frida test license\n", encoding="utf-8")
    artifact_name = (
        helper.SOURCE_PUBLIC_ARTIFACT_NAME if source_runtime else helper.ARTIFACT_NAME
    )
    manifest: dict[str, object] = {
        "schemaVersion": 2,
        "artifactType": "wda-xkey-macos-key-capture",
        "artifactName": artifact_name,
        "distributionMode": "public",
        "platform": "macos",
        "architecture": "universal2",
        "architectures": ["arm64", "x86_64"],
        "appId": helper.APP_ID,
        "sourceRevision": SOURCE_REVISION,
        "build": {
            "id": BUILD_NAME,
            "issuedAtUnix": ISSUED_AT,
            "expiresAtUnix": EXPIRES_AT,
            "validitySeconds": helper.BUILD_LIFETIME_SECONDS,
            "development": False,
        },
        "authorizationMode": "local-process-policy",
        "onlineRequired": False,
        "signing": {
            "mode": "self-signed",
            "helperLeafCertificateSha256": HELPER_SIGNER,
            "hostLeafCertificateSha256": HOST_SIGNER,
            "teamId": "",
            "hardenedRuntime": True,
            "timestamped": False,
            "notarized": False,
        },
        "files": {
            helper.HELPER_FILE_NAME: _metadata(helper_path),
            helper.THIRD_PARTY_NOTICE_FILE_NAME: _metadata(notice_path),
        },
    }
    if source_runtime:
        manifest["sourceRuntime"] = True
        manifest["hostVerification"] = "same-user-direct-parent"
    manifest_path = root / helper.MANIFEST_FILE_NAME
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    trust = {
        "schemaVersion": 1,
        "artifactName": artifact_name,
        "sourceRevision": SOURCE_REVISION,
        "buildId": BUILD_NAME,
        "appId": helper.APP_ID,
        "producerRepository": "owner/private-producer",
        "producerWorkflowRunId": 123456,
        "helperIdentifier": helper.HELPER_BUNDLE_ID,
        "helperLeafCertificateSha256": HELPER_SIGNER,
        "hostIdentifier": helper.HOST_SIGNING_IDENTIFIER,
        "hostLeafCertificateSha256": HOST_SIGNER,
        "signingMode": "self-signed",
        "manifestSha256": manifest_sha,
    }
    trust_path = root / helper.TRUST_FILE_NAME
    trust_path.write_text(json.dumps(trust, separators=(",", ":")), encoding="utf-8")
    checksummed = [
        helper.THIRD_PARTY_NOTICE_FILE_NAME,
        helper.MANIFEST_FILE_NAME,
        helper.TRUST_FILE_NAME,
        helper.HELPER_FILE_NAME,
    ]
    checksums_path = root / helper.CHECKSUMS_FILE_NAME
    checksums_path.write_text(
        "".join(f"{_metadata(root / name)['sha256']}  {name}\n" for name in sorted(checksummed)),
        encoding="ascii",
    )
    provenance = {
        "schemaVersion": 1,
        "producer": "github-actions",
        "workflow": ".github/workflows/macos-key-capture-production.yml",
        "repository": "owner/private-producer",
        "runId": 123456,
        "runAttempt": 1,
        "sourceRevision": SOURCE_REVISION,
        "buildId": BUILD_NAME,
        "artifactName": artifact_name,
        "manifestSha256": manifest_sha,
        "trustSha256": hashlib.sha256(trust_path.read_bytes()).hexdigest(),
        "checksumsSha256": hashlib.sha256(checksums_path.read_bytes()).hexdigest(),
    }
    (root / helper.PROVENANCE_FILE_NAME).write_text(
        json.dumps(provenance, separators=(",", ":")), encoding="utf-8"
    )
    return helper_path, manifest


def _signature_info() -> helper.MacosCodeSignatureInfo:
    return helper.MacosCodeSignatureInfo(
        identifier=helper.HELPER_BUNDLE_ID,
        leaf_sha256=HELPER_SIGNER,
        architectures=frozenset({"arm64", "x86_64"}),
    )


def test_default_signature_verifier_uses_system_certificate_export_convention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    helper_path = tmp_path / helper.HELPER_FILE_NAME
    helper_path.write_bytes(b"signed-macho-test-fixture")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        if "--extract-certificates" in argv:
            Path(kwargs["cwd"], "codesign0").write_bytes(b"test-certificate")
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if "--verbose=4" in argv:
            return SimpleNamespace(
                returncode=0,
                stdout=b"",
                stderr=f"Identifier={helper.HELPER_BUNDLE_ID}\n".encode("ascii"),
            )
        if argv[:2] == ["/usr/bin/lipo", "-archs"]:
            return SimpleNamespace(returncode=0, stdout=b"arm64 x86_64\n", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    class FakeCertificate:
        @staticmethod
        def fingerprint(_algorithm) -> bytes:
            return bytes.fromhex(HELPER_SIGNER)

    monkeypatch.setattr(helper.sys, "platform", "darwin")
    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    monkeypatch.setattr(
        helper.x509, "load_der_x509_certificate", lambda raw: FakeCertificate()
    )

    signature = helper._default_code_signature_verifier(helper_path)

    extraction = next(call for call in calls if "--extract-certificates" in call[0])
    assert extraction[0] == [
        "/usr/bin/codesign",
        "--display",
        "--extract-certificates",
        str(helper_path),
    ]
    assert Path(str(extraction[1]["cwd"])).name.startswith("wda-xkey-cert-")
    assert signature == _signature_info()


def _validated_bundle(tmp_path: Path) -> helper.ValidatedMacosDbKeyBundle:
    _write_bundle(tmp_path)
    return helper.validate_macos_db_key_bundle(
        tmp_path,
        now_unix=ISSUED_AT + 1,
        code_signature_verifier=lambda _path: _signature_info(),
    )


def test_validate_bundle_accepts_minimal_signed_producer_artifact(tmp_path: Path):
    bundle = _validated_bundle(tmp_path)

    assert bundle.build_id == BUILD_NAME
    assert bundle.source_revision == SOURCE_REVISION
    assert bundle.helper_signer_sha256 == HELPER_SIGNER
    assert set(bundle.manifest) == {
        "schemaVersion", "artifactType", "artifactName", "distributionMode", "platform",
        "architecture", "architectures", "appId", "sourceRevision", "build",
        "authorizationMode", "onlineRequired", "signing", "files",
    }


def test_validate_bundle_accepts_restricted_source_public_artifact(tmp_path: Path):
    _write_bundle(tmp_path, source_runtime=True)
    bundle = helper.validate_macos_db_key_bundle(
        tmp_path,
        now_unix=ISSUED_AT + 1,
        code_signature_verifier=lambda _path: _signature_info(),
    )

    assert bundle.source_runtime is True
    assert bundle.manifest["artifactName"] == helper.SOURCE_PUBLIC_ARTIFACT_NAME
    assert bundle.manifest["hostVerification"] == "same-user-direct-parent"


def test_validate_bundle_rejects_source_public_artifact_in_frozen_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _write_bundle(tmp_path, source_runtime=True)
    monkeypatch.setattr(helper.sys, "frozen", True, raising=False)

    with pytest.raises(helper.MacosDbKeyIntegrityError, match="宿主校验策略无效"):
        helper.validate_macos_db_key_bundle(
            tmp_path,
            now_unix=ISSUED_AT + 1,
            code_signature_verifier=lambda _path: _signature_info(),
        )


def test_validate_bundle_rejects_unexpected_manifest_metadata(tmp_path: Path):
    _write_bundle(tmp_path)
    manifest_path = tmp_path / helper.MANIFEST_FILE_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unexpectedDetails"] = {"opaque": True}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(helper.MacosDbKeyIntegrityError, match="字段不匹配"):
        helper.validate_macos_db_key_bundle(
            tmp_path,
            now_unix=ISSUED_AT + 1,
            code_signature_verifier=lambda _path: _signature_info(),
        )


def test_validate_bundle_rejects_modified_helper_or_expired_build(tmp_path: Path):
    helper_path, _ = _write_bundle(tmp_path)
    helper_path.write_bytes(b"patched")
    with pytest.raises(helper.MacosDbKeyIntegrityError, match="已被修改"):
        helper.validate_macos_db_key_bundle(
            tmp_path,
            now_unix=ISSUED_AT + 1,
            code_signature_verifier=lambda _path: _signature_info(),
        )

    other = tmp_path / "other"
    _write_bundle(other)
    with pytest.raises(helper.MacosDbKeyUnavailableError, match="已过期"):
        helper.validate_macos_db_key_bundle(
            other,
            now_unix=EXPIRES_AT,
            code_signature_verifier=lambda _path: _signature_info(),
        )


class _FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int) -> None:
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.pid = 4242

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


def _run_fake(
    bundle: helper.ValidatedMacosDbKeyBundle,
    *,
    stdout: bytes,
    stderr: bytes = b"",
    returncode: int = 0,
) -> tuple[str, list[str], dict[str, object]]:
    observed: dict[str, object] = {}

    def factory(argv, **kwargs):
        observed["argv"] = argv
        observed["kwargs"] = kwargs
        return _FakeProcess(stdout, stderr, returncode)

    result = helper._run_capture_helper(
        bundle,
        pid=4321,
        timeout_ms=30_000,
        cancel_event=None,
        deadline_monotonic=time.monotonic() + 2,
        popen_factory=factory,
    )
    return result, observed["argv"], observed["kwargs"]


def test_helper_invocation_exposes_only_pid_timeout_and_one_key_line(tmp_path: Path):
    bundle = _validated_bundle(tmp_path)
    key, argv, options = _run_fake(bundle, stdout=b"ab" * 32 + b"\n")

    assert key == "ab" * 32
    assert argv == [
        str(bundle.helper_path), "--capture", "--pid", "4321", "--timeout-ms", "30000"
    ]
    assert options["stdin"] is not subprocess.PIPE
    assert set(options["env"]) <= {"PATH", "LANG", "HOME", "TMPDIR", "LC_ALL"}


@pytest.mark.parametrize(
    ("returncode", "error_type", "code"),
    [
        (20, helper.MacosDbKeyIntegrityError, "HELPER_INTEGRITY_FAILURE"),
        (21, helper.MacosDbKeyIntegrityError, "HELPER_ARGUMENT_ERROR"),
        (22, helper.MacosDbKeyUnavailableError, "HELPER_EXITED"),
        (23, helper.MacosDbKeyUnavailableError, "CAPTURE_FAILED"),
        (24, helper.MacosDbKeyTimeoutError, "TIMEOUT"),
        (25, helper.MacosDbKeyReloginRequiredError, "WECHAT_RELOGIN_REQUIRED"),
        (26, helper.MacosDbKeyUnavailableError, "PROCESS_EXITED"),
        (27, helper.MacosDbKeyAuthorizationError, "PROCESS_ACCESS_DENIED"),
        (28, helper.MacosDbKeyUnavailableError, "UNSUPPORTED_WECHAT"),
        (29, helper.MacosDbKeyUnavailableError, "CAPTURE_RUNTIME_UNAVAILABLE"),
        (30, helper.MacosDbKeyUnavailableError, "CAPTURE_SESSION_DETACHED"),
    ],
)
def test_helper_exit_codes_are_coarse_and_failure_stdout_must_be_empty(
    tmp_path: Path, returncode: int, error_type: type[BaseException], code: str
):
    bundle = _validated_bundle(tmp_path)
    with pytest.raises(error_type) as caught:
        _run_fake(bundle, stdout=b"", returncode=returncode)
    assert getattr(caught.value, "code") == code

    with pytest.raises(helper.MacosDbKeyIntegrityError) as leaked:
        _run_fake(bundle, stdout=b"ab" * 32 + b"\n", returncode=returncode)
    assert leaked.value.code == "PROTOCOL_ERROR"


def test_helper_rejects_extra_stdout_and_secret_on_stderr(tmp_path: Path):
    bundle = _validated_bundle(tmp_path)
    with pytest.raises(helper.MacosDbKeyIntegrityError) as extra:
        _run_fake(bundle, stdout=b"ab" * 32 + b"\nextra")
    assert extra.value.code == "PROTOCOL_ERROR"

    with pytest.raises(helper.MacosDbKeyIntegrityError) as stderr:
        _run_fake(bundle, stdout=b"", stderr=b"prefix " + b"ab" * 32, returncode=23)
    assert stderr.value.code == "SECRET_OUTPUT_VIOLATION"


def test_capture_tries_next_pid_only_after_confirmed_process_exit(tmp_path: Path):
    bundle = _validated_bundle(tmp_path)
    calls: list[int] = []

    def runner(_bundle, *, pid, **_kwargs):
        calls.append(pid)
        if pid == 111:
            raise helper.MacosDbKeyUnavailableError(
                "old process exited", code="PROCESS_EXITED", retryable=True
            )
        return "cd" * 32

    result = helper.capture_macos_database_key(
        bundle=bundle,
        pid_provider=lambda: (222, 111),
        helper_runner=runner,
    )

    assert calls == [111, 222]
    assert result == {
        "db_key": "cd" * 32,
        "method": "macos_private_helper",
        "pid": 222,
        "build_id": BUILD_NAME,
    }


def test_capture_follows_wechat_main_process_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _validated_bundle(tmp_path)
    pid_snapshots = iter(((111,), (), (222,)))
    calls: list[int] = []

    def pid_provider():
        return next(pid_snapshots, (222,))

    def runner(_bundle, *, pid, **_kwargs):
        calls.append(pid)
        if pid == 111:
            raise helper.MacosDbKeyUnavailableError(
                "old process exited", code="PROCESS_EXITED", retryable=True
            )
        return "ef" * 32

    monkeypatch.setattr(helper.time, "sleep", lambda _seconds: None)
    result = helper.capture_macos_database_key(
        bundle=bundle,
        pid_provider=pid_provider,
        helper_runner=runner,
    )

    assert calls == [111, 222]
    assert result["db_key"] == "ef" * 32
    assert result["pid"] == 222


def test_capture_does_not_relabel_generic_failure_when_pid_remains(tmp_path: Path):
    bundle = _validated_bundle(tmp_path)
    calls: list[int] = []

    def runner(_bundle, *, pid, **_kwargs):
        calls.append(pid)
        raise helper.MacosDbKeyUnavailableError(
            "capture failed", code="CAPTURE_FAILED", retryable=True
        )

    with pytest.raises(helper.MacosDbKeyUnavailableError) as caught:
        helper.capture_macos_database_key(
            bundle=bundle,
            pid_provider=lambda: (66262,),
            helper_runner=runner,
        )

    assert caught.value.code == "CAPTURE_FAILED"
    assert calls == [66262]


def test_capture_waits_for_wechat_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _validated_bundle(tmp_path)
    pid_snapshots = iter(((), (333,)))

    monkeypatch.setattr(helper.time, "sleep", lambda _seconds: None)
    result = helper.capture_macos_database_key(
        bundle=bundle,
        pid_provider=lambda: next(pid_snapshots, (333,)),
        helper_runner=lambda _bundle, *, pid, **_kwargs: "12" * 32,
    )

    assert result["db_key"] == "12" * 32
    assert result["pid"] == 333


def test_capture_keeps_waiting_after_relogin_required_for_a_new_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundle = _validated_bundle(tmp_path)
    pid_snapshots = iter(((111,), (222,)))
    calls: list[int] = []

    def runner(_bundle, *, pid, **_kwargs):
        calls.append(pid)
        if pid == 111:
            raise helper.MacosDbKeyReloginRequiredError()
        return "34" * 32

    monkeypatch.setattr(helper.time, "sleep", lambda _seconds: None)
    result = helper.capture_macos_database_key(
        bundle=bundle,
        pid_provider=lambda: next(pid_snapshots, (222,)),
        helper_runner=runner,
    )

    assert calls == [111, 222]
    assert result["db_key"] == "34" * 32
    assert result["pid"] == 222
