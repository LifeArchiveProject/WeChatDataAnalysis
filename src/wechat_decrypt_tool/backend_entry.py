"""Entry point for bundling the FastAPI backend into a standalone executable.

This avoids dynamic import strings like "pkg.module:app" which some bundlers
cannot detect reliably.
"""

import multiprocessing
import json
import os
import sys

# PyInstaller/frozen Windows builds re-launch this executable for
# multiprocessing workers.  The memory/DLL key scanners use process pools; if
# we import and start the FastAPI app before freeze_support() has a chance to
# divert worker processes, every worker tries to bind the backend port again.
if __name__ == "__main__":
    multiprocessing.freeze_support()

def _run_opencc_smoke() -> None:
    from opencc import OpenCC
    import opencc

    converter = OpenCC("t2s")
    payload = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "openccModule": str(getattr(opencc, "__file__", "") or ""),
        "results": {
            "繁體中文": converter.convert("繁體中文"),
            "軟體與資料庫": converter.convert("軟體與資料庫"),
        },
    }
    print(json.dumps(payload, ensure_ascii=True))


def main() -> None:
    if "--smoke-opencc" in sys.argv[1:]:
        _run_opencc_smoke()
        return

    import uvicorn

    from wechat_decrypt_tool.api import app
    from wechat_decrypt_tool.runtime_settings import read_effective_backend_host, read_effective_backend_port

    host, _ = read_effective_backend_host(default="127.0.0.1")
    port, _ = read_effective_backend_port(default=10392)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
