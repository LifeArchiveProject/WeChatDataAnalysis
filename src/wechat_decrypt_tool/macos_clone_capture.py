"""Safe macOS WCDB passphrase capture using an isolated APFS clone.

The Tencent-signed application is never modified.  A disposable ad-hoc copy
runs with a private HOME containing a copy-on-write clone of the real WeChat
container.  LLDB is attached only to that disposable process and accepts a
PBKDF2 password only when the KDF profile and salt match a cloned database and
the candidate passes that database's page-one HMAC verification.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import platform
import plistlib
import re
import shutil
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .macos_db_key_capture import (
    DEFAULT_DEBUG_ROOT,
    MacOSDBKeyCaptureFailure,
    _build_lldb_capture_command,
    _debug_copy_path,
    _find_wechat_main_pid,
    _has_compatible_debug_entitlements,
    _has_debug_copy_marker,
    _is_tencent_official_signature,
    _launch_wechat,
    _mark_debug_copy,
    _quit_wechat,
    _run,
    _run_as_administrator,
    _validate_captured_passphrase,
    inspect_wechat_signature,
    normalize_wechat_app_path,
    save_passphrase,
)

PREPARED_STATE_NAME = "prepared-clone-capture.json"
BREAKPOINT_PREFLIGHT_NAME = "breakpoint-preflight.json"
WECHAT_CONTAINER_RELATIVE = Path("Library/Containers/com.tencent.xinWeChat")
WECHAT_DOCUMENTS_RELATIVE = Path("Documents")
# Verified against the installed Tencent WeChat 4.1.12 arm64 image. The
# breakpoint is the instruction immediately after the function that returns
# the 32-byte WCDB passphrase in a libc++ string at x29-0xb8.
WECHAT_KEY_RETURN_POINTS = {
    "1B1A6433-A445-3247-B7E1-753C09CDB137": 0x2FC6880,
}


def _state_path(debug_root: Path) -> Path:
    return debug_root.expanduser() / PREPARED_STATE_NAME


def _breakpoint_preflight_path(debug_root: Path) -> Path:
    return debug_root.expanduser() / BREAKPOINT_PREFLIGHT_NAME


def _write_state(debug_root: Path, payload: dict[str, Any]) -> Path:
    target = _state_path(debug_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    os.chmod(target, 0o600)
    return target


def _read_state(debug_root: Path) -> dict[str, Any]:
    target = _state_path(debug_root)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise MacOSDBKeyCaptureFailure(
            "clone_capture_not_prepared",
            "没有找到已准备好的隔离微信。请重新执行第一步。",
        ) from exc
    if not isinstance(payload, dict):
        raise MacOSDBKeyCaptureFailure("clone_capture_state_invalid", "隔离微信状态文件无效，请重新准备")
    return payload


def _remove_state(debug_root: Path) -> None:
    target = _state_path(debug_root)
    if target.is_file():
        target.unlink()


def _remove_breakpoint_preflight(debug_root: Path) -> None:
    target = _breakpoint_preflight_path(debug_root)
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def _is_safe_clone_profile(profile: Path, debug_root: Path) -> bool:
    try:
        resolved = profile.expanduser().resolve(strict=False)
        root = debug_root.expanduser().resolve(strict=False)
    except OSError:
        return False
    return resolved.parent == root and resolved.name.startswith("profile-clone-")


def _remove_clone_profile(profile: Path, debug_root: Path) -> None:
    if not _is_safe_clone_profile(profile, debug_root):
        raise MacOSDBKeyCaptureFailure(
            "clone_profile_path_unsafe",
            f"拒绝清理非 WCDA 隔离目录: {profile}",
        )
    if profile.exists():
        last_error: OSError | None = None
        for _attempt in range(5):
            try:
                shutil.rmtree(profile)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.4)
        if profile.exists() and last_error is not None:
            raise last_error


def _debug_copy_is_ready(debug_app: Path) -> bool:
    if not debug_app.is_dir():
        return False
    signature = inspect_wechat_signature(debug_app)
    return bool(
        signature.get("valid")
        and signature.get("ad_hoc")
        and not signature.get("hardened_runtime")
        and _has_compatible_debug_entitlements(debug_app)
        and _has_debug_copy_marker(debug_app)
    )


def _ensure_disposable_debug_copy(wechat_app: Path, debug_root: Path) -> tuple[Path, bool]:
    """Create a copy-on-write app copy; never sign the installed application."""

    debug_root = debug_root.expanduser()
    debug_root.mkdir(parents=True, exist_ok=True)
    os.chmod(debug_root, 0o700)
    debug_app = _debug_copy_path(wechat_app, debug_root)
    if _debug_copy_is_ready(debug_app):
        return debug_app, False
    if debug_app.exists():
        if debug_app.parent.resolve() != debug_root.resolve():
            raise MacOSDBKeyCaptureFailure("debug_copy_path_unsafe", f"调试副本路径不安全: {debug_app}")
        shutil.rmtree(debug_app)

    with tempfile.TemporaryDirectory(prefix="app-copy-", dir=str(debug_root)) as temporary_dir:
        staged_app = Path(temporary_dir) / "WeChat.app"
        # clonefile(2) keeps the temporary copy cheap while preserving bundle
        # metadata. Failure is explicit; there is no physical-copy fallback.
        _clone_path_force(wechat_app, staged_app)
        shutil.move(str(staged_app), str(debug_app))

    _mark_debug_copy(debug_app)
    _run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(debug_app)], timeout=300, check=False)
    _run(["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(debug_app)], timeout=300)
    if not _debug_copy_is_ready(debug_app):
        raise MacOSDBKeyCaptureFailure("debug_copy_sign_failed", "独立微信调试副本签名校验失败")
    return debug_app, True


def _filesystem_type(path: Path) -> str:
    """Return the mounted filesystem type for a local clone source."""

    lines = _run(["/bin/df", "-P", str(path)], timeout=30).stdout.splitlines()
    if len(lines) < 2:
        raise MacOSDBKeyCaptureFailure("clone_filesystem_unknown", f"无法识别快照文件系统: {path}")
    device = lines[-1].split()[0]
    info = _run(["/usr/sbin/diskutil", "info", "-plist", device], timeout=30).stdout
    try:
        payload = plistlib.loads(info.encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError) as exc:
        raise MacOSDBKeyCaptureFailure("clone_filesystem_unknown", f"无法读取快照文件系统信息: {path}") from exc
    return str(payload.get("FilesystemType") or "").strip().lower()


def _is_wechat_container_path(path: Path) -> bool:
    """Classify access errors without resolving protected container paths."""

    try:
        candidate = Path(os.path.abspath(os.path.normpath(os.fspath(path.expanduser()))))
        container_root = Path.home() / WECHAT_CONTAINER_RELATIVE
        return candidate == container_root or container_root in candidate.parents
    except (OSError, TypeError, ValueError):
        return False


def _raise_clone_source_error(source: Path, error_number: int, *, cause: OSError | None = None) -> None:
    if _is_wechat_container_path(source) and error_number in {errno.EACCES, errno.EPERM}:
        failure = MacOSDBKeyCaptureFailure(
            "database_permission_denied",
            "macOS 已阻止 WeChatDataAnalysis 读取微信默认数据容器。请在“系统设置 → 隐私与安全性 → 完全磁盘访问权限”中启用 /Applications/WeChatDataAnalysis.app，然后完全退出并重启本应用后重试。",
        )
        if cause is not None:
            raise failure from cause
        raise failure


def _require_local_apfs_clone(source: Path, destination_parent: Path) -> None:
    """Fail closed before ``cp -c`` could become a physical/network copy."""

    try:
        source_stat = source.stat()
    except OSError as exc:
        _raise_clone_source_error(source, int(exc.errno or 0), cause=exc)
        raise MacOSDBKeyCaptureFailure("clone_source_unavailable", f"无法访问写时复制来源: {source}") from exc
    try:
        destination_stat = destination_parent.stat()
    except OSError as exc:
        raise MacOSDBKeyCaptureFailure(
            "clone_destination_unavailable",
            f"无法访问写时复制目标目录: {destination_parent}",
        ) from exc
    if source.is_symlink():
        raise MacOSDBKeyCaptureFailure("clone_source_symlink", f"拒绝从符号链接创建微信数据快照: {source}")
    if source_stat.st_dev != destination_stat.st_dev:
        raise MacOSDBKeyCaptureFailure(
            "clone_cross_device_blocked",
            "微信数据不在本机快照卷；为避免把网络盘或外部卷数据整库复制到系统盘，已停止操作。",
        )
    if _filesystem_type(source) != "apfs" or _filesystem_type(destination_parent) != "apfs":
        raise MacOSDBKeyCaptureFailure(
            "clone_requires_apfs",
            "隔离登录只允许使用本机 APFS 写时复制快照，已拒绝普通整库复制。",
        )


def _clone_path_force(source: Path, destination: Path) -> None:
    """Clone a file hierarchy through clonefile(2), which never copies data."""

    _require_local_apfs_clone(source, destination.parent)
    if os.path.lexists(destination):
        raise MacOSDBKeyCaptureFailure("clone_destination_exists", f"写时复制目标已存在: {destination}")
    libc = ctypes.CDLL(None, use_errno=True)
    clonefile = libc.clonefile
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    if clonefile(os.fsencode(source), os.fsencode(destination), 0) != 0:
        error_number = ctypes.get_errno()
        _raise_clone_source_error(source, error_number)
        raise MacOSDBKeyCaptureFailure(
            "clonefile_failed",
            f"无法创建 APFS 写时复制快照: {source.name} ({os.strerror(error_number)})",
        )


def _clone_real_wechat_container(debug_root: Path) -> Path:
    source = Path.home() / WECHAT_CONTAINER_RELATIVE
    if not source.is_dir():
        raise MacOSDBKeyCaptureFailure("wechat_container_missing", f"找不到微信默认数据容器: {source}")

    profile = Path(tempfile.mkdtemp(prefix="profile-clone-", dir=str(debug_root)))
    os.chmod(profile, 0o700)
    destination = profile / WECHAT_CONTAINER_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _clone_path_force(source, destination)
        if not destination.is_dir():
            raise MacOSDBKeyCaptureFailure("clone_profile_failed", "微信容器写时复制快照未创建")
        source_data = source / "Data"
        source_documents = source_data / "Documents"
        # CFFIXED_USER_HOME points at ``profile``. Mirror the complete sandbox
        # Data home there (Documents/Library/tmp), while retaining the nested
        # container layout used by WeChatAppEx's explicit command-line paths.
        for child in source_data.iterdir():
            if child.is_symlink():
                continue
            if child.name == "Library":
                # The nested container clone above already created
                # profile/Library/Containers. Merge the remaining Foundation
                # home entries one at a time instead of replacing that tree.
                private_library = profile / "Library"
                private_library.mkdir(parents=True, exist_ok=True)
                for library_child in child.iterdir():
                    if library_child.is_symlink():
                        continue
                    _clone_path_force(library_child, private_library / library_child.name)
                continue
            _clone_path_force(child, profile / child.name)
        private_documents = profile / WECHAT_DOCUMENTS_RELATIVE
        # The user's configured xwechat_files may be a symlink to a network or external volume.
        # Never let the disposable client follow that link: materialize an
        # independent copy inside both private layouts instead.
        _materialize_private_xwechat_files(source_documents, destination / "Data/Documents")
        _materialize_private_xwechat_files(source_documents, private_documents)
    except Exception:
        _remove_clone_profile(profile, debug_root)
        raise
    return profile


def _materialize_private_xwechat_files(source_documents: Path, cloned_documents: Path) -> None:
    destination = cloned_documents / "xwechat_files"
    local_candidate = source_documents / "app_data/xwechat_files"
    source: Path | None = (
        local_candidate
        if local_candidate.is_dir() and not local_candidate.is_symlink()
        else None
    )
    if source is None:
        local_backups = sorted(
            (
                candidate
                for candidate in source_documents.glob("xwechat_files.local-backup-*")
                if candidate.is_dir() and not candidate.is_symlink()
            ),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
        source = local_backups[0] if local_backups else None
    if source is None or not source.is_dir():
        raise MacOSDBKeyCaptureFailure(
            "wechat_data_snapshot_source_missing",
            "默认容器中没有本机 xwechat_files 数据副本；为避免从网络盘或外部卷整库复制到系统盘，已停止操作。",
        )

    if destination.is_symlink() or destination.is_file():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    _clone_path_force(source, destination)


def _collect_database_salts(profile: Path) -> list[str]:
    container = profile / WECHAT_CONTAINER_RELATIVE
    salts: set[str] = set()
    for database in container.rglob("*.db"):
        if "db_storage" not in database.parts:
            continue
        try:
            with database.open("rb") as handle:
                page = handle.read(4096)
        except OSError:
            continue
        if len(page) < 4096 or page.startswith(b"SQLite format 3"):
            continue
        salts.add(page[:16].hex())
    if not salts:
        raise MacOSDBKeyCaptureFailure(
            "clone_database_salts_missing",
            "隔离容器中没有找到可用于匹配密钥的加密微信数据库",
        )
    return sorted(salts)


def _normalize_salts(values: Iterable[str | bytes]) -> list[str]:
    normalized: set[str] = set()
    for value in values:
        candidate = value.hex() if isinstance(value, bytes) else str(value or "").strip().lower()
        if len(candidate) == 32 and all(char in "0123456789abcdef" for char in candidate):
            normalized.add(candidate)
    return sorted(normalized)


def build_lldb_salt_capture_script(
    result_path: Path,
    expected_salts: Iterable[str | bytes],
    *,
    probe_page1: bytes | None = None,
    enable_key_return_fallback: bool = True,
) -> str:
    """Build callbacks that validate candidates before stopping the process."""

    salts = _normalize_salts(expected_salts)
    if not salts:
        raise MacOSDBKeyCaptureFailure("capture_salts_missing", "没有可用于过滤 PBKDF2 调用的数据库 salt")
    result_literal = json.dumps(str(result_path))
    salts_literal = json.dumps(salts)
    hmac_salts_literal = json.dumps(
        {
            bytes(value ^ 0x3A for value in bytes.fromhex(salt)).hex(): salt
            for salt in salts
        },
        sort_keys=True,
    )
    page1_literal = json.dumps(bytes(probe_page1 or b"").hex())
    return f'''import hashlib
import hmac
import json
import lldb
import os

RESULT_PATH = {result_literal}
EXPECTED_SALTS = frozenset({salts_literal})
EXPECTED_HMAC_SALTS = {hmac_salts_literal}
PROBE_PAGE1 = bytes.fromhex({page1_literal})
KEY_RETURN_POINTS = {json.dumps(WECHAT_KEY_RETURN_POINTS)}
ENABLE_KEY_RETURN_FALLBACK = {bool(enable_key_return_fallback)!r}
MODULE_NAME = __name__
DIAGNOSTICS = {{
    "pbkdf_calls": 0,
    "pbkdf_shape_hits": 0,
    "pbkdf_rounds_2_hits": 0,
    "pbkdf_rounds_256000_hits": 0,
    "pbkdf_salt_hits": 0,
    "key_return_hits": 0,
    "candidate_rejections": 0,
}}

def _write_result(payload):
    flags = os.O_WRONLY | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(RESULT_PATH, flags)
    try:
        data = json.dumps(payload).encode()
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                return False
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True

def _record_diagnostic(name):
    DIAGNOSTICS[name] = int(DIAGNOSTICS.get(name, 0)) + 1
    _write_result({{"diagnostics": dict(DIAGNOSTICS)}})

def _register(frame, name):
    return frame.FindRegister(name).GetValueAsUnsigned()

def _candidate_matches_page1(candidate):
    if len(candidate) != 32 or len(PROBE_PAGE1) < 4096:
        return False
    salt = PROBE_PAGE1[:16]
    stored_hmac = PROBE_PAGE1[4032:4096]
    for enc_key in (candidate, hashlib.pbkdf2_hmac("sha512", candidate, salt, 256000, 32)):
        mac_salt = bytes(value ^ 0x3A for value in salt)
        mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, 32)
        digest = hmac.new(mac_key, digestmod=hashlib.sha512)
        digest.update(PROBE_PAGE1[16:4032])
        digest.update((1).to_bytes(4, "little"))
        if hmac.compare_digest(stored_hmac, digest.digest()):
            return True
    return False

def _normalize_candidate(raw):
    if len(raw) == 32:
        return raw
    if len(raw) == 64:
        try:
            decoded = bytes.fromhex(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return b""
        return decoded if len(decoded) == 32 else b""
    return b""

def _save_valid_candidate(candidate, salt, source, process):
    normalized = _normalize_candidate(candidate)
    if not _candidate_matches_page1(normalized):
        _record_diagnostic("candidate_rejections")
        return False
    _write_result({{
        "passphrase": normalized.hex(),
        "salt": salt,
        "source": source,
        "diagnostics": dict(DIAGNOSTICS),
    }})
    print("WEDATA_MATCHED_VALIDATED_DATABASE_KEY", source, flush=True)
    process.Kill()
    os._exit(0)

def _pbkdf_callback(frame, bp_loc, _internal_dict):
    process = frame.GetThread().GetProcess()
    _record_diagnostic("pbkdf_calls")
    algorithm = _register(frame, "x0")
    password_ptr = _register(frame, "x1")
    password_len = _register(frame, "x2")
    salt_ptr = _register(frame, "x3")
    salt_len = _register(frame, "x4")
    prf = _register(frame, "x5")
    rounds = _register(frame, "x6")
    if algorithm != 2 or password_len != 32 or salt_len != 16 or prf != 5 or rounds not in (2, 256000):
        return False
    _record_diagnostic("pbkdf_shape_hits")
    _record_diagnostic("pbkdf_rounds_2_hits" if rounds == 2 else "pbkdf_rounds_256000_hits")

    error = lldb.SBError()
    salt = process.ReadMemory(salt_ptr, salt_len, error)
    if not error.Success() or len(salt) != 16:
        return False
    salt_hex = salt.hex()
    if rounds == 2:
        database_salt = EXPECTED_HMAC_SALTS.get(salt_hex, "")
        source = "pbkdf2_hmac_password"
    else:
        database_salt = salt_hex if salt_hex in EXPECTED_SALTS else ""
        source = "pbkdf2_passphrase"
    if not database_salt:
        return False
    _record_diagnostic("pbkdf_salt_hits")
    password = process.ReadMemory(password_ptr, password_len, error)
    if not error.Success() or len(password) != 32:
        return False

    _save_valid_candidate(password, database_salt, source, process)
    return False

def _report_process_exit(debugger, _command, _result, _internal_dict):
    process = debugger.GetSelectedTarget().GetProcess()
    state = process.GetState()
    try:
        state_name = lldb.SBDebugger.StateAsCString(state) or str(int(state))
    except Exception:
        state_name = str(int(state))
    try:
        exit_status = int(process.GetExitStatus())
    except Exception:
        exit_status = -1
    try:
        exit_description = " ".join(str(process.GetExitDescription() or "").split())[:240]
    except Exception:
        exit_description = ""
    payload = {{
        "pid": int(process.GetProcessID() or 0),
        "state": state_name,
        "exit_status": exit_status,
        "exit_description": exit_description,
    }}
    _write_result({{"diagnostics": dict(DIAGNOSTICS), "process_exit": payload}})
    print("WEDATA_DEBUG_PROCESS_EXIT " + json.dumps(payload, sort_keys=True), flush=True)

def _read_libcxx_string(frame):
    process = frame.GetThread().GetProcess()
    object_address = _register(frame, "x29") - 0xB8
    error = lldb.SBError()
    header = process.ReadMemory(object_address, 24, error)
    if not error.Success() or len(header) != 24:
        return b""
    flag = header[23]
    if flag & 0x80:
        data_address = int.from_bytes(header[0:8], "little")
        length = int.from_bytes(header[8:16], "little")
    else:
        data_address = object_address
        length = flag
    if length <= 0 or length > 128:
        return b""
    value = process.ReadMemory(data_address, length, error)
    return value if error.Success() and len(value) == length else b""

def _key_return_callback(frame, bp_loc, _internal_dict):
    process = frame.GetThread().GetProcess()
    _record_diagnostic("key_return_hits")
    candidate = _read_libcxx_string(frame)
    _save_valid_candidate(candidate, PROBE_PAGE1[:16].hex(), "wechat_key_return", process)
    return False

def _setup(debugger, _command, _result, _internal_dict):
    target = debugger.GetSelectedTarget()
    breakpoint = target.BreakpointCreateByName("CCKeyDerivationPBKDF")
    breakpoint.SetScriptCallbackFunction(f"{{MODULE_NAME}}._pbkdf_callback")
    breakpoint.SetAutoContinue(True)
    pbkdf_locations = breakpoint.GetNumResolvedLocations()
    key_locations = 0
    if ENABLE_KEY_RETURN_FALLBACK:
        for module in target.module_iter():
            uuid = (module.GetUUIDString() or "").upper()
            offset = KEY_RETURN_POINTS.get(uuid)
            if offset is None:
                continue
            address = module.ResolveFileAddress(offset)
            section = address.GetSection() if address.IsValid() else lldb.SBSection()
            if (
                not address.IsValid()
                or not section.IsValid()
                or not (section.GetPermissions() & lldb.ePermissionsExecutable)
                or address.GetLoadAddress(target) == lldb.LLDB_INVALID_ADDRESS
            ):
                continue
            key_breakpoint = target.BreakpointCreateBySBAddress(address)
            key_breakpoint.SetScriptCallbackFunction(f"{{MODULE_NAME}}._key_return_callback")
            key_breakpoint.SetAutoContinue(True)
            key_locations += key_breakpoint.GetNumResolvedLocations()
    print("WEDATA_KEY_MONITOR_READY", pbkdf_locations, key_locations, flush=True)
    if pbkdf_locations <= 0 and key_locations <= 0:
        process = target.GetProcess()
        process.Detach()
        os._exit(24)

def __lldb_init_module(debugger, _internal_dict):
    debugger.HandleCommand(f"command script add -f {{MODULE_NAME}}._setup wedata_capture")
    debugger.HandleCommand(f"command script add -f {{MODULE_NAME}}._report_process_exit wedata_capture_exit_report")
'''


def build_lldb_breakpoint_preflight_script(result_path: Path) -> str:
    """Build a read-only LLDB command that verifies usable runtime breakpoints."""

    result_literal = json.dumps(str(result_path))
    return f'''import json
import lldb
import os

RESULT_PATH = {result_literal}
KEY_RETURN_POINTS = {json.dumps(WECHAT_KEY_RETURN_POINTS)}
MODULE_NAME = __name__

def _write_result(payload):
    flags = os.O_WRONLY | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(RESULT_PATH, flags)
    try:
        data = json.dumps(payload).encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def _resolved_locations(breakpoint):
    try:
        return breakpoint.GetNumResolvedLocations()
    except AttributeError:
        return sum(1 for index in range(breakpoint.GetNumLocations()) if breakpoint.GetLocationAtIndex(index).IsResolved())

def _setup(debugger, _command, _result, _internal_dict):
    target = debugger.GetSelectedTarget()
    process = target.GetProcess()
    pbkdf_breakpoint = target.BreakpointCreateByName("CCKeyDerivationPBKDF")
    pbkdf_locations = _resolved_locations(pbkdf_breakpoint)
    pbkdf_breakpoint.SetEnabled(False)
    key_locations = 0
    matched_modules = []
    rejected_points = []
    for module in target.module_iter():
        uuid = (module.GetUUIDString() or "").upper()
        offset = KEY_RETURN_POINTS.get(uuid)
        if offset is None:
            continue
        module_name = module.GetFileSpec().GetFilename() or "unknown"
        address = module.ResolveFileAddress(offset)
        section = address.GetSection() if address.IsValid() else lldb.SBSection()
        load_address = address.GetLoadAddress(target) if address.IsValid() else lldb.LLDB_INVALID_ADDRESS
        executable = bool(section.IsValid() and section.GetPermissions() & lldb.ePermissionsExecutable)
        if (
            not address.IsValid()
            or not section.IsValid()
            or not executable
            or load_address == lldb.LLDB_INVALID_ADDRESS
        ):
            rejected_points.append({{
                "module": module_name,
                "uuid": uuid,
                "offset": offset,
                "section": section.GetName() if section.IsValid() else "",
            }})
            continue
        breakpoint = target.BreakpointCreateBySBAddress(address)
        locations = _resolved_locations(breakpoint)
        breakpoint.SetEnabled(False)
        if locations > 0:
            key_locations += locations
            matched_modules.append({{
                "module": module_name,
                "uuid": uuid,
                "offset": offset,
                "section": section.GetName() or "",
            }})
    payload = {{
        "pid": process.GetProcessID(),
        "pbkdf_locations": pbkdf_locations,
        "key_return_locations": key_locations,
        "matched_modules": matched_modules,
        "rejected_points": rejected_points,
    }}
    _write_result(payload)
    print("WEDATA_BREAKPOINT_PREFLIGHT", pbkdf_locations, key_locations, flush=True)
    process.Detach()

def __lldb_init_module(debugger, _internal_dict):
    debugger.HandleCommand(f"command script add -f {{MODULE_NAME}}._setup wedata_preflight")
'''


def preflight_capture_breakpoints(*, pid: int, debug_root: Path = DEFAULT_DEBUG_ROOT) -> dict[str, Any]:
    """Attach briefly, validate breakpoint locations, and detach before re-login."""

    if platform.machine().lower() not in {"arm64", "aarch64"}:
        raise MacOSDBKeyCaptureFailure("capture_arch_unsupported", "当前安全捕获流程仅支持 Apple Silicon Mac")
    if shutil.which("lldb") is None:
        raise MacOSDBKeyCaptureFailure("lldb_missing", "未安装 LLDB，请先运行 xcode-select --install")

    result_path = _breakpoint_preflight_path(debug_root)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(result_path.parent, 0o700)
    _remove_breakpoint_preflight(debug_root)
    result_path.touch(mode=0o600, exist_ok=False)
    os.chmod(result_path, 0o600)
    with tempfile.TemporaryDirectory(prefix="wedata-breakpoint-preflight-") as temporary_dir:
        root = Path(temporary_dir)
        callback_path = root / "preflight_callback.py"
        callback_path.write_text(build_lldb_breakpoint_preflight_script(result_path), encoding="utf-8")
        os.chmod(callback_path, 0o600)
        command_path = root / "preflight.lldb"
        command_path.write_text(
            "settings set target.preload-symbols false\n"
            f"process attach -p {int(pid)}\n"
            "process handle SIGTRAP -n false -p false -s false\n"
            f"command script import {callback_path}\n"
            "wedata_preflight\n"
            "quit\n",
            encoding="utf-8",
        )
        os.chmod(command_path, 0o600)
        command = _build_lldb_capture_command(command_path, 45)
        output = _run_as_administrator(command, timeout=90)

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        payload = {}
    compact = " ".join(str(output or "").split()).lower()
    if "attach failed" in compact or "not allowed to attach" in compact:
        _remove_breakpoint_preflight(debug_root)
        raise MacOSDBKeyCaptureFailure("lldb_attach_failed", "LLDB 无法附加独立调试微信完成断点预检")

    pbkdf_locations = int(payload.get("pbkdf_locations") or 0)
    key_return_locations = int(payload.get("key_return_locations") or 0)
    if pbkdf_locations <= 0 and key_return_locations <= 0:
        _remove_breakpoint_preflight(debug_root)
        raise MacOSDBKeyCaptureFailure(
            "capture_breakpoints_unavailable",
            "当前微信版本没有可用的密钥捕获断点；监测未启动，请不要退出账号。",
            process_attached=True,
        )
    return {
        "pid": int(payload.get("pid") or pid),
        "pbkdf_locations": pbkdf_locations,
        "key_return_locations": key_return_locations,
        "matched_modules": list(payload.get("matched_modules") or []),
        "rejected_points": list(payload.get("rejected_points") or []),
        "ready_for_monitoring": True,
        "process_attached": True,
        "process_detached": True,
    }


def capture_salt_matched_passphrase(
    *,
    pid: int,
    expected_salts: Iterable[str | bytes],
    probe_db_path: str | Path,
    timeout: int = 240,
    enable_key_return_fallback: bool = True,
) -> str:
    if platform.machine().lower() not in {"arm64", "aarch64"}:
        raise MacOSDBKeyCaptureFailure("capture_arch_unsupported", "当前安全捕获流程仅支持 Apple Silicon Mac")
    if shutil.which("lldb") is None:
        raise MacOSDBKeyCaptureFailure("lldb_missing", "未安装 LLDB，请先运行 xcode-select --install")

    salts = _normalize_salts(expected_salts)
    probe_database = Path(probe_db_path).expanduser()
    try:
        with probe_database.open("rb") as handle:
            probe_page1 = handle.read(4096)
    except OSError as exc:
        raise MacOSDBKeyCaptureFailure(
            "probe_database_unreadable",
            f"无法读取目标数据库用于实时校验: {probe_database}",
        ) from exc
    if len(probe_page1) < 4096:
        raise MacOSDBKeyCaptureFailure("probe_database_invalid", f"目标数据库首页不完整: {probe_database}")
    with tempfile.TemporaryDirectory(prefix="wedata-salt-capture-") as temporary_dir:
        root = Path(temporary_dir)
        result_path = root / "result.json"
        result_path.touch(mode=0o600)
        callback_path = root / "capture_callback.py"
        callback_path.write_text(
            build_lldb_salt_capture_script(
                result_path,
                salts,
                probe_page1=probe_page1,
                enable_key_return_fallback=enable_key_return_fallback,
            ),
            encoding="utf-8",
        )
        os.chmod(callback_path, 0o600)
        command_path = root / "capture.lldb"
        command_path.write_text(
            "settings set target.preload-symbols false\n"
            f"process attach -p {int(pid)}\n"
            "process handle SIGTRAP -n false -p false -s false\n"
            f"command script import {callback_path}\n"
            "wedata_capture\n"
            "process continue\n"
            "wedata_capture_exit_report\n"
            "quit\n",
            encoding="utf-8",
        )
        os.chmod(command_path, 0o600)
        command = _build_lldb_capture_command(command_path, timeout)
        output = _run_as_administrator(command, timeout=float(timeout + 45))
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            payload = {}

    passphrase = str(payload.get("passphrase") or "").strip().lower()
    captured_salt = str(payload.get("salt") or "").strip().lower()
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    if len(passphrase) == 64 and captured_salt in salts:
        return passphrase
    compact = " ".join(str(output or "").split()).lower()
    if "attach failed" in compact or "not allowed to attach" in compact:
        raise MacOSDBKeyCaptureFailure("lldb_attach_failed", "LLDB 无法附加独立调试微信")
    ready_match = re.search(r"wedata_key_monitor_ready\s+(\d+)\s+(\d+)", compact)
    if ready_match and int(ready_match.group(1)) <= 0 and int(ready_match.group(2)) <= 0:
        raise MacOSDBKeyCaptureFailure(
            "capture_breakpoints_unavailable",
            "当前微信版本没有可用的密钥捕获断点；监测未启动，请不要退出账号。",
            process_attached=True,
        )
    pbkdf_calls = int(diagnostics.get("pbkdf_calls") or 0)
    pbkdf_shape_hits = int(diagnostics.get("pbkdf_shape_hits") or 0)
    pbkdf_rounds_2_hits = int(diagnostics.get("pbkdf_rounds_2_hits") or 0)
    pbkdf_rounds_256000_hits = int(diagnostics.get("pbkdf_rounds_256000_hits") or 0)
    pbkdf_salt_hits = int(diagnostics.get("pbkdf_salt_hits") or 0)
    key_return_hits = int(diagnostics.get("key_return_hits") or 0)
    candidate_rejections = int(diagnostics.get("candidate_rejections") or 0)
    detail = (
        f"断点统计：PBKDF2 调用 {pbkdf_calls}，参数匹配 {pbkdf_shape_hits}，"
        f"rounds=2 命中 {pbkdf_rounds_2_hits}，rounds=256000 命中 {pbkdf_rounds_256000_hits}，"
        f"数据库 salt 匹配 {pbkdf_salt_hits}，微信内部断点 {key_return_hits}，"
        f"候选校验失败 {candidate_rejections}。"
    )
    process_exit = payload.get("process_exit") if isinstance(payload.get("process_exit"), dict) else None
    if process_exit is not None:
        exit_pid = int(process_exit.get("pid") or pid)
        exit_state = " ".join(str(process_exit.get("state") or "unknown").split())[:40]
        exit_status = int(process_exit.get("exit_status") or 0)
        exit_description = " ".join(str(process_exit.get("exit_description") or "").split())[:240]
        exit_detail = f"PID {exit_pid}，状态 {exit_state}，退出码 {exit_status}"
        if exit_description:
            exit_detail += f"，原因 {exit_description}"
        raise MacOSDBKeyCaptureFailure(
            "debug_wechat_exited_during_capture",
            f"独立调试微信在捕获阶段提前结束（{exit_detail}）。" + detail
            + "未保存任何未经数据库校验的候选；"
            + "请将这段非敏感诊断随微信版本和 build 一并反馈。",
            process_attached=True,
        )
    raise MacOSDBKeyCaptureFailure(
        "passphrase_not_captured",
        "没有捕获到与微信数据库 salt 匹配的 passphrase。" + detail
        + "请先在未监测状态下退出到登录界面，再启动监测并重新登录同一账号。",
        process_attached=True,
    )


def _cleanup_prepared_clone(debug_root: Path) -> None:
    try:
        state = _read_state(debug_root)
    except MacOSDBKeyCaptureFailure:
        _remove_breakpoint_preflight(debug_root)
        return
    debug_app = Path(str(state.get("debug_app_path") or ""))
    profile = Path(str(state.get("profile_path") or ""))
    if debug_app.is_dir() and debug_app.parent.resolve() == debug_root.resolve():
        _quit_wechat(debug_app)
    if _is_safe_clone_profile(profile, debug_root):
        _remove_clone_profile(profile, debug_root)
    _remove_state(debug_root)
    _remove_breakpoint_preflight(debug_root)


def prepare_clone_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    del backup_root  # The official app is never changed, so no recovery archive is required.
    if platform.system().lower() != "darwin":
        raise MacOSDBKeyCaptureFailure("unsupported_platform", "LLDB 密钥捕获仅支持 macOS")
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure("official_wechat_untrusted", "正式微信不是有效的腾讯签名版本，已停止操作")
    if _find_wechat_main_pid(wechat_app) is not None:
        raise MacOSDBKeyCaptureFailure(
            "official_wechat_running",
            "请先正常退出腾讯原版微信；安全捕获只会启动名称为 WeChat Debug - WCDA 的独立副本。",
        )

    debug_root = debug_root.expanduser()
    debug_root.mkdir(parents=True, exist_ok=True)
    os.chmod(debug_root, 0o700)
    _cleanup_prepared_clone(debug_root)
    debug_app, debug_created = _ensure_disposable_debug_copy(wechat_app, debug_root)
    # Also recover from a stale state file: a previous debug process must not
    # be mistaken for the new profile that will be written below.
    _quit_wechat(debug_app)
    profile = _clone_real_wechat_container(debug_root)
    try:
        salts = _collect_database_salts(profile)
        debug_pid = _launch_wechat(debug_app, isolated_home=profile)
        state_path = _write_state(
            debug_root,
            {
                "debug_app_path": str(debug_app),
                "profile_path": str(profile),
                "debug_pid": debug_pid,
                "database_salts": salts,
            },
        )
    except Exception:
        _quit_wechat(debug_app)
        _remove_clone_profile(profile, debug_root)
        raise

    return {
        "method": "macos_clone_lldb_prepare",
        "wechat_resigned": False,
        "wechat_modified": False,
        "official_wechat_preserved": True,
        "debug_app_path": str(debug_app),
        "debug_copy_created": debug_created,
        "debug_pid": debug_pid,
        "profile_cloned": True,
        "matched_salt_count": len(salts),
        "state_path": str(state_path),
        "process_attached": False,
        "ready_for_preflight": True,
        "normal_wechat_running": False,
        "backup_path": "",
        "backup_created": False,
    }


def cleanup_clone_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    del backup_root
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure(
            "official_wechat_untrusted",
            "腾讯原版微信签名异常；为避免覆盖应用，已停止自动清理。",
            wechat_modified=True,
        )
    _cleanup_prepared_clone(debug_root)
    return {
        "method": "macos_clone_lldb_cancelled",
        "wechat_modified": False,
        "wechat_resigned": False,
        "official_wechat_preserved": True,
        "official_wechat_verified": True,
        "official_wechat_restored": False,
        "normal_wechat_running": _find_wechat_main_pid(wechat_app) is not None,
    }


def preflight_prepared_clone(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    """Verify breakpoint locations for the prepared Debug process, then detach."""

    del backup_root
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure("official_wechat_untrusted", "腾讯原版微信签名异常，已停止断点预检")
    state = _read_state(debug_root)
    debug_app = Path(str(state.get("debug_app_path") or ""))
    profile = Path(str(state.get("profile_path") or ""))
    if not _is_safe_clone_profile(profile, debug_root) or not _debug_copy_is_ready(debug_app):
        raise MacOSDBKeyCaptureFailure("clone_capture_state_invalid", "隔离微信状态无效，请重新准备")
    saved_pid = int(state.get("debug_pid") or 0)
    debug_pid = _find_wechat_main_pid(debug_app)
    if saved_pid <= 0 or debug_pid is None or debug_pid != saved_pid:
        raise MacOSDBKeyCaptureFailure("debug_capture_state_stale", "独立微信进程与捕获快照不匹配，请重新准备")

    try:
        result = preflight_capture_breakpoints(pid=debug_pid, debug_root=debug_root)
    except Exception:
        _cleanup_prepared_clone(debug_root)
        raise
    result.update(
        {
            "method": "macos_lldb_breakpoint_preflight",
            "debug_app_path": str(debug_app),
            "official_wechat_preserved": True,
            "wechat_modified": False,
            "wechat_resigned": False,
        }
    )
    return result


def capture_prepared_clone(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    probe_db_path: str | Path | None,
    timeout: int = 240,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    del backup_root
    wechat_app = normalize_wechat_app_path(wechat_install_path)
    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure("official_wechat_untrusted", "腾讯原版微信签名异常，已停止捕获")
    state = _read_state(debug_root)
    debug_app = Path(str(state.get("debug_app_path") or ""))
    profile = Path(str(state.get("profile_path") or ""))
    salts = _normalize_salts(state.get("database_salts") or [])
    if not _is_safe_clone_profile(profile, debug_root) or not _debug_copy_is_ready(debug_app):
        raise MacOSDBKeyCaptureFailure("clone_capture_state_invalid", "隔离微信状态无效，请重新准备")
    saved_pid = int(state.get("debug_pid") or 0)
    debug_pid = _find_wechat_main_pid(debug_app)
    if debug_pid is None:
        _cleanup_prepared_clone(debug_root)
        raise MacOSDBKeyCaptureFailure("debug_wechat_not_running", "独立调试微信未运行，请重新准备")
    if saved_pid <= 0 or debug_pid != saved_pid:
        _cleanup_prepared_clone(debug_root)
        raise MacOSDBKeyCaptureFailure("debug_capture_state_stale", "独立微信进程与捕获快照不匹配，请重新准备")
    if not probe_db_path:
        _cleanup_prepared_clone(debug_root)
        raise MacOSDBKeyCaptureFailure("probe_database_required", "必须提供目标数据库用于校验捕获结果")

    preflight_path = _breakpoint_preflight_path(debug_root)
    try:
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        _cleanup_prepared_clone(debug_root)
        raise MacOSDBKeyCaptureFailure(
            "capture_preflight_required",
            "尚未完成断点预检；监测未启动，请重新准备并先执行预检。",
        )
    if (
        int(preflight.get("pid") or 0) != debug_pid
        or (
            int(preflight.get("pbkdf_locations") or 0) <= 0
            and int(preflight.get("key_return_locations") or 0) <= 0
        )
    ):
        _cleanup_prepared_clone(debug_root)
        raise MacOSDBKeyCaptureFailure(
            "capture_preflight_stale",
            "断点预检结果与当前独立微信进程不匹配；监测未启动，请重新准备。",
        )

    cache_path: Path | None = None
    try:
        passphrase = capture_salt_matched_passphrase(
            pid=debug_pid,
            expected_salts=salts,
            probe_db_path=probe_db_path,
            timeout=timeout,
            # Monitoring starts only after the account is already at the QR
            # screen, so it is safe to arm both validated locations.  On
            # WeChat 4.1.12 the public CommonCrypto symbol resolves but is not
            # necessarily called again by every re-login path; the verified
            # internal return point is therefore required as a live fallback.
            enable_key_return_fallback=int(preflight.get("key_return_locations") or 0) > 0,
        )
        _validate_captured_passphrase(passphrase, probe_db_path)
        cache_path = save_passphrase(passphrase)
    finally:
        _cleanup_prepared_clone(debug_root)
    if cache_path is None:
        raise MacOSDBKeyCaptureFailure("passphrase_not_saved", "passphrase 未能安全保存")
    return {
        "method": "macos_clone_lldb_passphrase",
        "cache_path": str(cache_path),
        "wechat_modified": False,
        "wechat_resigned": False,
        "official_wechat_preserved": True,
        "official_wechat_verified": True,
        "official_wechat_restored": False,
        "debug_app_path": str(debug_app),
        "debug_copy_created": False,
        "profile_cloned": True,
        "process_attached": True,
        "normal_wechat_running": False,
        "backup_path": "",
        "backup_created": False,
    }


__all__ = [
    "build_lldb_breakpoint_preflight_script",
    "build_lldb_salt_capture_script",
    "capture_prepared_clone",
    "capture_salt_matched_passphrase",
    "cleanup_clone_capture",
    "preflight_capture_breakpoints",
    "preflight_prepared_clone",
    "prepare_clone_capture",
]
