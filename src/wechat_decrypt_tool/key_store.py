import datetime
import json
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from .app_paths import get_account_keys_path

_KEY_STORE_PATH = get_account_keys_path()
_KEY_STORE_LOCK = threading.RLock()


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


def _normalize_image_xor_key(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 0xFF else None
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = int(raw[2:], 16) if raw.lower().startswith("0x") else int(raw, 16)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 0xFF else None


def _same_complete_image_key_pair(
    existing: dict[str, Any],
    image_xor_key: Optional[str],
    image_aes_key: Optional[str],
) -> bool:
    if existing.get("image_key_verified") is not True:
        return False
    if image_xor_key is None or image_aes_key is None:
        return False
    existing_xor = _normalize_image_xor_key(existing.get("image_xor_key"))
    incoming_xor = _normalize_image_xor_key(image_xor_key)
    existing_aes = str(existing.get("image_aes_key") or "").strip()[:16]
    incoming_aes = str(image_aes_key or "").strip()[:16]
    return (
        existing_xor is not None
        and existing_xor == incoming_xor
        and len(existing_aes) == 16
        and existing_aes == incoming_aes
    )


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_account_keys_store() -> dict[str, Any]:
    with _KEY_STORE_LOCK:
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
    image_key_verified: Optional[bool] = None,
    image_key_source: Optional[str] = None,
    image_key_source_wxid_dir: Optional[str] = None,
    image_key_derived_wxid: Optional[str] = None,
    image_key_code: Optional[int] = None,
) -> dict[str, Any]:
    account = str(account or "").strip()
    if not account:
        return {}

    with _KEY_STORE_LOCK:
        store = load_account_keys_store()
        target_accounts = _normalize_account_aliases(account, aliases=aliases)
        has_image_key_update = image_xor_key is not None or image_aes_key is not None
        updated_at = datetime.datetime.now().isoformat(timespec="seconds")
        primary_item: dict[str, Any] = {}
        for target_account in target_accounts:
            existing = store.get(target_account, {})
            item = dict(existing) if isinstance(existing, dict) else {}

            if db_key is not None:
                item["db_key"] = str(db_key)
                item["db_key_source_wxid_dir"] = normalize_key_store_path(db_key_source_wxid_dir)
                item["db_key_source_db_storage_path"] = normalize_key_store_path(db_key_source_db_storage_path)

            preserve_verified = image_key_verified is None and _same_complete_image_key_pair(
                item,
                image_xor_key,
                image_aes_key,
            )
            if image_xor_key is not None:
                item["image_xor_key"] = str(image_xor_key)
            if image_aes_key is not None:
                item["image_aes_key"] = str(image_aes_key)
            if has_image_key_update and not preserve_verified:
                verified = image_key_verified is True
                item["image_key_verified"] = verified
                item["image_key_source"] = str(image_key_source or "legacy_or_manual").strip()
                item["image_key_source_wxid_dir"] = (
                    normalize_key_store_path(image_key_source_wxid_dir) if verified else ""
                )
                item["image_key_derived_wxid"] = (
                    str(image_key_derived_wxid or "").strip() if verified else ""
                )
                if verified and image_key_code is not None:
                    try:
                        item["image_key_code"] = int(image_key_code)
                    except (TypeError, ValueError):
                        item["image_key_code"] = None
                else:
                    item["image_key_code"] = None

            item["updated_at"] = updated_at
            store[target_account] = dict(item)
            if target_account == account:
                primary_item = dict(item)

        try:
            _atomic_write_json(_KEY_STORE_PATH, store)
        except Exception:
            # 不影响主流程：写入失败时静默忽略
            pass

        return primary_item


def remove_account_keys_from_store(account: str) -> bool:
    account = str(account or "").strip()
    if not account:
        return False

    with _KEY_STORE_LOCK:
        store = load_account_keys_store()
        if account not in store:
            return False

        try:
            store.pop(account, None)
            _atomic_write_json(_KEY_STORE_PATH, store)
            return True
        except Exception:
            return False
