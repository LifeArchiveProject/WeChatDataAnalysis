from __future__ import annotations

from pathlib import Path


_IGNORED_SOURCE_DATABASE_NAMES = frozenset({"key_info.db"})
_INDEX_DATABASE_NAMES = frozenset({"chat_search_index.db", "chat_search_index.tmp.db"})
_INDEX_DATABASE_SUFFIXES = ("_fts.db",)
_INTERNAL_OUTPUT_DATABASE_NAMES = frozenset(
    {
        "chat_search_index.db",
        "chat_search_index.tmp.db",
        "session_last_message.db",
    }
)


def normalize_database_file_name(file_name: str | Path) -> str:
    return Path(str(file_name or "")).name.strip().lower()


def is_index_database_file(file_name: str | Path) -> bool:
    lower_name = normalize_database_file_name(file_name)
    if not lower_name:
        return False
    if lower_name in _INDEX_DATABASE_NAMES:
        return True
    return lower_name.endswith(_INDEX_DATABASE_SUFFIXES)


def should_skip_source_database(file_name: str | Path) -> bool:
    lower_name = normalize_database_file_name(file_name)
    if not lower_name:
        return True
    if lower_name in _IGNORED_SOURCE_DATABASE_NAMES:
        return True
    return is_index_database_file(lower_name)


def should_include_in_database_count(file_name: str | Path) -> bool:
    lower_name = normalize_database_file_name(file_name)
    if not lower_name.endswith(".db"):
        return False
    if should_skip_source_database(lower_name):
        return False
    if lower_name in _INTERNAL_OUTPUT_DATABASE_NAMES:
        return False
    return True


def list_countable_database_names(account_dir: Path) -> list[str]:
    if not account_dir.exists():
        return []

    db_files = [
        path.name
        for path in account_dir.glob("*.db")
        if path.is_file() and should_include_in_database_count(path.name)
    ]
    db_files.sort()
    return db_files
