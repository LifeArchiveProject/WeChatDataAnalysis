from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from .app_paths import get_output_databases_dir
from .key_store import get_account_keys_from_store, load_account_keys_store, normalize_key_store_path
from .sqlite_diagnostics import is_usable_sqlite_db


@dataclass(frozen=True)
class ChatAccountContext:
    name: str
    account_dir: Path
    has_decrypted_dbs: bool
    source_info: dict[str, Any]
    db_key_present: bool = False

    @property
    def db_storage_path(self) -> str:
        return str(self.source_info.get("db_storage_path") or "").strip()

    @property
    def wxid_dir(self) -> str:
        return str(self.source_info.get("wxid_dir") or "").strip()

    @property
    def mode(self) -> str:
        if self.db_storage_path or self.wxid_dir:
            return "direct"
        return "decrypted" if self.has_decrypted_dbs else "unknown"


def _safe_account_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    # Account names are wxids / aliases, not paths. Keep this deliberately strict
    # so resolving key-store accounts cannot create arbitrary directories.
    if any(ch in name for ch in ("/", "\\", ":", "\x00")):
        return ""
    if name in {".", ".."}:
        return ""
    return name


def _is_valid_decrypted_sqlite(path: Path) -> bool:
    return is_usable_sqlite_db(path)


def _has_decrypted_chat_dbs(account_dir: Path) -> bool:
    return _is_valid_decrypted_sqlite(account_dir / "session.db") and _is_valid_decrypted_sqlite(account_dir / "contact.db")


def _load_source_json(account_dir: Path) -> dict[str, Any]:
    p = account_dir / "_source.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _source_info_from_key_store(account: str) -> tuple[dict[str, Any], bool]:
    keys = get_account_keys_from_store(account)
    if not isinstance(keys, dict):
        return {}, False

    db_storage_path = normalize_key_store_path(keys.get("db_key_source_db_storage_path"))
    wxid_dir = normalize_key_store_path(keys.get("db_key_source_wxid_dir"))
    source: dict[str, Any] = {}
    if db_storage_path:
        source["db_storage_path"] = db_storage_path
    if wxid_dir:
        source["wxid_dir"] = wxid_dir
    return source, len(str(keys.get("db_key") or "").strip()) == 64


def _merge_source_info(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    out = dict(primary or {})
    for k in ("db_storage_path", "wxid_dir"):
        if not str(out.get(k) or "").strip() and str((fallback or {}).get(k) or "").strip():
            out[k] = str(fallback.get(k) or "").strip()
    return out


def _maybe_write_source_info(account_dir: Path, source_info: dict[str, Any]) -> None:
    db_storage_path = str((source_info or {}).get("db_storage_path") or "").strip()
    wxid_dir = str((source_info or {}).get("wxid_dir") or "").strip()
    if not db_storage_path and not wxid_dir:
        return
    payload = {}
    if db_storage_path:
        payload["db_storage_path"] = db_storage_path
    if wxid_dir:
        payload["wxid_dir"] = wxid_dir
    try:
        account_dir.mkdir(parents=True, exist_ok=True)
        p = account_dir / "_source.json"
        existing = _load_source_json(account_dir)
        merged = _merge_source_info(existing, payload)
        if merged != existing:
            p.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # Source persistence is an optimization for existing helpers; do not fail account resolution.
        pass


def _context_for_name(account: str) -> Optional[ChatAccountContext]:
    account_name = _safe_account_name(account)
    if not account_name:
        return None
    account_dir = (get_output_databases_dir() / account_name).resolve()
    has_dbs = False
    source_from_dir: dict[str, Any] = {}
    try:
        if account_dir.exists() and account_dir.is_dir():
            has_dbs = _has_decrypted_chat_dbs(account_dir)
            source_from_dir = _load_source_json(account_dir)
    except Exception:
        has_dbs = False
        source_from_dir = {}

    source_from_keys, key_present = _source_info_from_key_store(account_name)
    source_info = _merge_source_info(source_from_dir, source_from_keys)
    if not has_dbs and not source_info and not key_present:
        return None

    return ChatAccountContext(
        name=account_name,
        account_dir=account_dir,
        has_decrypted_dbs=bool(has_dbs),
        source_info=source_info,
        db_key_present=bool(key_present),
    )


def list_chat_account_contexts() -> list[ChatAccountContext]:
    names: set[str] = set()
    output_databases_dir = get_output_databases_dir()
    if output_databases_dir.exists():
        try:
            for p in output_databases_dir.iterdir():
                if p.is_dir():
                    n = _safe_account_name(p.name)
                    if n:
                        names.add(n)
        except Exception:
            pass

    store = load_account_keys_store()
    if isinstance(store, dict):
        for name, item in store.items():
            n = _safe_account_name(name)
            if not n or not isinstance(item, dict):
                continue
            has_key = len(str(item.get("db_key") or "").strip()) == 64
            has_source = bool(
                str(item.get("db_key_source_db_storage_path") or "").strip()
                or str(item.get("db_key_source_wxid_dir") or "").strip()
            )
            if has_key or has_source:
                names.add(n)

    contexts: list[ChatAccountContext] = []
    for name in sorted(names):
        ctx = _context_for_name(name)
        if ctx is not None:
            contexts.append(ctx)
    contexts.sort(key=lambda c: (0 if c.mode == "direct" else 1, c.name.lower()))
    return contexts


def list_chat_account_names() -> list[str]:
    return [ctx.name for ctx in list_chat_account_contexts()]


def resolve_chat_account_context(account: Optional[str]) -> ChatAccountContext:
    contexts = list_chat_account_contexts()
    if not contexts:
        raise HTTPException(
            status_code=404,
            detail="No chat accounts found. Please save a db key/db_storage path or decrypt first.",
        )

    selected = _safe_account_name(account) or contexts[0].name
    by_name = {ctx.name: ctx for ctx in contexts}
    ctx = by_name.get(selected)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    base = get_output_databases_dir().resolve()
    candidate = ctx.account_dir.resolve()
    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid account path.")

    if ctx.source_info:
        _maybe_write_source_info(candidate, ctx.source_info)
    elif ctx.has_decrypted_dbs:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    return ChatAccountContext(
        name=ctx.name,
        account_dir=candidate,
        has_decrypted_dbs=ctx.has_decrypted_dbs,
        source_info=ctx.source_info,
        db_key_present=ctx.db_key_present,
    )


def is_decrypted_chat_account_dir(account_dir: Path) -> bool:
    return _has_decrypted_chat_dbs(Path(account_dir))

