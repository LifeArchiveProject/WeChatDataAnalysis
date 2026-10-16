#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import zipfile
from pathlib import Path
from typing import Iterable


SENSITIVE_ENTRY_NAMES = {
    ".env",
    "account_keys.json",
    "desktop-settings.json",
    "preferences.json",
    "wechat-passphrase.json",
}
SENSITIVE_SUFFIXES = {".db", ".log"}
PERSONAL_PATH_PATTERN = re.compile(rb"/(?:Users|home)/[^/\x00\r\n\t ]+/")
MACHO_MAGICS = {
    b"\xca\xfe\xba\xbe",
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xfe\xed\xfa\xce",
}


def _entry_is_sensitive(name: str) -> bool:
    path = Path(name)
    return path.name.lower() in SENSITIVE_ENTRY_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES


def _personal_markers() -> tuple[bytes, ...]:
    markers: set[bytes] = set()
    home = str(Path.home())
    if home not in {"", "/"}:
        markers.add(home.encode("utf-8"))
    username = os.environ.get("USER", "").strip()
    if len(username) >= 3:
        markers.add(f"/{username}/".encode("utf-8"))
    return tuple(sorted(markers))


def _content_violations(label: str, payload: bytes) -> list[str]:
    violations: list[str] = []
    # Prebuilt extension modules commonly retain harmless CI paths such as
    # /Users/runner. We still scan every byte for this builder's exact home and
    # username, while applying the generic home-directory rule to non-Mach-O
    # code and resources where a path would indicate accidental bundling.
    is_macho = payload[:4] in MACHO_MAGICS
    if not is_macho and PERSONAL_PATH_PATTERN.search(payload):
        violations.append(f"{label}: 包含用户主目录绝对路径")
    for marker in _personal_markers():
        if marker in payload:
            violations.append(f"{label}: 包含当前构建用户信息")
            break
    return violations


def audit_directory(root: Path) -> list[str]:
    violations: list[str] = []
    if not root.is_dir():
        return [f"目录不存在: {root}"]
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if _entry_is_sensitive(relative):
            violations.append(f"{relative}: 不应打包运行时数据或私密文件")
            continue
        try:
            violations.extend(_content_violations(relative, path.read_bytes()))
        except OSError as exc:
            violations.append(f"{relative}: 无法审计: {exc}")
    return violations


def audit_zip(path: Path) -> list[str]:
    violations: list[str] = []
    if not path.is_file():
        return [f"安装包不存在: {path}"]
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if _entry_is_sensitive(info.filename):
                    violations.append(f"{info.filename}: 不应打包运行时数据或私密文件")
    except (OSError, zipfile.BadZipFile) as exc:
        violations.append(f"无法读取安装包 {path}: {exc}")
    return violations


def run_audit(paths: Iterable[Path]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        if path.is_dir():
            violations.extend(audit_directory(path))
        elif path.suffix.lower() == ".zip":
            violations.extend(audit_zip(path))
        else:
            violations.append(f"不支持的审计目标: {path}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="检查公开安装包是否混入个人路径或运行时私密文件")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    violations = run_audit(args.paths)
    if violations:
        print("发布审计失败：")
        for item in violations:
            print(f"- {item}")
        return 1
    print("发布审计通过：未发现个人路径、数据库、日志或密钥缓存文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
