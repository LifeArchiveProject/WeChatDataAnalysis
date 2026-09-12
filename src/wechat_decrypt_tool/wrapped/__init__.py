"""WeChat Wrapped (年度总结) backend modules.

This package is intentionally split into small modules so we can implement
ideas incrementally (按点子编号依次实现), avoiding a single giant file.
"""

from pathlib import Path

from ..account_identity import resolve_account_self_username
from ..wcdb_realtime import _normalize_native_account_name


def resolve_wrapped_self_username(account_dir: Path) -> str:
    """Return the message sender identity, not the account storage directory name."""
    username = resolve_account_self_username(account_dir)
    if username == account_dir.name:
        return _normalize_native_account_name(username)
    return username
