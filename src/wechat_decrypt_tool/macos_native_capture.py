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
    timeout: int = 240,
) -> dict[str, Any]:
    if pid <= 0:
        raise MacOSDBKeyCaptureFailure("native_capture_invalid_pid", "微信调试进程 PID 无效")

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

    try:
        raw_output = _run_as_administrator(
            shlex.join(command),
            timeout=max(int(timeout), 30) + _HELPER_TIMEOUT_PAD,
        ).strip()
    except MacOSDBKeyCaptureFailure as exc:
        embedded = _extract_embedded_json(str(exc))
        if embedded is None:
            raise
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

    status = str(payload.get("status") or "").strip().lower()
    if status != "ok":
        code = str(payload.get("code") or "native_capture_failed").strip() or "native_capture_failed"
        message = str(payload.get("message") or "原生捕获器执行失败").strip() or "原生捕获器执行失败"
        raise MacOSDBKeyCaptureFailure(code, message, process_attached=True)
    if str(payload.get("mode") or "").strip().lower() != mode:
        raise MacOSDBKeyCaptureFailure("native_capture_mode_mismatch", "原生捕获器返回模式不匹配")
    if int(payload.get("pid") or 0) != pid:
        raise MacOSDBKeyCaptureFailure("native_capture_pid_mismatch", "原生捕获器返回的微信进程不匹配")
    if int(payload.get("stub_file_address") or 0) != stub_address:
        raise MacOSDBKeyCaptureFailure("native_capture_stub_mismatch", "原生捕获器返回的断点地址不匹配")
    if str(payload.get("method") or "") != "macos_native_mach":
        raise MacOSDBKeyCaptureFailure("native_capture_method_mismatch", "原生捕获器返回的方法标识无效")
    return payload


def _extract_embedded_json(message: str) -> str | None:
    raw = str(message or "").strip()
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
