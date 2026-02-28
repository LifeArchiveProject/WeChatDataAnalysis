from __future__ import annotations

import json
import os
import re
from pathlib import Path


RUNTIME_SETTINGS_FILENAME = "runtime_settings.json"
BACKEND_PORT_KEY = "backend_port"
ENV_PORT_KEY = "WECHAT_TOOL_PORT"
ENV_FILE_KEY = "WECHAT_TOOL_ENV_FILE"
DEFAULT_ENV_FILENAME = ".env"


def _parse_port(value: object) -> int | None:
    if value is None:
        return None
    try:
        raw = str(value).strip()
    except Exception:
        return None
    if not raw:
        return None
    try:
        port = int(raw, 10)
    except Exception:
        return None
    if port < 1 or port > 65535:
        return None
    return port


def get_runtime_settings_path() -> Path:
    from .app_paths import get_output_dir

    return get_output_dir() / RUNTIME_SETTINGS_FILENAME


def read_backend_port_setting() -> int | None:
    path = get_runtime_settings_path()
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return None
        return _parse_port(data.get(BACKEND_PORT_KEY))
    except Exception:
        return None


def write_backend_port_setting(port: int | None) -> None:
    path = get_runtime_settings_path()
    safe_port = _parse_port(port)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    try:
        data: dict = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8") or "{}")
                if isinstance(existing, dict):
                    data = existing
            except Exception:
                data = {}

        if safe_port is None:
            data.pop(BACKEND_PORT_KEY, None)
        else:
            data[BACKEND_PORT_KEY] = safe_port

        # Keep the file small and stable; remove if empty.
        if not data:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def read_effective_backend_port(default: int) -> tuple[int, str]:
    """Return (port, source) where source is one of: env | settings | default."""

    env_raw = str(os.environ.get("WECHAT_TOOL_PORT", "") or "").strip()
    env_port = _parse_port(env_raw)
    if env_port is not None:
        return env_port, "env"

    settings_port = read_backend_port_setting()
    if settings_port is not None:
        return settings_port, "settings"

    return int(default), "default"


def get_env_file_path() -> Path | None:
    """Best-effort env file path for `uv run` (defaults to repo root `.env`)."""

    v = str(os.environ.get(ENV_FILE_KEY, "") or "").strip()
    if v:
        try:
            return Path(v)
        except Exception:
            return None

    cwd = Path.cwd()
    # Heuristic: only write `.env` in a project root (avoid polluting random dirs).
    try:
        if (cwd / "pyproject.toml").is_file():
            return cwd / DEFAULT_ENV_FILENAME
    except Exception:
        return None

    return None


def _set_env_var_in_file(env_file: Path, key: str, value: str | None) -> bool:
    try:
        env_file.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return False

    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
    try:
        raw = env_file.read_text(encoding="utf-8") if env_file.is_file() else ""
    except Exception:
        raw = ""

    lines = raw.splitlines(keepends=True) if raw else []
    out: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            if value is None:
                continue
            if not replaced:
                out.append(f"{key}={value}\n")
                replaced = True
            continue
        out.append(line)

    if value is not None and not replaced:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append(f"{key}={value}\n")

    try:
        env_file.write_text("".join(out), encoding="utf-8")
        return True
    except Exception:
        return False


def write_backend_port_env_file(port: int | None) -> Path | None:
    """Write `WECHAT_TOOL_PORT` into a `.env` file so `uv run main.py` picks it up on restart.

    Note: `uv` doesn't override already-set env vars; `.env` only applies when the variable is not
    present in the current shell/session.
    """

    env_file = get_env_file_path()
    if not env_file:
        return None

    safe_port = _parse_port(port)
    ok = _set_env_var_in_file(env_file, ENV_PORT_KEY, str(safe_port) if safe_port is not None else None)
    return env_file if ok else None
