from __future__ import annotations

import hashlib
import os
import struct
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .app_paths import get_data_dir


_ENVELOPE_MAGIC = b"WCEKEY01"
_PLAINTEXT_MAGIC = b"WCERAW01"
_DPAPI_MAGIC = b"WCEDP001"
_KDF_SALT_BYTES = 16
_NONCE_BYTES = 12
_PATH_DIGEST_BYTES = 32
_DATABASE_SALT_BYTES = 16
_RAW_KEY_BYTES = 32
_DATABASE_KDF_PROFILE = b"pbkdf2-hmac-sha512:256000:32"
_MAX_RECORDS = 64
_MAX_CACHE_FILE_BYTES = 128 * 1024
_RECORD_BYTES = _PATH_DIGEST_BYTES + _DATABASE_SALT_BYTES + _RAW_KEY_BYTES
_CACHE_LOCK = threading.RLock()


@dataclass
class CachedRawKey:
    salt: bytes
    key: bytearray = field(repr=False)


def database_cache_key(path: Path) -> str:
    candidate = Path(path).expanduser()
    try:
        candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        candidate = candidate.absolute()
    return os.path.normcase(os.fspath(candidate))


def _cache_directory() -> Path:
    return get_data_dir() / ".native-core-cache-v1"


def _digest_cache_key(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).digest()


def _root_digest(database_root: Path) -> bytes:
    return _digest_cache_key(database_cache_key(database_root))


def _cache_path(database_root: Path) -> Path:
    return _cache_directory() / f"{_root_digest(database_root).hex()}.bin"


def _derive_envelope_key(database_key: bytes | bytearray, salt: bytes) -> bytearray:
    if len(database_key) != _RAW_KEY_BYTES:
        raise ValueError("A 32-byte database key is required for the raw-key cache.")
    return bytearray(
        HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"WeChatDataAnalysis native-core raw-key cache v1",
        ).derive(database_key)
    )


def _envelope_aad(header: bytes, root_digest: bytes) -> bytes:
    return header + root_digest + b"\0" + _DATABASE_KDF_PROFILE


def _dpapi_transform(
    payload: bytes,
    *,
    entropy: bytes,
    protect: bool,
) -> bytes:
    import ctypes
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def make_blob(data: bytes) -> tuple[_DataBlob, object]:
        buffer = (ctypes.c_ubyte * max(1, len(data)))()
        if data:
            ctypes.memmove(buffer, data, len(data))
        return (
            _DataBlob(
                cbData=len(data),
                pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
            ),
            buffer,
        )

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    input_blob, input_buffer = make_blob(payload)
    entropy_blob, entropy_buffer = make_blob(entropy)
    output_blob = _DataBlob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    if protect:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        )
    else:
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            flags,
            ctypes.byref(output_blob),
        )

    del input_buffer, entropy_buffer
    if not ok:
        error = ctypes.WinError(ctypes.get_last_error())
        if output_blob.pbData:
            kernel32.LocalFree(
                wintypes.HLOCAL(
                    ctypes.cast(output_blob.pbData, ctypes.c_void_p).value
                )
            )
        raise error
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(
                wintypes.HLOCAL(
                    ctypes.cast(output_blob.pbData, ctypes.c_void_p).value
                )
            )


def _protect_platform_payload(payload: bytes, root_digest: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        return payload
    protected = _dpapi_transform(
        payload,
        entropy=b"WeChatDataAnalysis raw-key cache v1\0" + root_digest,
        protect=True,
    )
    return _DPAPI_MAGIC + protected


def _unprotect_platform_payload(payload: bytes, root_digest: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        return payload
    if not payload.startswith(_DPAPI_MAGIC):
        raise ValueError("Windows raw-key cache is not DPAPI protected.")
    return _dpapi_transform(
        payload[len(_DPAPI_MAGIC) :],
        entropy=b"WeChatDataAnalysis raw-key cache v1\0" + root_digest,
        protect=False,
    )


def _zero_key_records(records: Mapping[bytes, CachedRawKey]) -> None:
    for entry in records.values():
        entry.key[:] = b"\0" * len(entry.key)


def _decode_records(plaintext: bytearray) -> dict[bytes, CachedRawKey]:
    header_bytes = len(_PLAINTEXT_MAGIC) + 2
    if len(plaintext) < header_bytes or bytes(plaintext[: len(_PLAINTEXT_MAGIC)]) != _PLAINTEXT_MAGIC:
        raise ValueError("Invalid raw-key cache plaintext header.")
    count = struct.unpack_from("<H", plaintext, len(_PLAINTEXT_MAGIC))[0]
    if count > _MAX_RECORDS or len(plaintext) != header_bytes + count * _RECORD_BYTES:
        raise ValueError("Invalid raw-key cache record count.")

    records: dict[bytes, CachedRawKey] = {}
    offset = header_bytes
    for _index in range(count):
        path_digest = bytes(plaintext[offset : offset + _PATH_DIGEST_BYTES])
        offset += _PATH_DIGEST_BYTES
        database_salt = bytes(plaintext[offset : offset + _DATABASE_SALT_BYTES])
        offset += _DATABASE_SALT_BYTES
        raw_key = bytearray(plaintext[offset : offset + _RAW_KEY_BYTES])
        offset += _RAW_KEY_BYTES
        replaced = records.get(path_digest)
        if replaced is not None:
            replaced.key[:] = b"\0" * len(replaced.key)
        records[path_digest] = CachedRawKey(salt=database_salt, key=raw_key)
    return records


def _encode_records(records: Mapping[bytes, CachedRawKey]) -> bytearray:
    if len(records) > _MAX_RECORDS:
        raise ValueError("Raw-key cache contains too many database records.")
    plaintext = bytearray(_PLAINTEXT_MAGIC)
    plaintext.extend(struct.pack("<H", len(records)))
    for path_digest, entry in sorted(records.items(), key=lambda item: item[0]):
        if (
            len(path_digest) != _PATH_DIGEST_BYTES
            or len(entry.salt) != _DATABASE_SALT_BYTES
            or len(entry.key) != _RAW_KEY_BYTES
        ):
            raise ValueError("Invalid raw-key cache record.")
        plaintext.extend(path_digest)
        plaintext.extend(entry.salt)
        plaintext.extend(entry.key)
    return plaintext


def _load_all_records(
    database_root: Path,
    database_key: bytes | bytearray,
) -> dict[bytes, CachedRawKey]:
    path = _cache_path(database_root)
    try:
        size = path.stat().st_size
        if size <= 0 or size > _MAX_CACHE_FILE_BYTES:
            return {}
        payload = path.read_bytes()
    except OSError:
        return {}

    try:
        payload = _unprotect_platform_payload(payload, _root_digest(database_root))
    except (OSError, ValueError):
        return {}

    header_bytes = len(_ENVELOPE_MAGIC) + _KDF_SALT_BYTES + _NONCE_BYTES
    if len(payload) <= header_bytes + 16 or payload[: len(_ENVELOPE_MAGIC)] != _ENVELOPE_MAGIC:
        return {}
    kdf_salt_offset = len(_ENVELOPE_MAGIC)
    nonce_offset = kdf_salt_offset + _KDF_SALT_BYTES
    kdf_salt = payload[kdf_salt_offset:nonce_offset]
    nonce = payload[nonce_offset:header_bytes]
    header = payload[:header_bytes]
    envelope_key: bytearray | None = None
    try:
        envelope_key = _derive_envelope_key(database_key, kdf_salt)
        decrypted = AESGCM(envelope_key).decrypt(
            nonce,
            payload[header_bytes:],
            _envelope_aad(header, _root_digest(database_root)),
        )
    except (InvalidTag, ValueError):
        return {}
    finally:
        if envelope_key is not None:
            envelope_key[:] = b"\0" * len(envelope_key)

    plaintext = bytearray(decrypted)
    try:
        return _decode_records(plaintext)
    except ValueError:
        return {}
    finally:
        plaintext[:] = b"\0" * len(plaintext)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _write_all_records(
    database_root: Path,
    database_key: bytes | bytearray,
    records: Mapping[bytes, CachedRawKey],
) -> None:
    path = _cache_path(database_root)
    if not records:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    kdf_salt = os.urandom(_KDF_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    header = _ENVELOPE_MAGIC + kdf_salt + nonce
    plaintext = _encode_records(records)
    envelope_key: bytearray | None = None
    try:
        envelope_key = _derive_envelope_key(database_key, kdf_salt)
        ciphertext = AESGCM(envelope_key).encrypt(
            nonce,
            plaintext,
            _envelope_aad(header, _root_digest(database_root)),
        )
        payload = _protect_platform_payload(
            header + ciphertext,
            _root_digest(database_root),
        )
        _atomic_write(path, payload)
    finally:
        if envelope_key is not None:
            envelope_key[:] = b"\0" * len(envelope_key)
        plaintext[:] = b"\0" * len(plaintext)


def _require_database_under_root(database_root: Path, database_path: Path) -> None:
    root = Path(database_root).expanduser().resolve(strict=True)
    candidate = Path(database_path).expanduser().resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Raw-key cache database escaped its database root.") from exc


def load_cached_raw_keys(
    database_root: Path,
    database_key: bytes | bytearray,
    database_paths: Iterable[Path],
) -> dict[str, CachedRawKey]:
    requested: dict[bytes, str] = {}
    for database_path in database_paths:
        try:
            _require_database_under_root(database_root, database_path)
        except (OSError, ValueError):
            continue
        cache_key = database_cache_key(database_path)
        requested[_digest_cache_key(cache_key)] = cache_key
    if not requested:
        return {}

    with _CACHE_LOCK:
        records = _load_all_records(database_root, database_key)
    selected: dict[str, CachedRawKey] = {}
    for path_digest, entry in records.items():
        cache_key = requested.get(path_digest)
        if cache_key is None:
            entry.key[:] = b"\0" * len(entry.key)
            continue
        selected[cache_key] = entry
    return selected


def merge_cached_raw_keys(
    database_root: Path,
    database_key: bytes | bytearray,
    entries: Mapping[Path, tuple[bytes, bytes | bytearray]],
) -> bool:
    updates: dict[bytes, CachedRawKey] = {}
    for database_path, (database_salt, raw_key) in entries.items():
        _require_database_under_root(database_root, database_path)
        if len(database_salt) != _DATABASE_SALT_BYTES or len(raw_key) != _RAW_KEY_BYTES:
            raise ValueError("Raw-key cache entries require a 16-byte salt and 32-byte key.")
        path_digest = _digest_cache_key(database_cache_key(database_path))
        updates[path_digest] = CachedRawKey(
            salt=bytes(database_salt),
            key=bytearray(raw_key),
        )
    if not updates:
        return False

    with _CACHE_LOCK:
        records = _load_all_records(database_root, database_key)
        try:
            for path_digest, entry in updates.items():
                replaced = records.pop(path_digest, None)
                if replaced is not None:
                    replaced.key[:] = b"\0" * len(replaced.key)
                records[path_digest] = entry
            _write_all_records(database_root, database_key, records)
            return True
        finally:
            _zero_key_records(records)


def remove_cached_raw_key(
    database_root: Path,
    database_key: bytes | bytearray,
    database_path: Path,
) -> bool:
    try:
        _require_database_under_root(database_root, database_path)
    except (OSError, ValueError):
        return False
    path_digest = _digest_cache_key(database_cache_key(database_path))
    with _CACHE_LOCK:
        records = _load_all_records(database_root, database_key)
        removed = records.pop(path_digest, None)
        try:
            if removed is None:
                return False
            removed.key[:] = b"\0" * len(removed.key)
            _write_all_records(database_root, database_key, records)
            return True
        finally:
            _zero_key_records(records)


def remove_cache_for_root(database_root: Path) -> bool:
    with _CACHE_LOCK:
        try:
            _cache_path(database_root).unlink(missing_ok=False)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False
