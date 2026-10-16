from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional


_LEGACY_BACKUP_SUFFIX_RE = re.compile(
    r"^(?P<account>.+)\.backup-\d{8}-\d{6}(?:-\d+)?$",
    re.IGNORECASE,
)
_WXID_SOURCE_SUFFIX_RE = re.compile(
    r"^(?P<account>wxid_[^\s]+)_[0-9a-f]{4}$",
    re.IGNORECASE,
)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def canonical_account_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        return ""

    backup_match = _LEGACY_BACKUP_SUFFIX_RE.fullmatch(name)
    if backup_match is not None:
        name = backup_match.group("account")

    source_match = _WXID_SOURCE_SUFFIX_RE.fullmatch(name)
    if source_match is not None:
        name = source_match.group("account")
    return name


def is_internal_account_directory_name(value: Any) -> bool:
    name = str(value or "").strip()
    if not name or name.startswith("."):
        return True
    return _LEGACY_BACKUP_SUFFIX_RE.fullmatch(name) is not None


def _append_candidate(output: list[str], value: Any) -> None:
    raw = str(value or "").strip()
    if not raw:
        return

    values = [raw]
    try:
        if "/" in raw or "\\" in raw:
            values.insert(0, raw.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1])
    except Exception:
        pass

    for item in values:
        for candidate in (canonical_account_name(item), item):
            candidate = str(candidate or "").strip()
            if candidate and candidate not in output:
                output.append(candidate)


def _append_source_path_candidate(
    output: list[str],
    value: Any,
    *,
    db_storage: bool = False,
) -> None:
    raw = str(value or "").strip()
    if not raw:
        return
    try:
        parts = [part for part in raw.rstrip("/\\").replace("\\", "/").split("/") if part]
        leaf = parts[-1] if parts else ""
        if db_storage and leaf.lower() == "db_storage":
            leaf = parts[-2] if len(parts) > 1 else ""
    except Exception:
        leaf = ""
    _append_candidate(output, leaf)


def account_identity_candidates(account_dir: Path) -> list[str]:
    account_path = Path(account_dir)
    output: list[str] = []

    account_info = _read_json_object(account_path / "account.json")
    for key in ("username", "user_name", "wxid", "account"):
        _append_candidate(output, account_info.get(key))

    source_info = _read_json_object(account_path / "_source.json")
    for key in ("native_wxid", "username", "user_name", "wxid", "account"):
        _append_candidate(output, source_info.get(key))
    _append_source_path_candidate(output, source_info.get("wxid_dir"))
    _append_source_path_candidate(
        output,
        source_info.get("db_storage_path"),
        db_storage=True,
    )

    original_info = source_info.get("original_info")
    if isinstance(original_info, dict):
        for key in (
            "username",
            "user_name",
            "wxid",
            "account",
            "account_dir",
            "wxid_dir",
        ):
            _append_candidate(output, original_info.get(key))

    _append_candidate(output, account_path.name)
    return output


def resolve_account_self_username(account_dir: Path) -> str:
    account_path = Path(account_dir)
    raw_directory_name = str(account_path.name or "").strip()

    # Preserve the long-standing API value for direct/source-suffix accounts.
    # Imported snapshots always carry account.json (the importer generates it
    # when necessary), which gives us an explicit cross-platform identity.
    account_info = _read_json_object(account_path / "account.json")
    explicit: list[str] = []
    for key in ("username", "user_name", "wxid", "account"):
        _append_candidate(explicit, account_info.get(key))
    if explicit:
        return explicit[0]

    return raw_directory_name


def resolve_account_self_rowid(
    connection: sqlite3.Connection,
    account_dir: Path,
    *,
    candidates: Optional[Iterable[str]] = None,
) -> tuple[Optional[int], str]:
    candidate_values = list(candidates or account_identity_candidates(account_dir))
    fallback_username = (
        candidate_values[0]
        if candidate_values
        else str(Path(account_dir).name or "").strip()
    )

    for username in candidate_values:
        try:
            row = connection.execute(
                "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                (str(username),),
            ).fetchone()
        except Exception:
            return None, fallback_username
        if row is None or row[0] is None:
            continue
        try:
            return int(row[0]), str(username)
        except (TypeError, ValueError):
            continue
    return None, fallback_username


__all__ = [
    "account_identity_candidates",
    "canonical_account_name",
    "is_internal_account_directory_name",
    "resolve_account_self_rowid",
    "resolve_account_self_username",
]
