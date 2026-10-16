from __future__ import annotations

import os
from pathlib import Path

ENV_DATA_DIR_KEY = "WECHAT_TOOL_DATA_DIR"
ENV_OUTPUT_DIR_KEY = "WECHAT_TOOL_OUTPUT_DIR"


def get_data_dir() -> Path:
    """Base writable directory for all runtime output (logs, databases, key store).

    - Desktop (Electron) should set `WECHAT_TOOL_DATA_DIR` to a per-user directory
      (e.g. `%APPDATA%/WeChatDataAnalysis`).
    - Dev defaults to the current working directory (repo root).
    """

    v = os.environ.get(ENV_DATA_DIR_KEY, "").strip()
    if v:
        return Path(v).expanduser()
    return Path.cwd()


def get_output_dir() -> Path:
    v = os.environ.get(ENV_OUTPUT_DIR_KEY, "").strip()
    if v:
        return Path(v).expanduser()
    return get_data_dir() / "output"


def get_output_databases_dir() -> Path:
    return get_output_dir() / "databases"


def get_account_keys_path() -> Path:
    return get_output_dir() / "account_keys.json"
