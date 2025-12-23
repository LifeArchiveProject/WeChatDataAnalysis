from __future__ import annotations

import heapq
import io
import json
import re
import sqlite3
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from .chat_helpers import (
    _decode_message_content,
    _decode_sqlite_text,
    _extract_sender_from_group_xml,
    _extract_xml_attr,
    _extract_xml_tag_or_attr,
    _extract_xml_tag_text,
    _infer_message_brief_by_local_type,
    _infer_transfer_status_text,
    _iter_message_db_paths,
    _list_decrypted_accounts,
    _load_contact_rows,
    _lookup_resource_md5,
    _parse_app_message,
    _parse_pat_message,
    _pick_display_name,
    _quote_ident,
    _resolve_account_dir,
    _resolve_msg_table_name,
    _resource_lookup_chat_id,
    _should_keep_session,
    _split_group_sender_prefix,
)
from .logging_config import get_logger
from .media_helpers import (
    _convert_silk_to_wav,
    _detect_image_media_type,
    _fallback_search_media_by_file_id,
    _resolve_account_db_storage_dir,
    _resolve_account_wxid_dir,
    _resolve_media_path_for_kind,
    _try_find_decrypted_resource,
)

logger = get_logger(__name__)

ExportFormat = Literal["json", "txt"]
ExportScope = Literal["selected", "all", "groups", "singles"]
ExportStatus = Literal["queued", "running", "done", "error", "cancelled"]
MediaKind = Literal["image", "emoji", "video", "video_thumb", "voice", "file"]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(s: str, max_len: int = 80) -> str:
    t = str(s or "").strip()
    if not t:
        return ""
    t = _INVALID_PATH_CHARS.sub("_", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    return t


def _format_ts(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _is_md5(s: str) -> bool:
    return bool(re.fullmatch(r"(?i)[0-9a-f]{32}", str(s or "").strip()))


@dataclass
class ExportProgress:
    conversations_total: int = 0
    conversations_done: int = 0
    current_conversation_index: int = 0  # 1-based
    current_conversation_username: str = ""
    current_conversation_name: str = ""
    current_conversation_messages_total: int = 0
    current_conversation_messages_exported: int = 0
    messages_exported: int = 0
    media_copied: int = 0
    media_missing: int = 0


@dataclass
class ExportJob:
    export_id: str
    account: str
    status: ExportStatus = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: str = ""
    zip_path: Optional[Path] = None
    options: dict[str, Any] = field(default_factory=dict)
    progress: ExportProgress = field(default_factory=ExportProgress)
    cancel_requested: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "exportId": self.export_id,
            "account": self.account,
            "status": self.status,
            "createdAt": int(self.created_at),
            "startedAt": int(self.started_at) if self.started_at else None,
            "finishedAt": int(self.finished_at) if self.finished_at else None,
            "error": self.error or "",
            "zipPath": str(self.zip_path) if self.zip_path else "",
            "zipReady": bool(self.zip_path and self.zip_path.exists()),
            "options": self.options,
            "progress": {
                "conversationsTotal": self.progress.conversations_total,
                "conversationsDone": self.progress.conversations_done,
                "currentConversationIndex": self.progress.current_conversation_index,
                "currentConversationUsername": self.progress.current_conversation_username,
                "currentConversationName": self.progress.current_conversation_name,
                "currentConversationMessagesTotal": self.progress.current_conversation_messages_total,
                "currentConversationMessagesExported": self.progress.current_conversation_messages_exported,
                "messagesExported": self.progress.messages_exported,
                "mediaCopied": self.progress.media_copied,
                "mediaMissing": self.progress.media_missing,
            },
        }


class _JobCancelled(Exception):
    pass


class ChatExportManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ExportJob] = {}

    def list_jobs(self) -> list[ExportJob]:
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, export_id: str) -> Optional[ExportJob]:
        with self._lock:
            return self._jobs.get(export_id)

    def cancel_job(self, export_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(export_id)
            if not job:
                return False
            job.cancel_requested = True
            if job.status in {"queued"}:
                job.status = "cancelled"
                job.finished_at = time.time()
            return True

    def create_job(
        self,
        *,
        account: Optional[str],
        scope: ExportScope,
        usernames: list[str],
        export_format: ExportFormat,
        start_time: Optional[int],
        end_time: Optional[int],
        include_hidden: bool,
        include_official: bool,
        include_media: bool,
        media_kinds: list[MediaKind],
        allow_process_key_extract: bool,
        privacy_mode: bool,
        file_name: Optional[str],
    ) -> ExportJob:
        account_dir = _resolve_account_dir(account)
        export_id = uuid.uuid4().hex[:12]

        job = ExportJob(
            export_id=export_id,
            account=account_dir.name,
            status="queued",
            options={
                "scope": scope,
                "usernames": usernames,
                "format": export_format,
                "startTime": int(start_time) if start_time else None,
                "endTime": int(end_time) if end_time else None,
                "includeHidden": bool(include_hidden),
                "includeOfficial": bool(include_official),
                "includeMedia": bool(include_media),
                "mediaKinds": media_kinds,
                "allowProcessKeyExtract": bool(allow_process_key_extract),
                "privacyMode": bool(privacy_mode),
                "fileName": str(file_name or "").strip(),
            },
        )

        with self._lock:
            self._jobs[export_id] = job

        t = threading.Thread(
            target=self._run_job_safe,
            args=(job, account_dir),
            name=f"chat-export-{export_id}",
            daemon=True,
        )
        t.start()
        return job

    def _run_job_safe(self, job: ExportJob, account_dir: Path) -> None:
        try:
            self._run_job(job, account_dir)
        except Exception as e:
            logger.exception(f"export job failed: {job.export_id}: {e}")
            with self._lock:
                job.status = "error"
                job.error = str(e)
                job.finished_at = time.time()

    def _should_cancel(self, job: ExportJob) -> bool:
        with self._lock:
            return bool(job.cancel_requested)

    def _run_job(self, job: ExportJob, account_dir: Path) -> None:
        with self._lock:
            if job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = time.time()
            job.error = ""

        opts = dict(job.options or {})
        scope: ExportScope = str(opts.get("scope") or "selected")  # type: ignore[assignment]
        export_format: ExportFormat = str(opts.get("format") or "json")  # type: ignore[assignment]
        include_hidden = bool(opts.get("includeHidden"))
        include_official = bool(opts.get("includeOfficial"))
        include_media = bool(opts.get("includeMedia"))
        allow_process_key_extract = bool(opts.get("allowProcessKeyExtract"))
        privacy_mode = bool(opts.get("privacyMode"))

        media_kinds_raw = opts.get("mediaKinds") or []
        media_kinds: list[MediaKind] = []
        for k in media_kinds_raw:
            ks = str(k or "").strip()
            if ks in {"image", "emoji", "video", "video_thumb", "voice", "file"}:
                media_kinds.append(ks)  # type: ignore[arg-type]

        if privacy_mode:
            include_media = False
            media_kinds = []

        st = int(opts.get("startTime") or 0) or None
        et = int(opts.get("endTime") or 0) or None

        target_usernames = _resolve_export_targets(
            account_dir=account_dir,
            scope=scope,
            usernames=list(opts.get("usernames") or []),
            include_hidden=include_hidden,
            include_official=include_official,
        )
        if not target_usernames:
            raise ValueError("No target conversations to export.")

        exports_root = account_dir.parents[1] / "exports" / account_dir.name
        exports_root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        base_name = str(opts.get("fileName") or "").strip()
        if not base_name:
            if privacy_mode:
                base_name = f"wechat_chat_export_privacy_{ts}_{job.export_id}.zip"
            else:
                base_name = f"wechat_chat_export_{account_dir.name}_{ts}_{job.export_id}.zip"
        else:
            base_name = _safe_name(base_name, max_len=120) or f"wechat_chat_export_{account_dir.name}_{ts}_{job.export_id}.zip"
            if not base_name.lower().endswith(".zip"):
                base_name += ".zip"

        final_zip = (exports_root / base_name).resolve()
        tmp_zip = (exports_root / f".{base_name}.{job.export_id}.part").resolve()

        contact_db_path = account_dir / "contact.db"
        message_resource_db_path = account_dir / "message_resource.db"
        media_db_path = account_dir / "media_0.db"
        head_image_db_path = account_dir / "head_image.db"

        resource_conn: Optional[sqlite3.Connection] = None
        try:
            if message_resource_db_path.exists():
                resource_conn = sqlite3.connect(str(message_resource_db_path))
                resource_conn.row_factory = sqlite3.Row
        except Exception:
            try:
                if resource_conn is not None:
                    resource_conn.close()
            except Exception:
                pass
            resource_conn = None

        head_image_conn: Optional[sqlite3.Connection] = None
        if not privacy_mode:
            try:
                if head_image_db_path.exists():
                    head_image_conn = sqlite3.connect(str(head_image_db_path))
            except Exception:
                try:
                    if head_image_conn is not None:
                        head_image_conn.close()
                except Exception:
                    pass
                head_image_conn = None

        contact_cache: dict[str, str] = {}
        contact_row_cache: dict[str, sqlite3.Row] = {}

        def resolve_display_name(u: str) -> str:
            if not u:
                return ""
            if u in contact_cache:
                return contact_cache[u]
            rows = _load_contact_rows(contact_db_path, [u])
            row = rows.get(u)
            if row is not None:
                contact_row_cache[u] = row
            name = _pick_display_name(row, u)
            contact_cache[u] = name
            return name

        conv_rows = _load_contact_rows(contact_db_path, target_usernames)
        for k, v in conv_rows.items():
            contact_row_cache[k] = v
            contact_cache[k] = _pick_display_name(v, k)

        media_written: dict[str, str] = {}
        avatar_written: dict[str, str] = {}
        report: dict[str, Any] = {
            "schemaVersion": 1,
            "exportId": job.export_id,
            "account": account_dir.name,
            "createdAt": _now_iso(),
            "missingMedia": [],
            "errors": [],
        }

        with self._lock:
            job.progress.conversations_total = len(target_usernames)
            job.progress.conversations_done = 0
            job.progress.messages_exported = 0
            job.progress.media_copied = 0
            job.progress.media_missing = 0

        try:
            if tmp_zip.exists():
                try:
                    tmp_zip.unlink()
                except Exception:
                    pass

            with zipfile.ZipFile(tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                for idx, conv_username in enumerate(target_usernames, start=1):
                    if self._should_cancel(job):
                        raise _JobCancelled()

                    conv_row = contact_row_cache.get(conv_username)
                    conv_name = _pick_display_name(conv_row, conv_username)
                    conv_is_group = bool(conv_username.endswith("@chatroom"))

                    conv_dir = f"conversations/{_conversation_dir_name(idx, conv_name, conv_username, conv_is_group, privacy_mode)}"

                    with self._lock:
                        job.progress.current_conversation_index = idx
                        job.progress.current_conversation_username = conv_username
                        job.progress.current_conversation_name = conv_name
                        job.progress.current_conversation_messages_exported = 0
                        job.progress.current_conversation_messages_total = 0

                    try:
                        estimated_total = _estimate_conversation_message_count(
                            account_dir=account_dir,
                            conv_username=conv_username,
                            start_time=st,
                            end_time=et,
                        )
                    except Exception:
                        estimated_total = 0

                    with self._lock:
                        job.progress.current_conversation_messages_total = int(estimated_total)

                    chat_id = None
                    try:
                        if resource_conn is not None:
                            chat_id = _resource_lookup_chat_id(resource_conn, conv_username)
                    except Exception:
                        chat_id = None

                    conv_avatar_path = ""
                    if not privacy_mode:
                        conv_avatar_path = _materialize_avatar(
                            zf=zf,
                            head_image_conn=head_image_conn,
                            username=conv_username,
                            avatar_written=avatar_written,
                        )

                    if export_format == "txt":
                        exported_count = _write_conversation_txt(
                            zf=zf,
                            conv_dir=conv_dir,
                            account_dir=account_dir,
                            conv_username=conv_username,
                            conv_name=conv_name,
                            conv_avatar_path=conv_avatar_path,
                            conv_is_group=conv_is_group,
                            start_time=st,
                            end_time=et,
                            resource_conn=resource_conn,
                            resource_chat_id=chat_id,
                            head_image_conn=head_image_conn,
                            resolve_display_name=resolve_display_name,
                            privacy_mode=privacy_mode,
                            include_media=include_media,
                            media_kinds=media_kinds,
                            media_written=media_written,
                            avatar_written=avatar_written,
                            report=report,
                            allow_process_key_extract=allow_process_key_extract,
                            media_db_path=media_db_path,
                            job=job,
                            lock=self._lock,
                        )
                    else:
                        exported_count = _write_conversation_json(
                            zf=zf,
                            conv_dir=conv_dir,
                            account_dir=account_dir,
                            conv_username=conv_username,
                            conv_name=conv_name,
                            conv_avatar_path=conv_avatar_path,
                            conv_is_group=conv_is_group,
                            start_time=st,
                            end_time=et,
                            resource_conn=resource_conn,
                            resource_chat_id=chat_id,
                            head_image_conn=head_image_conn,
                            resolve_display_name=resolve_display_name,
                            privacy_mode=privacy_mode,
                            include_media=include_media,
                            media_kinds=media_kinds,
                            media_written=media_written,
                            avatar_written=avatar_written,
                            report=report,
                            allow_process_key_extract=allow_process_key_extract,
                            media_db_path=media_db_path,
                            job=job,
                            lock=self._lock,
                        )

                    meta = {
                        "schemaVersion": 1,
                        "username": "" if privacy_mode else conv_username,
                        "displayName": "已隐藏" if privacy_mode else conv_name,
                        "avatarPath": "" if privacy_mode else (conv_avatar_path or ""),
                        "isGroup": bool(conv_is_group),
                        "exportedAt": _now_iso(),
                        "messageCount": int(exported_count),
                    }
                    zf.writestr(f"{conv_dir}/meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

                    with self._lock:
                        job.progress.conversations_done += 1

                manifest = {
                    "schemaVersion": 1,
                    "exportedAt": _now_iso(),
                    "exportId": job.export_id,
                    "account": "hidden" if privacy_mode else account_dir.name,
                    "format": export_format,
                    "scope": scope,
                    "filters": {
                        "startTime": st,
                        "endTime": et,
                        "includeHidden": include_hidden,
                        "includeOfficial": include_official,
                    },
                    "options": {
                        "includeMedia": include_media,
                        "mediaKinds": media_kinds,
                        "allowProcessKeyExtract": allow_process_key_extract,
                        "privacyMode": privacy_mode,
                    },
                    "stats": {
                        "conversations": len(target_usernames),
                        "messagesExported": job.progress.messages_exported,
                        "mediaCopied": job.progress.media_copied,
                        "mediaMissing": job.progress.media_missing,
                    },
                    "accountsAvailable": _list_decrypted_accounts(),
                }
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                zf.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))

            if final_zip.exists():
                final_zip = (exports_root / f"{final_zip.stem}_{job.export_id}{final_zip.suffix}").resolve()
            tmp_zip.replace(final_zip)

            with self._lock:
                job.status = "done"
                job.zip_path = final_zip
                job.finished_at = time.time()
        except _JobCancelled:
            try:
                if tmp_zip.exists():
                    tmp_zip.unlink()
            except Exception:
                pass
            with self._lock:
                job.status = "cancelled"
                job.finished_at = time.time()
        finally:
            try:
                if resource_conn is not None:
                    resource_conn.close()
            except Exception:
                pass
            try:
                if head_image_conn is not None:
                    head_image_conn.close()
            except Exception:
                pass


def _resolve_export_targets(
    *,
    account_dir: Path,
    scope: ExportScope,
    usernames: list[str],
    include_hidden: bool,
    include_official: bool,
) -> list[str]:
    if scope == "selected":
        uniq = list(dict.fromkeys([str(u or "").strip() for u in usernames if str(u or "").strip()]))
        return uniq

    session_db_path = account_dir / "session.db"
    conn = sqlite3.connect(str(session_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT username, is_hidden
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            """,
        ).fetchall()
    finally:
        conn.close()

    out: list[str] = []
    for r in rows:
        u = str(r["username"] or "").strip()
        if not u:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(u, include_official=include_official):
            continue
        if scope == "groups" and (not u.endswith("@chatroom")):
            continue
        if scope == "singles" and u.endswith("@chatroom"):
            continue
        out.append(u)
    return out


def _conversation_dir_name(
    idx: int,
    display_name: str,
    username: str,
    is_group: bool,
    privacy_mode: bool,
) -> str:
    h = uuid.uuid5(uuid.NAMESPACE_DNS, username).hex[:8] if username else uuid.uuid4().hex[:8]
    if privacy_mode:
        kind = "group" if is_group else "single"
        return f"{idx:04d}_{kind}_{h}"

    base = _safe_name(display_name, max_len=40) or "conversation"
    user_part = _safe_name(username, max_len=50) or "unknown"
    return f"{idx:04d}_{base}_{user_part}_{h}"


def _estimate_conversation_message_count(
    *,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
) -> int:
    total = 0
    for db_path in _iter_message_db_paths(account_dir):
        conn = sqlite3.connect(str(db_path))
        try:
            table = _resolve_msg_table_name(conn, conv_username)
            if not table:
                continue
            quoted = _quote_ident(table)
            where = []
            params: list[Any] = []
            if start_time is not None:
                where.append("create_time >= ?")
                params.append(int(start_time))
            if end_time is not None:
                where.append("create_time <= ?")
                params.append(int(end_time))
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""
            row = conn.execute(f"SELECT COUNT(1) FROM {quoted}{where_sql}", params).fetchone()
            if row and row[0] is not None:
                total += int(row[0])
        finally:
            conn.close()
    return total


@dataclass
class _Row:
    db_stem: str
    table_name: str
    local_id: int
    server_id: int
    local_type: int
    sort_seq: int
    create_time: int
    raw_text: str
    sender_username: str
    is_sent: bool


def _iter_rows_for_conversation(
    *,
    account_dir: Path,
    conv_username: str,
    start_time: Optional[int],
    end_time: Optional[int],
) -> Iterable[_Row]:
    db_paths = _iter_message_db_paths(account_dir)
    if not db_paths:
        return []

    account_wxid = account_dir.name

    def iter_db(db_path: Path) -> Iterable[_Row]:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            table_name = _resolve_msg_table_name(conn, conv_username)
            if not table_name:
                return

            # Force sqlite3 to return TEXT as raw bytes for this query, so we can zstd-decompress
            # compress_content reliably (and avoid losing binary payloads).
            conn.text_factory = bytes

            my_rowid = None
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (account_wxid,),
                ).fetchone()
                if r is not None:
                    my_rowid = int(r[0])
            except Exception:
                my_rowid = None

            quoted = _quote_ident(table_name)
            where = []
            params: list[Any] = []
            if start_time is not None:
                where.append("m.create_time >= ?")
                params.append(int(start_time))
            if end_time is not None:
                where.append("m.create_time <= ?")
                params.append(int(end_time))
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""

            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                f"{where_sql} "
                "ORDER BY m.create_time ASC, m.sort_seq ASC, m.local_id ASC "
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
                f"FROM {quoted} m "
                f"{where_sql} "
                "ORDER BY m.create_time ASC, m.sort_seq ASC, m.local_id ASC "
            )

            try:
                cur = conn.execute(sql_with_join, params)
            except Exception:
                cur = conn.execute(sql_no_join, params)

            batch = 400
            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break
                for r in rows:
                    local_id = int(r["local_id"] or 0)
                    server_id = int(r["server_id"] or 0)
                    local_type = int(r["local_type"] or 0)
                    sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                    create_time = int(r["create_time"] or 0)
                    sender_username = _decode_sqlite_text(r["sender_username"]).strip()

                    is_sent = False
                    if my_rowid is not None:
                        try:
                            is_sent = int(r["real_sender_id"] or 0) == int(my_rowid)
                        except Exception:
                            is_sent = False

                    raw_text = _decode_message_content(r["compress_content"], r["message_content"]).strip()

                    is_group = bool(conv_username.endswith("@chatroom"))
                    sender_prefix = ""
                    if is_group and raw_text and (not raw_text.startswith("<")) and (not raw_text.startswith('"<')):
                        sender_prefix, raw_text = _split_group_sender_prefix(raw_text)
                    if is_group and sender_prefix:
                        sender_username = sender_prefix
                    if is_group and raw_text and (raw_text.startswith("<") or raw_text.startswith('"<')):
                        xml_sender = _extract_sender_from_group_xml(raw_text)
                        if xml_sender:
                            sender_username = xml_sender

                    if is_sent:
                        sender_username = account_wxid
                    elif (not is_group) and (not sender_username):
                        sender_username = conv_username

                    yield _Row(
                        db_stem=db_path.stem,
                        table_name=table_name,
                        local_id=local_id,
                        server_id=server_id,
                        local_type=local_type,
                        sort_seq=sort_seq,
                        create_time=create_time,
                        raw_text=raw_text,
                        sender_username=sender_username,
                        is_sent=bool(is_sent),
                    )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    streams = [iter_db(p) for p in db_paths]

    def sort_key(r: _Row) -> tuple[int, int, int]:
        return (int(r.create_time or 0), int(r.sort_seq or 0), int(r.local_id or 0))

    return heapq.merge(*streams, key=sort_key)


def _parse_message_for_export(
    *,
    row: _Row,
    conv_username: str,
    is_group: bool,
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
) -> dict[str, Any]:
    raw_text = row.raw_text or ""
    local_type = int(row.local_type or 0)
    is_sent = bool(row.is_sent)

    render_type = "text"
    content_text = raw_text
    title = ""
    url = ""
    image_md5 = ""
    image_file_id = ""
    emoji_md5 = ""
    emoji_url = ""
    thumb_url = ""
    image_url = ""
    video_md5 = ""
    video_thumb_md5 = ""
    video_file_id = ""
    video_thumb_file_id = ""
    video_url = ""
    video_thumb_url = ""
    voice_length = ""
    quote_title = ""
    quote_content = ""
    amount = ""
    cover_url = ""
    file_size = ""
    pay_sub_type = ""
    transfer_status = ""
    file_md5 = ""
    transfer_id = ""
    voip_type = ""

    if local_type == 10000:
        render_type = "system"
        if "revokemsg" in raw_text:
            content_text = "撤回了一条消息"
        else:
            import re as _re

            content_text = _re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
            content_text = _re.sub(r"\\s+", " ", content_text).strip() or "[系统消息]"
    elif local_type == 49:
        parsed = _parse_app_message(raw_text)
        render_type = str(parsed.get("renderType") or "text")
        content_text = str(parsed.get("content") or "")
        title = str(parsed.get("title") or "")
        url = str(parsed.get("url") or "")
        quote_title = str(parsed.get("quoteTitle") or "")
        quote_content = str(parsed.get("quoteContent") or "")
        amount = str(parsed.get("amount") or "")
        cover_url = str(parsed.get("coverUrl") or "")
        thumb_url = str(parsed.get("thumbUrl") or "")
        file_size = str(parsed.get("size") or "")
        pay_sub_type = str(parsed.get("paySubType") or "")
        file_md5 = str(parsed.get("fileMd5") or "")
        transfer_id = str(parsed.get("transferId") or "")

        if render_type == "transfer":
            if not transfer_id:
                transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
            transfer_status = _infer_transfer_status_text(
                is_sent=is_sent,
                paysubtype=pay_sub_type,
                receivestatus=str(parsed.get("receiveStatus") or ""),
                sendertitle=str(parsed.get("senderTitle") or ""),
                receivertitle=str(parsed.get("receiverTitle") or ""),
                senderdes=str(parsed.get("senderDes") or ""),
                receiverdes=str(parsed.get("receiverDes") or ""),
            )
            if not content_text:
                content_text = transfer_status or "转账"
    elif local_type == 266287972401:
        render_type = "system"
        template = _extract_xml_tag_text(raw_text, "template")
        content_text = "[拍一拍]" if template else "[拍一拍]"
    elif local_type == 244813135921:
        render_type = "quote"
        parsed = _parse_app_message(raw_text)
        content_text = str(parsed.get("content") or "[引用消息]")
        quote_title = str(parsed.get("quoteTitle") or "")
        quote_content = str(parsed.get("quoteContent") or "")
    elif local_type == 3:
        render_type = "image"
        image_md5 = _extract_xml_attr(raw_text, "md5") or _extract_xml_tag_text(raw_text, "md5")
        if not image_md5:
            for k in [
                "cdnthumbmd5",
                "cdnthumd5",
                "cdnmidimgmd5",
                "cdnbigimgmd5",
                "hdmd5",
                "hevc_mid_md5",
                "hevc_md5",
                "imgmd5",
                "filemd5",
            ]:
                image_md5 = _extract_xml_attr(raw_text, k) or _extract_xml_tag_text(raw_text, k)
                if image_md5:
                    break

        _cdn_url_or_id = (
            _extract_xml_attr(raw_text, "cdnthumburl")
            or _extract_xml_attr(raw_text, "cdnthumurl")
            or _extract_xml_attr(raw_text, "cdnmidimgurl")
            or _extract_xml_attr(raw_text, "cdnbigimgurl")
            or _extract_xml_tag_text(raw_text, "cdnthumburl")
            or _extract_xml_tag_text(raw_text, "cdnthumurl")
            or _extract_xml_tag_text(raw_text, "cdnmidimgurl")
            or _extract_xml_tag_text(raw_text, "cdnbigimgurl")
        )
        _cdn_url_or_id = str(_cdn_url_or_id or "").strip()
        image_url = _cdn_url_or_id if _cdn_url_or_id.startswith(("http://", "https://")) else ""
        if (not image_url) and _cdn_url_or_id:
            image_file_id = _cdn_url_or_id

        if (not image_md5) and resource_conn is not None:
            image_md5 = _lookup_resource_md5(
                resource_conn,
                resource_chat_id,
                message_local_type=local_type,
                server_id=int(row.server_id or 0),
                local_id=int(row.local_id or 0),
                create_time=int(row.create_time or 0),
            )
        content_text = "[图片]"
    elif local_type == 34:
        render_type = "voice"
        duration = _extract_xml_attr(raw_text, "voicelength")
        voice_length = duration
        content_text = f"[语音 {duration}秒]" if duration else "[语音]"
    elif local_type == 43 or local_type == 62:
        render_type = "video"
        video_md5 = _extract_xml_attr(raw_text, "md5")
        video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
        video_thumb_url_or_id = _extract_xml_attr(raw_text, "cdnthumburl") or _extract_xml_tag_text(
            raw_text, "cdnthumburl"
        )
        video_url_or_id = _extract_xml_attr(raw_text, "cdnvideourl") or _extract_xml_tag_text(
            raw_text, "cdnvideourl"
        )

        video_thumb_url = (
            video_thumb_url_or_id
            if str(video_thumb_url_or_id or "").strip().lower().startswith(("http://", "https://"))
            else ""
        )
        video_url = (
            video_url_or_id if str(video_url_or_id or "").strip().lower().startswith(("http://", "https://")) else ""
        )
        video_thumb_file_id = "" if video_thumb_url else (str(video_thumb_url_or_id or "").strip() or "")
        video_file_id = "" if video_url else (str(video_url_or_id or "").strip() or "")
        if (not video_thumb_md5) and resource_conn is not None:
            video_thumb_md5 = _lookup_resource_md5(
                resource_conn,
                resource_chat_id,
                message_local_type=local_type,
                server_id=int(row.server_id or 0),
                local_id=int(row.local_id or 0),
                create_time=int(row.create_time or 0),
            )
        content_text = "[视频]"
    elif local_type == 47:
        render_type = "emoji"
        emoji_md5 = _extract_xml_attr(raw_text, "md5")
        if not emoji_md5:
            emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
        emoji_url = _extract_xml_attr(raw_text, "cdnurl")
        if not emoji_url:
            emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
        if (not emoji_md5) and resource_conn is not None:
            emoji_md5 = _lookup_resource_md5(
                resource_conn,
                resource_chat_id,
                message_local_type=local_type,
                server_id=int(row.server_id or 0),
                local_id=int(row.local_id or 0),
                create_time=int(row.create_time or 0),
            )
        content_text = "[表情]"
    elif local_type == 50:
        render_type = "voip"
        try:
            import re as _re

            block = raw_text
            m_voip = _re.search(
                r"(<VoIPBubbleMsg[^>]*>.*?</VoIPBubbleMsg>)",
                raw_text,
                flags=_re.IGNORECASE | _re.DOTALL,
            )
            if m_voip:
                block = m_voip.group(1) or raw_text
            room_type = str(_extract_xml_tag_text(block, "room_type") or "").strip()
            if room_type == "0":
                voip_type = "video"
            elif room_type == "1":
                voip_type = "audio"

            voip_msg = str(_extract_xml_tag_text(block, "msg") or "").strip()
            content_text = voip_msg or "通话"
        except Exception:
            content_text = "通话"
    elif local_type != 1:
        if not content_text:
            content_text = _infer_message_brief_by_local_type(local_type)
        else:
            if content_text.startswith("<") or content_text.startswith('"<'):
                if "<appmsg" in content_text.lower():
                    parsed = _parse_app_message(content_text)
                    rt = str(parsed.get("renderType") or "")
                    if rt and rt != "text":
                        render_type = rt
                        content_text = str(parsed.get("content") or content_text)
                        title = str(parsed.get("title") or title)
                        url = str(parsed.get("url") or url)
                        quote_title = str(parsed.get("quoteTitle") or quote_title)
                        quote_content = str(parsed.get("quoteContent") or quote_content)
                        amount = str(parsed.get("amount") or amount)
                        cover_url = str(parsed.get("coverUrl") or cover_url)
                        thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                        file_size = str(parsed.get("size") or file_size)
                        pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                        file_md5 = str(parsed.get("fileMd5") or file_md5)
                        transfer_id = str(parsed.get("transferId") or transfer_id)

                        if render_type == "transfer":
                            if not transfer_id:
                                transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
                            transfer_status = _infer_transfer_status_text(
                                is_sent=is_sent,
                                paysubtype=pay_sub_type,
                                receivestatus=str(parsed.get("receiveStatus") or ""),
                                sendertitle=str(parsed.get("senderTitle") or ""),
                                receivertitle=str(parsed.get("receiverTitle") or ""),
                                senderdes=str(parsed.get("senderDes") or ""),
                                receiverdes=str(parsed.get("receiverDes") or ""),
                            )
                            if not content_text:
                                content_text = transfer_status or "转账"
                t = _extract_xml_tag_text(content_text, "title")
                d = _extract_xml_tag_text(content_text, "des")
                content_text = t or d or _infer_message_brief_by_local_type(local_type)

    if not content_text:
        content_text = _infer_message_brief_by_local_type(local_type)

    if local_type == 266287972401:
        try:
            if raw_text:
                content_text = _parse_pat_message(raw_text, {})
        except Exception:
            pass

    return {
        "id": f"{row.db_stem}:{row.table_name}:{row.local_id}",
        "localId": row.local_id,
        "serverId": row.server_id,
        "createTime": row.create_time,
        "createTimeText": _format_ts(row.create_time),
        "sortSeq": row.sort_seq,
        "type": local_type,
        "renderType": render_type,
        "isSent": bool(is_sent),
        "senderUsername": row.sender_username,
        "conversationUsername": conv_username,
        "isGroup": bool(is_group),
        "content": content_text,
        "title": title,
        "url": url,
        "thumbUrl": thumb_url,
        "imageMd5": image_md5,
        "imageFileId": image_file_id,
        "imageUrl": image_url,
        "emojiMd5": emoji_md5,
        "emojiUrl": emoji_url,
        "videoMd5": video_md5,
        "videoThumbMd5": video_thumb_md5,
        "videoFileId": video_file_id,
        "videoThumbFileId": video_thumb_file_id,
        "videoUrl": video_url,
        "videoThumbUrl": video_thumb_url,
        "voiceLength": voice_length,
        "quoteTitle": quote_title,
        "quoteContent": quote_content,
        "amount": amount,
        "coverUrl": cover_url,
        "fileSize": file_size,
        "fileMd5": file_md5,
        "paySubType": pay_sub_type,
        "transferStatus": transfer_status,
        "transferId": transfer_id,
        "voipType": voip_type,
    }


def _write_conversation_json(
    *,
    zf: zipfile.ZipFile,
    conv_dir: str,
    account_dir: Path,
    conv_username: str,
    conv_name: str,
    conv_avatar_path: str,
    conv_is_group: bool,
    start_time: Optional[int],
    end_time: Optional[int],
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    head_image_conn: Optional[sqlite3.Connection],
    resolve_display_name: Any,
    privacy_mode: bool,
    include_media: bool,
    media_kinds: list[MediaKind],
    media_written: dict[str, str],
    avatar_written: dict[str, str],
    report: dict[str, Any],
    allow_process_key_extract: bool,
    media_db_path: Path,
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.json"
    exported = 0

    with zf.open(arcname, "w") as fp:
        tw = io.TextIOWrapper(fp, encoding="utf-8", newline="\n")
        tw.write("{\n")
        tw.write("  \"schemaVersion\": 1,\n")
        tw.write(f"  \"exportedAt\": {json.dumps(_now_iso(), ensure_ascii=False)},\n")
        tw.write(f"  \"account\": {json.dumps('hidden' if privacy_mode else account_dir.name, ensure_ascii=False)},\n")
        tw.write(
            "  \"conversation\": "
            + json.dumps(
                {
                    "username": "" if privacy_mode else conv_username,
                    "displayName": "已隐藏" if privacy_mode else conv_name,
                    "avatarPath": "" if privacy_mode else (conv_avatar_path or ""),
                    "isGroup": bool(conv_is_group),
                },
                ensure_ascii=False,
            )
            + ",\n"
        )
        tw.write(
            "  \"filters\": "
            + json.dumps(
                {"startTime": int(start_time) if start_time else None, "endTime": int(end_time) if end_time else None},
                ensure_ascii=False,
            )
            + ",\n"
        )
        tw.write("  \"messages\": [\n")

        sender_alias_map: dict[str, int] = {}
        first = True
        for row in _iter_rows_for_conversation(
            account_dir=account_dir,
            conv_username=conv_username,
            start_time=start_time,
            end_time=end_time,
        ):
            msg = _parse_message_for_export(
                row=row,
                conv_username=conv_username,
                is_group=conv_is_group,
                resource_conn=resource_conn,
                resource_chat_id=resource_chat_id,
            )
            su = str(msg.get("senderUsername") or "").strip()
            if privacy_mode:
                _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
            else:
                msg["senderDisplayName"] = resolve_display_name(su) if su else ""
                msg["senderAvatarPath"] = (
                    _materialize_avatar(
                        zf=zf,
                        head_image_conn=head_image_conn,
                        username=su,
                        avatar_written=avatar_written,
                    )
                    if (su and head_image_conn is not None)
                    else ""
                )

            if include_media:
                _attach_offline_media(
                    zf=zf,
                    account_dir=account_dir,
                    conv_username=conv_username,
                    msg=msg,
                    media_written=media_written,
                    report=report,
                    media_kinds=media_kinds,
                    allow_process_key_extract=allow_process_key_extract,
                    media_db_path=media_db_path,
                    lock=lock,
                    job=job,
                )

            if not first:
                tw.write(",\n")
            tw.write("    " + json.dumps(msg, ensure_ascii=False))
            first = False

            exported += 1
            with lock:
                job.progress.messages_exported += 1
                job.progress.current_conversation_messages_exported = exported

            if exported % 200 == 0 and job.cancel_requested:
                raise _JobCancelled()

        tw.write("\n  ]\n")
        tw.write("}\n")
        tw.flush()
    return exported


def _write_conversation_txt(
    *,
    zf: zipfile.ZipFile,
    conv_dir: str,
    account_dir: Path,
    conv_username: str,
    conv_name: str,
    conv_avatar_path: str,
    conv_is_group: bool,
    start_time: Optional[int],
    end_time: Optional[int],
    resource_conn: Optional[sqlite3.Connection],
    resource_chat_id: Optional[int],
    head_image_conn: Optional[sqlite3.Connection],
    resolve_display_name: Any,
    privacy_mode: bool,
    include_media: bool,
    media_kinds: list[MediaKind],
    media_written: dict[str, str],
    avatar_written: dict[str, str],
    report: dict[str, Any],
    allow_process_key_extract: bool,
    media_db_path: Path,
    job: ExportJob,
    lock: threading.Lock,
) -> int:
    arcname = f"{conv_dir}/messages.txt"
    exported = 0

    with zf.open(arcname, "w") as fp:
        tw = io.TextIOWrapper(fp, encoding="utf-8", newline="\n")
        if privacy_mode:
            tw.write("会话: 已隐藏\n")
            tw.write("账号: hidden\n")
        else:
            tw.write(f"会话: {conv_name} ({conv_username})\n")
            tw.write(f"账号: {account_dir.name}\n")
            if conv_avatar_path:
                tw.write(f"会话头像: {conv_avatar_path}\n")
        if start_time or end_time:
            st = _format_ts(int(start_time)) if start_time else "不限"
            et = _format_ts(int(end_time)) if end_time else "不限"
            tw.write(f"时间范围: {st} ~ {et}\n")
        tw.write(f"导出时间: {_now_iso()}\n")
        tw.write("\n")

        sender_alias_map: dict[str, int] = {}
        for row in _iter_rows_for_conversation(
            account_dir=account_dir,
            conv_username=conv_username,
            start_time=start_time,
            end_time=end_time,
        ):
            msg = _parse_message_for_export(
                row=row,
                conv_username=conv_username,
                is_group=conv_is_group,
                resource_conn=resource_conn,
                resource_chat_id=resource_chat_id,
            )
            su = str(msg.get("senderUsername") or "").strip()
            if privacy_mode:
                _privacy_scrub_message(msg, conv_is_group=conv_is_group, sender_alias_map=sender_alias_map)
            else:
                msg["senderDisplayName"] = resolve_display_name(su) if su else ""
                msg["senderAvatarPath"] = (
                    _materialize_avatar(
                        zf=zf,
                        head_image_conn=head_image_conn,
                        username=su,
                        avatar_written=avatar_written,
                    )
                    if (su and head_image_conn is not None)
                    else ""
                )

            if include_media:
                _attach_offline_media(
                    zf=zf,
                    account_dir=account_dir,
                    conv_username=conv_username,
                    msg=msg,
                    media_written=media_written,
                    report=report,
                    media_kinds=media_kinds,
                    allow_process_key_extract=allow_process_key_extract,
                    media_db_path=media_db_path,
                    lock=lock,
                    job=job,
                )

            tw.write(_format_message_line_txt(msg=msg) + "\n")

            exported += 1
            with lock:
                job.progress.messages_exported += 1
                job.progress.current_conversation_messages_exported = exported

            if exported % 200 == 0 and job.cancel_requested:
                raise _JobCancelled()

        tw.flush()
    return exported


def _format_message_line_txt(*, msg: dict[str, Any]) -> str:
    ts = int(msg.get("createTime") or 0)
    time_text = _format_ts(ts)
    sender_username = str(msg.get("senderUsername") or "").strip()
    sender_display = str(msg.get("senderDisplayName") or "").strip()
    if sender_display and sender_username:
        sender = f"{sender_display}({sender_username})"
    else:
        sender = sender_display or sender_username or "未知"

    avatar_path = str(msg.get("senderAvatarPath") or "").strip()
    if avatar_path:
        sender = f"{sender} [avatar={avatar_path}]"

    rt = str(msg.get("renderType") or "text")
    content = str(msg.get("content") or "").strip()
    extra = ""
    if rt == "link":
        title = str(msg.get("title") or "").strip()
        url = str(msg.get("url") or "").strip()
        extra = f" {title} {url}".strip()
    elif rt == "transfer":
        amt = str(msg.get("amount") or "").strip()
        st = str(msg.get("transferStatus") or "").strip()
        extra = f" 金额={amt} 状态={st}".strip()
    elif rt == "file":
        title = str(msg.get("title") or "").strip()
        sz = str(msg.get("fileSize") or "").strip()
        extra = f" {title} size={sz}".strip()

    media = msg.get("offlineMedia") or []
    media_desc = ""
    if isinstance(media, list) and media:
        paths: list[str] = []
        for m in media:
            try:
                p = str(m.get("path") or "").strip()
            except Exception:
                p = ""
            if p:
                paths.append(p)
        if paths:
            media_desc = " " + " ".join(paths)

    if rt == "system":
        return f"[{time_text}] [系统] {content}".rstrip()

    return f"[{time_text}] {sender}: {content}{extra}{media_desc}".rstrip()


def _privacy_scrub_message(
    msg: dict[str, Any],
    *,
    conv_is_group: bool,
    sender_alias_map: dict[str, int],
) -> None:
    sender_username = str(msg.get("senderUsername") or "").strip()
    is_sent = bool(msg.get("isSent"))

    if is_sent:
        alias = "我"
        pseudo_username = "me"
    else:
        if not conv_is_group:
            alias = "对方"
            pseudo_username = "other"
        else:
            idx = sender_alias_map.get(sender_username)
            if idx is None:
                idx = len(sender_alias_map) + 1
                sender_alias_map[sender_username] = idx
            alias = f"成员#{idx}"
            pseudo_username = f"member_{idx}"

    rt = str(msg.get("renderType") or "text").strip() or "text"
    content_map = {
        "text": "[文本]",
        "system": "[系统消息]",
        "image": "[图片]",
        "emoji": "[表情]",
        "video": "[视频]",
        "voice": "[语音]",
        "link": "[链接]",
        "file": "[文件]",
        "transfer": "[转账]",
        "redPacket": "[红包]",
        "quote": "[引用消息]",
        "voip": "[通话]",
    }
    msg["content"] = content_map.get(rt, f"[{rt}]")

    msg["senderDisplayName"] = alias
    msg["senderUsername"] = pseudo_username
    msg["senderAvatarPath"] = ""
    msg["conversationUsername"] = ""

    # Remove potentially sensitive payload fields.
    for k in (
        "title",
        "url",
        "thumbUrl",
        "imageMd5",
        "imageFileId",
        "imageUrl",
        "emojiMd5",
        "emojiUrl",
        "videoMd5",
        "videoThumbMd5",
        "videoFileId",
        "videoThumbFileId",
        "videoUrl",
        "videoThumbUrl",
        "voiceLength",
        "quoteTitle",
        "quoteContent",
        "amount",
        "coverUrl",
        "fileSize",
        "fileMd5",
        "paySubType",
        "transferStatus",
        "transferId",
        "voipType",
    ):
        if k in msg:
            msg[k] = ""

    msg.pop("offlineMedia", None)


def _attach_offline_media(
    *,
    zf: zipfile.ZipFile,
    account_dir: Path,
    conv_username: str,
    msg: dict[str, Any],
    media_written: dict[str, str],
    report: dict[str, Any],
    media_kinds: list[MediaKind],
    allow_process_key_extract: bool,
    media_db_path: Path,
    lock: threading.Lock,
    job: ExportJob,
) -> None:
    # allow_process_key_extract is reserved for future: try to decrypt missing media using process memory keys
    _ = allow_process_key_extract

    rt = str(msg.get("renderType") or "")

    def record_missing(kind: str, ident: str) -> None:
        with lock:
            job.progress.media_missing += 1
        try:
            report["missingMedia"].append(
                {
                    "kind": kind,
                    "id": ident,
                    "conversation": conv_username,
                    "messageId": msg.get("id"),
                }
            )
        except Exception:
            pass

    offline: list[dict[str, Any]] = []

    if rt == "image" and "image" in media_kinds:
        md5 = str(msg.get("imageMd5") or "").strip().lower()
        file_id = str(msg.get("imageFileId") or "").strip()
        arc, is_new = _materialize_media(
            zf=zf,
            account_dir=account_dir,
            conv_username=conv_username,
            kind="image",
            md5=md5 if _is_md5(md5) else "",
            file_id=file_id,
            media_written=media_written,
            suggested_name="",
        )
        if arc:
            offline.append({"kind": "image", "path": arc, "md5": md5, "fileId": file_id})
            if is_new:
                with lock:
                    job.progress.media_copied += 1
        else:
            record_missing("image", md5 or file_id)

    if rt == "emoji" and "emoji" in media_kinds:
        md5 = str(msg.get("emojiMd5") or "").strip().lower()
        arc, is_new = _materialize_media(
            zf=zf,
            account_dir=account_dir,
            conv_username=conv_username,
            kind="emoji",
            md5=md5 if _is_md5(md5) else "",
            file_id="",
            media_written=media_written,
            suggested_name="",
        )
        if arc:
            offline.append({"kind": "emoji", "path": arc, "md5": md5})
            if is_new:
                with lock:
                    job.progress.media_copied += 1
        else:
            record_missing("emoji", md5)

    if rt == "video":
        if "video_thumb" in media_kinds:
            md5 = str(msg.get("videoThumbMd5") or "").strip().lower()
            file_id = str(msg.get("videoThumbFileId") or "").strip()
            arc, is_new = _materialize_media(
                zf=zf,
                account_dir=account_dir,
                conv_username=conv_username,
                kind="video_thumb",
                md5=md5 if _is_md5(md5) else "",
                file_id=file_id,
                media_written=media_written,
                suggested_name="",
            )
            if arc:
                offline.append({"kind": "video_thumb", "path": arc, "md5": md5, "fileId": file_id})
                if is_new:
                    with lock:
                        job.progress.media_copied += 1
            else:
                record_missing("video_thumb", md5 or file_id)

        if "video" in media_kinds:
            md5 = str(msg.get("videoMd5") or "").strip().lower()
            file_id = str(msg.get("videoFileId") or "").strip()
            arc, is_new = _materialize_media(
                zf=zf,
                account_dir=account_dir,
                conv_username=conv_username,
                kind="video",
                md5=md5 if _is_md5(md5) else "",
                file_id=file_id,
                media_written=media_written,
                suggested_name="",
            )
            if arc:
                offline.append({"kind": "video", "path": arc, "md5": md5, "fileId": file_id})
                if is_new:
                    with lock:
                        job.progress.media_copied += 1
            else:
                record_missing("video", md5 or file_id)

    if rt == "voice" and "voice" in media_kinds:
        server_id = int(msg.get("serverId") or 0)
        if server_id > 0:
            arc, is_new = _materialize_voice(
                zf=zf,
                media_db_path=media_db_path,
                server_id=server_id,
                media_written=media_written,
            )
            if arc:
                offline.append({"kind": "voice", "path": arc, "serverId": server_id})
                if is_new:
                    with lock:
                        job.progress.media_copied += 1
            else:
                record_missing("voice", str(server_id))

    if rt == "file" and "file" in media_kinds:
        md5 = str(msg.get("fileMd5") or "").strip().lower()
        arc, is_new = _materialize_media(
            zf=zf,
            account_dir=account_dir,
            conv_username=conv_username,
            kind="file",
            md5=md5 if _is_md5(md5) else "",
            file_id="",
            media_written=media_written,
            suggested_name=str(msg.get("title") or "").strip(),
        )
        if arc:
            offline.append({"kind": "file", "path": arc, "md5": md5, "title": str(msg.get("title") or "").strip()})
            if is_new:
                with lock:
                    job.progress.media_copied += 1
        else:
            record_missing("file", md5)

    if offline:
        msg["offlineMedia"] = offline


def _materialize_avatar(
    *,
    zf: zipfile.ZipFile,
    head_image_conn: Optional[sqlite3.Connection],
    username: str,
    avatar_written: dict[str, str],
) -> str:
    u = str(username or "").strip()
    if not u or head_image_conn is None:
        return ""

    key = f"avatar:{u}"
    if key in avatar_written:
        return avatar_written[key]

    try:
        row = head_image_conn.execute(
            "SELECT image_buffer FROM head_image WHERE username = ? ORDER BY update_time DESC LIMIT 1",
            (u,),
        ).fetchone()
    except Exception:
        row = None

    if not row or row[0] is None:
        avatar_written[key] = ""
        return ""

    data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)
    if not data:
        avatar_written[key] = ""
        return ""

    mt = _detect_image_media_type(data[:32])
    ext = "dat"
    if mt == "image/png":
        ext = "png"
    elif mt == "image/jpeg":
        ext = "jpg"
    elif mt == "image/gif":
        ext = "gif"
    elif mt == "image/webp":
        ext = "webp"

    safe = _safe_name(u, max_len=50) or "avatar"
    h = uuid.uuid5(uuid.NAMESPACE_DNS, u).hex[:8]
    arc = f"media/avatars/{safe}_{h}.{ext}"
    if len(arc) > 220:
        arc = f"media/avatars/avatar_{h}.{ext}"

    try:
        zf.writestr(arc, data)
    except Exception:
        avatar_written[key] = ""
        return ""

    avatar_written[key] = arc
    return arc


def _materialize_voice(
    *,
    zf: zipfile.ZipFile,
    media_db_path: Path,
    server_id: int,
    media_written: dict[str, str],
) -> tuple[str, bool]:
    key = f"voice:{int(server_id)}"
    existing = media_written.get(key)
    if existing:
        return existing, False

    if not media_db_path.exists():
        return "", False

    conn = sqlite3.connect(str(media_db_path))
    try:
        row = conn.execute(
            "SELECT voice_data FROM VoiceInfo WHERE svr_id = ? ORDER BY create_time DESC LIMIT 1",
            (int(server_id),),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row or row[0] is None:
        return "", False

    data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)

    wav = _convert_silk_to_wav(data)
    if wav != data and wav[:4] == b"RIFF":
        ext = "wav"
        payload = wav
    else:
        ext = "silk"
        payload = data

    arc = f"media/voices/voice_{int(server_id)}.{ext}"
    zf.writestr(arc, payload)
    media_written[key] = arc
    return arc, True


def _materialize_media(
    *,
    zf: zipfile.ZipFile,
    account_dir: Path,
    conv_username: str,
    kind: MediaKind,
    md5: str,
    file_id: str,
    media_written: dict[str, str],
    suggested_name: str,
) -> tuple[str, bool]:
    ident = md5 or file_id
    if not ident:
        return "", False

    key = f"{kind}:{ident}"
    existing = media_written.get(key)
    if existing:
        return existing, False

    src: Optional[Path] = None
    if md5 and _is_md5(md5):
        try:
            src = _try_find_decrypted_resource(account_dir, md5)
        except Exception:
            src = None

        if src is None:
            try:
                src = _resolve_media_path_for_kind(account_dir, kind=kind, md5=md5, username=conv_username)
            except Exception:
                src = None

    if src is None and file_id:
        try:
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            for r in [wxid_dir, db_storage_dir]:
                if not r:
                    continue
                hit = _fallback_search_media_by_file_id(
                    str(r),
                    str(file_id),
                    kind=str(kind),
                    username=str(conv_username or ""),
                )
                if hit:
                    src = Path(hit)
                    break
        except Exception:
            src = None

    if not src:
        return "", False

    try:
        if not src.exists() or (not src.is_file()):
            return "", False
    except Exception:
        return "", False

    ext = src.suffix.lstrip(".").lower()
    if not ext:
        try:
            head = src.read_bytes()[:32]
        except Exception:
            head = b""
        mt = _detect_image_media_type(head)
        if mt.startswith("image/"):
            ext = mt.split("/", 1)[-1]
        elif len(head) >= 8 and head[4:8] == b"ftyp":
            ext = "mp4"
        else:
            ext = "dat"

    folder = "misc"
    if kind == "image":
        folder = "images"
    elif kind == "emoji":
        folder = "emojis"
    elif kind == "video":
        folder = "videos"
    elif kind == "video_thumb":
        folder = "video_thumbs"
    elif kind == "file":
        folder = "files"

    nice = _safe_name(suggested_name, max_len=60)
    if nice and kind == "file":
        arc_name = f"{nice}_{ident}.{ext}" if ext else f"{nice}_{ident}"
    else:
        arc_name = f"{ident}.{ext}" if ext else ident
    if len(arc_name) > 160:
        arc_name = arc_name[:160]

    arc = f"media/{folder}/{arc_name}"
    try:
        zf.write(src, arcname=arc)
    except Exception:
        return "", False

    media_written[key] = arc
    return arc, True


CHAT_EXPORT_MANAGER = ChatExportManager()
