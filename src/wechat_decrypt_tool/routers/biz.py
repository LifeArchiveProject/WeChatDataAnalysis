import hashlib
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..chat_helpers import _resolve_account_dir
from ..path_fix import PathFixRoute
from ..logging_config import get_logger

try:
    import zstandard as zstd
except Exception:
    zstd = None

logger = get_logger(__name__)
router = APIRouter(route_class=PathFixRoute)


def decompress_zstd_content(data: bytes, source_id: str, local_id: int) -> Optional[bytes]:
    """Zstandard 解压逻辑"""
    if not data or not data.startswith(b'\x28\xb5\x2f\xfd'):
        return None
    try:
        if zstd:
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(data, max_output_size=10 * 1024 * 1024)
    except Exception as e:
        error_msg = f"❌ [解压失败] 服务号id: {source_id}, local_id: {local_id} -> {e}"
        print(error_msg)
        logger.error(error_msg)
    return None


def extract_xml_from_db_content(content: Any, source_id: str, local_id: int) -> str:
    """提取并解压数据库内容"""
    if not content:
        return ""

    if isinstance(content, memoryview):
        content = content.tobytes()
    elif isinstance(content, str):
        content = content.encode('utf-8', errors='ignore')

    if isinstance(content, bytes):
        decompressed = decompress_zstd_content(content, source_id, local_id)
        if decompressed:
            return decompressed.decode('utf-8', errors='ignore')

        # 若不是 zstd 压缩或解压失败，尝试直接 decode
        try:
            return content.decode('utf-8', errors='ignore')
        except Exception:
            return ""
    return ""


def parse_wechat_xml_to_struct(xml_str: str, source_id: str, local_id: int) -> Optional[Dict[str, Any]]:
    """解析微信服务号 XML 到 Dict"""
    if not xml_str.strip():
        return None
    try:
        root = ET.fromstring(xml_str)

        def get_tag_text(element, path, default=""):
            node = element.find(path)
            return node.text if node is not None and node.text else default

        main_cover = get_tag_text(root, ".//appmsg/thumburl")
        if not main_cover:
            main_cover = get_tag_text(root, ".//topnew/cover")

        result = {
            "title": get_tag_text(root, ".//appmsg/title"),
            "des": get_tag_text(root, ".//appmsg/des"),
            "url": get_tag_text(root, ".//appmsg/url"),
            "cover": main_cover,
            "content_list": []
        }

        items = root.findall(".//mmreader/category/item")
        for item in items:
            item_struct = {
                "title": get_tag_text(item, "title"),
                "url": get_tag_text(item, "url"),
                "cover": get_tag_text(item, "cover"),
                "summary": get_tag_text(item, "summary")
            }
            if item_struct["title"]:
                result["content_list"].append(item_struct)

        return result
    except Exception as e:
        error_msg = f"❌ [解析XML失败] 服务号id: {source_id}, local_id: {local_id} -> {e}"
        print(error_msg)
        logger.error(error_msg)
        return None


def parse_pay_xml(xml_str: str, local_id: int) -> Optional[Dict[str, Any]]:
    """解析微信支付 XML"""
    if not xml_str.strip():
        return None
    try:
        root = ET.fromstring(xml_str)

        def get_text(path):
            node = root.find(path)
            return node.text if node is not None else ""

        record = {
            "title": get_text(".//appmsg/title"),
            "description": get_text(".//appmsg/des"),
            "merchant_name": get_text(".//template_header/display_name"),
            "merchant_icon": get_text(".//template_header/icon_url"),
            "timestamp": int(get_text(".//pub_time") or 0),
            "formatted_time": ""
        }
        return record
    except Exception as e:
        error_msg = f"❌ [解析微信支付XML失败] 支付id: gh_3dfda90e39d6, local_id: {local_id} -> {e}"
        print(error_msg)
        logger.error(error_msg)
        return None


# 接口 1：获取全部的服务号/公众号的信息
@router.get("/api/biz/list", summary="获取全部服务号/公众号列表")
def get_biz_account_list(account: Optional[str] = None):
    account_dir = _resolve_account_dir(account)

    # 1. 遍历 biz_message_*.db，从 Name2Id 拿到所有 id
    biz_ids = set()
    for db_file in account_dir.glob("biz_message*.db"):
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()

            # 不同微信版本的主键可能是 user_name 或 username
            cursor.execute("PRAGMA table_info(Name2Id)")
            cols = [row[1].lower() for row in cursor.fetchall()]
            user_col = "username" if "username" in cols else "user_name" if "user_name" in cols else ""

            if user_col:
                rows = cursor.execute(f"SELECT {user_col} FROM Name2Id").fetchall()
                for r in rows:
                    if r[0]:
                        biz_ids.add(r[0])
            conn.close()
        except Exception as e:
            logger.warning(f"读取 Name2Id 失败 {db_file}: {e}")

    # 2. 查询 contact.db 完善昵称和头像信息
    contact_db_path = account_dir / "contact.db"
    contact_info = {}
    if contact_db_path.exists() and biz_ids:
        try:
            conn = sqlite3.connect(str(contact_db_path))
            cursor = conn.cursor()

            placeholders = ",".join(["?"] * len(biz_ids))
            query = f"SELECT username, remark, nick_name, alias, big_head_url FROM contact WHERE username IN ({placeholders})"
            rows = cursor.execute(query, list(biz_ids)).fetchall()

            for r in rows:
                uname = r[0]
                remark = r[1]
                nick_name = r[2]
                alias = r[3]
                head_url = r[4]

                # 优先级: remark > nick_name > alias > id
                name = remark or nick_name or alias or uname
                contact_info[uname] = {
                    "username": uname,
                    "name": name,
                    "avatar": head_url
                }
            conn.close()
        except Exception as e:
            logger.warning(f"读取 contact.db 失败: {e}")

    result = []
    for uid in biz_ids:
        if uid in contact_info:
            result.append(contact_info[uid])
        else:
            result.append({"username": uid, "name": uid, "avatar": ""})

    return {"status": "success", "total": len(result), "data": result}


# 接口 2：获取普通服务号/公众号的 json 消息
@router.get("/api/biz/messages", summary="获取指定服务号的消息")
def get_biz_messages(username: str, account: Optional[str] = None, limit: int = 50, offset: int = 0):
    if username == "gh_3dfda90e39d6":
        raise HTTPException(status_code=400, detail="微信支付记录请请求 /api/biz/pay_records 接口")

    account_dir = _resolve_account_dir(account)
    md5_id = hashlib.md5(username.encode('utf-8')).hexdigest().lower()
    table_name = f"Msg_{md5_id}"

    target_db = None
    for db_file in account_dir.glob("biz_message*.db"):
        conn = sqlite3.connect(str(db_file))
        try:
            res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=?",
                               (table_name,)).fetchone()
            if res:
                target_db = db_file
                break
        except Exception:
            pass
        finally:
            conn.close()

    if not target_db:
        return {"status": "success", "data": [], "message": f"未找到 {username} 的消息历史"}

    messages = []
    try:
        conn = sqlite3.connect(str(target_db))
        cursor = conn.cursor()

        query = f"""
            SELECT local_id, create_time, message_content 
            FROM [{table_name}] 
            WHERE local_type != 1 
            ORDER BY create_time DESC 
            LIMIT ? OFFSET ?
        """
        rows = cursor.execute(query, (limit, offset)).fetchall()

        for local_id, c_time, content in rows:
            raw_xml = extract_xml_from_db_content(content, username, local_id)
            if not raw_xml:
                continue

            struct_data = parse_wechat_xml_to_struct(raw_xml, username, local_id)
            if struct_data:
                struct_data["local_id"] = local_id
                struct_data["create_time"] = c_time
                messages.append(struct_data)

        conn.close()
    except Exception as e:
        logger.error(f"[biz] 数据库查询出错: {e}")
        return {"status": "error", "message": str(e)}

    return {"status": "success", "data": messages}


# 接口 3：返回微信支付的 json 消息
@router.get("/api/biz/pay_records", summary="获取微信支付记录")
def get_wechat_pay_records(account: Optional[str] = None, limit: int = 50, offset: int = 0):
    username = "gh_3dfda90e39d6"
    account_dir = _resolve_account_dir(account)
    md5_id = hashlib.md5(username.encode('utf-8')).hexdigest().lower()
    table_name = f"Msg_{md5_id}"

    target_db = None
    for db_file in account_dir.glob("biz_message*.db"):
        conn = sqlite3.connect(str(db_file))
        try:
            res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=?",
                               (table_name,)).fetchone()
            if res:
                target_db = db_file
                break
        except Exception:
            pass
        finally:
            conn.close()

    if not target_db:
        return {"status": "success", "data": [], "message": "未找到微信支付的消息历史"}

    messages = []
    try:
        conn = sqlite3.connect(str(target_db))
        cursor = conn.cursor()

        query = f"""
            SELECT local_id, create_time, message_content 
            FROM [{table_name}] 
            WHERE local_type = 21474836529 OR local_type != 1 
            ORDER BY create_time DESC 
            LIMIT ? OFFSET ?
        """
        rows = cursor.execute(query, (limit, offset)).fetchall()

        for local_id, c_time, content in rows:
            raw_xml = extract_xml_from_db_content(content, username, local_id)
            if not raw_xml:
                continue

            parsed_data = parse_pay_xml(raw_xml, local_id)
            if parsed_data:
                parsed_data["local_id"] = local_id
                parsed_data["create_time"] = c_time
                if not parsed_data["timestamp"]:
                    parsed_data["timestamp"] = c_time

                parsed_data["formatted_time"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(parsed_data["timestamp"])
                )
                messages.append(parsed_data)

        conn.close()
    except Exception as e:
        logger.error(f"[biz] 查询微信支付数据库出错: {e}")
        return {"status": "error", "message": str(e)}

    return {"status": "success", "data": messages}