from __future__ import annotations

import math
import random
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pypinyin import lazy_pinyin, Style

from ...chat_helpers import _decode_message_content, _decode_sqlite_text, _iter_message_db_paths, _quote_ident
from ...chat_search_index import get_chat_search_index_db_path
from ...logging_config import get_logger

logger = get_logger(__name__)


# 键盘布局中用于“磨损”展示的按键（字母 + 数字 + 常用标点）。
# 注意：功能键（Tab/Enter/Backspace 等）不统计；空格键单独放在 spaceHits。
_KEYBOARD_KEYS = (
    list("`1234567890-=")
    + list("qwertyuiop[]\\")
    + list("asdfghjkl;\'")
    + list("zxcvbnm,./")
)
_KEYBOARD_KEY_SET = set(_KEYBOARD_KEYS)

# 将“显示字符”映射到键盘上的“实际按键”（用基础键位表示，如 '!' => '1', '？' => '/'）。
_CHAR_TO_KEY: dict[str, str] = {
    # ASCII shifted symbols
    "~": "`",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "<": ",",
    ">": ".",
    "?": "/",
    # Common fullwidth / CJK punctuation (approximate key mapping)
    "～": "`",
    "！": "1",
    "＠": "2",
    "＃": "3",
    "＄": "4",
    "％": "5",
    "＾": "6",
    "＆": "7",
    "＊": "8",
    "（": "9",
    "）": "0",
    "¥": "4",
    "￥": "4",
    "＿": "-",
    "＋": "=",
    "｛": "[",
    "｝": "]",
    "｜": "\\",
    "：": ";",
    "＂": "'",
    "＜": ",",
    "＞": ".",
    "？": "/",
    "，": ",",
    "、": ",",
    "。": ".",
    "．": ".",
    "；": ";",
    "“": "'",
    "”": "'",
    "‘": "'",
    "’": "'",
    "【": "[",
    "】": "]",
    "《": ",",
    "》": ".",
    "—": "-",
    "－": "-",
    "＝": "=",
    "／": "/",
    "＼": "\\",
    "·": "`",  # 常见：中文输入法下“·”常用 ` 键打出
    "…": ".",  # 近似处理：省略号按 '.' 计
}

# 默认拼音字母频率分布（用于：有中文但采样不足时的兜底估算）
_DEFAULT_PINYIN_FREQ = {
    "a": 0.121,
    "i": 0.118,
    "n": 0.098,
    "e": 0.089,
    "u": 0.082,
    "g": 0.072,
    "h": 0.065,
    "o": 0.052,
    "z": 0.048,
    "s": 0.042,
    "x": 0.038,
    "y": 0.036,
    "d": 0.032,
    "l": 0.028,
    "j": 0.026,
    "b": 0.022,
    "c": 0.020,
    "w": 0.018,
    "m": 0.016,
    "f": 0.014,
    "t": 0.012,
    "r": 0.010,
    "p": 0.009,
    "k": 0.007,
    "q": 0.005,
    "v": 0.001,
}
_AVG_PINYIN_LEN = 2.8


def _is_cjk_han(ch: str) -> bool:
    """是否为中文汉字（用于拼音估算）。"""
    if not ch:
        return False
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF) or (0x3400 <= o <= 0x4DBF)


def _char_to_key(ch: str) -> str | None:
    """将单个字符映射为键盘按键 code（与前端键盘布局的 code 保持一致）。"""
    if not ch:
        return None

    # Fullwidth digits: '０'..'９'
    if "０" <= ch <= "９":
        return chr(ord(ch) - ord("０") + ord("0"))

    if ch in _KEYBOARD_KEY_SET:
        return ch

    mapped = _CHAR_TO_KEY.get(ch)
    if mapped is not None:
        return mapped

    if ch.isalpha():
        low = ch.lower()
        if low in _KEYBOARD_KEY_SET:
            return low

    return None


def _update_keyboard_counters(
    text: str,
    *,
    direct_counter: Counter,
    pinyin_counter: Counter,
    pinyin_cache: dict[str, str],
    do_pinyin: bool,
) -> tuple[int, int, int]:
    """
    扫描一条消息文本，累加：
    - direct_counter: 非中文汉字部分（英文/数字/标点）可直接映射到按键的统计（精确）
    - pinyin_counter: 中文汉字部分的拼音字母统计（仅当 do_pinyin=True 时才做；用于采样估算）
    并返回 (nonspace_chars, cjk_han_chars, space_chars)。
    """
    if not text:
        return 0, 0, 0

    nonspace = 0
    cjk = 0
    spaces = 0

    for ch in text:
        # 真实可见空格：统计进 spaceHits（不计入 sentChars/receivedChars 的口径）
        if ch == " " or ch == "\u3000":
            spaces += 1
            continue
        if ch.isspace():
            continue

        nonspace += 1

        if _is_cjk_han(ch):
            cjk += 1
            if do_pinyin:
                py = pinyin_cache.get(ch)
                if py is None:
                    lst = lazy_pinyin(ch, style=Style.NORMAL)
                    py = (lst[0] or "").lower() if lst else ""
                    pinyin_cache[ch] = py
                for letter in py:
                    # pypinyin 在 Style.NORMAL 下通常只会给出 a-z（含 ü=>v），这里再做一次过滤。
                    if letter in _KEYBOARD_KEY_SET:
                        pinyin_counter[letter] += 1
            continue

        k = _char_to_key(ch)
        if k is not None:
            direct_counter[k] += 1

    return nonspace, cjk, spaces


def compute_keyboard_stats(*, account_dir: Path, year: int, sample_rate: float = 1.0) -> dict[str, Any]:
    """
    统计键盘敲击数据。

    - 英文/数字/标点：可直接从消息文本映射到按键（精确统计）
    - 中文汉字：需要拼音转换，成本高；对“消息”做采样（sample_rate）后估算总体拼音字母分布
    """
    start_ts, end_ts = _year_range_epoch_seconds(year)
    my_username = str(account_dir.name or "").strip()

    sample_rate = max(0.0, min(1.0, float(sample_rate)))

    direct_counter: Counter[str] = Counter()
    pinyin_counter: Counter[str] = Counter()
    pinyin_cache: dict[str, str] = {}

    total_cjk_chars = 0
    sampled_cjk_chars = 0
    actual_space_chars = 0

    total_messages = 0
    sampled_messages = 0
    used_index = False

    # 优先使用搜索索引（更快）
    index_path = get_chat_search_index_db_path(account_dir)
    if index_path.exists():
        conn = sqlite3.connect(str(index_path))
        try:
            has_fts = (
                conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
                is not None
            )
            if has_fts and my_username:
                ts_expr = (
                    "CASE "
                    "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                    "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                    "ELSE CAST(create_time AS INTEGER) "
                    "END"
                )
                where = (
                    f"{ts_expr} >= ? AND {ts_expr} < ? "
                    "AND db_stem NOT LIKE 'biz_message%' "
                    "AND render_type = 'text' "
                    "AND \"text\" IS NOT NULL "
                    "AND TRIM(CAST(\"text\" AS TEXT)) != '' "
                    "AND sender_username = ?"
                )

                sql = f"SELECT \"text\" FROM message_fts WHERE {where}"
                try:
                    cur = conn.execute(sql, (start_ts, end_ts, my_username))
                    used_index = True
                    for row in cur:
                        txt = str(row[0] or "").strip()
                        if not txt:
                            continue
                        total_messages += 1

                        if sample_rate >= 1.0:
                            do_sample = True
                        elif sample_rate <= 0.0:
                            do_sample = False
                        else:
                            do_sample = random.random() < sample_rate

                        if do_sample:
                            sampled_messages += 1

                        _, cjk, spaces = _update_keyboard_counters(
                            txt,
                            direct_counter=direct_counter,
                            pinyin_counter=pinyin_counter,
                            pinyin_cache=pinyin_cache,
                            do_pinyin=do_sample,
                        )
                        total_cjk_chars += cjk
                        actual_space_chars += spaces
                        if do_sample:
                            sampled_cjk_chars += cjk
                except Exception:
                    used_index = False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # 如果索引不可用，回退到直接扫描（慢，但兼容）
    if not used_index:
        db_paths = _iter_message_db_paths(account_dir)
        for db_path in db_paths:
            try:
                if db_path.name.lower().startswith("biz_message"):
                    continue
            except Exception:
                pass
            if not db_path.exists():
                continue

            conn: sqlite3.Connection | None = None
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                conn.text_factory = bytes

                my_rowid: Optional[int]
                try:
                    r2 = conn.execute("SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1", (my_username,)).fetchone()
                    my_rowid = int(r2[0]) if r2 and r2[0] is not None else None
                except Exception:
                    my_rowid = None

                if my_rowid is None:
                    continue

                tables = _list_message_tables(conn)
                if not tables:
                    continue

                ts_expr = (
                    "CASE "
                    "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                    "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                    "ELSE CAST(create_time AS INTEGER) "
                    "END"
                )

                for table in tables:
                    qt = _quote_ident(table)
                    sql = (
                        "SELECT real_sender_id, message_content, compress_content "
                        f"FROM {qt} "
                        "WHERE local_type = 1 "
                        f"  AND {ts_expr} >= ? AND {ts_expr} < ?"
                    )
                    try:
                        cur = conn.execute(sql, (start_ts, end_ts))
                    except Exception:
                        continue

                    for r in cur:
                        try:
                            rsid = int(r["real_sender_id"] or 0)
                        except Exception:
                            rsid = 0

                        if rsid != my_rowid:
                            continue

                        txt = ""
                        try:
                            txt = _decode_message_content(r["compress_content"], r["message_content"]).strip()
                        except Exception:
                            txt = ""
                        if not txt:
                            continue
                        total_messages += 1
                        if sample_rate >= 1.0:
                            do_sample = True
                        elif sample_rate <= 0.0:
                            do_sample = False
                        else:
                            do_sample = random.random() < sample_rate
                        if do_sample:
                            sampled_messages += 1
                        _, cjk, spaces = _update_keyboard_counters(
                            txt,
                            direct_counter=direct_counter,
                            pinyin_counter=pinyin_counter,
                            pinyin_cache=pinyin_cache,
                            do_pinyin=do_sample,
                        )
                        total_cjk_chars += cjk
                        actual_space_chars += spaces
                        if do_sample:
                            sampled_cjk_chars += cjk
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

    # 中文拼音部分：按“中文汉字数量”缩放（比按总字符缩放更合理，也能让数字/标点更准确）
    est_pinyin_counter: Counter[str] = Counter()
    sampled_pinyin_hits = int(sum(pinyin_counter.values()))
    if total_cjk_chars > 0:
        if sampled_cjk_chars > 0 and sampled_pinyin_hits > 0:
            scale_factor = total_cjk_chars / sampled_cjk_chars
            for k, cnt in pinyin_counter.items():
                est_pinyin_counter[k] = int(round(cnt * scale_factor))
        else:
            # 兜底：有中文但采样不足（或采样中无法提取拼音），用默认分布估算
            total_pinyin_hits = int(total_cjk_chars * _AVG_PINYIN_LEN)
            for k, freq in _DEFAULT_PINYIN_FREQ.items():
                est_pinyin_counter[k] = int(freq * total_pinyin_hits)

    key_hits_counter: Counter[str] = Counter()
    key_hits_counter.update(direct_counter)
    key_hits_counter.update(est_pinyin_counter)

    key_hits: dict[str, int] = {k: int(key_hits_counter.get(k, 0)) for k in _KEYBOARD_KEYS}
    total_non_space_hits = int(sum(key_hits.values()))

    # 空格键：= 真实空格（如英文句子） + 中文拼音选词带来的“隐含空格”（粗略估算）
    implied_space_hits = int(sum(est_pinyin_counter.values()) * 0.15)
    space_hits = int(actual_space_chars + implied_space_hits)

    total_key_hits = int(total_non_space_hits + space_hits)

    # 频率只对“非空格键”归一化；空格频率由 spaceHits 单独给出
    key_frequency: dict[str, float] = {}
    for k in _KEYBOARD_KEYS:
        key_frequency[k] = (key_hits.get(k, 0) / total_non_space_hits) if total_non_space_hits > 0 else 0.0

    logger.info(
        "Keyboard stats computed: account=%s year=%s sample_rate=%.2f msgs=%d sampled=%d cjk=%d sampled_cjk=%d total_hits=%d",
        my_username,
        year,
        float(sample_rate),
        int(total_messages),
        int(sampled_messages),
        int(total_cjk_chars),
        int(sampled_cjk_chars),
        int(total_key_hits),
    )

    return {
        "totalKeyHits": total_key_hits,
        "keyHits": key_hits,
        "keyFrequency": key_frequency,
        "spaceHits": space_hits,
    }


def _year_range_epoch_seconds(year: int) -> tuple[int, int]:
    # Use local time boundaries (same semantics as sqlite "localtime").
    start = int(datetime(year, 1, 1).timestamp())
    end = int(datetime(year + 1, 1, 1).timestamp())
    return start, end


def _list_message_tables(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    except Exception:
        return []
    names: list[str] = []
    for r in rows:
        if not r or not r[0]:
            continue
        name = _decode_sqlite_text(r[0]).strip()
        if not name:
            continue
        ln = name.lower()
        if ln.startswith(("msg_", "chat_")):
            names.append(name)
    return names


# Book analogy table (for "sent chars").
_BOOK_ANALOGIES: list[dict[str, Any]] = [
    {"min": 1, "max": 100_000, "level": "小量级", "options": ["一本《小王子》", "一本《解忧杂货店》"]},
    {"min": 100_000, "max": 500_000, "level": "中量级", "options": ["一本《三体Ⅰ：地球往事》", "一套《朝花夕拾+呐喊》（鲁迅经典合集）"]},
    {"min": 500_000, "max": 1_000_000, "level": "大量级", "options": ["一本《红楼梦》（全本）", "一本《百年孤独》（全本无删减）"]},
    {"min": 1_000_000, "max": 5_000_000, "level": "超大量级", "options": ["一套《三体》全三册", "一本《西游记》（全本白话文）"]},
    {"min": 5_000_000, "max": 10_000_000, "level": "千万级Ⅰ", "options": ["一套金庸武侠《射雕+神雕+倚天》（经典三部曲）", "一套《平凡的世界》全三册"]},
    {"min": 10_000_000, "max": 50_000_000, "level": "千万级Ⅱ", "options": ["一套《哈利·波特》全七册（中文版）", "一本《资治通鉴》（文白对照全本）"]},
    {"min": 50_000_000, "max": 100_000_000, "level": "亿级Ⅰ", "options": ["一套《冰与火之歌》全系列（中文版）", "一本《史记》（全本含集解索隐正义）"]},
    {"min": 100_000_000, "max": 500_000_000, "level": "亿级Ⅱ", "options": ["一套《中国大百科全书》（单卷本全册）", "一套《金庸武侠全集》（15部完整版）"]},
    {"min": 500_000_000, "max": None, "level": "亿级Ⅲ", "options": ["一套《四库全书》（文津阁精选集）", "一套《大英百科全书》（国际完整版）"]},
]


# A4 analogy table (for "received chars").
# Estimation assumptions:
# - A4 (single side) holds about 1700 chars (depends on font/spacing; this is an approximation).
# - 70g A4 paper thickness is roughly 0.1mm => 100 sheets ≈ 1cm.
_A4_CHARS_PER_SHEET = 1700
_A4_SHEETS_PER_CM = 100.0

# "Level" is a coarse grouping by character count; the physical object analogy is picked by the
# estimated stacked height (so the text stays self-consistent).
_A4_LEVELS: list[dict[str, Any]] = [
    {"min": 1, "max": 100_000, "level": "小量级"},
    {"min": 100_000, "max": 500_000, "level": "中量级"},
    {"min": 500_000, "max": 1_000_000, "level": "大量级"},
    {"min": 1_000_000, "max": 5_000_000, "level": "超大量级"},
    {"min": 5_000_000, "max": 10_000_000, "level": "千万级Ⅰ"},
    {"min": 10_000_000, "max": 50_000_000, "level": "千万级Ⅱ"},
    {"min": 50_000_000, "max": 100_000_000, "level": "亿级Ⅰ"},
    {"min": 100_000_000, "max": 500_000_000, "level": "亿级Ⅱ"},
    {"min": 500_000_000, "max": None, "level": "亿级Ⅲ"},
]

# Physical object analogies by stacked height (cm).
_A4_HEIGHT_ANALOGIES: list[dict[str, Any]] = [
    {"minCm": 0.0, "maxCm": 0.5, "objects": ["1枚硬币的厚度", "1张银行卡的厚度"]},
    {"minCm": 0.5, "maxCm": 2.0, "objects": ["1叠便利贴", "1本薄款软皮笔记本"]},
    {"minCm": 2.0, "maxCm": 6.0, "objects": ["3-5本加厚硬壳笔记本", "1本厚词典"]},
    {"minCm": 6.0, "maxCm": 30.0, "objects": ["10本办公台账", "1个矮款文件柜单层满装"]},
    {"minCm": 30.0, "maxCm": 60.0, "objects": ["1个标准办公文件盒", "1个登机箱（约55cm）"]},
    {"minCm": 60.0, "maxCm": 200.0, "objects": ["1.7-1.8m成年人身高", "2个办公文件柜叠放"]},
    {"minCm": 200.0, "maxCm": 600.0, "objects": ["2层普通住宅层高", "1棵成年矮树（枇杷树/橘子树）"]},
    {"minCm": 600.0, "maxCm": 2500.0, "objects": ["4-8层居民楼层高", "1棵成年大树（梧桐树/樟树）"]},
    {"minCm": 2500.0, "maxCm": 5000.0, "objects": ["10-18层小高层住宅", "1栋小型临街写字楼"]},
    {"minCm": 5000.0, "maxCm": 25000.0, "objects": ["20-80层超高层住宅", "城市核心区小高层地标"]},
    {"minCm": 25000.0, "maxCm": None, "objects": ["1栋城市核心超高层写字楼", "国内中型摩天大楼（约100层）"]},
]


def _pick_option(options: list[str], *, seed: int) -> str:
    if not options:
        return ""
    idx = abs(int(seed)) % len(options)
    return str(options[idx] or "").strip()


def _pick_book_analogy(chars: int) -> Optional[dict[str, Any]]:
    n = int(chars or 0)
    if n <= 0:
        return None

    for row in _BOOK_ANALOGIES:
        lo = int(row["min"] or 0)
        hi = row.get("max")
        if n < lo:
            continue
        if hi is None or n < int(hi):
            picked = _pick_option(list(row.get("options") or []), seed=n)
            return {
                "level": str(row.get("level") or ""),
                "book": picked,
                "text": f"相当于写了{picked}" if picked else "",
            }
    return None


def _format_height(height_cm: float) -> str:
    try:
        cm = float(height_cm)
    except Exception:
        cm = 0.0
    if cm <= 0:
        return "0cm"
    if cm < 1:
        mm = cm * 10.0
        return f"{mm:.1f}mm"
    if cm < 100:
        if cm < 10:
            return f"{cm:.1f}cm"
        return f"{cm:.0f}cm"
    m = cm / 100.0
    if m < 10:
        return f"{m:.1f}m"
    return f"{m:.0f}m"


def _a4_stats(chars: int) -> dict[str, Any]:
    # Rough estimate: 1 A4 page ~ 1700 chars; 100 pages ~ 1cm thick.
    n = int(chars or 0)
    if n <= 0:
        return {"sheets": 0, "heightCm": 0.0, "heightText": "0cm"}
    sheets = int(math.ceil(n / float(_A4_CHARS_PER_SHEET)))
    height_cm = float(sheets) / float(_A4_SHEETS_PER_CM)
    return {"sheets": int(sheets), "heightCm": float(height_cm), "heightText": _format_height(height_cm)}


def _pick_a4_analogy(chars: int) -> Optional[dict[str, Any]]:
    n = int(chars or 0)
    if n <= 0:
        return None

    a4 = _a4_stats(n)

    level = ""
    for row in _A4_LEVELS:
        lo = int(row["min"] or 0)
        hi = row.get("max")
        if n < lo:
            continue
        if hi is None or n < int(hi):
            level = str(row.get("level") or "")
            break

    height_cm = float(a4.get("heightCm") or 0.0)
    picked = ""
    for row in _A4_HEIGHT_ANALOGIES:
        lo = float(row.get("minCm") or 0.0)
        hi = row.get("maxCm")
        if height_cm < lo:
            continue
        if hi is None or height_cm < float(hi):
            picked = _pick_option(list(row.get("objects") or []), seed=n)
            break

    return {
        "level": level,
        "object": picked,
        "a4": a4,
        "text": (
            f"大约 {int(a4['sheets']):,} 张 A4，堆起来约 {a4['heightText']}" + (f"，差不多是{picked}的高度" if picked else "")
        ).strip("，"),
    }


def compute_text_message_char_counts(*, account_dir: Path, year: int) -> tuple[int, int]:
    """Return (sent_chars, received_chars) for render_type='text' messages in the year."""

    start_ts, end_ts = _year_range_epoch_seconds(year)
    my_username = str(account_dir.name or "").strip()

    # Prefer search index when available.
    index_path = get_chat_search_index_db_path(account_dir)
    if index_path.exists():
        conn = sqlite3.connect(str(index_path))
        try:
            has_fts = (
                conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_fts' LIMIT 1").fetchone()
                is not None
            )
            if has_fts:
                ts_expr = (
                    "CASE "
                    "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                    "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                    "ELSE CAST(create_time AS INTEGER) "
                    "END"
                )
                where = (
                    f"{ts_expr} >= ? AND {ts_expr} < ? "
                    "AND db_stem NOT LIKE 'biz_message%' "
                    "AND render_type = 'text' "
                    "AND \"text\" IS NOT NULL "
                    "AND TRIM(CAST(\"text\" AS TEXT)) != ''"
                )

                sql_total = f"SELECT COALESCE(SUM(LENGTH(REPLACE(\"text\", ' ', ''))), 0) AS chars FROM message_fts WHERE {where}"
                r_total = conn.execute(sql_total, (start_ts, end_ts)).fetchone()
                total_chars = int((r_total[0] if r_total else 0) or 0)

                if my_username:
                    sql_sent = f"{sql_total} AND sender_username = ?"
                    r_sent = conn.execute(sql_sent, (start_ts, end_ts, my_username)).fetchone()
                    sent_chars = int((r_sent[0] if r_sent else 0) or 0)
                else:
                    sent_chars = 0

                recv_chars = max(0, total_chars - sent_chars)
                return sent_chars, recv_chars
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # Fallback: scan message shards directly (slower, but works without the index).
    t0 = time.time()
    sent_total = 0
    recv_total = 0

    db_paths = _iter_message_db_paths(account_dir)
    for db_path in db_paths:
        try:
            if db_path.name.lower().startswith("biz_message"):
                continue
        except Exception:
            pass
        if not db_path.exists():
            continue

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            my_rowid: Optional[int]
            try:
                r2 = conn.execute("SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1", (my_username,)).fetchone()
                my_rowid = int(r2[0]) if r2 and r2[0] is not None else None
            except Exception:
                my_rowid = None

            tables = _list_message_tables(conn)
            if not tables:
                continue

            ts_expr = (
                "CASE "
                "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                "ELSE CAST(create_time AS INTEGER) "
                "END"
            )

            for table in tables:
                qt = _quote_ident(table)
                sql = (
                    "SELECT real_sender_id, message_content, compress_content "
                    f"FROM {qt} "
                    "WHERE local_type = 1 "
                    f"  AND {ts_expr} >= ? AND {ts_expr} < ?"
                )
                try:
                    cur = conn.execute(sql, (start_ts, end_ts))
                except Exception:
                    continue

                for r in cur:
                    try:
                        rsid = int(r["real_sender_id"] or 0)
                    except Exception:
                        rsid = 0
                    txt = ""
                    try:
                        txt = _decode_message_content(r["compress_content"], r["message_content"]).strip()
                    except Exception:
                        txt = ""
                    if not txt:
                        continue

                    # Match search index semantics: count non-whitespace characters.
                    cnt = 0
                    for ch in txt:
                        if not ch.isspace():
                            cnt += 1
                    if cnt <= 0:
                        continue

                    if my_rowid is not None and rsid == my_rowid:
                        sent_total += cnt
                    else:
                        recv_total += cnt
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    logger.info(
        "Wrapped card#2 message chars computed (fallback scan): account=%s year=%s sent=%s recv=%s dbs=%s elapsed=%.2fs",
        str(account_dir.name or "").strip(),
        year,
        int(sent_total),
        int(recv_total),
        len(db_paths),
        time.time() - t0,
    )
    return int(sent_total), int(recv_total)


def build_card_02_message_chars(*, account_dir: Path, year: int) -> dict[str, Any]:
    sent_chars, recv_chars = compute_text_message_char_counts(account_dir=account_dir, year=year)

    sent_book = _pick_book_analogy(sent_chars)
    recv_a4 = _pick_a4_analogy(recv_chars)

    # 计算键盘敲击统计
    keyboard_stats = compute_keyboard_stats(account_dir=account_dir, year=year, sample_rate=1.0)

    if sent_chars > 0 and recv_chars > 0:
        narrative = f"你今年在微信里打了 {sent_chars:,} 个字，也收到了 {recv_chars:,} 个字。"
    elif sent_chars > 0:
        narrative = f"你今年在微信里打了 {sent_chars:,} 个字。"
    elif recv_chars > 0:
        narrative = f"你今年在微信里收到了 {recv_chars:,} 个字。"
    else:
        narrative = "今年你还没有文字消息"

    return {
        "id": 2,
        "title": "你今年打了多少字？够写一本书吗？",
        "scope": "global",
        "category": "C",
        "status": "ok",
        "kind": "text/message_chars",
        "narrative": narrative,
        "data": {
            "year": int(year),
            "sentChars": int(sent_chars),
            "receivedChars": int(recv_chars),
            "sentBook": sent_book,
            "receivedA4": recv_a4,
            "keyboard": keyboard_stats,
        },
    }
