from __future__ import annotations

import base64
import sqlite3
import sys
import zipfile
from contextlib import ExitStack, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import chat_export_service, native_core_export
from wechat_decrypt_tool.export_integrity import IntegrityZipWriter, write_zip_integrity_sidecars
from wechat_decrypt_tool.native_core_client import (
    NativeCoreComponentMissingError,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreStatus,
)
from wechat_decrypt_tool.native_core_export import NativeSealedExportResult
from wechat_decrypt_tool.routers import account_archive_export, chat_contacts, record_export


def _request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": path,
            "headers": [],
        }
    )


def _fake_wec1_publish(source_path, output_path, **_kwargs):
    source = Path(source_path)
    output = Path(output_path)
    output.write_bytes(b"WEC1" + source.read_bytes())
    source.unlink()
    return SimpleNamespace(output_path=output)


def _fake_native_seal(export_id: str) -> NativeSealedExportResult:
    return NativeSealedExportResult(
        export_id=export_id,
        manifest_size=2,
        manifest_sha256="0" * 64,
        seal_format="WES1",
        envelope=b"WES1\x01\x00test-envelope",
    )


class _FakeEncryptedSession:
    def __init__(self, export_id: str, plaintext_size: int, chunk_size: int) -> None:
        self.header = SimpleNamespace(
            encoded=b"WEC1-fake-header",
            export_id=export_id,
            plaintext_size=plaintext_size,
            chunk_size=chunk_size,
            chunk_count=(plaintext_size + chunk_size - 1) // chunk_size,
        )
        self.closed = False

    def write(self, payload: bytes) -> bytes:
        return b"record:" + payload

    def finish(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.closed = True


class _FakeExportClient:
    def __init__(self, *, envelope: bytes = b"WES1-envelope") -> None:
        self.envelope = envelope

    def seal_export_manifest(self, export_id: str, manifest: bytes) -> bytes:
        assert export_id
        assert manifest
        return self.envelope

    def begin_encrypted_export(
        self,
        export_id: str,
        *,
        plaintext_size: int,
        content_key: bytes,
        chunk_size: int,
    ) -> _FakeEncryptedSession:
        assert len(content_key) == 32
        return _FakeEncryptedSession(export_id, plaintext_size, chunk_size)


def test_required_mode_never_falls_back_when_native_export_is_missing() -> None:
    with patch.object(
        native_core_export,
        "managed_native_core_operation",
        side_effect=NativeCoreComponentMissingError("missing"),
    ):
        with pytest.raises(NativeCoreComponentMissingError):
            native_core_export.seal_export_manifest("required", b"{}")


def test_required_mode_propagates_native_export_policy_failures() -> None:
    denied = NativeCorePolicyError(
        "denied",
        status=int(NativeCoreStatus.FEATURE_DENIED),
    )
    with (
        patch.object(native_core_export, "managed_native_core_operation", return_value=nullcontext()),
        patch.object(native_core_export, "get_native_core_client", return_value=_FakeExportClient()),
        patch.object(_FakeExportClient, "seal_export_manifest", side_effect=denied),
    ):
        with pytest.raises(NativeCorePolicyError):
            native_core_export.seal_export_manifest("required-policy", b"{}")


@pytest.mark.parametrize("seal_format", ["WES1", "WES2"])
def test_seal_manifest_reports_native_envelope_format(seal_format: str) -> None:
    envelope = seal_format.encode("ascii") + b"-envelope"
    with (
        patch.object(
            native_core_export,
            "managed_native_core_operation",
            return_value=nullcontext(),
        ),
        patch.object(
            native_core_export,
            "get_native_core_client",
            return_value=_FakeExportClient(envelope=envelope),
        ),
    ):
        result = native_core_export.seal_export_manifest("native-format", b"{}")

    assert result.seal_format == seal_format
    assert result.envelope == envelope


def test_seal_manifest_rejects_unknown_native_envelope_format() -> None:
    with (
        patch.object(
            native_core_export,
            "managed_native_core_operation",
            return_value=nullcontext(),
        ),
        patch.object(
            native_core_export,
            "get_native_core_client",
            return_value=_FakeExportClient(envelope=b"BAD1-envelope"),
        ),
        pytest.raises(NativeCoreProtocolError, match="invalid WES1/WES2 envelope"),
    ):
        native_core_export.seal_export_manifest("invalid-format", b"{}")


def test_seal_manifest_refreshes_license_required_and_retries_once() -> None:
    client = Mock()
    denied = NativeCorePolicyError(
        "license required",
        status=int(NativeCoreStatus.LICENSE_REQUIRED),
    )
    envelope = b"WES1-refreshed"
    client.seal_export_manifest.side_effect = [denied, envelope]

    with patch(
        "wechat_decrypt_tool.native_core_lease.refresh_native_core_lease"
    ) as refresh:
        result = native_core_export._seal_export_manifest(
            client,
            export_id="refresh-export",
            manifest=b"{}",
        )

    assert result == envelope
    assert client.seal_export_manifest.call_args_list == [
        call("refresh-export", b"{}"),
        call("refresh-export", b"{}"),
    ]
    refresh.assert_called_once_with(client, native_core_export.NativeCoreFeature.EXPORT)


def test_seal_manifest_refresh_failure_preserves_original_policy_error() -> None:
    client = Mock()
    denied = NativeCorePolicyError(
        "license required",
        status=int(NativeCoreStatus.LICENSE_REQUIRED),
    )
    refresh_error = RuntimeError("license service unavailable")
    client.seal_export_manifest.side_effect = denied

    with (
        patch(
            "wechat_decrypt_tool.native_core_lease.refresh_native_core_lease",
            side_effect=refresh_error,
        ) as refresh,
        pytest.raises(NativeCorePolicyError) as caught,
    ):
        native_core_export._seal_export_manifest(
            client,
            export_id="refresh-failed",
            manifest=b"{}",
        )

    assert caught.value is denied
    assert caught.value.__cause__ is refresh_error
    assert client.seal_export_manifest.call_count == 1
    refresh.assert_called_once_with(client, native_core_export.NativeCoreFeature.EXPORT)


def test_seal_manifest_non_refreshable_policy_error_does_not_refresh() -> None:
    client = Mock()
    denied = NativeCorePolicyError(
        "tamper detected",
        status=int(NativeCoreStatus.TAMPER_DETECTED),
    )
    client.seal_export_manifest.side_effect = denied

    with (
        patch(
            "wechat_decrypt_tool.native_core_lease.refresh_native_core_lease"
        ) as refresh,
        pytest.raises(NativeCorePolicyError) as caught,
    ):
        native_core_export._seal_export_manifest(
            client,
            export_id="tampered-export",
            manifest=b"{}",
        )

    assert caught.value is denied
    assert client.seal_export_manifest.call_count == 1
    refresh.assert_not_called()


def test_seal_manifest_invalid_lease_preserves_verify_stage_without_refresh() -> None:
    client = Mock()
    denied = NativeCorePolicyError(
        "wechatdb native verify export seal failed: invalid lease (-6)",
        status=int(NativeCoreStatus.LEASE_INVALID),
    )
    client.seal_export_manifest.side_effect = denied

    with (
        patch(
            "wechat_decrypt_tool.native_core_lease.refresh_native_core_lease"
        ) as refresh,
        pytest.raises(NativeCorePolicyError) as caught,
    ):
        native_core_export._seal_export_manifest(
            client,
            export_id="invalid-lease-export",
            manifest=b"{}",
        )

    assert caught.value is denied
    assert str(caught.value) == (
        "wechatdb native verify export seal failed: invalid lease (-6)"
    )
    assert client.seal_export_manifest.call_count == 1
    refresh.assert_not_called()


@pytest.mark.parametrize("seal_format", ["WES1", "WES2"])
def test_zip_export_contains_raw_native_authoritative_sidecar(
    seal_format: str,
) -> None:
    envelope = seal_format.encode("ascii") + b"\x01\x00signed-envelope"
    native_result = NativeSealedExportResult(
        export_id="zip-native-seal",
        manifest_size=2,
        manifest_sha256="0" * 64,
        seal_format=seal_format,
        envelope=envelope,
    )
    with TemporaryDirectory() as td, patch(
        "wechat_decrypt_tool.export_integrity.seal_export_manifest",
        return_value=native_result,
    ):
        target = Path(td) / "export.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as raw:
            writer = IntegrityZipWriter(raw)
            writer.writestr("data.json", "{}")
            sealed = write_zip_integrity_sidecars(writer, "zip-native-seal")

        with zipfile.ZipFile(target) as archive:
            assert archive.read("_integrity/signature.wes") == envelope
            assert archive.read("_integrity/manifest.json")
        assert sealed["authoritativeSealFormat"] == seal_format


def test_browser_contacts_export_writes_native_wes1_response() -> None:
    source = (ROOT / "frontend" / "pages" / "contacts.vue").read_text(encoding="utf-8")
    assert "sealed.nativeManifestFileName" in source
    assert "sealed.nativeSignatureFileName" in source
    assert "exportContentFromBase64(sealed.nativeSignatureBase64)" in source


def test_wec1_wrapper_removes_plaintext_and_never_persists_key() -> None:
    key_text = base64.b64encode(bytes(range(32))).decode("ascii")
    content_key = native_core_export.decode_export_content_key(key_text, enabled=True)
    assert content_key == bytearray(range(32))

    with TemporaryDirectory() as td:
        source = Path(td) / "chat.zip"
        destination = Path(td) / "chat.zip.wec"
        source.write_bytes(b"private export payload")
        with (
            patch.object(native_core_export, "managed_native_core_operation", return_value=nullcontext()),
            patch.object(native_core_export, "get_native_core_client", return_value=_FakeExportClient()),
        ):
            result = native_core_export.encrypt_export_file_and_remove_source(
                source,
                destination,
                export_id="wec1-test",
                content_key=content_key,
            )

        assert not source.exists()
        assert destination.read_bytes().startswith(b"WEC1-fake-header")
        assert result.output_path == destination
        assert key_text.encode("ascii") not in destination.read_bytes()

    native_core_export.erase_export_content_key(content_key)
    assert content_key == bytearray(32)


def test_account_archive_explicit_encryption_publishes_only_wec1() -> None:
    content_key = bytearray(range(32))

    def fake_encrypt(source_path, output_path, **_kwargs):
        source = Path(source_path)
        output = Path(output_path)
        output.write_bytes(b"WEC1" + source.read_bytes())
        source.unlink()
        return SimpleNamespace(output_path=output)

    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_test"
        output_dir = root / "exports"
        account_dir.mkdir()
        for database_name in ("contact.db", "session.db", "message.db"):
            connection = sqlite3.connect(account_dir / database_name)
            try:
                connection.execute("CREATE TABLE fixture(value INTEGER)")
                connection.commit()
            finally:
                connection.close()
        job = account_archive_export.AccountArchiveExportJob(
            export_id="archive-wec1",
            encrypted=True,
            content_key=content_key,
        )
        with account_archive_export._JOBS_LOCK:
            account_archive_export._JOBS[job.export_id] = job
        try:
            with (
                patch.object(
                    account_archive_export,
                    "_resolve_account_dir",
                    return_value=account_dir,
                ),
                patch.object(
                    account_archive_export,
                    "encrypt_export_file_and_remove_source",
                    side_effect=fake_encrypt,
                ),
                patch(
                    "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                    side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
                ),
            ):
                account_archive_export._run_account_archive_export(
                    job.export_id,
                    {
                        "account": account_dir.name,
                        "output_dir": str(output_dir),
                        "include_databases": True,
                        "include_resources": False,
                        "file_name": "account.zip",
                    },
                )
        finally:
            with account_archive_export._JOBS_LOCK:
                account_archive_export._JOBS.pop(job.export_id, None)

        output = Path(job.zip_path)
        assert job.status == "done", job.error
        assert output.name == "account.zip.wec"
        assert output.read_bytes().startswith(b"WEC1")
        assert not (output_dir / "account.zip").exists()
        assert not (output_dir / "account.zip.tmp").exists()
        assert job.content_key is None
        assert "content_key" not in str(job.to_public_dict()).lower()


@pytest.mark.parametrize("export_format", ["json", "html"])
def test_encrypted_record_export_leaves_only_wec1(export_format: str) -> None:
    key_text = base64.b64encode(bytes(range(32))).decode("ascii")
    with TemporaryDirectory() as td:
        output_dir = Path(td) / "exports"
        request = record_export.RecordExportRequest(
            account="wxid_test",
            dataset="payments",
            format=export_format,
            output_dir=str(output_dir),
            file_name=f"payments-{export_format}",
            encrypt=True,
            content_key_base64=key_text,
        )
        with (
            patch.object(
                record_export,
                "_load_records",
                return_value=(
                    [{"kind": "transfer", "transferState": "received", "createTime": 1}],
                    {"account": "wxid_test", "dataSource": "realtime"},
                ),
            ),
            patch.object(
                record_export,
                "encrypt_export_file_and_remove_source",
                side_effect=_fake_wec1_publish,
            ),
            patch(
                "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
            ),
        ):
            response = record_export.export_records(_request("/api/records/export"), request)

        output = Path(response["outputPath"])
        assert output.suffix == ".wec"
        assert output.read_bytes().startswith(b"WEC1")
        assert list(output_dir.iterdir()) == [output]
        assert response["integrityManifestPath"] == ""
        assert response["integritySignaturePath"] == ""
        assert response["nativeIntegrityManifestPath"] == ""
        assert response["nativeIntegritySignaturePath"] == ""
        assert response["authoritativeSealFormat"] == "WEC1"


@pytest.mark.parametrize(
    ("failure_stage", "export_format"),
    [("seal", "json"), ("encrypt", "json"), ("encrypt", "html")],
)
def test_encrypted_record_export_failure_removes_every_artifact(
    failure_stage: str,
    export_format: str,
) -> None:
    key_text = base64.b64encode(bytes(range(32))).decode("ascii")
    with TemporaryDirectory() as td:
        output_dir = Path(td) / "exports"
        request = record_export.RecordExportRequest(
            account="wxid_test",
            dataset="payments",
            format=export_format,
            output_dir=str(output_dir),
            file_name="payments-failure",
            encrypt=True,
            content_key_base64=key_text,
        )

        def fail_seal(path: Path, _export_id: str):
            path.with_name(path.name + ".manifest.json").write_text("partial", encoding="utf-8")
            path.with_name(path.name + ".signature.wes").write_bytes(b"WES1-partial")
            raise RuntimeError("seal failed")

        def fail_encrypt(source_path, output_path, **_kwargs):
            Path(output_path).write_bytes(b"WEC1-partial")
            assert Path(source_path).exists()
            raise RuntimeError("encrypt failed")

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    record_export,
                    "_load_records",
                    return_value=([], {"account": "wxid_test", "dataSource": "realtime"}),
                )
            )
            if failure_stage == "seal":
                stack.enter_context(
                    patch.object(record_export, "write_file_integrity_sidecars", side_effect=fail_seal)
                )
            else:
                stack.enter_context(
                    patch(
                        "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                        side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
                    )
                )
                stack.enter_context(
                    patch.object(
                        record_export,
                        "encrypt_export_file_and_remove_source",
                        side_effect=fail_encrypt,
                    )
                )
            with pytest.raises(HTTPException):
                record_export.export_records(_request("/api/records/export"), request)

        assert output_dir.exists()
        assert list(output_dir.iterdir()) == []


def test_encrypted_record_export_failure_preserves_existing_wec1() -> None:
    key_text = base64.b64encode(bytes(range(32))).decode("ascii")
    with TemporaryDirectory() as td:
        output_dir = Path(td) / "exports"
        output_dir.mkdir()
        existing_output = output_dir / "payments-existing.json.wec"
        existing_payload = b"WEC1-existing"
        existing_output.write_bytes(existing_payload)
        request = record_export.RecordExportRequest(
            account="wxid_test",
            dataset="payments",
            format="json",
            output_dir=str(output_dir),
            file_name="payments-existing",
            encrypt=True,
            content_key_base64=key_text,
        )

        attempted_output: list[Path] = []

        def fail_encrypt(source_path, output_path, **_kwargs):
            candidate = Path(output_path)
            attempted_output.append(candidate)
            assert candidate != existing_output
            candidate.write_bytes(b"WEC1-partial")
            assert Path(source_path).exists()
            raise RuntimeError("encrypt failed")

        with (
            patch.object(
                record_export,
                "_load_records",
                return_value=([], {"account": "wxid_test", "dataSource": "realtime"}),
            ),
            patch(
                "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
            ),
            patch.object(
                record_export,
                "encrypt_export_file_and_remove_source",
                side_effect=fail_encrypt,
            ),
        ):
            with pytest.raises(HTTPException):
                record_export.export_records(
                    _request("/api/records/export"), request
                )

        assert attempted_output and not attempted_output[0].exists()
        assert existing_output.read_bytes() == existing_payload
        assert list(output_dir.iterdir()) == [existing_output]


@pytest.mark.parametrize("export_format", ["json", "html"])
def test_encrypted_contacts_export_leaves_only_wec1(export_format: str) -> None:
    key_text = base64.b64encode(bytes(range(32))).decode("ascii")
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_test"
        output_dir = root / "exports"
        account_dir.mkdir()
        request = chat_contacts.ContactExportRequest(
            account=account_dir.name,
            source="decrypted",
            output_dir=str(output_dir),
            format=export_format,
            encrypt=True,
            content_key_base64=key_text,
        )
        with (
            patch.object(chat_contacts, "_resolve_account_dir", return_value=account_dir),
            patch.object(
                chat_contacts,
                "_run_contacts_read_with_fallback",
                return_value=(
                    [{"username": "wxid_friend", "displayName": "Friend", "type": "friend"}],
                    "decrypted",
                    {},
                ),
            ),
            patch.object(
                chat_contacts,
                "encrypt_export_file_and_remove_source",
                side_effect=_fake_wec1_publish,
            ),
            patch(
                "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
            ),
        ):
            response = chat_contacts.export_chat_contacts(
                _request("/api/chat/contacts/export"), request
            )

        output = Path(response["outputPath"])
        assert output.suffix == ".wec"
        assert output.read_bytes().startswith(b"WEC1")
        assert list(output_dir.iterdir()) == [output]
        assert response["integrityManifestPath"] == ""
        assert response["integritySignaturePath"] == ""
        assert response["nativeIntegrityManifestPath"] == ""
        assert response["nativeIntegritySignaturePath"] == ""
        assert response["authoritativeSealFormat"] == "WEC1"


@pytest.mark.parametrize("export_format", ["json", "html"])
def test_encrypted_contacts_export_failure_removes_every_artifact(export_format: str) -> None:
    key_text = base64.b64encode(bytes(range(32))).decode("ascii")
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_test"
        output_dir = root / "exports"
        account_dir.mkdir()
        request = chat_contacts.ContactExportRequest(
            account=account_dir.name,
            source="decrypted",
            output_dir=str(output_dir),
            format=export_format,
            encrypt=True,
            content_key_base64=key_text,
        )

        def fail_encrypt(source_path, output_path, **_kwargs):
            Path(output_path).write_bytes(b"WEC1-partial")
            assert Path(source_path).exists()
            raise RuntimeError("encrypt failed")

        with (
            patch.object(chat_contacts, "_resolve_account_dir", return_value=account_dir),
            patch.object(
                chat_contacts,
                "_run_contacts_read_with_fallback",
                return_value=([], "decrypted", {}),
            ),
            patch.object(
                chat_contacts,
                "encrypt_export_file_and_remove_source",
                side_effect=fail_encrypt,
            ),
            patch(
                "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
            ),
        ):
            with pytest.raises(HTTPException):
                chat_contacts.export_chat_contacts(
                    _request("/api/chat/contacts/export"), request
                )

        assert output_dir.exists()
        assert list(output_dir.iterdir()) == []


def test_encrypted_favorites_archive_leaves_only_wec1() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_test"
        output_dir = root / "exports"
        account_dir.mkdir()
        with (
            patch.object(
                chat_export_service,
                "encrypt_export_file_and_remove_source",
                side_effect=_fake_wec1_publish,
            ),
            patch(
                "wechat_decrypt_tool.export_integrity.seal_export_manifest",
                side_effect=lambda export_id, _manifest: _fake_native_seal(export_id),
            ),
        ):
            job = chat_export_service.export_prepared_chat_archive(
                account_dir=account_dir,
                output_dir=output_dir,
                file_name="favorites.zip",
                title="Favorites",
                export_format="json",
                conversations=[
                    {
                        "username": "__favorites__",
                        "displayName": "Favorites",
                        "messages": [{"id": "1", "renderType": "text", "content": "hello"}],
                    }
                ],
                include_media=False,
                media_kinds=[],
                message_types=["text"],
                encrypt=True,
                content_key=bytearray(range(32)),
            )

        assert job.status == "done", job.error
        assert job.zip_path is not None
        assert job.zip_path.read_bytes().startswith(b"WEC1PK")
        assert list(output_dir.iterdir()) == [job.zip_path]


def test_encrypted_favorites_archive_failure_removes_partial_zip() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_test"
        output_dir = root / "exports"
        account_dir.mkdir()
        with patch.object(
            chat_export_service,
            "write_zip_integrity_sidecars",
            side_effect=RuntimeError("seal failed"),
        ):
            job = chat_export_service.export_prepared_chat_archive(
                account_dir=account_dir,
                output_dir=output_dir,
                file_name="favorites.zip",
                title="Favorites",
                export_format="json",
                conversations=[
                    {
                        "username": "__favorites__",
                        "displayName": "Favorites",
                        "messages": [{"id": "1", "renderType": "text", "content": "hello"}],
                    }
                ],
                include_media=False,
                media_kinds=[],
                message_types=["text"],
                encrypt=True,
                content_key=bytearray(range(32)),
            )

        assert job.status == "error"
        assert output_dir.exists()
        assert list(output_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("enabled", "encoded"),
    [
        (True, None),
        (True, base64.b64encode(b"short").decode("ascii")),
        (False, base64.b64encode(bytes(32)).decode("ascii")),
    ],
)
def test_wec1_key_contract_rejects_ambiguous_requests(enabled: bool, encoded: str | None) -> None:
    with pytest.raises(ValueError):
        native_core_export.decode_export_content_key(encoded, enabled=enabled)
