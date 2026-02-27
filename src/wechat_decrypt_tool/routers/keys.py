from typing import Optional

from fastapi import APIRouter

from ..key_store import get_account_keys_from_store
from ..key_service import get_db_key_workflow, fetch_and_save_remote_keys
from ..media_helpers import _load_media_keys, _resolve_account_dir
from ..path_fix import PathFixRoute

router = APIRouter(route_class=PathFixRoute)


@router.get("/api/keys", summary="获取账号已保存的密钥")
async def get_saved_keys(account: Optional[str] = None):
    """获取账号的数据库密钥与图片密钥（用于前端自动回填）"""
    account_name: Optional[str] = None
    account_dir = None

    try:
        account_dir = _resolve_account_dir(account)
        account_name = account_dir.name
    except Exception:
        # 账号可能尚未解密；仍允许从全局 store 读取（如果传入了 account）
        account_name = str(account or "").strip() or None

    keys: dict = {}
    if account_name:
        keys = get_account_keys_from_store(account_name)

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
    }

    return {
        "status": "success",
        "account": account_name,
        "keys": result,
    }


@router.get("/api/get_keys", summary="自动获取微信数据库与图片密钥")
async def get_wechat_db_key():
    """
    自动流程：
    1. 结束微信进程
    2. 启动微信
    3. 根据版本注入双 Hook
    4. 抓取 DB 与 图片密钥(AES + XOR)并返回
    """
    try:
        keys_data = get_db_key_workflow()

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
async def get_image_key(account: Optional[str] = None):
    """
    通过模拟 Next.js Server Action 协议，利用本地微信配置文件换取 AES/XOR 密钥。

    1. 读取 [wx_dir]/all_users/config/global_config (Blob 1)
    2. 读 同上目录下的global_config.crc
    3. 构造 Multipart 包发送至远程服务器
    4. 解析返回流，自动存入本地数据库
    """
    try:
        result = await fetch_and_save_remote_keys(account)

        return {
            "status": 0,
            "errmsg": "ok",
            "data": {
                "xor_key": result["xor_key"],
                "aes_key": result["aes_key"],
                "nick_name": result.get("nick_name"),
                "account": result["wxid"]
            }
        }
    except FileNotFoundError as e:
        return {
            "status": -1,
            "errmsg": f"文件缺失: {str(e)}",
            "data": {}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": -1,
            "errmsg": f"获取失败: {str(e)}",
            "data": {}
        }
