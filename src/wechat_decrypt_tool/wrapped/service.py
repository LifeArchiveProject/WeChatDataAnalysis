from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..chat_helpers import _resolve_account_dir
from ..logging_config import get_logger
from .storage import wrapped_cache_path
from .cards.card_01_cyber_schedule import build_card_01_cyber_schedule

logger = get_logger(__name__)


# We implement cards strictly in the order of `docs/wechat_wrapped_ideas_feasibility.md`.
_IMPLEMENTED_UPTO_ID = 1


def _default_year() -> int:
    return datetime.now().year


def build_wrapped_annual_response(
    *,
    account: Optional[str],
    year: Optional[int],
    refresh: bool = False,
) -> dict[str, Any]:
    """Build annual wrapped response for the given account/year.

    For now we only implement cards up to id=1.
    """

    account_dir = _resolve_account_dir(account)
    y = int(year or _default_year())
    scope = "global"

    cache_path = wrapped_cache_path(account_dir=account_dir, scope=scope, year=y, implemented_upto=_IMPLEMENTED_UPTO_ID)
    if (not refresh) and cache_path.exists():
        try:
            cached_obj = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached_obj, dict) and isinstance(cached_obj.get("cards"), list):
                cached_obj["cached"] = True
                return cached_obj
        except Exception:
            pass

    cards: list[dict[str, Any]] = []
    cards.append(build_card_01_cyber_schedule(account_dir=account_dir, year=y))

    obj: dict[str, Any] = {
        "account": account_dir.name,
        "year": y,
        "scope": scope,
        "username": None,
        "generated_at": int(time.time()),
        "cached": False,
        "cards": cards,
    }

    try:
        cache_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to write wrapped cache: %s", cache_path)

    return obj

