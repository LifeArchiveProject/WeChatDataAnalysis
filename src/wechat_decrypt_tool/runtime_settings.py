from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path


RUNTIME_SETTINGS_FILENAME = "runtime_settings.json"
BACKEND_PORT_KEY = "backend_port"
BACKEND_HOST_KEY = "backend_host"
MCP_TOKEN_KEY = "mcp_token"
ENV_PORT_KEY = "WECHAT_TOOL_PORT"
ENV_HOST_KEY = "WECHAT_TOOL_HOST"
ENV_MCP_TOKEN_KEY = "WECHAT_TOOL_MCP_TOKEN"
ENV_FILE_KEY = "WECHAT_TOOL_ENV_FILE"
DEFAULT_ENV_FILENAME = ".env"
LOOPBACK_BACKEND_HOST = "127.0.0.1"
LAN_BACKEND_HOST = "0.0.0.0"


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


def _normalize_host(value: object) -> str | None:
    try:
        raw = str(value or "").strip()
    except Exception:
        return None
    if raw in {LOOPBACK_BACKEND_HOST, "localhost", "::1"}:
        return LOOPBACK_BACKEND_HOST
    if raw in {LAN_BACKEND_HOST, "::"}:
        return LAN_BACKEND_HOST
    return None


def _normalize_mcp_token(value: object) -> str | None:
    try:
        raw = str(value or "").strip()
    except Exception:
        return None
    if len(raw) < 16 or len(raw) > 512:
        return None
    if any(ch.isspace() for ch in raw):
        return None
    return raw


def generate_mcp_token() -> str:
    return secrets.token_urlsafe(32)


def _read_runtime_settings() -> dict:
    path = get_runtime_settings_path()
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_runtime_settings(data: dict) -> None:
    path = get_runtime_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    try:
        cleaned = data if isinstance(data, dict) else {}
        if not cleaned:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return

        path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def get_runtime_settings_path() -> Path:
    from .app_paths import get_output_dir

    return get_output_dir() / RUNTIME_SETTINGS_FILENAME


def read_backend_port_setting() -> int | None:
    try:
        data = _read_runtime_settings()
        return _parse_port(data.get(BACKEND_PORT_KEY))
    except Exception:
        return None


def write_backend_port_setting(port: int | None) -> None:
    safe_port = _parse_port(port)
    try:
        data = _read_runtime_settings()

        if safe_port is None:
            data.pop(BACKEND_PORT_KEY, None)
        else:
            data[BACKEND_PORT_KEY] = safe_port

        _write_runtime_settings(data)
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


def read_backend_host_setting() -> str | None:
    try:
        data = _read_runtime_settings()
        return _normalize_host(data.get(BACKEND_HOST_KEY))
    except Exception:
        return None


def write_backend_host_setting(host: str | None) -> None:
    safe_host = _normalize_host(host)
    try:
        data = _read_runtime_settings()
        if safe_host is None:
            data.pop(BACKEND_HOST_KEY, None)
        else:
            data[BACKEND_HOST_KEY] = safe_host
        _write_runtime_settings(data)
    except Exception:
        return


def read_effective_backend_host(default: str = LOOPBACK_BACKEND_HOST) -> tuple[str, str]:
    """Return (host, source) where source is one of: env | settings | default."""

    env_host = _normalize_host(os.environ.get(ENV_HOST_KEY, ""))
    if env_host is not None:
        return env_host, "env"

    settings_host = read_backend_host_setting()
    if settings_host is not None:
        return settings_host, "settings"

    return _normalize_host(default) or LOOPBACK_BACKEND_HOST, "default"


def read_mcp_token_setting() -> str | None:
    try:
        data = _read_runtime_settings()
        return _normalize_mcp_token(data.get(MCP_TOKEN_KEY))
    except Exception:
        return None


def write_mcp_token_setting(token: str | None) -> None:
    safe_token = _normalize_mcp_token(token)
    try:
        data = _read_runtime_settings()
        if safe_token is None:
            data.pop(MCP_TOKEN_KEY, None)
        else:
            data[MCP_TOKEN_KEY] = safe_token
        _write_runtime_settings(data)
    except Exception:
        return


def read_effective_mcp_token() -> tuple[str | None, str]:
    """Return (token, source) where source is one of: env | settings | missing."""

    env_token = _normalize_mcp_token(os.environ.get(ENV_MCP_TOKEN_KEY, ""))
    if env_token is not None:
        return env_token, "env"

    settings_token = read_mcp_token_setting()
    if settings_token is not None:
        return settings_token, "settings"

    return None, "missing"


def ensure_mcp_token() -> tuple[str, str]:
    token, source = read_effective_mcp_token()
    if token:
        return token, source

    token = generate_mcp_token()
    write_mcp_token_setting(token)
    return token, "generated"


def reset_mcp_token() -> str:
    token = generate_mcp_token()
    write_mcp_token_setting(token)
    return token


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


def write_backend_host_env_file(host: str | None) -> Path | None:
    """Write `WECHAT_TOOL_HOST` into a `.env` file so `uv run main.py` picks it up on restart."""

    env_file = get_env_file_path()
    if not env_file:
        return None

    safe_host = _normalize_host(host)
    ok = _set_env_var_in_file(env_file, ENV_HOST_KEY, safe_host)
    return env_file if ok else None


def write_mcp_token_env_file(token: str | None) -> Path | None:
    """Write `WECHAT_TOOL_MCP_TOKEN` into a `.env` file so `uv run main.py` picks it up."""

    env_file = get_env_file_path()
    if not env_file:
        return None

    safe_token = _normalize_mcp_token(token)
    ok = _set_env_var_in_file(env_file, ENV_MCP_TOKEN_KEY, safe_token)
    return env_file if ok else None
