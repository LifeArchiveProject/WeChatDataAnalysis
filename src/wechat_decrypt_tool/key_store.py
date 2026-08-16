import datetime
import json
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from .account_identity import canonical_account_name
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


def _stored_db_storage_path(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    direct = normalize_key_store_path(item.get("db_key_source_db_storage_path"))
    if direct:
        return direct
    wxid_dir = normalize_key_store_path(item.get("db_key_source_wxid_dir"))
    return normalize_key_store_path(Path(wxid_dir) / "db_storage") if wxid_dir else ""


def _purge_native_raw_key_cache_roots(roots: Iterable[str]) -> None:
    try:
        from .native_core_raw_key_cache import remove_cache_for_root
    except Exception:
        return
    for root in roots:
        try:
            remove_cache_for_root(Path(root))
        except Exception:
            pass


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


def _canonical_account_key_name(value: Any) -> str:
    return canonical_account_name(value)


def _stored_account_identity_names(name: str, item: Any) -> set[str]:
    identities = {
        _canonical_account_key_name(name),
        _canonical_account_key_name(
            (item or {}).get("image_key_derived_wxid") if isinstance(item, dict) else ""
        ),
    }
    if isinstance(item, dict):
        for key in ("db_key_source_wxid_dir", "image_key_source_wxid_dir"):
            raw = normalize_key_store_path(item.get(key))
            if raw:
                identities.add(_canonical_account_key_name(Path(raw).name))
    return {value for value in identities if value}


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
    raise_on_write_error: bool = False,
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
        stale_cache_roots: set[str] = set()
        for target_account in target_accounts:
            existing = store.get(target_account, {})
            item = dict(existing) if isinstance(existing, dict) else {}

            if db_key is not None:
                previous_root = _stored_db_storage_path(item)
                item["db_key"] = str(db_key)
                item["db_key_source_wxid_dir"] = normalize_key_store_path(db_key_source_wxid_dir)
                item["db_key_source_db_storage_path"] = normalize_key_store_path(db_key_source_db_storage_path)
                next_root = _stored_db_storage_path(item)
                if previous_root and previous_root != next_root:
                    stale_cache_roots.add(previous_root)

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

        write_succeeded = False
        try:
            _atomic_write_json(_KEY_STORE_PATH, store)
            write_succeeded = True
        except Exception:
            if raise_on_write_error:
                raise

        if write_succeeded and stale_cache_roots:
            referenced_roots = {
                root
                for item in store.values()
                if (root := _stored_db_storage_path(item))
            }
            _purge_native_raw_key_cache_roots(
                stale_cache_roots - referenced_roots
            )

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
            removed = store.pop(account, None)
            _atomic_write_json(_KEY_STORE_PATH, store)
            source_root = _stored_db_storage_path(removed)
            root_still_used = bool(
                source_root
                and any(
                    _stored_db_storage_path(item) == source_root
                    for item in store.values()
                )
            )
            if source_root and not root_still_used:
                _purge_native_raw_key_cache_roots([source_root])
            return True
        except Exception:
            return False


def remove_account_family_keys_from_store(account: str) -> list[str]:
    """Remove canonical/source-suffix aliases for one WeChat account atomically."""

    account = str(account or "").strip()
    canonical_account = _canonical_account_key_name(account)
    if not canonical_account:
        return []

    with _KEY_STORE_LOCK:
        store = load_account_keys_store()
        remove_names: list[str] = []
        target_roots: set[str] = set()

        for name, item in store.items():
            if canonical_account in _stored_account_identity_names(name, item):
                remove_names.append(str(name))
                root = _stored_db_storage_path(item)
                if root:
                    target_roots.add(root)

        # Source-equivalent aliases can use a human-facing account name rather
        # than the canonical wxid. Once one canonical entry identifies the
        # source root, remove every remaining key-store alias for that root.
        if target_roots:
            for name, item in store.items():
                if str(name) in remove_names:
                    continue
                if _stored_db_storage_path(item) in target_roots:
                    remove_names.append(str(name))

        if not remove_names:
            return []

        removed_items = [store.pop(name, None) for name in remove_names]
        _atomic_write_json(_KEY_STORE_PATH, store)

        removed_roots = {
            root
            for item in removed_items
            if (root := _stored_db_storage_path(item))
        }
        referenced_roots = {
            root
            for item in store.values()
            if (root := _stored_db_storage_path(item))
        }
        _purge_native_raw_key_cache_roots(removed_roots - referenced_roots)
        return remove_names
