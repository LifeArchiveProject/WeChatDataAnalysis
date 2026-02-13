from bisect import bisect_left, bisect_right
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import re
import httpx
import html # 修复&amp;转义的问题！！！
import sqlite3
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..chat_helpers import _load_contact_rows, _pick_display_name, _resolve_account_dir
from ..logging_config import get_logger
from ..media_helpers import _read_and_maybe_decrypt_media, _resolve_account_wxid_dir
from ..path_fix import PathFixRoute
from ..wcdb_realtime import (
    WCDBRealtimeError,
    WCDB_REALTIME,
    exec_query as _wcdb_exec_query,
    get_sns_timeline as _wcdb_get_sns_timeline,
)

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)

SNS_MEDIA_PICKS_FILE = "_sns_media_picks.json"


def _parse_csv_list(raw: Optional[str]) -> list[str]:
    if raw is None:
        return []
    s = str(raw or "").strip()
    if not s:
        return []
    # Best-effort: allow comma-separated list in one query param.
    return [p.strip() for p in s.split(",") if p.strip()]


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _build_location_text(node: Optional[ET.Element]) -> str:
    if node is None:
        return ""

    def _get(key: str) -> str:
        return str(node.get(key) or node.findtext(key) or "").strip()

    def _clean(v: str) -> str:
        # Some WeChat XML uses special whitespace (NBSP / thin spaces) inside the location string.
        return (
            str(v or "")
            .replace("\u00a0", " ")
            .replace("\u2006", " ")
            .strip()
        )

    city = _clean(_get("city"))
    poi = _clean(_get("poiName") or _get("poi") or _get("label"))
    address = _clean(_get("address") or _get("poiAddress"))

    # Avoid duplicated city prefix like: "广安市·广安市·xxx".
    if city and poi and poi.startswith(city):
        rest = poi[len(city):].lstrip(" ·")
        if rest:
            poi = rest

    # WeChat UI typically renders `city·poi/address`.
    if city and (poi or address):
        return f"{city}·{poi or address}".strip()

    for cand in (poi, address, city):
        if cand:
            return cand
    return ""


def _parse_timeline_xml(xml_text: str, fallback_username: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "username": fallback_username,
        "createTime": 0,
        "contentDesc": "",
        "location": "",
        "media": [],
        "likes": [],
        "comments": [],
        "type": 1,  # 默认类型
        "title": "",
        "contentUrl": "",
        "finderFeed": {}
    }

    xml_str = str(xml_text or "").strip()
    if not xml_str:
        return out

    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return out

    def _find_text(*paths: str) -> str:
        for p in paths:
            try:
                v = root.findtext(p)
            except Exception:
                v = None
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    # &amp转义！！
    def _clean_url(u: str) -> str:
        if not u:
            return ""

        cleaned = html.unescape(u)
        cleaned = cleaned.replace("&amp;", "&")
        return cleaned.strip()

    out["username"] = _find_text(".//TimelineObject/username", ".//TimelineObject/user_name",
                                 ".//username") or fallback_username
    out["createTime"] = _safe_int(_find_text(".//TimelineObject/createTime", ".//createTime"))
    out["contentDesc"] = _find_text(".//TimelineObject/contentDesc", ".//contentDesc")
    out["location"] = _build_location_text(root.find(".//location"))

    # --- 提取内容类型 ---
    post_type = _safe_int(_find_text(".//ContentObject/type", ".//type"))
    out["type"] = post_type

    # --- 如果是公众号文章 (Type 3) ---
    if post_type == 3:
        out["title"] = _find_text(".//ContentObject/title")
        out["contentUrl"] = _clean_url(_find_text(".//ContentObject/contentUrl"))

    # --- 如果是视频号 (Type 28) ---
    if post_type == 28:
        out["title"] = _find_text(".//ContentObject/title")
        out["contentUrl"] = _clean_url(_find_text(".//ContentObject/contentUrl"))
        out["finderFeed"] = {
            "nickname": _find_text(".//finderFeed/nickname"),
            "desc": _find_text(".//finderFeed/desc"),
            "thumbUrl": _clean_url(
                _find_text(".//finderFeed/mediaList/media/thumbUrl", ".//finderFeed/mediaList/media/coverUrl")),
            "url": _clean_url(_find_text(".//finderFeed/mediaList/media/url"))
        }

    media: list[dict[str, Any]] = []
    try:
        for m in root.findall(".//mediaList//media"):
            mt = _safe_int(m.findtext("type"))
            url_el = m.find("url") if m.find("url") is not None else m.find("urlV")
            thumb_el = m.find("thumb") if m.find("thumb") is not None else m.find("thumbV")

            url = _clean_url(url_el.text if url_el is not None else "")
            thumb = _clean_url(thumb_el.text if thumb_el is not None else "")

            url_attrs = dict(url_el.attrib) if url_el is not None and url_el.attrib else {}
            thumb_attrs = dict(thumb_el.attrib) if thumb_el is not None and thumb_el.attrib else {}
            media_id = str(m.findtext("id") or "").strip()
            size_el = m.find("size")
            size = dict(size_el.attrib) if size_el is not None and size_el.attrib else {}

            if not url and not thumb:
                continue

            media.append({
                "type": mt,
                "id": media_id,
                "url": url,
                "thumb": thumb,
                "urlAttrs": url_attrs,
                "thumbAttrs": thumb_attrs,
                "size": size,
            })
    except Exception:
        pass
    out["media"] = media

    likes: list[str] = []
    try:
        for u in root.findall(".//likeList//like//username"):
            if u is None or not u.text:
                continue
            v = str(u.text).strip()
            if v:
                likes.append(v)
    except Exception:
        likes = []
    out["likes"] = likes

    comments: list[dict[str, Any]] = []
    try:
        for c in root.findall(".//commentList//comment"):
            content = str(c.findtext("content") or "").strip()
            if not content:
                continue
            comments.append(
                {
                    "username": str(c.findtext("username") or "").strip(),
                    "nickname": str(c.findtext("nickName") or "").strip(),
                    "content": content,
                    "refUsername": str(c.findtext("refUserName") or "").strip(),
                    "refNickname": str(c.findtext("refNickName") or "").strip(),
                }
            )
    except Exception:
        comments = []
    out["comments"] = comments

    return out


def _image_size_from_bytes(data: bytes, media_type: str) -> tuple[int, int]:
    mt = str(media_type or "").lower()
    if mt == "image/png":
        # PNG IHDR width/height are stored at byte offsets 16..24
        if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
            try:
                w = int.from_bytes(data[16:20], "big")
                h = int.from_bytes(data[20:24], "big")
                return w, h
            except Exception:
                return 0, 0
        return 0, 0
    if mt in {"image/jpeg", "image/jpg"}:
        # Minimal JPEG SOF parser.
        if len(data) < 4 or (not data.startswith(b"\xFF\xD8")):
            return 0, 0
        i = 2
        while i + 3 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            # Skip padding 0xFF bytes.
            while i < len(data) and data[i] == 0xFF:
                i += 1
            if i >= len(data):
                break
            marker = data[i]
            i += 1
            # Markers without a segment length.
            if marker in (0xD8, 0xD9):
                continue
            if marker == 0xDA:  # Start of scan.
                break
            if i + 1 >= len(data):
                break
            seg_len = (data[i] << 8) + data[i + 1]
            i += 2
            if seg_len < 2:
                break
            # SOF markers which contain width/height.
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                # segment: [precision(1), height(2), width(2), ...]
                if i + 4 < len(data):
                    try:
                        h = (data[i + 1] << 8) + data[i + 2]
                        w = (data[i + 3] << 8) + data[i + 4]
                        return w, h
                    except Exception:
                        return 0, 0
            i += seg_len - 2
        return 0, 0
    return 0, 0


@lru_cache(maxsize=16)
def _sns_img_time_index(wxid_dir_str: str) -> tuple[list[float], list[str]]:
    """Build a (mtime_sorted, path_sorted) index for local Moments cache images.

    WeChat stores encrypted SNS cache images under:
      `{wxid_dir}/cache/YYYY-MM/Sns/Img/<2hex>/<30hex>`
    """
    wxid_dir = Path(str(wxid_dir_str or "").strip())
    out: list[tuple[float, str]] = []

    cache_root = wxid_dir / "cache"
    try:
        month_dirs = [p for p in cache_root.iterdir() if p.is_dir()]
    except Exception:
        month_dirs = []

    for mdir in month_dirs:
        img_root = mdir / "Sns" / "Img"
        try:
            if not (img_root.exists() and img_root.is_dir()):
                continue
        except Exception:
            continue
        # The Img dir uses a 2-level layout; keep this tight (no global rglob).
        try:
            for sub in img_root.iterdir():
                if not sub.is_dir():
                    continue
                for f in sub.iterdir():
                    try:
                        if not f.is_file():
                            continue
                        st = f.stat()
                        out.append((float(st.st_mtime), str(f)))
                    except Exception:
                        continue
        except Exception:
            continue

    out.sort(key=lambda x: x[0])
    mtimes = [m for m, _p in out]
    paths = [_p for _m, _p in out]
    return mtimes, paths


def _normalize_hex32(value: Optional[str]) -> str:
    """Return the first 32 hex chars from value, or '' if not present."""
    s = str(value or "").strip().lower()
    if not s:
        return ""
    # Keep only hex chars. Some attrs may contain separators or be wrapped.
    s = re.sub(r"[^0-9a-f]", "", s)
    if len(s) < 32:
        return ""
    return s[:32]


def _sns_media_picks_path(account_dir: Path) -> Path:
    return account_dir / SNS_MEDIA_PICKS_FILE


def _sns_post_id_from_media_key(media_key: str) -> str:
    # Frontend stores picks under `${postId}:${idx}`.
    s = str(media_key or "").strip()
    if not s:
        return ""
    return s.split(":", 1)[0].strip()


@lru_cache(maxsize=32)
def _load_sns_media_picks_cached(path_str: str, mtime: float) -> dict[str, str]:
    p = Path(str(path_str or "").strip())
    try:
        raw = p.read_text(encoding="utf-8")
    except Exception:
        return {}

    try:
        obj = json.loads(raw)
    except Exception:
        return {}

    picks_obj = obj.get("picks") if isinstance(obj, dict) else None
    if not isinstance(picks_obj, dict):
        return {}

    out: dict[str, str] = {}
    for k, v in picks_obj.items():
        mk = str(k or "").strip()
        if not mk:
            continue
        ck = _normalize_hex32(str(v or ""))
        if not ck:
            continue
        out[mk] = ck
    return out


def _load_sns_media_picks(account_dir: Path) -> dict[str, str]:
    p = _sns_media_picks_path(account_dir)
    try:
        st = p.stat()
        mtime = float(st.st_mtime)
    except Exception:
        mtime = 0.0
    return _load_sns_media_picks_cached(str(p), mtime)


def _save_sns_media_picks(account_dir: Path, picks: dict[str, str]) -> int:
    # Normalize + keep it stable for easier diff/debugging.
    out: dict[str, str] = {}
    for k, v in (picks or {}).items():
        mk = str(k or "").strip()
        if not mk:
            continue
        ck = _normalize_hex32(str(v or ""))
        if not ck:
            continue
        out[mk] = ck

    try:
        payload = {"updated_at": int(time.time()), "picks": dict(sorted(out.items(), key=lambda x: x[0]))}
        _sns_media_picks_path(account_dir).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        _load_sns_media_picks_cached.cache_clear()
    except Exception:
        pass

    return len(out)


@lru_cache(maxsize=16)
def _sns_img_roots(wxid_dir_str: str) -> tuple[str, ...]:
    """List all month cache roots that contain `Sns/Img`."""
    wxid_dir = Path(str(wxid_dir_str or "").strip())
    cache_root = wxid_dir / "cache"
    try:
        month_dirs = [p for p in cache_root.iterdir() if p.is_dir()]
    except Exception:
        month_dirs = []

    roots: list[str] = []
    for mdir in month_dirs:
        img_root = mdir / "Sns" / "Img"
        try:
            if img_root.exists() and img_root.is_dir():
                roots.append(str(img_root))
        except Exception:
            continue
    # Keep it stable (helps debugging and caching predictability).
    roots.sort()
    return tuple(roots)


def _resolve_sns_cached_image_path_by_md5(
    *,
    wxid_dir: Path,
    md5: str,
    create_time: int,
) -> Optional[str]:
    """Try to resolve SNS cache image by md5-based cache path layout."""
    md5_32 = _normalize_hex32(md5)
    if not md5_32:
        return None

    sub = md5_32[:2]
    rest = md5_32[2:]
    roots = _sns_img_roots(str(wxid_dir))
    if not roots:
        return None

    best: tuple[float, str] | None = None
    for root_str in roots:
        try:
            p = Path(root_str) / sub / rest
            if not (p.exists() and p.is_file()):
                continue
            # Prefer the cache file closest to the post create_time (if provided),
            # otherwise pick the newest one.
            st = p.stat()
            if create_time > 0:
                score = abs(float(st.st_mtime) - float(create_time))
            else:
                score = -float(st.st_mtime)
            if best is None or score < best[0]:
                best = (score, str(p))
        except Exception:
            continue
    return best[1] if best else None


def _sns_cache_key_from_path(p: Path) -> str:
    """Return the 32-hex cache key for a SNS cache file path, or ''."""
    try:
        # cache/.../Sns/Img/<2hex>/<30hex>
        key = f"{p.parent.name}{p.name}"
    except Exception:
        return ""
    return _normalize_hex32(key)


def _generate_sns_cache_key(tid: str, media_id: str, media_type: int = 2) -> str:
    """
    公式: md5(tid_mediaId_type)
    Example: 14852422213384352392_14852422213963625090_2 -> 6d479249ca5a090fab5c42c79bc56b89
    """
    if not tid or not media_id:
        return ""

    raw_key = f"{tid}_{media_id}_{media_type}"

    try:
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()
    except Exception:
        return ""

def _resolve_sns_cached_image_path_by_cache_key(
    *,
    wxid_dir: Path,
    cache_key: str,
    create_time: int,
) -> Optional[str]:
    """Resolve SNS cache image by `<2hex>/<30hex>` cache key."""
    key32 = _normalize_hex32(cache_key)
    if not key32:
        return None

    sub = key32[:2]
    rest = key32[2:]
    roots = _sns_img_roots(str(wxid_dir))
    if not roots:
        return None

    best: tuple[float, str] | None = None
    for root_str in roots:
        try:
            p = Path(root_str) / sub / rest
            if not (p.exists() and p.is_file()):
                continue
            st = p.stat()
            if create_time > 0:
                score = abs(float(st.st_mtime) - float(create_time))
            else:
                score = -float(st.st_mtime)
            if best is None or score < best[0]:
                best = (score, str(p))
        except Exception:
            continue
    return best[1] if best else None


@lru_cache(maxsize=4096)
def _resolve_sns_cached_image_path(
    *,
    account_dir_str: str,
    create_time: int,
    width: int,
    height: int,
    idx: int,
    total_size: int = 0,
) -> Optional[str]:
    """Best-effort resolve a local cached SNS image for a post+media meta."""
    total_size_i = int(total_size or 0)
    must_match_size = width > 0 and height > 0
    # Without size/total_size, time-only matching is too error-prone and can easily mix images.
    if (not must_match_size) and total_size_i <= 0:
        return None

    account_dir = Path(str(account_dir_str or "").strip())
    if not account_dir.exists():
        return None

    wxid_dir = _resolve_account_wxid_dir(account_dir)
    if not wxid_dir:
        return None

    mtimes, paths = _sns_img_time_index(str(wxid_dir))
    if not mtimes:
        return None

    create_time_i = int(create_time or 0)
    if create_time_i > 0:
        # We don't know when the image was cached (could be close to create_time, could be hours later).
        # Use a generous window but keep it bounded for performance.
        window = 72 * 3600  # 72h
        lo = create_time_i - window
        hi = create_time_i + window

        l = bisect_left(mtimes, lo)
        r = bisect_right(mtimes, hi)
        if l >= r:
            # Fallback: search the newest N files if time window has no hits.
            l = max(0, len(mtimes) - 800)
            r = len(mtimes)
    else:
        # Missing createTime: only probe the newest cache entries.
        l = max(0, len(mtimes) - 800)
        r = len(mtimes)

    # Rank by time proximity to create_time (or by recency when createTime is missing).
    candidates: list[tuple[float, str]] = []
    for j in range(l, r):
        try:
            if create_time_i > 0:
                candidates.append((abs(mtimes[j] - float(create_time_i)), paths[j]))
            else:
                candidates.append((-mtimes[j], paths[j]))
        except Exception:
            continue
    candidates.sort(key=lambda x: x[0])

    matched: list[tuple[int, float, str]] = []
    # Limit the work per request.
    max_probe = 2000 if (r - l) <= 2000 else 2000
    for _diff, pstr in candidates[:max_probe]:
        try:
            p = Path(pstr)
            payload, media_type = _read_and_maybe_decrypt_media(p, account_dir)
            if not payload or not str(media_type or "").startswith("image/"):
                continue
            if must_match_size:
                w0, h0 = _image_size_from_bytes(payload, str(media_type or ""))
                if (w0, h0) != (width, height):
                    continue

            size_diff = abs(len(payload) - total_size_i) if total_size_i > 0 else 0
            # When totalSize is available, it tends to be a stronger discriminator than mtime.
            matched.append((int(size_diff), float(_diff), pstr))
        except Exception:
            continue

    if not matched:
        return None
    if must_match_size:
        matched.sort(key=lambda x: (x[0], x[1], x[2]))
        # If we have totalSize, treat it as a strong discriminator and always take the best match.
        if total_size_i > 0:
            return matched[0][2]
        idx0 = max(0, int(idx or 0))
        return matched[idx0][2] if idx0 < len(matched) else None
    # No size: only return a best-effort match when totalSize is available.
    if total_size_i > 0:
        matched.sort(key=lambda x: (x[0], x[1], x[2]))
        return matched[0][2]
    return None


@lru_cache(maxsize=2048)
def _list_sns_cached_image_candidate_keys(
    *,
    account_dir_str: str,
    create_time: int,
    width: int,
    height: int,
) -> tuple[str, ...]:
    """List local SNS cache candidates (as 32-hex cache keys) for a media item.

    The ordering matches `_resolve_sns_cached_image_path()`'s scan order, so `idx`
    is stable within the same (account, create_time, width, height) input.
    """
    if create_time <= 0 or width <= 0 or height <= 0:
        return tuple()

    account_dir = Path(str(account_dir_str or "").strip())
    if not account_dir.exists():
        return tuple()

    wxid_dir = _resolve_account_wxid_dir(account_dir)
    if not wxid_dir:
        return tuple()

    mtimes, paths = _sns_img_time_index(str(wxid_dir))
    if not mtimes:
        return tuple()

    window = 72 * 3600  # 72h
    lo = create_time - window
    hi = create_time + window

    l = bisect_left(mtimes, lo)
    r = bisect_right(mtimes, hi)
    if l >= r:
        l = max(0, len(mtimes) - 800)
        r = len(mtimes)

    candidates: list[tuple[float, str]] = []
    for j in range(l, r):
        try:
            candidates.append((abs(mtimes[j] - float(create_time)), paths[j]))
        except Exception:
            continue
    candidates.sort(key=lambda x: x[0])

    max_probe = 2000 if (r - l) <= 2000 else 2000
    out: list[str] = []
    seen: set[str] = set()
    for _diff, pstr in candidates[:max_probe]:
        try:
            p = Path(pstr)
            payload, media_type = _read_and_maybe_decrypt_media(p, account_dir)
            if not payload or not str(media_type or "").startswith("image/"):
                continue
            w0, h0 = _image_size_from_bytes(payload, str(media_type or ""))
            if (w0, h0) != (width, height):
                continue
            key = _sns_cache_key_from_path(p)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
        except Exception:
            continue

    return tuple(out)


@router.get("/api/sns/timeline", summary="获取朋友圈时间线")
def list_sns_timeline(
    account: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    usernames: Optional[str] = None,
    keyword: Optional[str] = None,
):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    account_dir = _resolve_account_dir(account)
    contact_db_path = account_dir / "contact.db"

    users = _parse_csv_list(usernames)
    kw = str(keyword or "").strip()

    # Prefer real-time WCDB access (reads the latest encrypted db_storage/sns/sns.db).
    # Fallback to the decrypted sqlite copy in output/{account}/sns.db.
    try:
        conn = WCDB_REALTIME.ensure_connected(account_dir)

        def _clean_name(v: Any) -> str:
            return str(v or "").replace("\xa0", " ").strip()

        # Base timeline (includes likes/comments) from WCDB API.
        with conn.lock:
            rows = _wcdb_get_sns_timeline(
                conn.handle,
                limit=limit + 1,
                offset=offset,
                usernames=users,
                keyword=kw,
            )

            # Best-effort: enrich posts with XML-only fields (location + media attrs/size)
            # by querying SnsTimeLine.content from the encrypted sns.db.
            content_by_tid: dict[int, str] = {}
            try:
                sns_db_path = conn.db_storage_dir / "sns" / "sns.db"
                if not sns_db_path.exists():
                    sns_db_path = conn.db_storage_dir / "sns.db"

                def _to_signed_i64(v: int) -> int:
                    x = int(v) & 0xFFFFFFFFFFFFFFFF
                    if x >= 0x8000000000000000:
                        x -= 0x10000000000000000
                    return int(x)

                tids: list[int] = []
                for r in (rows or [])[: int(limit)]:
                    if not isinstance(r, dict):
                        continue
                    try:
                        tid_u = int(r.get("id") or 0)
                    except Exception:
                        continue
                    tids.append(_to_signed_i64(tid_u))

                tids = list(dict.fromkeys(tids))
                if tids and sns_db_path.exists():
                    in_sql = ",".join([str(x) for x in tids])
                    sql = f"SELECT tid, content FROM SnsTimeLine WHERE tid IN ({in_sql})"
                    sql_rows = _wcdb_exec_query(conn.handle, kind="media", path=str(sns_db_path), sql=sql)
                    for rr in sql_rows:
                        try:
                            tid_val = int(rr.get("tid"))
                        except Exception:
                            continue
                        content_by_tid[tid_val] = str(rr.get("content") or "")
            except Exception:
                content_by_tid = {}

        has_more = len(rows) > limit
        rows = rows[:limit]

        post_usernames = [str((r or {}).get("username") or "").strip() for r in rows if isinstance(r, dict)]
        post_usernames = [u for u in post_usernames if u]
        contact_rows = _load_contact_rows(contact_db_path, post_usernames) if contact_db_path.exists() else {}

        timeline: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue

            uname = str(r.get("username") or "").strip()
            nickname = _clean_name(r.get("nickname"))
            display = nickname or (_pick_display_name(contact_rows.get(uname), uname) if uname else uname)

            create_time = _safe_int(r.get("createTime"))
            content_desc = str(r.get("contentDesc") or "")
            media = r.get("media") if isinstance(r.get("media"), list) else []
            likes = r.get("likes") if isinstance(r.get("likes"), list) else []
            likes = [_clean_name(x) for x in likes if _clean_name(x)]
            comments = r.get("comments") if isinstance(r.get("comments"), list) else []

            # Enrich with parsed XML when available.
            location = str(r.get("location") or "")

            post_type = 1
            title = ""
            content_url = ""
            finder_feed = {}
            try:
                tid_u = int(r.get("id") or 0)
                tid_s = (tid_u & 0xFFFFFFFFFFFFFFFF)
                if tid_s >= 0x8000000000000000:
                    tid_s -= 0x10000000000000000
                xml = content_by_tid.get(int(tid_s))
                if xml:
                    parsed = _parse_timeline_xml(xml, uname)
                    if parsed.get("location"):
                        location = str(parsed.get("location") or "")

                    post_type = parsed.get("type", 1)
                    title = parsed.get("title", "")
                    content_url = parsed.get("contentUrl", "")
                    finder_feed = parsed.get("finderFeed", {})

                    pmedia = parsed.get("media") or []
                    if isinstance(pmedia, list) and isinstance(media, list) and pmedia:
                        # Merge by index (best-effort).
                        merged: list[dict[str, Any]] = []
                        for i, m0 in enumerate(media):
                            mp = pmedia[i] if i < len(pmedia) else None
                            if not isinstance(mp, dict):
                                merged.append(m0 if isinstance(m0, dict) else {})
                                continue
                            mm = dict(mp)
                            if isinstance(m0, dict):
                                for k in ("url", "thumb"):
                                    v = m0.get(k)
                                    if v:
                                        mm[k] = v
                                for k, v in m0.items():
                                    if k not in mm:
                                        mm[k] = v
                            merged.append(mm)
                        media = merged
            except Exception:
                pass

            pid = str(r.get("id") or "") or str(create_time or "") or uname
            timeline.append(
                {
                    "id": pid,
                    "tid": r.get("id"),
                    "username": uname,
                    "displayName": _clean_name(display) or uname,
                    "createTime": create_time,
                    "contentDesc": content_desc,
                    "location": str(location or ""),
                    "media": media,
                    "likes": likes,
                    "comments": comments,
                    "type": post_type,
                    "title": title,
                    "contentUrl": content_url,
                    "finderFeed": finder_feed,
                }
            )

        return {"timeline": timeline, "hasMore": has_more, "limit": limit, "offset": offset, "source": "wcdb"}
    except WCDBRealtimeError as e:
        logger.info("[sns] wcdb realtime unavailable: %s", e)
    except Exception as e:
        logger.warning("[sns] wcdb realtime failed: %s", e)

    # Legacy path: query the decrypted sns.db under output/databases/{account}.
    sns_db_path = account_dir / "sns.db"
    if not sns_db_path.exists():
        raise HTTPException(status_code=404, detail="sns.db not found for this account.")

    filters: list[str] = []
    params: list[Any] = []

    if users:
        placeholders = ",".join(["?"] * len(users))
        filters.append(f"user_name IN ({placeholders})")
        params.extend(users)

    if kw:
        filters.append("content LIKE ?")
        params.append(f"%{kw}%")

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    sql = f"""
        SELECT tid, user_name, content
        FROM SnsTimeLine
        {where_sql}
        ORDER BY tid DESC
        LIMIT ? OFFSET ?
    """
    # Fetch 1 extra row to determine hasMore.
    params_with_page = params + [limit + 1, offset]

    conn = sqlite3.connect(str(sns_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params_with_page).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("[sns] query failed: %s", e)
        raise HTTPException(status_code=500, detail=f"sns.db query failed: {e}")
    finally:
        conn.close()

    has_more = len(rows) > limit
    rows = rows[:limit]

    post_usernames = [str(r["user_name"] or "").strip() for r in rows if str(r["user_name"] or "").strip()]
    contact_rows = _load_contact_rows(contact_db_path, post_usernames) if contact_db_path.exists() else {}

    timeline: list[dict[str, Any]] = []
    for r in rows:
        try:
            tid = r["tid"]
        except Exception:
            tid = None
        uname = str(r["user_name"] or "").strip()
        parsed = _parse_timeline_xml(str(r["content"] or ""), uname)
        display = _pick_display_name(contact_rows.get(uname), uname) if uname else uname

        timeline.append(
            {
                "id": str(tid if tid is not None else parsed.get("createTime") or "") or uname,
                "tid": tid,
                "username": uname or parsed.get("username") or "",
                "displayName": display,
                "createTime": int(parsed.get("createTime") or 0),
                "contentDesc": str(parsed.get("contentDesc") or ""),
                "location": str(parsed.get("location") or ""),
                "media": parsed.get("media") or [],
                "likes": parsed.get("likes") or [],
                "comments": parsed.get("comments") or [],
                "type": parsed.get("type", 1),
                "title": parsed.get("title", ""),
                "contentUrl": parsed.get("contentUrl", ""),
                "finderFeed": parsed.get("finderFeed", {}),
            }
        )

    return {"timeline": timeline, "hasMore": has_more, "limit": limit, "offset": offset}


class SnsMediaPicksSaveRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    picks: dict[str, str] = Field(default_factory=dict, description="手动匹配表：`${postId}:${idx}` -> 32hex cacheKey")


@router.post("/api/sns/media_picks", summary="保存朋友圈图片手动匹配结果（本机）")
async def save_sns_media_picks(request: SnsMediaPicksSaveRequest):
    account_dir = _resolve_account_dir(request.account)
    count = _save_sns_media_picks(account_dir, request.picks or {})
    return {"status": "success", "count": int(count)}


@router.get("/api/sns/media_candidates", summary="获取朋友圈图片本地缓存候选")
def list_sns_media_candidates(
    account: Optional[str] = None,
    create_time: int = 0,
    width: int = 0,
    height: int = 0,
    limit: int = 24,
    offset: int = 0,
):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    account_dir = _resolve_account_dir(account)
    keys = _list_sns_cached_image_candidate_keys(
        account_dir_str=str(account_dir),
        create_time=int(create_time or 0),
        width=int(width or 0),
        height=int(height or 0),
    )
    total = len(keys)
    end = min(total, offset + limit)
    items = [{"idx": i, "key": keys[i]} for i in range(offset, end)]
    return {"count": total, "items": items, "hasMore": end < total, "limit": limit, "offset": offset}


@router.get("/api/sns/media", summary="获取朋友圈图片（本地缓存优先）")
async def get_sns_media(
        account: Optional[str] = None,
        create_time: int = 0,
        width: int = 0,
        height: int = 0,
        total_size: int = 0,
        idx: int = 0,
        avoid_picked: int = 0,
        post_id: Optional[str] = None,
        media_id: Optional[str] = None,
        media_type: int = 2,
        pick: Optional[str] = None,
        md5: Optional[str] = None,
        url: Optional[str] = None,
):
    account_dir = _resolve_account_dir(account)
    wxid_dir = _resolve_account_wxid_dir(account_dir)

    if wxid_dir and post_id and media_id:
        deterministic_key = _generate_sns_cache_key(post_id, media_id, media_type)

        exact_match_path = _resolve_sns_cached_image_path_by_cache_key(
            wxid_dir=wxid_dir,
            cache_key=deterministic_key,
            create_time=0
        )

        if exact_match_path:
            print(f"=====exact_match_path======={exact_match_path}=============")
            try:
                payload, mtype = _read_and_maybe_decrypt_media(Path(exact_match_path), account_dir)
                if payload and str(mtype or "").startswith("image/"):
                    resp = Response(content=payload, media_type=str(mtype or "image/jpeg"))
                    resp.headers["Cache-Control"] = "public, max-age=31536000"  # 确定性缓存可以设置很久
                    resp.headers["X-SNS-Source"] = "deterministic-hash"
                    return resp
            except Exception:
                pass

        print("no exact match path")

    # 0) User-picked cache key override (stable across candidate ordering).
    pick_key = _normalize_hex32(pick)
    if pick_key:
        wxid_dir = _resolve_account_wxid_dir(account_dir)
        if wxid_dir:
            local = _resolve_sns_cached_image_path_by_cache_key(
                wxid_dir=wxid_dir,
                cache_key=pick_key,
                create_time=int(create_time or 0),
            )
            if local:
                try:
                    payload, media_type = _read_and_maybe_decrypt_media(Path(local), account_dir)
                    if payload and str(media_type or "").startswith("image/"):
                        resp = Response(content=payload, media_type=str(media_type or "image/jpeg"))
                        resp.headers["Cache-Control"] = "public, max-age=86400"
                        return resp
                except Exception:
                    pass

    # Optional: avoid using a cache image that was manually pinned to another post.
    # Only applies when frontend enables this setting and the current media has no explicit `pick`.
    try:
        avoid_flag = bool(int(avoid_picked or 0))
    except Exception:
        avoid_flag = False
    cur_post_id = str(post_id or "").strip()
    reserved_other: set[str] = set()
    if avoid_flag and (not pick_key) and cur_post_id:
        picks_map = _load_sns_media_picks(account_dir)
        for mk, ck in (picks_map or {}).items():
            pid = _sns_post_id_from_media_key(mk)
            if not pid or pid == cur_post_id:
                continue
            if ck:
                reserved_other.add(str(ck))

    # 1) Try local decrypted cache first (works for old posts where CDN URLs return placeholders).
    local = _resolve_sns_cached_image_path(
        account_dir_str=str(account_dir),
        create_time=int(create_time or 0),
        width=int(width or 0),
        height=int(height or 0),
        idx=max(0, int(idx or 0)),
        total_size=int(total_size or 0),
    )
    if local and reserved_other:
        try:
            ck0 = _sns_cache_key_from_path(Path(local))
            if ck0 and ck0 in reserved_other:
                local = None
        except Exception:
            pass
    if local:
        try:
            payload, media_type = _read_and_maybe_decrypt_media(Path(local), account_dir)
            if payload and str(media_type or "").startswith("image/"):
                resp = Response(content=payload, media_type=str(media_type or "image/jpeg"))
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp
        except Exception:
            pass

    # 1.5) If enabled, and the default match was skipped (or not found), pick the next candidate
    # that is not reserved by a manual pick on another post.
    if reserved_other and int(create_time or 0) > 0 and int(width or 0) > 0 and int(height or 0) > 0:
        wxid_dir = _resolve_account_wxid_dir(account_dir)
        if wxid_dir:
            keys = _list_sns_cached_image_candidate_keys(
                account_dir_str=str(account_dir),
                create_time=int(create_time or 0),
                width=int(width or 0),
                height=int(height or 0),
            )
            base_idx = max(0, int(idx or 0))
            for ck in keys[base_idx:]:
                if not ck or ck in reserved_other:
                    continue
                local2 = _resolve_sns_cached_image_path_by_cache_key(
                    wxid_dir=wxid_dir,
                    cache_key=str(ck),
                    create_time=int(create_time or 0),
                )
                if not local2:
                    continue
                try:
                    payload, media_type = _read_and_maybe_decrypt_media(Path(local2), account_dir)
                    if payload and str(media_type or "").startswith("image/"):
                        resp = Response(content=payload, media_type=str(media_type or "image/jpeg"))
                        resp.headers["Cache-Control"] = "public, max-age=86400"
                        return resp
                except Exception:
                    continue

    # 2) Fallback to the remote URL (may still return a Tencent placeholder image).
    u = str(url or "").strip()
    if not u:
        raise HTTPException(status_code=404, detail="SNS media not found.")

    # Delay-import to avoid pulling requests machinery during normal timeline listing.
    from .chat_media import proxy_image  # pylint: disable=import-outside-toplevel

    try:
        return await proxy_image(u)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetch sns media failed: {e}")


@router.get("/api/sns/article_thumb", summary="提取公众号文章封面图")
async def proxy_article_thumb(url: str):
    u = str(url or "").strip()
    if not u.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(u, headers=headers)
            resp.raise_for_status()
            html_text = resp.text

            match = re.search(r'["\'](https?://[^"\']*?mmbiz_[a-zA-Z]+[^"\']*?)["\']', html_text)

            if not match:
                raise HTTPException(status_code=404, detail="未在 HTML 中找到图片 URL")

            img_url = match.group(1)
            img_url = html.unescape(img_url).replace("&amp;", "&")

            img_resp = await client.get(img_url, headers=headers)
            img_resp.raise_for_status()

            return Response(
                content=img_resp.content,
                media_type=img_resp.headers.get("Content-Type", "image/jpeg")
            )

    except Exception as e:
        logger.warning(f"[sns] 提取公众号封面失败 url={u[:50]}... : {e}")
        raise HTTPException(status_code=404, detail="无法获取文章封面")