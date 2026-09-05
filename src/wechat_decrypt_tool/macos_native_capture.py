"""Lightweight macOS WCDB key capture helper orchestration.

This module replaces the LLDB Python frontend for the in-place capture path.
The privileged operation is reduced to a small native helper that can preflight
the PBKDF import stub and capture the 32-byte key with lower memory overhead.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .logging_config import get_logger
from .macos_db_key_capture import (
    DEFAULT_DEBUG_ROOT,
    DEFAULT_WECHAT_APP,
    MacOSDBKeyCaptureFailure,
    _PASSPHRASE_RE,
    _run,
    _run_as_administrator,
)

_STUB_HEADER = "Indirect symbols for (__TEXT,__stubs)"
_SECTION_HEADER_RE = re.compile(r"^Indirect symbols for \(([^)]+)\)")
_STUB_LINE_RE = re.compile(r"^\s*(0x[0-9a-fA-F]+)\s+\d+\s+_CCKeyDerivationPBKDF\s*$")
_SEGNAME_TEXT_RE = re.compile(r"^\s*segname\s+__TEXT\s*$")
_VMADDR_RE = re.compile(r"^\s*vmaddr\s+(0x[0-9a-fA-F]+)\s*$")
_VMMAP_TEXT_LINE_RE = re.compile(r"^__TEXT\s+([0-9a-fA-F]+)-[0-9a-fA-F]+\s+.*?\s+(\/.*)$")
_JSON_LIMIT = 128 * 1024
_HELPER_TIMEOUT_PAD = 45
_HELPER_NAME = "wcdb-native-capture"
_HELPER_SOURCE = Path(__file__).resolve().parent / "native" / "macos" / "source" / "wcdb_native_capture.c"
_TRANSACTION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_DIAGNOSTIC_COUNTERS = (
    "pbkdf_calls", "wcdb_profile_hits", "rounds2_hits", "rounds256000_hits",
    "salt_matches", "candidate_rejects", "salt_read_failures", "candidate_read_failures",
)
_DIAGNOSTIC_STAGES = frozenset({
    "initializing", "read_page1", "attach", "resolve_breakpoint", "read_breakpoint",
    "install_exception_port", "install_breakpoint", "write_ready", "waiting", "pbkdf_seen",
    "profile_matched", "rounds2_seen", "rounds256000_seen", "salt_read_failed", "salt_mismatch",
    "salt_matched", "candidate_read_failed", "candidate_rejected", "validated",
})
_NATIVE_FAILURE_MESSAGES = {
    "native_capture_failed": "原生捕获器执行失败",
    "native_invalid_arguments": "原生捕获器参数无效",
    "native_attach_failed": "原生捕获器无法附加微信进程",
    "native_image_not_found": "原生捕获器未找到微信原生模块",
    "native_breakpoint_read_failed": "原生捕获器无法读取 PBKDF 断点指令",
    "native_breakpoint_shape_mismatch": "微信 PBKDF 导入桩布局与原生捕获器不匹配",
    "native_breakpoint_install_failed": "原生捕获器无法安装硬件断点",
    "native_probe_database_unreadable": "原生捕获器无法读取数据库校验页",
    "native_exception_port_failed": "原生捕获器无法安装断点异常端口",
    "native_ready_signal_failed": "原生捕获器无法写入就绪信号",
    "native_cleanup_failed": "原生捕获器无法确认调试状态已完整恢复，必须结束当前事务",
    "native_capture_timeout": "原生捕获等待超时，未取得通过校验的账号密钥",
    "native_capture_target_exited": "微信目标进程已退出，原生捕获提前结束",
    "native_capture_interrupted": "原生捕获器收到终止信号，捕获已中断",
    "native_capture_wait_failed": "原生捕获断点监听失败，捕获提前结束",
    "native_capture_unvalidated": "原生捕获候选未通过数据库校验",
}


def _parse_capture_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept only bounded counters and fixed stages, never arbitrary helper data."""
    raw = payload.get("diagnostics")
    result: dict[str, Any] = {}
    if not isinstance(raw, dict):
        raw = {}
    for name in _DIAGNOSTIC_COUNTERS:
        value = raw.get(name)
        if type(value) is int and 0 <= value <= (1 << 64) - 1:
            result[name] = value
    if "pbkdf_calls" not in result:
        legacy_calls = payload.get("pbkdf_calls")
        if type(legacy_calls) is int and 0 <= legacy_calls <= (1 << 64) - 1:
            result["pbkdf_calls"] = legacy_calls
    stage = raw.get("last_stage")
    if isinstance(stage, str) and stage in _DIAGNOSTIC_STAGES:
        result["last_stage"] = stage
    return result


def _diagnostic_failure_message(code: str, diagnostics: dict[str, Any]) -> str:
    message = _NATIVE_FAILURE_MESSAGES[code]
    if code == "native_capture_timeout":
        if diagnostics.get("pbkdf_calls") == 0:
            message += "；未命中 PBKDF 断点"
        elif diagnostics.get("wcdb_profile_hits") == 0:
            message += "；PBKDF 调用未匹配预期 WCDB 参数"
        elif diagnostics.get("rounds256000_hits") == 0 and diagnostics.get("rounds2_hits", 0) > 0:
            message += "；只命中 2 轮派生调用，不能将单库派生密钥作为账号密钥"
        elif diagnostics.get("rounds256000_hits", 0) > 0 and diagnostics.get("salt_matches") == 0:
            message += "；账号密钥派生调用未匹配校验库的盐"
        elif diagnostics.get("candidate_rejects", 0) > 0:
            message += "；候选账号密钥未通过校验"
    if diagnostics:
        summary = ", ".join(f"{name}={value}" for name, value in diagnostics.items())
        message += f"（诊断：{summary}）"
    return message


def _resolve_wechat_dylib(wechat_app: Path) -> Path:
    candidate = wechat_app / "Contents" / "Resources" / "wechat.dylib"
    if not candidate.is_file():
        raise MacOSDBKeyCaptureFailure(
            "native_wechat_dylib_missing",
            f"找不到微信原生模块: {candidate}",
        )
    return candidate


def _parse_pbkdf_stub_address(output: str) -> int:
    in_stub_section = False
    for raw_line in str(output or "").splitlines():
        line = raw_line.rstrip()
        header = _SECTION_HEADER_RE.match(line)
        if header:
            in_stub_section = line.startswith(_STUB_HEADER)
            continue
        if not in_stub_section:
            continue
        matched = _STUB_LINE_RE.match(line)
        if matched:
            return int(matched.group(1), 16)
    raise MacOSDBKeyCaptureFailure(
        "native_pbkdf_stub_missing",
        "未能在微信 wechat.dylib 的 __TEXT,__stubs 中找到 PBKDF 导入桩。",
    )


def _resolve_pbkdf_stub_address(dylib_path: Path) -> int:
    result = _run(
        ["/usr/bin/otool", "-arch", "arm64", "-Iv", str(dylib_path)],
        timeout=60,
    )
    return _parse_pbkdf_stub_address(result.stdout)


def _resolve_text_vmaddr(dylib_path: Path) -> int:
    result = _run(
        ["/usr/bin/otool", "-arch", "arm64", "-l", str(dylib_path)],
        timeout=60,
    )
    inside_text = False
    for raw_line in str(result.stdout or "").splitlines():
        line = raw_line.rstrip()
        if _SEGNAME_TEXT_RE.match(line):
            inside_text = True
            continue
        if inside_text:
            matched = _VMADDR_RE.match(line)
            if matched:
                return int(matched.group(1), 16)
            if line.strip().startswith("segname "):
                inside_text = False
    raise MacOSDBKeyCaptureFailure(
        "native_text_vmaddr_missing",
        "未能解析 wechat.dylib 的 __TEXT 虚拟地址。",
    )


def _resolve_loaded_text_base(pid: int, dylib_path: Path) -> int:
    expected = str(dylib_path)
    deadline = time.monotonic() + 20.0
    while True:
        result = _run(
            ["/usr/bin/vmmap", str(int(pid))],
            timeout=60,
            check=False,
        )
        output = f"{result.stdout}\n{result.stderr}"
        for raw_line in output.splitlines():
            matched = _VMMAP_TEXT_LINE_RE.match(raw_line)
            if not matched:
                continue
            if matched.group(2).strip() == expected:
                return int(matched.group(1), 16)
        if time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    raise MacOSDBKeyCaptureFailure(
        "native_vmmap_image_missing",
        "vmmap 中没有找到已加载的 wechat.dylib __TEXT 映像。",
    )


def _resolve_runtime_breakpoint_address(pid: int, dylib_path: Path, stub_file_address: int) -> int:
    text_base = _resolve_loaded_text_base(pid, dylib_path)
    text_vmaddr = _resolve_text_vmaddr(dylib_path)
    return text_base + (int(stub_file_address) - text_vmaddr) + 8


def _native_helper_path(debug_root: Path) -> Path:
    return debug_root.expanduser() / "native" / _HELPER_NAME


def _source_digest() -> str:
    try:
        return hashlib.sha256(_HELPER_SOURCE.read_bytes()).hexdigest()
    except OSError as exc:
        raise MacOSDBKeyCaptureFailure(
            "native_helper_source_missing",
            f"找不到原生捕获器源码: {_HELPER_SOURCE}",
        ) from exc


def ensure_native_capture_helper(*, debug_root: Path = DEFAULT_DEBUG_ROOT) -> Path:
    helper_path = _native_helper_path(debug_root)
    digest_path = helper_path.with_suffix(".sha256")
    expected_digest = _source_digest()
    try:
        if (
            helper_path.is_file()
            and os.access(helper_path, os.X_OK)
            and digest_path.read_text(encoding="utf-8").strip() == expected_digest
        ):
            return helper_path
    except OSError:
        pass

    helper_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(helper_path.parent, 0o700)
    with tempfile.TemporaryDirectory(prefix="wcdb-native-build-", dir=str(helper_path.parent)) as temp_dir:
        staged = Path(temp_dir) / _HELPER_NAME
        _run(
            [
                "/usr/bin/xcrun",
                "clang",
                "-arch",
                "arm64",
                "-O2",
                "-Wall",
                "-Wextra",
                "-std=c11",
                "-o",
                str(staged),
                str(_HELPER_SOURCE),
            ],
            timeout=300,
        )
        os.chmod(staged, 0o700)
        staged.replace(helper_path)
    helper_path.chmod(0o700)
    digest_path.write_text(expected_digest, encoding="utf-8")
    os.chmod(digest_path, 0o600)
    return helper_path


def _run_helper(
    *,
    mode: str,
    pid: int,
    wechat_app: Path,
    debug_root: Path,
    stub_file_address: int | None = None,
    probe_db_path: Path | None = None,
    probe_page1_path: Path | None = None,
    ready_file: Path | None = None,
    transaction_id: str | None = None,
    timeout: int = 240,
) -> dict[str, Any]:
    if pid <= 0:
        raise MacOSDBKeyCaptureFailure("native_capture_invalid_pid", "微信调试进程 PID 无效")
    if transaction_id and (not isinstance(transaction_id, str) or not _TRANSACTION_ID_RE.fullmatch(transaction_id)):
        raise MacOSDBKeyCaptureFailure("native_capture_invalid_transaction", "原生捕获事务标识无效")

    helper_path = ensure_native_capture_helper(debug_root=debug_root)
    dylib = _resolve_wechat_dylib(wechat_app)
    stub_address = int(stub_file_address or _resolve_pbkdf_stub_address(dylib))
    breakpoint_address = _resolve_runtime_breakpoint_address(pid, dylib, stub_address)
    if stub_address <= 0:
        raise MacOSDBKeyCaptureFailure("native_capture_invalid_stub", "PBKDF 导入桩地址无效")
    if breakpoint_address <= 0:
        raise MacOSDBKeyCaptureFailure("native_capture_invalid_breakpoint", "PBKDF 运行时断点地址无效")

    command = [
        str(helper_path),
        "--mode",
        mode,
        "--pid",
        str(pid),
        "--stub-file-address",
        hex(stub_address),
        "--breakpoint-address",
        hex(breakpoint_address),
    ]
    if probe_page1_path is not None:
        command.extend(["--page1-file", str(probe_page1_path.expanduser())])
    elif probe_db_path is not None:
        command.extend(["--database", str(probe_db_path.expanduser())])
    if mode == "capture":
        command.extend(["--timeout", str(max(int(timeout), 30))])
    if ready_file is not None:
        command.extend(["--ready-file", str(ready_file.expanduser())])
    if transaction_id:
        command.extend(["--transaction-id", transaction_id])

    try:
        raw_output = _run_as_administrator(
            shlex.join(command),
            timeout=max(int(timeout), 30) + _HELPER_TIMEOUT_PAD,
        ).strip()
    except MacOSDBKeyCaptureFailure as exc:
        embedded = _extract_embedded_json(str(exc))
        if embedded is None:
            # osascript can report the helper's termination without JSON.  Do
            # not forward stderr: it may contain a partial secret-bearing result.
            if exc.code == "administrator_cancelled":
                raise MacOSDBKeyCaptureFailure("administrator_cancelled", "已取消管理员授权") from None
            if exc.code == "administrator_timeout":
                raise MacOSDBKeyCaptureFailure("administrator_timeout", "管理员授权或原生捕获等待超时") from None
            if re.search(r"(?<!\d)1009(?!\d)|\bSIG(?:KILL|TERM|INT)\b|\bkilled(?::\s*9)?\b|\bterminated\b", str(exc), re.I):
                raise MacOSDBKeyCaptureFailure(
                    "native_capture_helper_terminated", "原生捕获器被系统终止，捕获提前结束",
                ) from None
            raise MacOSDBKeyCaptureFailure("administrator_failed", "管理员调用原生捕获器失败，未返回可解析结果") from None
        raw_output = embedded
    if not raw_output:
        raise MacOSDBKeyCaptureFailure("native_capture_empty", "原生捕获器没有返回结果")
    if len(raw_output) > _JSON_LIMIT:
        raise MacOSDBKeyCaptureFailure("native_capture_oversized", "原生捕获器返回异常长输出，已拒绝解析")
    try:
        payload = json.loads(raw_output)
    except ValueError as exc:
        raise MacOSDBKeyCaptureFailure("native_capture_non_json", "原生捕获器返回了无效结果") from exc
    if not isinstance(payload, dict):
        raise MacOSDBKeyCaptureFailure("native_capture_invalid_payload", "原生捕获器返回结构无效")

    diagnostics = _parse_capture_diagnostics(payload)
    status = str(payload.get("status") or "").strip().lower()
    if status != "ok":
        raw_code = payload.get("code")
        code = raw_code if isinstance(raw_code, str) and raw_code in _NATIVE_FAILURE_MESSAGES else "native_capture_failed"
        get_logger(__name__).warning("native capture failed: code=%s diagnostics=%s", code, diagnostics)
        message = _diagnostic_failure_message(code, diagnostics)
        raise MacOSDBKeyCaptureFailure(code, message, process_attached=True)
    if str(payload.get("mode") or "").strip().lower() != mode:
        raise MacOSDBKeyCaptureFailure("native_capture_mode_mismatch", "原生捕获器返回模式不匹配")
    if type(payload.get("pid")) is not int or payload.get("pid") != pid:
        raise MacOSDBKeyCaptureFailure("native_capture_pid_mismatch", "原生捕获器返回的微信进程不匹配")
    if type(payload.get("stub_file_address")) is not int or payload.get("stub_file_address") != stub_address:
        raise MacOSDBKeyCaptureFailure("native_capture_stub_mismatch", "原生捕获器返回的断点地址不匹配")
    if str(payload.get("method") or "") != "macos_native_mach":
        raise MacOSDBKeyCaptureFailure("native_capture_method_mismatch", "原生捕获器返回的方法标识无效")
    # Success callers need the key, but must not inherit arbitrary helper fields
    # that might later be copied into application state or diagnostics.
    result = {name: payload[name] for name in ("status", "mode", "method", "pid", "stub_file_address")}
    result["diagnostics"] = diagnostics
    if "pbkdf_calls" in diagnostics:
        result["pbkdf_calls"] = diagnostics["pbkdf_calls"]
    if mode == "capture":
        result["validated"] = payload.get("validated") is True
        result["db_key"] = payload.get("db_key")
    return result


def _extract_embedded_json(message: str) -> str | None:
    raw = str(message or "").strip()
    if len(raw) > _JSON_LIMIT:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = raw[start : end + 1].strip()
    try:
        payload = json.loads(candidate)
    except ValueError:
        return None
    return candidate if isinstance(payload, dict) else None


def preflight_native_wcdb_capture(
    *,
    pid: int,
    wechat_app: Path = DEFAULT_WECHAT_APP,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    payload = _run_helper(
        mode="preflight",
        pid=pid,
        wechat_app=wechat_app,
        debug_root=debug_root,
        timeout=90,
    )
    payload.pop("db_key", None)
    payload.pop("validated", None)
    return payload


def capture_native_wcdb_key(
    *,
    pid: int,
    wechat_app: Path = DEFAULT_WECHAT_APP,
    probe_db_path: Path,
    probe_page1_path: Path | None = None,
    ready_file: Path | None = None,
    transaction_id: str | None = None,
    timeout: int = 240,
    debug_root: Path = DEFAULT_DEBUG_ROOT,
) -> dict[str, Any]:
    payload = _run_helper(
        mode="capture",
        pid=pid,
        wechat_app=wechat_app,
        debug_root=debug_root,
        probe_db_path=probe_db_path,
        probe_page1_path=probe_page1_path,
        ready_file=ready_file,
        transaction_id=transaction_id,
        timeout=timeout,
    )
    if not bool(payload.get("validated")):
        raise MacOSDBKeyCaptureFailure(
            "native_capture_unvalidated",
            "原生捕获器拿到了候选密钥，但没有通过数据库校验。",
            process_attached=True,
        )
    key = str(payload.get("db_key") or "").strip().lower()
    if not _PASSPHRASE_RE.fullmatch(key):
        raise MacOSDBKeyCaptureFailure(
            "native_capture_invalid_key",
            "原生捕获器返回的数据库密钥格式无效。",
            process_attached=True,
        )
    payload["db_key"] = key
    return payload


__all__ = [
    "_parse_pbkdf_stub_address",
    "capture_native_wcdb_key",
    "ensure_native_capture_helper",
    "preflight_native_wcdb_capture",
]
