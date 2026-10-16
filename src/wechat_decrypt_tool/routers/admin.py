from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from starlette.requests import Request

from ..logging_config import get_log_file_path, get_logger
from ..path_fix import PathFixRoute
from ..runtime_settings import (
    default_backend_host,
    read_effective_backend_host,
    read_effective_backend_port,
    remote_calls_enabled,
    write_backend_port_env_file,
    write_backend_port_setting,
)


router = APIRouter(route_class=PathFixRoute)
logger = get_logger(__name__)

DEFAULT_BACKEND_PORT = 10392
_PORT_CHANGE_IN_PROGRESS = False


def _format_host_for_url(host: str) -> str:
    h = str(host or "").strip() or "127.0.0.1"
    if ":" in h and not (h.startswith("[") and h.endswith("]")):
        return f"[{h}]"
    return h


def _get_backend_bind_host() -> str:
    host, _ = read_effective_backend_host(default=default_backend_host())
    return host


def _get_backend_access_host() -> str:
    host = _get_backend_bind_host()
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


def _is_loopback_client(request: Request) -> bool:
    if remote_calls_enabled():
        return True
    client = request.client
    host = str(getattr(client, "host", "") or "").strip()
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback:
            return True
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped and ip.ipv4_mapped.is_loopback:
            return True
    except ValueError:
        if host.lower() == "localhost":
            return True
    return False


def _get_current_log_file_path() -> Path:
    log_file = Path(get_log_file_path())
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if not log_file.exists():
        try:
            log_file.touch(exist_ok=True)
        except Exception:
            pass
    return log_file


def _open_path_with_default_app(path: Path) -> None:
    target = str(path)
    if os.name == "nt":
        opener = getattr(os, "startfile", None)
        if opener is None:
            raise RuntimeError("当前系统不支持默认打开文件")
        opener(target)
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
        return

    subprocess.Popen(["xdg-open", target])


def _is_port_available(port: int, host: str) -> bool:
    try:
        addr = (host, int(port))
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            s.bind(addr)
        return True
    except Exception:
        return False


async def _wait_for_backend_ready(health_url: str, timeout_s: float = 30.0) -> bool:
    started = time.time()
    async with httpx.AsyncClient(timeout=1.0) as client:
        while time.time() - started < timeout_s:
            try:
                resp = await client.get(health_url)
                if resp.status_code < 500:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.3)
    return False


def _spawn_backend_process(next_port: int, next_host: str | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    env["WECHAT_TOOL_PORT"] = str(int(next_port))
    env["WECHAT_TOOL_HOST"] = str(next_host or _get_backend_bind_host())

    # Keep the same working directory so output paths remain consistent.
    # (When `WECHAT_TOOL_DATA_DIR` is not set, the app uses `Path.cwd()`.)
    cwd = os.getcwd()
    cwd_path = Path(cwd)

    # Ensure local imports work when running from source (repo root + src layout).
    src_dir = cwd_path / "src"
    try:
        existing_pp = str(env.get("PYTHONPATH", "") or "").strip()
        if src_dir.is_dir():
            env["PYTHONPATH"] = str(src_dir) if not existing_pp else f"{src_dir}{os.pathsep}{existing_pp}"
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
        spawn_cwd = cwd
    else:
        main_py = cwd_path / "main.py"
        if main_py.is_file():
            cmd = [sys.executable, str(main_py)]
            spawn_cwd = cwd
        else:
            cmd = [sys.executable, "-m", "wechat_decrypt_tool.backend_entry"]
            spawn_cwd = cwd

    return subprocess.Popen(cmd, cwd=spawn_cwd, env=env)


async def _exit_process_after(delay_s: float) -> None:
    try:
        await asyncio.sleep(max(0.0, float(delay_s)))
    except Exception:
        pass
    os._exit(0)  # noqa: S404


@router.get("/api/admin/log-file", summary="获取当前后端日志文件路径")
async def get_backend_log_file() -> dict:
    log_file = _get_current_log_file_path()
    return {"path": str(log_file), "exists": log_file.exists()}


@router.post("/api/admin/log-file/open", summary="打开当前后端日志文件（默认仅本机；远程模式可用）")
async def open_backend_log_file(request: Request) -> dict:
    if not _is_loopback_client(request):
        raise HTTPException(status_code=403, detail="仅允许本机访问该接口")

    log_file = _get_current_log_file_path()
    try:
        _open_path_with_default_app(log_file)
    except Exception as e:
        logger.error("open_backend_log_file failed path=%s err=%s", log_file, e)
        raise HTTPException(status_code=500, detail=f"打开日志文件失败：{e}")
    return {"success": True, "path": str(log_file)}


@router.post("/api/admin/log-frontend-server-error", summary="记录前端感知到的服务器错误")
async def log_frontend_server_error(payload: dict) -> dict:
    data = payload if isinstance(payload, dict) else {}
    try:
        status = int(data.get("status"))
    except Exception:
        status = 0

    method = str(data.get("method") or "").strip().upper() or "GET"
    request_url = str(data.get("request_url") or "").strip()
    message = str(data.get("message") or "").strip()
    backend_detail = str(data.get("backend_detail") or "").strip()
    source = str(data.get("source") or "").strip()
    page_url = str(data.get("page_url") or "").strip()

    logger.error(
        "[frontend-server-error] status=%s method=%s request_url=%s message=%s backend_detail=%s source=%s page_url=%s",
        status,
        method,
        request_url,
        message,
        backend_detail,
        source,
        page_url,
    )
    return {"success": True, "path": str(_get_current_log_file_path())}


@router.get("/api/admin/port", summary="获取后端端口（用于前端设置页）")
async def get_backend_port() -> dict:
    port, source = read_effective_backend_port(default=DEFAULT_BACKEND_PORT)
    return {"port": port, "source": source, "default_port": DEFAULT_BACKEND_PORT}


@router.post("/api/admin/port", summary="修改后端端口并重启（默认仅本机；远程模式可用）")
async def set_backend_port(payload: dict, request: Request, background_tasks: BackgroundTasks) -> dict:
    if not _is_loopback_client(request):
        raise HTTPException(status_code=403, detail="仅允许本机访问该接口")

    global _PORT_CHANGE_IN_PROGRESS
    if _PORT_CHANGE_IN_PROGRESS:
        raise HTTPException(status_code=409, detail="端口切换中，请稍后重试")

    raw = payload.get("port") if isinstance(payload, dict) else None
    try:
        next_port = int(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="端口无效：请输入 1-65535 的整数")
    if next_port < 1 or next_port > 65535:
        raise HTTPException(status_code=400, detail="端口无效：请输入 1-65535 的整数")

    current_port, _ = read_effective_backend_port(default=DEFAULT_BACKEND_PORT)
    if next_port == int(current_port):
        write_backend_port_setting(next_port)
        env_file = write_backend_port_env_file(next_port)
        host = _format_host_for_url(_get_backend_access_host())
        return {
            "success": True,
            "changed": False,
            "port": next_port,
            "ui_url": f"http://{host}:{next_port}/",
            "env_file": str(env_file) if env_file else None,
        }

    bind_host = _get_backend_bind_host()
    if not _is_port_available(next_port, bind_host):
        raise HTTPException(status_code=409, detail=f"端口 {next_port} 已被占用，请换一个端口")

    proc = None
    _PORT_CHANGE_IN_PROGRESS = True
    try:
        try:
            proc = _spawn_backend_process(next_port)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"启动新后端进程失败：{e}")

        access_host = _get_backend_access_host()
        health_url = f"http://{_format_host_for_url(access_host)}:{next_port}/api/health"
        ok = await _wait_for_backend_ready(health_url, timeout_s=30.0)
        if not ok:
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"新端口启动超时：{health_url}")

        # Persist only after the new backend is confirmed ready.
        write_backend_port_setting(next_port)
        env_file = write_backend_port_env_file(next_port)

        background_tasks.add_task(_exit_process_after, 0.2)

        host = _format_host_for_url(access_host)
        return {
            "success": True,
            "changed": True,
            "port": next_port,
            "ui_url": f"http://{host}:{next_port}/",
            "env_file": str(env_file) if env_file else None,
        }
    finally:
        _PORT_CHANGE_IN_PROGRESS = False
