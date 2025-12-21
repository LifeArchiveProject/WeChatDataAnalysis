import base64
import hashlib
import html
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException

from .logging_config import get_logger

try:
    import zstandard as zstd  # type: ignore
except Exception:
    zstd = None

logger = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DATABASES_DIR = _REPO_ROOT / "output" / "databases"
_DEBUG_SESSIONS = os.environ.get("WECHAT_TOOL_DEBUG_SESSIONS", "0") == "1"


def _list_decrypted_accounts() -> list[str]:
    if not _OUTPUT_DATABASES_DIR.exists():
        return []

    accounts: list[str] = []
    for p in _OUTPUT_DATABASES_DIR.iterdir():
        if not p.is_dir():
            continue
        if (p / "session.db").exists() and (p / "contact.db").exists():
            accounts.append(p.name)

    accounts.sort()
    return accounts


def _resolve_account_dir(account: Optional[str]) -> Path:
    accounts = _list_decrypted_accounts()
    if not accounts:
        raise HTTPException(
            status_code=404,
            detail="No decrypted databases found. Please decrypt first.",
        )

    selected = account or accounts[0]
    base = _OUTPUT_DATABASES_DIR.resolve()
    candidate = (_OUTPUT_DATABASES_DIR / selected).resolve()

    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid account path.")

    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Account not found.")

    if not (candidate / "session.db").exists():
        raise HTTPException(status_code=404, detail="session.db not found for this account.")
    if not (candidate / "contact.db").exists():
        raise HTTPException(status_code=404, detail="contact.db not found for this account.")

    return candidate


def _should_keep_session(username: str, include_official: bool) -> bool:
    if not username:
        return False

    if not include_official and username.startswith("gh_"):
        return False

    if username.startswith(("weixin", "qqmail", "fmessage", "medianote", "floatbottle", "newsapp")):
        return False

    if "@kefu.openim" in username:
        return False
    if "@openim" in username:
        return False
    if "service_" in username:
        return False

    if username in {
        "brandsessionholder",
        "brandservicesessionholder",
        "notifymessage",
        "opencustomerservicemsg",
        "notification_messages",
        "userexperience_alarm",
    }:
        return False

    return username.endswith("@chatroom") or username.startswith("wxid_") or ("@" not in username)


def _format_session_time(ts: Optional[int]) -> str:
    """智能时间格式化：今天显示时间，昨天显示"昨天 HH:MM"，本周显示"星期X HH:MM"，本年显示"M月D日 HH:MM"，跨年显示"YYYY年M月D日 HH:MM"""
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts))
        now = datetime.now()
        time_str = dt.strftime("%H:%M")

        # 计算日期差异（基于日历日期）
        today_start = datetime(now.year, now.month, now.day)
        target_start = datetime(dt.year, dt.month, dt.day)
        day_diff = (today_start - target_start).days

        # 今天
        if day_diff == 0:
            return time_str

        # 昨天
        if day_diff == 1:
            return f"昨天 {time_str}"

        # 本周内（2-6天前，显示星期）
        if 2 <= day_diff <= 6:
            week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            # Python weekday(): Monday=0, Sunday=6
            return f"{week_days[dt.weekday()]} {time_str}"

        # 本年内
        if dt.year == now.year:
            return f"{dt.month}月{dt.day}日 {time_str}"

        # 跨年
        return f"{dt.year}年{dt.month}月{dt.day}日 {time_str}"
    except Exception:
        return ""


def _infer_last_message_brief(msg_type: Optional[int], sub_type: Optional[int]) -> str:
    t = int(msg_type or 0)
    s = int(sub_type or 0)

    if t == 1:
        return "[Text]"
    if t == 3:
        return "[Image]"
    if t == 34:
        return "[Voice]"
    if t == 42:
        return "[Contact Card]"
    if t == 43:
        return "[Video]"
    if t == 47:
        return "[Emoji]"
    if t == 48:
        return "[Location]"
    if t == 49:
        if s == 5:
            return "[Link]"
        if s == 6:
            return "[File]"
        if s in (33, 36):
            return "[Mini Program]"
        if s == 57:
            return "[Quote]"
        if s in (63, 88):
            return "[Live]"
        if s == 87:
            return "[Announcement]"
        if s == 2000:
            return "[Transfer]"
        if s == 2003:
            return "[Red Packet]"
        if s == 19:
            return "[Chat History]"
        return "[App Message]"
    if t == 10000:
        return "[System]"
    return "[Message]"


def _infer_message_brief_by_local_type(local_type: Optional[int]) -> str:
    t = int(local_type or 0)
    if t == 1:
        return ""
    if t == 3:
        return "[Image]"
    if t == 34:
        return "[Voice]"
    if t == 43:
        return "[Video]"
    if t == 47:
        return "[Emoji]"
    if t == 48:
        return "[Location]"
    if t == 50:
        return "[VoIP]"
    if t == 10000:
        return "[System]"
    if t == 244813135921:
        return "[Quote]"
    if t == 17179869233:
        return "[Link]"
    if t == 21474836529:
        return "[Article]"
    if t == 154618822705:
        return "[Mini Program]"
    if t == 12884901937:
        return "[Music]"
    if t == 8594229559345:
        return "[Red Packet]"
    if t == 81604378673:
        return "[Chat History]"
    if t == 266287972401:
        return "[Pat]"
    if t == 8589934592049:
        return "[Transfer]"
    if t == 270582939697:
        return "[Live]"
    if t == 25769803825:
        return "[File]"
    return "[Message]"


def _quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _resolve_msg_table_name(conn: sqlite3.Connection, username: str) -> Optional[str]:
    if not username:
        return None
    md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
    expected = f"msg_{md5_hex}".lower()
    expected_chat = f"chat_{md5_hex}".lower()

    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = [r[0] for r in rows if r and r[0]]

    for name in names:
        if str(name).lower() == expected:
            return str(name)

    for name in names:
        if str(name).lower() == expected_chat:
            return str(name)

    for name in names:
        ln = str(name).lower()
        if ln.startswith("msg_") and md5_hex in ln:
            return str(name)
        if ln.startswith("chat_") and md5_hex in ln:
            return str(name)

    for name in names:
        if md5_hex in str(name).lower():
            return str(name)

    partial = md5_hex[:24]
    for name in names:
        if partial in str(name).lower():
            return str(name)

    return None


def _query_head_image_usernames(head_image_db_path: Path, usernames: list[str]) -> set[str]:
    uniq = list(dict.fromkeys([u for u in usernames if u]))
    if not uniq:
        return set()
    if not head_image_db_path.exists():
        return set()

    conn = sqlite3.connect(str(head_image_db_path))
    try:
        placeholders = ",".join(["?"] * len(uniq))
        rows = conn.execute(
            f"SELECT username FROM head_image WHERE username IN ({placeholders})",
            uniq,
        ).fetchall()
        return {str(r[0]) for r in rows if r and r[0]}
    finally:
        conn.close()


def _build_avatar_url(account_dir_name: str, username: str) -> str:
    return f"/api/chat/avatar?account={quote(account_dir_name)}&username={quote(username)}"


def _decode_sqlite_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    if isinstance(value, memoryview):
        try:
            return bytes(value).decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return str(value)


def _is_mostly_printable_text(s: str) -> bool:
    if not s:
        return False
    sample = s[:600]
    if not sample:
        return False
    printable = sum(1 for ch in sample if ch.isprintable() or ch in {"\n", "\r", "\t"})
    return (printable / len(sample)) >= 0.85


def _looks_like_xml(s: str) -> bool:
    if not s:
        return False
    t = s.lstrip()
    if t.startswith('"') and t.endswith('"'):
        t = t.strip('"').lstrip()
    return t.startswith("<")


def _decode_message_content(compress_value: Any, message_value: Any) -> str:
    msg_text = _decode_sqlite_text(message_value)

    if isinstance(message_value, (bytes, bytearray, memoryview)):
        raw = bytes(message_value) if isinstance(message_value, memoryview) else message_value
        if raw.startswith(b"\x28\xb5\x2f\xfd") and zstd is not None:
            try:
                out = zstd.decompress(raw)
                s = out.decode("utf-8", errors="ignore")
                s = html.unescape(s.strip())
                if _looks_like_xml(s) or _is_mostly_printable_text(s):
                    msg_text = s
            except Exception:
                pass

    if compress_value is None:
        return msg_text

    def try_decode_text_blob(text: str) -> Optional[str]:
        t = (text or "").strip()
        if not t:
            return None

        if len(t) >= 16 and len(t) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", t):
            try:
                raw = bytes.fromhex(t)
                if zstd is not None:
                    try:
                        out = zstd.decompress(raw)
                        s2 = out.decode("utf-8", errors="ignore")
                        s2 = html.unescape(s2.strip())
                        if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                            return s2
                    except Exception:
                        pass
                s2 = raw.decode("utf-8", errors="ignore")
                s2 = html.unescape(s2.strip())
                if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                    return s2
            except Exception:
                return None

        if len(t) >= 24 and len(t) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/=]+", t):
            try:
                raw = base64.b64decode(t)
                if zstd is not None:
                    try:
                        out = zstd.decompress(raw)
                        s2 = out.decode("utf-8", errors="ignore")
                        s2 = html.unescape(s2.strip())
                        if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                            return s2
                    except Exception:
                        pass
                s2 = raw.decode("utf-8", errors="ignore")
                s2 = html.unescape(s2.strip())
                if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                    return s2
            except Exception:
                return None

        return None

    if isinstance(compress_value, str):
        s = html.unescape(compress_value.strip())
        s2 = try_decode_text_blob(s)
        if s2:
            return s2
        if _looks_like_xml(s) or _is_mostly_printable_text(s):
            return s
        return msg_text

    data: Optional[bytes] = None
    if isinstance(compress_value, memoryview):
        data = bytes(compress_value)
    elif isinstance(compress_value, (bytes, bytearray)):
        data = bytes(compress_value)

    if not data:
        return msg_text

    if zstd is not None:
        try:
            out = zstd.decompress(data)
            s = out.decode("utf-8", errors="ignore")
            s = html.unescape(s.strip())
            if _looks_like_xml(s) or _is_mostly_printable_text(s):
                return s
        except Exception:
            pass

    try:
        s = data.decode("utf-8", errors="ignore")
        s = html.unescape(s.strip())
        s2 = try_decode_text_blob(s)
        if s2:
            return s2
        if _looks_like_xml(s) or _is_mostly_printable_text(s):
            return s
    except Exception:
        pass

    return msg_text


_MD5_HEX_RE = re.compile(rb"(?i)[0-9a-f]{32}")


def _extract_md5_from_blob(blob: Any) -> str:
    if blob is None:
        return ""
    if isinstance(blob, memoryview):
        data = bytes(blob)
    elif isinstance(blob, (bytes, bytearray)):
        data = bytes(blob)
    else:
        try:
            data = bytes(blob)
        except Exception:
            return ""

    if not data:
        return ""
    m = _MD5_HEX_RE.findall(data)
    if not m:
        return ""
    best = Counter([x.lower() for x in m]).most_common(1)[0][0]
    try:
        return best.decode("ascii", errors="ignore")
    except Exception:
        return ""


def _resource_lookup_chat_id(resource_conn: sqlite3.Connection, username: str) -> Optional[int]:
    if not username:
        return None
    try:
        row = resource_conn.execute(
            "SELECT rowid FROM ChatName2Id WHERE user_name = ? LIMIT 1",
            (username,),
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        return None
    return None


def _lookup_resource_md5(
    resource_conn: sqlite3.Connection,
    chat_id: Optional[int],
    message_local_type: int,
    server_id: int,
    local_id: int,
    create_time: int,
) -> str:
    if server_id <= 0 and local_id <= 0:
        return ""

    where_chat = ""
    params_prefix: list[Any] = []
    if chat_id is not None and int(chat_id) > 0:
        where_chat = " AND chat_id = ?"
        params_prefix.append(int(chat_id))

    where_type = ""
    if int(message_local_type) > 0:
        where_type = " AND message_local_type = ?"
        params_prefix.append(int(message_local_type))

    try:
        if server_id > 0:
            row = resource_conn.execute(
                "SELECT packed_info FROM MessageResourceInfo WHERE message_svr_id = ?"
                + where_chat
                + where_type
                + " ORDER BY message_id DESC LIMIT 1",
                [int(server_id)] + params_prefix,
            ).fetchone()
            if row and row[0] is not None:
                md5 = _extract_md5_from_blob(row[0])
                if md5:
                    return md5
    except Exception:
        pass

    try:
        if local_id > 0 and create_time > 0:
            row = resource_conn.execute(
                "SELECT packed_info FROM MessageResourceInfo WHERE message_local_id = ? AND message_create_time = ?"
                + where_chat
                + where_type
                + " ORDER BY message_id DESC LIMIT 1",
                [int(local_id), int(create_time)] + params_prefix,
            ).fetchone()
            if row and row[0] is not None:
                return _extract_md5_from_blob(row[0])
    except Exception:
        pass

    return ""


def _strip_cdata(s: str) -> str:
    if not s:
        return ""
    out = s.replace("<![CDATA[", "").replace("]]>", "")
    return out.strip()


def _extract_xml_tag_text(xml_text: str, tag: str) -> str:
    if not xml_text or not tag:
        return ""
    m = re.search(
        rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>",
        xml_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return ""
    return _strip_cdata(m.group(1) or "")


def _extract_xml_attr(xml_text: str, attr: str) -> str:
    if not xml_text or not attr:
        return ""
    m = re.search(rf"{re.escape(attr)}\s*=\s*['\"]([^'\"]+)['\"]", xml_text, flags=re.IGNORECASE)
    return (m.group(1) or "").strip() if m else ""


def _extract_xml_tag_or_attr(xml_text: str, name: str) -> str:
    v = _extract_xml_tag_text(xml_text, name)
    if v:
        return v
    return _extract_xml_attr(xml_text, name)


def _extract_refermsg_block(xml_text: str) -> str:
    if not xml_text:
        return ""
    m = re.search(r"(<refermsg[^>]*>.*?</refermsg>)", xml_text, flags=re.IGNORECASE | re.DOTALL)
    return (m.group(1) or "").strip() if m else ""


def _infer_transfer_status_text(
    is_sent: bool,
    paysubtype: str,
    receivestatus: str,
    sendertitle: str,
    receivertitle: str,
    senderdes: str,
    receiverdes: str,
) -> str:
    t = str(paysubtype or "").strip()
    rs = str(receivestatus or "").strip()

    if rs == "1":
        return "已收款"
    if rs == "2":
        return "已退还"
    if rs == "3":
        return "已过期"

    if t == "4":
        return "已退还"
    if t == "9":
        return "已被退还"
    if t == "10":
        return "已过期"

    if t == "8":
        return "发起转账"
    if t == "3":
        return "已收款" if is_sent else "已被接收"
    if t == "1":
        return "转账"

    title = sendertitle if is_sent else receivertitle
    if title:
        return title
    des = senderdes if is_sent else receiverdes
    if des:
        return des
    return "转账"


def _split_group_sender_prefix(text: str) -> tuple[str, str]:
    if not text:
        return "", text
    sep = text.find(":\n")
    if sep <= 0:
        return "", text
    prefix = text[:sep].strip()
    body = text[sep + 2 :].lstrip("\n")
    if not prefix or len(prefix) > 128:
        return "", text
    if re.search(r"\s", prefix):
        return "", text
    if prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix:
        return prefix, body
    return "", text


def _extract_sender_from_group_xml(xml_text: str) -> str:
    if not xml_text:
        return ""

    v = _extract_xml_tag_text(xml_text, "fromusername")
    if v:
        return v
    v = _extract_xml_attr(xml_text, "fromusername")
    if v:
        return v
    return ""


def _parse_pat_message(text: str, contact_rows: dict[str, sqlite3.Row]) -> str:
    template = _extract_xml_tag_text(text, "template")
    if not template:
        return "[拍一拍]"
    wxids = list({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
    rendered = template
    for wxid in wxids:
        row = contact_rows.get(wxid)
        name = _pick_display_name(row, wxid)
        rendered = rendered.replace(f"${{{wxid}}}", name)
    return rendered.strip() or "[拍一拍]"


def _parse_quote_message(text: str) -> str:
    title = _extract_xml_tag_text(text, "title")
    if title:
        return title
    refer = _extract_xml_tag_text(text, "content")
    if refer:
        return refer
    return "[引用消息]"


def _parse_app_message(text: str) -> dict[str, Any]:
    app_type_raw = _extract_xml_tag_text(text, "type")
    try:
        app_type = int(str(app_type_raw or "0").strip() or "0")
    except Exception:
        app_type = 0
    title = _extract_xml_tag_text(text, "title")
    des = _extract_xml_tag_text(text, "des")
    url = _extract_xml_tag_text(text, "url")

    if "<patmsg" in text.lower() or "<template>" in text.lower():
        return {"renderType": "system", "content": "[拍一拍]"}

    if app_type in (5, 68) and url:
        thumb_url = _extract_xml_tag_text(text, "thumburl")
        return {
            "renderType": "link",
            "content": des or title or "[链接]",
            "title": title or des or "",
            "url": url,
            "thumbUrl": thumb_url or "",
        }

    if app_type in (6, 74):
        file_name = title or ""
        total_len = _extract_xml_tag_text(text, "totallen")
        file_md5 = (
            _extract_xml_tag_or_attr(text, "md5")
            or _extract_xml_tag_or_attr(text, "filemd5")
            or _extract_xml_tag_or_attr(text, "file_md5")
        )
        return {
            "renderType": "file",
            "content": f"[文件] {file_name}".strip(),
            "title": file_name,
            "size": total_len or "",
            "fileMd5": file_md5 or "",
        }

    if app_type == 57 or "<refermsg" in text:
        refer_block = _extract_refermsg_block(text)

        try:
            text_wo_refer = re.sub(
                r"(<refermsg[^>]*>.*?</refermsg>)",
                "",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        except Exception:
            text_wo_refer = text

        reply_text = _extract_xml_tag_text(text_wo_refer, "title") or _extract_xml_tag_text(text, "title")
        refer_displayname = _extract_xml_tag_or_attr(refer_block, "displayname")
        refer_content = _extract_xml_tag_text(refer_block, "content")
        refer_type = _extract_xml_tag_or_attr(refer_block, "type")

        rt = (reply_text or "").strip()
        rc = (refer_content or "").strip()
        if rt and rc:
            if rc == rt:
                refer_content = ""
            else:
                lines = [ln.strip() for ln in rc.splitlines()]
                if lines and lines[0] == rt:
                    refer_content = "\n".join(rc.splitlines()[1:]).lstrip()
                elif rc.startswith(rt):
                    rest = rc[len(rt) :].lstrip()
                    refer_content = rest

        t = str(refer_type or "").strip()
        if t == "3":
            refer_content = "[图片]"
        elif t == "47":
            refer_content = "[表情]"
        elif t == "43" or t == "62":
            refer_content = "[视频]"
        elif t == "34":
            refer_content = "[语音]"
        elif t == "49" and refer_content:
            refer_content = f"[链接] {refer_content}".strip()

        return {
            "renderType": "quote",
            "content": reply_text or "[引用消息]",
            "quoteTitle": refer_displayname or "",
            "quoteContent": refer_content or "",
        }

    if app_type == 2000 or (
        "<wcpayinfo" in text and ("transfer" in text.lower() or "paysubtype" in text.lower())
    ):
        feedesc = _extract_xml_tag_or_attr(text, "feedesc")
        pay_memo = _extract_xml_tag_or_attr(text, "pay_memo")
        paysubtype = _extract_xml_tag_or_attr(text, "paysubtype")
        receivestatus = _extract_xml_tag_or_attr(text, "receivestatus")
        sendertitle = _extract_xml_tag_or_attr(text, "sendertitle")
        receivertitle = _extract_xml_tag_or_attr(text, "receivertitle")
        senderdes = _extract_xml_tag_or_attr(text, "senderdes")
        receiverdes = _extract_xml_tag_or_attr(text, "receiverdes")
        transferid = _extract_xml_tag_or_attr(text, "transferid")
        invalidtime = _extract_xml_tag_or_attr(text, "invalidtime")

        logger.debug(
            f"[转账解析] paysubtype={paysubtype}, receivestatus={receivestatus}, "
            f"transferid={transferid}, feedesc={feedesc}"
        )

        return {
            "renderType": "transfer",
            "content": (pay_memo or "").strip(),
            "title": (feedesc or title or "").strip(),
            "amount": feedesc or "",
            "paySubType": str(paysubtype or "").strip(),
            "receiveStatus": str(receivestatus or "").strip(),
            "senderTitle": sendertitle or "",
            "receiverTitle": receivertitle or "",
            "senderDes": senderdes or "",
            "receiverDes": receiverdes or "",
            "transferId": str(transferid or "").strip(),
            "invalidTime": str(invalidtime or "").strip(),
        }

    if app_type in (2001, 2003) or (
        "<wcpayinfo" in text and ("redenvelope" in text.lower() or "sendertitle" in text.lower())
    ):
        sendertitle = _extract_xml_tag_text(text, "sendertitle")
        receivertitle = _extract_xml_tag_text(text, "receivertitle")
        senderdes = _extract_xml_tag_text(text, "senderdes")
        receiverdes = _extract_xml_tag_text(text, "receiverdes")
        cover = _extract_xml_tag_text(text, "receiverc2cshowsourceurl")
        return {
            "renderType": "redPacket",
            "content": (sendertitle or receivertitle or title or "红包").strip() or "红包",
            "title": (senderdes or receiverdes or des or "").strip(),
            "coverUrl": cover or "",
        }

    if title or des:
        return {"renderType": "text", "content": title or des}

    return {"renderType": "text", "content": "[应用消息]"}


def _iter_message_db_paths(account_dir: Path) -> list[Path]:
    if not account_dir.exists():
        return []

    candidates: list[Path] = []
    for p in account_dir.glob("*.db"):
        n = p.name
        ln = n.lower()
        if ln in {"session.db", "contact.db", "head_image.db"}:
            continue
        if ln == "message_resource.db":
            continue
        if ln == "message_fts.db":
            continue

        if re.match(r"^message(_\d+)?\.db$", ln):
            candidates.append(p)
            continue
        if re.match(r"^biz_message(_\d+)?\.db$", ln):
            candidates.append(p)
            continue
        if "message" in ln and ln.endswith(".db"):
            candidates.append(p)
            continue
    candidates.sort(key=lambda x: x.name)
    return candidates


def _resolve_msg_table_name_by_map(lower_to_actual: dict[str, str], username: str) -> Optional[str]:
    if not username:
        return None
    md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
    expected = f"msg_{md5_hex}".lower()
    expected_chat = f"chat_{md5_hex}".lower()

    if expected in lower_to_actual:
        return lower_to_actual[expected]
    if expected_chat in lower_to_actual:
        return lower_to_actual[expected_chat]

    for ln, actual in lower_to_actual.items():
        if ln.startswith("msg_") and md5_hex in ln:
            return actual
        if ln.startswith("chat_") and md5_hex in ln:
            return actual

    for ln, actual in lower_to_actual.items():
        if md5_hex in ln:
            return actual

    partial = md5_hex[:24]
    for ln, actual in lower_to_actual.items():
        if partial in ln:
            return actual

    return None


def _build_latest_message_preview(
    username: str,
    local_type: int,
    raw_text: str,
    is_group: bool,
    sender_username: str = "",
) -> str:
    raw_text = (raw_text or "").strip()
    sender_prefix = ""
    if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
        sender_prefix, raw_text = _split_group_sender_prefix(raw_text)
    if is_group and (not sender_prefix) and sender_username:
        sender_prefix = str(sender_username).strip()

    content_text = ""
    if local_type == 10000:
        if "revokemsg" in raw_text:
            content_text = "撤回了一条消息"
        else:
            content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
            content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
    elif local_type == 244813135921:
        parsed = _parse_app_message(raw_text)
        qt = str(parsed.get("quoteTitle") or "").strip()
        qc = str(parsed.get("quoteContent") or "").strip()
        c0 = str(parsed.get("content") or "").strip()
        content_text = qc or c0 or qt or "[引用消息]"
    elif local_type == 49:
        parsed = _parse_app_message(raw_text)
        rt = str(parsed.get("renderType") or "")
        content_text = str(parsed.get("content") or "")
        title_text = str(parsed.get("title") or "").strip()
        if rt == "file" and title_text:
            content_text = title_text
        if (not content_text) and rt == "transfer":
            content_text = (
                str(parsed.get("senderTitle") or "")
                or str(parsed.get("receiverTitle") or "")
                or "转账"
            )
        if not content_text:
            content_text = title_text or str(parsed.get("url") or "")
    elif local_type == 25769803825:
        parsed = _parse_app_message(raw_text)
        title_text = str(parsed.get("title") or "").strip()
        content_text = title_text or str(parsed.get("content") or "").strip() or "[文件]"
    elif local_type == 3:
        content_text = "[图片]"
    elif local_type == 34:
        duration = _extract_xml_attr(raw_text, "voicelength")
        content_text = f"[语音 {duration}秒]" if duration else "[语音]"
    elif local_type == 43 or local_type == 62:
        content_text = "[视频]"
    elif local_type == 47:
        content_text = "[表情]"
    else:
        if raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
            content_text = raw_text
        else:
            content_text = _infer_message_brief_by_local_type(local_type)

    content_text = (content_text or "").strip() or _infer_message_brief_by_local_type(local_type)
    content_text = re.sub(r"\s+", " ", content_text).strip()
    if sender_prefix and content_text:
        return f"{sender_prefix}: {content_text}"
    return content_text


def _load_latest_message_previews(account_dir: Path, usernames: list[str]) -> dict[str, str]:
    if not usernames:
        return {}

    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return {}

    remaining = {u for u in usernames if u}
    best: dict[str, tuple[tuple[int, int, int], str]] = {}

    if _DEBUG_SESSIONS:
        logger.info(
            f"[sessions.preview] account_dir={account_dir} usernames={len(remaining)} dbs={len(db_paths)}"
        )
        logger.info(
            f"[sessions.preview] db_paths={', '.join([p.name for p in db_paths[:8]])}{'...' if len(db_paths) > 8 else ''}"
        )

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = [str(r[0]) for r in rows if r and r[0]]
            lower_to_actual = {n.lower(): n for n in names}

            found: dict[str, str] = {}
            for u in list(remaining):
                tn = _resolve_msg_table_name_by_map(lower_to_actual, u)
                if tn:
                    found[u] = tn

            if not found:
                continue

            conn.text_factory = bytes
            for u, tn in found.items():
                quoted = _quote_ident(tn)
                try:
                    try:
                        r = conn.execute(
                            "SELECT "
                            "m.local_type, m.message_content, m.compress_content, m.create_time, m.sort_seq, m.local_id, "
                            "n.user_name AS sender_username "
                            f"FROM {quoted} m "
                            "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                            "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                    except Exception:
                        r = conn.execute(
                            "SELECT "
                            "local_type, message_content, compress_content, create_time, sort_seq, local_id, '' AS sender_username "
                            f"FROM {quoted} "
                            "ORDER BY create_time DESC, sort_seq DESC, local_id DESC "
                            "LIMIT 1"
                        ).fetchone()
                except Exception as e:
                    if _DEBUG_SESSIONS:
                        logger.info(
                            f"[sessions.preview] db={db_path.name} username={u} table={tn} query_failed={e}"
                        )
                    continue
                if r is None:
                    continue

                local_type = int(r["local_type"] or 0)
                create_time = int(r["create_time"] or 0)
                sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                local_id = int(r["local_id"] or 0)
                sort_key = (create_time, sort_seq, local_id)

                raw_text = _decode_message_content(r["compress_content"], r["message_content"]).strip()
                sender_username = _decode_sqlite_text(r["sender_username"]).strip()
                preview = _build_latest_message_preview(
                    username=u,
                    local_type=local_type,
                    raw_text=raw_text,
                    is_group=bool(u.endswith("@chatroom")),
                    sender_username=sender_username,
                )
                if not preview:
                    continue

                prev = best.get(u)
                if prev is None or sort_key > prev[0]:
                    best[u] = (sort_key, preview)
        finally:
            conn.close()

    previews = {u: v[1] for u, v in best.items() if v and v[1]}
    if _DEBUG_SESSIONS:
        logger.info(
            f"[sessions.preview] built_previews={len(previews)} remaining_without_preview={len(remaining - set(previews.keys()))}"
        )
    return previews


def _pick_display_name(contact_row: Optional[sqlite3.Row], fallback_username: str) -> str:
    if contact_row is None:
        return fallback_username

    for key in ("remark", "nick_name", "alias"):
        try:
            v = contact_row[key]
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()

    return fallback_username


def _pick_avatar_url(contact_row: Optional[sqlite3.Row]) -> Optional[str]:
    if contact_row is None:
        return None

    for key in ("big_head_url", "small_head_url"):
        try:
            v = contact_row[key]
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def _load_contact_rows(contact_db_path: Path, usernames: list[str]) -> dict[str, sqlite3.Row]:
    uniq = list(dict.fromkeys([u for u in usernames if u]))
    if not uniq:
        return {}

    result: dict[str, sqlite3.Row] = {}

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        def query_table(table: str, targets: list[str]) -> None:
            if not targets:
                return
            placeholders = ",".join(["?"] * len(targets))
            sql = f"""
                SELECT username, remark, nick_name, alias, big_head_url, small_head_url
                FROM {table}
                WHERE username IN ({placeholders})
            """
            rows = conn.execute(sql, targets).fetchall()
            for r in rows:
                result[r["username"]] = r

        query_table("contact", uniq)
        missing = [u for u in uniq if u not in result]
        query_table("stranger", missing)
        return result
    finally:
        conn.close()
