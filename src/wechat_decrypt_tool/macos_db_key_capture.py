"""macOS WeChat 4.1+ passphrase capture with explicit administrator approval.

The LLDB breakpoint and register selection are adapted from
TANGandXUE/wcdb-key-tool (MIT).  WeChat is temporarily re-signed only after a
Tencent-signed, version-matched backup has been verified.  The higher-level
capture workflow records recovery state before that mutation and restores the
official application after success, failure, cancellation, or the next launch.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_WECHAT_APP = Path("/Applications/WeChat.app")
DEFAULT_DEBUG_ROOT = Path.home() / "Library/Caches/WeChatDataAnalysis/wechat-debug"
LOCAL_RESTORE_STAGING_NAME = ".WeChat.wedata-official-restore.app"
DEBUG_COPY_DISPLAY_NAME = "WeChat Debug - WCDA"
DEBUG_LOGIN_HELPER = Path("Contents/MacOS/WeChatAppEx.app")
PASSPHRASE_RELATIVE_PATH = Path(".wcdb-key-tool/wechat-passphrase.json")
_PASSPHRASE_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MEMORY_LINE_RE = re.compile(r"\s*0x[0-9a-fA-F]+:\s+((?:0x[0-9a-fA-F]{2}\s*)+)$")


@dataclass(frozen=True, slots=True)
class MacOSDBKeyCaptureFailure(RuntimeError):
    code: str
    message: str
    requires_wechat_resign: bool = False
    wechat_modified: bool = False
    process_attached: bool = False

    def __str__(self) -> str:
        return self.message


def _run(
    args: list[str],
    *,
    timeout: float = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
    except subprocess.TimeoutExpired as exc:
        raise MacOSDBKeyCaptureFailure("command_timeout", f"命令执行超时: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = " ".join(str(exc.stderr or exc.stdout or "").split())[-600:]
        raise MacOSDBKeyCaptureFailure(
            "command_failed",
            f"命令执行失败: {Path(args[0]).name}{(': ' + detail) if detail else ''}",
        ) from exc


def _run_as_administrator(command: str, *, timeout: float) -> str:
    apple_script = (
        "on run argv\n"
        "do shell script (item 1 of argv) with administrator privileges\n"
        "end run"
    )
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", apple_script, command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise MacOSDBKeyCaptureFailure("administrator_timeout", "管理员授权或密钥捕获等待超时") from exc
    except subprocess.CalledProcessError as exc:
        detail = " ".join(str(exc.stderr or exc.stdout or "").split())[-600:]
        code = "administrator_cancelled" if "User canceled" in detail or "-128" in detail else "administrator_failed"
        message = "已取消管理员授权" if code == "administrator_cancelled" else f"管理员操作失败: {detail or '未知错误'}"
        raise MacOSDBKeyCaptureFailure(code, message) from exc
    return str(result.stdout or "")


def normalize_wechat_app_path(value: str | Path | None) -> Path:
    candidate = Path(value or DEFAULT_WECHAT_APP).expanduser()
    if candidate.name == "WeChat" and candidate.parent.name == "MacOS":
        candidate = candidate.parents[2]
    try:
        candidate = candidate.resolve(strict=True)
    except OSError as exc:
        raise MacOSDBKeyCaptureFailure("wechat_missing", f"微信应用不存在: {candidate}") from exc
    if candidate.suffix.lower() != ".app" or not candidate.is_dir():
        raise MacOSDBKeyCaptureFailure("invalid_wechat_app", f"不是有效的微信 App: {candidate}")

    info_path = candidate / "Contents/Info.plist"
    executable = candidate / "Contents/MacOS/WeChat"
    try:
        info = plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise MacOSDBKeyCaptureFailure("invalid_wechat_app", f"无法读取微信 Info.plist: {candidate}") from exc
    if str(info.get("CFBundleIdentifier") or "") != "com.tencent.xinWeChat" or not executable.is_file():
        raise MacOSDBKeyCaptureFailure("invalid_wechat_app", f"应用身份不是 com.tencent.xinWeChat: {candidate}")
    return candidate


def inspect_wechat_signature(wechat_app: Path) -> dict[str, Any]:
    result = _run(["/usr/bin/codesign", "-dvvv", str(wechat_app)], check=False)
    output = f"{result.stdout}\n{result.stderr}"
    valid = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(wechat_app)],
        capture_output=True,
        text=True,
        check=False,
    ).returncode == 0
    hardened_runtime = bool(re.search(r"flags=.*\bruntime\b", output))
    ad_hoc = "Signature=adhoc" in output or bool(re.search(r"flags=0x[0-9a-fA-F]+\(adhoc", output))
    team_match = re.search(r"^TeamIdentifier=([^\s]+)", output, re.MULTILINE)
    identifier_match = re.search(r"^Identifier=([^\s]+)", output, re.MULTILINE)
    cdhash_match = re.search(r"^CDHash=([0-9a-fA-F]+)", output, re.MULTILINE)
    team_identifier = "" if not team_match or team_match.group(1) == "not" else team_match.group(1)
    return {
        "valid": valid,
        "hardened_runtime": hardened_runtime,
        "ad_hoc": ad_hoc,
        "team_identifier": team_identifier,
        "identifier": identifier_match.group(1) if identifier_match else "",
        "cdhash": cdhash_match.group(1).lower() if cdhash_match else "",
        "requires_resign": (not valid) or hardened_runtime or not ad_hoc,
    }


def _is_tencent_official_signature(signature: dict[str, Any]) -> bool:
    return bool(
        signature.get("valid")
        and not signature.get("ad_hoc")
        and signature.get("team_identifier") == "5A4RE8SF68"
        and signature.get("identifier") == "com.tencent.xinWeChat"
    )


def _wechat_version(wechat_app: Path) -> tuple[str, str]:
    info = plistlib.loads((wechat_app / "Contents/Info.plist").read_bytes())
    safe = lambda value: re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "unknown"))
    return safe(info.get("CFBundleShortVersionString")), safe(info.get("CFBundleVersion"))


def _original_backup_path(wechat_app: Path, backup_root: Path) -> Path:
    version, build = _wechat_version(wechat_app)
    return backup_root.expanduser() / f"WeChat-{version}-{build}-original.zip"


def backup_original_wechat(wechat_app: Path, backup_root: Path) -> tuple[Path, bool]:
    version, build = _wechat_version(wechat_app)
    backup_root = backup_root.expanduser()
    backup_root.mkdir(parents=True, exist_ok=True)
    # App bundles copied directly to some external filesystems can lose
    # signature-related metadata. A ditto ZIP with sequestered resource forks
    # restores the original bundle faithfully on macOS.
    final_path = backup_root / f"WeChat-{version}-{build}-original.zip"
    if final_path.is_file():
        valid = subprocess.run(
            ["/usr/bin/unzip", "-tqq", str(final_path)],
            capture_output=True,
            text=True,
            check=False,
        ).returncode == 0
        if valid and final_path.stat().st_size > 0:
            return final_path, False
        raise MacOSDBKeyCaptureFailure("backup_invalid", f"已有微信备份压缩包不完整，请人工检查: {final_path}")

    staging = backup_root / f".{final_path.name}.copying"
    if staging.exists():
        staging.unlink()
    try:
        _run(
            [
                "/usr/bin/ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(wechat_app),
                str(staging),
            ],
            timeout=1800,
        )
        _run(["/usr/bin/unzip", "-tqq", str(staging)], timeout=600)
        staging.replace(final_path)
    except Exception:
        if staging.exists():
            staging.unlink()
        raise
    return final_path, True


def verify_original_wechat_backup(
    backup_path: Path,
    *,
    expected_version: tuple[str, str] | None = None,
    work_root: Path | None = None,
) -> dict[str, Any]:
    """Extract and verify the selected backup archive before changing the installed app."""

    backup_path = backup_path.expanduser()
    if not backup_path.is_file() or backup_path.stat().st_size <= 0:
        raise MacOSDBKeyCaptureFailure("backup_missing", f"找不到微信原版备份: {backup_path}")
    _run(["/usr/bin/unzip", "-tqq", str(backup_path)], timeout=600)

    verify_root = (work_root or DEFAULT_DEBUG_ROOT).expanduser()
    verify_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="verify-backup-", dir=str(verify_root)) as temp_dir:
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        _run(["/usr/bin/ditto", "-x", "-k", str(backup_path), str(extract_root)], timeout=1800)
        extracted_app = normalize_wechat_app_path(extract_root / "WeChat.app")
        signature = inspect_wechat_signature(extracted_app)
        if not _is_tencent_official_signature(signature):
            raise MacOSDBKeyCaptureFailure(
                "official_backup_untrusted",
                "所选目录中的微信原版备份不是有效的腾讯签名版本，已停止临时重签。",
            )
        version = _wechat_version(extracted_app)
        if expected_version is not None and version != expected_version:
            raise MacOSDBKeyCaptureFailure(
                "official_backup_version_mismatch",
                "所选目录中的微信原版备份版本与当前安装版本不一致，已停止临时重签。",
            )
    return {
        "backup_path": str(backup_path),
        "backup_size": backup_path.stat().st_size,
        "version": version[0],
        "build": version[1],
        "team_identifier": signature.get("team_identifier", ""),
        "cdhash": signature.get("cdhash", ""),
        "verified": True,
    }


def _local_restore_staging_path(wechat_app: Path) -> Path:
    return wechat_app.with_name(LOCAL_RESTORE_STAGING_NAME)


def _remove_local_restore_staging(staged: Path) -> None:
    if not os.path.lexists(staged):
        return
    if staged.is_symlink() or not staged.is_dir():
        raise MacOSDBKeyCaptureFailure(
            "local_restore_path_unsafe",
            f"原版微信保护路径类型异常，已停止自动覆盖: {staged}",
            wechat_modified=True,
        )
    shutil.rmtree(staged)


def _prepare_local_restore_staging(
    wechat_app: Path,
    *,
    expected_version: tuple[str, str],
    expected_cdhash: str,
) -> Path:
    """Create a same-volume APFS clone that survives a temporary backup-volume outage."""

    staged = _local_restore_staging_path(wechat_app)
    _remove_local_restore_staging(staged)
    library = ctypes.CDLL(None, use_errno=True)
    clonefile = getattr(library, "clonefile", None)
    if clonefile is None:
        raise MacOSDBKeyCaptureFailure("local_restore_clone_unavailable", "当前 macOS 不支持原版微信写时复制保护")
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    if clonefile(os.fsencode(wechat_app), os.fsencode(staged), 0) != 0:
        error_number = ctypes.get_errno()
        if os.path.lexists(staged):
            _remove_local_restore_staging(staged)
        raise MacOSDBKeyCaptureFailure(
            "local_restore_clone_failed",
            f"无法创建原版微信写时复制保护: {os.strerror(error_number)}",
        )
    signature = inspect_wechat_signature(staged)
    if (
        not _is_tencent_official_signature(signature)
        or _wechat_version(staged) != expected_version
        or (expected_cdhash and str(signature.get("cdhash") or "").lower() != expected_cdhash.lower())
    ):
        _remove_local_restore_staging(staged)
        raise MacOSDBKeyCaptureFailure("local_restore_clone_invalid", "原版微信写时复制保护校验失败，已停止临时重签")
    return staged


def _find_wechat_pid() -> int | None:
    result = subprocess.run(["/usr/bin/pgrep", "-x", "WeChat"], capture_output=True, text=True, check=False)
    for value in str(result.stdout or "").split():
        if value.isdigit():
            return int(value)
    return None


def _find_wechat_main_pid(wechat_app: Path) -> int | None:
    executable = str(wechat_app / "Contents/MacOS/WeChat")
    result = subprocess.run(["/usr/bin/pgrep", "-f", f"^{re.escape(executable)}$"], capture_output=True, text=True, check=False)
    for value in str(result.stdout or "").split():
        if value.isdigit():
            return int(value)
    return None


def _find_wechat_bundle_pids(wechat_app: Path) -> list[int]:
    pattern = "^" + re.escape(str(wechat_app / "Contents")) + "/"
    result = subprocess.run(["/usr/bin/pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return [int(value) for value in str(result.stdout or "").split() if value.isdigit()]


def _quit_wechat(wechat_app: Path, timeout: float = 30, *, force_for_restore: bool = False) -> None:
    pid = _find_wechat_main_pid(wechat_app)
    if pid is None:
        # A matched LLDB callback can kill the main process before this
        # cleanup hook runs. Reap any remaining helpers belonging to this
        # disposable bundle so they cannot keep the profile open.
        remaining = _find_wechat_bundle_pids(wechat_app)
        if not remaining:
            return
        subprocess.run(["/bin/kill", "-TERM", *(str(value) for value in remaining)], capture_output=True, text=True, check=False)
        deadline = time.monotonic() + min(timeout, 10)
        while time.monotonic() < deadline:
            remaining = _find_wechat_bundle_pids(wechat_app)
            if not remaining:
                return
            time.sleep(0.25)
        remaining = _find_wechat_bundle_pids(wechat_app)
        if remaining:
            subprocess.run(["/bin/kill", "-KILL", *(str(value) for value in remaining)], capture_output=True, text=True, check=False)
        return
    if wechat_app == DEFAULT_WECHAT_APP:
        try:
            subprocess.run(
                ["/usr/bin/osascript", "-e", 'tell application id "com.tencent.xinWeChat" to quit'],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # An ad-hoc in-place build can stop servicing AppleEvents while its
            # login window is open.  Fall through to the bounded SIGTERM path
            # instead of blocking restoration of the Tencent-signed backup.
            pass
    else:
        subprocess.run(["/bin/kill", "-TERM", str(pid)], capture_output=True, text=True, check=False)
    graceful_deadline = time.monotonic() + min(timeout, 15)
    while time.monotonic() < graceful_deadline:
        if _find_wechat_main_pid(wechat_app) is None:
            break
        time.sleep(0.25)

    # WeChat can ignore the AppleEvent when a secondary window is busy.  A
    # normal SIGTERM is still a controlled application shutdown and is safer
    # than signing while any process has the bundle open.
    current_pid = _find_wechat_main_pid(wechat_app)
    if current_pid:
        subprocess.run(["/bin/kill", "-TERM", str(current_pid)], capture_output=True, text=True, check=False)
    deadline = time.monotonic() + max(5, timeout - 15)
    while time.monotonic() < deadline:
        if _find_wechat_main_pid(wechat_app) is None:
            break
        time.sleep(0.25)
    if _find_wechat_main_pid(wechat_app) is not None:
        if not force_for_restore:
            raise MacOSDBKeyCaptureFailure("wechat_still_running", "微信未能正常退出，请手动退出微信后重试")
        # LLDB/debugserver can leave the temporary process stopped.  SIGTERM is
        # then only pending and cannot complete before restoration.  This
        # force path is reserved for restoring the verified official bundle,
        # and targets only PIDs whose executable lives inside this exact app.
        remaining_main = _find_wechat_main_pid(wechat_app)
        if remaining_main:
            subprocess.run(["/bin/kill", "-CONT", str(remaining_main)], capture_output=True, text=True, check=False)
            subprocess.run(["/bin/kill", "-KILL", str(remaining_main)], capture_output=True, text=True, check=False)
        forced_deadline = time.monotonic() + 5
        while time.monotonic() < forced_deadline:
            if _find_wechat_main_pid(wechat_app) is None:
                break
            time.sleep(0.25)
        if _find_wechat_main_pid(wechat_app) is not None:
            raise MacOSDBKeyCaptureFailure("wechat_force_stop_failed", "无法结束临时调试微信，已停止替换应用")

    helper_deadline = time.monotonic() + 10
    while time.monotonic() < helper_deadline:
        remaining = _find_wechat_bundle_pids(wechat_app)
        if not remaining:
            return
        time.sleep(0.25)
    remaining = _find_wechat_bundle_pids(wechat_app)
    if remaining:
        subprocess.run(["/bin/kill", "-TERM", *(str(pid) for pid in remaining)], capture_output=True, text=True, check=False)
        final_deadline = time.monotonic() + 5
        while time.monotonic() < final_deadline:
            remaining = _find_wechat_bundle_pids(wechat_app)
            if not remaining:
                return
            time.sleep(0.25)
        remaining = _find_wechat_bundle_pids(wechat_app)
        if remaining:
            subprocess.run(["/bin/kill", "-KILL", *(str(pid) for pid in remaining)], capture_output=True, text=True, check=False)


def _launch_wechat(
    wechat_app: Path,
    timeout: float = 45,
    *,
    isolated_home: Path | None = None,
) -> int:
    if isolated_home is None:
        _run(["/usr/bin/open", "-n", str(wechat_app)], timeout=15)
    else:
        # An ad-hoc build is intentionally not allowed to read Tencent's
        # protected app container.  Launch the disposable copy with a private
        # Foundation home instead.  This gives WeChat a working login UI while
        # keeping the user's normal account data completely out of scope.
        isolated_home.mkdir(parents=True, exist_ok=True)
        os.chmod(isolated_home, 0o700)
        temp_root = isolated_home / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        os.chmod(temp_root, 0o700)
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(isolated_home),
                "CFFIXED_USER_HOME": str(isolated_home),
                "TMPDIR": f"{temp_root}{os.sep}",
            }
        )
        try:
            subprocess.Popen(
                [str(wechat_app / "Contents/MacOS/WeChat")],
                cwd=str(isolated_home),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise MacOSDBKeyCaptureFailure(
                "wechat_launch_failed",
                f"未能启动隔离微信副本: {wechat_app}",
            ) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = _find_wechat_main_pid(wechat_app)
        if pid:
            time.sleep(2)
            stable_pid = _find_wechat_main_pid(wechat_app)
            if stable_pid:
                return stable_pid
        time.sleep(0.25)
    raise MacOSDBKeyCaptureFailure("wechat_launch_failed", f"未能启动微信副本: {wechat_app}")


def _has_compatible_debug_entitlements(wechat_app: Path) -> bool:
    # Tencent's app group and sandbox container are valid only for Tencent's
    # Developer ID.  Preserving any of those claims on an ad-hoc signature
    # produces a window that is visible but whose login controls do not work.
    # The outer app and the WeChatAppEx login/verification helper must both be
    # entitlement-free.  Otherwise the QR window appears, but WeChatAppEx dies
    # in libsecinit before it can display the phone-confirmation/code screen.
    for target in (wechat_app, wechat_app / DEBUG_LOGIN_HELPER):
        if not target.exists():
            return False
        result = _run(["/usr/bin/codesign", "-d", "--entitlements", ":-", str(target)], check=False)
        output = f"{result.stdout}\n{result.stderr}"
        if "<key>" in output:
            return False
    return True


def _has_compatible_in_place_signature(wechat_app: Path) -> bool:
    """Allow LLDB without removing permissions required by WeChat 4.1.12.

    The installed build is sandboxed. Dropping the outer bundle's original
    entitlements lets the process start, but it exits immediately after its
    app-group/container initialization. Only the outer executable is signed
    ad-hoc; its original permissions are retained and the login helper keeps
    its untouched Tencent signature.
    """

    outer_entitlements = _run(
        ["/usr/bin/codesign", "-d", "--entitlements", ":-", str(wechat_app)],
        check=False,
    )
    entitlement_output = f"{outer_entitlements.stdout}\n{outer_entitlements.stderr}"
    required_entitlements = (
        "<key>com.apple.application-identifier</key>",
        "<string>5A4RE8SF68.com.tencent.xinWeChat</string>",
        "<key>com.apple.security.app-sandbox</key>",
        "<key>com.apple.security.application-groups</key>",
        "<key>com.apple.security.network.client</key>",
    )
    if any(value not in entitlement_output for value in required_entitlements):
        return False

    helper = wechat_app / DEBUG_LOGIN_HELPER
    if not helper.exists():
        return False
    helper_signature = inspect_wechat_signature(helper)
    return bool(
        helper_signature.get("valid")
        and not helper_signature.get("ad_hoc")
        and helper_signature.get("team_identifier") == "5A4RE8SF68"
        and helper_signature.get("identifier") == "com.tencent.flue.WeChatAppEx"
    )


def _debug_copy_path(wechat_app: Path, debug_root: Path) -> Path:
    version, build = _wechat_version(wechat_app)
    return debug_root.expanduser() / f"WeChat-{version}-{build}-Debug.app"


def _has_debug_copy_marker(wechat_app: Path) -> bool:
    try:
        info = plistlib.loads((wechat_app / "Contents/Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return False
    marked = bool(
        info.get("WeDataDebugCopy") is True
        and info.get("CFBundleDisplayName") == DEBUG_COPY_DISPLAY_NAME
        and info.get("CFBundleName") == DEBUG_COPY_DISPLAY_NAME
    )
    if not marked:
        return False
    for strings_path in (wechat_app / "Contents/Resources").glob("*.lproj/InfoPlist.strings"):
        try:
            localized = plistlib.loads(strings_path.read_bytes())
        except (OSError, plistlib.InvalidFileException):
            return False
        if (
            localized.get("CFBundleDisplayName") != DEBUG_COPY_DISPLAY_NAME
            or localized.get("CFBundleName") != DEBUG_COPY_DISPLAY_NAME
        ):
            return False
    return True


def _mark_debug_copy(wechat_app: Path) -> None:
    info_path = wechat_app / "Contents/Info.plist"
    try:
        info = plistlib.loads(info_path.read_bytes())
        info["CFBundleDisplayName"] = DEBUG_COPY_DISPLAY_NAME
        info["CFBundleName"] = DEBUG_COPY_DISPLAY_NAME
        info["WeDataDebugCopy"] = True
        info_path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY, sort_keys=False))
        for strings_path in (wechat_app / "Contents/Resources").glob("*.lproj/InfoPlist.strings"):
            try:
                localized = plistlib.loads(strings_path.read_bytes())
            except plistlib.InvalidFileException:
                # Tencent ships localized InfoPlist.strings in the legacy
                # OpenStep format.  plistlib cannot parse it, but macOS plutil
                # can safely normalize it before the disposable copy is signed.
                _run(["/usr/bin/plutil", "-convert", "binary1", str(strings_path)])
                localized = plistlib.loads(strings_path.read_bytes())
            localized["CFBundleDisplayName"] = DEBUG_COPY_DISPLAY_NAME
            localized["CFBundleName"] = DEBUG_COPY_DISPLAY_NAME
            strings_path.write_bytes(plistlib.dumps(localized, fmt=plistlib.FMT_BINARY, sort_keys=False))
    except (OSError, plistlib.InvalidFileException, MacOSDBKeyCaptureFailure) as exc:
        raise MacOSDBKeyCaptureFailure(
            "debug_copy_mark_failed",
            f"无法标记微信调试副本: {exc}",
        ) from exc


def _prepare_debug_copy(wechat_app: Path, backup_path: Path, debug_root: Path) -> tuple[Path, bool]:
    debug_root = debug_root.expanduser()
    debug_root.mkdir(parents=True, exist_ok=True)
    debug_app = _debug_copy_path(wechat_app, debug_root)
    if debug_app.exists():
        signature = inspect_wechat_signature(debug_app)
        if (
            signature["valid"]
            and signature["ad_hoc"]
            and not signature["hardened_runtime"]
            and _has_compatible_debug_entitlements(debug_app)
            and _has_debug_copy_marker(debug_app)
        ):
            return debug_app, False
        shutil.rmtree(debug_app)

    with tempfile.TemporaryDirectory(prefix="prepare-", dir=str(debug_root)) as temp_dir:
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        _run(["/usr/bin/ditto", "-x", "-k", str(backup_path), str(extract_root)], timeout=1800)
        extracted_app = extract_root / "WeChat.app"
        normalize_wechat_app_path(extracted_app)
        shutil.move(str(extracted_app), str(debug_app))

    # Keep the bundle identifier for application compatibility, but make this
    # disposable process visually unmistakable in the Dock and app switcher.
    _mark_debug_copy(debug_app)

    # The backup ZIP may retain the original download quarantine. The debug copy
    # is derived locally from an already verified Tencent-signed application,
    # so remove quarantine only from this disposable copy before re-signing.
    # A Tencent-owned read-only shader cache can reject xattr deletion even in
    # the copied bundle.  xattr still clears the bundle/main-executable marker,
    # which is what LaunchServices evaluates, so tolerate per-file warnings.
    _run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(debug_app)], timeout=300, check=False)
    # WeChat's post-scan confirmation UI is hosted by WeChatAppEx.  It cannot
    # initialize its original Tencent sandbox while embedded in an ad-hoc
    # parent bundle, so apply the same entitlement-free ad-hoc identity to the
    # complete disposable copy.  The official installation remains untouched.
    _run(
        [
            "/usr/bin/codesign",
            "--force",
            "--deep",
            "--sign",
            "-",
            str(debug_app),
        ],
        timeout=300,
    )
    signature = inspect_wechat_signature(debug_app)
    if (
        not signature["valid"]
        or signature["hardened_runtime"]
        or not signature["ad_hoc"]
        or not _has_compatible_debug_entitlements(debug_app)
    ):
        raise MacOSDBKeyCaptureFailure("debug_copy_sign_failed", "微信调试副本签名或 entitlement 校验失败")
    return debug_app, True


def ensure_wechat_debuggable(
    wechat_app: Path,
    backup_root: Path,
    *,
    debug_root: Path | None = None,
) -> dict[str, Any]:
    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure("official_wechat_untrusted", "正式微信不是有效的腾讯签名版本，已停止自动处理")
    backup_path, backup_created = backup_original_wechat(wechat_app, backup_root)
    debug_app, debug_created = _prepare_debug_copy(
        wechat_app,
        backup_path,
        debug_root or DEFAULT_DEBUG_ROOT,
    )
    return {
        "wechat_resigned": False,
        "wechat_modified": False,
        "official_wechat_preserved": True,
        "debug_app_path": str(debug_app),
        "debug_copy_created": debug_created,
        "backup_path": str(backup_path),
        "backup_created": backup_created,
    }


def ensure_wechat_in_place_debuggable(
    wechat_app: Path,
    backup_root: Path,
    *,
    before_resign: Any | None = None,
) -> dict[str, Any]:
    """Temporarily ad-hoc sign WeChat at its original application path.

    WeChat 4.1.12 exits immediately when an ad-hoc copy outside
    ``/Applications/WeChat.app`` tries to use Tencent's normal container.  The
    upstream wcdb-key-tool therefore signs the installed path in place.  Keep
    that mutation recoverable by requiring a verified Tencent backup first and
    restoring it after capture, cancellation, or launch failure.
    """

    signature = inspect_wechat_signature(wechat_app)
    if not _is_tencent_official_signature(signature):
        raise MacOSDBKeyCaptureFailure(
            "wechat_signature_untrusted",
            "当前 /Applications/WeChat.app 不是有效的腾讯正式签名版本，已停止临时重签。",
            wechat_modified=bool(signature.get("ad_hoc")),
        )
    if not os.access(wechat_app, os.W_OK) or not os.access(wechat_app.parent, os.W_OK):
        raise MacOSDBKeyCaptureFailure(
            "in_place_restore_permissions_unsafe",
            "当前用户不能直接写入微信及其安装目录；为保证异常退出后无需再次授权也能恢复原版，已停止临时重签。",
        )

    backup_path, backup_created = backup_original_wechat(wechat_app, backup_root)
    backup_verification = verify_original_wechat_backup(
        backup_path,
        expected_version=_wechat_version(wechat_app),
    )
    original_cdhash = str(signature.get("cdhash") or "").lower()
    backup_cdhash = str(backup_verification.get("cdhash") or "").lower()
    if original_cdhash and backup_cdhash != original_cdhash:
        raise MacOSDBKeyCaptureFailure(
            "official_backup_identity_mismatch",
            "所选目录中的原版备份虽有腾讯签名，但与当前安装的微信不是同一构建，已停止临时重签。",
        )

    recovery = {
        "wechat_app_path": str(wechat_app),
        "backup_path": str(backup_path),
        "backup_created": backup_created,
        "version": backup_verification["version"],
        "build": backup_verification["build"],
        "official_cdhash": backup_cdhash,
    }
    if before_resign is not None:
        before_resign(dict(recovery))

    try:
        _quit_wechat(wechat_app)
        staged_app = _prepare_local_restore_staging(
            wechat_app,
            expected_version=(str(recovery["version"]), str(recovery["build"])),
            expected_cdhash=str(recovery["official_cdhash"]),
        )
        # Sign the same-volume APFS clone, not the application path that was
        # just used by LaunchServices.  Newer macOS releases can transiently
        # deny signature replacement on that recently exited path even when
        # it is writable.  The atomic exchange below installs the verified
        # debug clone while moving the untouched official bundle into the
        # recovery slot.
        sign_command = [
            "/usr/bin/codesign",
            "--force",
            "--preserve-metadata=entitlements",
            "--sign",
            "-",
            str(staged_app),
        ]
        try:
            _run(sign_command, timeout=300)
        except MacOSDBKeyCaptureFailure:
            # App Store / managed installations can be root-owned.  Match the
            # upstream prerequisite while keeping the exact target quoted.
            _run_as_administrator(shlex.join(sign_command), timeout=345)
        signature = inspect_wechat_signature(staged_app)
        if (
            not signature.get("valid")
            or not signature.get("ad_hoc")
            or signature.get("hardened_runtime")
            or not _has_compatible_in_place_signature(staged_app)
        ):
            raise MacOSDBKeyCaptureFailure(
                "in_place_sign_failed",
                "临时调试签名校验失败。",
                requires_wechat_resign=True,
                wechat_modified=True,
            )
        _atomic_swap_paths(wechat_app, staged_app)
        installed_signature = inspect_wechat_signature(wechat_app)
        if (
            not installed_signature.get("valid")
            or not installed_signature.get("ad_hoc")
            or installed_signature.get("hardened_runtime")
            or not _has_compatible_in_place_signature(wechat_app)
        ):
            raise MacOSDBKeyCaptureFailure(
                "in_place_swap_verify_failed",
                "临时微信原子安装后的签名校验失败。",
                requires_wechat_resign=True,
                wechat_modified=True,
            )
    except Exception as capture_error:
        try:
            restore_official_wechat_if_needed(
                wechat_app,
                backup_path,
                expected_version=(str(recovery["version"]), str(recovery["build"])),
                expected_cdhash=str(recovery["official_cdhash"]),
            )
        except Exception as restore_error:
            raise MacOSDBKeyCaptureFailure(
                "official_restore_failed",
                f"临时重签失败，且自动恢复腾讯原版微信失败: {restore_error}",
                requires_wechat_resign=True,
                wechat_modified=True,
            ) from restore_error
        raise capture_error

    return {
        "wechat_resigned": True,
        "wechat_modified": True,
        "official_wechat_preserved": False,
        "debug_app_path": str(wechat_app),
        "debug_copy_created": False,
        "debug_in_place": True,
        "backup_path": str(backup_path),
        "backup_created": backup_created,
        "backup_verified": True,
        "official_cdhash": backup_cdhash,
    }


def restore_official_wechat_if_needed(
    wechat_app: Path,
    backup_path: Path,
    *,
    work_root: Path | None = None,
    expected_version: tuple[str, str] | None = None,
    expected_cdhash: str | None = None,
) -> dict[str, Any]:
    """Verify the normal Tencent build and restore it atomically when needed."""

    staged = _local_restore_staging_path(wechat_app)
    current = inspect_wechat_signature(wechat_app)
    if _is_tencent_official_signature(current):
        # Recovery may have been interrupted just after the atomic exchange.
        # At that point the installed path is already official and ``staged``
        # contains only WCDA's displaced ad-hoc bundle.
        _remove_local_restore_staging(staged)
        return {"official_wechat_verified": True, "official_wechat_restored": False}

    use_local_staging = False
    if os.path.lexists(staged):
        if staged.is_symlink() or not staged.is_dir():
            raise MacOSDBKeyCaptureFailure(
                "local_restore_path_unsafe",
                f"原版微信保护路径类型异常，已停止自动覆盖: {staged}",
                wechat_modified=True,
            )
        try:
            staged_signature = inspect_wechat_signature(staged)
            staged_version = _wechat_version(staged)
            staged_cdhash = str(staged_signature.get("cdhash") or "").lower()
            use_local_staging = bool(
                _is_tencent_official_signature(staged_signature)
                and (expected_version is None or staged_version == expected_version)
                and (not expected_cdhash or staged_cdhash == str(expected_cdhash).lower())
            )
        except (OSError, plistlib.InvalidFileException, MacOSDBKeyCaptureFailure):
            use_local_staging = False
        if not use_local_staging:
            _remove_local_restore_staging(staged)

    if not use_local_staging:
        restore_root = (work_root or DEFAULT_DEBUG_ROOT).expanduser()
        restore_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="restore-", dir=str(restore_root)) as temp_dir:
            extract_root = Path(temp_dir) / "extract"
            extract_root.mkdir()
            _run(["/usr/bin/ditto", "-x", "-k", str(backup_path), str(extract_root)], timeout=1800)
            extracted_app = normalize_wechat_app_path(extract_root / "WeChat.app")
            restored_signature = inspect_wechat_signature(extracted_app)
            if not _is_tencent_official_signature(restored_signature):
                raise MacOSDBKeyCaptureFailure("official_backup_untrusted", "所选目录中的微信原版备份签名校验失败，已停止恢复")
            restored_version = _wechat_version(extracted_app)
            if expected_version is not None and restored_version != expected_version:
                raise MacOSDBKeyCaptureFailure("official_backup_version_mismatch", "所选目录中的微信原版备份版本不匹配，已停止恢复")
            restored_cdhash = str(restored_signature.get("cdhash") or "").lower()
            if expected_cdhash and restored_cdhash != str(expected_cdhash).lower():
                raise MacOSDBKeyCaptureFailure("official_backup_identity_mismatch", "所选目录中的微信原版备份身份不匹配，已停止恢复")
            try:
                _run(["/usr/bin/ditto", str(extracted_app), str(staged)], timeout=1800)
            except Exception:
                if os.path.lexists(staged):
                    _remove_local_restore_staging(staged)
                raise
        staged_signature = inspect_wechat_signature(staged)
        if not _is_tencent_official_signature(staged_signature):
            _remove_local_restore_staging(staged)
            raise MacOSDBKeyCaptureFailure("official_restore_staging_invalid", "恢复暂存的腾讯微信签名校验失败")

    _quit_wechat(wechat_app, force_for_restore=True)
    swapped = False
    try:
        _atomic_swap_paths(wechat_app, staged)
        swapped = True
        installed = inspect_wechat_signature(wechat_app)
        if not _is_tencent_official_signature(installed):
            raise MacOSDBKeyCaptureFailure("official_restore_verify_failed", "恢复后的腾讯微信签名校验失败")
    except Exception:
        if swapped:
            try:
                _atomic_swap_paths(wechat_app, staged)
                swapped = False
            except Exception as rollback_error:
                raise MacOSDBKeyCaptureFailure(
                    "official_restore_rollback_failed",
                    f"微信原版恢复校验失败，且无法回滚交换: {rollback_error}",
                    wechat_modified=True,
                ) from rollback_error
        if os.path.lexists(staged):
            _remove_local_restore_staging(staged)
        raise
    _remove_local_restore_staging(staged)

    return {"official_wechat_verified": True, "official_wechat_restored": True}


def _atomic_swap_paths(first: Path, second: Path) -> None:
    """Atomically exchange two same-volume paths using renameatx_np(2)."""

    library = ctypes.CDLL(None, use_errno=True)
    renameatx_np = getattr(library, "renameatx_np", None)
    if renameatx_np is None:
        raise MacOSDBKeyCaptureFailure("atomic_restore_unavailable", "当前 macOS 不支持微信原版原子恢复")
    renameatx_np.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameatx_np.restype = ctypes.c_int
    at_fdcwd = -2
    rename_swap = 0x00000002
    if renameatx_np(at_fdcwd, os.fsencode(first), at_fdcwd, os.fsencode(second), rename_swap) != 0:
        error_number = ctypes.get_errno()
        raise MacOSDBKeyCaptureFailure(
            "atomic_restore_failed",
            f"无法原子交换微信原版与临时版本: {os.strerror(error_number)}",
            wechat_modified=True,
        )


def _parse_passphrase(output: str) -> str:
    values: list[str] = []
    for line in str(output or "").splitlines():
        match = _MEMORY_LINE_RE.match(line)
        if match:
            values.extend(re.findall(r"0x([0-9a-fA-F]{2})", match.group(1)))
    candidate = "".join(values[:32]).lower()
    return candidate if _PASSPHRASE_RE.fullmatch(candidate) else ""


def _build_lldb_capture_command(script_path: Path, timeout: int) -> str:
    """Keep LLDB stdin open, but stop the keeper as soon as LLDB exits.

    The upstream wcdb-key-tool reads LLDB stdout continuously and terminates
    the pipeline immediately after parsing 32 bytes.  AppleScript's
    ``do shell script`` only returns stdout after the privileged command exits,
    so a plain ``(cat; sleep) | lldb`` makes a successful capture appear stuck
    until the sleep finishes.  This wrapper preserves the upstream stdin
    behaviour while explicitly killing the producer when LLDB detaches.
    """

    script_arg = shlex.quote(str(script_path))
    keepalive = max(1, int(timeout))
    shell = (
        "capture_dir=$(/usr/bin/mktemp -d /tmp/wedata-lldb.XXXXXX)\n"
        'capture_fifo="$capture_dir/stdin"\n'
        'producer_pid=""\n'
        'lldb_pid=""\n'
        'watchdog_pid=""\n'
        "cleanup() {\n"
        '  if [ -n "$producer_pid" ]; then /bin/kill "$producer_pid" 2>/dev/null || true; fi\n'
        '  if [ -n "$watchdog_pid" ]; then /bin/kill "$watchdog_pid" 2>/dev/null || true; fi\n'
        '  if [ -n "$lldb_pid" ]; then /bin/kill "$lldb_pid" 2>/dev/null || true; fi\n'
        '  /bin/rm -rf "$capture_dir"\n'
        "}\n"
        "trap cleanup EXIT HUP INT TERM\n"
        '/usr/bin/mkfifo "$capture_fifo"\n'
        # ``exec`` makes the recorded producer PID become the sleep process
        # after cat finishes, so SIGTERM actually ends the keepalive instead
        # of leaving a child sleep behind while the shell waits for it.
        f"( /bin/cat {script_arg}; exec /bin/sleep {keepalive} ) > \"$capture_fifo\" &\n"
        "producer_pid=$!\n"
        '/usr/bin/env TERM=dumb /usr/bin/lldb < "$capture_fifo" 2>&1 &\n'
        "lldb_pid=$!\n"
        f'( /bin/sleep {keepalive}; /bin/kill -TERM "$lldb_pid" 2>/dev/null || true ) &\n'
        "watchdog_pid=$!\n"
        'wait "$lldb_pid"\n'
        "lldb_status=$?\n"
        'lldb_pid=""\n'
        '/bin/kill "$watchdog_pid" 2>/dev/null || true\n'
        'wait "$watchdog_pid" 2>/dev/null || true\n'
        'watchdog_pid=""\n'
        '/bin/kill "$producer_pid" 2>/dev/null || true\n'
        'wait "$producer_pid" 2>/dev/null || true\n'
        'producer_pid=""\n'
        'echo "WEDATA_LLDB_EXIT=$lldb_status"\n'
        # Administrator approval is the only AppleScript-level failure.  LLDB
        # diagnostics stay in stdout so the caller can report the real cause.
        "exit 0\n"
    )
    return shlex.join(["/bin/bash", "-c", shell])


def capture_passphrase_lldb(timeout: int = 240, *, pid: int | None = None) -> str:
    if shutil.which("lldb") is None:
        raise MacOSDBKeyCaptureFailure("lldb_missing", "未安装 LLDB，请先运行 xcode-select --install")
    pid = pid or _find_wechat_pid()
    if not pid:
        raise MacOSDBKeyCaptureFailure("wechat_not_running", "未找到微信进程，请先启动微信")

    is_arm = platform.machine().lower() in {"arm64", "aarch64"}
    password_register, length_register = ("x1", "x2") if is_arm else ("rsi", "rdx")
    script = (
        "settings set target.preload-symbols false\n"
        f"process attach -p {pid}\n"
        f"breakpoint set -n CCKeyDerivationPBKDF -c '${length_register} == 32'\n"
        "breakpoint command add 1\n"
        f"memory read --size 1 --count 32 --format x ${password_register}\n"
        "detach\n"
        "quit\n"
        "DONE\n"
        "process continue\n"
    )
    with tempfile.TemporaryDirectory(prefix="wedata-wxcap-") as temp_dir:
        script_path = Path(temp_dir) / "capture.lldb"
        script_path.write_text(script, encoding="utf-8")
        os.chmod(script_path, 0o600)
        command = _build_lldb_capture_command(script_path, timeout)
        output = _run_as_administrator(command, timeout=float(timeout + 45))

    passphrase = _parse_passphrase(output)
    if passphrase:
        return passphrase
    compact = " ".join(output.split())
    if "attach failed" in compact.lower() or "not allowed to attach" in compact.lower():
        raise MacOSDBKeyCaptureFailure(
            "lldb_attach_failed",
            "LLDB 无法附加微信调试副本，请确认管理员授权已完成",
        )
    raise MacOSDBKeyCaptureFailure(
        "passphrase_not_captured",
        "未捕获到 passphrase。请在捕获期间于微信中退出账号并重新登录后再试。",
        process_attached=True,
    )


def save_passphrase(passphrase: str, *, home: Path | None = None) -> Path:
    normalized = str(passphrase or "").strip().lower()
    if not _PASSPHRASE_RE.fullmatch(normalized):
        raise MacOSDBKeyCaptureFailure("invalid_passphrase", "捕获到的 passphrase 格式无效")
    target = (home or Path.home()) / PASSPHRASE_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    temp_path = target.with_suffix(".tmp")
    temp_path.write_text(json.dumps({"passphrase": normalized}, indent=2), encoding="utf-8")
    os.chmod(temp_path, 0o600)
    temp_path.replace(target)
    os.chmod(target, 0o600)
    return target


def _validate_captured_passphrase(passphrase: str, probe_db_path: str | Path | None) -> None:
    if probe_db_path is None:
        return
    database = Path(probe_db_path).expanduser()
    try:
        with database.open("rb") as handle:
            page1 = handle.read(4096)
        from .wechat_decrypt import PAGE_SIZE, _resolve_page1_key_material

        validated = (
            len(page1) >= PAGE_SIZE
            and _resolve_page1_key_material(bytes.fromhex(passphrase), page1) is not None
        )
    except (OSError, ValueError) as exc:
        raise MacOSDBKeyCaptureFailure(
            "passphrase_validation_failed",
            f"无法使用目标数据库校验捕获结果: {database}",
            process_attached=True,
        ) from exc
    if not validated:
        raise MacOSDBKeyCaptureFailure(
            "passphrase_database_mismatch",
            "已捕获登录时的 passphrase，但无法通过所选数据库校验。请确认调试微信登录的是同一账号，且使用默认微信数据路径后重试。",
            process_attached=True,
        )


def prepare_macos_passphrase_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
) -> dict[str, Any]:
    """Temporarily re-sign the default-path client and launch without LLDB."""

    from .macos_inplace_capture import prepare_in_place_capture

    return prepare_in_place_capture(wechat_install_path, backup_root=backup_root)


def cleanup_macos_passphrase_capture(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
) -> dict[str, Any]:
    """Close the temporary client and restore the Tencent-signed application."""

    from .macos_inplace_capture import cleanup_in_place_capture

    return cleanup_in_place_capture(wechat_install_path, backup_root=backup_root)


def capture_prepared_macos_passphrase(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    probe_db_path: str | Path | None = None,
    timeout: int = 240,
    save_result: bool = True,
) -> dict[str, Any]:
    """Attach after logout, capture on re-login, then restore the official app."""

    from .macos_inplace_capture import capture_prepared_in_place

    return capture_prepared_in_place(
        wechat_install_path,
        backup_root=backup_root,
        probe_db_path=probe_db_path,
        timeout=timeout,
        save_result=save_result,
    )


def preflight_prepared_macos_passphrase(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
) -> dict[str, Any]:
    """Validate capture breakpoints and detach before the user logs out."""

    from .macos_inplace_capture import preflight_prepared_in_place_capture

    return preflight_prepared_in_place_capture(wechat_install_path, backup_root=backup_root)


def capture_and_cache_macos_passphrase(
    wechat_install_path: str | Path | None,
    *,
    backup_root: Path,
    probe_db_path: str | Path | None = None,
    timeout: int = 240,
) -> dict[str, Any]:
    prepare_macos_passphrase_capture(wechat_install_path, backup_root=backup_root)
    preflight_prepared_macos_passphrase(wechat_install_path, backup_root=backup_root)
    return capture_prepared_macos_passphrase(
        wechat_install_path,
        backup_root=backup_root,
        probe_db_path=probe_db_path,
        timeout=timeout,
    )


__all__ = [
    "MacOSDBKeyCaptureFailure",
    "capture_and_cache_macos_passphrase",
    "capture_passphrase_lldb",
    "capture_prepared_macos_passphrase",
    "cleanup_macos_passphrase_capture",
    "ensure_wechat_debuggable",
    "ensure_wechat_in_place_debuggable",
    "inspect_wechat_signature",
    "normalize_wechat_app_path",
    "preflight_prepared_macos_passphrase",
    "prepare_macos_passphrase_capture",
    "restore_official_wechat_if_needed",
    "save_passphrase",
    "verify_original_wechat_backup",
]
