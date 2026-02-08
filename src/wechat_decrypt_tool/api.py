"""微信解密工具的FastAPI Web服务器"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from .logging_config import setup_logging, get_logger
from .path_fix import PathFixRoute
from .chat_realtime_autosync import CHAT_REALTIME_AUTOSYNC
from .routers.chat import router as _chat_router
from .routers.chat_contacts import router as _chat_contacts_router
from .routers.chat_export import router as _chat_export_router
from .routers.chat_media import router as _chat_media_router
from .routers.decrypt import router as _decrypt_router
from .routers.health import router as _health_router
from .routers.keys import router as _keys_router
from .routers.media import router as _media_router
from .routers.sns import router as _sns_router
from .routers.wechat_detection import router as _wechat_detection_router
from .routers.wrapped import router as _wrapped_router
from .wcdb_realtime import WCDB_REALTIME, shutdown as _wcdb_shutdown

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="微信数据库解密工具",
    description="现代化的微信数据库解密工具，支持微信信息检测和数据库解密功能",
    version="0.1.0",
)

# 设置自定义路由类
app.router.route_class = PathFixRoute

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(_health_router)
app.include_router(_wechat_detection_router)
app.include_router(_decrypt_router)
app.include_router(_keys_router)
app.include_router(_media_router)
app.include_router(_chat_router)
app.include_router(_chat_contacts_router)
app.include_router(_chat_export_router)
app.include_router(_chat_media_router)
app.include_router(_sns_router)
app.include_router(_wrapped_router)


class _SPAStaticFiles(StaticFiles):
    """StaticFiles with a SPA fallback (Nuxt generate output)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fallback_200 = Path(str(self.directory)) / "200.html"
        self._fallback_index = Path(str(self.directory)) / "index.html"

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise

            # For client-side routes (no file extension), return Nuxt's SPA fallback.
            name = Path(path).name
            if "." in name:
                raise

            if self._fallback_200.exists():
                return FileResponse(str(self._fallback_200))
            return FileResponse(str(self._fallback_index))


def _maybe_mount_frontend() -> None:
    """Serve the generated Nuxt static site at `/` if present.

    This keeps web + desktop UI identical when the desktop shell (Electron) loads
    http://127.0.0.1:<port>/ from the same backend that serves `/api/*`.
    """

    ui_dir_env = os.environ.get("WECHAT_TOOL_UI_DIR", "").strip()

    candidates: list[Path] = []
    if ui_dir_env:
        candidates.append(Path(ui_dir_env))

    # Repo default: `frontend/.output/public` after `npm --prefix frontend run generate`.
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "frontend" / ".output" / "public")

    ui_dir: Path | None = None
    for p in candidates:
        try:
            if (p / "index.html").is_file():
                ui_dir = p
                break
        except Exception:
            continue

    if not ui_dir:
        return

    try:
        app.mount("/", _SPAStaticFiles(directory=str(ui_dir), html=True), name="ui")
        logger.info("Serving frontend UI from: %s", ui_dir)
    except Exception:
        logger.exception("Failed to mount frontend UI from: %s", ui_dir)


_maybe_mount_frontend()


@app.on_event("startup")
async def _startup_background_jobs() -> None:
    try:
        CHAT_REALTIME_AUTOSYNC.start()
    except Exception:
        logger.exception("Failed to start realtime autosync service")


@app.on_event("shutdown")
async def _shutdown_wcdb_realtime() -> None:
    try:
        CHAT_REALTIME_AUTOSYNC.stop()
    except Exception:
        pass
    close_ok = False
    lock_timeout_s: float | None = 0.2
    try:
        raw = str(os.environ.get("WECHAT_TOOL_WCDB_SHUTDOWN_LOCK_TIMEOUT_S", "0.2") or "").strip()
        lock_timeout_s = float(raw) if raw else 0.2
        if lock_timeout_s <= 0:
            lock_timeout_s = None
    except Exception:
        lock_timeout_s = 0.2
    try:
        close_ok = WCDB_REALTIME.close_all(lock_timeout_s=lock_timeout_s)
    except Exception:
        close_ok = False
    if close_ok:
        try:
            _wcdb_shutdown()
        except Exception:
            pass
    else:
        # If some conn locks were busy, other threads may still be running WCDB calls; avoid shutting down the lib.
        logger.warning("[wcdb] close_all not fully completed; skip wcdb_shutdown")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("WECHAT_TOOL_HOST", "127.0.0.1")
    port = int(os.environ.get("WECHAT_TOOL_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
