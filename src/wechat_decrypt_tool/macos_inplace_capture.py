"""Recoverable in-place LLDB capture for macOS WeChat 4.1+.

The upstream macOS method requires the installed WeChat bundle to be ad-hoc
signed so LLDB can attach.  This module makes that temporary mutation
transactional: a verified Tencent archive is stored in the caller-selected
backup directory, recovery state is fsynced locally before signing, and the official app
is restored on every terminal path.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

from .macos_clone_capture import (
    _breakpoint_preflight_path,
    _remove_breakpoint_preflight,
)
from .macos_db_key_capture import (
    DEFAULT_DEBUG_ROOT,
    DEFAULT_WECHAT_APP,
    MacOSDBKeyCaptureFailure,
    _find_wechat_bundle_pids,
    _find_wechat_main_pid,
    _has_compatible_in_place_signature,
    _is_tencent_official_signature,
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
STATE_SCHEMA_VERSION = 1


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


def native_capture_monitor_ready(*, debug_root: Path = DEFAULT_DEBUG_ROOT) -> bool:
    """Return true only after the native monitor has armed its breakpoint."""

    target = _native_capture_ready_path(debug_root)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("status") == "ready"
        and payload.get("method") == "macos_native_mach"
        and int(payload.get("pid") or 0) > 0
    )


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
        }
    try:
        state = _read_state(debug_root)
        stage = str(state.get("stage") or "unknown").strip().lower()
    except MacOSDBKeyCaptureFailure:
        stage = "invalid"
    if stage not in {"backup_verified", "resigned", "launched", "preflight_passed", "invalid"}:
        stage = "unknown"
    return {
        "pending": True,
        "stage": stage,
        "needs_cleanup": True,
        "monitor_ready": native_capture_monitor_ready(debug_root=debug_root),
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
    if not isinstance(payload, dict) or int(payload.get("schema_version") or 0) != STATE_SCHEMA_VERSION:
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


def recover_stale_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    """Restore a Tencent-signed bundle from a previously recorded transaction."""

    wechat_app = normalize_wechat_app_path(wechat_install_path)
    _terminate_native_capture_processes(debug_root)
    if not has_pending_in_place_capture(debug_root=debug_root):
        signature = inspect_wechat_signature(wechat_app)
        if not _is_tencent_official_signature(signature):
            raise MacOSDBKeyCaptureFailure(
                "in_place_recovery_state_missing",
                "微信当前不是腾讯原签名，且没有可信恢复状态；为避免覆盖错误应用，已停止自动恢复。",
                wechat_modified=True,
            )
        return {
            "official_wechat_verified": True,
            "official_wechat_restored": False,
            "wechat_modified": False,
        }

    state = _read_state(debug_root)
    _validate_state_target(state, wechat_app)
    backup_path = _safe_backup_from_state(state, backup_root)
    expected_version = (str(state.get("version") or ""), str(state.get("build") or ""))
    expected_cdhash = str(state.get("official_cdhash") or "").lower()
    result = restore_official_wechat_if_needed(
        wechat_app,
        backup_path,
        expected_version=expected_version,
        expected_cdhash=expected_cdhash or None,
    )
    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure(
            "official_restore_verify_failed",
            "自动恢复完成后仍无法验证腾讯原版微信签名，恢复状态已保留。",
            wechat_modified=True,
        )
    _remove_breakpoint_preflight(debug_root)
    _remove_native_capture_ready(debug_root)
    # Remove durable state last.  If the process dies after the atomic app
    # exchange but before this unlink, the next startup observes an official
    # installation, removes any displaced staging bundle, and finishes safely.
    _remove_state(debug_root)
    return {
        **result,
        "wechat_modified": False,
        "backup_path": str(backup_path),
    }


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
        if original_error is None:
            raise
        raise MacOSDBKeyCaptureFailure(
            "official_restore_failed",
            f"捕获未完成，且自动恢复腾讯原版微信失败: {restore_error}",
            requires_wechat_resign=True,
            wechat_modified=True,
        ) from restore_error


def prepare_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
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

    # A killed prior run is recovered before a new mutation can begin.
    if has_pending_in_place_capture(debug_root=debug_root):
        recover_stale_in_place_capture(wechat_app, backup_root=backup_root, debug_root=debug_root)
    else:
        signature = inspect_wechat_signature(wechat_app)
        if not _is_tencent_official_signature(signature):
            raise MacOSDBKeyCaptureFailure(
                "in_place_recovery_state_missing",
                "微信当前不是腾讯原签名，且没有可信恢复状态；已停止临时重签。",
                wechat_modified=True,
            )
    debug_root = debug_root.expanduser()
    debug_root.mkdir(parents=True, exist_ok=True)
    os.chmod(debug_root, 0o700)

    def record_recovery_state(recovery: dict[str, Any]) -> None:
        _write_state(
            debug_root,
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "stage": "backup_verified",
                "created_at": int(time.time()),
                **recovery,
            },
        )

    try:
        prepared = ensure_wechat_in_place_debuggable(
            wechat_app,
            backup_root,
            before_resign=record_recovery_state,
        )
        state = _read_state(debug_root)
        state["stage"] = "resigned"
        _write_state(debug_root, state)
        debug_pid = _launch_wechat(wechat_app)
        state["stage"] = "launched"
        state["debug_pid"] = debug_pid
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

    return {
        "method": "macos_inplace_lldb_prepare",
        **prepared,
        "debug_pid": debug_pid,
        "state_path": str(_state_path(debug_root)),
        "process_attached": False,
        "ready_for_preflight": True,
        "normal_wechat_running": False,
    }


def cleanup_in_place_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    _terminate_native_capture_processes(debug_root)
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
    if not _prepared_signature_is_valid(wechat_app):
        raise MacOSDBKeyCaptureFailure(
            "in_place_signature_changed",
            "临时调试微信签名状态已变化，将先恢复腾讯原版后再重新开始。",
            wechat_modified=True,
        )
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
        result: dict[str, Any] | None = None
        last_error: MacOSDBKeyCaptureFailure | None = None
        for candidate_pid in _candidate_bundle_pids(wechat_app, debug_pid):
            try:
                result = preflight_native_wcdb_capture(
                    pid=candidate_pid,
                    wechat_app=wechat_app,
                    debug_root=debug_root,
                )
                break
            except MacOSDBKeyCaptureFailure as exc:
                last_error = exc
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
        _write_preflight_result(debug_root, result)
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
            "method": "macos_inplace_native_preflight",
            "debug_app_path": str(wechat_app),
            "official_wechat_preserved": False,
            "wechat_modified": True,
            "wechat_resigned": True,
        }
    )
    return result


def capture_prepared_in_place(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    probe_db_path: str | Path | None,
    timeout: int = 240,
    save_result: bool = True,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
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
        probe_page1_path = _write_probe_page1(debug_root, probe_page1)

        preflight_path = _breakpoint_preflight_path(debug_root)
        try:
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            preflight = {}
        preflight_pid = int(preflight.get("pid") or debug_pid)
        candidate_pids = _candidate_bundle_pids(wechat_app, debug_pid)
        if preflight_pid not in candidate_pids:
            preflight_pid = candidate_pids[0] if candidate_pids else debug_pid

        ready_path = _prepare_native_capture_ready(debug_root)
        capture = capture_native_wcdb_key(
            pid=preflight_pid,
            wechat_app=wechat_app,
            probe_db_path=probe_database,
            probe_page1_path=probe_page1_path,
            ready_file=ready_path,
            timeout=timeout,
            debug_root=debug_root,
        )
        passphrase = str(capture.get("db_key") or "")
        _validate_captured_passphrase(passphrase, probe_database)
        if save_result:
            cache_path = save_passphrase(passphrase)
    except Exception as exc:
        if has_pending_in_place_capture(debug_root=debug_root):
            _restore_after_terminal_path(
                wechat_app,
                backup_root=backup_root,
                debug_root=debug_root,
                original_error=exc,
            )
        raise
    else:
        recovery = _restore_after_terminal_path(
            wechat_app,
            backup_root=backup_root,
            debug_root=debug_root,
        )
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
