"""WxCDN（https://wxcdn.c3o.re）客户端：签发 token、查询额度、兑换、下载媒体。

与 ``key_service.fetch_and_save_remote_keys`` 使用同一份鉴权输入（账号文件夹名 +
``global_config`` / ``global_config.crc``），Worker 契约见 wxcdn-api.md：

1. ``POST /token``（multipart：weixinIDFolder / fileBytes / crcBytes / tokenDuration）
   签发 Bearer token，同时返回 account + quota。
2. ``GET /quota``、``POST /redeem``、``GET /download`` 均带 ``Authorization: Bearer``。
3. 下载优先在本地 AES-ECB 解密；解不出可识别文件时才回退一次带 ``key=`` 的服务端解密。

每个 wxid 的 token / 套餐 / 额度 / 最近下载记录持久化在
``get_data_dir()/cdn_account_state.json``。token 永远不写进日志。
"""

from __future__ import annotations

import asyncio
import email.utils
import json
import logging
import os
import re
import threading
import time
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from .app_paths import get_data_dir
from .key_service import (
    _resolve_wxid_dir_for_image_key,
    get_wechat_internal_global_config,
)

logger = logging.getLogger(__name__)

WORKER_BASE_URL = "https://wxcdn.c3o.re"
TOKEN_URL = f"{WORKER_BASE_URL}/token"
QUOTA_URL = f"{WORKER_BASE_URL}/quota"
REDEEM_URL = f"{WORKER_BASE_URL}/redeem"
DOWNLOAD_URL = f"{WORKER_BASE_URL}/download"

TOKEN_DURATIONS = ("short", "medium", "long")
DEFAULT_TOKEN_DURATION = "medium"

MEDIA_TYPES = frozenset(
    {"orig", "normal", "thumb", "video", "file", "bigfile", "voice", "live", "origlive"}
)
# 这些类型的解密结果必须以已知文件头开头才算解密成功。
_IMAGE_LIKE_MEDIA_TYPES = frozenset({"orig", "normal", "thumb", "live", "origlive"})

# token 到期前多少秒就视为需要刷新。
_TOKEN_REFRESH_MARGIN_SECONDS = 300
# 进程级：两次 /token 调用之间的最小间隔（Worker 按 IP 每 10 秒 3 次限频）。
_TOKEN_MIN_INTERVAL_SECONDS = 4.0
# /token 被限频却没给 Retry-After、或网络不通时，多久之内不再自动重试。
_TOKEN_RATE_LIMIT_DEFAULT_BACKOFF_SECONDS = 10
_TOKEN_NETWORK_ERROR_BACKOFF_SECONDS = 30
_RECENT_LIMIT = 50

_SETTINGS_FILE_NAME = "cdn_image_settings.json"
_STATE_FILE_NAME = "cdn_account_state.json"
_LEGACY_QUOTA_FILE_NAME = "cdn_image_quota.json"

_TOKEN_FIELDS = ("token", "tokenDuration", "issuedAt", "expiresAt")


def _now() -> float:
    return time.time()


async def _sleep(seconds: float) -> None:
    """闸门等待；单独包一层方便测试替换。"""
    await asyncio.sleep(seconds)


def _make_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """构造 httpx 客户端；测试可 monkeypatch 成 MockTransport。"""
    kwargs.setdefault("timeout", 30)
    return httpx.AsyncClient(**kwargs)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class CdnError(RuntimeError):
    """Worker 返回的可分类错误（以及网络/配置类错误）。"""

    default_code = "cdn_error"
    default_status = 502

    def __init__(
        self,
        message: str = "",
        *,
        code: Optional[str] = None,
        status: Optional[int] = None,
        retry_after: Optional[int] = None,
        quota: Optional[Dict[str, Any]] = None,
        locked_until: Optional[int] = None,
    ) -> None:
        self.code = str(code or self.default_code)
        self.status = int(status if status is not None else self.default_status)
        self.message = str(message or self.code)
        self.retry_after = retry_after
        self.quota = quota
        self.locked_until = locked_until
        super().__init__(self.message)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"{type(self).__name__}(code={self.code!r}, status={self.status}, message={self.message!r})"

    def to_detail(self) -> Dict[str, Any]:
        detail: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.retry_after is not None:
            detail["retryAfterSeconds"] = int(self.retry_after)
        if self.locked_until is not None:
            detail["lockedUntil"] = int(self.locked_until)
        if self.quota is not None:
            detail["quota"] = self.quota
        return detail

    def headers(self) -> Dict[str, str]:
        if self.retry_after is not None:
            return {"Retry-After": str(max(0, int(self.retry_after)))}
        return {}


class CdnInvalidTokenError(CdnError):
    default_code = "invalid_token"
    default_status = 401


class CdnAccountFrozenError(CdnError):
    default_code = "account_frozen"
    default_status = 403


class CdnRateLimitedError(CdnError):
    default_code = "rate_limited"
    default_status = 429


class CdnQuotaExceededError(CdnError):
    """额度不足（429 quota_exceeded）。chat_media 依赖这个名字。"""

    default_code = "quota_exceeded"
    default_status = 429


class CdnRedeemError(CdnError):
    default_code = "invalid_redeem_code"
    default_status = 400


_REDEEM_CODES = frozenset(
    {
        "invalid_redeem_code",
        "redeem_code_used",
        "plan_not_upgraded",
        "redeem_code_expired",
        "redeem_code_revoked",
        "redeem_locked",
    }
)


def _parse_retry_after(resp: httpx.Response, body: Dict[str, Any]) -> Optional[int]:
    raw = resp.headers.get("Retry-After")
    if raw:
        text = str(raw).strip()
        try:
            return max(0, int(float(text)))
        except (TypeError, ValueError):
            pass
        # RFC 7231 允许 HTTP-date 形式（Cloudflare 的部分 429 就是这样）。
        try:
            when = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            when = None
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0, int(when.timestamp() - _now()))
    value = body.get("retryAfterSeconds")
    if value is not None:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            pass
    return None


def _safe_json(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _raise_for_worker_error(resp: httpx.Response, wxid: Optional[str] = None) -> None:
    """把非 2xx 响应翻译成对应的 CdnError 子类并抛出。2xx 直接返回。"""
    status = int(resp.status_code)
    if 200 <= status < 300:
        return
    body = _safe_json(resp)
    code = str(body.get("code") or "").strip()
    message = str(body.get("error") or body.get("message") or "").strip()
    retry_after = _parse_retry_after(resp, body)
    quota = body.get("quota") if isinstance(body.get("quota"), dict) else None
    locked_until: Optional[int] = None
    if body.get("lockedUntil") is not None:
        try:
            locked_until = int(body.get("lockedUntil"))
        except (TypeError, ValueError):
            locked_until = None

    if status == 401:
        raise CdnInvalidTokenError(message or "token 无效或已过期", code=code or "invalid_token", status=401)
    if status == 403:
        # 只有 Worker 明确说 account_frozen 才冻结；Cloudflare/WAF/代理返回的
        # 403（通常是 HTML、没有 code）只是暂时性错误，不能把账号锁死在本地。
        if code == "account_frozen":
            if wxid:
                _mark_frozen(wxid, message)
            raise CdnAccountFrozenError(message or "账号已被冻结", code=code, status=403)
        raise CdnError(
            message or "WxCDN 拒绝了请求 (HTTP 403)",
            code=code or "http_403",
            status=403,
            retry_after=retry_after,
        )
    if status == 429:
        if code == "quota_exceeded":
            raise CdnQuotaExceededError(
                message or "额度不足", code=code, status=429, retry_after=retry_after, quota=quota
            )
        if code == "redeem_locked":
            if locked_until is None and retry_after is not None:
                locked_until = int(_now()) + int(retry_after)
            raise CdnRedeemError(
                message or "兑换功能已临时锁定",
                code=code,
                status=429,
                retry_after=retry_after,
                locked_until=locked_until,
            )
        raise CdnRateLimitedError(
            message or "请求过于频繁", code=code or "rate_limited", status=429, retry_after=retry_after
        )
    if code in _REDEEM_CODES or code.startswith("redeem_"):
        raise CdnRedeemError(message or code, code=code, status=status, retry_after=retry_after)
    raise CdnError(
        message or f"Worker 返回 HTTP {status}",
        code=code or f"http_{status}",
        status=status,
        retry_after=retry_after,
    )


def _network_error(exc: Exception) -> CdnError:
    return CdnError(f"无法连接 WxCDN 服务: {exc.__class__.__name__}", code="network_error", status=502)


# ---------------------------------------------------------------------------
# 设置：开关 + token 时长（cdn_image_settings.json）
# ---------------------------------------------------------------------------


def _settings_path() -> Path:
    return get_data_dir() / _SETTINGS_FILE_NAME


def _read_settings() -> Dict[str, Any]:
    try:
        raw = json.loads(_settings_path().read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_settings(settings: Dict[str, Any]) -> None:
    path = _settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[cdn_image] 写入设置失败: %s", exc)


def is_cdn_download_enabled() -> bool:
    """是否启用「本地缺原图时自动从 CDN 获取」。默认关闭。"""
    return bool(_read_settings().get("enabled", False))


def set_cdn_download_enabled(enabled: bool) -> None:
    settings = _read_settings()
    settings["enabled"] = bool(enabled)
    _write_settings(settings)


def get_token_duration() -> str:
    value = str(_read_settings().get("tokenDuration") or "").strip().lower()
    return value if value in TOKEN_DURATIONS else DEFAULT_TOKEN_DURATION


def set_token_duration(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in TOKEN_DURATIONS:
        raise ValueError(f"tokenDuration 必须是 {', '.join(TOKEN_DURATIONS)} 之一")
    settings = _read_settings()
    settings["tokenDuration"] = normalized
    _write_settings(settings)
    return normalized


# ---------------------------------------------------------------------------
# 每个 wxid 的持久状态（cdn_account_state.json）
# ---------------------------------------------------------------------------

_state_lock = threading.RLock()
_legacy_cleanup_dirs: set[str] = set()
# 内存里的状态才是事实来源，文件只负责持久化：写盘失败只丢持久性，不丢 token。
# 按 data_dir 分桶，避免测试/切换数据目录时串数据。
_state_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _state_path() -> Path:
    return get_data_dir() / _STATE_FILE_NAME


def _cleanup_legacy_quota_file() -> None:
    try:
        data_dir = get_data_dir()
        key = str(data_dir)
        if key in _legacy_cleanup_dirs:
            return
        _legacy_cleanup_dirs.add(key)
        legacy = data_dir / _LEGACY_QUOTA_FILE_NAME
        if legacy.exists():
            legacy.unlink()
            logger.info("[cdn_image] 已删除旧的本地配额文件")
    except Exception:  # noqa: BLE001
        pass


def _empty_state() -> Dict[str, Any]:
    return {
        "token": None,
        "tokenDuration": None,
        "issuedAt": None,
        "expiresAt": None,
        "account": None,
        "quota": None,
        "quotaFetchedAt": None,
        "quotaSource": None,
        "frozen": False,
        "frozenAt": None,
        "redeemLockedUntil": None,
        "tokenRetryUntil": None,
        "lastError": None,
        "recent": [],
    }


def _read_state_file() -> Dict[str, Dict[str, Any]]:
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _load_all_state() -> Dict[str, Dict[str, Any]]:
    """返回当前 data_dir 对应的内存状态（首次访问时从文件加载）。

    返回的是缓存对象本身，调用方必须持有 ``_state_lock`` 再修改，并随后
    调用 ``_save_all_state`` 持久化。
    """
    _cleanup_legacy_quota_file()
    key = str(get_data_dir())
    with _state_lock:
        cached = _state_cache.get(key)
        if cached is None:
            cached = _read_state_file()
            _state_cache[key] = cached
        return cached


def _save_all_state(state: Dict[str, Dict[str, Any]]) -> None:
    path = _state_path()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except Exception:  # noqa: BLE001
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("[cdn_image] 写入账号状态失败: %s", exc)
        try:
            tmp.unlink()
        except Exception:  # noqa: BLE001
            pass


def _get_state(wxid: str) -> Dict[str, Any]:
    with _state_lock:
        merged = _empty_state()
        merged.update(_load_all_state().get(wxid) or {})
        return merged


def _get_token_retry_until(state: Dict[str, Any]) -> int:
    try:
        return int(state.get("tokenRetryUntil") or 0)
    except (TypeError, ValueError):
        return 0


def _update_state(wxid: str, **fields: Any) -> Dict[str, Any]:
    with _state_lock:
        state = _load_all_state()
        entry = _empty_state()
        entry.update(state.get(wxid) or {})
        entry.update(fields)
        state[wxid] = entry
        _save_all_state(state)
        return dict(entry)


def _mark_frozen(wxid: str, message: str = "") -> None:
    now = int(_now())
    _update_state(
        wxid,
        frozen=True,
        frozenAt=now,
        lastError={"code": "account_frozen", "message": message or "账号已被冻结", "at": now},
    )


def _set_last_error(wxid: str, err: CdnError, **extra: Any) -> None:
    now = int(_now())
    payload: Dict[str, Any] = {"code": err.code, "message": err.message, "at": now}
    fields: Dict[str, Any] = dict(extra)
    if err.quota is not None:
        payload["quota"] = err.quota
        if err.code == "quota_exceeded":
            # Worker 在 quota_exceeded 时附带的是最新额度，快照里的 quota 也要跟上。
            fields.update(quota=err.quota, quotaFetchedAt=now, quotaSource="download")
    fields["lastError"] = payload
    _update_state(wxid, **fields)


def _apply_worker_payload(
    wxid: str, body: Dict[str, Any], *, source: str, extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    fields: Dict[str, Any] = dict(extra or {})
    if isinstance(body.get("account"), dict):
        fields["account"] = body["account"]
    if isinstance(body.get("quota"), dict):
        fields["quota"] = body["quota"]
    if "account" in fields or "quota" in fields:
        fields["quotaFetchedAt"] = int(_now())
        fields["quotaSource"] = source
    return _update_state(wxid, **fields)


def _token_is_fresh(state: Dict[str, Any], now: float) -> bool:
    token = str(state.get("token") or "")
    if not token:
        return False
    try:
        expires_at = float(state.get("expiresAt") or 0)
    except (TypeError, ValueError):
        return False
    return expires_at - _TOKEN_REFRESH_MARGIN_SECONDS > now


def _local_wechat_roots() -> list:
    """本机微信数据根目录候选（xwechat_files 一级）。"""
    roots = []
    try:
        home = Path.home()
    except Exception:  # noqa: BLE001
        return roots
    roots.append(home / "Library" / "Containers" / "com.tencent.xinWeChat" / "Data" / "Documents" / "xwechat_files")
    roots.append(home / "Documents" / "xwechat_files")
    for env_key in ("WECHAT_TOOL_XWECHAT_FILES", "WECHAT_XWECHAT_FILES"):
        extra = str(os.environ.get(env_key) or "").strip()
        if extra:
            roots.append(Path(extra).expanduser())
    return roots


def _find_local_wxid_dir(account: Optional[str]) -> Optional[Path]:
    """账号目录反查失败时（例如从压缩包导入的账号），直接在本机 xwechat_files 里按 wxid 精确/前缀匹配。
    要求该目录含 db_storage，且根目录下有 all_users/config/global_config（签发 token 需要）。"""
    name = str(account or "").strip()
    if not name or "/" in name or "\\" in name:
        return None
    for root in _local_wechat_roots():
        try:
            if not root.is_dir() or not (root / "all_users" / "config" / "global_config").is_file():
                continue
            exact = root / name
            candidates = [exact] if exact.is_dir() else []
            candidates += sorted(
                (c for c in root.iterdir() if c.is_dir() and c.name.startswith(name + "_")),
                key=lambda c: c.stat().st_mtime,
                reverse=True,
            )
            for cand in candidates:
                if (cand / "db_storage").is_dir():
                    logger.info("[cdn_image] 通过本机 xwechat_files 匹配到 wxid_dir: account=%s dir=%s", name, str(cand))
                    return cand
        except Exception:  # noqa: BLE001
            continue
    return None


def _resolve_wxid(
    account: Optional[str],
    *,
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> Tuple[str, Path]:
    try:
        wx_id_dir = _resolve_wxid_dir_for_image_key(
            account, wxid_dir=wxid_dir, db_storage_path=db_storage_path
        )
    except Exception:
        if wxid_dir or db_storage_path:
            raise
        fallback = _find_local_wxid_dir(account)
        if fallback is None:
            raise
        wx_id_dir = fallback
    return wx_id_dir.name, wx_id_dir


def clear_cached_token(account: Optional[str] = None) -> None:
    """清掉 token（账号切换 / 显式失效时）。account 可以是账号名或 wxid。"""
    cleared = {name: None for name in _TOKEN_FIELDS}
    with _state_lock:
        state = _load_all_state()
        if account:
            keys = {str(account).strip()}
            try:
                keys.add(_resolve_wxid(str(account).strip())[0])
            except Exception:  # noqa: BLE001
                pass
        else:
            keys = set(state.keys())
        changed = False
        for key in keys:
            if key in state:
                state[key].update(cleared)
                changed = True
        if changed:
            _save_all_state(state)


# ---------------------------------------------------------------------------
# token
# ---------------------------------------------------------------------------

_token_locks: Dict[Tuple[int, str], asyncio.Lock] = {}
_last_token_request_at = 0.0
# 不是合法 wxid 的键，专门给进程级 /token 闸门用。
_TOKEN_GATE_KEY = "\x00token-gate"


def _lock_for(wxid: str) -> asyncio.Lock:
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = 0
    key = (loop_id, wxid)
    lock = _token_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _token_locks[key] = lock
    return lock


async def _request_token(wxid: str, wx_id_dir: Path) -> Dict[str, Any]:
    global _last_token_request_at
    try:
        blob1 = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config")
        blob2 = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config.crc")
    except Exception as exc:  # noqa: BLE001
        raise CdnError(
            f"读取微信配置文件失败: {exc}", code="config_unreadable", status=400
        ) from exc

    duration = get_token_duration()
    files = {
        "fileBytes": ("global_config", blob1, "application/octet-stream"),
        "crcBytes": ("global_config.crc", blob2, "application/octet-stream"),
    }
    data = {"weixinIDFolder": wxid, "tokenDuration": duration}

    # 进程级串行：Worker 按 IP 限频，不同 wxid 也不能同时打 /token。
    async with _lock_for(_TOKEN_GATE_KEY):
        wait = _last_token_request_at + _TOKEN_MIN_INTERVAL_SECONDS - _now()
        if wait > 0:
            await _sleep(wait)
        _last_token_request_at = _now()

        logger.info("[cdn_image] 请求 CDN token: wxid=%s duration=%s", wxid, duration)
        try:
            async with _make_async_client(timeout=30) as client:
                resp = await client.post(TOKEN_URL, data=data, files=files)
        except (httpx.HTTPError, OSError) as exc:
            err = _network_error(exc)
            err.retry_after = _TOKEN_NETWORK_ERROR_BACKOFF_SECONDS
            _set_last_error(wxid, err, tokenRetryUntil=int(_now()) + _TOKEN_NETWORK_ERROR_BACKOFF_SECONDS)
            raise err from exc
    try:
        _raise_for_worker_error(resp, wxid)
    except CdnAccountFrozenError:
        raise  # _mark_frozen 已经写了 lastError
    except CdnRateLimitedError as err:
        backoff = err.retry_after if err.retry_after is not None else _TOKEN_RATE_LIMIT_DEFAULT_BACKOFF_SECONDS
        _set_last_error(wxid, err, tokenRetryUntil=int(_now()) + int(backoff))
        raise
    except CdnError as err:
        _set_last_error(wxid, err)
        raise
    body = _safe_json(resp)
    token = str(body.get("token") or "").strip()
    if not token:
        raise CdnError("CDN token 返回为空", code="empty_token", status=502)

    now = int(_now())
    issued_at = body.get("issuedAt") or now
    expires_at = body.get("expiresAt")
    if expires_at is None and body.get("expiresIn") is not None:
        expires_at = int(issued_at) + int(body["expiresIn"])
    state = _apply_worker_payload(
        wxid,
        body,
        source="token",
        extra={
            "token": token,
            "tokenDuration": str(body.get("tokenDuration") or duration),
            "issuedAt": int(issued_at),
            "expiresAt": int(expires_at) if expires_at is not None else None,
            "frozen": False,
            "frozenAt": None,
            "tokenRetryUntil": None,
            "lastError": None,
        },
    )
    logger.info(
        "[cdn_image] CDN token 获取成功: wxid=%s expiresAt=%s plan=%s",
        wxid,
        state.get("expiresAt"),
        (state.get("account") or {}).get("plan"),
    )
    return state


def _usable_token(state: Dict[str, Any], stale_token: Optional[str]) -> Optional[str]:
    """本地已有的、且不是调用方刚被拒绝的那枚新鲜 token。"""
    if not _token_is_fresh(state, _now()):
        return None
    token = str(state["token"])
    if stale_token is not None and token == stale_token:
        return None
    return token


def _raise_if_in_token_backoff(state: Dict[str, Any]) -> None:
    retry_until = _get_token_retry_until(state)
    now = int(_now())
    if retry_until <= now:
        return
    remaining = retry_until - now
    last = state.get("lastError") or {}
    if str(last.get("code") or "") == "network_error":
        raise CdnError(
            str(last.get("message") or "无法连接 WxCDN 服务"),
            code="network_error",
            status=502,
            retry_after=remaining,
        )
    raise CdnRateLimitedError(
        str(last.get("message") or "签发 token 过于频繁"),
        code="rate_limited",
        status=429,
        retry_after=remaining,
    )


async def ensure_token(
    account: Optional[str] = None,
    *,
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
    force: bool = False,
    stale_token: Optional[str] = None,
) -> str:
    """返回该账号可用的 Bearer token；快过期或 force 时重新签发。

    ``stale_token`` 是调用方刚被 Worker 以 401 拒绝的那枚 token：如果本地已经
    换成了别的新鲜 token（并发的其他调用已经刷新过）就直接复用，不再打 /token；
    只有本地仍是这枚旧 token 时才重新签发。这样 N 个并发 401 只会触发一次刷新。

    ``force`` 用于用户主动「连接」：无视新鲜度与退避窗口，直接签发。
    """
    wxid, wx_id_dir = _resolve_wxid(account, wxid_dir=wxid_dir, db_storage_path=db_storage_path)
    state = _get_state(wxid)
    if state.get("frozen") and not force:
        last = state.get("lastError") or {}
        raise CdnAccountFrozenError(str(last.get("message") or "账号已被冻结"))
    if not force:
        token = _usable_token(state, stale_token)
        if token is not None:
            return token

    async with _lock_for(wxid):
        state = _get_state(wxid)
        if not force:
            token = _usable_token(state, stale_token)
            if token is not None:
                return token
            # /token 刚被限频或网络不通：在 Retry-After 窗口内不再打 Worker。
            _raise_if_in_token_backoff(state)
        state = await _request_token(wxid, wx_id_dir)
        return str(state["token"])


# 兼容旧名字
fetch_cdn_token = ensure_token


def _bearer(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------


async def fetch_quota(
    account: Optional[str] = None,
    *,
    max_age_seconds: float = 60,
    force: bool = False,
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> Dict[str, Any]:
    wxid, _ = _resolve_wxid(account, wxid_dir=wxid_dir, db_storage_path=db_storage_path)
    state = _get_state(wxid)
    if not force:
        fetched_at = state.get("quotaFetchedAt")
        if (
            fetched_at is not None
            and state.get("quota") is not None
            and _now() - float(fetched_at) < float(max_age_seconds)
        ):
            return {"account": state.get("account"), "quota": state.get("quota")}

    kwargs = {"wxid_dir": wxid_dir, "db_storage_path": db_storage_path}
    token = await ensure_token(account, **kwargs)
    for attempt in range(2):
        try:
            async with _make_async_client(timeout=30) as client:
                resp = await client.get(QUOTA_URL, headers=_bearer(token))
        except (httpx.HTTPError, OSError) as exc:
            raise _network_error(exc) from exc
        if resp.status_code == 401 and attempt == 0:
            token = await ensure_token(account, stale_token=token, **kwargs)
            continue
        try:
            _raise_for_worker_error(resp, wxid)
        except CdnError as err:
            _set_last_error(wxid, err)
            raise
        body = _safe_json(resp)
        state = _apply_worker_payload(wxid, body, source="quota", extra={"lastError": None})
        return {"account": state.get("account"), "quota": state.get("quota")}
    raise CdnInvalidTokenError("token 刷新后仍被拒绝")  # pragma: no cover - defensive


# ---------------------------------------------------------------------------
# redeem
# ---------------------------------------------------------------------------

_REDEEM_SEPARATORS = r"\s\-‐‑‒–—―−－﹣　"
_REDEEM_STRIP_RE = re.compile(f"[{_REDEEM_SEPARATORS}]+")
# 显式的 wx 前缀：wx 后面跟着分隔符（"wx-…"、"wx …"）。
_REDEEM_EXPLICIT_PREFIX_RE = re.compile(f"^[{_REDEEM_SEPARATORS}]*wx[{_REDEEM_SEPARATORS}]+", re.IGNORECASE)
_CROCKFORD_KEEP_RE = re.compile(r"[^0-9A-HJKMNP-TV-Z]")
_REDEEM_CODE_LENGTH = 20


def normalize_redeem_code(raw: str) -> str:
    """把用户输入的兑换码规整成 20 位 Crockford Base32（不含 wx- 前缀）。

    W、X 本身也是 Crockford 字母：用户省略 ``wx-`` 前缀、而码恰好以 WX 开头时
    不能把这两位当前缀吃掉。只有「wx 后面带分隔符」或「去掉 WX 后仍够 20 位」
    才视为前缀。
    """
    text = str(raw or "")
    explicit_prefix = bool(_REDEEM_EXPLICIT_PREFIX_RE.match(text))
    text = _REDEEM_STRIP_RE.sub("", text).upper()
    if text.startswith("WX") and (explicit_prefix or len(text) - 2 >= _REDEEM_CODE_LENGTH):
        text = text[2:]
    text = text.replace("O", "0").replace("I", "1").replace("L", "1")
    text = _CROCKFORD_KEEP_RE.sub("", text)
    return text[:_REDEEM_CODE_LENGTH]


def _redeem_code_hint(code: str) -> str:
    if len(code) <= 8:
        return "*" * len(code)
    return f"{code[:4]}...{code[-4:]}"


async def redeem_code(
    account: Optional[str],
    code: str,
    *,
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> Dict[str, Any]:
    wxid, _ = _resolve_wxid(account, wxid_dir=wxid_dir, db_storage_path=db_storage_path)
    normalized = normalize_redeem_code(code)
    if len(normalized) != 20:
        raise CdnRedeemError("兑换码格式不正确", code="invalid_redeem_code", status=400)

    state = _get_state(wxid)
    locked_until = state.get("redeemLockedUntil")
    now = int(_now())
    if locked_until is not None:
        try:
            locked_until_int = int(locked_until)
        except (TypeError, ValueError):
            locked_until_int = 0
        if locked_until_int > now:
            raise CdnRedeemError(
                "兑换功能因连续失败已临时锁定",
                code="redeem_locked",
                status=429,
                retry_after=locked_until_int - now,
                locked_until=locked_until_int,
            )
        _update_state(wxid, redeemLockedUntil=None)

    hint = _redeem_code_hint(normalized)
    logger.info("[cdn_image] 提交兑换码: wxid=%s code=%s", wxid, hint)
    kwargs = {"wxid_dir": wxid_dir, "db_storage_path": db_storage_path}
    token = await ensure_token(account, **kwargs)
    payload = {"code": "wx-" + normalized}
    for attempt in range(2):
        try:
            async with _make_async_client(timeout=30) as client:
                resp = await client.post(REDEEM_URL, json=payload, headers=_bearer(token))
        except (httpx.HTTPError, OSError) as exc:
            raise _network_error(exc) from exc
        if resp.status_code == 401 and attempt == 0:
            token = await ensure_token(account, stale_token=token, **kwargs)
            continue
        try:
            _raise_for_worker_error(resp, wxid)
        except CdnRedeemError as err:
            if err.code == "redeem_locked" and err.locked_until is not None:
                _update_state(wxid, redeemLockedUntil=int(err.locked_until))
            logger.info("[cdn_image] 兑换失败: wxid=%s code=%s reason=%s", wxid, hint, err.code)
            raise
        except CdnError as err:
            _set_last_error(wxid, err)
            raise
        body = _safe_json(resp)
        _apply_worker_payload(
            wxid, body, source="redeem", extra={"redeemLockedUntil": None, "lastError": None}
        )
        logger.info(
            "[cdn_image] 兑换成功: wxid=%s code=%s plan=%s",
            wxid,
            hint,
            (body.get("redemption") or {}).get("plan"),
        )
        return body
    raise CdnInvalidTokenError("token 刷新后仍被拒绝")  # pragma: no cover - defensive


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

_KNOWN_MAGIC_PREFIXES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG",  # PNG
    b"GIF8",  # GIF
    b"BM",  # BMP
)


def _looks_like_known_media(data: bytes) -> bool:
    if not data:
        return False
    if data.startswith(_KNOWN_MAGIC_PREFIXES):
        return True
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return True
    return False


def _try_local_aes_ecb_decrypt(data: bytes, aes_key_hex: str) -> Tuple[Optional[bytes], bool]:
    """本地 AES-ECB 解密。返回 (明文或 None, PKCS7 去填充是否成功)。"""
    khex = str(aes_key_hex or "").strip().lower()
    if not re.fullmatch(r"(?:[0-9a-f]{32}|[0-9a-f]{48}|[0-9a-f]{64})", khex):
        return None, False
    if not data or len(data) % 16 != 0:
        return None, False
    try:
        from Crypto.Cipher import AES
        from Crypto.Util import Padding

        key = bytes.fromhex(khex)
        plain = AES.new(key, AES.MODE_ECB).decrypt(data)
    except Exception:  # noqa: BLE001
        return None, False
    try:
        return Padding.unpad(plain, AES.block_size), True
    except Exception:  # noqa: BLE001
        return plain, False


def _parse_quota_header(value: Optional[str]) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() == "unlimited":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _record_download(wxid: str, resp: httpx.Response, *, media_type: str, size: int) -> None:
    headers = resp.headers
    state = _get_state(wxid)
    quota: Dict[str, Any] = dict(state.get("quota") or {})
    touched = False
    for header, field in (
        ("X-Quota-Limit", "limitBytes"),
        ("X-Quota-Used", "usedBytes"),
        ("X-Quota-Remaining", "remainingBytes"),
        ("X-Quota-Reset", "resetsAt"),
    ):
        if header in headers:
            quota[field] = _parse_quota_header(headers.get(header))
            touched = True
    content_length: Optional[int] = None
    try:
        if headers.get("Content-Length"):
            content_length = int(headers.get("Content-Length"))
    except (TypeError, ValueError):
        content_length = None

    recent = list(state.get("recent") or [])
    recent.append(
        {
            "at": int(_now()),
            "type": media_type,
            "bytes": content_length if content_length is not None else int(size),
            "cache": str(headers.get("X-WXCDN-Cache") or "").upper() or None,
            "remainingAfter": quota.get("remainingBytes") if "X-Quota-Remaining" in headers else None,
        }
    )
    recent = recent[-_RECENT_LIMIT:]
    fields: Dict[str, Any] = {"recent": recent, "lastError": None}
    if touched:
        fields["quota"] = quota
        fields["quotaFetchedAt"] = int(_now())
        fields["quotaSource"] = "download"
    _update_state(wxid, **fields)


async def download_media(
    account: Optional[str],
    fileid: str,
    *,
    media_type: str = "orig",
    aes_key_hex: str = "",
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> bytes:
    """按 fileid 从 WxCDN 拉取媒体字节（优先本地解密）。"""
    fileid = str(fileid or "").strip()
    if not fileid:
        raise ValueError("缺少 fileid，无法从 CDN 获取媒体")
    media_type = str(media_type or "").strip().lower()
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"不支持的 media_type: {media_type!r}")
    aes_key_hex = str(aes_key_hex or "").strip().lower()

    wxid, _ = _resolve_wxid(account, wxid_dir=wxid_dir, db_storage_path=db_storage_path)
    kwargs = {"wxid_dir": wxid_dir, "db_storage_path": db_storage_path}
    token = await ensure_token(account, **kwargs)

    async def _fetch(params: Dict[str, str]) -> httpx.Response:
        nonlocal token
        for attempt in range(2):
            try:
                async with _make_async_client(timeout=120) as client:
                    resp = await client.get(DOWNLOAD_URL, params=params, headers=_bearer(token))
            except (httpx.HTTPError, OSError) as exc:
                raise _network_error(exc) from exc
            if resp.status_code == 401 and attempt == 0:
                token = await ensure_token(account, stale_token=token, **kwargs)
                continue
            try:
                _raise_for_worker_error(resp, wxid)
            except CdnError as err:
                _set_last_error(wxid, err)
                raise
            return resp
        raise CdnInvalidTokenError("token 刷新后仍被拒绝")  # pragma: no cover - defensive

    base_params: Dict[str, str] = {"fileid": fileid, "type": media_type}
    resp = await _fetch(base_params)
    raw = resp.content
    if not raw:
        raise CdnError("CDN 下载返回为空", code="empty_response", status=502)

    result: Optional[bytes] = None
    if not aes_key_hex or _looks_like_known_media(raw):
        result = raw
    else:
        plain, unpadded = _try_local_aes_ecb_decrypt(raw, aes_key_hex)
        if plain is not None:
            if _looks_like_known_media(plain):
                result = plain
            elif media_type not in _IMAGE_LIKE_MEDIA_TYPES and unpadded:
                result = plain
        if result is None:
            logger.debug(
                "[cdn_image] 本地解密未得到可识别文件，回退服务端解密: fileid=%s type=%s",
                fileid[:32],
                media_type,
            )
            resp = await _fetch({**base_params, "key": aes_key_hex})
            result = resp.content
            if not result:
                raise CdnError("CDN 下载返回为空", code="empty_response", status=502)

    _record_download(wxid, resp, media_type=media_type, size=len(result))
    logger.info(
        "[cdn_image] 下载成功: wxid=%s type=%s bytes=%s cache=%s",
        wxid,
        media_type,
        len(result),
        resp.headers.get("X-WXCDN-Cache"),
    )
    return result


async def download_original_image(
    account: Optional[str],
    fileid: str,
    *,
    aes_key_hex: str = "",
    image_type: str = "orig",
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> bytes:
    """兼容旧接口：按 fileid 拉取原图字节。"""
    return await download_media(
        account,
        fileid,
        media_type=image_type,
        aes_key_hex=aes_key_hex,
        wxid_dir=wxid_dir,
        db_storage_path=db_storage_path,
    )


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


def _snapshot_from_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = state or _empty_state()
    now = _now()
    token = str(state.get("token") or "")
    try:
        expires_at = float(state.get("expiresAt") or 0)
    except (TypeError, ValueError):
        expires_at = 0.0
    return {
        "connected": bool(token) and expires_at > now,
        "account": state.get("account"),
        "quota": state.get("quota"),
        "tokenExpiresAt": state.get("expiresAt"),
        "tokenIssuedAt": state.get("issuedAt"),
        "quotaFetchedAt": state.get("quotaFetchedAt"),
        "quotaSource": state.get("quotaSource"),
        "frozen": bool(state.get("frozen")),
        "redeemLockedUntil": state.get("redeemLockedUntil"),
        "tokenRetryUntil": state.get("tokenRetryUntil"),
        "lastError": state.get("lastError"),
        "recent": list(state.get("recent") or []),
        "enabled": is_cdn_download_enabled(),
        "tokenDuration": get_token_duration(),
    }


def get_plan_snapshot(
    account: Optional[str] = None,
    *,
    wxid_dir: Optional[str] = None,
    db_storage_path: Optional[str] = None,
) -> Dict[str, Any]:
    """同步、无网络、绝不抛错的套餐快照。"""
    try:
        wxid, _ = _resolve_wxid(account, wxid_dir=wxid_dir, db_storage_path=db_storage_path)
    except Exception:  # noqa: BLE001
        snapshot = _snapshot_from_state(None)
        snapshot["connected"] = False
        snapshot["account"] = None
        snapshot["wxid"] = None
        return snapshot
    try:
        snapshot = _snapshot_from_state(_get_state(wxid))
    except Exception:  # noqa: BLE001
        snapshot = _snapshot_from_state(None)
    snapshot["wxid"] = wxid
    return snapshot


_cleanup_legacy_quota_file()
