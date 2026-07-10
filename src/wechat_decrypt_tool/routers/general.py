from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Query, Request

from ..chat_accounts import resolve_chat_account_context
from ..chat_helpers import (
    _build_avatar_url,
    _decode_message_content,
    _infer_message_brief_by_local_type,
    _infer_transfer_status_text,
    _iter_message_db_paths,
    _load_contact_rows,
    _parse_app_message,
    _parse_system_message_content,
    _pick_display_name,
    _resolve_msg_table_name_by_map,
)
from ..sqlite_diagnostics import is_usable_sqlite_db
from ..wcdb_realtime import WCDB_REALTIME, exec_query as _wcdb_exec_query, get_display_names as _wcdb_get_display_names

router = APIRouter()

_MAX_LIMIT = 500


def _clamp_limit(value: int | None, default: int = 80) -> int:
    try:
        v = int(value if value is not None else default)
    except Exception:
        v = default
    if v <= 0:
        return default
    return min(v, _MAX_LIMIT)


def _clamp_offset(value: int | None) -> int:
    try:
        v = int(value or 0)
    except Exception:
        v = 0
    return max(v, 0)


def _general_context(account: Optional[str]):
    ctx = resolve_chat_account_context(account)
    db_path = ctx.account_dir / "general.db"
    if not db_path.exists():
        if _account_has_realtime_source(ctx):
            return ctx, db_path
        raise HTTPException(status_code=404, detail=f"general.db not found for account: {ctx.name}")
    if not is_usable_sqlite_db(db_path):
        if _account_has_realtime_source(ctx):
            return ctx, db_path
        raise HTTPException(status_code=400, detail="general.db is not a usable SQLite database.")
    return ctx, db_path


def _general_db_path(account: Optional[str]) -> tuple[str, Path]:
    ctx, db_path = _general_context(account)
    return ctx.name, db_path


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # Some WeChat TEXT columns contain protobuf-ish bytes. Decode lossy so a single
    # bad value does not break list endpoints.
    conn.text_factory = lambda b: b.decode("utf-8", "replace")
    return conn


def _source_requested(value: Any = "auto") -> str:
    source = str(value or "auto").strip().lower()
    return source if source in {"auto", "realtime", "decrypted"} else "auto"


def _account_has_realtime_source(ctx: Any) -> bool:
    return bool(
        getattr(ctx, "db_key_present", False)
        and (str(getattr(ctx, "db_storage_path", "") or "").strip() or str(getattr(ctx, "wxid_dir", "") or "").strip())
    )


def _quote_ident(ident: str) -> str:
    return '"' + str(ident or "").replace('"', '""') + '"'


class _DictRow(dict):
    """Small sqlite3.Row-like wrapper for WCDB exec_query rows."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data or {})
        self._ordered_keys = list((data or {}).keys())

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return dict.__getitem__(self, self._ordered_keys[key])
        return dict.__getitem__(self, key)


class _RowsCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [_DictRow(row) for row in rows if isinstance(row, dict)]

    def fetchall(self) -> list[_DictRow]:
        return list(self._rows)

    def fetchone(self) -> _DictRow | None:
        return self._rows[0] if self._rows else None


class _SQLiteSource:
    source = "decrypted"

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn = _connect(self.db_path)

    def __enter__(self) -> "_SQLiteSource":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def execute(self, *args: Any, **kwargs: Any):
        return self._conn.execute(*args, **kwargs)

    def close(self) -> None:
        self._conn.close()


class _WCDBDatabaseSource:
    source = "realtime"

    def __init__(self, rt_conn: Any, db_path: Path) -> None:
        self.rt_conn = rt_conn
        self.db_path = Path(db_path)

    def __enter__(self) -> "_WCDBDatabaseSource":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> _RowsCursor:
        if params:
            raise WCDBRealtimeHTTPError("WCDB realtime general query does not support bound parameters.")
        with self.rt_conn.lock:
            rows = _wcdb_exec_query(
                self.rt_conn.handle,
                # The bundled native API accepts an explicit absolute path for
                # arbitrary db_storage DBs through this exec path.  `general`
                # is not a native enum, so keep the proven generic kind.
                kind="message",
                path=str(self.db_path),
                sql=str(sql or ""),
            )
        return _RowsCursor(rows)

    def close(self) -> None:
        return None


class WCDBRealtimeHTTPError(RuntimeError):
    pass


def _open_realtime_db_source(ctx: Any, *, db_group: str, db_name: str) -> _WCDBDatabaseSource:
    rt_conn = WCDB_REALTIME.ensure_connected(ctx.account_dir)
    db_path = Path(rt_conn.db_storage_dir) / db_group / db_name
    if not db_path.exists() or not db_path.is_file():
        raise FileNotFoundError(f"realtime db not found: {db_path}")
    return _WCDBDatabaseSource(rt_conn, db_path)


def _open_db_source(
    ctx: Any,
    *,
    source: str = "auto",
    db_group: str,
    db_name: str,
    decrypted_name: str,
) -> _SQLiteSource | _WCDBDatabaseSource:
    source_norm = _source_requested(source)
    realtime_capable = _account_has_realtime_source(ctx)
    if source_norm in {"auto", "realtime"} and realtime_capable:
        try:
            return _open_realtime_db_source(ctx, db_group=db_group, db_name=db_name)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"实时读取 {db_group}/{db_name} 失败：{exc}",
            )

    if source_norm == "realtime":
        raise HTTPException(
            status_code=503,
            detail="实时模式不可用：缺少数据库密钥或 db_storage 路径。",
        )

    db_path = ctx.account_dir / decrypted_name
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"{decrypted_name} not found for account: {ctx.name}")
    if not is_usable_sqlite_db(db_path):
        raise HTTPException(status_code=400, detail=f"{decrypted_name} is not a usable SQLite database.")
    return _SQLiteSource(db_path)


def _open_general_source(ctx: Any, source: str = "auto") -> _SQLiteSource | _WCDBDatabaseSource:
    return _open_db_source(
        ctx,
        source=source,
        db_group="general",
        db_name="general.db",
        decrypted_name="general.db",
    )


def _source_meta(conn: Any) -> dict[str, str]:
    return {
        "dataSource": str(getattr(conn, "source", "decrypted") or "decrypted"),
        "database": str(getattr(conn, "db_path", "") or ""),
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _time_text(value: Any) -> str:
    ts = _safe_int(value, 0)
    if ts <= 0:
        return ""
    if ts > 10_000_000_000:
        ts = ts // 1000
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _text(value: Any, *, max_len: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            out = value.decode("utf-8", "replace")
        except Exception:
            out = ""
    else:
        out = str(value)
    out = out.replace("\x00", "").strip()
    if max_len and len(out) > max_len:
        return out[:max_len] + f"…（len={len(out)}）"
    return out


def _blob_len(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    return len(str(value).encode("utf-8", "replace"))


def _json_obj(value: Any) -> dict[str, Any]:
    raw = _text(value)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _coerce_blob_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    text = str(value or "").strip()
    if not text:
        return b""
    compact = re.sub(r"\s+", "", text)
    if compact.lower().startswith("0x"):
        compact = compact[2:]
    if len(compact) >= 2 and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            return bytes.fromhex(compact)
        except Exception:
            return b""
    return text.encode("utf-8", "replace")


def _decode_varint(raw: bytes, idx: int) -> tuple[int | None, int]:
    shift = 0
    value = 0
    start = idx
    while idx < len(raw) and shift < 70:
        b = raw[idx]
        idx += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, idx
        shift += 7
    return None, start


def _decode_probable_utf8(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8", "replace").replace("\x00", "").strip()
    except Exception:
        return ""
    if not text:
        return ""
    printable = sum(1 for ch in text if ch.isprintable())
    if printable / max(len(text), 1) < 0.75:
        return ""
    return text


def _parse_finder_userpage_extra_buffer(extra_buffer: Any) -> dict[str, Any]:
    """Parse the small protobuf-like header in general.wcfinderuserpage.extra_buffer.

    Observed fields in the decrypted DB:
      field 2 = video-account nickname / display alias
      field 5 = last update timestamp
      field 6 = channels profile URL containing username=v2_...@finder

    Larger buffers may continue with cached feed objects after this header; this
    parser intentionally only extracts the stable top-level metadata needed by
    the UI and skips unknown fields.
    """
    raw = _coerce_blob_bytes(extra_buffer)
    out: dict[str, Any] = {
        "nickname": "",
        "signature": "",
        "description": "",
        "updateTime": 0,
        "updateTimeText": "",
        "profileUrl": "",
        "finderUsername": "",
        "hasProfile": False,
    }
    if not raw:
        return out

    idx = 0
    while idx < len(raw):
        tag, next_idx = _decode_varint(raw, idx)
        if tag is None or tag == 0:
            break
        idx = next_idx
        field_no = tag >> 3
        wire_type = tag & 0x7

        if wire_type == 0:
            val, next_idx = _decode_varint(raw, idx)
            if val is None:
                break
            idx = next_idx
            if field_no == 5:
                out["updateTime"] = int(val)
                out["updateTimeText"] = _time_text(val)
            continue

        if wire_type == 2:
            size, next_idx = _decode_varint(raw, idx)
            if size is None:
                break
            idx = next_idx
            end = idx + int(size)
            if end > len(raw):
                break
            chunk = raw[idx:end]
            idx = end
            text = _decode_probable_utf8(chunk)
            if field_no == 2 and text:
                out["nickname"] = text
            elif field_no == 3 and text:
                out["signature"] = text
            elif field_no == 4 and text:
                out["description"] = text
            elif field_no == 6 and text:
                out["profileUrl"] = text
                out["finderUsername"] = _extract_finder_username_from_url(text)
            continue

        if wire_type == 1:
            idx += 8
            continue
        if wire_type == 5:
            idx += 4
            continue
        break

    out["hasProfile"] = bool(out.get("nickname") or out.get("profileUrl") or out.get("finderUsername"))
    return out


def _extract_finder_username_from_url(url: Any) -> str:
    raw = _text(url)
    if not raw:
        return ""
    try:
        query = parse_qs(urlsplit(raw).query)
        username = _text((query.get("username") or [""])[0])
        if username:
            return unquote(username)
    except Exception:
        pass
    match = re.search(r"(v2_[^&\s\"'<>]+@finder)", raw)
    return unquote(match.group(1)) if match else ""


def _finder_profile_url(username: Any) -> str:
    value = _text(username)
    if not value:
        return ""
    return f"https://channels.weixin.qq.com/web/pages/profile?username={quote(value, safe='@_')}"


def _finder_live_url(export_id: Any) -> str:
    value = _text(export_id)
    if not value:
        return ""
    # The WeChat Channels web live page uses eid=export/... .  Only records
    # carrying finder_export_id can be opened directly; finder_live_id alone is
    # not enough to reconstruct this URL.
    return f"https://channels.weixin.qq.com/web/pages/live?eid={quote(value, safe='')}"


def _finder_identity_from_parts(
    *,
    username: str = "",
    display_name: str = "",
    avatar: str = "",
    profile_url: str = "",
    description: str = "",
    source: str = "",
    owner_username: str = "",
) -> dict[str, Any]:
    username = _text(username)
    display_name = _text(display_name)
    avatar = _text(avatar)
    profile_url = _text(profile_url) or _finder_profile_url(username)
    description = _text(description, max_len=220)
    return {
        "username": username,
        "displayName": display_name or (username if username else "未知视频号"),
        "name": display_name or (username if username else "未知视频号"),
        "nickname": display_name,
        "avatar": avatar,
        "avatarUrl": avatar,
        "profileUrl": profile_url,
        "description": description,
        "source": source,
        "ownerUsername": _text(owner_username),
        "isFinder": True,
        "hasResolvedName": bool(display_name and display_name != username),
    }


def _xml_text(element: ET.Element | None, *names: str) -> str:
    if element is None:
        return ""
    lowered = {name.lower() for name in names if name}
    for child in element.iter():
        if child.tag.lower() in lowered:
            return _text(child.text)
    return ""


def _parse_sns_finder_identity_from_xml(raw_content: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = _text(raw_content)
    if not text or "finder" not in text.lower():
        return [], []

    try:
        root = ET.fromstring(text)
    except Exception:
        # Some timeline XML can be partially malformed. Regex fallback still
        # extracts the fields that make the UI human-readable.
        return _parse_sns_finder_identity_by_regex(text)

    identities: list[dict[str, Any]] = []
    live_infos: list[dict[str, Any]] = []

    for node in root.iter():
        tag = str(node.tag or "").lower()
        if tag == "finderlive":
            finder_username = _xml_text(node, "finderUsername", "username")
            live_id = _xml_text(node, "finderLiveID", "liveId")
            nickname = _xml_text(node, "nickname")
            head_url = _xml_text(node, "headUrl", "avatar")
            desc = _xml_text(node, "desc", "description", "liveDescription")
            cover_url = _xml_text(node, "coverUrl", "coverurl", "avatar")
            object_id = _xml_text(node, "finderObjectID", "objectId")
            if finder_username or nickname or live_id:
                identity = _finder_identity_from_parts(
                    username=finder_username,
                    display_name=nickname,
                    avatar=head_url,
                    description=desc,
                    source="sns.finderLive",
                )
                if identity.get("username") or identity.get("hasResolvedName"):
                    identities.append(identity)
                live_infos.append({
                    "finderLiveId": _safe_int(live_id, 0),
                    "finderUsername": finder_username,
                    "nickname": nickname,
                    "headUrl": head_url,
                    "coverUrl": cover_url,
                    "desc": desc,
                    "objectId": object_id,
                    "source": "sns.finderLive",
                })
        elif tag == "finderfeed":
            finder_username = _xml_text(node, "username", "finderUsername")
            nickname = _xml_text(node, "nickname", "findernickname")
            head_url = _xml_text(node, "avatar", "headUrl")
            desc = _xml_text(node, "desc", "description")
            object_id = _xml_text(node, "objectId", "finderObjectID")
            nonce_id = _xml_text(node, "objectNonceId")
            if finder_username or nickname:
                identities.append(_finder_identity_from_parts(
                    username=finder_username,
                    display_name=nickname,
                    avatar=head_url,
                    description=desc,
                    source="sns.finderFeed",
                ) | {
                    "objectId": object_id,
                    "objectNonceId": nonce_id,
                })

    return identities, live_infos


def _regex_tag_text(text: str, tag: str) -> str:
    match = re.search(rf"<{re.escape(tag)}(?:\s[^>]*)?>(.*?)</{re.escape(tag)}>", text, re.I | re.S)
    if not match:
        return ""
    value = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", match.group(1).strip(), flags=re.S)
    return _text(value)


def _parse_sns_finder_identity_by_regex(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    identities: list[dict[str, Any]] = []
    live_infos: list[dict[str, Any]] = []
    for match in re.finditer(r"<finderLive\b[^>]*>(.*?)</finderLive>", text, re.I | re.S):
        block = match.group(1)
        finder_username = _regex_tag_text(block, "finderUsername") or _regex_tag_text(block, "username")
        live_id = _regex_tag_text(block, "finderLiveID") or _regex_tag_text(block, "liveId")
        nickname = _regex_tag_text(block, "nickname")
        head_url = _regex_tag_text(block, "headUrl") or _regex_tag_text(block, "avatar")
        desc = _regex_tag_text(block, "desc") or _regex_tag_text(block, "description")
        cover_url = _regex_tag_text(block, "coverUrl")
        object_id = _regex_tag_text(block, "finderObjectID") or _regex_tag_text(block, "objectId")
        identities.append(_finder_identity_from_parts(
            username=finder_username,
            display_name=nickname,
            avatar=head_url,
            description=desc,
            source="sns.finderLive",
        ))
        live_infos.append({
            "finderLiveId": _safe_int(live_id, 0),
            "finderUsername": finder_username,
            "nickname": nickname,
            "headUrl": head_url,
            "coverUrl": cover_url,
            "desc": desc,
            "objectId": object_id,
            "source": "sns.finderLive",
        })

    for match in re.finditer(r"<finderFeed\b[^>]*>(.*?)</finderFeed>", text, re.I | re.S):
        block = match.group(1)
        finder_username = _regex_tag_text(block, "username") or _regex_tag_text(block, "finderUsername")
        identities.append(_finder_identity_from_parts(
            username=finder_username,
            display_name=_regex_tag_text(block, "nickname") or _regex_tag_text(block, "findernickname"),
            avatar=_regex_tag_text(block, "avatar") or _regex_tag_text(block, "headUrl"),
            description=_regex_tag_text(block, "desc") or _regex_tag_text(block, "description"),
            source="sns.finderFeed",
        ) | {
            "objectId": _regex_tag_text(block, "objectId") or _regex_tag_text(block, "finderObjectID"),
            "objectNonceId": _regex_tag_text(block, "objectNonceId"),
        })
    return identities, live_infos


def _load_finder_sns_maps(ctx: Any, *, source: str = "decrypted") -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    by_username: dict[str, dict[str, Any]] = {}
    by_live_id: dict[int, dict[str, Any]] = {}
    try:
        if source == "realtime":
            conn_cm = _open_db_source(
                ctx,
                source="realtime",
                db_group="sns",
                db_name="sns.db",
                decrypted_name="sns.db",
            )
        else:
            sns_path = ctx.account_dir / "sns.db"
            if not sns_path.exists() or not is_usable_sqlite_db(sns_path):
                return {}, {}
            conn_cm = _SQLiteSource(sns_path)

        with conn_cm as conn:
            rows = conn.execute(
                """
                SELECT content
                FROM SnsTimeLine
                WHERE CAST(content AS TEXT) LIKE '%finderLive%'
                   OR CAST(content AS TEXT) LIKE '%finderFeed%'
                """
            ).fetchall()
            for row in rows:
                identities, live_infos = _parse_sns_finder_identity_from_xml(row["content"])
                for identity in identities:
                    username = _text(identity.get("username"))
                    if not username:
                        continue
                    prev = by_username.get(username, {})
                    # Prefer entries with a readable nickname/avatar over bare IDs.
                    if (not prev.get("hasResolvedName")) or identity.get("avatar") or identity.get("description"):
                        by_username[username] = {**prev, **identity}
                for live in live_infos:
                    live_id = _safe_int(live.get("finderLiveId"), 0)
                    if live_id <= 0:
                        continue
                    by_live_id[live_id] = live
    except Exception:
        return by_username, by_live_id

    return by_username, by_live_id


def _merge_finder_identity(primary: dict[str, Any] | None, fallback: dict[str, Any] | None) -> dict[str, Any] | None:
    if primary and fallback:
        merged = {**fallback, **primary}
        for key in ("displayName", "name", "nickname"):
            if not _text(primary.get(key)) or _text(primary.get(key)) == _text(primary.get("username")):
                if _text(fallback.get(key)):
                    merged[key] = fallback.get(key)
        for key in ("avatar", "avatarUrl", "description", "profileUrl"):
            if not _text(primary.get(key)) and _text(fallback.get(key)):
                merged[key] = fallback.get(key)
        merged["hasResolvedName"] = bool(
            _text(merged.get("displayName")) and _text(merged.get("displayName")) != _text(merged.get("username"))
        )
        return merged
    return primary or fallback


def _compact_parts(*parts: str) -> str:
    return " · ".join([_text(part) for part in parts if _text(part)])


def _extract_search_payload_summary(value: Any) -> dict[str, Any]:
    data = _json_obj(value)
    if not data:
        return {
            "hotword": "",
            "scene": None,
            "businessType": None,
            "source": "",
            "docPullType": "",
            "parentType": None,
            "opType": None,
            "fromTagSearch": None,
            "id": "",
            "searchId": "",
            "requestId": "",
            "summaryText": "",
            "fields": [],
        }

    scene = data.get("scene")
    business_type = data.get("businesstype")
    parent_type = data.get("parentType")
    op_type = data.get("optype")
    from_tag_search = data.get("fromTagSearch")
    source = _text(data.get("source"))
    doc_pull_type = _text(data.get("docPullType"))
    hotword = _text(data.get("hotword"))
    request_id = _text(data.get("requestId"))
    search_id = _text(data.get("searchId"))
    record_id = _text(data.get("id"))

    fields: list[dict[str, str]] = []
    if scene is not None:
        fields.append({"label": "场景", "value": _text(scene)})
    if business_type is not None:
        fields.append({"label": "业务", "value": _text(business_type)})
    if parent_type is not None:
        fields.append({"label": "父类型", "value": _text(parent_type)})
    if op_type is not None:
        fields.append({"label": "操作", "value": _text(op_type)})
    if source:
        fields.append({"label": "来源", "value": source})
    if doc_pull_type:
        fields.append({"label": "拉取", "value": doc_pull_type})
    if from_tag_search is not None:
        fields.append({"label": "标签搜索", "value": _text(from_tag_search)})

    return {
        "hotword": hotword,
        "scene": _safe_int(scene, 0) if scene is not None else None,
        "businessType": _safe_int(business_type, 0) if business_type is not None else None,
        "source": source,
        "docPullType": doc_pull_type,
        "parentType": _safe_int(parent_type, 0) if parent_type is not None else None,
        "opType": _safe_int(op_type, 0) if op_type is not None else None,
        "fromTagSearch": _safe_int(from_tag_search, 0) if from_tag_search is not None else None,
        "id": record_id,
        "searchId": search_id,
        "requestId": request_id,
        "summaryText": _compact_parts(*[f"{x['label']} {x['value']}" for x in fields[:4]]),
        "fields": fields,
    }


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        name = _text(row[0])
        if not name:
            continue
        try:
            out[name] = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] or 0)
        except Exception:
            out[name] = 0
    return out


def _contains_keyword(item: dict[str, Any], keyword: str, fields: Iterable[str]) -> bool:
    kw = str(keyword or "").strip().lower()
    if not kw:
        return True
    for field in fields:
        value = item.get(field)
        if isinstance(value, list):
            hay = " ".join(_text(x) for x in value)
        elif isinstance(value, dict):
            hay = json.dumps(value, ensure_ascii=False)
        else:
            hay = _text(value)
        if kw in hay.lower():
            return True
    return False


def _page(items: list[dict[str, Any]], *, limit: int, offset: int) -> tuple[list[dict[str, Any]], bool]:
    return items[offset:offset + limit], offset + limit < len(items)


def _load_wcdb_display_names_best_effort(account_dir: Path, usernames: list[str]) -> dict[str, str]:
    targets = list(dict.fromkeys([_text(u) for u in usernames if _text(u)]))
    if not targets:
        return {}
    try:
        status = WCDB_REALTIME.get_status(account_dir)
        can_connect = bool(status.get("dll_present")) and bool(status.get("key_present")) and bool(status.get("session_db_path"))
        if not can_connect:
            return {}
        conn = WCDB_REALTIME.ensure_connected(account_dir)
        with conn.lock:
            return _wcdb_get_display_names(conn.handle, targets) or {}
    except Exception:
        return {}


def _resolve_general_contacts(
    *,
    account_dir: Path,
    account_name: str,
    usernames: list[str],
    base_url: str,
) -> dict[str, dict[str, Any]]:
    uniq = list(dict.fromkeys([_text(u) for u in usernames if _text(u)]))
    if not uniq:
        return {}

    contact_rows = _load_contact_rows(account_dir / "contact.db", uniq)
    unresolved_names: list[str] = []
    preliminary_names: dict[str, str] = {}
    for username in uniq:
        display_name = _text(_pick_display_name(contact_rows.get(username), username))
        preliminary_names[username] = display_name
        if (not display_name) or display_name == username:
            unresolved_names.append(username)

    wcdb_names = _load_wcdb_display_names_best_effort(account_dir, unresolved_names)
    base = str(base_url or "").rstrip("/")
    out: dict[str, dict[str, Any]] = {}
    for username in uniq:
        display_name = preliminary_names.get(username) or username
        wcdb_name = _text(wcdb_names.get(username))
        if (not display_name or display_name == username) and wcdb_name and wcdb_name != username:
            display_name = wcdb_name
        avatar_path = _build_avatar_url(account_name, username)
        out[username] = {
            "username": username,
            "displayName": display_name or username,
            "name": display_name or username,
            "avatar": f"{base}{avatar_path}" if base else avatar_path,
            "isGroup": username.endswith("@chatroom"),
            "hasResolvedName": bool(display_name and display_name != username),
        }
    return out


def _attach_contact(
    item: dict[str, Any],
    contact_map: dict[str, dict[str, Any]],
    source_field: str,
    target_field: str,
) -> None:
    username = _text(item.get(source_field))
    if username and username in contact_map:
        item[target_field] = contact_map[username]


def _message_base_type(local_type: Any) -> int:
    value = _safe_int(local_type, 0)
    return value & 0xFFFFFFFF if value > 0xFFFFFFFF else value


def _format_amount_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    text = text.replace("￥", "¥").strip()
    return text


def _summarize_message_row(row: sqlite3.Row) -> dict[str, Any]:
    local_type = _safe_int(row["local_type"], 0)
    base_type = _message_base_type(local_type)
    raw_text = _decode_message_content(row["compress_content"], row["message_content"]).strip()
    parsed: dict[str, Any] = {}
    render_type = "text"
    content = ""
    amount = ""
    pay_sub_type = ""
    transfer_status = ""
    transfer_id = ""
    transfer_memo = ""

    if "<appmsg" in raw_text.lower() or base_type == 49:
        parsed = _parse_app_message(raw_text)
        render_type = _text(parsed.get("renderType")) or "text"
        amount = _format_amount_text(parsed.get("amount"))
        pay_sub_type = _text(parsed.get("paySubType"))
        transfer_id = _text(parsed.get("transferId"))
        if render_type == "transfer":
            transfer_memo = _text(parsed.get("content"))
        content = (
            _text(parsed.get("content"))
            or _text(parsed.get("title"))
            or (f"转账 {amount}" if render_type == "transfer" and amount else "")
        )
        if render_type == "transfer":
            transfer_status = _infer_transfer_status_text(
                is_sent=False,
                paysubtype=pay_sub_type,
                receivestatus=_text(parsed.get("receiveStatus")),
                sendertitle=_text(parsed.get("senderTitle")),
                receivertitle=_text(parsed.get("receiverTitle")),
                senderdes=_text(parsed.get("senderDes")),
                receiverdes=_text(parsed.get("receiverDes")),
            )
            if not content:
                content = transfer_status or "转账"
    elif base_type == 10000:
        render_type = "system"
        content = _parse_system_message_content(raw_text)
    elif base_type == 1:
        render_type = "text"
        content = raw_text
    else:
        render_type = _text(_infer_message_brief_by_local_type(base_type)) or "message"
        if raw_text and not raw_text.lstrip().startswith("<"):
            content = raw_text
        else:
            content = _infer_message_brief_by_local_type(base_type)

    content = _text(content, max_len=180) or _infer_message_brief_by_local_type(base_type)
    return {
        "localId": _safe_int(row["local_id"], 0),
        "serverId": _safe_int(row["server_id"], 0),
        "localType": local_type,
        "baseType": base_type,
        "createTime": _safe_int(row["create_time"], 0),
        "createTimeText": _time_text(row["create_time"]),
        "renderType": render_type,
        "content": content,
        "amount": amount,
        "amountText": amount,
        "paySubType": pay_sub_type,
        "transferStatus": transfer_status,
        "transferId": transfer_id,
        "transferMemo": transfer_memo,
    }


def _message_lookup_key(username: str, *, server_id: Any = 0, local_id: Any = 0) -> str:
    u = _text(username)
    sid = _safe_int(server_id, 0)
    lid = _safe_int(local_id, 0)
    return f"{u}|s:{sid}|l:{lid}"


def _iter_realtime_message_db_paths(rt_conn: Any) -> list[Path]:
    message_dir = Path(rt_conn.db_storage_dir) / "message"
    try:
        return sorted(
            [p for p in message_dir.glob("message_*.db") if p.is_file()],
            key=lambda p: p.name.lower(),
        )
    except Exception:
        return []


def _lookup_messages_for_requests_realtime(
    account_dir: Path,
    requests: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    try:
        rt_conn = WCDB_REALTIME.ensure_connected(account_dir)
    except Exception:
        return {}

    normalized: list[dict[str, Any]] = []
    for req in requests:
        username = _text(req.get("username"))
        if not username:
            continue
        server_id = _safe_int(req.get("serverId"), 0)
        local_id = _safe_int(req.get("localId"), 0)
        if server_id <= 0 and local_id <= 0:
            continue
        normalized.append({"username": username, "serverId": server_id, "localId": local_id, "key": _message_lookup_key(username, server_id=server_id, local_id=local_id)})
    if not normalized:
        return {}

    pending = {req["key"]: req for req in normalized}
    out: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for req in normalized:
        grouped.setdefault(req["username"], []).append(req)

    for db_path in _iter_realtime_message_db_paths(rt_conn):
        if not pending:
            break
        try:
            with rt_conn.lock:
                table_rows = _wcdb_exec_query(
                    rt_conn.handle,
                    kind="message",
                    path=str(db_path),
                    sql="SELECT name FROM sqlite_master WHERE type='table'",
                )
        except Exception:
            continue
        lower_to_actual: dict[str, str] = {}
        for row in table_rows:
            name = _text((row or {}).get("name"))
            if name:
                lower_to_actual[name.lower()] = name

        for username, reqs in grouped.items():
            active_reqs = [req for req in reqs if req["key"] in pending]
            if not active_reqs:
                continue
            table_name = _resolve_msg_table_name_by_map(lower_to_actual, username)
            if not table_name:
                continue
            server_ids = sorted({int(req["serverId"]) for req in active_reqs if int(req["serverId"]) > 0})
            local_ids = sorted({int(req["localId"]) for req in active_reqs if int(req["localId"]) > 0})
            where_parts: list[str] = []
            if server_ids:
                where_parts.append("server_id IN (" + ",".join(str(int(x)) for x in server_ids) + ")")
            if local_ids:
                where_parts.append("local_id IN (" + ",".join(str(int(x)) for x in local_ids) + ")")
            if not where_parts:
                continue
            sql = (
                "SELECT local_id, server_id, local_type, create_time, message_content, compress_content "
                f"FROM {_quote_ident(table_name)} WHERE " + " OR ".join(where_parts)
            )
            try:
                with rt_conn.lock:
                    rows = _wcdb_exec_query(rt_conn.handle, kind="message", path=str(db_path), sql=sql)
            except Exception:
                continue
            summarized = [_summarize_message_row(_DictRow(row)) for row in rows if isinstance(row, dict)]
            for req in active_reqs:
                if req["key"] not in pending:
                    continue
                sid = int(req["serverId"])
                lid = int(req["localId"])
                match = None
                if sid > 0:
                    match = next((m for m in summarized if int(m.get("serverId") or 0) == sid), None)
                if match is None and lid > 0:
                    match = next((m for m in summarized if int(m.get("localId") or 0) == lid), None)
                if match is not None:
                    out[req["key"]] = match
                    pending.pop(req["key"], None)
    return out


def _lookup_messages_for_requests(
    account_dir: Path,
    requests: list[dict[str, Any]],
    *,
    source: str = "decrypted",
) -> dict[str, dict[str, Any]]:
    if source == "realtime":
        return _lookup_messages_for_requests_realtime(account_dir, requests)

    normalized: list[dict[str, Any]] = []
    for req in requests:
        username = _text(req.get("username"))
        if not username:
            continue
        server_id = _safe_int(req.get("serverId"), 0)
        local_id = _safe_int(req.get("localId"), 0)
        if server_id <= 0 and local_id <= 0:
            continue
        normalized.append({"username": username, "serverId": server_id, "localId": local_id, "key": _message_lookup_key(username, server_id=server_id, local_id=local_id)})
    if not normalized:
        return {}

    pending = {req["key"]: req for req in normalized}
    out: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for req in normalized:
        grouped.setdefault(req["username"], []).append(req)

    for db_path in _iter_message_db_paths(account_dir):
        if not pending:
            break
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.text_factory = bytes
        try:
            lower_to_actual: dict[str, str] = {}
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                name = _text(row[0])
                if name:
                    lower_to_actual[name.lower()] = name

            for username, reqs in grouped.items():
                active_reqs = [req for req in reqs if req["key"] in pending]
                if not active_reqs:
                    continue
                table_name = _resolve_msg_table_name_by_map(lower_to_actual, username)
                if not table_name:
                    continue

                server_ids = sorted({int(req["serverId"]) for req in active_reqs if int(req["serverId"]) > 0})
                local_ids = sorted({int(req["localId"]) for req in active_reqs if int(req["localId"]) > 0})
                rows: list[sqlite3.Row] = []
                if server_ids:
                    placeholders = ",".join(["?"] * len(server_ids))
                    try:
                        rows.extend(conn.execute(
                            f'SELECT local_id, server_id, local_type, create_time, message_content, compress_content FROM "{table_name}" WHERE server_id IN ({placeholders})',
                            server_ids,
                        ).fetchall())
                    except Exception:
                        pass
                if local_ids:
                    placeholders = ",".join(["?"] * len(local_ids))
                    try:
                        rows.extend(conn.execute(
                            f'SELECT local_id, server_id, local_type, create_time, message_content, compress_content FROM "{table_name}" WHERE local_id IN ({placeholders})',
                            local_ids,
                        ).fetchall())
                    except Exception:
                        pass

                if not rows:
                    continue
                summarized = [_summarize_message_row(row) for row in rows]
                for req in active_reqs:
                    if req["key"] not in pending:
                        continue
                    sid = int(req["serverId"])
                    lid = int(req["localId"])
                    match = None
                    if sid > 0:
                        match = next((m for m in summarized if int(m.get("serverId") or 0) == sid), None)
                    if match is None and lid > 0:
                        match = next((m for m in summarized if int(m.get("localId") or 0) == lid), None)
                    if match is not None:
                        out[req["key"]] = match
                        pending.pop(req["key"], None)
        finally:
            conn.close()

    return out


def _attach_payment_message_details(account_dir: Path, items: list[dict[str, Any]], *, source: str = "decrypted") -> None:
    requests: list[dict[str, Any]] = []
    request_targets: list[tuple[dict[str, Any], str]] = []
    for item in items:
        session_name = _text(item.get("sessionName"))
        if not session_name:
            continue
        candidates: list[int] = []
        if item.get("kind") == "transfer":
            candidates = [_safe_int(item.get("messageServerId"), 0), _safe_int(item.get("secondMessageServerId"), 0)]
        else:
            candidates = [_safe_int(item.get("messageServerId"), 0)]
        for server_id in candidates:
            if server_id <= 0:
                continue
            key = _message_lookup_key(session_name, server_id=server_id)
            requests.append({"username": session_name, "serverId": server_id, "localId": 0})
            request_targets.append((item, key))

    details = _lookup_messages_for_requests(account_dir, requests, source=source)
    for item, key in request_targets:
        if "message" in item:
            continue
        detail = details.get(key)
        if not detail:
            if item.get("kind") == "redpacket":
                item["amountUnavailableReason"] = "redEnvelopeTable 未包含金额字段，且未在消息库中找到对应红包 XML。"
            continue
        item["message"] = detail
        item["messageSummary"] = _text(detail.get("content"), max_len=180)
        amount = _format_amount_text(detail.get("amount"))
        if amount:
            item["amount"] = amount
            item["amountText"] = amount
        elif item.get("kind") == "redpacket":
            item["amountUnavailableReason"] = "红包金额未保存在 redEnvelopeTable/native_url/消息 XML 中。"
        if detail.get("transferStatus"):
            item["transferStatus"] = detail.get("transferStatus")
        if detail.get("transferMemo"):
            item["transferMemo"] = detail.get("transferMemo")


def _attach_revoke_message_details(account_dir: Path, items: list[dict[str, Any]], *, source: str = "decrypted") -> None:
    requests: list[dict[str, Any]] = []
    request_targets: list[tuple[dict[str, Any], str]] = []
    for item in items:
        if item.get("kind") == "batch":
            username = _text(item.get("sessionName"))
            local_id = _safe_int(item.get("msgLocalId"), 0)
            if username and local_id > 0:
                key = _message_lookup_key(username, local_id=local_id)
                requests.append({"username": username, "serverId": 0, "localId": local_id})
                request_targets.append((item, key))
        else:
            username = _text(item.get("toUserName"))
            server_id = _safe_int(item.get("svrId"), 0)
            if username and server_id > 0:
                key = _message_lookup_key(username, server_id=server_id)
                requests.append({"username": username, "serverId": server_id, "localId": 0})
                request_targets.append((item, key))

    details = _lookup_messages_for_requests(account_dir, requests, source=source)
    for item, key in request_targets:
        detail = details.get(key)
        if not detail:
            continue
        item["message"] = detail
        item["messageSummary"] = _text(detail.get("content"), max_len=180)


@router.get("/api/general/overview", summary="general.db 概览")
def get_general_overview(
    account: Optional[str] = None,
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
):
    ctx, _db_path = _general_context(account)
    account_name = ctx.name
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        counts = _table_counts(conn)
        meta = _source_meta(conn)
    return {
        "status": "success",
        "account": account_name,
        "tableCounts": counts,
        **meta,
    }


@router.get("/api/general/friend-verifications", summary="好友验证/陌生人验证记录")
def list_friend_verifications(
    request: Request,
    account: Optional[str] = None,
    q: str = "",
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
    limit: int = Query(80, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    ctx, db_path = _general_context(account)
    account_name = ctx.name
    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)
    items: list[dict[str, Any]] = []
    usernames: list[str] = []
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        meta = _source_meta(conn)
        rows = conn.execute(
            """
            SELECT user_name_, type_, timestamp_, encrypt_user_name_, content_, is_sender_,
                   ticket_, scene_, fmessage_detail_buf_, remark_, label_ids_
            FROM FMessageTable
            ORDER BY timestamp_ DESC
            """
        ).fetchall()
        for r in rows:
            user_name = _text(r["user_name_"])
            if user_name:
                usernames.append(user_name)
            item = {
                "userName": user_name,
                "type": _safe_int(r["type_"], 0),
                "timestamp": _safe_int(r["timestamp_"], 0),
                "timeText": _time_text(r["timestamp_"]),
                "encryptUserName": _text(r["encrypt_user_name_"], max_len=260),
                "content": _text(r["content_"]),
                "isSender": bool(_safe_int(r["is_sender_"], 0)),
                "ticket": _text(r["ticket_"], max_len=260),
                "scene": _safe_int(r["scene_"], 0),
                "detailSize": _blob_len(r["fmessage_detail_buf_"]),
                "remark": _text(r["remark_"]),
                "labelIds": _text(r["label_ids_"]),
            }
            items.append(item)
    contact_map = _resolve_general_contacts(
        account_dir=ctx.account_dir,
        account_name=account_name,
        usernames=usernames,
        base_url=str(request.base_url).rstrip("/"),
    )
    for item in items:
        _attach_contact(item, contact_map, "userName", "contact")
    items = [item for item in items if _contains_keyword(item, q, ["userName", "content", "remark", "scene", "contact"])]
    sliced, has_more = _page(items, limit=limit, offset=offset)
    return {"status": "success", "account": account_name, "total": len(items), "hasMore": has_more, "items": sliced, **meta}


def _extract_weapp_summary(external_info: Any) -> dict[str, Any]:
    data = _json_obj(external_info)
    if not data:
        return {"keys": [], "registerBody": "", "bindEntries": [], "bindEntryCount": 0, "categories": []}

    register = data.get("RegisterSource") if isinstance(data.get("RegisterSource"), dict) else {}
    bind = data.get("BindWxaInfo") if isinstance(data.get("BindWxaInfo"), dict) else {}
    dynamic = data.get("WxaAppDynamic") if isinstance(data.get("WxaAppDynamic"), dict) else {}
    entries = []
    for raw in bind.get("bizEntryInfo") or []:
        if not isinstance(raw, dict):
            continue
        entries.append({
            "title": _text(raw.get("title")),
            "username": _text(raw.get("username")),
            "iconUrl": _text(raw.get("icon_url")),
        })
    wxa_entries = []
    for raw in bind.get("wxaEntryInfo") or []:
        if not isinstance(raw, dict):
            continue
        wxa_entries.append({
            "title": _text(raw.get("title") or raw.get("nickname") or raw.get("name")),
            "username": _text(raw.get("username") or raw.get("user_name")),
            "appId": _text(raw.get("appid") or raw.get("app_id")),
            "iconUrl": _text(raw.get("icon_url") or raw.get("iconUrl")),
        })
    categories = []
    for raw in dynamic.get("NewCategories") or []:
        if isinstance(raw, str):
            categories.append(raw)
        elif isinstance(raw, dict):
            name = raw.get("name") or raw.get("category") or raw.get("category_name")
            if name:
                categories.append(_text(name))
    return {
        "keys": list(data.keys()),
        "registerBody": _text(register.get("RegisterBody")),
        "bindEntries": entries[:6],
        "bindEntryCount": len(entries),
        "wxaEntries": wxa_entries[:6],
        "wxaEntryCount": len(wxa_entries),
        "categories": categories[:8],
    }


@router.get("/api/general/mini-programs", summary="小程序/WA 联系人信息")
def list_mini_programs(
    account: Optional[str] = None,
    q: str = "",
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
    limit: int = Query(80, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    ctx, _db_path = _general_context(account)
    account_name = ctx.name
    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)
    items: list[dict[str, Any]] = []
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        meta = _source_meta(conn)
        rows = conn.execute(
            """
            SELECT w.user_name, w.type, w.brand_icon_url, w.external_info, w.contact_pack_data,
                   w.wx_app_opt, w.head_image_status, w.app_id,
                   a.last_update_time, length(a.version) AS version_size
            FROM wacontact w
            LEFT JOIN WeAppBizAttrSyncBufferTableV02 a ON a.user_name = w.user_name
            ORDER BY COALESCE(a.last_update_time, 0) DESC, w.user_name ASC
            """
        ).fetchall()
        for r in rows:
            summary = _extract_weapp_summary(r["external_info"])
            titles = [x.get("title", "") for x in summary.get("bindEntries", []) if x.get("title")]
            titles.extend([x.get("title", "") for x in summary.get("wxaEntries", []) if x.get("title")])
            item = {
                "userName": _text(r["user_name"]),
                "type": _safe_int(r["type"], 0),
                "brandIconUrl": _text(r["brand_icon_url"]),
                "externalInfoSize": _blob_len(r["external_info"]),
                "contactPackDataSize": _blob_len(r["contact_pack_data"]),
                "wxAppOpt": _safe_int(r["wx_app_opt"], 0),
                "headImageStatus": _text(r["head_image_status"]),
                "appId": _text(r["app_id"]),
                "lastUpdateTime": _safe_int(r["last_update_time"], 0),
                "lastUpdateText": _time_text(r["last_update_time"]),
                "versionSize": _safe_int(r["version_size"], 0),
                "summary": summary,
                "titles": titles[:8],
            }
            if _contains_keyword(item, q, ["userName", "appId", "brandIconUrl", "titles", "summary"]):
                items.append(item)
    sliced, has_more = _page(items, limit=limit, offset=offset)
    return {"status": "success", "account": account_name, "total": len(items), "hasMore": has_more, "items": sliced, **meta}


@router.get("/api/general/finder", summary="视频号/直播缓存")
def list_finder_records(
    request: Request,
    account: Optional[str] = None,
    q: str = "",
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
    limit: int = Query(100, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    ctx, db_path = _general_context(account)
    account_name = ctx.name
    limit = _clamp_limit(limit, 100)
    offset = _clamp_offset(offset)
    usernames: list[str] = []
    finder_usernames: list[str] = []
    page_finder_map: dict[str, dict[str, Any]] = {}
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        meta = _source_meta(conn)
        lives = []
        for r in conn.execute(
            """
            SELECT finder_live_id, finder_username, finder_export_id, live_status, replay_status, charge_flag
            FROM wcfinderlivestatus
            WHERE live_status IN (1, 2)
            ORDER BY finder_live_id DESC
            """
        ).fetchall():
            finder_username = _text(r["finder_username"])
            if finder_username:
                finder_usernames.append(finder_username)
            finder_export_id = _text(r["finder_export_id"], max_len=260)
            live_url = _finder_live_url(finder_export_id)
            item = {
                "finderLiveId": _safe_int(r["finder_live_id"], 0),
                "finderUsername": finder_username,
                "finderExportId": finder_export_id,
                "liveUrl": live_url,
                "jumpUrl": live_url,
                "canOpenLive": bool(live_url),
                "openLiveHint": "可通过 finder_export_id 打开直播页" if live_url else "该记录未保存 finder_export_id，无法可靠构造直播页直达链接",
                "profileUrl": _finder_profile_url(finder_username),
                "liveStatus": _safe_int(r["live_status"], 0),
                "replayStatus": _safe_int(r["replay_status"], 0),
                "chargeFlag": _safe_int(r["charge_flag"], 0),
            }
            lives.append(item)

        pages = []
        for r in conn.execute("SELECT username, extra_buffer FROM wcfinderuserpage ORDER BY username ASC").fetchall():
            username = _text(r["username"])
            if username:
                usernames.append(username)
            profile = _parse_finder_userpage_extra_buffer(r["extra_buffer"])
            finder_username = _text(profile.get("finderUsername"))
            if finder_username:
                finder_usernames.append(finder_username)
                page_finder_map[finder_username] = _finder_identity_from_parts(
                    username=finder_username,
                    display_name=_text(profile.get("nickname")),
                    profile_url=_text(profile.get("profileUrl")),
                    description=_compact_parts(
                        _text(profile.get("signature")),
                        _text(profile.get("description")),
                    ),
                    source="general.wcfinderuserpage",
                    owner_username=username,
                )
            item = {
                "username": username,
                "finderUsername": finder_username,
                "profileUrl": _text(profile.get("profileUrl")),
                "profile": profile,
                "extraBufferSize": _blob_len(r["extra_buffer"]),
            }
            pages.append(item)

        counts = [dict(row) for row in conn.execute(
            """
            SELECT live_status AS liveStatus, replay_status AS replayStatus, charge_flag AS chargeFlag, COUNT(*) AS count
            FROM wcfinderlivestatus
            WHERE live_status IN (1, 2)
            GROUP BY live_status, replay_status, charge_flag
            ORDER BY count DESC
            """
        ).fetchall()]

    sns_finder_map, sns_live_map = _load_finder_sns_maps(ctx, source=meta.get("dataSource", "decrypted"))
    finder_map: dict[str, dict[str, Any]] = dict(page_finder_map)
    for username, identity in sns_finder_map.items():
        finder_map[username] = _merge_finder_identity(identity, finder_map.get(username)) or identity

    combined = [{"kind": "live", **x} for x in lives]
    contact_map = _resolve_general_contacts(
        account_dir=ctx.account_dir,
        account_name=account_name,
        usernames=usernames,
        base_url=str(request.base_url).rstrip("/"),
    )
    for item in combined:
        if item.get("kind") == "live":
            live_info = sns_live_map.get(_safe_int(item.get("finderLiveId"), 0), {})
            if live_info:
                item["liveInfo"] = live_info
                if not _text(item.get("finderUsername")) and _text(live_info.get("finderUsername")):
                    item["finderUsername"] = _text(live_info.get("finderUsername"))
                if _text(live_info.get("desc")):
                    item["description"] = _text(live_info.get("desc"), max_len=220)
                if _text(live_info.get("coverUrl")):
                    item["coverUrl"] = _text(live_info.get("coverUrl"))
                if _text(live_info.get("objectId")):
                    item["objectId"] = _text(live_info.get("objectId"))
            finder_username = _text(item.get("finderUsername"))
            identity = finder_map.get(finder_username)
            if not identity and live_info:
                identity = _finder_identity_from_parts(
                    username=finder_username or _text(live_info.get("finderUsername")),
                    display_name=_text(live_info.get("nickname")),
                    avatar=_text(live_info.get("headUrl")),
                    description=_text(live_info.get("desc"), max_len=220),
                    source=_text(live_info.get("source")) or "sns.finderLive",
                )
            if identity:
                item["contact"] = identity
                if not _text(item.get("profileUrl")):
                    item["profileUrl"] = _text(identity.get("profileUrl"))
            else:
                _attach_contact(item, contact_map, "finderUsername", "contact")
    combined = [
        item for item in combined
        if _safe_int(item.get("liveStatus"), 0) in {1, 2}
    ]
    combined = [
        item for item in combined
        if _contains_keyword(item, q, [
            "finderUsername", "finderExportId", "finderLiveId", "username", "contact",
            "profile", "profileUrl", "description", "liveInfo",
        ])
    ]
    live_total = sum(1 for item in combined if item.get("kind") == "live")
    openable_total = sum(1 for item in combined if item.get("canOpenLive"))
    sliced, has_more = _page(combined, limit=limit, offset=offset)
    return {
        "status": "success",
        "account": account_name,
        "total": len(combined),
        "hasMore": has_more,
        "counts": counts,
        "liveTotal": live_total,
        "userPageTotal": 0,
        "openableTotal": openable_total,
        "items": sliced,
        **meta,
    }


@router.get("/api/general/payments", summary="转账和红包记录")
def list_payment_records(
    request: Request,
    account: Optional[str] = None,
    q: str = "",
    kind: str = Query("all", pattern="^(all|transfer|redpacket)$"),
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
    limit: int = Query(120, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    ctx, db_path = _general_context(account)
    account_name = ctx.name
    limit = _clamp_limit(limit, 120)
    offset = _clamp_offset(offset)
    items: list[dict[str, Any]] = []
    usernames: list[str] = []
    stats: dict[str, Any] = {}
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        meta = _source_meta(conn)
        if kind in {"all", "transfer"}:
            for r in conn.execute(
                """
                SELECT transfer_id, transcation_id, message_server_id, second_message_server_id,
                       session_name, pay_sub_type, pay_receiver, pay_payer, begin_transfer_time,
                       last_modified_time, invalid_time, last_update_time, delay_confirm_flag, bubble_clicked_flag
                FROM transferTable
                ORDER BY begin_transfer_time DESC
                """
            ).fetchall():
                session_name = _text(r["session_name"])
                pay_receiver = _text(r["pay_receiver"])
                pay_payer = _text(r["pay_payer"])
                usernames.extend([session_name, pay_receiver, pay_payer])
                item = {
                    "kind": "transfer",
                    "transferId": _text(r["transfer_id"]),
                    "transactionId": _text(r["transcation_id"]),
                    "messageServerId": _safe_int(r["message_server_id"], 0),
                    "secondMessageServerId": _safe_int(r["second_message_server_id"], 0),
                    "sessionName": session_name,
                    "paySubType": _safe_int(r["pay_sub_type"], 0),
                    "payReceiver": pay_receiver,
                    "payPayer": pay_payer,
                    "beginTransferTime": _safe_int(r["begin_transfer_time"], 0),
                    "beginTransferTimeText": _time_text(r["begin_transfer_time"]),
                    "lastModifiedTime": _safe_int(r["last_modified_time"], 0),
                    "lastModifiedTimeText": _time_text(r["last_modified_time"]),
                    "invalidTime": _safe_int(r["invalid_time"], 0),
                    "invalidTimeText": _time_text(r["invalid_time"]),
                    "lastUpdateTime": _safe_int(r["last_update_time"], 0),
                    "lastUpdateTimeText": _time_text(r["last_update_time"]),
                    "delayConfirmFlag": _safe_int(r["delay_confirm_flag"], 0),
                    "bubbleClickedFlag": r["bubble_clicked_flag"] if r["bubble_clicked_flag"] is not None else None,
                    "sortTime": _safe_int(r["begin_transfer_time"], 0),
                }
                items.append(item)
        if kind in {"all", "redpacket"}:
            for r in conn.execute(
                """
                SELECT message_server_id, session_name, sender_user_name, native_url, send_id,
                       scene_id, hb_status, hb_type, receive_status
                FROM redEnvelopeTable
                ORDER BY message_server_id DESC
                """
            ).fetchall():
                session_name = _text(r["session_name"])
                sender_user_name = _text(r["sender_user_name"])
                usernames.extend([session_name, sender_user_name])
                item = {
                    "kind": "redpacket",
                    "messageServerId": _safe_int(r["message_server_id"], 0),
                    "sessionName": session_name,
                    "senderUserName": sender_user_name,
                    "nativeUrl": _text(r["native_url"], max_len=260),
                    "sendId": _text(r["send_id"]),
                    "sceneId": _safe_int(r["scene_id"], 0),
                    "hbStatus": _safe_int(r["hb_status"], 0),
                    "hbType": _safe_int(r["hb_type"], 0),
                    "receiveStatus": _safe_int(r["receive_status"], 0),
                    "sortTime": 0,
                }
                items.append(item)
        try:
            stats["transferCount"] = int(conn.execute("SELECT COUNT(*) FROM transferTable").fetchone()[0] or 0)
            stats["redPacketCount"] = int(conn.execute("SELECT COUNT(*) FROM redEnvelopeTable").fetchone()[0] or 0)
            stats["transferSessions"] = int(conn.execute("SELECT COUNT(DISTINCT session_name) FROM transferTable").fetchone()[0] or 0)
            stats["redPacketSessions"] = int(conn.execute("SELECT COUNT(DISTINCT session_name) FROM redEnvelopeTable").fetchone()[0] or 0)
        except Exception:
            pass
    contact_map = _resolve_general_contacts(
        account_dir=ctx.account_dir,
        account_name=account_name,
        usernames=usernames,
        base_url=str(request.base_url).rstrip("/"),
    )
    for item in items:
        _attach_contact(item, contact_map, "sessionName", "sessionContact")
        if item.get("kind") == "transfer":
            _attach_contact(item, contact_map, "payPayer", "payerContact")
            _attach_contact(item, contact_map, "payReceiver", "receiverContact")
        else:
            _attach_contact(item, contact_map, "senderUserName", "senderContact")
    items = [
        item for item in items
        if _contains_keyword(
            item,
            q,
            [
                "transferId", "transactionId", "sessionName", "payReceiver", "payPayer",
                "senderUserName", "sendId", "nativeUrl", "sessionContact", "payerContact",
                "receiverContact", "senderContact",
            ],
        )
    ]
    items.sort(key=lambda x: (_safe_int(x.get("sortTime"), 0), _safe_int(x.get("messageServerId"), 0)), reverse=True)
    sliced, has_more = _page(items, limit=limit, offset=offset)
    _attach_payment_message_details(ctx.account_dir, sliced, source=meta.get("dataSource", "decrypted"))
    return {"status": "success", "account": account_name, "total": len(items), "hasMore": has_more, "stats": stats, "items": sliced, **meta}


@router.get("/api/general/revokes", summary="撤回/可撤回缓存")
def list_revoke_records(
    request: Request,
    account: Optional[str] = None,
    q: str = "",
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
    limit: int = Query(100, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    ctx, db_path = _general_context(account)
    account_name = ctx.name
    limit = _clamp_limit(limit, 100)
    offset = _clamp_offset(offset)
    items: list[dict[str, Any]] = []
    usernames: list[str] = []
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        meta = _source_meta(conn)
        for r in conn.execute(
            """
            SELECT local_id, batch_id, msg_unique_id, session_name, msg_local_id, msg_create_time
            FROM revokebatchmessage
            ORDER BY msg_create_time DESC, local_id DESC
            """
        ).fetchall():
            session_name = _text(r["session_name"])
            if session_name:
                usernames.append(session_name)
            item = {
                "kind": "batch",
                "recordType": "batch_revoke_candidate",
                "recordTypeLabel": "可批量撤回缓存",
                "semantic": "revokebatchmessage 记录的是本机发送消息的批量撤回候选/索引，不等同于已经撤回。",
                "isActualRevoke": False,
                "localId": _safe_int(r["local_id"], 0),
                "batchId": _safe_int(r["batch_id"], 0),
                "msgUniqueId": _text(r["msg_unique_id"]),
                "sessionName": session_name,
                "msgLocalId": _safe_int(r["msg_local_id"], 0),
                "msgCreateTime": _safe_int(r["msg_create_time"], 0),
                "msgCreateTimeText": _time_text(r["msg_create_time"]),
            }
            items.append(item)
        for r in conn.execute(
            """
            SELECT to_user_name, svr_id, message_type, revoke_time, content, at_user_list
            FROM revokemessage
            ORDER BY revoke_time DESC
            """
        ).fetchall():
            to_user_name = _text(r["to_user_name"])
            if to_user_name:
                usernames.append(to_user_name)
            item = {
                "kind": "single",
                "recordType": "actual_revoke",
                "recordTypeLabel": "已撤回",
                "semantic": "revokemessage 记录实际撤回通知。",
                "isActualRevoke": True,
                "toUserName": to_user_name,
                "svrId": _safe_int(r["svr_id"], 0),
                "messageType": _safe_int(r["message_type"], 0),
                "revokeTime": _safe_int(r["revoke_time"], 0),
                "revokeTimeText": _time_text(r["revoke_time"]),
                "content": _text(r["content"], max_len=320),
                "atUserList": _text(r["at_user_list"], max_len=320),
            }
            items.append(item)
    contact_map = _resolve_general_contacts(
        account_dir=ctx.account_dir,
        account_name=account_name,
        usernames=usernames,
        base_url=str(request.base_url).rstrip("/"),
    )
    for item in items:
        if item.get("kind") == "batch":
            _attach_contact(item, contact_map, "sessionName", "sessionContact")
        else:
            _attach_contact(item, contact_map, "toUserName", "sessionContact")
    items = [
        item for item in items
        if _contains_keyword(
            item,
            q,
            ["msgUniqueId", "sessionName", "batchId", "msgLocalId", "toUserName", "svrId", "content", "atUserList", "sessionContact"],
        )
    ]
    items.sort(key=lambda x: _safe_int(x.get("msgCreateTime") or x.get("revokeTime"), 0), reverse=True)
    sliced, has_more = _page(items, limit=limit, offset=offset)
    _attach_revoke_message_details(ctx.account_dir, sliced, source=meta.get("dataSource", "decrypted"))
    actual_total = sum(1 for item in items if item.get("isActualRevoke"))
    candidate_total = sum(1 for item in items if item.get("recordType") == "batch_revoke_candidate")
    return {
        "status": "success",
        "account": account_name,
        "total": len(items),
        "actualTotal": actual_total,
        "candidateTotal": candidate_total,
        "hasMore": has_more,
        "items": sliced,
        **meta,
    }


@router.get("/api/general/search-records", summary="首页搜索框相关历史记录")
def list_search_records(
    request: Request,
    account: Optional[str] = None,
    source: str = Query("auto", pattern="^(auto|realtime|decrypted)$"),
    limit: int = Query(30, ge=1, le=100),
):
    ctx, db_path = _general_context(account)
    account_name = ctx.name
    limit = min(max(int(limit or 30), 1), 100)
    items: list[dict[str, Any]] = []
    chat_usernames: list[str] = []
    meta: dict[str, str] = {}
    with _open_general_source(ctx, source) as conn:
        meta = _source_meta(conn)
        for r in conn.execute("SELECT username, query, score, last_click_time FROM SearchRecent").fetchall():
            username = _text(r["username"])
            if username:
                chat_usernames.append(username)
            items.append({
                "source": "聊天搜索",
                "keyword": _text(r["query"]),
                "username": username,
                "score": _safe_int(r["score"], 0),
                "timestamp": _safe_int(r["last_click_time"], 0),
                "timeText": _time_text(r["last_click_time"]),
            })
        for table, source in (("brand_search_record", "品牌搜索"), ("websearch_record", "网页搜索")):
            for r in conn.execute(f'SELECT keyword, pay_load_, create_time FROM "{table}"').fetchall():
                payload_summary = _extract_search_payload_summary(r["pay_load_"])
                items.append({
                    "source": source,
                    "keyword": _text(r["keyword"]) or _text(payload_summary.get("hotword")),
                    "payload": _text(r["pay_load_"], max_len=260),
                    "payloadSummary": payload_summary,
                    "summaryText": _text(payload_summary.get("summaryText")),
                    "timestamp": _safe_int(r["create_time"], 0),
                    "timeText": _time_text(r["create_time"]),
                })
    contact_map = _resolve_general_contacts(
        account_dir=ctx.account_dir,
        account_name=account_name,
        usernames=chat_usernames,
        base_url=str(request.base_url).rstrip("/"),
    )
    for item in items:
        if item.get("source") != "聊天搜索":
            continue
        username = _text(item.get("username"))
        if username and username in contact_map:
            item["contact"] = contact_map[username]
    items.sort(key=lambda x: _safe_int(x.get("timestamp"), 0), reverse=True)
    return {"status": "success", "account": account_name, "total": len(items), "items": items[:limit], **meta}
