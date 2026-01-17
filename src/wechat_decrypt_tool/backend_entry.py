"""Entry point for bundling the FastAPI backend into a standalone executable.

This avoids dynamic import strings like "pkg.module:app" which some bundlers
cannot detect reliably.
"""

import os

import uvicorn

from wechat_decrypt_tool.api import app


def main() -> None:
    host = os.environ.get("WECHAT_TOOL_HOST", "127.0.0.1")
    port = int(os.environ.get("WECHAT_TOOL_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
