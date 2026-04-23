from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from ..logging_config import get_logger
from ..key_store import get_account_keys_from_store, normalize_key_store_path
from ..key_service import get_db_key_workflow, get_image_key_integrated_workflow
from ..media_helpers import _load_media_keys, _resolve_account_dir
from ..path_fix import PathFixRoute

router = APIRouter(route_class=PathFixRoute)
logger = get_logger(__name__)


def _summarize_aes_key(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return raw
    return f"{raw[:4]}...{raw[-4:]}(len={len(raw)})"


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
    selected_db_key_account = ""
    selected_db_key_score = -1
    db_key_blocked_reason = ""
    db_key_source_wxid_dir = ""
    db_key_source_db_storage_path = ""

    for candidate_account in candidate_accounts:
        candidate_keys = get_account_keys_from_store(candidate_account)
        if not isinstance(candidate_keys, dict) or not candidate_keys:
            continue

        if not str(keys.get("image_xor_key") or "").strip():
            keys["image_xor_key"] = str(candidate_keys.get("image_xor_key") or "").strip()
        if not str(keys.get("image_aes_key") or "").strip():
            keys["image_aes_key"] = str(candidate_keys.get("image_aes_key") or "").strip()
        if not str(keys.get("updated_at") or "").strip():
            keys["updated_at"] = str(candidate_keys.get("updated_at") or "").strip()

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

    # 兼容：如果 store 里没有图片密钥，尝试从账号目录的 _media_keys.json 读取
    if account_dir and isinstance(keys, dict):
        try:
            media = _load_media_keys(account_dir)
            if keys.get("image_xor_key") in (None, "") and media.get("xor") is not None:
                keys["image_xor_key"] = f"0x{int(media['xor']):02X}"
            if keys.get("image_aes_key") in (None, "") and str(media.get("aes") or "").strip():
                keys["image_aes_key"] = str(media.get("aes") or "").strip()
        except Exception:
            pass

    # 仅返回需要的字段
    result = {
        "db_key": str(keys.get("db_key") or "").strip(),
        "image_xor_key": str(keys.get("image_xor_key") or "").strip(),
        "image_aes_key": str(keys.get("image_aes_key") or "").strip(),
        "updated_at": str(keys.get("updated_at") or "").strip(),
        "db_key_source_wxid_dir": db_key_source_wxid_dir,
        "db_key_source_db_storage_path": db_key_source_db_storage_path,
        "db_key_store_account": selected_db_key_account,
        "db_key_blocked_reason": db_key_blocked_reason,
    }
    logger.info(
        "[keys] get_saved_keys done: account=%s db_key_present=%s db_key_store_account=%s db_key_source_wxid_dir=%s blocked_reason=%s xor_key=%s aes_key=%s updated_at=%s",
        str(account_name or ""),
        bool(result["db_key"]),
        result["db_key_store_account"],
        result["db_key_source_wxid_dir"],
        result["db_key_blocked_reason"],
        result["image_xor_key"],
        _summarize_aes_key(result["image_aes_key"]),
        result["updated_at"],
    )

    return {
        "status": "success",
        "account": account_name,
        "keys": result,
    }


@router.get("/api/get_keys", summary="自动获取微信数据库与图片密钥")
async def get_wechat_db_key(wechat_install_path: Optional[str] = None):
    """
    自动流程：
    1. 结束微信进程
    2. 启动微信
    3. 根据版本注入双 Hook
    4. 抓取 DB 与 图片密钥(AES + XOR)并返回
    """
    try:
        logger.info(
            "[keys] get_wechat_db_key start: wechat_install_path=%s",
            str(wechat_install_path or "").strip(),
        )
        keys_data = get_db_key_workflow(wechat_install_path=wechat_install_path)

        return {
            "status": 0,
            "errmsg": "ok",
            "data": keys_data # 现在完美包含了 db_key, aes_key, xor_key
        }

    except TimeoutError:
        return {
            "status": -1,
            "errmsg": "获取超时，请确保微信没有开启自动登录并且在弹窗中完成了登录",
            "data": {}
        }
    except Exception as e:
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
    通过模拟 Next.js Server Action 协议，利用本地微信配置文件换取 AES/XOR 密钥。

    1. 读取 [wx_dir]/all_users/config/global_config (Blob 1)
    2. 读 同上目录下的global_config.crc
    3. 构造 Multipart 包发送至远程服务器
    4. 解析返回流，自动存入本地数据库
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
            "[keys] get_image_key done: request_account=%s response_account=%s xor_key=%s aes_key=%s",
            str(account or "").strip(),
            str(result.get("wxid") or "").strip(),
            str(result.get("xor_key") or "").strip(),
            _summarize_aes_key(str(result.get("aes_key") or "").strip()),
        )

        return {
            "status": 0,
            "errmsg": "ok",
            "data": {
                "xor_key": result["xor_key"],
                "aes_key": result["aes_key"],
                "nick_name": result.get("nick_name", ""),
                "account": result.get("wxid", "")
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
