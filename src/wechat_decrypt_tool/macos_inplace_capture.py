"""Recoverable in-place LLDB capture for macOS WeChat 4.1+.

The upstream macOS method requires the installed WeChat bundle to be ad-hoc
signed so LLDB can attach.  This module makes that temporary mutation
transactional: a verified Tencent archive is stored in the caller-selected
backup directory, recovery state is fsynced locally before signing, and the official app
is restored on every terminal path.
"""

from __future__ import annotations

import json
import functools
import hashlib
import os
import platform
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .macos_clone_capture import (
    capture_salt_matched_passphrase,
    _breakpoint_preflight_path,
    _remove_breakpoint_preflight,
)
from .macos_db_key_capture import (
    DEFAULT_DEBUG_ROOT,
    DEFAULT_WECHAT_APP,
    MacOSDBKeyCaptureFailure,
    _find_wechat_bundle_pids,
    _find_wechat_main_pid,
    _debug_identity_matches,
    _has_compatible_in_place_signature,
    _is_tencent_official_signature,
    _local_restore_staging_path,
    _official_identity_matches,
    _launch_wechat,
    _run_as_administrator,
    _validate_captured_passphrase,
    ensure_wechat_in_place_debuggable,
    inspect_wechat_signature,
    normalize_wechat_app_path,
    restore_official_wechat_if_needed,
    save_passphrase,
)
from .macos_native_capture import (
    capture_native_wcdb_key,
    preflight_native_wcdb_capture,
)

IN_PLACE_STATE_NAME = "prepared-in-place-capture.json"
NATIVE_CAPTURE_READY_NAME = "native-capture-ready.json"
STATE_SCHEMA_VERSION = 2
CAPTURE_PHASES = frozenset({"waiting_authorization", "monitoring", "captured", "validating", "restoring"})
DEFAULT_CAPTURE_LOCK_ROOT = Path.home() / "Library/Application Support/WeData/capture-locks"
_OWNER_SESSION = uuid.uuid4().hex
_INSTALLATION_LOCKS: dict[str, dict[str, Any]] = {}
_INSTALLATION_LOCKS_MUTEX = threading.Lock()
_INSTALLATION_OPERATIONS: dict[str, tuple[int, int]] = {}


def _serialized_installation_operation(function):
    """Serialize a synchronous API call, without pinning future calls to its thread."""
    @functools.wraps(function)
    def guarded(wechat_install_path, *args, **kwargs):
        wechat_app = normalize_wechat_app_path(wechat_install_path)
        key, thread = str(wechat_app), threading.get_ident()
        with _INSTALLATION_LOCKS_MUTEX:
            owner, depth = _INSTALLATION_OPERATIONS.get(key, (thread, 0))
            if owner != thread:
                raise MacOSDBKeyCaptureFailure("in_place_capture_busy", "此微信安装的操作尚未结束，请等待完成后重试。")
            _INSTALLATION_OPERATIONS[key] = (thread, depth + 1)
        try:
            return function(wechat_install_path, *args, **kwargs)
        finally:
            with _INSTALLATION_LOCKS_MUTEX:
                owner, depth = _INSTALLATION_OPERATIONS[key]
                if depth == 1:
                    del _INSTALLATION_OPERATIONS[key]
                else:
                    _INSTALLATION_OPERATIONS[key] = (owner, depth - 1)
    return guarded


def _acquire_installation_lock(wechat_app: Path, debug_root: Path) -> dict[str, Any]:
    """Keep a same-user OS lock across HTTP workers and selected data roots.

    The local per-user directory deliberately needs no /Applications write or
    administrator authorization. Transactions by other OS users are not covered.
    """
    import fcntl

    key, owner = str(wechat_app.resolve()), str(debug_root.expanduser().resolve())
    with _INSTALLATION_LOCKS_MUTEX:
        existing = _INSTALLATION_LOCKS.get(key)
        if existing is not None and existing["owner_pid"] != os.getpid():
            # A fork must not treat its parent's inherited descriptor as a new
            # independent transaction owner.
            os.close(existing["fd"])
            del _INSTALLATION_LOCKS[key]
            existing = None
        if existing is not None:
            if existing["debug_root"] != owner:
                raise MacOSDBKeyCaptureFailure("in_place_capture_busy", "此微信安装已有其他捕获事务，请先结束该事务。")
            return existing
        lock_root = DEFAULT_CAPTURE_LOCK_ROOT.expanduser()
        lock_path = lock_root / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = None
        try:
            if lock_root.is_symlink():
                raise OSError("capture lock directory must not be a symlink")
            lock_root.mkdir(parents=True, exist_ok=True)
            os.chmod(lock_root, 0o700)
            descriptor = os.open(lock_path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise MacOSDBKeyCaptureFailure("in_place_capture_busy", "此微信安装正由另一个进程操作，请稍后重试。") from exc
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise MacOSDBKeyCaptureFailure("in_place_capture_lock_unavailable", "无法创建当前用户的本地捕获锁，已停止临时修改。") from exc
        lease = {"fd": descriptor, "debug_root": owner, "transaction_id": uuid.uuid4().hex, "owner_pid": os.getpid()}
        _INSTALLATION_LOCKS[key] = lease
        return lease


def _release_installation_lock(wechat_app: Path, debug_root: Path) -> None:
    key, owner = str(wechat_app.resolve()), str(debug_root.expanduser().resolve())
    with _INSTALLATION_LOCKS_MUTEX:
        lease = _INSTALLATION_LOCKS.get(key)
        if lease is not None and lease["debug_root"] == owner:
            del _INSTALLATION_LOCKS[key]
            os.close(lease["fd"])


def _transaction_is_active(wechat_app: Path, state: dict[str, Any]) -> bool:
    with _INSTALLATION_LOCKS_MUTEX:
        lease = _INSTALLATION_LOCKS.get(str(wechat_app.resolve()))
        return bool(
            lease and state.get("transaction_id") == lease["transaction_id"]
            and state.get("owner_session") == _OWNER_SESSION and state.get("owner_pid") == os.getpid()
        )


def _preserve_recovery_assets(wechat_app: Path, debug_root: Path, state: dict[str, Any]) -> None:
    """Retire an inactive transaction without destroying its original bundle."""
    archived = dict(state)
    archived["stage"] = "superseded_by_external_install"
    archived["superseded_at"] = int(time.time())
    identifier = uuid.uuid4().hex
    staged = _local_restore_staging_path(wechat_app)
    if os.path.lexists(staged):
        if staged.is_symlink() or not staged.is_dir():
            raise MacOSDBKeyCaptureFailure("local_restore_path_unsafe", "原版保护路径异常，已保留并停止操作。")
        preserved = staged.with_name(f".WeChat.wedata-preserved-{identifier}.app")
        # Save the intended destination first so interruption never loses the
        # relationship between the old state and its preserved bundle.
        archived["preserved_staging_path"] = str(preserved)
    else:
        preserved = None
    archive_root = debug_root.expanduser() / "recovery-history" / identifier
    _write_state(archive_root, archived)
    if preserved is not None:
        staged.rename(preserved)
    _remove_state(debug_root)


def _state_path(debug_root: Path) -> Path:
    return debug_root.expanduser() / IN_PLACE_STATE_NAME


def _native_capture_ready_path(debug_root: Path) -> Path:
    return debug_root.expanduser() / NATIVE_CAPTURE_READY_NAME


def _prepare_native_capture_ready(debug_root: Path) -> Path:
    target = _native_capture_ready_path(debug_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    target.touch(mode=0o600, exist_ok=False)
    os.chmod(target, 0o600)
    return target


def _capture_signal(state: dict[str, Any], debug_root: Path) -> str | None:
    """Read only a transaction/PID-bound, non-secret helper progress signal."""
    target = _native_capture_ready_path(debug_root)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    try:
        pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
        preflight = state.get("preflight")
        expected_pid = int((preflight.get("pid") if isinstance(preflight, dict) else None) or state.get("debug_pid") or 0)
    except (TypeError, ValueError):
        return None
    valid = (
        isinstance(payload, dict)
        and state.get("stage") == "capturing"
        and state.get("transaction_id")
        and payload.get("transaction_id") == state.get("transaction_id")
        and payload.get("status") in ("ready", "captured")
        and payload.get("method") in ("macos_native_mach", "macos_lldb_stub")
        and pid > 0
        and pid == expected_pid
    )
    return payload["status"] if valid else None


def _capture_phase(state: dict[str, Any], debug_root: Path) -> str | None:
    if state.get("stage") != "capturing":
        return None
    phase = state.get("capture_phase")
    if phase in ("captured", "validating", "restoring"):
        # The ready file can outlive the monitor. Never invite another login
        # after capture, or while the verified original is being restored.
        return phase
    signal = _capture_signal(state, debug_root)
    if signal == "captured":
        return "captured"
    if signal == "ready":
        return "monitoring"
    if phase == "monitoring":
        return "waiting_authorization"
    return phase if isinstance(phase, str) and phase in CAPTURE_PHASES else None


def native_capture_monitor_ready(*, debug_root: Path = DEFAULT_DEBUG_ROOT) -> bool:
    """Return true only while this transaction's login monitor is armed."""
    try:
        state = _read_state(debug_root)
    except MacOSDBKeyCaptureFailure:
        return False
    return _capture_phase(state, debug_root) == "monitoring"


def _set_capture_phase(debug_root: Path, state: dict[str, Any], phase: str) -> None:
    """Progress is advisory: a UI write failure must never prevent recovery."""
    if state.get("stage") != "capturing" or phase not in CAPTURE_PHASES:
        return
    state["capture_phase"] = phase
    try:
        _write_state(debug_root, state)
    except OSError:
        pass


def _remove_native_capture_ready(debug_root: Path) -> None:
    try:
        _native_capture_ready_path(debug_root).unlink()
    except FileNotFoundError:
        pass


def has_pending_in_place_capture(*, debug_root: Path = DEFAULT_DEBUG_ROOT) -> bool:
    return _state_path(debug_root).is_file()


def get_in_place_capture_status(*, debug_root: Path = DEFAULT_DEBUG_ROOT) -> dict[str, Any]:
    """Return the persisted recovery stage without exposing local paths."""

    if not has_pending_in_place_capture(debug_root=debug_root):
        return {
            "pending": False,
            "stage": "idle",
            "needs_cleanup": False,
            "monitor_ready": False,
            "capture_backend": None,
            "capture_phase": None,
            "prepared_process_exited": None,
            "transaction_id": None,
            "recovery_error_code": None,
        }
    try:
        state = _read_state(debug_root)
        stage = str(state.get("stage") or "unknown").strip().lower()
    except MacOSDBKeyCaptureFailure:
        stage = "invalid"
        state = {}
    if stage not in {"backup_verified", "debug_prepared", "resigned", "awaiting_manual_launch", "launched", "preflight_passed", "capturing", "external_install_conflict", "recovery_blocked", "invalid"}:
        stage = "unknown"
    backend = state.get("capture_backend")
    recovery_code = state.get("recovery_error_code")
    transaction_id = state.get("transaction_id")
    phase = _capture_phase(state, debug_root)
    prepared_process_exited = None
    # Read-only health information for the idle login/preflight UI. Never
    # interpret the deliberate post-capture shutdown as an abnormal exit.
    if stage in {"launched", "preflight_passed"} and state.get("wechat_app_path") == str(DEFAULT_WECHAT_APP):
        try:
            expected_pid = int(state.get("debug_pid") or 0)
            if expected_pid > 0:
                prepared_process_exited = _find_wechat_main_pid(DEFAULT_WECHAT_APP) != expected_pid
        except (OSError, subprocess.SubprocessError, TypeError, ValueError):
            pass  # Unknown is not proof of exit and must not trigger recovery.
    return {
        "pending": True,
        "stage": stage,
        "needs_cleanup": True,
        "monitor_ready": phase == "monitoring",
        "capture_phase": phase,
        "prepared_process_exited": prepared_process_exited,
        "capture_backend": backend if isinstance(backend, str) and backend in {"native", "lldb"} else None,
        "transaction_id": transaction_id if isinstance(transaction_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", transaction_id) else None,
        "recovery_error_code": recovery_code if isinstance(recovery_code, str) and recovery_code in {
            "external_install_conflict", "in_place_debug_identity_unknown", "official_restore_staging_conflict",
        } else None,
    }


def _native_capture_process_targets(debug_root: Path) -> tuple[list[int], list[int]]:
    helper_path = str(debug_root.expanduser() / "native" / "wcdb-native-capture")
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,user=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    osascript_pids: list[int] = []
    helper_pids: list[int] = []
    for raw_line in str(result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line or helper_path not in line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[2]
        if command.startswith("/usr/bin/osascript ") and helper_path in command:
            osascript_pids.append(pid)
        elif command.startswith(helper_path):
            helper_pids.append(pid)
    return osascript_pids, helper_pids


def _terminate_native_capture_processes(debug_root: Path) -> None:
    osascript_pids, helper_pids = _native_capture_process_targets(debug_root)
    if osascript_pids:
        subprocess.run(
            ["/bin/kill", "-TERM", *(str(pid) for pid in osascript_pids)],
            capture_output=True,
            text=True,
            check=False,
        )
    if helper_pids:
        try:
            _run_as_administrator(
                "/bin/kill -TERM "
                + " ".join(str(pid) for pid in helper_pids)
                + " 2>/dev/null || true; /bin/sleep 1; /bin/kill -KILL "
                + " ".join(str(pid) for pid in helper_pids)
                + " 2>/dev/null || true",
                timeout=20,
            )
        except MacOSDBKeyCaptureFailure:
            pass
    lingering_osascript, _ = _native_capture_process_targets(debug_root)
    if lingering_osascript:
        subprocess.run(
            ["/bin/kill", "-KILL", *(str(pid) for pid in lingering_osascript)],
            capture_output=True,
            text=True,
            check=False,
        )


def _write_state(debug_root: Path, payload: dict[str, Any]) -> Path:
    target = _state_path(debug_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        temporary.replace(target)
    except OSError:
        # Only remove the temporary file created by this invocation. Retain
        # the last durable recovery state and allow a later update to retry.
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    os.chmod(target, 0o600)
    try:
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        # Some network-backed home directories reject directory fsync.  The
        # file itself is already fsynced and atomically renamed.
        pass
    return target


def _write_preflight_result(debug_root: Path, payload: dict[str, Any]) -> Path:
    target = _breakpoint_preflight_path(debug_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(target)
    os.chmod(target, 0o600)
    return target


def _write_probe_page1(debug_root: Path, page1: bytes) -> Path:
    target = debug_root.expanduser() / f"probe-page1-{os.getpid()}.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        view = memoryview(page1)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(target, 0o600)
    return target


def _read_state(debug_root: Path) -> dict[str, Any]:
    target = _state_path(debug_root)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise MacOSDBKeyCaptureFailure(
            "in_place_capture_not_prepared",
            "没有找到可恢复的临时重签状态，请重新开始。",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") not in (1, STATE_SCHEMA_VERSION):
        raise MacOSDBKeyCaptureFailure("in_place_capture_state_invalid", "临时重签恢复状态无效，已停止操作")
    return payload


def _remove_state(debug_root: Path) -> None:
    try:
        _state_path(debug_root).unlink()
    except FileNotFoundError:
        pass


def _safe_backup_from_state(state: dict[str, Any], backup_root: Path) -> Path:
    candidate = Path(str(state.get("backup_path") or "")).expanduser()
    root = Path(os.path.abspath(os.fspath(backup_root.expanduser())))
    normalized = Path(os.path.abspath(os.fspath(candidate)))
    if normalized.parent != root or normalized.suffix.lower() != ".zip" or not normalized.name.startswith("WeChat-"):
        raise MacOSDBKeyCaptureFailure(
            "official_backup_path_unsafe",
            "恢复状态中的备份路径不在当前所选备份目录，已拒绝覆盖微信。",
            wechat_modified=True,
        )
    # Do not require the selected backup volume to be reachable here. A verified same-volume APFS
    # clone is created before signing and is the first recovery source.  The
    # archive remains the durable second source if that clone is missing.
    return normalized


def _validate_state_target(state: dict[str, Any], wechat_app: Path) -> None:
    if Path(str(state.get("wechat_app_path") or "")) != wechat_app:
        raise MacOSDBKeyCaptureFailure(
            "in_place_capture_target_mismatch",
            "恢复状态对应的微信安装路径与当前路径不一致，已拒绝覆盖。",
            wechat_modified=True,
        )


def _prepared_signature_is_valid(wechat_app: Path) -> bool:
    signature = inspect_wechat_signature(wechat_app)
    return bool(
        signature.get("valid")
        and signature.get("ad_hoc")
        and not signature.get("hardened_runtime")
        and _has_compatible_in_place_signature(wechat_app)
    )


@_serialized_installation_operation
def recover_stale_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    """Restore a Tencent-signed bundle from a previously recorded transaction."""

    wechat_app = normalize_wechat_app_path(wechat_install_path)
    if not has_pending_in_place_capture(debug_root=debug_root):
        signature = inspect_wechat_signature(wechat_app)
        if not _is_tencent_official_signature(signature):
            raise MacOSDBKeyCaptureFailure(
                "in_place_recovery_state_missing",
                "微信当前不是腾讯原签名，且没有可信恢复状态；为避免覆盖错误应用，已停止自动恢复。",
                wechat_modified=True,
            )
        _release_installation_lock(wechat_app, debug_root)
        return {
            "official_wechat_verified": True,
            "official_wechat_restored": False,
            "wechat_modified": False,
        }

    _acquire_installation_lock(wechat_app, debug_root)
    try:
        state = _read_state(debug_root)
        _validate_state_target(state, wechat_app)
        backup_path = _safe_backup_from_state(state, backup_root)
        expected_version = (str(state.get("version") or ""), str(state.get("build") or ""))
        expected_cdhash = str(state.get("official_cdhash") or "").lower()
        if not all(expected_version) or not expected_cdhash:
            raise MacOSDBKeyCaptureFailure("in_place_capture_state_invalid", "恢复状态缺少原版构建身份，已保留并停止操作。")
        _terminate_native_capture_processes(debug_root)
        result = restore_official_wechat_if_needed(
            wechat_app,
            backup_path,
            expected_version=expected_version,
            expected_cdhash=expected_cdhash,
            expected_debug_identity=state.get("debug_identity"),
        )
        signature = inspect_wechat_signature(wechat_app)
        if not _official_identity_matches(wechat_app, signature, expected_version, expected_cdhash):
            raise MacOSDBKeyCaptureFailure(
                "official_restore_verify_failed", "恢复后微信与本次原版构建身份不符；恢复状态已保留。", wechat_modified=True,
            )
        _remove_breakpoint_preflight(debug_root)
        _remove_native_capture_ready(debug_root)
        _remove_state(debug_root)
        return {**result, "wechat_modified": False, "backup_path": str(backup_path)}
    except MacOSDBKeyCaptureFailure as exc:
        if exc.code == "external_install_conflict":
            state["stage"] = "external_install_conflict"
            state["recovery_error_code"] = exc.code
            _write_state(debug_root, state)
        elif exc.code in {"in_place_debug_identity_unknown", "official_restore_staging_conflict"}:
            state["stage"] = "recovery_blocked"
            state["recovery_error_code"] = exc.code
            _write_state(debug_root, state)
        raise
    finally:
        _release_installation_lock(wechat_app, debug_root)


def _restore_after_terminal_path(
    wechat_app: Path,
    *,
    backup_root: Path,
    debug_root: Path,
    original_error: Exception | None = None,
) -> dict[str, Any]:
    try:
        return recover_stale_in_place_capture(
            wechat_app,
            backup_root=backup_root,
            debug_root=debug_root,
        )
    except Exception as restore_error:
        if isinstance(restore_error, MacOSDBKeyCaptureFailure) and restore_error.code in {
            "external_install_conflict", "in_place_debug_identity_unknown", "official_restore_staging_conflict", "in_place_capture_busy",
        }:
            raise
        if original_error is None:
            raise
        raise MacOSDBKeyCaptureFailure(
            "official_restore_failed",
            f"捕获未完成，且自动恢复腾讯原版微信失败: {restore_error}",
            requires_wechat_resign=True,
            wechat_modified=True,
        ) from restore_error


@_serialized_installation_operation
def prepare_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
    defer_launch: bool = False,
) -> dict[str, Any]:
    """Verify backup, persist recovery state, re-sign in place, and launch."""

    if platform.system().lower() != "darwin":
        raise MacOSDBKeyCaptureFailure("unsupported_platform", "LLDB 密钥捕获仅支持 macOS")
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    if wechat_app != DEFAULT_WECHAT_APP:
        raise MacOSDBKeyCaptureFailure(
            "in_place_default_path_required",
            "临时重签仅允许作用于 /Applications/WeChat.app，请先使用微信默认安装路径。",
        )

    debug_root = debug_root.expanduser()
    debug_root.mkdir(parents=True, exist_ok=True)
    os.chmod(debug_root, 0o700)
    lease = _acquire_installation_lock(wechat_app, debug_root)
    superseded = False

    def record_recovery_state(recovery: dict[str, Any]) -> None:
        _write_state(
            debug_root,
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "stage": "debug_prepared" if recovery.get("debug_identity") else "backup_verified",
                "created_at": int(time.time()),
                "transaction_id": lease["transaction_id"],
                "owner_session": _OWNER_SESSION,
                "owner_pid": os.getpid(),
                **recovery,
            },
        )

    try:
        if has_pending_in_place_capture(debug_root=debug_root):
            previous = _read_state(debug_root)
            _validate_state_target(previous, wechat_app)
            signature = inspect_wechat_signature(wechat_app)
            previous_version = (str(previous.get("version") or ""), str(previous.get("build") or ""))
            previous_cdhash = str(previous.get("official_cdhash") or "")
            if (
                not _transaction_is_active(wechat_app, previous)
                and _is_tencent_official_signature(signature)
                and (not all(previous_version) or not previous_cdhash or not _official_identity_matches(wechat_app, signature, previous_version, previous_cdhash))
            ):
                # A fresh explicit prepare after the old owner has ended may
                # adopt the user's new official installation, never replace it.
                _preserve_recovery_assets(wechat_app, debug_root, previous)
                superseded = True
            else:
                recover_stale_in_place_capture(wechat_app, backup_root=backup_root, debug_root=debug_root)
                lease = _acquire_installation_lock(wechat_app, debug_root)
        signature = inspect_wechat_signature(wechat_app)
        if not _is_tencent_official_signature(signature):
            raise MacOSDBKeyCaptureFailure(
                "in_place_recovery_state_missing", "微信当前不是腾讯原签名，且没有可确认的调试副本身份；已停止临时重签。", wechat_modified=True,
            )
        # Staging without state can survive a crash before the first swap.
        # Preserve it before the low-level clone helper uses the fixed slot.
        if os.path.lexists(_local_restore_staging_path(wechat_app)):
            _preserve_recovery_assets(wechat_app, debug_root, {"schema_version": STATE_SCHEMA_VERSION, "wechat_app_path": str(wechat_app)})
        with _INSTALLATION_LOCKS_MUTEX:
            lease["transaction_id"] = uuid.uuid4().hex
        prepared = ensure_wechat_in_place_debuggable(
            wechat_app,
            backup_root,
            before_resign=record_recovery_state,
        )
        state = _read_state(debug_root)
        state["stage"] = "resigned"
        _write_state(debug_root, state)
        # Desktop opt-in: keep the recovery transaction while the user decides
        # whether to open the app. This neither grants trust nor changes policy.
        debug_pid = None if defer_launch else _launch_wechat(wechat_app)
        state["stage"] = "awaiting_manual_launch" if defer_launch else "launched"
        state["debug_pid"] = debug_pid
        _write_state(debug_root, state)
    except Exception as exc:
        try:
            if has_pending_in_place_capture(debug_root=debug_root):
                _restore_after_terminal_path(
                    wechat_app, backup_root=backup_root, debug_root=debug_root, original_error=exc,
                )
        finally:
            _release_installation_lock(wechat_app, debug_root)
        raise

    return {
        "method": "macos_inplace_lldb_prepare",
        **prepared,
        "debug_pid": debug_pid,
        "state_path": str(_state_path(debug_root)),
        "process_attached": False,
        "ready_for_preflight": not defer_launch,
        "requires_manual_launch": defer_launch,
        "normal_wechat_running": False,
        "previous_transaction_superseded": superseded,
        "transaction_id": state["transaction_id"],
    }


@_serialized_installation_operation
def confirm_manual_in_place_launch(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    transaction_id: str,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    """Check an explicitly user-started app, never launch or authorize it."""
    app = normalize_wechat_app_path(wechat_install_path)
    state = _read_state(debug_root)
    _validate_state_target(state, app)
    _safe_backup_from_state(state, backup_root)
    if (state.get("stage") != "awaiting_manual_launch" or not transaction_id
            or transaction_id != state.get("transaction_id")
            or not _transaction_is_active(app, state)):
        raise MacOSDBKeyCaptureFailure("in_place_capture_owner_changed", "等待启动的事务已变化，请先恢复微信。", wechat_modified=True)

    def verify_identity() -> None:
        if not _prepared_signature_is_valid(app) or not _debug_identity_matches(app, state.get("debug_identity")):
            raise MacOSDBKeyCaptureFailure("in_place_debug_identity_unknown", "微信安装已变化，已停止检查并保留恢复资产。", wechat_modified=True)

    verify_identity()
    result = {"transaction_id": transaction_id, "ready_for_preflight": False, "requires_manual_launch": True}
    pid = _find_wechat_main_pid(app)
    if not pid:
        return result
    time.sleep(2)
    if _find_wechat_main_pid(app) != pid:
        return result
    verify_identity()
    state["debug_pid"] = pid
    state["stage"] = "launched"
    _write_state(debug_root, state)
    return {**result, "ready_for_preflight": True, "requires_manual_launch": False}


@_serialized_installation_operation
def cleanup_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    if has_pending_in_place_capture(debug_root=debug_root):
        recovery = recover_stale_in_place_capture(
            wechat_app,
            backup_root=backup_root,
            debug_root=debug_root,
        )
    else:
        signature = inspect_wechat_signature(wechat_app)
        if not _is_tencent_official_signature(signature):
            raise MacOSDBKeyCaptureFailure(
                "in_place_recovery_state_missing",
                "微信当前不是腾讯原签名，且没有可信恢复状态；已停止自动恢复。",
                wechat_modified=True,
            )
        recovery = {
            "official_wechat_verified": True,
            "official_wechat_restored": False,
            "wechat_modified": False,
        }
        _release_installation_lock(wechat_app, debug_root)
    return {
        "method": "macos_inplace_lldb_cancelled",
        "wechat_resigned": False,
        "official_wechat_preserved": True,
        "normal_wechat_running": False,
        **recovery,
    }


def _require_prepared_process(
    wechat_app: Path,
    *,
    backup_root: Path,
    debug_root: Path,
) -> tuple[dict[str, Any], int]:
    state = _read_state(debug_root)
    _validate_state_target(state, wechat_app)
    _safe_backup_from_state(state, backup_root)
    if not _transaction_is_active(wechat_app, state):
        raise MacOSDBKeyCaptureFailure("in_place_capture_owner_changed", "捕获事务已结束或来自先前进程，请重新准备微信。", wechat_modified=True)
    if not _prepared_signature_is_valid(wechat_app):
        raise MacOSDBKeyCaptureFailure(
            "in_place_signature_changed",
            "微信安装签名状态已变化，已停止捕获并检查本次恢复条件。",
            wechat_modified=True,
        )
    if not _debug_identity_matches(wechat_app, state.get("debug_identity")):
        raise MacOSDBKeyCaptureFailure("in_place_debug_identity_unknown", "当前调试微信不是本次准备的同一副本，已停止捕获。", wechat_modified=True)
    saved_pid = int(state.get("debug_pid") or 0)
    current_pid = _find_wechat_main_pid(wechat_app)
    if saved_pid <= 0 or current_pid is None or saved_pid != current_pid:
        raise MacOSDBKeyCaptureFailure(
            "debug_wechat_not_running",
            "临时调试微信已经退出，将自动恢复腾讯原版微信。",
            wechat_modified=True,
        )
    return state, current_pid


def _candidate_bundle_pids(wechat_app: Path, main_pid: int) -> list[int]:
    pids = [main_pid]
    for value in _find_wechat_bundle_pids(wechat_app):
        if value > 0 and value not in pids:
            pids.append(value)

    commands: dict[int, str] = {}
    loaded_crypto_image: dict[int, bool] = {}
    crypto_image = str(wechat_app / "Contents" / "Resources" / "wechat.dylib")
    for value in pids:
        result = subprocess.run(
            ["/bin/ps", "-p", str(value), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        commands[value] = str(result.stdout or "").strip()
        try:
            vmmap = subprocess.run(
                ["/usr/bin/vmmap", str(value)],
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
            loaded_crypto_image[value] = crypto_image in f"{vmmap.stdout}\n{vmmap.stderr}"
        except (OSError, subprocess.TimeoutExpired):
            loaded_crypto_image[value] = False
    return sorted(
        pids,
        key=lambda value: (
            0 if loaded_crypto_image.get(value, False) else 1,
            0 if value == main_pid else 1,
            0 if "/WeChatAppEx.app/Contents/MacOS/WeChatAppEx" in commands.get(value, "") else 1,
        ),
    )


def _backend_identity(state: dict[str, Any]) -> dict[str, str]:
    return {
        field: str(state.get(field) or "")
        for field in ("version", "build", "official_cdhash")
    } | {"macos_version": platform.mac_ver()[0]}


def _remember_software_backend(state: dict[str, Any], debug_root: Path) -> None:
    """Remember compatibility for this exact official build, without key data."""
    import uuid

    root = debug_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "capture-backend-preference.json"
    temporary = root / f".capture-backend-{uuid.uuid4().hex}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"backend": "lldb", "identity": _backend_identity(state)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _preferred_capture_backend(wechat_app: Path, state: dict[str, Any], debug_root: Path) -> str:
    try:
        if int(platform.mac_ver()[0].split(".")[0]) >= 27:
            return "lldb"
    except (ValueError, IndexError):
        pass
    try:
        remembered = json.loads((debug_root.expanduser() / "capture-backend-preference.json").read_text(encoding="utf-8"))
        if remembered.get("backend") == "lldb" and remembered.get("identity") == _backend_identity(state):
            return "lldb"
    except (OSError, ValueError, AttributeError):
        pass
    # Older Mac builds need not contain the native helper's expected dylib.
    if not (wechat_app / "Contents/Resources/wechat.dylib").is_file():
        return "lldb"
    return "native"


def _can_use_software_backend(error: MacOSDBKeyCaptureFailure) -> bool:
    # Only failures before native debug-state mutation may reuse this PID.
    # task_for_pid alone obtains a task port; image/stub inspection does not
    # suspend threads, install breakpoints, or replace exception ports.
    return error.code in {
        "native_image_not_found", "native_wechat_dylib_missing", "native_pbkdf_stub_missing",
        "native_text_vmaddr_missing", "native_vmmap_image_missing", "native_breakpoint_shape_mismatch",
    }


def _requires_fresh_software_transaction(error: MacOSDBKeyCaptureFailure) -> bool:
    # These outcomes have no verified rollback receipt. Even a live, matching
    # PID can still be suspended or retain native debug state after helper death.
    return error.code in {
        "native_breakpoint_install_failed", "native_exception_port_failed", "native_capture_helper_terminated",
        "native_cleanup_failed",
    } or (
        error.code == "administrator_failed"
        and any(marker in str(error).lower() for marker in ("(1009)", "sigkill", "由于收到信号"))
    )


def _preflight_backend(backend: str, pid: int, wechat_app: Path, debug_root: Path) -> dict[str, Any]:
    if backend == "lldb":
        from .macos_clone_capture import preflight_capture_breakpoints

        result = preflight_capture_breakpoints(pid=pid, debug_root=debug_root, wechat_app=wechat_app)
    else:
        result = preflight_native_wcdb_capture(pid=pid, wechat_app=wechat_app, debug_root=debug_root)
        result = {"pbkdf_locations": 1, "key_return_locations": 0, **result}
    return {**result, "pid": pid, "capture_backend": backend, "ready_for_monitoring": True}


@_serialized_installation_operation
def preflight_prepared_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    try:
        state, debug_pid = _require_prepared_process(
            wechat_app,
            backup_root=backup_root,
            debug_root=debug_root,
        )
        _remove_native_capture_ready(debug_root)
        backend = _preferred_capture_backend(wechat_app, state, debug_root)
        result: dict[str, Any] | None = None
        last_error: MacOSDBKeyCaptureFailure | None = None
        for candidate_pid in _candidate_bundle_pids(wechat_app, debug_pid):
            try:
                result = _preflight_backend(backend, candidate_pid, wechat_app, debug_root)
                break
            except MacOSDBKeyCaptureFailure as exc:
                last_error = exc
                if backend == "native" and _requires_fresh_software_transaction(exc):
                    _remember_software_backend(state, debug_root)
                    raise MacOSDBKeyCaptureFailure(
                        exc.code,
                        "原生预检未能确认调试状态已清理，本次操作将结束并恢复微信；"
                        "已记录下次使用 LLDB。请重新开始新事务，勿继续登录当前临时微信。",
                        process_attached=True,
                    ) from exc
                if backend == "native" and _can_use_software_backend(exc):
                    result = _preflight_backend("lldb", candidate_pid, wechat_app, debug_root)
                    _remember_software_backend(state, debug_root)
                    break
                if exc.code != "native_image_not_found":
                    raise
        if result is None:
            if last_error is not None:
                raise last_error
            raise MacOSDBKeyCaptureFailure(
                "native_image_not_found",
                "临时微信进程中没有找到可用于原生预检的 wechat.dylib。",
                process_attached=True,
            )
        result["transaction_id"] = str(state.get("transaction_id") or "")
        _write_preflight_result(debug_root, result)
        state["preflight"] = result
        state["capture_backend"] = result["capture_backend"]
        state["stage"] = "preflight_passed"
        _write_state(debug_root, state)
    except Exception as exc:
        if has_pending_in_place_capture(debug_root=debug_root):
            _restore_after_terminal_path(
                wechat_app,
                backup_root=backup_root,
                debug_root=debug_root,
                original_error=exc,
            )
        raise
    result.update(
        {
            "method": "macos_inplace_" + result["capture_backend"] + "_preflight",
            "debug_app_path": str(wechat_app),
            "official_wechat_preserved": False,
            "wechat_modified": True,
            "wechat_resigned": True,
        }
    )
    return result


@_serialized_installation_operation
def capture_prepared_in_place(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    probe_db_path: str | Path | None,
    timeout: int = 240,
    save_result: bool = True,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    from .macos_capture_validation import read_account_probe_pages, validate_account_candidate

    wechat_app = normalize_wechat_app_path(wechat_install_path)
    cache_path: Path | None = None
    probe_page1_path: Path | None = None
    ready_path: Path | None = None
    state: dict[str, Any] = {}
    recovery: dict[str, Any] = {}
    try:
        state, debug_pid = _require_prepared_process(
            wechat_app,
            backup_root=backup_root,
            debug_root=debug_root,
        )
        if not probe_db_path:
            raise MacOSDBKeyCaptureFailure("probe_database_required", "必须提供目标数据库用于校验捕获结果")
        probe_database = Path(probe_db_path).expanduser()
        try:
            with probe_database.open("rb") as handle:
                probe_page1 = handle.read(4096)
        except OSError as exc:
            raise MacOSDBKeyCaptureFailure(
                "probe_database_unreadable",
                f"无法读取目标数据库用于实时校验: {probe_database}",
            ) from exc
        if len(probe_page1) < 4096 or probe_page1.startswith(b"SQLite format 3"):
            raise MacOSDBKeyCaptureFailure("probe_database_invalid", f"目标数据库不是有效的加密 WCDB: {probe_database}")
        account_pages = read_account_probe_pages(probe_database)
        probe_page1_path = _write_probe_page1(debug_root, probe_page1)

        preflight_path = _breakpoint_preflight_path(debug_root)
        try:
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            preflight = state.get("preflight") if isinstance(state.get("preflight"), dict) else {}
        if not isinstance(preflight, dict) or not preflight:
            raise MacOSDBKeyCaptureFailure("capture_preflight_required", "请先完成断点预检，再启动登录监测。")
        transaction_id = str(state.get("transaction_id") or "")
        if transaction_id and preflight.get("transaction_id") != transaction_id:
            raise MacOSDBKeyCaptureFailure("capture_preflight_stale", "断点预检属于上一次操作，请重新开始本次获取。")
        preflight_pid = int(preflight.get("pid") or debug_pid)
        candidate_pids = _candidate_bundle_pids(wechat_app, debug_pid)
        if preflight_pid not in candidate_pids:
            raise MacOSDBKeyCaptureFailure("capture_target_changed", "预检后的微信进程已更换，请重新开始并完成预检。")
        backend = str(preflight.get("capture_backend") or state.get("capture_backend") or "native")
        if backend not in {"native", "lldb"}:
            raise MacOSDBKeyCaptureFailure("capture_backend_invalid", "预检记录的监测方案无效，请重新开始。")
        state["stage"] = "capturing"
        state["capture_phase"] = "waiting_authorization"
        state["capture_backend"] = backend
        state["preflight"] = preflight
        _write_state(debug_root, state)
        ready_path = _prepare_native_capture_ready(debug_root)

        def run_software() -> dict[str, Any]:
            details = capture_salt_matched_passphrase(
                pid=preflight_pid,
                expected_salts=[page[:16] for page in account_pages.values()],
                probe_db_path=probe_database,
                account_probe_pages=account_pages,
                pbkdf_stub_plan=state["preflight"].get("pbkdf_stub_plan"),
                return_details=True,
                transaction_id=transaction_id,
                ready_file=ready_path,
                timeout=timeout,
            )
            return {**details, "db_key": details["passphrase"], "method": "macos_lldb_stub"}

        if backend == "lldb":
            capture = run_software()
        else:
            try:
                capture = capture_native_wcdb_key(
                    pid=preflight_pid, wechat_app=wechat_app, probe_db_path=probe_database,
                    probe_page1_path=probe_page1_path, ready_file=ready_path,
                    timeout=timeout, debug_root=debug_root, transaction_id=transaction_id,
                )
            except MacOSDBKeyCaptureFailure as native_error:
                if _requires_fresh_software_transaction(native_error):
                    _remember_software_backend(state, debug_root)
                    raise MacOSDBKeyCaptureFailure(
                        native_error.code,
                        "原生捕获未能确认调试状态已清理，本次操作将结束并恢复微信；"
                        "已记录下次使用 LLDB。请重新开始新事务，等待监测就绪后再登录。",
                        process_attached=True,
                    ) from native_error
                if native_error.code == "native_capture_timeout":
                    _remember_software_backend(state, debug_root)
                    raise MacOSDBKeyCaptureFailure(
                        native_error.code,
                        f"{native_error}；已记录兼容方案，下次获取会改用 LLDB。请重新开始，等待监测就绪后再登录。",
                        process_attached=True,
                    ) from native_error
                if not _can_use_software_backend(native_error):
                    raise
                _require_prepared_process(wechat_app, backup_root=backup_root, debug_root=debug_root)
                _remove_native_capture_ready(debug_root)
                result = _preflight_backend("lldb", preflight_pid, wechat_app, debug_root)
                result["transaction_id"] = transaction_id
                state["preflight"] = result
                state["capture_backend"] = "lldb"
                _write_state(debug_root, state)
                _write_preflight_result(debug_root, result)
                _remember_software_backend(state, debug_root)
                ready_path = _prepare_native_capture_ready(debug_root)
                capture = run_software()
        passphrase = str(capture.get("db_key") or "")
        _set_capture_phase(debug_root, state, "validating")
        validation = validate_account_candidate(passphrase, account_pages)
        _set_capture_phase(debug_root, state, "captured")
    except Exception as exc:
        if has_pending_in_place_capture(debug_root=debug_root):
            _set_capture_phase(debug_root, state, "restoring")
            _restore_after_terminal_path(
                wechat_app,
                backup_root=backup_root,
                debug_root=debug_root,
                original_error=exc,
            )
        raise
    else:
        _set_capture_phase(debug_root, state, "restoring")
        recovery = _restore_after_terminal_path(
            wechat_app,
            backup_root=backup_root,
            debug_root=debug_root,
        )
        if save_result:
            cache_path = save_passphrase(passphrase)
    finally:
        _remove_native_capture_ready(debug_root)
        if probe_page1_path is not None:
            try:
                probe_page1_path.unlink()
            except FileNotFoundError:
                pass

    if save_result and cache_path is None:
        raise MacOSDBKeyCaptureFailure("passphrase_not_saved", "passphrase 未能安全保存")
    return {
        "method": str(capture.get("method") or "macos_native_mach"),
        "key_mode": validation["key_mode"],
        "account_roles_validated": True,
        "validated_roles": validation["validated_roles"],
        "validated": True,
        "probe_db_path": str(probe_database),
        "db_key": passphrase,
        "cache_path": str(cache_path) if cache_path is not None else "",
        "wechat_modified": False,
        "wechat_resigned": True,
        "official_wechat_preserved": True,
        "official_wechat_verified": bool(recovery.get("official_wechat_verified")),
        "official_wechat_restored": bool(recovery.get("official_wechat_restored")),
        "debug_app_path": str(wechat_app),
        "debug_copy_created": False,
        "profile_cloned": False,
        "process_attached": True,
        "normal_wechat_running": False,
        "backup_path": str(state.get("backup_path") or ""),
        "backup_created": bool(state.get("backup_created")),
    }


__all__ = [
    "capture_prepared_in_place",
    "cleanup_in_place_capture",
    "get_in_place_capture_status",
    "has_pending_in_place_capture",
    "native_capture_monitor_ready",
    "preflight_prepared_in_place_capture",
    "prepare_in_place_capture",
    "recover_stale_in_place_capture",
]
