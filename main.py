#!/usr/bin/env python3
"""
微信解密工具主启动脚本

使用方法:
    uv run main.py

默认在10392端口启动API服务
"""

import multiprocessing
import os
import sys
from pathlib import Path

# Keep standalone/frozen launches safe when scanner code uses multiprocessing.
if __name__ == "__main__":
    multiprocessing.freeze_support()

# Source launches must run this checkout's src/, not the copy that
# `uv sync --no-editable` froze into site-packages. Keep this above every
# project import.
SRC_DIR = Path(__file__).resolve().parent / "src"
if SRC_DIR.is_dir():
    if str(SRC_DIR) in sys.path:
        sys.path.remove(str(SRC_DIR))
    sys.path.insert(0, str(SRC_DIR))

import uvicorn

import wechat_decrypt_tool
from wechat_decrypt_tool.desktop_parent_watchdog import (
    start_desktop_parent_watchdog_from_env,
)
from wechat_decrypt_tool.native_core_client import configure_native_core_entrypoint
from wechat_decrypt_tool.network_access import get_lan_access_host
from wechat_decrypt_tool.runtime_settings import (
    read_effective_backend_host,
    read_effective_backend_port,
)


def main():
    """启动微信解密工具API服务"""
    start_desktop_parent_watchdog_from_env()
    configure_native_core_entrypoint()
    host, host_source = read_effective_backend_host(default="127.0.0.1")
    port, port_source = read_effective_backend_port(default=10392)
    access_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    lan_access_host = get_lan_access_host(default="127.0.0.1") if host in {"0.0.0.0", "::"} else access_host

    print("=" * 60)
    print("微信解密工具 API 服务")
    print("=" * 60)
    print("正在启动服务...")
    if port_source == "env":
        print("端口来源: 环境变量 WECHAT_TOOL_PORT")
    elif port_source == "settings":
        print("端口来源: 配置文件 output/runtime_settings.json（由网页/桌面设置写入）")
    else:
        print("端口来源: 默认值")
    if host_source == "env":
        print("监听地址来源: 环境变量 WECHAT_TOOL_HOST")
    elif host_source == "settings":
        print("监听地址来源: 配置文件 output/runtime_settings.json（由网页/桌面设置写入）")
    else:
        print("监听地址来源: 默认值")
    print(f"监听地址: {host}")
    code_source = str(Path(wechat_decrypt_tool.__file__).resolve())
    try:
        print(f"代码来源: {code_source}")
    except UnicodeEncodeError:
        # 标准输出的编码表示不了仓库路径时，退回转义形式，不让这行诊断信息中断启动。
        print(f"代码来源: {ascii(code_source)}")
    print(f"API文档: http://{access_host}:{port}/docs")
    print(f"健康检查: http://{access_host}:{port}/api/health")
    if lan_access_host != access_host:
        print(f"局域网 MCP: http://{lan_access_host}:{port}/mcp")
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    enable_reload = os.environ.get("WECHAT_TOOL_RELOAD", "0") == "1"

    # 启动API服务
    uvicorn.run(
        "wechat_decrypt_tool.api:app",
        host=host,
        port=port,
        reload=enable_reload,
        reload_dirs=[str(SRC_DIR)] if enable_reload else None,
        reload_excludes=[
            "output/*",
            "output/**",
            "frontend/*",
            "frontend/**",
            ".venv/*",
            ".venv/**",
        ] if enable_reload else None,
        log_level="info"
    )

if __name__ == "__main__":
    main()
