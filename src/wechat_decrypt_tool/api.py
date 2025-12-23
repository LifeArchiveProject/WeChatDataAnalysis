"""微信解密工具的FastAPI Web服务器"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logging_config import setup_logging, get_logger
from .path_fix import PathFixRoute
from .routers.chat import router as _chat_router
from .routers.chat_export import router as _chat_export_router
from .routers.chat_media import router as _chat_media_router
from .routers.decrypt import router as _decrypt_router
from .routers.health import router as _health_router
from .routers.media import router as _media_router
from .routers.wechat_detection import router as _wechat_detection_router

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
app.include_router(_media_router)
app.include_router(_chat_router)
app.include_router(_chat_export_router)
app.include_router(_chat_media_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
