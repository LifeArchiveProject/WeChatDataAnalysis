from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_DEVICE_KEY_PREFIX = "LifeArchiveProject.WeChatDB.Native.RealSmoke."

from wechat_decrypt_tool import native_core_broker as broker
from wechat_decrypt_tool import native_core_client as core
from wechat_decrypt_tool import native_core_export
from wechat_decrypt_tool import native_core_lease
from wechat_decrypt_tool.native_core_device_credential import DeviceCredentialStore


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only smoke test for a real encrypted WeChat database."
    )
    parser.add_argument("--key-store", type=Path, required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument(
        "--native-dir",
        type=Path,
        default=ROOT.parent / "wechatdb-native" / "build" / "windows-vs" / "Release",
    )
    parser.add_argument("--database", default="session/session.db")
    parser.add_argument(
        "--all-databases",
        action="store_true",
        help="Open every .db file below db_storage and prove the originals remain unchanged.",
    )
    parser.add_argument(
        "--verify-credential-renewal",
        action="store_true",
        help="Force a second production lease refresh using the persisted device credential.",
    )
    parser.add_argument(
        "--verify-export",
        action="store_true",
        help="Create temporary WES1 and WEC1 artifacts through the online-authorized broker.",
    )
    parser.add_argument(
        "--temporary-root",
        type=Path,
        help="Private work directory whose parent process can remove it after a forced timeout.",
    )
    parser.add_argument(
        "--device-key-name",
        help="Ephemeral CNG key name preallocated by the parent acceptance harness.",
    )
    return parser.parse_args()


def _device_key_name(explicit: str | None) -> str:
    value = str(explicit or (_DEVICE_KEY_PREFIX + uuid.uuid4().hex)).strip()
    if re.fullmatch(re.escape(_DEVICE_KEY_PREFIX) + r"[0-9a-f]{32}", value) is None:
        raise RuntimeError("Smoke device key name is outside the ephemeral test namespace.")
    return value


@contextmanager
def _temporary_root(explicit: Path | None) -> Iterator[Path]:
    if explicit is None:
        with TemporaryDirectory(prefix="wda-native-real-smoke-") as raw_temp:
            yield Path(raw_temp)
        return

    path = explicit.expanduser().resolve()
    if path.exists():
        raise RuntimeError("Explicit smoke temporary root already exists.")
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _signed_lease(
    private_key: ec.EllipticCurvePrivateKey,
    status: core.NativeCoreRuntimeStatus,
    features: int,
) -> bytes:
    now = int(time.time())
    unsigned = (
        struct.pack(
            "<4sHHQQQQQ",
            b"WCL1",
            1,
            0,
            now,
            now - 1,
            now + 600,
            1,
            int(features),
        )
        + uuid.uuid4().bytes
        + status.device_id
        + status.build_id
        + status.startup_nonce
    )
    signature = private_key.sign(unsigned, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(signature)
    return unsigned + r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _delete_windows_device_key(key_name: str) -> None:
    if not sys.platform.startswith("win"):
        return
    ncrypt = ctypes.WinDLL("ncrypt")
    ncrypt.NCryptOpenStorageProvider.argtypes = [
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    ncrypt.NCryptOpenKey.argtypes = [
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    ncrypt.NCryptDeleteKey.argtypes = [ctypes.c_size_t, ctypes.c_uint32]
    ncrypt.NCryptFreeObject.argtypes = [ctypes.c_size_t]
    silent = 0x00000040
    for provider_name in (
        "Microsoft Platform Crypto Provider",
        "Microsoft Software Key Storage Provider",
    ):
        provider = ctypes.c_size_t()
        if ncrypt.NCryptOpenStorageProvider(ctypes.byref(provider), provider_name, 0) != 0:
            continue
        try:
            key = ctypes.c_size_t()
            if ncrypt.NCryptOpenKey(
                provider.value, ctypes.byref(key), key_name, 0, silent
            ) == 0:
                if ncrypt.NCryptDeleteKey(key.value, 0) != 0:
                    ncrypt.NCryptFreeObject(key.value)
        finally:
            ncrypt.NCryptFreeObject(provider.value)


def _load_target(
    key_store_path: Path,
    account: str,
    database_relative_path: str,
) -> tuple[Path, Path, bytearray, str]:
    store = json.loads(key_store_path.read_text(encoding="utf-8"))
    if not isinstance(store, dict):
        raise RuntimeError("Key store root must be a JSON object.")
    entry = store.get(account)
    if not isinstance(entry, dict):
        raise RuntimeError(f"Account is not present in key store: {account}")

    encoded_key = str(entry.get("db_key") or "").strip()
    storage_value = str(entry.get("db_key_source_db_storage_path") or "").strip()
    if len(encoded_key) != 64:
        raise RuntimeError("Account does not contain a 32-byte database key.")
    try:
        key = bytearray.fromhex(encoded_key)
    except ValueError as exc:
        raise RuntimeError("Account database key is not valid hexadecimal.") from exc

    encoded_key = ""
    entry.clear()
    store.clear()
    storage = Path(storage_value).expanduser().resolve(strict=True)
    database = (storage / Path(database_relative_path)).resolve(strict=True)
    if storage not in database.parents or not database.is_file():
        key[:] = b"\0" * len(key)
        raise RuntimeError("Database path escaped db_storage or is not a file.")
    fingerprint = hashlib.sha256(key).hexdigest()[:16]
    return storage, database, key, fingerprint


def _query_records(database: core.NativeCoreDatabase, sql: str) -> tuple[dict, ...]:
    with database.open_query(sql) as query:
        rows: list[dict] = []
        while True:
            page = query.fetch(max_rows=2048, max_bytes=256 * 1024)
            rows.extend(dict(row) for row in page.records())
            if not page.has_more:
                return tuple(rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _database_failure_marker(storage: Path, database: Path, error: Exception) -> str:
    relative = database.relative_to(storage).as_posix()
    path_sha256 = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
    status = getattr(error, "status", None)
    status_value = str(status) if type(status) is int else "unknown"
    return f"pathSha256={path_sha256} status={status_value}"


def _authorization_profile(manifest_path: Path) -> str:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Native core build manifest is unreadable.") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError("Native core build manifest root must be an object.")
    development = manifest.get("developmentBuild")
    staging_trust = manifest.get("stagingPinnedSignerTrust")
    if development is True and staging_trust is False:
        return "development"
    if development is False and staging_trust is True:
        return "staging"
    if development is False and staging_trust is False:
        return "production"
    raise RuntimeError("Native core build manifest has an invalid build profile.")


def _discover_databases(storage: Path) -> tuple[Path, ...]:
    databases: list[Path] = []
    for candidate in storage.rglob("*"):
        if candidate.suffix.lower() != ".db":
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if storage not in resolved.parents or not resolved.is_file():
            continue
        databases.append(resolved)
    databases.sort(key=lambda path: path.relative_to(storage).as_posix().lower())
    if not databases:
        raise RuntimeError(f"No database files were found below: {storage}")
    return tuple(databases)


def _inspect_database(
    client: core.NativeCoreClient,
    database: Path,
    key: bytearray,
) -> tuple[tuple[dict, ...], int | None]:
    with client.open_database(
        database,
        key=key,
        key_mode=core.NativeCoreDatabaseKeyMode.AUTO,
    ) as opened:
        schema_rows = _query_records(
            opened,
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table', 'view') ORDER BY name",
        )
        schema_names = {str(row["name"]) for row in schema_rows}
        session_count = None
        if "SessionTable" in schema_names:
            session_count = int(
                _query_records(
                    opened,
                    "SELECT COUNT(*) AS session_count FROM SessionTable",
                )[0]["session_count"]
            )
    return schema_rows, session_count


def main() -> int:
    args = _parse_args()
    native_dir = args.native_dir.expanduser().resolve(strict=True)
    broker_path = native_dir / "wechatdb_broker.exe"
    client_path = native_dir / "wechatdb_client.dll"
    manifest_path = native_dir / "wechatdb_native_build.json"
    for component in (broker_path, client_path, manifest_path):
        if not component.is_file():
            raise RuntimeError(f"Native component is missing: {component}")
    authorization_profile = _authorization_profile(manifest_path)

    storage, database, key, fingerprint = _load_target(
        args.key_store.expanduser().resolve(strict=True),
        str(args.account).strip(),
        str(args.database),
    )
    private_key = (
        ec.generate_private_key(ec.SECP256R1())
        if authorization_profile == "development"
        else None
    )
    device_key_name = _device_key_name(args.device_key_name)

    broker.stop_native_core_broker()
    try:
        databases = _discover_databases(storage) if args.all_databases else (database,)
        if database not in databases:
            databases = tuple(sorted((*databases, database), key=os.fspath))
        source_hashes = {candidate: _sha256_file(candidate) for candidate in databases}
        with _temporary_root(args.temporary_root) as temp_dir:
            environment = {
                "WECHAT_TOOL_DATA_DIR": str(temp_dir / "app-data"),
                broker.ENV_NATIVE_CORE_BROKER: str(broker_path),
                broker.ENV_NATIVE_CORE_DEVICE_KEY_NAME: device_key_name,
                core.ENV_NATIVE_CORE_LIBRARY: str(client_path),
                core.ENV_NATIVE_CORE_MODE: core.NativeCoreMode.REQUIRED.value,
            }
            controlled_names = set(environment)
            controlled_names.update(
                {
                    broker.ENV_NATIVE_CORE_TRUST_KEY,
                    core.ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
                    core.ENV_NATIVE_CORE_ALLOW_STAGING_BUILD,
                }
            )
            if authorization_profile == "development":
                if private_key is None:
                    raise RuntimeError("Development lease key was not initialized.")
                public = private_key.public_key().public_numbers()
                public_hex = (
                    public.x.to_bytes(32, "big").hex()
                    + public.y.to_bytes(32, "big").hex()
                )
                trust_path = temp_dir / "trust-key.hex"
                trust_path.write_text(public_hex + "\n", encoding="ascii")
                environment[broker.ENV_NATIVE_CORE_TRUST_KEY] = str(trust_path)
                environment[core.ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD] = "1"
            elif authorization_profile == "staging":
                environment[core.ENV_NATIVE_CORE_ALLOW_STAGING_BUILD] = "1"
            previous = {name: os.environ.get(name) for name in controlled_names}
            for name in controlled_names:
                os.environ.pop(name, None)
            os.environ.update(environment)
            try:
                broker.ensure_native_core_broker(database_root=storage)
                client = core.get_native_core_client()
                runtime = client.get_status()
                requested_features = int(core.NativeCoreFeature.DATABASE_READ)
                if authorization_profile == "development":
                    if private_key is None:
                        raise RuntimeError("Development lease key was not initialized.")
                    client.install_lease(
                        _signed_lease(private_key, runtime, requested_features)
                    )
                else:
                    first_refresh = native_core_lease.refresh_native_core_lease(
                        client, core.NativeCoreFeature.DATABASE_READ
                    )
                    if not first_refresh.refreshed:
                        raise RuntimeError("Production smoke did not refresh its first lease.")
                credential_persisted = False
                credential_stable_across_renewal = False
                second_lease_refreshed = False
                wes1_seal_verified = False
                wec1_encryption_verified = False
                wec1_decryption_verified = False
                if args.verify_credential_renewal:
                    if authorization_profile not in {"production", "staging"}:
                        raise RuntimeError(
                            "Credential renewal verification requires an online-authorized build."
                        )
                    credential_path = DeviceCredentialStore().path
                    if not credential_path.is_file():
                        raise RuntimeError(
                            "Production smoke did not persist a device credential."
                        )
                    credential_persisted = True
                    credential_digest = _sha256_file(credential_path)
                    second_refresh = native_core_lease.refresh_native_core_lease(
                        client,
                        core.NativeCoreFeature.DATABASE_READ,
                        minimum_validity_seconds=24 * 60 * 60,
                    )
                    if not second_refresh.refreshed:
                        raise RuntimeError(
                            "Production smoke did not perform its credential renewal."
                        )
                    second_lease_refreshed = True
                    credential_stable_across_renewal = (
                        credential_path.is_file()
                        and _sha256_file(credential_path) == credential_digest
                    )
                    if not credential_stable_across_renewal:
                        raise RuntimeError(
                            "Device credential changed during an authenticated renewal."
                        )
                inspected: list[dict[str, object]] = []
                selected_schema_rows: tuple[dict, ...] = ()
                session_count = None
                for candidate in databases:
                    try:
                        schema_rows, candidate_session_count = _inspect_database(
                            client, candidate, key
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            "Native core could not open database: "
                            + _database_failure_marker(storage, candidate, exc)
                        ) from None
                    if candidate == database:
                        selected_schema_rows = schema_rows
                        session_count = candidate_session_count
                    inspected.append(
                        {
                            "path": candidate.relative_to(storage).as_posix(),
                            "bytes": candidate.stat().st_size,
                            "objectCount": len(schema_rows),
                            "sessionCount": candidate_session_count,
                        }
                    )
                if args.verify_export:
                    core.close_native_core_client()
                    export_manifest = json.dumps(
                        {
                            "schemaVersion": 1,
                            "exportId": "native-real-smoke",
                            "databaseCount": len(inspected),
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    sealed = native_core_export.seal_export_manifest(
                        "native-real-smoke",
                        export_manifest,
                    )
                    wes1_seal_verified = sealed.envelope.startswith(b"WES1")
                    if not wes1_seal_verified:
                        raise RuntimeError("Production smoke did not produce a WES1 envelope.")

                    plaintext_path = temp_dir / "native-real-smoke.bin"
                    encrypted_path = temp_dir / "native-real-smoke.wec"
                    decrypted_path = temp_dir / "native-real-smoke.decrypted.bin"
                    plaintext = b"wechatdb-native-export-smoke\n" * 8192
                    plaintext_path.write_bytes(plaintext)
                    content_key = bytearray(os.urandom(32))
                    try:
                        encrypted = native_core_export.encrypt_export_file(
                            plaintext_path,
                            encrypted_path,
                            export_id="native-real-smoke",
                            content_key=content_key,
                        )
                        decrypted = native_core_export.decrypt_export_file(
                            encrypted_path,
                            decrypted_path,
                            content_key=content_key,
                        )
                    finally:
                        content_key[:] = b"\0" * len(content_key)
                    wec1_encryption_verified = (
                        encrypted.output_path == encrypted_path
                        and encrypted.plaintext_size == len(plaintext)
                        and encrypted_path.read_bytes()[:4] == b"WEC1"
                        and plaintext_path.read_bytes() == plaintext
                    )
                    if not wec1_encryption_verified:
                        raise RuntimeError("Production smoke did not produce a valid WEC1 artifact.")
                    wec1_decryption_verified = (
                        decrypted.output_path == decrypted_path
                        and decrypted.plaintext_size == len(plaintext)
                        and decrypted_path.read_bytes() == plaintext
                    )
                    if not wec1_decryption_verified:
                        raise RuntimeError(
                            "Production smoke did not decrypt the WEC1 artifact exactly."
                        )
            finally:
                try:
                    core.close_native_core_client()
                finally:
                    try:
                        # Release the broker's Windows log handle before the
                        # TemporaryDirectory context removes its data root.
                        broker.stop_native_core_broker()
                    finally:
                        try:
                            logging.shutdown()
                        finally:
                            for name, value in previous.items():
                                if value is None:
                                    os.environ.pop(name, None)
                                else:
                                    os.environ[name] = value

        changed_sources = [
            candidate.relative_to(storage).as_posix()
            for candidate, before in source_hashes.items()
            if _sha256_file(candidate) != before
        ]
        if changed_sources:
            raise RuntimeError(
                "Source databases changed during native-core smoke: "
                + ", ".join(changed_sources)
            )

        print(
            json.dumps(
                {
                    "status": "ok",
                    "authorizationProfile": authorization_profile,
                    "account": str(args.account).strip(),
                    "database": str(database),
                    "keyFingerprint": fingerprint,
                    "objectCount": len(selected_schema_rows),
                    "sessionCount": session_count,
                    "databaseCount": len(inspected),
                    "databaseBytes": sum(int(item["bytes"]) for item in inspected),
                    "databases": inspected,
                    "sourceHashesStable": True,
                    "credentialPersisted": credential_persisted,
                    "credentialStableAcrossRenewal": credential_stable_across_renewal,
                    "secondLeaseRefreshed": second_lease_refreshed,
                    "wes1SealVerified": wes1_seal_verified,
                    "wec1EncryptionVerified": wec1_encryption_verified,
                    "wec1DecryptionVerified": wec1_decryption_verified,
                    "brokerProcessId": int(runtime.broker_process_id),
                    "buildId": runtime.build_id.hex(),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        key[:] = b"\0" * len(key)
        broker.stop_native_core_broker()
        _delete_windows_device_key(device_key_name)


if __name__ == "__main__":
    raise SystemExit(main())
