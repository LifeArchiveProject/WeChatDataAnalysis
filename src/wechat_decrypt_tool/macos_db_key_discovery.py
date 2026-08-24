"""Safe macOS database-key discovery without attaching to or modifying WeChat."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_KEY_FIELD_NAMES = {
    "passphrase",
    "db_key",
    "database_key",
    "raw_key",
    "enc_key",
    "default_key",
    "__default_key",
}


@dataclass(frozen=True, slots=True)
class MacOSDBKeyDiscoveryFailure(RuntimeError):
    code: str
    message: str
    checked_sources: int = 0

    def __str__(self) -> str:
        return self.message


def _normalize_hex_key(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    if raw.lower().startswith("x'") and raw.endswith("'"):
        raw = raw[2:-1]
    return raw.lower() if _HEX_KEY_RE.fullmatch(raw) else ""


def _candidate_files(database: Path, home: Path) -> list[Path]:
    candidates = [
        home / ".wcdb-key-tool" / "wechat-passphrase.json",
        home / ".wechat-cli" / "all_keys.json",
        home / ".wechat-cli" / "keys.json",
        home / ".wechat-summary" / "all_keys.json",
    ]
    current = database.parent
    for _ in range(4):
        candidates.extend(current / name for name in ("all_keys.json", "wechat_keys.json", "keys.json"))
        if current.parent == current:
            break
        current = current.parent

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        normalized = str(path.expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path.expanduser())
    return unique


def _path_matches_database(key: str, database: Path) -> bool:
    normalized = str(key or "").replace("\\", "/").strip().lower()
    if not normalized:
        return False
    db_path = database.as_posix().lower()
    return (
        normalized == database.name.lower()
        or db_path.endswith(normalized)
        or normalized.endswith("/" + database.name.lower())
    )


def _extract_candidates(payload: Any, database: Path) -> Iterable[tuple[str, str]]:
    if not isinstance(payload, dict):
        return

    for field, value in payload.items():
        field_name = str(field or "").strip().lower()
        normalized = _normalize_hex_key(value)
        if normalized and field_name in _KEY_FIELD_NAMES:
            yield normalized, field_name

    maps: list[dict[str, Any]] = [payload]
    for field in ("keys", "databases", "derived_key_map", "key_map"):
        nested = payload.get(field)
        if isinstance(nested, dict):
            maps.append(nested)

    for mapping in maps:
        for key, value in mapping.items():
            if not _path_matches_database(str(key), database):
                continue
            if isinstance(value, dict):
                for nested_field in _KEY_FIELD_NAMES:
                    normalized = _normalize_hex_key(value.get(nested_field))
                    if normalized:
                        yield normalized, f"path:{nested_field}"
            else:
                normalized = _normalize_hex_key(value)
                if normalized:
                    yield normalized, "path"


def discover_macos_db_key(
    probe_db_path: str | Path,
    *,
    home: str | Path | None = None,
    extra_files: Iterable[str | Path] = (),
) -> dict[str, Any]:
    if sys.platform != "darwin":
        raise MacOSDBKeyDiscoveryFailure("unsupported_platform", "安全密钥发现仅支持 macOS")

    database = Path(probe_db_path).expanduser()
    if not database.is_file():
        raise MacOSDBKeyDiscoveryFailure("database_missing", f"用于校验的数据库不存在: {database}")
    try:
        with database.open("rb") as handle:
            page1 = handle.read(4096)
    except PermissionError as exc:
        raise MacOSDBKeyDiscoveryFailure(
            "database_permission_denied",
            "macOS 已拒绝读取微信数据库目录。请在“系统设置 → 隐私与安全性 → 完全磁盘访问权限”中启用当前工具，然后完全退出并重新打开。",
        ) from exc
    if page1.startswith(b"SQLite format 3"):
        raise MacOSDBKeyDiscoveryFailure("database_plaintext", "所选数据库已经是明文 SQLite")

    from .wechat_decrypt import PAGE_SIZE, _resolve_page1_key_material

    if len(page1) < PAGE_SIZE:
        raise MacOSDBKeyDiscoveryFailure("database_incomplete", "数据库首页不足 4096 字节")

    home_path = Path(home).expanduser() if home is not None else Path.home()
    files = [*_candidate_files(database, home_path), *(Path(item).expanduser() for item in extra_files)]
    checked = 0
    seen_keys: set[str] = set()
    for source in files:
        if not source.is_file():
            continue
        checked += 1
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        for candidate, field in _extract_candidates(payload, database):
            if candidate in seen_keys:
                continue
            seen_keys.add(candidate)
            resolved = _resolve_page1_key_material(bytes.fromhex(candidate), page1)
            if resolved is None:
                continue
            _enc_key, _mac_key, mode = resolved
            return {
                "platform": "macos",
                "db_key": candidate,
                "method": "safe_local_cache",
                "source": str(source),
                "source_field": field,
                "key_mode": mode,
                "probe_db_path": str(database),
                "validated": True,
                "checked_sources": checked,
                "wechat_modified": False,
                "process_attached": False,
                "database_key_extraction": True,
                "manual_input_supported": True,
            }

    raise MacOSDBKeyDiscoveryFailure(
        "safe_key_not_found",
        "未在本机已保存的密钥或 passphrase 缓存中找到能通过当前数据库校验的候选。"
        "微信 4.1+ 的首次 passphrase 提取会先在所选备份目录验证腾讯原版备份，为默认路径微信"
        "准备同卷 APFS 写时复制恢复副本，再临时启用调试签名。请只在系统自动打开的窗口"
        "登录并进入聊天主界面；完成断点预检并分离后先退出账号，等微信显示登录界面再"
        "启动监测，随后只重新登录同一个账号。"
        "候选通过当前数据库校验后会缓存；完成、失败或取消时都会关闭临时版本、恢复腾讯"
        "原签名并清理临时恢复副本。"
        "也可导入另一台设备已生成的 all_keys.json / "
        "wechat-passphrase.json，或手动填写已验证密钥。",
        checked_sources=checked,
    )


__all__ = ["MacOSDBKeyDiscoveryFailure", "discover_macos_db_key"]
