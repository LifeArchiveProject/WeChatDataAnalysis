from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from ..path_fix import PathFixRoute
from ..wrapped.service import build_wrapped_annual_card, build_wrapped_annual_meta, build_wrapped_annual_response

router = APIRouter(route_class=PathFixRoute)


@router.get("/api/wrapped/annual", summary="微信聊天年度总结（WeChat Wrapped）- 后端数据")
async def wrapped_annual(
    year: Optional[int] = Query(None, description="年份（例如 2026）。默认当前年份。"),
    account: Optional[str] = Query(None, description="解密后的账号目录名。默认取第一个可用账号。"),
    refresh: bool = Query(False, description="是否强制重新计算（忽略缓存）。"),
):
    """返回年度总结完整数据（一次性包含全部卡片，可能较慢）。"""

    # This endpoint performs blocking sqlite/file IO, so run it in a worker thread.
    return await asyncio.to_thread(build_wrapped_annual_response, account=account, year=year, refresh=refresh)


@router.get("/api/wrapped/annual/meta", summary="微信聊天年度总结（WeChat Wrapped）- 目录（轻量）")
async def wrapped_annual_meta(
    year: Optional[int] = Query(None, description="年份（例如 2026）。默认当前年份。"),
    account: Optional[str] = Query(None, description="解密后的账号目录名。默认取第一个可用账号。"),
    refresh: bool = Query(False, description="是否强制重新计算（忽略缓存）。"),
):
    """返回年度总结的目录/元信息，用于前端懒加载每一页。"""

    return await asyncio.to_thread(build_wrapped_annual_meta, account=account, year=year, refresh=refresh)


@router.get("/api/wrapped/annual/cards/{card_id}", summary="微信聊天年度总结（WeChat Wrapped）- 单张卡片（按页加载）")
async def wrapped_annual_card(
    card_id: int = Path(..., description="卡片ID（与前端页面一一对应）", ge=0),
    year: Optional[int] = Query(None, description="年份（例如 2026）。默认当前年份。"),
    account: Optional[str] = Query(None, description="解密后的账号目录名。默认取第一个可用账号。"),
    refresh: bool = Query(False, description="是否强制重新计算（忽略缓存）。"),
):
    """按卡片 ID 返回单页数据（避免首屏一次性计算全部卡片）。"""

    try:
        return await asyncio.to_thread(
            build_wrapped_annual_card,
            account=account,
            year=year,
            card_id=card_id,
            refresh=refresh,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
