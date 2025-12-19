from fastapi import APIRouter

from ..logging_config import get_logger
from ..path_fix import PathFixRoute

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


@router.get("/", summary="根端点")
async def root():
    """根端点"""
    logger.info("访问根端点")
    return {"message": "微信数据库解密工具 API"}


@router.get("/api/health", summary="健康检查端点")
async def health_check():
    """健康检查端点"""
    logger.debug("健康检查请求")
    return {"status": "healthy", "service": "微信解密工具"}
