"""Entry point for bundling the FastAPI backend into a standalone executable.

This avoids dynamic import strings like "pkg.module:app" which some bundlers
cannot detect reliably.
"""

import os

import uvicorn

from wechat_decrypt_tool.api import app
from wechat_decrypt_tool.runtime_settings import read_effective_backend_port


def main() -> None:
    host = os.environ.get("WECHAT_TOOL_HOST", "127.0.0.1")
    port, _ = read_effective_backend_port(default=10392)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
