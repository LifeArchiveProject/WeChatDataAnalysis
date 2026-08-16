from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DECRYPTED_SNAPSHOT_IMPORT_MODES = {
    "manual_import",
    "account_archive_import",
}


def load_account_source_metadata(account_dir: Path) -> dict[str, Any]:
    path = Path(account_dir) / "_source.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def source_metadata_prefers_decrypted_snapshot(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    mode = str(value.get("import_mode") or "").strip().lower()
    return mode in _DECRYPTED_SNAPSHOT_IMPORT_MODES


def account_prefers_decrypted_snapshot(account_dir: Path) -> bool:
    account_path = Path(account_dir)
    if not source_metadata_prefers_decrypted_snapshot(
        load_account_source_metadata(account_path)
    ):
        return False
    # Only make the import marker authoritative while the imported snapshot is
    # still present. A later decrypt can replace _source.json and restore direct
    # mode without any migration step.
    return (account_path / "session.db").is_file() and (
        account_path / "contact.db"
    ).is_file()


__all__ = [
    "account_prefers_decrypted_snapshot",
    "load_account_source_metadata",
    "source_metadata_prefers_decrypted_snapshot",
]
