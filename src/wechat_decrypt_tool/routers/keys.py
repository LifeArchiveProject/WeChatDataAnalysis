from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..key_store import get_account_keys_from_store, normalize_key_store_path
from ..key_service import (
    get_db_key_workflow,
    get_image_key_integrated_workflow,
    get_image_key_memory_workflow,
)
from ..media_helpers import _load_media_keys, _resolve_account_dir
from ..path_fix import PathFixRoute
from ..platform_support import MAC_DB_KEY_GUIDANCE, current_platform, is_macos

router = APIRouter(route_class=PathFixRoute)
logger = get_logger(__name__)


class ImageKeyMemoryRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名")
    db_storage_path: Optional[str] = Field(None, description="账号的 db_storage 路径")
    wxid_dir: Optional[str] = Field(None, description="微信原始账号目录")


def _image_key_log_metadata(xor_value: object, aes_value: object) -> dict:
    xor_raw = str(xor_value or "").strip()
    aes_raw = str(aes_value or "").strip()
    return {
        "has_xor": bool(xor_raw),
        "has_aes": bool(aes_raw),
        "xor_length": len(xor_raw),
        "aes_length": len(aes_raw),
    }


def _is_valid_image_key_pair(xor_value: object, aes_value: object) -> bool:
    xor_raw = str(xor_value or "").strip()
    aes_raw = str(aes_value or "").strip()
    try:
        xor_key = int(xor_raw[2:], 16) if xor_raw.lower().startswith("0x") else int(xor_raw, 16)
        aes_key = aes_raw[:16].encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError):
        return False
    return 0 <= xor_key <= 0xFF and len(aes_key) == 16


def _resolve_requested_wxid_dir(*, db_storage_path: Optional[str] = None, wxid_dir: Optional[str] = None) -> str:
    explicit_wxid_dir = str(wxid_dir or "").strip()
    if explicit_wxid_dir:
        return normalize_key_store_path(explicit_wxid_dir)

    raw_db_storage_path = str(db_storage_path or "").strip()
    if not raw_db_storage_path:
        return ""

    candidate = Path(raw_db_storage_path).expanduser()
    try:
        if str(candidate.name or "").lower() == "db_storage":
            return normalize_key_store_path(str(candidate.parent))
    except Exception:
        pass

    try:
        if str((candidate / "db_storage").name or "").lower() == "db_storage":
            return normalize_key_store_path(str(candidate))
    except Exception:
        pass

    return ""


def _build_saved_key_candidates(account_name: Optional[str], request_account: Optional[str], request_wxid_dir: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for value in [
        Path(request_wxid_dir).name if request_wxid_dir else "",
        str(account_name or "").strip(),
        str(request_account or "").strip(),
    ]:
        key = str(value or "").strip()
        if (not key) or (key in seen):
            continue
        seen.add(key)
        out.append(key)

    return out


def _evaluate_db_key_candidate(
    *,
    store_account: str,
    keys: dict,
    account_name: Optional[str],
    request_wxid_dir: str,
    request_db_storage_path: str,
) -> tuple[bool, int, str]:
    db_key = str(keys.get("db_key") or "").strip()
    if not db_key:
        return False, -1, ""

    source_wxid_dir = normalize_key_store_path(keys.get("db_key_source_wxid_dir"))
    source_db_storage_path = normalize_key_store_path(keys.get("db_key_source_db_storage_path"))
    request_wxid_dir_name = Path(request_wxid_dir).name if request_wxid_dir else ""
    source_wxid_dir_name = Path(source_wxid_dir).name if source_wxid_dir else ""

    if request_db_storage_path and source_db_storage_path:
        if source_db_storage_path == request_db_storage_path:
            return True, 400, ""
        return (
            False,
            0,
            f"Saved db key source does not match current db_storage_path. request={request_db_storage_path} stored={source_db_storage_path}",
        )

    if request_wxid_dir and source_wxid_dir:
        if (source_wxid_dir == request_wxid_dir) or (
            source_wxid_dir_name and source_wxid_dir_name == request_wxid_dir_name
        ):
            return True, 300, ""
        return (
            False,
            0,
            f"Saved db key source does not match current wxid_dir. request={request_wxid_dir_name} stored={source_wxid_dir_name or source_wxid_dir}",
        )

    if request_wxid_dir_name:
        if store_account == request_wxid_dir_name:
            return True, 200, ""
        if account_name and request_wxid_dir_name == str(account_name or "").strip():
            return True, 100, ""
        return (
            False,
            0,
            f"Legacy saved db key is ambiguous for current wxid_dir={request_wxid_dir_name}. Please fetch a fresh db key.",
        )

    return True, 50, ""


@router.get("/api/keys", summary="获取账号已保存的密钥")
async def get_saved_keys(
    account: Optional[str] = None,
    db_storage_path: Optional[str] = None,
    wxid_dir: Optional[str] = None,
):
    """获取账号的数据库密钥与图片密钥（用于前端自动回填）"""
    account_name: Optional[str] = None
    account_dir = None

    try:
        account_dir = _resolve_account_dir(account)
        account_name = account_dir.name
    except Exception:
        # 账号可能尚未解密；仍允许从全局 store 读取（如果传入了 account）
        account_name = str(account or "").strip() or None

    request_db_storage_path = normalize_key_store_path(db_storage_path)
    request_wxid_dir = _resolve_requested_wxid_dir(db_storage_path=db_storage_path, wxid_dir=wxid_dir)
    candidate_accounts = _build_saved_key_candidates(account_name, account, request_wxid_dir)

    logger.info(
        "[keys] get_saved_keys start: request_account=%s resolved_account=%s account_dir=%s db_storage_path=%s wxid_dir=%s candidates=%s",
        str(account or "").strip(),
        str(account_name or ""),
        str(account_dir) if account_dir else "",
        request_db_storage_path,
        request_wxid_dir,
        candidate_accounts,
    )

    keys: dict = {}
    selected_image_keys: dict = {}
    selected_image_key_score = -1
    selected_db_key_account = ""
    selected_db_key_score = -1
    db_key_blocked_reason = ""
    db_key_source_wxid_dir = ""
    db_key_source_db_storage_path = ""

    for candidate_account in candidate_accounts:
        candidate_keys = get_account_keys_from_store(candidate_account)
        if not isinstance(candidate_keys, dict) or not candidate_keys:
            continue

        image_xor_key = str(candidate_keys.get("image_xor_key") or "").strip()
        image_aes_key = str(candidate_keys.get("image_aes_key") or "").strip()
        has_complete_image_pair = _is_valid_image_key_pair(image_xor_key, image_aes_key)
        image_key_source_wxid_dir = normalize_key_store_path(
            candidate_keys.get("image_key_source_wxid_dir")
        )
        image_key_source_matches = not request_wxid_dir or (
            bool(image_key_source_wxid_dir) and image_key_source_wxid_dir == request_wxid_dir
        )
        image_key_source_conflicts = bool(
            request_wxid_dir
            and image_key_source_wxid_dir
            and image_key_source_wxid_dir != request_wxid_dir
        )
        image_key_verified = (
            candidate_keys.get("image_key_verified") is True
            and has_complete_image_pair
            and image_key_source_matches
        )
        image_score = (
            -1 if image_key_source_conflicts
            else 300 if has_complete_image_pair and image_key_verified
            else 200 if has_complete_image_pair
            else 100 if image_xor_key or image_aes_key
            else -1
        )
        if image_score > selected_image_key_score:
            selected_image_key_score = image_score
            selected_image_keys = {
                "image_xor_key": image_xor_key,
                "image_aes_key": image_aes_key,
                "image_key_verified": image_key_verified,
                "image_key_source": str(candidate_keys.get("image_key_source") or "").strip(),
                "image_key_source_wxid_dir": image_key_source_wxid_dir,
                "image_key_derived_wxid": str(candidate_keys.get("image_key_derived_wxid") or "").strip(),
                "image_key_code": candidate_keys.get("image_key_code"),
                "image_key_store_account": candidate_account,
                "updated_at": str(candidate_keys.get("updated_at") or "").strip(),
            }

        ok, score, blocked_reason = _evaluate_db_key_candidate(
            store_account=candidate_account,
            keys=candidate_keys,
            account_name=account_name,
            request_wxid_dir=request_wxid_dir,
            request_db_storage_path=request_db_storage_path,
        )
        if ok and score > selected_db_key_score:
            selected_db_key_score = score
            selected_db_key_account = candidate_account
            keys["db_key"] = str(candidate_keys.get("db_key") or "").strip()
            db_key_source_wxid_dir = normalize_key_store_path(candidate_keys.get("db_key_source_wxid_dir"))
            db_key_source_db_storage_path = normalize_key_store_path(candidate_keys.get("db_key_source_db_storage_path"))
            if str(candidate_keys.get("updated_at") or "").strip():
                keys["updated_at"] = str(candidate_keys.get("updated_at") or "").strip()
        elif (not ok) and blocked_reason and (not db_key_blocked_reason):
            db_key_blocked_reason = blocked_reason

    keys.update(selected_image_keys)

    # 兼容：没有完整账号级记录时，尝试从账号目录的 _media_keys.json 读取一整对密钥。
    if account_dir and selected_image_key_score < 200:
        try:
            media = _load_media_keys(account_dir)
            media_xor = f"0x{int(media['xor']):02X}" if media.get("xor") is not None else ""
            media_aes = str(media.get("aes") or "").strip()
            if media_xor or media_aes:
                keys.update({
                    "image_xor_key": media_xor,
                    "image_aes_key": media_aes,
                    "image_key_verified": media.get("verified") is True and _is_valid_image_key_pair(
                        media_xor,
                        media_aes,
                    ),
                    "image_key_source": str(media.get("source") or "legacy_media_cache").strip(),
                    "image_key_source_wxid_dir": normalize_key_store_path(media.get("source_wxid_dir")),
                    "image_key_derived_wxid": str(media.get("derived_wxid") or "").strip(),
                    "image_key_code": media.get("code"),
                    "image_key_store_account": account_dir.name,
                })
        except Exception:
            pass

    # 仅返回需要的字段
    result = {
        "db_key": str(keys.get("db_key") or "").strip(),
        "image_xor_key": str(keys.get("image_xor_key") or "").strip(),
        "image_aes_key": str(keys.get("image_aes_key") or "").strip(),
        "image_key_verified": bool(keys.get("image_key_verified")),
        "image_key_source": str(keys.get("image_key_source") or "").strip(),
        "image_key_source_wxid_dir": str(keys.get("image_key_source_wxid_dir") or "").strip(),
        "image_key_derived_wxid": str(keys.get("image_key_derived_wxid") or "").strip(),
        "image_key_code": keys.get("image_key_code"),
        "image_key_store_account": str(keys.get("image_key_store_account") or "").strip(),
        "updated_at": str(keys.get("updated_at") or "").strip(),
        "db_key_source_wxid_dir": db_key_source_wxid_dir,
        "db_key_source_db_storage_path": db_key_source_db_storage_path,
        "db_key_store_account": selected_db_key_account,
        "db_key_blocked_reason": db_key_blocked_reason,
    }
    logger.info(
        "[keys] get_saved_keys done: account=%s db_key_present=%s db_key_store_account=%s db_key_source_wxid_dir=%s blocked_reason=%s image_keys=%s image_verified=%s image_source=%s updated_at=%s",
        str(account_name or ""),
        bool(result["db_key"]),
        result["db_key_store_account"],
        result["db_key_source_wxid_dir"],
        result["db_key_blocked_reason"],
        _image_key_log_metadata(result["image_xor_key"], result["image_aes_key"]),
        result["image_key_verified"],
        result["image_key_source"],
        result["updated_at"],
    )

    return {
        "status": "success",
        "account": account_name,
        "keys": result,
    }


@router.get("/api/get_keys", summary="自动获取微信数据库密钥")
async def get_wechat_db_key(
    wechat_install_path: Optional[str] = None,
    db_storage_path: Optional[str] = None,
    key_mode: Optional[str] = None,
):
    """
    自动流程：
    1. 优先自动扫描 DLL 辅助 key，再使用 key_v4 从运行中的微信进程扫描并校验数据库密钥
    2. key_v4 不可用或失败时回退到 wx_key Hook 流程
    """
    if is_macos():
        return {
            "status": -3,
            "errmsg": MAC_DB_KEY_GUIDANCE,
            "data": {
                "platform": "macos",
                "database_key_extraction": False,
                "manual_input_supported": True,
                "suggested_tools": [
                    {
                        "name": "WeFlow",
                        "url": "https://github.com/hicccc77/WeFlow",
                    }
                ],
            },
        }

    try:
        logger.info(
            "[keys] get_wechat_db_key start: wechat_install_path=%s db_storage_path=%s key_mode=%s",
            str(wechat_install_path or "").strip(),
            str(db_storage_path or "").strip(),
            str(key_mode or "auto").strip(),
        )
        keys_data = get_db_key_workflow(
            wechat_install_path=wechat_install_path,
            db_storage_path=db_storage_path,
            key_mode=key_mode or "auto",
        )

        return {
            "status": 0,
            "errmsg": "ok",
            "data": keys_data
        }

    except TimeoutError as e:
        mode = str(key_mode or "auto").strip().lower()
        if mode in {"v4", "key_v4", "memory", "memory_scan"}:
            return {
                "status": -2,
                "errmsg": f"扫内存失败: {str(e)}",
                "data": {
                    "method": "key_v4",
                    "can_fallback_to_hook": True,
                    "key_v4_error": str(e),
                }
            }
        return {
            "status": -1,
            "errmsg": str(e).strip() or "获取超时，请确保微信没有开启自动登录并且在弹窗中完成了登录",
            "data": {"platform": current_platform()}
        }
    except Exception as e:
        mode = str(key_mode or "auto").strip().lower()
        if mode in {"v4", "key_v4", "memory", "memory_scan"}:
            return {
                "status": -2,
                "errmsg": f"扫内存失败: {str(e)}",
                "data": {
                    "method": "key_v4",
                    "can_fallback_to_hook": True,
                    "key_v4_error": str(e),
                }
            }
        return {
            "status": -1,
            "errmsg": f"获取失败: {str(e)}",
            "data": {}
        }



@router.get("/api/get_image_key", summary="获取并保存微信图片密钥")
async def get_image_key(
    account: Optional[str] = None,
    db_storage_path: Optional[str] = None,
    wxid_dir: Optional[str] = None,
):
    """
    优先使用 WeFlow 本地机制解析并验真 AES/XOR 密钥：

    1. 从 kvcomm 文件名枚举候选 code
    2. 对候选 code 与 wxid 组合确定性派生密钥
    3. 使用账号目录内真实 V2 图片验证候选
    4. 本地未命中时才请求远端，并在可用模板存在时再次本地验真
    """
    try:
        logger.info(
            "[keys] get_image_key start: request_account=%s db_storage_path=%s wxid_dir=%s",
            str(account or "").strip(),
            str(db_storage_path or "").strip(),
            str(wxid_dir or "").strip(),
        )
        result = await get_image_key_integrated_workflow(
            account,
            db_storage_path=db_storage_path,
            wxid_dir=wxid_dir,
        )
        logger.info(
            "[keys] get_image_key done: request_account=%s response_account=%s image_keys=%s verified=%s source=%s",
            str(account or "").strip(),
            str(result.get("wxid") or "").strip(),
            _image_key_log_metadata(result.get("xor_key"), result.get("aes_key")),
            result.get("verified") is True,
            str(result.get("source") or "").strip(),
        )

        verified = result.get("verified") is True
        return {
            "status": 0 if verified else -2,
            "errmsg": "ok" if verified else "已获得候选密钥，但缺少可用于本地验真的 V2 图片",
            "data": {
                "xor_key": result["xor_key"],
                "aes_key": result["aes_key"],
                "nick_name": result.get("nick_name", ""),
                "account": result.get("wxid", ""),
                "matched_wxid": result.get("matched_wxid", ""),
                "source": result.get("source", ""),
                "verified": verified,
                "code": result.get("code"),
            }
        }
    except FileNotFoundError as e:
        logger.exception(
            "[keys] get_image_key file missing: request_account=%s db_storage_path=%s wxid_dir=%s",
            str(account or "").strip(),
            str(db_storage_path or "").strip(),
            str(wxid_dir or "").strip(),
        )
        return {
            "status": -1,
            "errmsg": f"文件缺失: {str(e)}",
            "data": {}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.exception(
            "[keys] get_image_key failed: request_account=%s db_storage_path=%s wxid_dir=%s",
            str(account or "").strip(),
            str(db_storage_path or "").strip(),
            str(wxid_dir or "").strip(),
        )
        return {
            "status": -1,
            "errmsg": f"获取失败: {str(e)}",
            "data": {}
        }


@router.post("/api/get_image_key_memory", summary="扫描微信内存获取图片密钥")
async def get_image_key_memory(request: ImageKeyMemoryRequest):
    """Explicitly scan WeChat process memory and accept only V2-verified keys."""
    try:
        logger.info(
            "[keys] get_image_key_memory start: request_account=%s db_storage_path=%s wxid_dir=%s",
            str(request.account or "").strip(),
            str(request.db_storage_path or "").strip(),
            str(request.wxid_dir or "").strip(),
        )
        result = await get_image_key_memory_workflow(
            request.account,
            db_storage_path=request.db_storage_path,
            wxid_dir=request.wxid_dir,
        )
        logger.info(
            "[keys] get_image_key_memory done: request_account=%s response_account=%s pid=%s image_keys=%s",
            str(request.account or "").strip(),
            str(result.get("wxid") or "").strip(),
            result.get("pid"),
            _image_key_log_metadata(result.get("xor_key"), result.get("aes_key")),
        )
        return {
            "status": 0,
            "errmsg": "ok",
            "data": {
                "xor_key": result["xor_key"],
                "aes_key": result["aes_key"],
                "account": result.get("wxid", ""),
                "matched_wxid": result.get("matched_wxid", ""),
                "source": result.get("source", "memory_v2_verified"),
                "verified": result.get("verified") is True,
                "pid": result.get("pid"),
                "encoding": result.get("encoding", ""),
            },
        }
    except FileNotFoundError as error:
        logger.exception(
            "[keys] get_image_key_memory account directory missing: request_account=%s",
            str(request.account or "").strip(),
        )
        return {"status": -1, "errmsg": f"文件缺失: {str(error)}", "data": {}}
    except Exception as error:
        logger.exception(
            "[keys] get_image_key_memory failed: request_account=%s",
            str(request.account or "").strip(),
        )
        return {"status": -1, "errmsg": f"内存扫描失败: {str(error)}", "data": {}}
