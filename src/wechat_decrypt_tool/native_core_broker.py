from __future__ import annotations

import atexit
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .native_core_client import (
    ENV_NATIVE_CORE_ENDPOINT,
    ENV_NATIVE_CORE_LIBRARY,
    NativeCoreBuildManifest,
    NativeCoreClient,
    NativeCoreComponentMissingError,
    NativeCoreProtocolError,
    NativeCoreStatus,
    NativeCoreUnavailableError,
    _required_native_core_build_manifest,
    close_native_core_client,
)


ENV_NATIVE_CORE_BROKER = "WECHAT_TOOL_NATIVE_CORE_BROKER"
ENV_NATIVE_CORE_TRUST_KEY = "WECHAT_TOOL_NATIVE_CORE_TRUST_KEY_PATH"
ENV_NATIVE_CORE_DEVICE_KEY_NAME = "WECHAT_TOOL_NATIVE_CORE_DEVICE_KEY_NAME"
ENV_NATIVE_CORE_STARTUP_TIMEOUT_MS = "WECHAT_TOOL_NATIVE_CORE_STARTUP_TIMEOUT_MS"

_DEFAULT_DEVICE_KEY_NAME = "LifeArchiveProject.WeChatDB.Native.Device.v1"

_lock = threading.RLock()
_process: subprocess.Popen[bytes] | None = None
_owned_endpoint = ""
_owned_database_roots: tuple[Path, ...] = ()
_owned_database_disabled = False
_owned_environment: dict[str, tuple[str | None, str]] = {}
_active_operations = 0


def _resolve_broker_trust_key(
    build_manifest: NativeCoreBuildManifest,
    broker_path: Path,
) -> str:
    trust_key = str(os.environ.get(ENV_NATIVE_CORE_TRUST_KEY, "") or "").strip()
    if not build_manifest.development_build:
        if trust_key:
            raise NativeCoreProtocolError(
                "Production native core rejects external development trust keys."
            )
        return ""
    if trust_key:
        return trust_key

    from .native_core_dev_lease import prepare_development_trust

    return str(prepare_development_trust(broker_path))


def _broker_child_environment() -> dict[str, str]:
    child_env = os.environ.copy()
    for name in tuple(child_env):
        if name.startswith("WECHAT_TOOL_NATIVE_CORE_LICENSE_") or name == (
            "WECHAT_TOOL_NATIVE_CORE_ALLOW_INSECURE_LICENSE_URL"
        ):
            child_env.pop(name, None)
    return child_env


def _busy_error(action: str) -> NativeCoreUnavailableError:
    return NativeCoreUnavailableError(
        f"wechatdb native broker is BUSY with {_active_operations} active operation(s); "
        f"cannot {action}.",
        status=int(NativeCoreStatus.BUSY),
    )


class NativeCoreManagedOperation:
    """A process-wide lease preventing broker replacement while native handles are live."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._closed = False

    @property
    def closed(self) -> bool:
        with _lock:
            return self._closed

    def close(self) -> None:
        global _active_operations
        with _lock:
            if self._closed:
                return
            self._closed = True
            if _active_operations <= 0:
                raise RuntimeError("native core managed operation count underflow")
            _active_operations -= 1
            if (
                _active_operations == 0
                and _process is not None
                and _owned_database_disabled
            ):
                # Export-only generations have no account state to preserve. Closing
                # them promptly also releases their log and endpoint resources.
                stop_native_core_broker()

    def __enter__(self) -> NativeCoreManagedOperation:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


def _broker_name() -> str:
    if sys.platform.startswith("win"):
        return "wechatdb_broker.exe"
    if sys.platform == "darwin":
        return "wechatdb_broker"
    raise NativeCoreComponentMissingError("wechatdb native broker supports Windows and macOS only.")


def _client_name() -> str:
    return "wechatdb_client.dll" if sys.platform.startswith("win") else "libwechatdb_client.dylib"


def _candidate_broker_paths() -> tuple[Path, ...]:
    package_dir = Path(__file__).resolve().parent
    repo_root = package_dir.parents[1]
    name = _broker_name()
    candidates: list[Path] = []
    explicit = str(os.environ.get(ENV_NATIVE_CORE_BROKER, "") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "native" / name)
    candidates.extend(
        (
            package_dir / "native" / name,
            repo_root.parent / "wechatdb-native" / "build" / "windows-vs" / "Release" / name,
            repo_root.parent / "wechatdb-native" / "build" / "windows-vs" / "Debug" / name,
            repo_root.parent / "wechatdb-native" / "build" / "windows-msvc-debug" / name,
            repo_root.parent / "wechatdb-native" / "build" / "macos-arm64-debug" / name,
        )
    )
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(str(candidate.resolve(strict=False)))
        if normalized not in seen:
            seen.add(normalized)
            result.append(candidate)
    return tuple(result)


def resolve_native_core_broker() -> Path:
    for candidate in _candidate_broker_paths():
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    raise NativeCoreComponentMissingError("wechatdb native broker executable was not found.")


def _new_endpoint() -> str:
    token = secrets.token_hex(12)
    if sys.platform.startswith("win"):
        return rf"\\.\pipe\LifeArchiveProject.WeChatDB.Native.{os.getpid()}.{token}"
    directory = tempfile.gettempdir().rstrip("/\\")
    return f"{directory}/lap-wce-{os.getpid()}-{token}.sock"


def _startup_timeout_seconds() -> float:
    raw = str(os.environ.get(ENV_NATIVE_CORE_STARTUP_TIMEOUT_MS, "5000") or "").strip()
    try:
        milliseconds = int(raw)
    except ValueError as exc:
        raise NativeCoreProtocolError(f"Invalid {ENV_NATIVE_CORE_STARTUP_TIMEOUT_MS} value.") from exc
    if milliseconds < 100 or milliseconds > 120_000:
        raise NativeCoreProtocolError(
            f"{ENV_NATIVE_CORE_STARTUP_TIMEOUT_MS} must be between 100 and 120000."
        )
    return milliseconds / 1000.0


def _canonical_database_root(value: Path | str) -> Path:
    if isinstance(value, str) and not value.strip():
        raise NativeCoreProtocolError("Native core database root must not be empty.")
    try:
        root = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise NativeCoreProtocolError(
            f"Native core database root does not exist: {value}"
        ) from exc
    if not root.is_dir():
        raise NativeCoreProtocolError(
            f"Native core database root is not a directory: {root}"
        )
    return root


def _same_database_root(first: Path, second: Path) -> bool:
    if os.path.normcase(os.fspath(first)) == os.path.normcase(os.fspath(second)):
        return True
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _discover_database_roots() -> tuple[Path, ...]:
    # Imports stay lazy because native_core_database imports this module while
    # the account and media helpers are still being initialized.
    from .chat_accounts import list_chat_account_contexts
    from .media_helpers import _resolve_account_db_storage_dir

    roots: list[Path] = []
    for context in list_chat_account_contexts():
        resolved = _resolve_account_db_storage_dir(context.account_dir)
        if resolved is None:
            continue
        try:
            root = _canonical_database_root(resolved)
        except NativeCoreProtocolError:
            continue
        if not any(_same_database_root(root, existing) for existing in roots):
            roots.append(root)
    return tuple(roots)


def _install_owned_environment(endpoint: str, client_path: Path) -> None:
    global _owned_environment
    assignments = {
        ENV_NATIVE_CORE_ENDPOINT: endpoint,
        ENV_NATIVE_CORE_LIBRARY: str(client_path),
    }
    _owned_environment = {
        name: (os.environ.get(name), value) for name, value in assignments.items()
    }
    os.environ.update(assignments)


def _clear_owned_environment() -> None:
    global _owned_environment
    owned_environment = _owned_environment
    _owned_environment = {}
    for name, (previous, assigned) in owned_environment.items():
        if os.environ.get(name) != assigned:
            continue
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _database_roots_for_launch(
    requested_root: Path | None,
    *,
    include_owned: bool,
) -> tuple[Path, ...]:
    candidates: list[Path | str] = list(_discover_database_roots())
    if include_owned:
        candidates.extend(_owned_database_roots)
    if requested_root is not None:
        candidates.append(requested_root)

    roots: list[Path] = []
    for candidate in candidates:
        root = _canonical_database_root(candidate)
        if not any(_same_database_root(root, existing) for existing in roots):
            roots.append(root)
    if not roots:
        raise NativeCoreProtocolError(
            "wechatdb native broker requires at least one resolved db_storage root."
        )
    return tuple(roots)


def _broker_log_file():
    data_dir = str(os.environ.get("WECHAT_TOOL_DATA_DIR", "") or "").strip()
    if not data_dir:
        return subprocess.DEVNULL
    log_path = Path(data_dir) / "logs" / "native-core-broker.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return open(log_path, "ab", buffering=0)
    except OSError:
        return subprocess.DEVNULL


def _wait_until_ready(
    process: subprocess.Popen[bytes],
    *,
    client_path: Path,
    endpoint: str,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise NativeCoreUnavailableError(
                f"wechatdb native broker exited during startup with code {exit_code}."
            )
        client: NativeCoreClient | None = None
        try:
            remaining_ms = max(100, int((deadline - time.monotonic()) * 1000))
            client = NativeCoreClient(
                library_path=client_path,
                endpoint=endpoint,
                connect_timeout_ms=min(1000, remaining_ms),
            )
            status = client.get_status()
            if int(status.broker_process_id) != int(process.pid):
                raise NativeCoreProtocolError("wechatdb native broker process identity mismatch.")
            return
        except NativeCoreUnavailableError as exc:
            last_error = exc
            time.sleep(0.05)
        finally:
            if client is not None:
                client.close()
    raise NativeCoreUnavailableError("wechatdb native broker did not become ready in time.") from last_error


def ensure_native_core_broker(
    *,
    database_root: Path | None = None,
    export_only: bool = False,
) -> str:
    global _process, _owned_endpoint, _owned_database_roots, _owned_database_disabled
    with _lock:
        if export_only and database_root is not None:
            raise NativeCoreProtocolError(
                "export_only and database_root are mutually exclusive."
            )
        launch_roots: tuple[Path, ...] | None = None
        launch_database_disabled = bool(export_only)
        if _process is not None:
            if _process.poll() is None:
                if export_only:
                    if _owned_database_disabled:
                        return _owned_endpoint
                    if _active_operations:
                        raise _busy_error("switch to export-only mode")
                    launch_roots = ()
                    stop_native_core_broker()
                elif database_root is None:
                    if not _owned_database_disabled:
                        return _owned_endpoint
                    if _active_operations:
                        raise _busy_error("switch to database mode")
                    launch_roots = _database_roots_for_launch(
                        None, include_owned=False
                    )
                    launch_database_disabled = False
                    # The default broker contract is database-capable. An idle
                    # export-only generation must not leak into a later database
                    # authorization preflight.
                    stop_native_core_broker()
                else:
                    requested = _canonical_database_root(database_root)
                    if not _owned_database_disabled and any(
                        _same_database_root(requested, root)
                        for root in _owned_database_roots
                    ):
                        return _owned_endpoint
                    if _active_operations:
                        action = (
                            "switch to database mode"
                            if _owned_database_disabled
                            else "expand its immutable database root policy"
                        )
                        raise _busy_error(action)
                    launch_roots = _database_roots_for_launch(
                        requested, include_owned=True
                    )
                    launch_database_disabled = False
                    # Mode and root policy are immutable. Restarting changes
                    # the startup nonce, so the next operation needs a lease
                    # bound to the new broker generation.
                    stop_native_core_broker()
            else:
                _process = None
                _owned_endpoint = ""
                _owned_database_roots = ()
                _owned_database_disabled = False
                _clear_owned_environment()
                close_native_core_client()

        if launch_roots is None:
            configured_endpoint = str(
                os.environ.get(ENV_NATIVE_CORE_ENDPOINT, "") or ""
            ).strip()
            if configured_endpoint:
                if database_root is not None:
                    raise NativeCoreProtocolError(
                        "An external native core endpoint cannot verify or expand "
                        "a requested database_root policy."
                    )
                return configured_endpoint

        broker_path = resolve_native_core_broker()
        client_path = broker_path.with_name(_client_name())
        if not client_path.is_file():
            raise NativeCoreComponentMissingError(
                f"wechatdb native client is missing next to broker: {client_path}"
            )
        build_manifest = _required_native_core_build_manifest(client_path)

        if launch_roots is None and not launch_database_disabled:
            launch_roots = _database_roots_for_launch(
                database_root, include_owned=False
            )
        elif launch_roots is None:
            launch_roots = ()

        endpoint = _new_endpoint()
        command = [
            str(broker_path),
            "--endpoint",
            endpoint,
            "--parent-pid",
            str(os.getpid()),
        ]
        trust_key = _resolve_broker_trust_key(build_manifest, broker_path)
        if trust_key:
            trust_path = Path(trust_key).expanduser().resolve(strict=False)
            if not trust_path.is_file():
                raise NativeCoreProtocolError(
                    f"Configured native core trust key file does not exist: {trust_path}"
                )
            command.extend(("--trust-key", str(trust_path)))
        device_key_name = str(
            os.environ.get(ENV_NATIVE_CORE_DEVICE_KEY_NAME, _DEFAULT_DEVICE_KEY_NAME) or ""
        ).strip()
        if not device_key_name:
            raise NativeCoreProtocolError("Native core device key name must not be empty.")
        command.extend(("--device-key-name", device_key_name))
        if launch_database_disabled:
            command.append("--disable-database")
        else:
            for root in launch_roots:
                command.extend(("--database-root", os.fspath(root)))

        child_env = _broker_child_environment()
        log_file = _broker_log_file()
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=child_env,
                close_fds=True,
                creationflags=creation_flags,
                start_new_session=not sys.platform.startswith("win"),
            )
        except OSError as exc:
            raise NativeCoreUnavailableError("Cannot start wechatdb native broker.") from exc
        finally:
            if log_file is not subprocess.DEVNULL:
                log_file.close()

        try:
            _wait_until_ready(
                process,
                client_path=client_path,
                endpoint=endpoint,
                timeout=_startup_timeout_seconds(),
            )
        except Exception:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if sys.platform == "darwin":
                Path(endpoint).unlink(missing_ok=True)
            raise

        close_native_core_client()
        _install_owned_environment(endpoint, client_path)
        _process = process
        _owned_endpoint = endpoint
        _owned_database_roots = launch_roots
        _owned_database_disabled = launch_database_disabled
        return endpoint


def managed_native_core_operation(
    *,
    database_root: Path | None = None,
    export_only: bool = False,
) -> NativeCoreManagedOperation:
    global _active_operations
    with _lock:
        endpoint = ensure_native_core_broker(
            database_root=database_root,
            export_only=export_only,
        )
        _active_operations += 1
        return NativeCoreManagedOperation(endpoint)


def stop_native_core_broker(*, _force: bool = False) -> None:
    global _process, _owned_endpoint, _owned_database_roots, _owned_database_disabled
    with _lock:
        if _active_operations and not _force:
            raise _busy_error("stop while managed operations are active")
        process = _process
        endpoint = _owned_endpoint
        _process = None
        _owned_endpoint = ""
        _owned_database_roots = ()
        _owned_database_disabled = False
        _clear_owned_environment()
        close_native_core_client()
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if endpoint and sys.platform == "darwin":
        Path(endpoint).unlink(missing_ok=True)


atexit.register(stop_native_core_broker, _force=True)


__all__ = [
    "ENV_NATIVE_CORE_BROKER",
    "ENV_NATIVE_CORE_DEVICE_KEY_NAME",
    "ENV_NATIVE_CORE_STARTUP_TIMEOUT_MS",
    "ENV_NATIVE_CORE_TRUST_KEY",
    "NativeCoreManagedOperation",
    "ensure_native_core_broker",
    "managed_native_core_operation",
    "resolve_native_core_broker",
    "stop_native_core_broker",
]
