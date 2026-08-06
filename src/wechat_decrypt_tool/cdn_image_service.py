"""CDN 原图下载服务客户端。

复用与 ``key_service.fetch_and_save_remote_keys`` 完全相同的 c3o.re 服务与鉴权
输入（账号文件夹名 + ``global_config`` / ``global_config.crc``），把「云端解析图片
密钥」的既有管道延伸到「拉取原图」：

1. ``POST https://view.free.c3o.re/api/token``（multipart：weixinIDFolder / fileBytes /
   crcBytes）换取 Bearer token，按账号缓存。
2. ``GET  https://wxcdn.c3o.re/download?fileid=<id>&type=orig[&key=<aes_hex>]``，
   头部带 ``Authorization: Bearer <token>``，返回（必要时已 AES-ECB 解密的）原图字节。

仅在本地找不到原图、且用户未关闭「自动获取原图(CDN)」时才会被调用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx

from .app_paths import get_data_dir
from .key_service import (
    _resolve_wxid_dir_for_image_key,
    get_wechat_internal_global_config,
)

logger = logging.getLogger(__name__)

TOKEN_URL = "https://view.free.c3o.re/api/token"
DOWNLOAD_URL = "https://wxcdn.c3o.re/download"

# 本地限次：同一账号每天最多从 CDN 下载多少张原图。
DAILY_DOWNLOAD_LIMIT = 10
_QUOTA_FILE_NAME = "cdn_image_quota.json"
_quota_lock = threading.Lock()


class CdnQuotaExceededError(RuntimeError):
    """当账号当天 CDN 原图下载次数已达上限时抛出。"""


def _quota_path() -> Path:
    return get_data_dir() / _QUOTA_FILE_NAME


def _today_str() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _read_quota_entry(wxid: str) -> int:
    """返回该账号今天已用的下载次数（跨天自动归零）。"""
    try:
        raw = json.loads(_quota_path().read_text(encoding="utf-8"))
    except Exception:
        return 0
    entry = (raw or {}).get(wxid) or {}
    if str(entry.get("date") or "") != _today_str():
        return 0
    try:
        return max(0, int(entry.get("count") or 0))
    except (TypeError, ValueError):
        return 0


def get_quota_remaining(wxid: str) -> int:
    with _quota_lock:
        return max(0, DAILY_DOWNLOAD_LIMIT - _read_quota_entry(wxid))


def _consume_quota(wxid: str) -> None:
    """成功下载一张后 +1（只有真正取回原图才消耗配额）。"""
    with _quota_lock:
        path = _quota_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}
        today = _today_str()
        entry = raw.get(wxid) or {}
        count = _read_quota_entry(wxid)  # already day-aware
        raw[wxid] = {"date": today, "count": count + 1}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[cdn_image] 写入下载配额失败: %s", exc)


# ---- 设置：自动获取原图(CDN)开关，默认关闭，用户可主动开启 ----
_SETTINGS_FILE_NAME = "cdn_image_settings.json"


def _settings_path() -> Path:
    return get_data_dir() / _SETTINGS_FILE_NAME


def is_cdn_download_enabled() -> bool:
    """是否启用「本地缺原图时自动从 CDN 获取」。默认关闭。"""
    try:
        raw = json.loads(_settings_path().read_text(encoding="utf-8"))
        return bool((raw or {}).get("enabled", False))
    except Exception:
        return False


def set_cdn_download_enabled(enabled: bool) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"enabled": bool(enabled)}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[cdn_image] 写入设置失败: %s", exc)

# token 有效期未在契约中给出，保守地按较短窗口缓存并在 401 时强制刷新。
_TOKEN_TTL_SECONDS = 45 * 60

# account(wxid 文件夹名) -> (token, expires_at_unix)
_token_cache: Dict[str, Tuple[str, float]] = {}
# 每个账号一把锁，避免并发首图同时打 /api/token。
_token_locks: Dict[str, asyncio.Lock] = {}


def _lock_for(wxid: str) -> asyncio.Lock:
    lock = _token_locks.get(wxid)
    if lock is None:
        lock = asyncio.Lock()
        _token_locks[wxid] = lock
    return lock


def clear_cached_token(account: Optional[str] = None) -> None:
    """清掉 token 缓存（账号切换 / 显式失效时）。"""
    if account:
        _token_cache.pop(str(account).strip(), None)
    else:
        _token_cache.clear()


async def fetch_cdn_token(
    account: Optional[str] = None,
    *,
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
    force: bool = False,
) -> str:
    """换取（并缓存）该账号的 CDN Bearer token。"""
    wx_id_dir = _resolve_wxid_dir_for_image_key(
        account,
        wxid_dir=wxid_dir,
        db_storage_path=db_storage_path,
    )
    wxid = wx_id_dir.name

    now = time.time()
    cached = _token_cache.get(wxid)
    if cached and not force and cached[1] > now:
        return cached[0]

    async with _lock_for(wxid):
        cached = _token_cache.get(wxid)
        if cached and not force and cached[1] > time.time():
            return cached[0]

        try:
            blob1 = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config")
            blob2 = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config.crc")
        except Exception as exc:  # noqa: BLE001 - 统一成一个可读错误
            raise RuntimeError(f"读取微信内部文件失败: {exc}") from exc

        files = {
            "fileBytes": ("file", blob1, "application/octet-stream"),
            "crcBytes": ("file.crc", blob2, "application/octet-stream"),
        }
        data = {"weixinIDFolder": wxid}

        logger.info("[cdn_image] 请求 CDN token: url=%s wxid=%s", TOKEN_URL, wxid)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(TOKEN_URL, data=data, files=files)
        if resp.status_code != 200:
            raise RuntimeError(
                f"CDN token 请求失败: {resp.status_code} - {resp.text[:120]}"
            )
        token = str((resp.json() or {}).get("token") or "").strip()
        if not token:
            raise RuntimeError("CDN token 返回为空")

        _token_cache[wxid] = (token, time.time() + _TOKEN_TTL_SECONDS)
        logger.info("[cdn_image] CDN token 获取成功: wxid=%s", wxid)
        return token


async def download_original_image(
    account: Optional[str],
    fileid: str,
    *,
    aes_key_hex: str = "",
    image_type: str = "orig",
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> bytes:
    """按 fileid 从 CDN 拉取原图字节；token 过期(401)自动刷新一次重试。"""
    fileid = str(fileid or "").strip()
    if not fileid:
        raise ValueError("缺少 fileid，无法从 CDN 获取原图")

    wxid = _resolve_wxid_dir_for_image_key(
        account, wxid_dir=wxid_dir, db_storage_path=db_storage_path
    ).name
    if get_quota_remaining(wxid) <= 0:
        raise CdnQuotaExceededError(
            f"账号 {wxid} 今日 CDN 原图下载已达上限（每天 {DAILY_DOWNLOAD_LIMIT} 次）"
        )

    params: Dict[str, str] = {"fileid": fileid, "type": image_type}
    aes_key_hex = str(aes_key_hex or "").strip()
    if aes_key_hex:
        params["key"] = aes_key_hex

    async def _do(token: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=60) as client:
            return await client.get(DOWNLOAD_URL, params=params, headers=headers)

    token = await fetch_cdn_token(
        account, wxid_dir=wxid_dir, db_storage_path=db_storage_path
    )
    resp = await _do(token)
    if resp.status_code in (401, 403):
        clear_cached_token(_resolve_wxid_dir_for_image_key(
            account, wxid_dir=wxid_dir, db_storage_path=db_storage_path
        ).name)
        token = await fetch_cdn_token(
            account, wxid_dir=wxid_dir, db_storage_path=db_storage_path, force=True
        )
        resp = await _do(token)

    if resp.status_code != 200:
        raise RuntimeError(f"CDN 原图下载失败: {resp.status_code} - {resp.text[:120]}")
    data = resp.content
    if not data:
        raise RuntimeError("CDN 原图下载返回为空")
    _consume_quota(wxid)
    logger.info(
        "[cdn_image] 原图下载成功: fileid=%s bytes=%s 今日剩余=%s",
        fileid,
        len(data),
        get_quota_remaining(wxid),
    )
    return data
