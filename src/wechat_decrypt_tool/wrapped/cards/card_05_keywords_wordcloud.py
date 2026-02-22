from __future__ import annotations

import hashlib
import logging
import math
import random
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import jieba

from ...chat_helpers import _decode_message_content, _decode_sqlite_text, _iter_message_db_paths, _quote_ident
from ...logging_config import get_logger

logger = get_logger(__name__)
try:
    jieba.setLogLevel(logging.ERROR)
except Exception:
    pass


_MD5_HEX_RE = re.compile(r"(?i)\b[0-9a-f]{32}\b")
_URL_RE = re.compile(r"(?i)\bhttps?://\S+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_SEQ_RE = re.compile(r"[\u4e00-\u9fff]+")
_HAS_ALNUM_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_EN_WORD_RE = re.compile(r"^[A-Za-z]{3,16}$")
_DATEISH_RE = re.compile(
    r"^(?:"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|"
    r"\d{1,2}:\d{2}"
    r"|"
    r"\d{1,2}月\d{1,2}日"
    r")$"
)

# Small but practical stopword list for chat keywords.
_STOPWORDS_ZH = {
    "的",
    "了",
    "是",
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "她们",
    "它们",
    "这",
    "那",
    "这个",
    "那个",
    "这里",
    "那里",
    "这样",
    "那样",
    "就是",
    "也是",
    "还有",
    "因为",
    "所以",
    "但是",
    "如果",
    "然后",
    "已经",
    "可以",
    "还是",
    "可能",
    "不会",
    "没有",
    "不是",
    "一个",
    "一下",
    "一下子",
    "一下下",
    "哈哈",
    "哈哈哈",
    "嘿嘿",
    "呜呜",
    "嗯",
    "哦",
    "啊",
    "呀",
    "啦",
    "嘛",
    "呢",
    "吧",
    "额",
    "诶",
    "哇",
    "唉",
    "好",
    "行",
    "可以",
    "ok",
    "OK",
}

_STOPWORDS_EN = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "at",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "i",
    "me",
    "my",
    "you",
    "your",
    "he",
    "she",
    "it",
    "we",
    "they",
    "them",
    "this",
    "that",
    "these",
    "those",
    "yeah",
    "haha",
    "ok",
    "okay",
    "pls",
    "lol",
}


def _year_range_epoch_seconds(year: int) -> tuple[int, int]:
    start = int(datetime(int(year), 1, 1).timestamp())
    end = int(datetime(int(year) + 1, 1, 1).timestamp())
    return start, end


def _stable_seed(account_name: str, year: int) -> int:
    s = f"{str(account_name or '').strip()}|{int(year)}|wrapped_keywords"
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


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


def _clean_text(text: str) -> str:
    s = str(text or "")
    if not s:
        return ""
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = _CTRL_RE.sub("", s)
    s = _URL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    # XML-like payloads are rarely useful as bubbles/keywords.
    if s.startswith("<") or s.startswith('"<'):
        return ""
    return s


def _is_good_bubble_text(text: str) -> bool:
    s = _clean_text(text)
    if not s:
        return False
    # 仅过滤极短噪声，不对消息长度设置上限。
    if len(s) < 2:
        return False
    if _URL_RE.search(s):
        return False
    if _MD5_HEX_RE.fullmatch(s.replace(" ", "")):
        return False
    # Avoid pure punctuation / emoji / digits.
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", s):
        return False
    if not _HAS_ALNUM_RE.search(s):
        return False
    if re.fullmatch(r"[0-9]+", s):
        return False
    return True


def _is_good_example_text(text: str) -> bool:
    s = _clean_text(text)
    if not s:
        return False
    # 仅过滤极短噪声，不对消息长度设置上限。
    if len(s) < 4:
        return False
    if _URL_RE.search(s):
        return False
    if _MD5_HEX_RE.search(s):
        return False
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", s):
        return False
    return True


def _normalize_token(tok: str) -> str:
    s = str(tok or "").strip()
    if not s:
        return ""
    if len(s) > 32:
        return ""

    # Trim punctuation on both sides.
    s = re.sub(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff]+$", "", s, flags=re.UNICODE).strip()
    if not s:
        return ""

    if _MD5_HEX_RE.fullmatch(s) or _MD5_HEX_RE.search(s):
        return ""
    if _DATEISH_RE.fullmatch(s):
        return ""

    # Discard if contains obvious long ids (alnum with many digits).
    if len(s) >= 18 and re.fullmatch(r"[A-Za-z0-9_-]+", s) and sum(ch.isdigit() for ch in s) >= 6:
        return ""

    # Remove tokens with digits.
    if any(ch.isdigit() for ch in s):
        return ""

    has_cjk = bool(_HAS_CJK_RE.search(s))
    if has_cjk:
        if not (2 <= len(s) <= 8):
            return ""
        if s in _STOPWORDS_ZH:
            return ""
        return s

    if _EN_WORD_RE.fullmatch(s):
        low = s.lower()
        if low in _STOPWORDS_EN:
            return ""
        return low

    return ""


def extract_keywords_jieba(texts: list[str], *, top_n: int = 40) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for raw in texts:
        s = _clean_text(raw)
        if not s:
            continue
        try:
            toks = jieba.lcut(s, cut_all=False)
        except Exception:
            toks = []
        had_token = False
        for tok in toks:
            w = _normalize_token(tok)
            if not w:
                continue
            counter[w] += 1
            had_token = True

        # Fallback for short chat phrases that Jieba often splits into single characters
        # (e.g. "在吗" -> ["在","吗"]) which we intentionally filter out.
        if not had_token and _HAS_CJK_RE.search(s):
            for seg in _CJK_SEQ_RE.findall(s):
                if len(seg) < 2:
                    continue
                for i in range(0, len(seg) - 1):
                    w = _normalize_token(seg[i : i + 2])
                    if not w:
                        continue
                    counter[w] += 1

    if not counter:
        return []

    items = [(w, int(c)) for w, c in counter.items() if int(c) > 1]
    if not items:
        # If everything is singleton, still provide something.
        items = [(w, int(c)) for w, c in counter.items() if int(c) > 0]

    items.sort(key=lambda kv: (-kv[1], kv[0]))
    items = items[: max(0, int(top_n or 0))]
    if not items:
        return []

    vals = [math.sqrt(max(0, c)) for _, c in items]
    minv = min(vals) if vals else 0.0
    maxv = max(vals) if vals else 0.0

    out: list[dict[str, Any]] = []
    for (w, c), v in zip(items, vals):
        if maxv <= minv:
            weight = 1.0
        else:
            weight = 0.2 + 0.8 * ((v - minv) / (maxv - minv))
        out.append({"word": w, "count": int(c), "weight": round(float(weight), 4)})
    return out


def pick_examples(
    keywords: list[dict[str, Any]],
    message_pool: list[str],
    *,
    per_word: int = 3,
) -> list[dict[str, Any]]:
    uniq_msgs = list(dict.fromkeys([_clean_text(x) for x in (message_pool or []) if _clean_text(x)]))
    out: list[dict[str, Any]] = []

    for kw in keywords:
        word = str(kw.get("word") or "").strip()
        if not word:
            continue
        count = int(kw.get("count") or 0)

        hits: list[str] = []
        if _HAS_CJK_RE.search(word):
            for msg in uniq_msgs:
                if len(hits) >= int(per_word):
                    break
                if not _is_good_example_text(msg):
                    continue
                if word in msg:
                    hits.append(msg)
        else:
            wlow = word.lower()
            for msg in uniq_msgs:
                if len(hits) >= int(per_word):
                    break
                if not _is_good_example_text(msg):
                    continue
                if wlow in msg.lower():
                    hits.append(msg)

        out.append({"word": word, "count": int(count), "messages": hits})

    return out


def build_keywords_payload(
    *,
    texts: list[str],
    seed: int,
    top_n: int = 40,
    bubble_limit: int = 180,
    examples_per_word: int = 3,
) -> dict[str, Any]:
    _ = seed  # 保留参数以兼容现有调用/测试；随机采样不再使用固定 seed。
    keywords = extract_keywords_jieba(list(texts or []), top_n=top_n)

    bubble_candidates = [_clean_text(x) for x in (texts or [])]
    bubble_candidates = [x for x in bubble_candidates if _is_good_bubble_text(x)]
    bubble_candidates = list(dict.fromkeys(bubble_candidates))

    rnd = random.SystemRandom()
    rnd.shuffle(bubble_candidates)
    bubble_messages = bubble_candidates[: max(0, int(bubble_limit or 0))]

    examples = pick_examples(keywords, texts, per_word=examples_per_word)

    top_kw = None
    if keywords:
        top_kw = {"word": str(keywords[0]["word"]), "count": int(keywords[0]["count"])}

    return {
        "topKeyword": top_kw,
        "keywords": keywords,
        "bubbleMessages": bubble_messages,
        "examples": examples,
    }


def _scan_message_pool(
    *,
    account_dir: Path,
    year: int,
    outgoing_only: bool,
    seed: int,
    max_pool: int = 3000,
    max_seen: int = 120_000,
) -> tuple[list[str], dict[str, Any]]:
    start_ts, end_ts = _year_range_epoch_seconds(int(year))
    _ = seed  # 保留参数以兼容现有调用；抽样本身使用非确定性随机。
    rnd = random.SystemRandom()

    db_paths = _iter_message_db_paths(account_dir)
    # Prefer chat shards; biz_message often contains service/ads content.
    db_paths = [p for p in db_paths if not p.name.lower().startswith("biz_message")]
    rnd.shuffle(db_paths)

    pool: list[str] = []
    seen = 0

    t0 = time.time()
    for db_path in db_paths:
        if not db_path.exists():
            continue

        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            conn.text_factory = bytes

            my_rowid: int | None = None
            if outgoing_only:
                try:
                    r = conn.execute(
                        "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                        (str(account_dir.name),),
                    ).fetchone()
                    if r is not None and r[0] is not None:
                        my_rowid = int(r[0])
                except Exception:
                    my_rowid = None
                if my_rowid is None:
                    continue

            tables = _list_message_tables(conn)
            if not tables:
                continue
            rnd.shuffle(tables)

            ts_expr = (
                "CASE "
                "WHEN CAST(create_time AS INTEGER) > 1000000000000 "
                "THEN CAST(CAST(create_time AS INTEGER)/1000 AS INTEGER) "
                "ELSE CAST(create_time AS INTEGER) "
                "END"
            )

            for table in tables:
                if seen >= int(max_seen):
                    break
                qt = _quote_ident(table)
                where_sender = ""
                params: tuple[Any, ...]
                if outgoing_only and my_rowid is not None:
                    where_sender = " AND CAST(real_sender_id AS INTEGER) = ?"
                    params = (start_ts, end_ts, int(my_rowid))
                else:
                    params = (start_ts, end_ts)
                sql = (
                    "SELECT message_content, compress_content "
                    f"FROM {qt} "
                    "WHERE CAST(local_type AS INTEGER) = 1 "
                    f"  AND {ts_expr} >= ? AND {ts_expr} < ?"
                    f"{where_sender}"
                )

                try:
                    cur = conn.execute(sql, params)
                except Exception:
                    continue

                for r in cur:
                    if seen >= int(max_seen):
                        break
                    raw_txt = ""
                    try:
                        raw_txt = _decode_message_content(r["compress_content"], r["message_content"]).strip()
                    except Exception:
                        raw_txt = ""
                    cleaned = _clean_text(raw_txt)
                    if not cleaned:
                        continue
                    seen += 1

                    if len(pool) < int(max_pool):
                        pool.append(cleaned)
                        continue

                    # Reservoir sampling over the accepted stream.
                    j = rnd.randrange(seen)
                    if j < int(max_pool):
                        pool[j] = cleaned
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        if seen >= int(max_seen):
            break

    elapsed = time.time() - t0
    meta = {
        "scannedMessages": int(seen),
        "sampledMessages": int(len(pool)),
        "sampleRate": round(float(len(pool)) / float(seen), 6) if seen > 0 else 0.0,
        "elapsedSec": round(float(elapsed), 3),
    }
    return pool, meta


def build_card_05_keywords_wordcloud(*, account_dir: Path, year: int) -> dict[str, Any]:
    title = "这一年，你把哪些词说了一遍又一遍？"
    seed = _stable_seed(str(account_dir.name or ""), int(year))

    pool, meta = _scan_message_pool(account_dir=account_dir, year=year, outgoing_only=True, seed=seed)
    if len(pool) < 80:
        pool, meta = _scan_message_pool(account_dir=account_dir, year=year, outgoing_only=False, seed=seed ^ 0x1234)

    payload = build_keywords_payload(texts=pool, seed=seed)

    logger.info(
        "Wrapped card#6 keywords computed: account=%s year=%s keywords=%s bubble=%s scanned=%s sampled=%s elapsed=%.2fs",
        str(account_dir.name or "").strip(),
        int(year),
        len(payload.get("keywords") or []),
        len(payload.get("bubbleMessages") or []),
        int(meta.get("scannedMessages") or 0),
        int(meta.get("sampledMessages") or 0),
        float(meta.get("elapsedSec") or 0.0),
    )

    return {
        "id": 6,
        "title": title,
        "scope": "global",
        "category": "C",
        "status": "ok",
        "kind": "text/keywords_wordcloud",
        "narrative": "你的年度关键词词云",
        "data": {
            "year": int(year),
            **payload,
            "meta": {
                "scannedMessages": int(meta.get("scannedMessages") or 0),
                "sampledMessages": int(meta.get("sampledMessages") or 0),
                "sampleRate": float(meta.get("sampleRate") or 0.0),
            },
        },
    }
