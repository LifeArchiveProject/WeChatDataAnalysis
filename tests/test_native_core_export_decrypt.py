from __future__ import annotations

import ctypes
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from wechat_decrypt_tool.native_core_broker import managed_native_core_operation
from wechat_decrypt_tool.native_core_client import (
    NativeCoreError,
    NativeCoreProtocolError,
    NativeCoreStatus,
    get_native_core_client,
    parse_native_encrypted_export_header,
    resolve_native_core_library,
)
from wechat_decrypt_tool.native_core_export import (
    decrypt_export_file,
    encrypt_export_file,
    encrypt_export_file_and_remove_source,
)


_CHUNK_SIZE = 64 * 1024
_CONTENT_KEY = bytes(range(32))


@pytest.fixture(autouse=True)
def _require_wec1_decryption_abi() -> None:
    library = ctypes.CDLL(str(resolve_native_core_library()))
    required = (
        "wce_export_decrypt_begin",
        "wce_export_decrypt_write",
        "wce_export_decrypt_finish",
        "wce_export_decrypt_abort",
    )
    if not all(hasattr(library, name) for name in required):
        pytest.skip("installed dev-local native core predates the WEC1 decryption ABI")


def _payload(size: int) -> bytes:
    return bytes((index * 31 + 7) & 0xFF for index in range(size))


def _create_archive(
    root: Path,
    payload: bytes,
    *,
    name: str = "payload.bin",
) -> tuple[Path, bytes]:
    source = root / name
    archive = root / f"{name}.wec"
    source.write_bytes(payload)
    encrypt_export_file(
        source,
        archive,
        export_id=f"decrypt-test-{name}",
        content_key=_CONTENT_KEY,
        chunk_size=_CHUNK_SIZE,
    )
    return archive, archive.read_bytes()


def _assert_no_decrypt_temp_files(root: Path) -> None:
    assert list(root.glob(".wcd-*.tmp")) == []


def test_real_wec1_streaming_round_trip_at_chunk_boundaries() -> None:
    sizes = (1, _CHUNK_SIZE, _CHUNK_SIZE + 1, _CHUNK_SIZE * 2 + 17)
    with TemporaryDirectory() as td, managed_native_core_operation(export_only=True):
        root = Path(td)
        for index, size in enumerate(sizes):
            expected = _payload(size)
            source = root / f"round-trip-{index}.bin"
            source.write_bytes(expected)
            encrypted = encrypt_export_file_and_remove_source(
                source,
                export_id=f"round-trip-{size}",
                content_key=_CONTENT_KEY,
                chunk_size=_CHUNK_SIZE,
            )

            assert not source.exists()
            decrypted = decrypt_export_file(
                encrypted.output_path,
                content_key=_CONTENT_KEY,
            )

            assert decrypted.output_path == source
            assert decrypted.export_id == f"round-trip-{size}"
            assert decrypted.plaintext_size == size
            assert decrypted.chunk_count == (size + _CHUNK_SIZE - 1) // _CHUNK_SIZE
            assert source.read_bytes() == expected
            _assert_no_decrypt_temp_files(root)


@pytest.mark.parametrize(
    "mutation",
    ("export-id", "salt", "tag", "ciphertext"),
)
def test_real_wec1_tampering_never_publishes_plaintext(mutation: str) -> None:
    with TemporaryDirectory() as td, managed_native_core_operation(export_only=True):
        root = Path(td)
        archive, encoded = _create_archive(root, _payload(_CHUNK_SIZE + 9))
        tampered = bytearray(encoded)
        header_size = struct.unpack_from("<I", tampered, 8)[0]
        offsets = {
            "export-id": 64,
            "salt": 40,
            "tag": header_size + 24,
            "ciphertext": header_size + 40,
        }
        tampered[offsets[mutation]] ^= 0x01 if mutation == "export-id" else 0x80
        archive.write_bytes(tampered)
        destination = root / "tampered.out"

        with pytest.raises(NativeCoreError) as caught:
            decrypt_export_file(
                archive,
                destination,
                content_key=_CONTENT_KEY,
            )

        assert caught.value.status == int(NativeCoreStatus.TAMPER_DETECTED)
        assert not destination.exists()
        _assert_no_decrypt_temp_files(root)


def test_real_wec1_wrong_key_preserves_existing_destination() -> None:
    with TemporaryDirectory() as td, managed_native_core_operation(export_only=True):
        root = Path(td)
        archive, _encoded = _create_archive(root, b"authenticated plaintext")
        destination = root / "existing.out"
        destination.write_bytes(b"keep this file")

        with pytest.raises(NativeCoreError) as caught:
            decrypt_export_file(
                archive,
                destination,
                content_key=bytes(reversed(_CONTENT_KEY)),
                overwrite=True,
            )

        assert caught.value.status == int(NativeCoreStatus.TAMPER_DETECTED)
        assert destination.read_bytes() == b"keep this file"
        _assert_no_decrypt_temp_files(root)


def test_real_wec1_truncation_and_trailing_data_leave_no_artifacts() -> None:
    with TemporaryDirectory() as td, managed_native_core_operation(export_only=True):
        root = Path(td)
        archive, encoded = _create_archive(root, _payload(_CHUNK_SIZE + 13))
        header_size = struct.unpack_from("<I", encoded, 8)[0]
        second_record = header_size + 40 + _CHUNK_SIZE
        cases = {
            "fixed-header": encoded[:63],
            "header-suffix": encoded[: header_size - 1],
            "record-prefix": encoded[: header_size + 23],
            "record-tag": encoded[: header_size + 24 + 15],
            "record-ciphertext": encoded[:-1],
            "second-record-prefix": encoded[: second_record + 5],
            "trailing-data": encoded + b"unexpected",
        }

        for name, malformed in cases.items():
            archive.write_bytes(malformed)
            destination = root / f"{name}.out"
            with pytest.raises(NativeCoreProtocolError):
                decrypt_export_file(
                    archive,
                    destination,
                    content_key=_CONTENT_KEY,
                )
            assert not destination.exists()
            _assert_no_decrypt_temp_files(root)


def test_empty_files_are_rejected_without_output_artifacts() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        empty_plaintext = root / "empty.bin"
        empty_plaintext.write_bytes(b"")
        encrypted_output = root / "empty.bin.wec"
        with pytest.raises(ValueError):
            encrypt_export_file(
                empty_plaintext,
                encrypted_output,
                export_id="empty",
                content_key=_CONTENT_KEY,
            )
        assert not encrypted_output.exists()

        empty_archive = root / "malformed.wec"
        empty_archive.write_bytes(b"")
        with pytest.raises(NativeCoreProtocolError):
            decrypt_export_file(empty_archive, content_key=_CONTENT_KEY)
        assert not (root / "malformed").exists()
        _assert_no_decrypt_temp_files(root)


def test_decrypt_session_finish_abort_and_tamper_lifecycle() -> None:
    with TemporaryDirectory() as td, managed_native_core_operation(export_only=True):
        root = Path(td)
        _archive, encoded = _create_archive(root, b"native session lifecycle")
        header_size = struct.unpack_from("<I", encoded, 8)[0]
        header = parse_native_encrypted_export_header(encoded[:header_size])
        record = encoded[header_size:]
        client = get_native_core_client()

        with client.begin_decrypted_export(
            header.encoded, content_key=_CONTENT_KEY
        ) as aborted:
            assert not aborted.closed
        assert aborted.closed

        finished = client.begin_decrypted_export(
            header.encoded, content_key=_CONTENT_KEY
        )
        assert finished.write(record) == b"native session lifecycle"
        finished.finish()
        assert finished.closed

        tampered_record = bytearray(record)
        tampered_record[24] ^= 0x01
        failed = client.begin_decrypted_export(
            header.encoded, content_key=_CONTENT_KEY
        )
        with pytest.raises(NativeCoreError) as caught:
            failed.write(tampered_record)
        assert caught.value.status == int(NativeCoreStatus.TAMPER_DETECTED)
        assert failed.closed
        assert client._decrypted_export_handles == set()
