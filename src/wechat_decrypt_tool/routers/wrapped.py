from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Query

from ..path_fix import PathFixRoute
from ..wrapped.service import build_wrapped_annual_response

router = APIRouter(route_class=PathFixRoute)


@router.get("/api/wrapped/annual", summary="微信聊天年度总结（WeChat Wrapped）- 后端数据")
async def wrapped_annual(
    year: Optional[int] = Query(None, description="年份（例如 2026）。默认当前年份。"),
    account: Optional[str] = Query(None, description="解密后的账号目录名。默认取第一个可用账号。"),
    refresh: bool = Query(False, description="是否强制重新计算（忽略缓存）。"),
):
    """返回年度总结数据（目前仅实现第 1 个点子：年度赛博作息表）。"""

    # This endpoint performs blocking sqlite/file IO, so run it in a worker thread.
    return await asyncio.to_thread(build_wrapped_annual_response, account=account, year=year, refresh=refresh)
