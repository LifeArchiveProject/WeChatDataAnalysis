import datetime
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from .app_paths import get_account_keys_path

_KEY_STORE_PATH = get_account_keys_path()


def normalize_key_store_path(path_value: Optional[str]) -> str:
    raw = str(path_value or "").strip()
    if not raw:
        return ""

    try:
        return str(Path(raw).expanduser().resolve())
    except Exception:
        try:
            return str(Path(raw).expanduser())
        except Exception:
            return raw


def _normalize_account_aliases(*values: Optional[str], aliases: Optional[Iterable[str]] = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for value in [*values, *(list(aliases or []))]:
        key = str(value or "").strip()
        if (not key) or (key in seen):
            continue
        seen.add(key)
        out.append(key)

    return out


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_account_keys_store() -> dict[str, Any]:
    if not _KEY_STORE_PATH.exists():
        return {}
    try:
        data = json.loads(_KEY_STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_account_keys_from_store(account: str) -> dict[str, Any]:
    store = load_account_keys_store()
    v = store.get(account, {})
    return v if isinstance(v, dict) else {}


def upsert_account_keys_in_store(
    account: str,
    *,
    db_key: Optional[str] = None,
    image_xor_key: Optional[str] = None,
    image_aes_key: Optional[str] = None,
    aliases: Optional[Iterable[str]] = None,
    db_key_source_wxid_dir: Optional[str] = None,
    db_key_source_db_storage_path: Optional[str] = None,
) -> dict[str, Any]:
    account = str(account or "").strip()
    if not account:
        return {}

    store = load_account_keys_store()
    target_accounts = _normalize_account_aliases(account, aliases=aliases)

    item: dict[str, Any] = {}
    for target_account in target_accounts:
        existing = store.get(target_account, {})
        if isinstance(existing, dict) and existing:
            item = dict(existing)
            break

    if db_key is not None:
        item["db_key"] = str(db_key)
        item["db_key_source_wxid_dir"] = normalize_key_store_path(db_key_source_wxid_dir)
        item["db_key_source_db_storage_path"] = normalize_key_store_path(db_key_source_db_storage_path)
    if image_xor_key is not None:
        item["image_xor_key"] = str(image_xor_key)
    if image_aes_key is not None:
        item["image_aes_key"] = str(image_aes_key)

    item["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    for target_account in target_accounts:
        store[target_account] = dict(item)

    try:
        _atomic_write_json(_KEY_STORE_PATH, store)
    except Exception:
        # 不影响主流程：写入失败时静默忽略
        pass

    return item


def remove_account_keys_from_store(account: str) -> bool:
    account = str(account or "").strip()
    if not account:
        return False

    store = load_account_keys_store()
    if account not in store:
        return False

    try:
        store.pop(account, None)
        _atomic_write_json(_KEY_STORE_PATH, store)
        return True
    except Exception:
        return False
