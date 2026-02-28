#!/usr/bin/env python3
"""
微信解密工具主启动脚本

使用方法:
    uv run main.py

默认在10392端口启动API服务
"""

import uvicorn
import os
from pathlib import Path
from wechat_decrypt_tool.runtime_settings import read_effective_backend_port

def main():
    """启动微信解密工具API服务"""
    host = os.environ.get("WECHAT_TOOL_HOST", "127.0.0.1")
    port, port_source = read_effective_backend_port(default=10392)
    access_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host

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
    print(f"API文档: http://{access_host}:{port}/docs")
    print(f"健康检查: http://{access_host}:{port}/api/health")
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    repo_root = Path(__file__).resolve().parent
    enable_reload = os.environ.get("WECHAT_TOOL_RELOAD", "0") == "1"

    # 启动API服务
    uvicorn.run(
        "wechat_decrypt_tool.api:app",
        host=host,
        port=port,
        reload=enable_reload,
        reload_dirs=[str(repo_root / "src")] if enable_reload else None,
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
