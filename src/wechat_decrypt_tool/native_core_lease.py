from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import weakref
from dataclasses import dataclass, replace

from .native_core_client import (
    ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
    ENV_NATIVE_CORE_ALLOW_STAGING_BUILD,
    NativeCoreBuildManifest,
    NativeCoreClient,
    NativeCoreDeviceProof,
    NativeCoreFeature,
    NativeCoreLicenseState,
    NativeCorePolicyError,
    NativeCoreProtocolError,
    NativeCoreRuntimeStatus,
    NativeCoreUnavailableError,
    _is_development_native_core_build_manifest,
    _is_production_native_core_build_manifest,
    _is_staging_native_core_build_manifest,
)
from .native_core_device_credential import (
    DeviceCredentialStore,
    StoredDeviceCredential,
)
from .native_core_telemetry import (
    clear_product_telemetry_context,
    configure_product_telemetry,
)


ENV_LICENSE_URL = "WECHAT_TOOL_NATIVE_CORE_LICENSE_URL"
ENV_LICENSE_TOKEN = "WECHAT_TOOL_NATIVE_CORE_LICENSE_TOKEN"
ENV_LICENSE_TIMEOUT_SECONDS = "WECHAT_TOOL_NATIVE_CORE_LICENSE_TIMEOUT_SECONDS"
DEFAULT_PRODUCTION_LICENSE_URL = "https://license.fqyw.love/v1/leases"
_PRODUCTION_APP_IDS = {
    "windows": "wechat-data-analysis.windows",
    "macos": "wechat-data-analysis.macos",
}
_LICENSE_PROTOCOL_VERSION = 2
_MAX_RESPONSE_BYTES = 64 * 1024
_EXPECTED_LEASE_BYTES = 224
_HEARTBEAT_INTERVAL_SECONDS = 60 * 60
_OFFLINE_RETRY_INITIAL_SECONDS = 30
_OFFLINE_RETRY_MAX_SECONDS = 15 * 60
_refresh_lock = threading.Lock()
_heartbeat_lock = threading.RLock()
_heartbeat_wakeup = threading.Event()
_heartbeat_thread: threading.Thread | None = None
_heartbeat_client_ref: weakref.ReferenceType[NativeCoreClient] | None = None
_heartbeat_feature = NativeCoreFeature.DATABASE_READ
_heartbeat_due_monotonic = float("inf")
_network_identity: tuple[str, bytes, bytes, NativeCoreClient] | None = None
_network_failure_count = 0
_network_retry_monotonic = 0.0


def _production_app_id(manifest: NativeCoreBuildManifest) -> str:
    app_id = _PRODUCTION_APP_IDS.get(manifest.platform)
    if app_id is None:
        raise NativeCoreProtocolError(
            "Native core build manifest contains an unsupported production platform."
        )
    return app_id


class _RejectLicenseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        del new_url
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "Native core license service redirects are not allowed.",
            headers,
            response,
        )


class _LicenseRequestRejected(NativeCorePolicyError):
    def __init__(self, message: str, *, http_status: int) -> None:
        super().__init__(message)
        self.http_status = int(http_status)


@dataclass(frozen=True)
class LeaseRefreshResult:
    status: NativeCoreRuntimeStatus
    refreshed: bool


@dataclass(frozen=True)
class NativeCoreConnectivityStatus:
    state: str
    last_attempt_unix: int | None
    last_success_unix: int | None
    next_attempt_unix: int | None
    background_refreshing: bool
    cached_lease_active: bool


_connectivity_status = NativeCoreConnectivityStatus(
    state="unknown",
    last_attempt_unix=None,
    last_success_unix=None,
    next_attempt_unix=None,
    background_refreshing=False,
    cached_lease_active=False,
)


@dataclass(frozen=True)
class _LicenseChallenge:
    challenge_id: bytes
    challenge: bytes
    expires_at: int


@dataclass(frozen=True)
class _LeaseGrant:
    lease: bytes
    device_credential: str | None
    device_id: bytes
    build_id: bytes
    service_url: str
    credential_store: DeviceCredentialStore | None


def get_native_core_connectivity_status() -> NativeCoreConnectivityStatus:
    with _heartbeat_lock:
        return _connectivity_status


def _lease_identity(
    service_url: str,
    status: NativeCoreRuntimeStatus,
    client: NativeCoreClient,
) -> tuple[str, bytes, bytes, NativeCoreClient]:
    return service_url, bytes(status.device_id), bytes(status.build_id), client


def _set_connectivity_status(**updates: object) -> None:
    global _connectivity_status
    _connectivity_status = replace(_connectivity_status, **updates)


def _record_cached_lease(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
) -> None:
    global _network_failure_count, _network_identity, _network_retry_monotonic
    with _heartbeat_lock:
        if _network_identity != identity:
            _network_identity = identity
            _network_failure_count = 0
            _network_retry_monotonic = 0.0
            state = "unknown"
            last_attempt = None
            last_success = None
        else:
            state = _connectivity_status.state
            last_attempt = _connectivity_status.last_attempt_unix
            last_success = _connectivity_status.last_success_unix
        _set_connectivity_status(
            state=state,
            last_attempt_unix=last_attempt,
            last_success_unix=last_success,
            next_attempt_unix=int(time.time()),
            background_refreshing=False,
            cached_lease_active=True,
        )


def _record_network_attempt(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
    *,
    background: bool,
) -> None:
    global _network_failure_count, _network_identity, _network_retry_monotonic
    with _heartbeat_lock:
        if _network_identity != identity:
            _network_identity = identity
            _network_failure_count = 0
            _network_retry_monotonic = 0.0
        _set_connectivity_status(
            state=_connectivity_status.state,
            last_attempt_unix=int(time.time()),
            next_attempt_unix=None,
            background_refreshing=background,
        )


def _record_network_success(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
) -> None:
    global _network_failure_count, _network_identity, _network_retry_monotonic
    now = int(time.time())
    with _heartbeat_lock:
        _network_identity = identity
        _network_failure_count = 0
        _network_retry_monotonic = 0.0
        _set_connectivity_status(
            state="online",
            last_attempt_unix=now,
            last_success_unix=now,
            next_attempt_unix=now + _HEARTBEAT_INTERVAL_SECONDS,
            background_refreshing=False,
            cached_lease_active=True,
        )


def _record_network_failure(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
    *,
    cached_lease_active: bool,
) -> int:
    global _network_failure_count, _network_identity, _network_retry_monotonic
    with _heartbeat_lock:
        if _network_identity != identity:
            _network_identity = identity
            _network_failure_count = 0
        _network_failure_count += 1
        delay = min(
            _OFFLINE_RETRY_MAX_SECONDS,
            _OFFLINE_RETRY_INITIAL_SECONDS
            * (2 ** min(_network_failure_count - 1, 10)),
        )
        _network_retry_monotonic = time.monotonic() + delay
        now = int(time.time())
        _set_connectivity_status(
            state="offline",
            last_attempt_unix=now,
            next_attempt_unix=now + delay,
            background_refreshing=False,
            cached_lease_active=cached_lease_active,
        )
        return delay


def _record_authoritative_denial(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
) -> None:
    global _network_failure_count, _network_identity, _network_retry_monotonic
    with _heartbeat_lock:
        _network_identity = identity
        _network_failure_count = 0
        _network_retry_monotonic = float("inf")
        _set_connectivity_status(
            state="denied",
            last_attempt_unix=int(time.time()),
            next_attempt_unix=None,
            background_refreshing=False,
            cached_lease_active=False,
        )
    clear_product_telemetry_context()


def _network_backoff_active(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
) -> bool:
    with _heartbeat_lock:
        return (
            _network_identity == identity
            and _connectivity_status.state == "offline"
            and time.monotonic() < _network_retry_monotonic
        )


def _is_authoritative_rejection(error: BaseException) -> bool:
    return (
        isinstance(error, _LicenseRequestRejected)
        and 400 <= error.http_status < 500
        and error.http_status not in {408, 425, 429}
    )


def _invalidate_authoritatively_denied_runtime(client: NativeCoreClient) -> None:
    del client
    try:
        from .native_core_broker import stop_native_core_broker

        stop_native_core_broker(_force=True)
    except Exception:
        # The denial state still blocks cached fallback even if process teardown
        # races with application shutdown.
        return


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: object, *, field_name: str, size: int) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise NativeCoreProtocolError(
            f"License service returned an invalid {field_name}."
        )
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise NativeCoreProtocolError(
            f"License service returned an invalid {field_name}."
        ) from exc
    padding = b"=" * (-len(encoded) % 4)
    try:
        decoded = base64.b64decode(
            encoded + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise NativeCoreProtocolError(
            f"License service returned an invalid {field_name}."
        ) from exc
    if (
        len(decoded) != size
        or not any(decoded)
        or _base64url(decoded) != value
    ):
        raise NativeCoreProtocolError(
            f"License service returned an invalid {field_name}."
        )
    return decoded


def _license_timeout() -> float:
    raw = str(os.environ.get(ENV_LICENSE_TIMEOUT_SECONDS, "10") or "").strip()
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise NativeCoreProtocolError(f"Invalid {ENV_LICENSE_TIMEOUT_SECONDS} value.") from exc
    if timeout < 1 or timeout > 120:
        raise NativeCoreProtocolError(f"{ENV_LICENSE_TIMEOUT_SECONDS} must be between 1 and 120.")
    return timeout


def _validated_license_url() -> str:
    value = str(
        os.environ.get(ENV_LICENSE_URL, DEFAULT_PRODUCTION_LICENSE_URL) or ""
    ).strip()
    if not value:
        value = DEFAULT_PRODUCTION_LICENSE_URL
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        parsed.port
    except ValueError as exc:
        raise NativeCoreProtocolError("Native core license URL is invalid.") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not hostname
        or username is not None
        or password is not None
    ):
        raise NativeCoreProtocolError("Native core license URL must use HTTPS.")
    if parsed.query or parsed.fragment:
        raise NativeCoreProtocolError(
            "Native core license URL must not contain a query or fragment."
        )
    if not parsed.path.endswith("/v1/leases"):
        raise NativeCoreProtocolError(
            "Native core license URL path must end with /v1/leases."
        )
    return value


def _challenge_url(license_url: str) -> str:
    parsed = urllib.parse.urlsplit(license_url)
    lease_suffix = "/v1/leases"
    if not parsed.path.endswith(lease_suffix):
        raise NativeCoreProtocolError(
            "Native core license URL path must end with /v1/leases."
        )
    challenge_path = parsed.path[: -len(lease_suffix)] + "/v1/challenges"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, challenge_path, "", "")
    )


def _validated_license_token() -> str | None:
    token = str(os.environ.get(ENV_LICENSE_TOKEN, "") or "").strip()
    if not token:
        return None
    if len(token) > 8192 or "\r" in token or "\n" in token:
        raise NativeCoreProtocolError(f"{ENV_LICENSE_TOKEN} is invalid.")
    return token


def _production_license_configuration() -> tuple[str, str | None]:
    url = _validated_license_url()
    token = _validated_license_token()
    _license_timeout()
    return url, token


def validate_native_core_authorization_policy(
    manifest: NativeCoreBuildManifest,
) -> str:
    if _is_production_native_core_build_manifest(manifest):
        if int(time.time()) >= manifest.build_expires_at_unix:
            raise NativeCorePolicyError(
                "This native core build has reached its fixed expiration time."
            )
        _production_license_configuration()
        return "production"
    staging_enabled = (
        not getattr(sys, "frozen", False)
        and str(os.environ.get(ENV_NATIVE_CORE_ALLOW_STAGING_BUILD, "") or "").strip()
        == "1"
    )
    if staging_enabled and _is_staging_native_core_build_manifest(manifest):
        _production_license_configuration()
        return "production"
    if _is_development_native_core_build_manifest(manifest):
        enabled = str(
            os.environ.get(ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD, "") or ""
        ).strip()
        if enabled != "1":
            raise NativeCoreProtocolError(
                "Development native core requires the explicit "
                f"{ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD}=1 local lease opt-in."
            )
        if str(os.environ.get(ENV_LICENSE_URL, "") or "").strip() or str(
            os.environ.get(ENV_LICENSE_TOKEN, "") or ""
        ).strip():
            raise NativeCoreProtocolError(
                "Development native core only accepts the explicit local development lease."
            )
        return "development"
    raise NativeCoreProtocolError(
        "Native core authorization rejected an unknown build manifest profile."
    )


def _decode_lease(value: object) -> bytes:
    if not isinstance(value, str) or not value or value != value.strip():
        raise NativeCoreProtocolError("License service response did not contain a lease.")
    try:
        payload = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise NativeCoreProtocolError("License service returned invalid base64 lease data.") from exc
    if len(payload) != _EXPECTED_LEASE_BYTES:
        raise NativeCoreProtocolError(
            f"License service returned an invalid lease size: {len(payload)}."
        )
    return payload


def _parse_json_object(raw: bytes, *, operation: str) -> dict[str, object]:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant: {value}")

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise NativeCoreProtocolError(
            f"Native core license service returned invalid JSON for {operation}."
        ) from exc
    if not isinstance(payload, dict):
        raise NativeCoreProtocolError(
            f"Native core license service returned an invalid {operation} payload."
        )
    return payload


def _post_json(
    opener: urllib.request.OpenerDirector,
    *,
    url: str,
    token: str | None,
    body: dict[str, object],
    operation: str,
) -> dict[str, object]:
    encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "WeChatDataAnalysis-NativeCore/2",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=encoded_body,
        method="POST",
        headers=headers,
    )
    try:
        with opener.open(request, timeout=_license_timeout()) as response:
            content_type = str(response.headers.get("Content-Type", "") or "")
            if content_type.split(";", 1)[0].strip().lower() != "application/json":
                raise NativeCoreProtocolError(
                    f"Native core license service returned a non-JSON {operation} response."
                )
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise _LicenseRequestRejected(
            "Native core license service rejected "
            f"the {operation} request with HTTP {exc.code}.",
            http_status=exc.code,
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NativeCoreUnavailableError("Native core license service is unavailable.") from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise NativeCoreProtocolError(
            f"Native core license {operation} response is too large."
        )
    return _parse_json_object(raw, operation=operation)


def _parse_challenge(payload: dict[str, object]) -> _LicenseChallenge:
    challenge_id = _decode_base64url(
        payload.get("challengeId"),
        field_name="challengeId",
        size=16,
    )
    challenge = _decode_base64url(
        payload.get("challenge"),
        field_name="challenge",
        size=32,
    )
    expires_at = payload.get("expiresAt")
    if type(expires_at) is not int or expires_at <= 0:
        raise NativeCoreProtocolError(
            "License service returned an invalid expiresAt."
        )
    return _LicenseChallenge(
        challenge_id=challenge_id,
        challenge=challenge,
        expires_at=expires_at,
    )


def _parse_device_credential(value: object, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or value != value.strip():
        raise NativeCoreProtocolError(
            "License service returned an invalid deviceCredential."
        )
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise NativeCoreProtocolError(
            "License service returned an invalid deviceCredential."
        ) from exc
    if (
        len(encoded) < 32
        or len(encoded) > 4096
        or any(byte < 0x21 or byte > 0x7E for byte in encoded)
    ):
        raise NativeCoreProtocolError(
            "License service returned an invalid deviceCredential."
        )
    return value


def _validate_unchanged_device_status(
    before: NativeCoreRuntimeStatus,
    after: NativeCoreRuntimeStatus,
) -> None:
    if (
        before.device_assurance != after.device_assurance
        or before.build_id != after.build_id
        or before.device_id != after.device_id
        or before.startup_nonce != after.startup_nonce
    ):
        raise NativeCorePolicyError(
            "Native core broker identity changed during license challenge."
        )


def _validated_device_proof(
    proof: NativeCoreDeviceProof,
    *,
    status: NativeCoreRuntimeStatus,
    feature: NativeCoreFeature,
) -> tuple[bytes, bytes]:
    try:
        build_id = bytes(proof.build_id)
        device_id = bytes(proof.device_id)
        startup_nonce = bytes(proof.startup_nonce)
        public_key = bytes(proof.device_public_key)
        signature = bytes(proof.signature)
    except (AttributeError, TypeError, ValueError) as exc:
        raise NativeCoreProtocolError(
            "Native core client returned an invalid device proof."
        ) from exc
    if (
        len(build_id) != 32
        or len(device_id) != 32
        or len(startup_nonce) != 32
        or len(public_key) != 64
        or len(signature) != 64
        or not any(public_key)
        or not any(signature)
    ):
        raise NativeCoreProtocolError(
            "Native core client returned an invalid device proof."
        )
    if (
        proof.device_assurance != status.device_assurance
        or int(proof.requested_features) != int(feature)
        or build_id != status.build_id
        or device_id != status.device_id
        or startup_nonce != status.startup_nonce
    ):
        raise NativeCorePolicyError(
            "Native core device proof does not match the challenged broker state."
        )
    return public_key, signature


def _request_lease(
    client: NativeCoreClient,
    status: NativeCoreRuntimeStatus,
    feature: NativeCoreFeature,
    *,
    credential_store: DeviceCredentialStore | None = None,
    stored_credential: StoredDeviceCredential | None = None,
) -> _LeaseGrant:
    license_url, injected_token = _production_license_configuration()
    token = injected_token
    if token is None:
        if credential_store is None:
            credential_store = DeviceCredentialStore()
        if stored_credential is None:
            try:
                loaded = credential_store.load(
                    device_id=status.device_id,
                    build_id=status.build_id,
                    service_url=license_url,
                )
            except NativeCoreProtocolError:
                # A copied, corrupt, or DPAPI-incompatible credential cannot be
                # trusted. The device proof still gates a fresh registration.
                credential_store.delete()
                loaded = None
            if isinstance(loaded, str):
                # Compatibility for focused mocks written against schema 1.
                stored_credential = StoredDeviceCredential(loaded, None, 1)
            else:
                stored_credential = loaded
        token = (
            None if stored_credential is None else stored_credential.credential
        )
    opener = urllib.request.build_opener(
        _RejectLicenseRedirects(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )

    def request_with_token(auth_token: str | None) -> dict[str, object]:
        challenge_body: dict[str, object] = {
            "protocolVersion": _LICENSE_PROTOCOL_VERSION,
            "deviceAssurance": int(status.device_assurance),
            "requestedFeatures": int(feature),
            "buildId": _base64url(status.build_id),
            "deviceId": _base64url(status.device_id),
            "startupNonce": _base64url(status.startup_nonce),
        }
        if auth_token is None:
            manifest = client.build_manifest
            signer_digest = bytes(manifest.client_signer_sha256)
            if len(signer_digest) != 32 or not any(signer_digest):
                raise NativeCoreProtocolError(
                    "Native core build manifest does not contain a valid client signer."
                )
            distribution_mode = manifest.distribution_mode
            distribution_capsule = manifest.distribution_capsule
            if distribution_mode == "controlled":
                if distribution_capsule is None:
                    raise NativeCoreProtocolError(
                        "Controlled native core build is missing its distribution capsule."
                    )
                challenge_body["distributionCapsule"] = distribution_capsule
            elif distribution_mode != "public" or distribution_capsule is not None:
                raise NativeCoreProtocolError(
                    "Native core build manifest contains an invalid distribution policy."
                )
            challenge_body.update(
                {
                    "appId": _production_app_id(manifest),
                    "hostSignerId": _base64url(signer_digest),
                }
            )
        challenge_payload = _post_json(
            opener,
            url=_challenge_url(license_url),
            token=auth_token,
            operation="challenge",
            body=challenge_body,
        )
        challenge = _parse_challenge(challenge_payload)
        current_status = client.get_status()
        _validate_unchanged_device_status(status, current_status)
        proof = client.create_device_proof(
            feature,
            challenge.challenge_id,
            challenge.challenge,
        )
        public_key, signature = _validated_device_proof(
            proof,
            status=current_status,
            feature=feature,
        )
        lease_body: dict[str, object] = {
            "challengeId": _base64url(challenge.challenge_id),
            "devicePublicKey": _base64url(public_key),
            "deviceSignature": _base64url(signature),
        }
        if auth_token is None:
            lease_body["registration"] = True
        return _post_json(
            opener,
            url=license_url,
            token=auth_token,
            operation="lease",
            body=lease_body,
        )

    try:
        lease_payload = request_with_token(token)
    except _LicenseRequestRejected as exc:
        if (
            injected_token is None
            and token is not None
            and credential_store is not None
            and exc.http_status in {401, 403}
        ):
            credential_store.delete()
        raise
    issued_credential = _parse_device_credential(
        lease_payload.get("deviceCredential"),
        required=token is None,
    )
    device_credential = issued_credential
    if (
        device_credential is None
        and injected_token is None
        and stored_credential is not None
    ):
        device_credential = stored_credential.credential
    return _LeaseGrant(
        lease=_decode_lease(lease_payload.get("leaseBase64")),
        device_credential=device_credential,
        device_id=bytes(status.device_id),
        build_id=bytes(status.build_id),
        service_url=license_url,
        credential_store=credential_store,
    )


def _schedule_heartbeat(
    client: NativeCoreClient,
    feature: NativeCoreFeature,
    *,
    delay_seconds: float,
) -> None:
    global _heartbeat_client_ref, _heartbeat_due_monotonic
    global _heartbeat_feature, _heartbeat_thread
    try:
        client_ref = weakref.ref(client)
    except TypeError:
        return
    due = time.monotonic() + max(0.0, float(delay_seconds))
    with _heartbeat_lock:
        current_client = (
            None if _heartbeat_client_ref is None else _heartbeat_client_ref()
        )
        if current_client is client and _heartbeat_thread is not None:
            _heartbeat_due_monotonic = min(_heartbeat_due_monotonic, due)
        else:
            _heartbeat_client_ref = client_ref
            _heartbeat_feature = NativeCoreFeature(feature)
            _heartbeat_due_monotonic = due
        if _heartbeat_thread is None or not _heartbeat_thread.is_alive():
            _heartbeat_thread = threading.Thread(
                target=_heartbeat_worker_main,
                name="wechatdb-license-heartbeat",
                daemon=True,
            )
            _heartbeat_thread.start()
        _heartbeat_wakeup.set()


def _clear_heartbeat_target(client: NativeCoreClient) -> None:
    global _heartbeat_client_ref, _heartbeat_due_monotonic
    with _heartbeat_lock:
        current = None if _heartbeat_client_ref is None else _heartbeat_client_ref()
        if current is client:
            _heartbeat_client_ref = None
            _heartbeat_due_monotonic = float("inf")
            _heartbeat_wakeup.set()


def _heartbeat_worker_main() -> None:
    global _heartbeat_client_ref, _heartbeat_thread, _heartbeat_due_monotonic
    while True:
        with _heartbeat_lock:
            client_ref = _heartbeat_client_ref
            feature = _heartbeat_feature
            due = _heartbeat_due_monotonic
        client = None if client_ref is None else client_ref()
        if client is None:
            with _heartbeat_lock:
                _heartbeat_thread = None
            return
        delay = max(0.0, due - time.monotonic())
        if _heartbeat_wakeup.wait(delay):
            _heartbeat_wakeup.clear()
            continue
        try:
            _refresh_native_core_lease_internal(
                client,
                feature,
                minimum_validity_seconds=0,
                force_online=True,
                background=True,
            )
        except Exception:
            with _heartbeat_lock:
                current = (
                    None
                    if _heartbeat_client_ref is None
                    else _heartbeat_client_ref()
                )
                if current is not client:
                    continue
                if _connectivity_status.state == "denied":
                    _heartbeat_client_ref = None
                    _heartbeat_thread = None
                    _heartbeat_due_monotonic = float("inf")
                    return
                if _connectivity_status.state != "offline":
                    _heartbeat_client_ref = None
                    _heartbeat_thread = None
                    _heartbeat_due_monotonic = float("inf")
                    return
                _heartbeat_due_monotonic = _network_retry_monotonic
        else:
            with _heartbeat_lock:
                current = (
                    None
                    if _heartbeat_client_ref is None
                    else _heartbeat_client_ref()
                )
                if current is client:
                    _heartbeat_due_monotonic = (
                        time.monotonic() + _HEARTBEAT_INTERVAL_SECONDS
                    )


def _reset_native_core_lease_state_for_tests() -> None:
    global _connectivity_status, _heartbeat_client_ref, _heartbeat_due_monotonic
    global _heartbeat_thread, _network_failure_count, _network_identity
    global _network_retry_monotonic
    with _heartbeat_lock:
        thread = _heartbeat_thread
        _heartbeat_client_ref = None
        _heartbeat_due_monotonic = float("inf")
        _heartbeat_thread = None
        _network_identity = None
        _network_failure_count = 0
        _network_retry_monotonic = 0.0
        _connectivity_status = NativeCoreConnectivityStatus(
            state="unknown",
            last_attempt_unix=None,
            last_success_unix=None,
            next_attempt_unix=None,
            background_refreshing=False,
            cached_lease_active=False,
        )
        _heartbeat_wakeup.set()
    if (
        thread is not None
        and thread is not threading.current_thread()
        and thread.is_alive()
    ):
        thread.join(timeout=1.0)
    clear_product_telemetry_context()


def _status_grants_feature(
    status: NativeCoreRuntimeStatus,
    feature: NativeCoreFeature,
    *,
    manifest: NativeCoreBuildManifest,
    now: int,
    minimum_validity_seconds: int,
) -> bool:
    valid_after = now + max(0, int(minimum_validity_seconds))
    if not bool(int(status.feature_bits) & int(feature)):
        return False
    if status.lease_expires_unix > valid_after:
        return True
    return (
        status.license_state
        in {NativeCoreLicenseState.ACTIVE, NativeCoreLicenseState.BUILD_ACTIVE}
        and bool(int(manifest.offline_bootstrap_feature_bits) & int(feature))
        and manifest.build_expires_at_unix > valid_after
    )


def _load_stored_credential(
    store: DeviceCredentialStore,
    *,
    status: NativeCoreRuntimeStatus,
    service_url: str,
) -> StoredDeviceCredential | None:
    try:
        loaded = store.load(
            device_id=status.device_id,
            build_id=status.build_id,
            service_url=service_url,
        )
    except NativeCoreProtocolError:
        store.delete()
        return None
    if isinstance(loaded, str):
        return StoredDeviceCredential(loaded, None, 1)
    return loaded


def _authoritative_denial_active(
    identity: tuple[str, bytes, bytes, NativeCoreClient],
) -> bool:
    with _heartbeat_lock:
        return (
            _network_identity == identity
            and _connectivity_status.state == "denied"
        )


def _refresh_native_core_lease_internal(
    client: NativeCoreClient,
    feature: NativeCoreFeature,
    *,
    minimum_validity_seconds: int,
    force_online: bool,
    background: bool,
    initial_status: NativeCoreRuntimeStatus | None = None,
) -> LeaseRefreshResult:
    with _refresh_lock:
        manifest = getattr(client, "build_manifest", None)
        if not isinstance(manifest, NativeCoreBuildManifest):
            raise NativeCoreProtocolError(
                "Native core client did not expose its verified build manifest."
            )
        authorization_profile = validate_native_core_authorization_policy(manifest)
        status = initial_status if initial_status is not None else client.get_status()
        now = int(time.time())
        if (
            not force_online
            and _status_grants_feature(
                status,
                feature,
                manifest=manifest,
                now=now,
                minimum_validity_seconds=minimum_validity_seconds,
            )
        ):
            if authorization_profile == "production":
                _schedule_heartbeat(
                    client,
                    feature,
                    delay_seconds=_HEARTBEAT_INTERVAL_SECONDS,
                )
            return LeaseRefreshResult(status=status, refreshed=False)
        if authorization_profile == "development":
            from .native_core_dev_lease import issue_development_lease

            lease = issue_development_lease(status, feature)
            grant = None
        else:
            license_url, injected_token = _production_license_configuration()
            identity = _lease_identity(license_url, status, client)
            credential_store = DeviceCredentialStore()
            stored_credential = _load_stored_credential(
                credential_store,
                status=status,
                service_url=license_url,
            )
            if (
                not force_online
                and stored_credential is not None
                and stored_credential.lease is not None
            ):
                try:
                    client.install_lease(stored_credential.lease)
                    cached_status = client.get_status()
                except (NativeCorePolicyError, NativeCoreProtocolError):
                    credential_store.delete()
                    stored_credential = None
                else:
                    if _status_grants_feature(
                        cached_status,
                        feature,
                        manifest=manifest,
                        now=now,
                        minimum_validity_seconds=minimum_validity_seconds,
                    ):
                        if (
                            manifest.build_expires_at_unix > 0
                            and cached_status.lease_expires_unix
                            > manifest.build_expires_at_unix
                        ):
                            credential_store.delete()
                            raise NativeCorePolicyError(
                                "Cached native core lease exceeds the fixed build expiration."
                            )
                        configure_product_telemetry(
                            license_url=license_url,
                            credential=stored_credential.credential,
                            device_id=bytes(cached_status.device_id),
                            build_id=bytes(cached_status.build_id),
                        )
                        _record_cached_lease(identity)
                        _schedule_heartbeat(client, feature, delay_seconds=0)
                        return LeaseRefreshResult(
                            status=cached_status,
                            refreshed=True,
                        )
                    credential_store.delete()
                    stored_credential = None
            if _authoritative_denial_active(identity):
                raise NativeCorePolicyError(
                    "Native core license service authoritatively denied this device."
                )
            if _network_backoff_active(identity):
                raise NativeCoreUnavailableError(
                    "Native core license service retry is delayed after a network failure."
                )
            _record_network_attempt(identity, background=background)
            cached_lease_active = _status_grants_feature(
                status,
                feature,
                manifest=manifest,
                now=now,
                minimum_validity_seconds=0,
            )
            try:
                requested = _request_lease(
                    client,
                    status,
                    feature,
                    credential_store=credential_store,
                    stored_credential=stored_credential,
                )
            except Exception as exc:
                if _is_authoritative_rejection(exc):
                    try:
                        credential_store.delete()
                    finally:
                        _record_authoritative_denial(identity)
                        _invalidate_authoritatively_denied_runtime(client)
                else:
                    _record_network_failure(
                        identity,
                        cached_lease_active=cached_lease_active,
                    )
                raise
            if isinstance(requested, bytes):
                # Compatibility for focused tests and downstream staging
                # adapters written against the pre-registration helper.
                lease = requested
                grant = None
            else:
                lease = requested.lease
                grant = requested
        try:
            client.install_lease(lease)
        except Exception:
            if authorization_profile == "production":
                _record_network_failure(
                    identity,
                    cached_lease_active=_status_grants_feature(
                        status,
                        feature,
                        manifest=manifest,
                        now=now,
                        minimum_validity_seconds=0,
                    ),
                )
            raise
        refreshed_status = client.get_status()
        if not (int(refreshed_status.feature_bits) & int(feature)):
            raise NativeCorePolicyError("Installed native core lease does not grant the requested feature.")
        if (
            manifest.build_expires_at_unix > 0
            and refreshed_status.lease_expires_unix > manifest.build_expires_at_unix
        ):
            raise NativeCorePolicyError(
                "Installed native core lease exceeds the fixed build expiration."
            )
        if (
            grant is not None
            and grant.device_credential is not None
            and grant.credential_store is not None
        ):
            grant.credential_store.save(
                grant.device_credential,
                lease,
                device_id=grant.device_id,
                build_id=grant.build_id,
                service_url=grant.service_url,
            )
        if grant is not None and grant.device_credential is not None:
            configure_product_telemetry(
                license_url=grant.service_url,
                credential=grant.device_credential,
                device_id=grant.device_id,
                build_id=grant.build_id,
            )
        if authorization_profile == "production":
            _record_network_success(identity)
            if not background:
                _schedule_heartbeat(
                    client,
                    feature,
                    delay_seconds=_HEARTBEAT_INTERVAL_SECONDS,
                )
        return LeaseRefreshResult(status=refreshed_status, refreshed=True)


def refresh_native_core_lease(
    client: NativeCoreClient,
    feature: NativeCoreFeature,
    *,
    minimum_validity_seconds: int = 60,
) -> LeaseRefreshResult:
    manifest = getattr(client, "build_manifest", None)
    if not isinstance(manifest, NativeCoreBuildManifest):
        raise NativeCoreProtocolError(
            "Native core client did not expose its verified build manifest."
        )
    authorization_profile = validate_native_core_authorization_policy(manifest)
    status = client.get_status()
    now = int(time.time())
    if _status_grants_feature(
        status,
        feature,
        manifest=manifest,
        now=now,
        minimum_validity_seconds=minimum_validity_seconds,
    ):
        if authorization_profile == "production":
            _schedule_heartbeat(
                client,
                feature,
                delay_seconds=_HEARTBEAT_INTERVAL_SECONDS,
            )
        return LeaseRefreshResult(status=status, refreshed=False)
    return _refresh_native_core_lease_internal(
        client,
        feature,
        minimum_validity_seconds=minimum_validity_seconds,
        force_online=False,
        background=False,
        initial_status=status,
    )


__all__ = [
    "ENV_LICENSE_TIMEOUT_SECONDS",
    "ENV_LICENSE_TOKEN",
    "ENV_LICENSE_URL",
    "DEFAULT_PRODUCTION_LICENSE_URL",
    "LeaseRefreshResult",
    "NativeCoreConnectivityStatus",
    "get_native_core_connectivity_status",
    "refresh_native_core_lease",
    "validate_native_core_authorization_policy",
]
