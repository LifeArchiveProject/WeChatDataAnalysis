"""Entry point for bundling the FastAPI backend into a standalone executable.

This avoids dynamic import strings like "pkg.module:app" which some bundlers
cannot detect reliably.
"""

import multiprocessing

# PyInstaller/frozen Windows builds re-launch this executable for
# multiprocessing workers.  The memory/DLL key scanners use process pools; if
# we import and start the FastAPI app before freeze_support() has a chance to
# divert worker processes, every worker tries to bind the backend port again.
if __name__ == "__main__":
    multiprocessing.freeze_support()

import uvicorn

from wechat_decrypt_tool.desktop_parent_watchdog import (
    start_desktop_parent_watchdog_from_env,
)
from wechat_decrypt_tool.native_core_client import configure_native_core_entrypoint
from wechat_decrypt_tool.runtime_settings import (
    read_effective_backend_host,
    read_effective_backend_port,
)


def main() -> None:
    start_desktop_parent_watchdog_from_env()
    configure_native_core_entrypoint()
    from wechat_decrypt_tool.api import app

    host, _ = read_effective_backend_host(default="127.0.0.1")
    port, _ = read_effective_backend_port(default=10392)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
