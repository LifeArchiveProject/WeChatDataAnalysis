"""WxCDN 套餐 / 连接 / 兑换接口。

Worker 或网络故障从不变成 500：``GET /api/cdn/plan`` 把错误放进
``snapshot["error"]`` 并以 200 返回；主动操作（connect / redeem）则把
Worker 的状态码与 ``code`` 原样透传，并带上 ``Retry-After``。
任何响应都不包含 token，也不包含兑换剩余尝试次数。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import cdn_image_service as svc

logger = logging.getLogger(__name__)

router = APIRouter()

_QUOTA_STALE_SECONDS = 60


def _error_payload(err: Exception) -> Dict[str, Any]:
    if isinstance(err, svc.CdnError):
        payload: Dict[str, Any] = {"code": err.code, "message": err.message}
        if err.retry_after is not None:
            payload["retryAfterSeconds"] = int(err.retry_after)
        if err.locked_until is not None:
            payload["lockedUntil"] = int(err.locked_until)
        return payload
    return {"code": "internal_error", "message": str(err) or err.__class__.__name__}


def _http_error(err: svc.CdnError) -> HTTPException:
    return HTTPException(
        status_code=int(err.status),
        detail=_error_payload(err),
        headers=err.headers() or None,
    )


def _clean_account(value: Optional[str]) -> str:
    return str(value or "").strip()


@router.get("/api/cdn/plan", summary="获取 WxCDN 套餐与额度快照")
async def get_cdn_plan(account: Optional[str] = None, refresh: bool = False):
    account = _clean_account(account)
    snapshot = svc.get_plan_snapshot(account)
    if not snapshot.get("wxid"):
        snapshot["error"] = {"code": "account_unresolved", "message": "无法定位该账号的微信数据目录"}
        return snapshot

    error: Optional[Exception] = None
    try:
        if snapshot.get("connected"):
            fetched_at = snapshot.get("quotaFetchedAt")
            stale = fetched_at is None or (time.time() - float(fetched_at)) > _QUOTA_STALE_SECONDS
            if refresh or stale:
                await svc.fetch_quota(account, force=bool(refresh))
        elif not snapshot.get("frozen"):
            await svc.ensure_token(account)
            if refresh:
                await svc.fetch_quota(account, force=True)
    except svc.CdnError as err:
        error = err
    except Exception as err:  # noqa: BLE001 - 网络/未知错误也不能 500
        logger.info("[cdn] 刷新套餐失败: account=%s error=%s", account, str(err)[:200])
        error = err

    snapshot = svc.get_plan_snapshot(account)
    if error is not None:
        snapshot["error"] = _error_payload(error)
    return snapshot


class CdnAccountRequest(BaseModel):
    account: str


@router.post("/api/cdn/connect", summary="签发/刷新 WxCDN token 并拉取额度")
async def connect_cdn(req: CdnAccountRequest):
    account = _clean_account(req.account)
    try:
        await svc.ensure_token(account, force=True)
        await svc.fetch_quota(account, force=True)
    except svc.CdnError as err:
        raise _http_error(err)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail={"code": "account_unresolved", "message": str(err)})
    return svc.get_plan_snapshot(account)


class CdnRedeemRequest(BaseModel):
    account: str
    code: str


@router.post("/api/cdn/redeem", summary="提交 WxCDN 兑换码")
async def redeem_cdn(req: CdnRedeemRequest):
    account = _clean_account(req.account)
    try:
        body = await svc.redeem_code(account, req.code)
    except svc.CdnError as err:
        raise _http_error(err)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail={"code": "account_unresolved", "message": str(err)})
    return {
        "redemption": body.get("redemption"),
        "account": body.get("account"),
        "quota": body.get("quota"),
        "snapshot": svc.get_plan_snapshot(account),
    }


class CdnTokenDurationRequest(BaseModel):
    value: str


@router.post("/api/cdn/token_duration", summary="设置 WxCDN token 有效期")
async def set_cdn_token_duration(req: CdnTokenDurationRequest):
    try:
        value = svc.set_token_duration(req.value)
    except ValueError as err:
        raise HTTPException(status_code=400, detail={"code": "invalid_token_duration", "message": str(err)})
    return {"status": "success", "tokenDuration": value}
