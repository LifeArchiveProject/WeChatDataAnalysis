import hashlib
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Any, Dict, List
import urllib
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..chat_helpers import _quote_ident, _resolve_account_dir
from ..media_helpers import _resolve_account_db_storage_dir
from ..path_fix import PathFixRoute
from ..logging_config import get_logger
from ..wcdb_realtime import (
    WCDBRealtimeError,
    WCDB_REALTIME,
    exec_query as _wcdb_exec_query,
    get_avatar_urls as _wcdb_get_avatar_urls,
    get_display_names as _wcdb_get_display_names,
)

try:
    import zstandard as zstd
except Exception:
    zstd = None

logger = get_logger(__name__)
router = APIRouter(route_class=PathFixRoute)


def _sql_literal(value: Any) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _pick_case_insensitive_value(item: Any, *keys: str) -> Any:
    if not isinstance(item, dict):
        return None
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
        key_lc = str(key or "").strip().lower()
        for actual_key, actual_value in item.items():
            if str(actual_key or "").strip().lower() == key_lc and actual_value is not None:
                return actual_value
    return None


def _normalize_biz_source(value: Optional[str]) -> str:
    v = str(value or "").strip().lower()
    if not v or v in {"auto", "default", "wechat"}:
        return "auto"
    if v in {"decrypted", "local", "snapshot", "output"}:
        return "decrypted"
    if v in {"realtime", "real-time", "wcdb"}:
        return "realtime"
    raise HTTPException(status_code=400, detail="Invalid source, use 'auto', 'decrypted' or 'realtime'.")


def _normalize_pagination(limit: Any, offset: Any) -> tuple[int, int]:
    try:
        normalized_limit = int(limit or 50)
    except Exception:
        normalized_limit = 50
    try:
        normalized_offset = int(offset or 0)
    except Exception:
        normalized_offset = 0
    return max(1, min(normalized_limit, 500)), max(0, normalized_offset)


def _is_biz_realtime_available(account_dir: Path) -> bool:
    try:
        info = WCDB_REALTIME.get_status(account_dir)
    except Exception:
        return False
    return bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))


def _resolve_biz_source_for_account(source_norm: str, account_dir: Path) -> str:
    if source_norm == "auto":
        return "realtime" if _is_biz_realtime_available(account_dir) else "decrypted"
    return source_norm


def _iter_biz_message_db_paths(account_dir: Path, *, source: str) -> list[Path]:
    source_norm = str(source or "decrypted").strip().lower()
    if source_norm == "realtime":
        db_storage_dir = _resolve_account_db_storage_dir(account_dir)
        if db_storage_dir is None:
            return []
        live_message_dir = db_storage_dir / "message"
        try:
            return sorted([p for p in live_message_dir.glob("biz_message*.db") if p.is_file()])
        except Exception:
            return []
    try:
        return sorted([p for p in account_dir.glob("biz_message*.db") if p.is_file()])
    except Exception:
        return []


def _coerce_realtime_blobish_content(value: Any) -> Any:
    """WCDB exec_query may return BLOBs as bytes, 0xHEX, or bare HEX strings."""
    if value is None:
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        s = value.strip()
        hex_part = ""
        if s.lower().startswith("0x"):
            hex_part = s[2:]
        elif len(s) >= 8 and len(s) % 2 == 0 and s[:8].lower() == "28b52ffd":
            # zstd frame magic as bare hex.
            hex_part = s
        if hex_part and all(c in "0123456789abcdefABCDEF" for c in hex_part):
            try:
                return bytes.fromhex(hex_part)
            except Exception:
                return value
    return value


def _exec_realtime_query(rt_conn: Any, db_path: Path, sql: str) -> list[dict[str, Any]]:
    with rt_conn.lock:
        rows = _wcdb_exec_query(rt_conn.handle, kind="message", path=str(db_path), sql=sql)
    return [r for r in (rows or []) if isinstance(r, dict)]


def _resolve_realtime_name2id_user_column(rt_conn: Any, db_path: Path) -> Optional[str]:
    try:
        rows = _exec_realtime_query(rt_conn, db_path, "PRAGMA table_info(Name2Id)")
    except Exception:
        return None

    cols: list[str] = []
    for row in rows:
        name = str(_pick_case_insensitive_value(row, "name") or "").strip()
        if name:
            cols.append(name)

    lower_to_actual = {c.lower(): c for c in cols}
    for candidate in ("user_name", "username"):
        actual = lower_to_actual.get(candidate)
        if actual:
            return actual
    return None


def _find_biz_message_db_for_table(
    account_dir: Path,
    table_name: str,
    *,
    source: str,
    rt_conn: Any = None,
) -> Optional[Path]:
    table_lower = str(table_name or "").strip().lower()
    if not table_lower:
        return None

    for db_file in _iter_biz_message_db_paths(account_dir, source=source):
        if source == "realtime" and rt_conn is not None:
            try:
                rows = _exec_realtime_query(
                    rt_conn,
                    db_file,
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    f"AND lower(name)={_sql_literal(table_lower)} LIMIT 1",
                )
                if rows:
                    return db_file
            except Exception:
                continue
        else:
            conn = sqlite3.connect(str(db_file))
            try:
                res = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=?",
                    (table_lower,),
                ).fetchone()
                if res:
                    return db_file
            except Exception:
                pass
            finally:
                conn.close()
    return None


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

    content = _coerce_realtime_blobish_content(content)

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

@router.get("/api/biz/proxy_image", summary="代理请求微信服务号图片")
def proxy_biz_image(url: str):
    if not url:
        return Response(status_code=400)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            return Response(content=content, media_type=content_type)
    except Exception as e:
        logger.error(f"[biz] 代理图片失败: {url} -> {e}")
        return Response(status_code=500)

# 接口 1：获取全部的服务号/公众号的信息
@router.get("/api/biz/list", summary="获取全部服务号/公众号列表")
def get_biz_account_list(account: Optional[str] = None, source: Optional[str] = None):
    account_dir = _resolve_account_dir(account)
    source_requested = _normalize_biz_source(source)
    source_norm = _resolve_biz_source_for_account(source_requested, account_dir)

    biz_ids = set()
    biz_latest_time = {}
    rt_conn = None
    if source_norm == "realtime":
        try:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            if source_requested != "auto":
                raise HTTPException(status_code=400, detail=str(e))
            source_norm = "decrypted"
        except Exception as e:
            if source_requested != "auto":
                raise HTTPException(status_code=400, detail=str(e))
            source_norm = "decrypted"

    # 1. 遍历 biz_message_*.db
    for db_file in _iter_biz_message_db_paths(account_dir, source=source_norm):
        try:
            rows = []
            if source_norm == "realtime" and rt_conn is not None:
                resolved_user_col = _resolve_realtime_name2id_user_column(rt_conn, db_file)
                if resolved_user_col:
                    user_queries = [f"SELECT {_quote_ident(resolved_user_col)} AS username FROM Name2Id"]
                else:
                    # Fallback for old WCDB wrappers that may not support PRAGMA. Do not quote here:
                    # SQLite can treat a double-quoted missing identifier as a string literal, which produced
                    # a fake row named "username" in the UI.
                    user_queries = [
                        "SELECT user_name AS username FROM Name2Id",
                        "SELECT username AS username FROM Name2Id",
                    ]
                for user_query in user_queries:
                    try:
                        rows = _exec_realtime_query(rt_conn, db_file, user_query)
                        if rows:
                            break
                    except Exception:
                        rows = []
                for r in rows:
                    uname = str((r or {}).get("username") or "").strip()
                    if uname.lower() in {"username", "user_name"}:
                        continue
                    if not uname:
                        continue
                    biz_ids.add(uname)

                    md5_id = hashlib.md5(uname.encode('utf-8')).hexdigest().lower()
                    table_name = f"Msg_{md5_id}"
                    try:
                        sql = f"SELECT MAX(create_time) AS max_time FROM {_quote_ident(table_name)}"
                        time_rows = _exec_realtime_query(rt_conn, db_file, sql)
                        if time_rows and time_rows[0].get("max_time"):
                            current_max = biz_latest_time.get(uname, 0)
                            biz_latest_time[uname] = max(current_max, int(time_rows[0].get("max_time") or 0))
                    except Exception:
                        pass
            else:
                conn = sqlite3.connect(str(db_file))
                cursor = conn.cursor()

                cursor.execute("PRAGMA table_info(Name2Id)")
                cols = [row[1].lower() for row in cursor.fetchall()]
                user_col = "username" if "username" in cols else "user_name" if "user_name" in cols else ""

                if user_col:
                    rows = cursor.execute(f"SELECT {user_col} FROM Name2Id").fetchall()
                    for r in rows:
                        if r[0]:
                            uname = r[0]
                            biz_ids.add(uname)

                            # 顺便查询该号的最后一条消息时间
                            md5_id = hashlib.md5(uname.encode('utf-8')).hexdigest().lower()
                            table_name = f"Msg_{md5_id}"
                            try:
                                time_res = conn.execute(f"SELECT MAX(create_time) FROM {table_name}").fetchone()
                                if time_res and time_res[0]:
                                    current_max = biz_latest_time.get(uname, 0)
                                    biz_latest_time[uname] = max(current_max, time_res[0])
                            except Exception:
                                pass
                conn.close()
        except Exception as e:
            logger.warning(f"读取 Name2Id 失败 {db_file}: {e}")

    contact_db_path = account_dir / "contact.db"
    contact_info = {}
    if contact_db_path.exists() and biz_ids:
        try:
            conn = sqlite3.connect(str(contact_db_path))
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(biz_ids))

            # 先查 contact 表
            query_contact = f"SELECT username, remark, nick_name, alias, big_head_url FROM contact WHERE username IN ({placeholders})"
            rows_contact = cursor.execute(query_contact, list(biz_ids)).fetchall()

            for r in rows_contact:
                uname = r[0]
                name = r[1] or r[2] or r[3] or uname
                contact_info[uname] = {
                    "username": uname,
                    "name": name,
                    "avatar": r[4],
                    "type": 3  # 默认给个 3（未知）
                }

            # 再查 biz_info 表获取类型
            try:
                query_biz = f"SELECT username, type FROM biz_info WHERE username IN ({placeholders})"
                rows_biz = cursor.execute(query_biz, list(biz_ids)).fetchall()
                for r in rows_biz:
                    uname = r[0]
                    biz_type = r[1]
                    # 如果查到了且是 0, 1, 2，就更新进去，否则保留 3
                    if uname in contact_info:
                        if biz_type in (0, 1, 2):
                            contact_info[uname]["type"] = biz_type
                        else:
                            contact_info[uname]["type"] = 3
            except Exception as e:
                logger.warning(f"读取 biz_info 失败: {e}")

            conn.close()
        except Exception as e:
            logger.warning(f"读取 contact.db 失败: {e}")

    wcdb_display_names = {}
    wcdb_avatar_urls = {}
    if source_norm == "realtime" and rt_conn is not None and biz_ids:
        missing_or_stale = []
        for uid in biz_ids:
            info = contact_info.get(uid) or {}
            name = str(info.get("name") or "").strip()
            avatar = str(info.get("avatar") or "").strip()
            if (not name) or name == uid or (not avatar):
                missing_or_stale.append(uid)
        missing_or_stale = list(dict.fromkeys(missing_or_stale))
        if missing_or_stale:
            try:
                with rt_conn.lock:
                    wcdb_display_names = _wcdb_get_display_names(rt_conn.handle, missing_or_stale)
            except Exception:
                wcdb_display_names = {}
            try:
                with rt_conn.lock:
                    wcdb_avatar_urls = _wcdb_get_avatar_urls(rt_conn.handle, missing_or_stale)
            except Exception:
                wcdb_avatar_urls = {}

    # 3. 组装结果。实时库里可能已经有新服务号，但 contact.db 尚未同步；这种情况保留兜底项。
    result = []
    for uid in biz_ids:
        info = dict(contact_info.get(uid) or {
            "username": uid,
            "name": uid,
            "avatar": "",
            "type": 1 if str(uid or "").startswith("gh_") else 3,
        })
        wcdb_name = str(wcdb_display_names.get(uid) or "").strip()
        if wcdb_name and (not str(info.get("name") or "").strip() or str(info.get("name") or "").strip() == uid):
            info["name"] = wcdb_name
        wcdb_avatar = str(wcdb_avatar_urls.get(uid) or "").strip()
        if wcdb_avatar and not str(info.get("avatar") or "").strip():
            info["avatar"] = wcdb_avatar
        if int(info.get("type") if info.get("type") is not None else 3) == 3 and str(uid or "").startswith("gh_"):
            info["type"] = 1
        info["last_time"] = biz_latest_time.get(uid, 0)
        if info["last_time"]:
            # 格式化日期给前端展示用
            info["formatted_last_time"] = time.strftime("%Y-%m-%d", time.localtime(info["last_time"]))
        else:
            info["formatted_last_time"] = ""
        result.append(info)

    # 4. 按最后一条消息的时间降序排列
    result.sort(key=lambda x: x.get("last_time", 0), reverse=True)

    return {"status": "success", "source": source_norm, "total": len(result), "data": result}


# 接口 2：获取普通服务号/公众号的 json 消息 (已修复表名比对 bug)
@router.get("/api/biz/messages", summary="获取指定服务号的消息")
def get_biz_messages(
    username: str,
    account: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
):
    if username == "gh_3dfda90e39d6":
        raise HTTPException(status_code=400, detail="微信支付记录请请求 /api/biz/pay_records 接口")
    limit, offset = _normalize_pagination(limit, offset)

    account_dir = _resolve_account_dir(account)
    source_requested = _normalize_biz_source(source)
    source_norm = _resolve_biz_source_for_account(source_requested, account_dir)
    rt_conn = None
    if source_norm == "realtime":
        try:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            if source_requested != "auto":
                raise HTTPException(status_code=400, detail=str(e))
            source_norm = "decrypted"
        except Exception as e:
            if source_requested != "auto":
                raise HTTPException(status_code=400, detail=str(e))
            source_norm = "decrypted"

    md5_id = hashlib.md5(username.encode('utf-8')).hexdigest().lower()
    table_name = f"Msg_{md5_id}"

    target_db = _find_biz_message_db_for_table(
        account_dir,
        table_name,
        source=source_norm,
        rt_conn=rt_conn,
    )

    if not target_db:
        if source_requested == "auto" and source_norm == "realtime":
            source_norm = "decrypted"
            rt_conn = None
            target_db = _find_biz_message_db_for_table(account_dir, table_name, source=source_norm)
        if not target_db:
            return {
                "status": "success",
                "account": account_dir.name,
                "source": source_norm,
                "data": [],
                "scanned": 0,
                "hasMore": False,
                "message": f"未找到 {username} 的消息历史",
            }

    # ... (后续数据库查询逻辑保持不变) ...
    messages = []
    scanned = 0
    try:
        if source_norm == "realtime" and rt_conn is not None:
            query = (
                "SELECT local_id, create_time, message_content "
                f"FROM {_quote_ident(table_name)} "
                "WHERE local_type != 1 "
                f"ORDER BY create_time DESC LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            rows = _exec_realtime_query(rt_conn, target_db, query)
            iter_rows = [
                (
                    int((r or {}).get("local_id") or 0),
                    int((r or {}).get("create_time") or 0),
                    (r or {}).get("message_content"),
                )
                for r in rows
            ]
        else:
            conn = sqlite3.connect(str(target_db))
            cursor = conn.cursor()

            query = f"""
                SELECT local_id, create_time, message_content
                FROM [{table_name}]
                WHERE local_type != 1
                ORDER BY create_time DESC
                LIMIT ? OFFSET ?
            """
            iter_rows = cursor.execute(query, (limit, offset)).fetchall()
            conn.close()

        scanned = len(iter_rows)
        for local_id, c_time, content in iter_rows:
            raw_xml = extract_xml_from_db_content(content, username, local_id)
            if not raw_xml:
                continue

            struct_data = parse_wechat_xml_to_struct(raw_xml, username, local_id)
            if struct_data:
                struct_data["local_id"] = local_id
                struct_data["create_time"] = c_time
                messages.append(struct_data)
    except Exception as e:
        logger.error(f"[biz] 数据库查询出错: {e}")
        return {"status": "error", "account": account_dir.name, "source": source_norm, "message": str(e)}

    return {
        "status": "success",
        "account": account_dir.name,
        "source": source_norm,
        "data": messages,
        "scanned": scanned,
        "hasMore": scanned >= limit,
    }


# 接口 3：返回微信支付的 json 消息 (已修复表名比对 bug)
@router.get("/api/biz/pay_records", summary="获取微信支付记录")
def get_wechat_pay_records(
    account: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
):
    username = "gh_3dfda90e39d6"
    limit, offset = _normalize_pagination(limit, offset)
    account_dir = _resolve_account_dir(account)
    source_requested = _normalize_biz_source(source)
    source_norm = _resolve_biz_source_for_account(source_requested, account_dir)
    rt_conn = None
    if source_norm == "realtime":
        try:
            rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
        except WCDBRealtimeError as e:
            if source_requested != "auto":
                raise HTTPException(status_code=400, detail=str(e))
            source_norm = "decrypted"
        except Exception as e:
            if source_requested != "auto":
                raise HTTPException(status_code=400, detail=str(e))
            source_norm = "decrypted"

    md5_id = hashlib.md5(username.encode('utf-8')).hexdigest().lower()
    table_name = f"Msg_{md5_id}"

    target_db = _find_biz_message_db_for_table(
        account_dir,
        table_name,
        source=source_norm,
        rt_conn=rt_conn,
    )

    if not target_db:
        if source_requested == "auto" and source_norm == "realtime":
            source_norm = "decrypted"
            rt_conn = None
            target_db = _find_biz_message_db_for_table(account_dir, table_name, source=source_norm)
        if not target_db:
            return {
                "status": "success",
                "account": account_dir.name,
                "source": source_norm,
                "data": [],
                "scanned": 0,
                "hasMore": False,
                "message": "未找到微信支付的消息历史",
            }

    messages = []
    scanned = 0
    try:
        if source_norm == "realtime" and rt_conn is not None:
            query = (
                "SELECT local_id, create_time, message_content "
                f"FROM {_quote_ident(table_name)} "
                "WHERE local_type = 21474836529 OR local_type != 1 "
                f"ORDER BY create_time DESC LIMIT {int(limit)} OFFSET {int(offset)}"
            )
            rows = _exec_realtime_query(rt_conn, target_db, query)
            iter_rows = [
                (
                    int((r or {}).get("local_id") or 0),
                    int((r or {}).get("create_time") or 0),
                    (r or {}).get("message_content"),
                )
                for r in rows
            ]
        else:
            conn = sqlite3.connect(str(target_db))
            cursor = conn.cursor()

            query = f"""
                SELECT local_id, create_time, message_content
                FROM [{table_name}]
                WHERE local_type = 21474836529 OR local_type != 1
                ORDER BY create_time DESC
                LIMIT ? OFFSET ?
            """
            iter_rows = cursor.execute(query, (limit, offset)).fetchall()
            conn.close()

        scanned = len(iter_rows)
        for local_id, c_time, content in iter_rows:
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
    except Exception as e:
        logger.error(f"[biz] 查询微信支付数据库出错: {e}")
        return {"status": "error", "account": account_dir.name, "source": source_norm, "message": str(e)}

    return {
        "status": "success",
        "account": account_dir.name,
        "source": source_norm,
        "data": messages,
        "scanned": scanned,
        "hasMore": scanned >= limit,
    }
