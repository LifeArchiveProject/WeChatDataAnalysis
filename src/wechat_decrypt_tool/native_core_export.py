from __future__ import annotations

import ctypes
import base64
import binascii
import errno
import hashlib
import os
import stat
import struct
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from .native_core_broker import managed_native_core_operation
from .native_core_client import (
    NativeCoreClient,
    NativeCoreEncryptedExportHeader,
    NativeCoreFeature,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreStatus,
    get_native_core_client,
    parse_native_encrypted_export_header,
)


_DEFAULT_CHUNK_SIZE = 512 * 1024
_MAX_PLAINTEXT_SIZE = 256 * 1024 * 1024 * 1024
_REFRESHABLE_POLICY_STATUSES = {
    int(NativeCoreStatus.LICENSE_REQUIRED),
    int(NativeCoreStatus.LEASE_EXPIRED),
    int(NativeCoreStatus.FEATURE_DENIED),
}
_EXPORT_SEAL_FORMATS = {
    b"WES1": "WES1",
    b"WES2": "WES2",
}


@dataclass(frozen=True)
class NativeEncryptedExportResult:
    source_path: Path
    output_path: Path
    export_id: str
    plaintext_size: int
    encrypted_size: int
    chunk_size: int
    chunk_count: int
    header: NativeCoreEncryptedExportHeader = field(repr=False)


@dataclass(frozen=True)
class NativeDecryptedExportResult:
    source_path: Path
    output_path: Path
    export_id: str
    plaintext_size: int
    encrypted_size: int
    chunk_size: int
    chunk_count: int
    header: NativeCoreEncryptedExportHeader = field(repr=False)


@dataclass(frozen=True)
class NativeSealedExportResult:
    export_id: str
    manifest_size: int
    manifest_sha256: str
    seal_format: str
    envelope: bytes = field(repr=False)


def decode_export_content_key(
    encoded_key: str | None,
    *,
    enabled: bool,
) -> bytearray | None:
    """Validate an explicit per-export WEC1 content key without persisting it."""

    encoded = str(encoded_key or "").strip()
    if not enabled:
        if encoded:
            raise ValueError("content_key_base64 requires encrypt=true")
        return None
    if not encoded:
        raise ValueError("content_key_base64 is required when encrypt=true")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("content_key_base64 must be valid Base64") from exc
    if len(decoded) != 32:
        raise ValueError("content_key_base64 must decode to exactly 32 bytes")
    return bytearray(decoded)


def erase_export_content_key(content_key: bytearray | None) -> None:
    if content_key is not None:
        content_key[:] = b"\x00" * len(content_key)


def _seal_export_manifest(
    client: NativeCoreClient,
    *,
    export_id: str,
    manifest: bytes,
) -> bytes:
    try:
        return client.seal_export_manifest(export_id, manifest)
    except NativeCorePolicyError as policy_error:
        if policy_error.status not in _REFRESHABLE_POLICY_STATUSES:
            raise
        try:
            from .native_core_lease import refresh_native_core_lease

            refresh_native_core_lease(client, NativeCoreFeature.EXPORT)
        except Exception as refresh_error:
            raise policy_error from refresh_error
        return client.seal_export_manifest(export_id, manifest)


def seal_export_manifest(
    export_id: str,
    manifest: bytes | bytearray | memoryview,
) -> NativeSealedExportResult:
    """Seal a canonical manifest with the mandatory native implementation."""

    payload = bytes(manifest)
    if not payload:
        raise ValueError("export manifest must not be empty")
    with managed_native_core_operation(export_only=True):
        envelope = _seal_export_manifest(
            get_native_core_client(),
            export_id=str(export_id or ""),
            manifest=payload,
        )
    seal_format = _EXPORT_SEAL_FORMATS.get(envelope[:4])
    if seal_format is None:
        raise NativeCoreProtocolError(
            "wechatdb native export returned an invalid WES1/WES2 envelope."
        )
    return NativeSealedExportResult(
        export_id=str(export_id or ""),
        manifest_size=len(payload),
        manifest_sha256=hashlib.sha256(payload).hexdigest(),
        seal_format=seal_format,
        envelope=envelope,
    )


def _canonical_destination(value: Path) -> Path:
    expanded = value.expanduser()
    if not expanded.name or expanded.suffix.lower() != ".wec":
        raise ValueError("encrypted export output must use the .wec extension")
    expanded.parent.mkdir(parents=True, exist_ok=True)
    parent = expanded.parent.resolve(strict=True)
    destination = parent / expanded.name
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError(destination)
    return destination


def _canonical_plaintext_destination(value: Path) -> Path:
    expanded = value.expanduser()
    if not expanded.name:
        raise ValueError("decrypted export output must be a file path")
    expanded.parent.mkdir(parents=True, exist_ok=True)
    parent = expanded.parent.resolve(strict=True)
    destination = parent / expanded.name
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError(destination)
    return destination


def _same_file(source: Path, destination: Path) -> bool:
    try:
        return destination.exists() and os.path.samefile(source, destination)
    except OSError:
        return os.path.normcase(os.fspath(source.resolve(strict=True))) == os.path.normcase(
            os.fspath(destination.absolute())
        )


def _begin_encrypted_export(
    client: NativeCoreClient,
    *,
    export_id: str,
    plaintext_size: int,
    content_key: bytes | bytearray | memoryview,
    chunk_size: int,
):
    try:
        return client.begin_encrypted_export(
            export_id,
            plaintext_size=plaintext_size,
            content_key=content_key,
            chunk_size=chunk_size,
        )
    except NativeCorePolicyError as policy_error:
        if policy_error.status not in _REFRESHABLE_POLICY_STATUSES:
            raise
        try:
            from .native_core_lease import refresh_native_core_lease

            refresh_native_core_lease(client, NativeCoreFeature.EXPORT)
        except Exception as refresh_error:
            raise policy_error from refresh_error
        return client.begin_encrypted_export(
            export_id,
            plaintext_size=plaintext_size,
            content_key=content_key,
            chunk_size=chunk_size,
        )


def _begin_decrypted_export(
    client: NativeCoreClient,
    *,
    header: NativeCoreEncryptedExportHeader,
    content_key: bytes | bytearray | memoryview,
):
    try:
        return client.begin_decrypted_export(
            header.encoded,
            content_key=content_key,
        )
    except NativeCorePolicyError as policy_error:
        if policy_error.status not in _REFRESHABLE_POLICY_STATUSES:
            raise
        try:
            from .native_core_lease import refresh_native_core_lease

            refresh_native_core_lease(client, NativeCoreFeature.EXPORT)
        except Exception as refresh_error:
            raise policy_error from refresh_error
        return client.begin_decrypted_export(
            header.encoded,
            content_key=content_key,
        )


def _publish_temp_file(temp_path: Path, destination: Path, *, overwrite: bool) -> None:
    if overwrite:
        os.replace(temp_path, destination)
        return

    if os.name == "nt":
        os.rename(temp_path, destination)
        return

    if sys.platform == "darwin":
        renamex_np = ctypes.CDLL(None, use_errno=True).renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        ctypes.set_errno(0)
        if renamex_np(
            os.fsencode(temp_path),
            os.fsencode(destination),
            0x00000004,  # RENAME_EXCL
        ) != 0:
            error = ctypes.get_errno() or errno.EIO
            if error == errno.EEXIST:
                raise FileExistsError(
                    error, os.strerror(error), os.fspath(destination)
                )
            raise OSError(error, os.strerror(error), os.fspath(destination))
        return

    # Linking within the destination directory provides an atomic no-replace
    # publish on other POSIX development platforms.
    os.link(temp_path, destination)
    try:
        temp_path.unlink()
    except OSError:
        destination.unlink(missing_ok=True)
        raise


def _sync_parent_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path.parent, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        os.close(descriptor)


def encrypt_export_file(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str] | None = None,
    *,
    export_id: str,
    content_key: bytes | bytearray | memoryview,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overwrite: bool = False,
) -> NativeEncryptedExportResult:
    """Encrypt one completed export artifact into an atomic WEC1 container.

    The source file is never modified. The process-wide export-only operation
    token is held through publish and cleanup.
    """

    source = Path(source_path).expanduser().resolve(strict=True)
    destination_value = (
        Path(output_path)
        if output_path is not None
        else source.with_name(source.name + ".wec")
    )
    destination = _canonical_destination(destination_value)
    if _same_file(source, destination):
        raise ValueError("encrypted export output must differ from the source file")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)

    key_view = memoryview(content_key)
    try:
        key_size = key_view.nbytes
    finally:
        key_view.release()
    if key_size != 32:
        raise ValueError("content_key must contain exactly 32 bytes")
    selected_chunk_size = int(chunk_size)
    if not 64 * 1024 <= selected_chunk_size <= 768 * 1024:
        raise ValueError("chunk_size must be between 65536 and 786432")

    with source.open("rb") as source_file, ExitStack() as operation_stack:
        source_before = os.fstat(source_file.fileno())
        if not stat.S_ISREG(source_before.st_mode):
            raise ValueError("encrypted export source must be a regular file")
        plaintext_size = int(source_before.st_size)
        if not 1 <= plaintext_size <= _MAX_PLAINTEXT_SIZE:
            raise ValueError(
                "encrypted export source size must be between 1 and 274877906944"
            )

        managed_operation = managed_native_core_operation(export_only=True)
        operation_stack.enter_context(managed_operation)
        active_client = get_native_core_client()

        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".wce-",
            suffix=".tmp",
            dir=destination.parent,
        )
        temp_path = Path(raw_temp_path)
        session = None
        published = False
        encrypted_size = 0
        try:
            key = bytearray(content_key)
            try:
                if len(key) != 32:
                    raise ValueError("content_key must contain exactly 32 bytes")
                session = _begin_encrypted_export(
                    active_client,
                    export_id=export_id,
                    plaintext_size=plaintext_size,
                    content_key=key,
                    chunk_size=selected_chunk_size,
                )
            finally:
                key[:] = b"\x00" * len(key)
            with os.fdopen(descriptor, "wb") as output_file:
                descriptor = -1
                output_file.write(session.header.encoded)
                encrypted_size += len(session.header.encoded)
                remaining = plaintext_size
                while remaining:
                    expected_size = min(session.header.chunk_size, remaining)
                    payload = source_file.read(expected_size)
                    if len(payload) != expected_size:
                        raise OSError("export source changed while it was being encrypted")
                    record = session.write(payload)
                    output_file.write(record)
                    encrypted_size += len(record)
                    remaining -= len(payload)
                if source_file.read(1):
                    raise OSError("export source changed while it was being encrypted")

                source_after = os.fstat(source_file.fileno())
                source_identity_before = (
                    source_before.st_dev,
                    source_before.st_ino,
                    source_before.st_size,
                    source_before.st_mtime_ns,
                )
                source_identity_after = (
                    source_after.st_dev,
                    source_after.st_ino,
                    source_after.st_size,
                    source_after.st_mtime_ns,
                )
                if source_identity_after != source_identity_before:
                    raise OSError("export source changed while it was being encrypted")

                session.finish()
                output_file.flush()
                os.fsync(output_file.fileno())

            _publish_temp_file(temp_path, destination, overwrite=overwrite)
            published = True
            _sync_parent_directory(destination)
            return NativeEncryptedExportResult(
                source_path=source,
                output_path=destination,
                export_id=session.header.export_id,
                plaintext_size=session.header.plaintext_size,
                encrypted_size=encrypted_size,
                chunk_size=session.header.chunk_size,
                chunk_count=session.header.chunk_count,
                header=session.header,
            )
        except BaseException:
            if session is not None and not session.closed:
                try:
                    session.abort()
                except Exception:
                    pass
            raise
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if not published:
                temp_path.unlink(missing_ok=True)


def encrypt_export_file_and_remove_source(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str] | None = None,
    *,
    export_id: str,
    content_key: bytes | bytearray | memoryview,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overwrite: bool = False,
) -> NativeEncryptedExportResult:
    """Create WEC1 output and remove the generated plaintext artifact.

    This helper is intended only for newly generated export files. The source
    is removed even when encryption fails so an explicitly encrypted export
    cannot silently leave a plaintext result behind.
    """

    source = Path(source_path).expanduser().resolve(strict=True)
    try:
        return encrypt_export_file(
            source,
            output_path,
            export_id=export_id,
            content_key=content_key,
            chunk_size=chunk_size,
            overwrite=overwrite,
        )
    finally:
        source.unlink(missing_ok=True)


def decrypt_export_file(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str] | None = None,
    *,
    content_key: bytes | bytearray | memoryview,
    overwrite: bool = False,
) -> NativeDecryptedExportResult:
    """Decrypt a WEC1 artifact into an atomically published plaintext file."""

    source = Path(source_path).expanduser().resolve(strict=True)
    if output_path is None:
        if source.suffix.lower() != ".wec":
            raise ValueError(
                "output_path is required when the encrypted source does not use .wec"
            )
        destination_value = source.with_suffix("")
    else:
        destination_value = Path(output_path)
    destination = _canonical_plaintext_destination(destination_value)
    if _same_file(source, destination):
        raise ValueError("decrypted export output must differ from the source file")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)

    key_view = memoryview(content_key)
    try:
        key_size = key_view.nbytes
    finally:
        key_view.release()
    if key_size != 32:
        raise ValueError("content_key must contain exactly 32 bytes")

    with source.open("rb") as source_file, ExitStack() as operation_stack:
        source_before = os.fstat(source_file.fileno())
        if not stat.S_ISREG(source_before.st_mode):
            raise ValueError("encrypted export source must be a regular file")

        fixed_header = source_file.read(64)
        if len(fixed_header) != 64:
            raise NativeCoreProtocolError("encrypted export header is truncated.")
        header_size = int(struct.unpack_from("<I", fixed_header, 8)[0])
        if not 65 <= header_size <= 192:
            raise NativeCoreProtocolError("encrypted export header has an invalid size.")
        header_suffix = source_file.read(header_size - 64)
        if len(header_suffix) != header_size - 64:
            raise NativeCoreProtocolError("encrypted export header is truncated.")
        header = parse_native_encrypted_export_header(fixed_header + header_suffix)

        managed_operation = managed_native_core_operation(export_only=True)
        operation_stack.enter_context(managed_operation)
        active_client = get_native_core_client()

        descriptor, raw_temp_path = tempfile.mkstemp(
            prefix=".wcd-",
            suffix=".tmp",
            dir=destination.parent,
        )
        temp_path = Path(raw_temp_path)
        session = None
        published = False
        try:
            key = bytearray(content_key)
            try:
                if len(key) != 32:
                    raise ValueError("content_key must contain exactly 32 bytes")
                session = _begin_decrypted_export(
                    active_client,
                    header=header,
                    content_key=key,
                )
            finally:
                key[:] = b"\x00" * len(key)

            with os.fdopen(descriptor, "wb") as output_file:
                descriptor = -1
                bytes_written = 0
                for _chunk_index in range(header.chunk_count):
                    expected_size = min(
                        header.chunk_size,
                        header.plaintext_size - bytes_written,
                    )
                    record_prefix = source_file.read(24)
                    if len(record_prefix) != 24:
                        raise NativeCoreProtocolError(
                            "encrypted export record is truncated."
                        )
                    record_body = source_file.read(16 + expected_size)
                    if len(record_body) != 16 + expected_size:
                        raise NativeCoreProtocolError(
                            "encrypted export record is truncated."
                        )
                    plaintext = session.write(record_prefix + record_body)
                    output_file.write(plaintext)
                    bytes_written += len(plaintext)

                if source_file.read(1):
                    raise NativeCoreProtocolError(
                        "encrypted export contains trailing data."
                    )

                source_after = os.fstat(source_file.fileno())
                source_identity_before = (
                    source_before.st_dev,
                    source_before.st_ino,
                    source_before.st_size,
                    source_before.st_mtime_ns,
                )
                source_identity_after = (
                    source_after.st_dev,
                    source_after.st_ino,
                    source_after.st_size,
                    source_after.st_mtime_ns,
                )
                if source_identity_after != source_identity_before:
                    raise OSError("encrypted export changed while it was being decrypted")

                session.finish()
                output_file.flush()
                os.fsync(output_file.fileno())

            _publish_temp_file(temp_path, destination, overwrite=overwrite)
            published = True
            _sync_parent_directory(destination)
            return NativeDecryptedExportResult(
                source_path=source,
                output_path=destination,
                export_id=header.export_id,
                plaintext_size=header.plaintext_size,
                encrypted_size=int(source_before.st_size),
                chunk_size=header.chunk_size,
                chunk_count=header.chunk_count,
                header=header,
            )
        except BaseException:
            if session is not None and not session.closed:
                try:
                    session.abort()
                except Exception:
                    pass
            raise
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if not published:
                temp_path.unlink(missing_ok=True)


__all__ = [
    "NativeDecryptedExportResult",
    "NativeEncryptedExportResult",
    "NativeSealedExportResult",
    "decode_export_content_key",
    "decrypt_export_file",
    "erase_export_content_key",
    "encrypt_export_file",
    "encrypt_export_file_and_remove_source",
    "seal_export_manifest",
]
