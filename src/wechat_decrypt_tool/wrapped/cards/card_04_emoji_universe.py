from __future__ import annotations

import functools
import hashlib
import html
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from ...chat_helpers import (
    _build_avatar_url,
    _decode_message_content,
    _extract_xml_attr,
    _extract_xml_tag_text,
    _iter_message_db_paths,
    _load_contact_rows,
    _lookup_resource_md5,
    _pick_display_name,
    _quote_ident,
    _resource_lookup_chat_id,
    _should_keep_session,
)
from ...chat_search_index import get_chat_search_index_db_path
from ...logging_config import get_logger

logger = get_logger(__name__)


_TS_WECHAT_EMOJI_ENTRY_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*:\s*"(?P<value>[^"]+)"\s*,?\s*$')
_MD5_HEX_RE = re.compile(r"(?i)[0-9a-f]{32}")
_EXPRESSION_ASSET_RE = re.compile(r"^Expression_(\d+)@2x\.png$")
_EMOJI_VS16 = "\ufe0f"
_EMOJI_ZWJ = "\u200d"
_EMOJI_KEYCAP = "\u20e3"


def _is_regional_indicator(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return 0x1F1E6 <= cp <= 0x1F1FF


def _is_emoji_modifier(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return 0x1F3FB <= cp <= 0x1F3FF


def _is_emoji_base(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return (
        (0x1F300 <= cp <= 0x1FAFF)
        or (0x2600 <= cp <= 0x26FF)
        or (0x2700 <= cp <= 0x27BF)
        or (0x1F1E6 <= cp <= 0x1F1FF)
        or cp in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
        or cp == 0x1F004
        or (0x1F170 <= cp <= 0x1F251)
    )


def _extract_unicode_emoji_tokens(text: str) -> list[str]:
    s = str(text or "")
    if not s:
        return []

    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]

        # keycap emoji: [0-9#*][VS16]?U+20E3
        if ch in "0123456789#*":
            j = i + 1
            if j < n and s[j] == _EMOJI_VS16:
                j += 1
            if j < n and s[j] == _EMOJI_KEYCAP:
                out.append(s[i : j + 1])
                i = j + 1
                continue

        # flags
        if _is_regional_indicator(ch):
            if (i + 1) < n and _is_regional_indicator(s[i + 1]):
                out.append(s[i : i + 2])
                i += 2
            else:
                out.append(ch)
                i += 1
            continue

        if not _is_emoji_base(ch):
            i += 1
            continue

        token: list[str] = [ch]
        j = i + 1
        if j < n and s[j] == _EMOJI_VS16:
            token.append(s[j])
            j += 1
        if j < n and _is_emoji_modifier(s[j]):
            token.append(s[j])
            j += 1

        # Handle ZWJ chains.
        while (j + 1) < n and s[j] == _EMOJI_ZWJ and _is_emoji_base(s[j + 1]):
            token.append(s[j])
            token.append(s[j + 1])
            j += 2
            if j < n and s[j] == _EMOJI_VS16:
                token.append(s[j])
                j += 1
            if j < n and _is_emoji_modifier(s[j]):
                token.append(s[j])
                j += 1

        out.append("".join(token))
        i = j

    return out


def _emoji_key_priority(key: str) -> tuple[int, int, str]:
    s = str(key or "").strip()
    if not s:
        return (9, 9, "")
    if re.fullmatch(r"\[[\u4e00-\u9fff]+\]", s):
        return (0, len(s), s)
    if re.fullmatch(r"/[\u4e00-\u9fff]+", s):
        return (1, len(s), s)
    if re.fullmatch(r"\[[A-Za-z][A-Za-z0-9_ ]*\]", s):
        return (2, len(s), s)
    if re.fullmatch(r"/:[^/\s]+", s):
        return (3, len(s), s)
    return (4, len(s), s)


def _normalize_index_text_for_emoji_match(text: str) -> str:
    """
    Our chat search index stores `message_fts.text` as `_to_char_token_text`, i.e.:
    - lowercased
    - whitespace removed
    - every character joined by single spaces

    Example: "[捂脸]" -> "[ 捂 脸 ]"
    For emoji matching, we normalize it back by removing whitespace and lowercasing.
    """

    return "".join(ch for ch in str(text or "").lower() if not ch.isspace())


def _iter_protobuf_varints(blob: bytes) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    data = bytes(blob or b"")
    if not data:
        return out

    i = 0
    n = len(data)
    while i < n:
        key = int(data[i])
        i += 1
        field = int(key >> 3)
        wire_type = int(key & 0x07)

        if wire_type == 0:  # varint
            shift = 0
            value = 0
            while i < n:
                b = int(data[i])
                i += 1
                value |= (b & 0x7F) << shift
                if b < 0x80:
                    break
                shift += 7
            out.append((field, int(value)))
            continue

        if wire_type == 1:  # 64-bit
            i += 8
            continue

        if wire_type == 2:  # length-delimited
            shift = 0
            ln = 0
            while i < n:
                b = int(data[i])
                i += 1
                ln |= (b & 0x7F) << shift
                if b < 0x80:
                    break
                shift += 7
            i += int(ln)
            continue

        if wire_type == 5:  # 32-bit
            i += 4
            continue

        break

    return out


def _extract_packed_emoji_meta(packed_info_data: Any) -> tuple[Optional[int], Optional[int]]:
    data: bytes = b""
    if packed_info_data is None:
        return None, None
    if isinstance(packed_info_data, memoryview):
        data = packed_info_data.tobytes()
    elif isinstance(packed_info_data, (bytes, bytearray)):
        data = bytes(packed_info_data)
    elif isinstance(packed_info_data, str):
        s = packed_info_data.strip()
        if s:
            try:
                data = bytes.fromhex(s) if (len(s) % 2 == 0 and re.fullmatch(r"(?i)[0-9a-f]+", s)) else s.encode(
                    "utf-8",
                    errors="ignore",
                )
            except Exception:
                data = b""
    if not data:
        return None, None

    field1: Optional[int] = None
    field2: Optional[int] = None
    for f, v in _iter_protobuf_varints(data):
        if f == 1 and field1 is None:
            field1 = int(v)
        elif f == 2 and field2 is None:
            field2 = int(v)
        if field1 is not None and field2 is not None:
            break
    return field1, field2


def _year_range_epoch_seconds(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1).timestamp())
    end = int(datetime(year + 1, 1, 1).timestamp())
    return start, end


def _mask_name(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        return ""
    if len(s) == 1:
        return "*"
    if len(s) == 2:
        return s[0] + "*"
    return s[0] + ("*" * (len(s) - 2)) + s[-1]


def _weekday_name_zh(weekday_index: int) -> str:
    labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    if 0 <= weekday_index < len(labels):
        return labels[weekday_index]
    return ""


def _list_message_tables(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except Exception:
        return []
    out: list[str] = []
    for r in rows:
        if not r or not r[0]:
            continue
        raw_name = r[0]
        if isinstance(raw_name, memoryview):
            raw_name = raw_name.tobytes()
        if isinstance(raw_name, (bytes, bytearray)):
            try:
                name = bytes(raw_name).decode("utf-8", errors="ignore")
            except Exception:
                continue
        else:
            name = str(raw_name)
        ln = name.lower()
        if ln.startswith(("msg_", "chat_")):
            out.append(name)
    return out


def _list_session_usernames(session_db_path: Path) -> list[str]:
    if not session_db_path.exists():
        return []
    conn = sqlite3.connect(str(session_db_path))
    try:
        try:
            rows = conn.execute("SELECT username FROM SessionTable").fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute("SELECT username FROM Session").fetchall()
    except Exception:
        rows = []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out: list[str] = []
    for r in rows:
        if not r or not r[0]:
            continue
        u = str(r[0]).strip()
        if u:
            out.append(u)
    return out


@functools.lru_cache(maxsize=1)
def _load_wechat_emoji_table() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "frontend" / "utils" / "wechat-emojis.ts"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    table: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if (not stripped) or stripped.startswith("//"):
            continue
        m = _TS_WECHAT_EMOJI_ENTRY_RE.match(line)
        if not m:
            continue
        key = str(m.group("key") or "")
        value = str(m.group("value") or "")
        if key and value:
            table[key] = value
    return table


@functools.lru_cache(maxsize=1)
def _load_wechat_emoji_regex() -> Optional[re.Pattern[str]]:
    table = _load_wechat_emoji_table()
    if not table:
        return None
    keys = sorted(table.keys(), key=len, reverse=True)
    escaped = [re.escape(k) for k in keys if k]
    if not escaped:
        return None
    try:
        return re.compile(f"({'|'.join(escaped)})")
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def _load_wechat_text_emoji_matcher() -> tuple[Optional[re.Pattern[str]], dict[str, str]]:
    """
    Build a matcher for extracting WeChat "small yellow face" codes from `message_fts.text`.

    Note: `message_fts.text` is stored as a char-tokenized string (see `_normalize_index_text_for_emoji_match`),
    so we match against normalized keys (lowercased + whitespace removed).

    Returns:
      - regex: matches normalized keys
      - norm_key -> canonical key (used as the public label)
    """

    table = _load_wechat_emoji_table()
    if not table:
        return None, {}

    asset_to_keys: dict[str, list[str]] = {}
    for key, value in table.items():
        asset = str(value or "").strip()
        if not asset:
            continue
        asset_to_keys.setdefault(asset, []).append(str(key or ""))

    asset_to_label: dict[str, str] = {}
    for asset, keys in asset_to_keys.items():
        keys2 = [k for k in keys if k]
        if not keys2:
            continue
        asset_to_label[asset] = sorted(keys2, key=_emoji_key_priority)[0]

    norm_to_label: dict[str, str] = {}
    for key, value in table.items():
        asset = str(value or "").strip()
        label = asset_to_label.get(asset)
        if not label:
            continue
        nk = _normalize_index_text_for_emoji_match(str(key or ""))
        if not nk:
            continue
        norm_to_label.setdefault(nk, label)

    keys_norm = sorted(norm_to_label.keys(), key=len, reverse=True)
    escaped = [re.escape(k) for k in keys_norm if k]
    if not escaped:
        return None, norm_to_label
    try:
        return re.compile(f"({'|'.join(escaped)})"), norm_to_label
    except Exception:
        return None, norm_to_label


@functools.lru_cache(maxsize=1)
def _load_wechat_expression_catalog() -> tuple[dict[int, str], dict[int, str]]:
    table = _load_wechat_emoji_table()
    if not table:
        return {}, {}

    id_to_asset: dict[int, str] = {}
    asset_to_keys: dict[str, list[str]] = {}
    for key, value in table.items():
        asset = str(value or "").strip()
        m = _EXPRESSION_ASSET_RE.fullmatch(asset)
        if not m:
            continue
        try:
            expr_id = int(m.group(1))
        except Exception:
            continue
        if expr_id <= 0:
            continue
        id_to_asset.setdefault(expr_id, asset)
        asset_to_keys.setdefault(asset, []).append(str(key or ""))

    id_to_label: dict[int, str] = {}
    for expr_id, asset in id_to_asset.items():
        keys = [k for k in asset_to_keys.get(asset, []) if k]
        if not keys:
            continue
        keys_sorted = sorted(keys, key=_emoji_key_priority)
        id_to_label[expr_id] = keys_sorted[0]

    return id_to_asset, id_to_label


def _pick_persona(
    *,
    sent_sticker_count: int,
    sticker_share: float,
    peak_hour: Optional[int],
    top_text_emoji_count: int,
) -> dict[str, str]:
    if sent_sticker_count <= 0 and top_text_emoji_count <= 0:
        return {"code": "quiet_observer", "label": "静默观察员", "reason": "你今年几乎没靠表情表达。"}

    if peak_hour is not None and 0 <= int(peak_hour) <= 4 and sent_sticker_count >= 50:
        return {"code": "midnight_sticker_king", "label": "午夜斗图王", "reason": "高峰活跃在深夜，夜聊斗图火力很足。"}

    if top_text_emoji_count >= 20 and top_text_emoji_count >= int(sent_sticker_count * 0.6):
        return {"code": "text_emoji_narrator", "label": "小黄脸叙事家", "reason": "你更常把小黄脸嵌进文字，表达更细腻。"}

    if sticker_share >= 0.45 and sent_sticker_count >= 80:
        return {"code": "sticker_machine_gun", "label": "表情包机关枪", "reason": "在你的表达里，表情包占比非常高。"}

    return {"code": "steady_fighter", "label": "稳健斗图手", "reason": "斗图稳定输出，节奏和分寸都在线。"}


def _build_local_emoji_url(
    *,
    account_name: str,
    md5: str,
    username: str,
    emoji_remote_url: str,
) -> str:
    base = f"/api/chat/media/emoji?account={quote(account_name)}&md5={quote(md5)}"
    if username:
        base += f"&username={quote(username)}"
    if emoji_remote_url:
        base += f"&emoji_url={quote(emoji_remote_url, safe='')}"
    return base


def compute_emoji_universe_stats(*, account_dir: Path, year: int) -> dict[str, Any]:
    start_ts, end_ts = _year_range_epoch_seconds(year)
    my_username = str(account_dir.name or "").strip()

    sent_sticker_count = 0
    total_sent_messages = 0
    sticker_active_days: set[str] = set()
    hour_counts: Counter[int] = Counter()
    weekday_counts: Counter[int] = Counter()
    sticker_by_username: Counter[str] = Counter()
    text_emoji_counts: Counter[str] = Counter()
    unicode_emoji_counts: Counter[str] = Counter()
    wechat_emoji_counts: Counter[int] = Counter()

    sticker_key_counts: Counter[str] = Counter()
    sticker_key_md5: dict[str, str] = {}
    sticker_key_expr_id: dict[str, int] = {}
    sticker_url_map: dict[str, str] = {}
    sticker_sample_username: dict[str, str] = {}
    sticker_key_username_counts: dict[str, Counter[str]] = defaultdict(Counter)
    sticker_key_first_ts_in_year: dict[str, int] = {}

    used_index = False

    emoji_table = _load_wechat_emoji_table()
    emoji_regex, emoji_norm_to_key = _load_wechat_text_emoji_matcher()
    expression_id_to_asset, expression_id_to_label = _load_wechat_expression_catalog()

    index_path = get_chat_search_index_db_path(account_dir)
    if index_path.exists():
        conn = sqlite3.connect(str(index_path))
        try:
            has_fts = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1"
                ).fetchone()
                is not None
            )
            if has_fts and my_username:
                used_index = True
                ts_expr = (
                    "CASE "
                    "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                    "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                    "ELSE CAST(create_time AS INTEGER) "
                    "END"
                )
                where_base = (
                    f"{ts_expr} >= ? AND {ts_expr} < ? "
                    "AND db_stem NOT LIKE 'biz_message%' "
                    "AND sender_username = ?"
                )

                try:
                    r_total = conn.execute(
                        f"SELECT COUNT(1) FROM message_fts WHERE {where_base} AND CAST(local_type AS INTEGER) != 10000",
                        (start_ts, end_ts, my_username),
                    ).fetchone()
                    total_sent_messages = int((r_total[0] if r_total else 0) or 0)
                except Exception:
                    total_sent_messages = 0

                try:
                    r_sticker = conn.execute(
                        f"SELECT COUNT(1) FROM message_fts WHERE {where_base} AND CAST(local_type AS INTEGER) = 47",
                        (start_ts, end_ts, my_username),
                    ).fetchone()
                    sent_sticker_count = int((r_sticker[0] if r_sticker else 0) or 0)
                except Exception:
                    sent_sticker_count = 0

                try:
                    rows_u = conn.execute(
                        f"SELECT username, COUNT(1) AS cnt "
                        f"FROM message_fts WHERE {where_base} AND CAST(local_type AS INTEGER) = 47 "
                        "GROUP BY username",
                        (start_ts, end_ts, my_username),
                    ).fetchall()
                except Exception:
                    rows_u = []
                for r in rows_u:
                    if not r:
                        continue
                    username = str(r[0] or "").strip()
                    if not username:
                        continue
                    try:
                        cnt = int(r[1] or 0)
                    except Exception:
                        cnt = 0
                    if cnt > 0:
                        sticker_by_username[username] += cnt

                try:
                    rows_t = conn.execute(
                        "SELECT "
                        "date(datetime(ts, 'unixepoch', 'localtime')) AS d, "
                        "CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS h, "
                        "CAST(strftime('%w', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS w "
                        "FROM ("
                        f"  SELECT {ts_expr} AS ts "
                        "  FROM message_fts "
                        f"  WHERE {where_base} AND CAST(local_type AS INTEGER) = 47"
                        ") sub",
                        (start_ts, end_ts, my_username),
                    ).fetchall()
                except Exception:
                    rows_t = []
                for r in rows_t:
                    if not r:
                        continue
                    d = str(r[0] or "").strip()
                    try:
                        h = int(r[1] if r[1] is not None else -1)
                    except Exception:
                        h = -1
                    try:
                        w0 = int(r[2] if r[2] is not None else -1)
                    except Exception:
                        w0 = -1
                    if d:
                        sticker_active_days.add(d)
                    if 0 <= h <= 23:
                        hour_counts[h] += 1
                    if 0 <= w0 <= 6:
                        # sqlite: 0=Sun..6=Sat -> 0=Mon..6=Sun
                        w = 6 if w0 == 0 else (w0 - 1)
                        weekday_counts[w] += 1

                try:
                    rows_text = conn.execute(
                        f"SELECT \"text\" FROM message_fts "
                        f"WHERE {where_base} AND render_type = 'text' "
                        "AND \"text\" IS NOT NULL AND TRIM(\"text\") != ''",
                        (start_ts, end_ts, my_username),
                    ).fetchall()
                except Exception:
                    rows_text = []
                for r in rows_text:
                    txt = str((r[0] if r else "") or "")
                    if not txt:
                        continue
                    txt_norm = _normalize_index_text_for_emoji_match(txt)
                    if emoji_regex is not None and txt_norm:
                        for m in emoji_regex.finditer(txt_norm):
                            nk = str(m.group(0) or "")
                            k = emoji_norm_to_key.get(nk) or nk
                            if k:
                                text_emoji_counts[k] += 1
                    for u in _extract_unicode_emoji_tokens(txt_norm):
                        if u:
                            unicode_emoji_counts[u] += 1
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Parse local_type=47 payloads from raw message DBs (md5/cdnurl), plus fallback counters when index missing.
    session_usernames = _list_session_usernames(account_dir / "session.db")
    md5_to_username: dict[str, str] = {}
    table_to_username: dict[str, str] = {}
    for u in session_usernames:
        md5_hex = hashlib.md5(u.encode("utf-8")).hexdigest().lower()
        md5_to_username[md5_hex] = u
        table_to_username[f"msg_{md5_hex}"] = u
        table_to_username[f"chat_{md5_hex}"] = u

    def resolve_username_from_table(table_name: str) -> str:
        ln = str(table_name or "").lower()
        x = table_to_username.get(ln)
        if x:
            return x
        m = _MD5_HEX_RE.search(ln)
        if m:
            return str(md5_to_username.get(m.group(0).lower()) or "")
        return ""

    resource_conn: sqlite3.Connection | None = None
    resource_chat_id_cache: dict[str, Optional[int]] = {}
    resource_db_path = account_dir / "message_resource.db"
    if resource_db_path.exists():
        try:
            resource_conn = sqlite3.connect(str(resource_db_path))
        except Exception:
            resource_conn = None

    ts_expr = (
        "CASE "
        "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
        "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
        "ELSE CAST(create_time AS INTEGER) "
        "END"
    )

    def _has_packed_info_data_column(conn: sqlite3.Connection, quoted_table: str) -> bool:
        try:
            cols = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        except Exception:
            return False
        for c in cols:
            if not c or len(c) < 2:
                continue
            name0 = c[1]
            if isinstance(name0, memoryview):
                name0 = name0.tobytes()
            if isinstance(name0, (bytes, bytearray)):
                try:
                    name0 = bytes(name0).decode("utf-8", errors="ignore")
                except Exception:
                    name0 = ""
            if str(name0 or "").strip().lower() == "packed_info_data":
                return True
        return False

    def _extract_sticker_from_row(
        *,
        row: sqlite3.Row,
        username: str,
        record_maps: bool,
        count_wechat_builtin: bool,
    ) -> tuple[int, str, str]:
        create_time_raw = int(row["create_time"] or 0)
        ts = create_time_raw
        if ts > 1_000_000_000_000:
            ts = int(ts / 1000)

        raw_text = ""
        try:
            raw_text = _decode_message_content(row["compress_content"], row["message_content"]).strip()
        except Exception:
            raw_text = ""

        emoji_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
        emoji_md5 = str(emoji_md5 or "").strip().lower()

        emoji_url = _extract_xml_attr(raw_text, "cdnurl") or _extract_xml_tag_text(raw_text, "cdn_url")
        emoji_url = html.unescape(str(emoji_url or "").strip())

        packed_emoji_id: Optional[int] = None
        try:
            _, packed_emoji_id = _extract_packed_emoji_meta(row["packed_info_data"])
        except Exception:
            packed_emoji_id = None

        if (not emoji_md5) and resource_conn is not None:
            chat_id = resource_chat_id_cache.get(username)
            if username not in resource_chat_id_cache:
                chat_id = _resource_lookup_chat_id(resource_conn, username)
                resource_chat_id_cache[username] = chat_id
            try:
                emoji_md5 = _lookup_resource_md5(
                    resource_conn,
                    chat_id,
                    message_local_type=47,
                    server_id=int(row["server_id"] or 0),
                    local_id=int(row["local_id"] or 0),
                    create_time=create_time_raw,
                )
            except Exception:
                emoji_md5 = ""

        emoji_md5 = str(emoji_md5 or "").strip().lower()
        sticker_key = ""
        if emoji_md5:
            sticker_key = f"md5:{emoji_md5}"
            if record_maps:
                sticker_key_md5[sticker_key] = emoji_md5
        elif packed_emoji_id is not None and int(packed_emoji_id) > 0:
            expr_id = int(packed_emoji_id)
            sticker_key = f"expr:{expr_id}"
            if record_maps:
                sticker_key_expr_id[sticker_key] = expr_id
            if count_wechat_builtin and expr_id in expression_id_to_asset:
                wechat_emoji_counts[expr_id] += 1

        return ts, sticker_key, emoji_url

    db_paths = [p for p in _iter_message_db_paths(account_dir) if not p.name.lower().startswith("biz_message")]
    for db_path in db_paths:
        if not db_path.exists():
            continue

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            my_rowid: Optional[int] = None
            try:
                r2 = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (my_username,),
                ).fetchone()
                if r2 is not None and r2[0] is not None:
                    my_rowid = int(r2[0])
            except Exception:
                my_rowid = None
            if my_rowid is None:
                continue

            tables = _list_message_tables(conn)
            for table_name in tables:
                username = resolve_username_from_table(table_name)
                qt = _quote_ident(table_name)

                # Fallback-only counters when search index is unavailable.
                if not used_index:
                    try:
                        r_total = conn.execute(
                            f"SELECT COUNT(1) FROM {qt} "
                            f"WHERE {ts_expr} >= ? AND {ts_expr} < ? "
                            "AND real_sender_id = ? AND CAST(local_type AS INTEGER) != 10000",
                            (start_ts, end_ts, my_rowid),
                        ).fetchone()
                        total_sent_messages += int((r_total[0] if r_total else 0) or 0)
                    except Exception:
                        pass

                    try:
                        rows_text = conn.execute(
                            f"SELECT message_content, compress_content FROM {qt} "
                            f"WHERE {ts_expr} >= ? AND {ts_expr} < ? "
                            "AND real_sender_id = ? AND CAST(local_type AS INTEGER) = 1",
                            (start_ts, end_ts, my_rowid),
                        ).fetchall()
                    except Exception:
                        rows_text = []
                    for rt in rows_text:
                        try:
                            txt = _decode_message_content(rt["compress_content"], rt["message_content"]).strip()
                        except Exception:
                            txt = ""
                        if not txt:
                            continue
                        txt_norm = _normalize_index_text_for_emoji_match(txt)
                        if emoji_regex is not None and txt_norm:
                            for m in emoji_regex.finditer(txt_norm):
                                nk = str(m.group(0) or "")
                                k = emoji_norm_to_key.get(nk) or nk
                                if k:
                                    text_emoji_counts[k] += 1
                        for u in _extract_unicode_emoji_tokens(txt_norm):
                            if u:
                                unicode_emoji_counts[u] += 1

                try:
                    packed_info_expr = "packed_info_data" if _has_packed_info_data_column(conn, qt) else "NULL AS packed_info_data"
                    rows_emoji = conn.execute(
                        f"SELECT server_id, local_id, create_time, message_content, compress_content, {packed_info_expr} "
                        f"FROM {qt} "
                        f"WHERE {ts_expr} >= ? AND {ts_expr} < ? "
                        "AND real_sender_id = ? AND CAST(local_type AS INTEGER) = 47",
                        (start_ts, end_ts, my_rowid),
                    ).fetchall()
                except Exception:
                    rows_emoji = []

                for r in rows_emoji:
                    ts, sticker_key, emoji_url = _extract_sticker_from_row(
                        row=r,
                        username=username,
                        record_maps=True,
                        count_wechat_builtin=True,
                    )

                    if not used_index:
                        sent_sticker_count += 1
                        if ts > 0:
                            dt = datetime.fromtimestamp(ts)
                            sticker_active_days.add(dt.strftime("%Y-%m-%d"))
                            hour_counts[dt.hour] += 1
                            sticker_by_username[username] += 1
                            weekday_counts[dt.weekday()] += 1

                    if not sticker_key:
                        continue

                    sticker_key_counts[sticker_key] += 1
                    prev_first_ts = sticker_key_first_ts_in_year.get(sticker_key)
                    if ts > 0 and (prev_first_ts is None or ts < prev_first_ts):
                        sticker_key_first_ts_in_year[sticker_key] = ts
                    if emoji_url and (sticker_key not in sticker_url_map):
                        sticker_url_map[sticker_key] = emoji_url
                    if username and (sticker_key not in sticker_sample_username):
                        sticker_sample_username[sticker_key] = username
                    if username:
                        sticker_key_username_counts[sticker_key][username] += 1
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    sticker_keys_in_year = set(sticker_key_counts.keys())
    sticker_key_last_ts_before_year: dict[str, int] = {}
    if sticker_keys_in_year and my_username:
        for db_path in db_paths:
            if not db_path.exists():
                continue

            conn: sqlite3.Connection | None = None
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                conn.text_factory = bytes

                my_rowid: Optional[int] = None
                try:
                    r2 = conn.execute(
                        "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                        (my_username,),
                    ).fetchone()
                    if r2 is not None and r2[0] is not None:
                        my_rowid = int(r2[0])
                except Exception:
                    my_rowid = None
                if my_rowid is None:
                    continue

                tables = _list_message_tables(conn)
                for table_name in tables:
                    username = resolve_username_from_table(table_name)
                    qt = _quote_ident(table_name)
                    packed_info_expr = (
                        "packed_info_data" if _has_packed_info_data_column(conn, qt) else "NULL AS packed_info_data"
                    )
                    try:
                        rows_hist = conn.execute(
                            f"SELECT server_id, local_id, create_time, message_content, compress_content, {packed_info_expr} "
                            f"FROM {qt} "
                            f"WHERE {ts_expr} < ? "
                            "AND real_sender_id = ? AND CAST(local_type AS INTEGER) = 47",
                            (start_ts, my_rowid),
                        )
                    except Exception:
                        rows_hist = []

                    for r in rows_hist:
                        ts, sticker_key, _ = _extract_sticker_from_row(
                            row=r,
                            username=username,
                            record_maps=False,
                            count_wechat_builtin=False,
                        )
                        if (not sticker_key) or (sticker_key not in sticker_keys_in_year) or ts <= 0:
                            continue
                        prev_ts = sticker_key_last_ts_before_year.get(sticker_key)
                        if prev_ts is None or ts > prev_ts:
                            sticker_key_last_ts_before_year[sticker_key] = ts
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

    if resource_conn is not None:
        try:
            resource_conn.close()
        except Exception:
            pass

    # Prefer index total when available, but keep non-negative relationship.
    if used_index:
        sent_sticker_count = max(int(sent_sticker_count), int(sum(sticker_key_counts.values())), int(sent_sticker_count))

    sent_sticker_count = int(sent_sticker_count)
    sticker_days = int(len(sticker_active_days))
    sticker_per_day = (float(sent_sticker_count) / float(sticker_days)) if sticker_days > 0 else 0.0
    sticker_share = (float(sent_sticker_count) / float(total_sent_messages)) if total_sent_messages > 0 else 0.0
    unique_sticker_type_count = int(len(sticker_key_counts))
    revive_gap_days_threshold = 60
    new_sticker_count_this_year = 0
    revived_sticker_count = 0
    revived_max_gap_days = 0
    new_sticker_keys_in_year: set[str] = set()
    revived_sticker_keys_in_year: set[str] = set()
    revived_gap_days_by_key: dict[str, int] = {}
    for sticker_key, first_ts in sticker_key_first_ts_in_year.items():
        if first_ts <= 0:
            continue
        prev_ts = sticker_key_last_ts_before_year.get(sticker_key)
        if prev_ts is None or prev_ts <= 0:
            new_sticker_count_this_year += 1
            new_sticker_keys_in_year.add(sticker_key)
            continue
        gap_days = int(max(0, (int(first_ts) - int(prev_ts))) // 86400)
        if gap_days >= revive_gap_days_threshold:
            revived_sticker_count += 1
            revived_sticker_keys_in_year.add(sticker_key)
            revived_gap_days_by_key[sticker_key] = int(gap_days)
            if gap_days > revived_max_gap_days:
                revived_max_gap_days = gap_days
    new_sticker_share = (
        float(new_sticker_count_this_year) / float(unique_sticker_type_count)
        if unique_sticker_type_count > 0
        else 0.0
    )
    revived_sticker_share = (
        float(revived_sticker_count) / float(unique_sticker_type_count)
        if unique_sticker_type_count > 0
        else 0.0
    )

    peak_hour: Optional[int] = None
    if hour_counts:
        peak_hour = max(range(24), key=lambda h: (int(hour_counts.get(h, 0)), -h))

    peak_weekday: Optional[int] = None
    if weekday_counts:
        peak_weekday = max(range(7), key=lambda w: (int(weekday_counts.get(w, 0)), -w))
    peak_weekday_name = _weekday_name_zh(peak_weekday if peak_weekday is not None else -1)

    def pick_sticker_owner_username(sticker_key: str) -> str:
        counts = sticker_key_username_counts.get(sticker_key)
        if counts:
            try:
                return sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[0][0]
            except Exception:
                pass
        return str(sticker_sample_username.get(sticker_key) or "")

    top_stickers_raw = sorted(sticker_key_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:6]
    new_sticker_samples_raw = sorted(
        [
            (k, int(sticker_key_counts.get(k, 0)))
            for k in new_sticker_keys_in_year
            if int(sticker_key_counts.get(k, 0)) > 0
        ],
        key=lambda kv: (-int(kv[1]), str(kv[0])),
    )[:4]
    revived_sticker_samples_raw = sorted(
        [
            (k, int(sticker_key_counts.get(k, 0)))
            for k in revived_sticker_keys_in_year
            if int(sticker_key_counts.get(k, 0)) > 0
        ],
        key=lambda kv: (-int(kv[1]), str(kv[0])),
    )[:4]

    sample_sticker_keys = [k for k, _ in top_stickers_raw + new_sticker_samples_raw + revived_sticker_samples_raw]
    sample_usernames = [pick_sticker_owner_username(key) for key in sample_sticker_keys]
    sample_contact_rows = _load_contact_rows(
        account_dir / "contact.db",
        [u for u in sample_usernames if u],
    )

    def build_sticker_stat_item(key: str, cnt: int) -> dict[str, Any]:
        md5 = str(sticker_key_md5.get(key) or "")
        expr_id = int(sticker_key_expr_id.get(key) or 0)
        sample_username = pick_sticker_owner_username(key)
        remote_url = str(sticker_url_map.get(key) or "")
        sample_row = sample_contact_rows.get(sample_username) if sample_username else None
        sample_display = _pick_display_name(sample_row, sample_username) if sample_username else ""
        sample_avatar_url = _build_avatar_url(str(account_dir.name or ""), sample_username) if sample_username else ""
        expr_asset = str(expression_id_to_asset.get(expr_id) or "") if expr_id > 0 else ""
        expr_label = str(expression_id_to_label.get(expr_id) or "") if expr_id > 0 else ""
        local_url = (
            _build_local_emoji_url(
                account_name=str(account_dir.name or ""),
                md5=str(md5),
                username=sample_username,
                emoji_remote_url=remote_url,
            )
            if md5
            else (f"/wxemoji/{expr_asset}" if expr_asset else "")
        )
        ratio = (float(cnt) / float(sent_sticker_count)) if sent_sticker_count > 0 else 0.0
        return {
            "md5": str(md5 or key),
            "count": int(cnt),
            "ratio": float(ratio),
            "emojiUrl": local_url,
            "emojiRemoteUrl": remote_url,
            "emojiId": int(expr_id) if expr_id > 0 else None,
            "emojiAssetPath": f"/wxemoji/{expr_asset}" if expr_asset else "",
            "emojiLabel": expr_label,
            "sampleUsername": sample_username,
            "sampleDisplayName": sample_display,
            "sampleAvatarUrl": sample_avatar_url,
        }

    top_stickers: list[dict[str, Any]] = [build_sticker_stat_item(key, cnt) for key, cnt in top_stickers_raw]
    new_sticker_samples: list[dict[str, Any]] = [
        build_sticker_stat_item(key, cnt) for key, cnt in new_sticker_samples_raw
    ]
    revived_sticker_samples: list[dict[str, Any]] = []
    for key, cnt in revived_sticker_samples_raw:
        item = build_sticker_stat_item(key, cnt)
        item["gapDays"] = int(revived_gap_days_by_key.get(key) or 0)
        revived_sticker_samples.append(item)

    top_wechat_emojis_raw = sorted(wechat_emoji_counts.items(), key=lambda kv: (-int(kv[1]), int(kv[0])))[:8]
    top_wechat_emojis: list[dict[str, Any]] = []
    for expr_id, cnt in top_wechat_emojis_raw:
        expr_asset = str(expression_id_to_asset.get(int(expr_id)) or "")
        expr_label = str(expression_id_to_label.get(int(expr_id)) or f"[表情{int(expr_id)}]")
        top_wechat_emojis.append(
            {
                "id": int(expr_id),
                "key": expr_label,
                "count": int(cnt),
                "assetPath": f"/wxemoji/{expr_asset}" if expr_asset else "",
            }
        )

    top_text_emojis_raw = sorted(text_emoji_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:6]
    top_text_emojis: list[dict[str, Any]] = []
    for key, cnt in top_text_emojis_raw:
        asset = str(emoji_table.get(key) or "")
        top_text_emojis.append(
            {
                "key": str(key),
                "count": int(cnt),
                "assetPath": f"/wxemoji/{asset}" if asset else "",
            }
        )

    top_unicode_emojis_raw = sorted(unicode_emoji_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:8]
    top_unicode_emojis: list[dict[str, Any]] = []
    for key, cnt in top_unicode_emojis_raw:
        top_unicode_emojis.append({"emoji": str(key), "count": int(cnt)})

    top_battle_partner_obj: dict[str, Any] = {
        "username": "",
        "displayName": "",
        "maskedName": "",
        "avatarUrl": "",
        "stickerCount": 0,
    }
    battle_candidates = [
        (u, c)
        for u, c in sticker_by_username.items()
        if u
        and (not u.endswith("@chatroom"))
        and _should_keep_session(u, include_official=False)
        and int(c) > 0
    ]
    if battle_candidates:
        top_u, top_cnt = sorted(battle_candidates, key=lambda kv: (-int(kv[1]), str(kv[0])))[0]
        rows = _load_contact_rows(account_dir / "contact.db", [top_u])
        row = rows.get(top_u)
        display = _pick_display_name(row, top_u)
        top_battle_partner_obj = {
            "username": top_u,
            "displayName": display,
            "maskedName": display,
            "avatarUrl": _build_avatar_url(str(account_dir.name or ""), top_u),
            "stickerCount": int(top_cnt),
        }

    top_text = top_text_emojis[0] if top_text_emojis else None
    top_wechat = top_wechat_emojis[0] if top_wechat_emojis else None
    persona = _pick_persona(
        sent_sticker_count=sent_sticker_count,
        sticker_share=float(sticker_share),
        peak_hour=peak_hour,
        top_text_emoji_count=int((top_text.get("count") if top_text else 0) or 0)
        + int((top_wechat.get("count") if top_wechat else 0) or 0),
    )

    lines: list[str] = []
    if sent_sticker_count > 0:
        lines.append(
            f"这一年，你用 {sent_sticker_count:,} 张表情包把聊天变得更有温度；在 {sticker_days:,} 个活跃日里，日均 {sticker_per_day:.1f} 张。"
        )
    else:
        lines.append("这一年你几乎没发过表情包。")

    if peak_hour is not None and peak_weekday_name:
        lines.append(f"你最活跃的时刻是 {peak_weekday_name} {peak_hour}:00。")

    if top_stickers:
        top0 = top_stickers[0]
        label0 = str(top0.get("emojiLabel") or "")
        if label0:
            lines.append(f"年度 C 位表情是 {label0}（{int(top0['count']):,} 次）。")
        else:
            lines.append(f"年度 C 位表情是 {top0['md5'][:8]}…（{int(top0['count']):,} 次）。")

    if top_wechat:
        lines.append(f"你最常用的小黄脸是 {top_wechat['key']}，共 {int(top_wechat['count']):,} 次。")
    elif top_text:
        lines.append(f"在文字聊天里，你最常打的小黄脸是 {top_text['key']}，共 {int(top_text['count']):,} 次。")
    if top_unicode_emojis:
        lines.append(f"普通 Emoji 最常用 {top_unicode_emojis[0]['emoji']}，共 {int(top_unicode_emojis[0]['count']):,} 次。")

    if int(top_battle_partner_obj.get("stickerCount") or 0) > 0:
        lines.append(
            f"和你斗图最狠的是 {top_battle_partner_obj['displayName']}（{int(top_battle_partner_obj['stickerCount']):,} 发）。"
        )

    lines.append(f"年度人格：{persona['label']}。")

    return {
        "year": int(year),
        "sentStickerCount": int(sent_sticker_count),
        "stickerActiveDays": int(sticker_days),
        "stickerPerActiveDay": float(sticker_per_day),
        "stickerShareOfSentMessages": float(sticker_share),
        "uniqueStickerTypeCount": int(unique_sticker_type_count),
        "newStickerCountThisYear": int(new_sticker_count_this_year),
        "newStickerShare": float(new_sticker_share),
        "newStickerSamples": new_sticker_samples,
        "revivedStickerCount": int(revived_sticker_count),
        "revivedStickerShare": float(revived_sticker_share),
        "revivedMinGapDays": int(revive_gap_days_threshold),
        "revivedMaxGapDays": int(revived_max_gap_days),
        "revivedStickerSamples": revived_sticker_samples,
        "peakHour": int(peak_hour) if peak_hour is not None else None,
        "peakWeekday": int(peak_weekday) if peak_weekday is not None else None,
        "peakWeekdayName": peak_weekday_name,
        "stickerHourCounts": [int(hour_counts.get(h, 0)) for h in range(24)],
        "stickerWeekdayCounts": [int(weekday_counts.get(w, 0)) for w in range(7)],
        "topStickers": top_stickers,
        "topWechatEmojis": top_wechat_emojis,
        "topTextEmojis": top_text_emojis,
        "topUnicodeEmojis": top_unicode_emojis,
        "topBattlePartner": top_battle_partner_obj,
        "persona": persona,
        "lines": lines,
        "settings": {"usedIndex": bool(used_index)},
    }


def build_card_04_emoji_universe(*, account_dir: Path, year: int) -> dict[str, Any]:
    data = compute_emoji_universe_stats(account_dir=account_dir, year=year)

    sent_sticker_count = int(data.get("sentStickerCount") or 0)
    sticker_days = int(data.get("stickerActiveDays") or 0)
    sticker_per_day = float(data.get("stickerPerActiveDay") or 0.0)
    top_stickers = list(data.get("topStickers") or [])
    top_wechat_emojis = list(data.get("topWechatEmojis") or [])
    top_text_emojis = list(data.get("topTextEmojis") or [])
    top_unicode_emojis = list(data.get("topUnicodeEmojis") or [])
    peak_weekday_name = str(data.get("peakWeekdayName") or "")
    peak_hour = data.get("peakHour")

    if sent_sticker_count <= 0 and (not top_wechat_emojis) and (not top_text_emojis) and (not top_unicode_emojis):
        narrative = "今年你几乎没用表情表达。"
    else:
        parts: list[str] = []
        if sent_sticker_count > 0:
            parts.append(
                f"这一年，你用 {sent_sticker_count:,} 张表情包把聊天变得更有温度；在 {sticker_days:,} 个活跃日里，日均 {sticker_per_day:.1f} 张。"
            )
        if peak_hour is not None and peak_weekday_name:
            parts.append(f"你最活跃的时刻是 {peak_weekday_name} {int(peak_hour)}:00。")
        tail_parts: list[str] = []
        if top_stickers:
            x = top_stickers[0]
            label0 = str(x.get("emojiLabel") or "").strip()
            if label0:
                tail_parts.append(f"年度 C 位表情是 {label0}（{int(x.get('count') or 0):,} 次）")
            else:
                tail_parts.append(f"年度 C 位表情是 {str(x.get('md5') or '')[:8]}…（{int(x.get('count') or 0):,} 次）")
        if top_wechat_emojis:
            x = top_wechat_emojis[0]
            tail_parts.append(f"你最常用的小黄脸是 {str(x.get('key') or '')}（{int(x.get('count') or 0):,} 次）")
        elif top_text_emojis:
            x = top_text_emojis[0]
            tail_parts.append(f"在文字聊天里，你最常打的小黄脸是 {str(x.get('key') or '')}（{int(x.get('count') or 0):,} 次）")
        if top_unicode_emojis:
            x = top_unicode_emojis[0]
            tail_parts.append(f"普通 Emoji 最常用 {str(x.get('emoji') or '')}（{int(x.get('count') or 0):,} 次）")
        if tail_parts:
            parts.append("，".join(tail_parts) + "。")
        narrative = "".join(parts)

    return {
        "id": 5,
        "title": "这一年，你的表情包里藏了多少心情？",
        "scope": "global",
        "category": "B",
        "status": "ok",
        "kind": "emoji/annual_universe",
        "narrative": narrative,
        "data": data,
    }
