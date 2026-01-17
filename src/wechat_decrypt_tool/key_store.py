import datetime
import json
from pathlib import Path
from typing import Any, Optional

from .app_paths import get_account_keys_path

_KEY_STORE_PATH = get_account_keys_path()


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
) -> dict[str, Any]:
    account = str(account or "").strip()
    if not account:
        return {}

    store = load_account_keys_store()
    item = store.get(account, {})
    if not isinstance(item, dict):
        item = {}

    if db_key is not None:
        item["db_key"] = str(db_key)
    if image_xor_key is not None:
        item["image_xor_key"] = str(image_xor_key)
    if image_aes_key is not None:
        item["image_aes_key"] = str(image_aes_key)

    item["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    store[account] = item

    try:
        _atomic_write_json(_KEY_STORE_PATH, store)
    except Exception:
        # 不影响主流程：写入失败时静默忽略
        pass

    return item
