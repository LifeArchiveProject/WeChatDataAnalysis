from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Protocol

from .account_identity import resolve_account_self_username
from .account_source_policy import account_prefers_decrypted_snapshot
from .chat_helpers import _extract_voice_transcript_from_packed_info
from .voice_transcription import _numbered_db_shards


_MAX_WECHAT_SERVER_ID = (1 << 64) - 1
_MAX_WECHAT_LOCAL_ID = (1 << 32) - 1
_POSITIVE_DECIMAL_ID = re.compile(r"^[1-9][0-9]*$")
_TRIGGER_RECEIPT_STATUSES = frozenset({"accepted", "pending"})
_NATIVE_TRANSCRIPT_CACHE_LOCK = threading.RLock()
_NATIVE_TRANSCRIPT_PENDING_TTL_SECONDS = 120.0
_NATIVE_TRANSCRIPT_ERROR_TTL_SECONDS = 300.0
_MAX_NATIVE_TRANSCRIPT_BYTES = 64 * 1024
_MAX_NATIVE_REQUEST_ID_BYTES = 256
_MAX_NATIVE_ERROR_CODE_BYTES = 128
_MAX_NATIVE_ERROR_MESSAGE_BYTES = 2048


class NativeVoiceTriggerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "native_trigger_failed")
        self.user_message = str(message or "微信原生语音转写触发失败。")


@dataclass(frozen=True)
class NativeVoiceTriggerCommand:
    account_dir: Path
    account: str
    conversation: str
    server_id: int
    local_id: int = 0


@dataclass(frozen=True)
class NativeVoiceTriggerReceipt:
    status: Literal["accepted", "pending"]
    request_id: str = ""


@dataclass(frozen=True)
class NativeVoiceTranscriptCacheEntry:
    account_dir: Path
    conversation: str
    server_id: int
    local_id: int
    status: Literal["pending", "success", "error"]
    request_id: str
    text: str
    error_code: str
    error_message: str
    updated_at: float
    expires_at: Optional[float]


class NativeVoiceTriggerTransport(Protocol):
    def trigger(self, command: NativeVoiceTriggerCommand) -> NativeVoiceTriggerReceipt:
        """Dispatch one bounded request; transcript polling belongs to the caller."""


class UnavailableNativeVoiceTriggerTransport:
    """Fail closed until the version-locked Win32 bridge is wired in."""

    def trigger(self, _command: NativeVoiceTriggerCommand) -> NativeVoiceTriggerReceipt:
        raise NativeVoiceTriggerError(
            "native_transport_unavailable",
            "微信原生语音转写桥接尚未接入当前构建。",
        )


_UNAVAILABLE_TRANSPORT = UnavailableNativeVoiceTriggerTransport()


def get_native_voice_trigger_transport() -> NativeVoiceTriggerTransport:
    try:
        from .native_core_voice_asr import build_native_core_voice_asr_transport

        transport = build_native_core_voice_asr_transport()
        if transport is not None:
            return transport
    except Exception:
        # Artifact discovery is intentionally fail-closed; trigger-time errors
        # are surfaced by the real transport as NativeVoiceTriggerError.
        pass
    return _UNAVAILABLE_TRANSPORT


def parse_native_voice_message_id(value: Optional[str], field_name: str) -> int:
    """Parse an exact decimal string without accepting JSON numbers or coercion."""

    if value is None:
        return 0
    if not isinstance(value, str) or not _POSITIVE_DECIMAL_ID.fullmatch(value):
        raise NativeVoiceTriggerError(
            "invalid_message_id",
            f"{field_name} 必须是正整数十进制字符串。",
        )
    parsed = int(value)
    maximum = _MAX_WECHAT_LOCAL_ID if field_name == "local_id" else _MAX_WECHAT_SERVER_ID
    if parsed > maximum:
        raise NativeVoiceTriggerError(
            "invalid_message_id",
            f"{field_name} 超出微信消息 ID 范围。",
        )
    return parsed


def normalize_native_voice_conversation(value: str) -> str:
    if not isinstance(value, str):
        raise NativeVoiceTriggerError("invalid_conversation", "username 必须是字符串。")
    conversation = value.strip()
    if not conversation:
        raise NativeVoiceTriggerError("invalid_conversation", "缺少 username。")
    if "\x00" in conversation or len(conversation.encode("utf-8")) > 1024:
        raise NativeVoiceTriggerError("invalid_conversation", "username 格式无效。")
    return conversation


def _native_voice_cache_path(account_dir: Path) -> Path:
    return Path(account_dir) / "_cache" / "native_voice_transcripts.sqlite3"


def _native_voice_cache_account_key(account_dir: Path) -> str:
    try:
        path = str(Path(account_dir).resolve(strict=False))
    except OSError:
        path = str(Path(account_dir).absolute())
    return os.path.normcase(path)


def _normalize_native_cache_id(value: int, *, field_name: str, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    minimum = 0 if allow_zero else 1
    maximum = _MAX_WECHAT_LOCAL_ID if field_name == "local_id" else _MAX_WECHAT_SERVER_ID
    if not minimum <= value <= maximum:
        raise ValueError(f"{field_name} is outside the WeChat message ID range")
    return value


def _normalize_native_cache_string(
    value: str,
    *,
    field_name: str,
    maximum_bytes: int,
    required: bool,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if "\x00" in normalized:
        raise ValueError(f"{field_name} contains a NUL character")
    if required and not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field_name} is too large")
    return normalized


def _normalize_native_request_id(value: str) -> str:
    normalized = _normalize_native_cache_string(
        value,
        field_name="request_id",
        maximum_bytes=_MAX_NATIVE_REQUEST_ID_BYTES,
        required=True,
    )
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in normalized):
        raise ValueError("request_id contains a control character")
    return normalized


def _normalize_native_transcript_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("text must be a string")
    return _normalize_native_cache_string(
        value.replace("\r\n", "\n").replace("\r", "\n"),
        field_name="text",
        maximum_bytes=_MAX_NATIVE_TRANSCRIPT_BYTES,
        required=True,
    )


def _native_voice_cache_expiry(updated_at: float, ttl_seconds: Optional[float]) -> Optional[float]:
    if ttl_seconds is None:
        return None
    ttl = float(ttl_seconds)
    if not math.isfinite(ttl) or ttl <= 0:
        raise ValueError("ttl_seconds must be a positive finite number")
    return updated_at + ttl


def _open_native_voice_cache(account_dir: Path, *, create: bool) -> Optional[sqlite3.Connection]:
    cache_path = _native_voice_cache_path(account_dir)
    if not create and not cache_path.is_file():
        return None
    if create:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cache_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    if create:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS native_voice_transcript (
                account_key TEXT NOT NULL,
                conversation TEXT NOT NULL,
                server_id TEXT NOT NULL,
                local_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'success', 'error')),
                request_id TEXT NOT NULL,
                text TEXT NOT NULL,
                error_code TEXT NOT NULL,
                error_message TEXT NOT NULL,
                updated_at REAL NOT NULL,
                expires_at REAL,
                PRIMARY KEY (account_key, conversation, server_id, local_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS native_voice_transcript_server_idx "
            "ON native_voice_transcript (account_key, server_id, updated_at DESC)"
        )
        conn.commit()
    return conn


def _native_voice_cache_entry_from_row(
    account_dir: Path,
    row: sqlite3.Row,
) -> NativeVoiceTranscriptCacheEntry:
    expires_at = row["expires_at"]
    return NativeVoiceTranscriptCacheEntry(
        account_dir=Path(account_dir),
        conversation=str(row["conversation"]),
        server_id=int(row["server_id"]),
        local_id=int(row["local_id"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        request_id=str(row["request_id"]),
        text=str(row["text"]),
        error_code=str(row["error_code"]),
        error_message=str(row["error_message"]),
        updated_at=float(row["updated_at"]),
        expires_at=float(expires_at) if expires_at is not None else None,
    )


def _write_native_voice_transcript_cache(
    *,
    account_dir: Path,
    conversation: str,
    server_id: int,
    local_id: int,
    status: Literal["pending", "success", "error"],
    request_id: str,
    text: str = "",
    error_code: str = "",
    error_message: str = "",
    ttl_seconds: Optional[float],
) -> NativeVoiceTranscriptCacheEntry:
    account_path = Path(account_dir)
    account_key = _native_voice_cache_account_key(account_path)
    resolved_conversation = normalize_native_voice_conversation(conversation)
    resolved_server_id = _normalize_native_cache_id(
        server_id,
        field_name="server_id",
        allow_zero=False,
    )
    resolved_local_id = _normalize_native_cache_id(
        local_id,
        field_name="local_id",
        allow_zero=True,
    )
    resolved_request_id = _normalize_native_request_id(request_id)
    resolved_text = _normalize_native_transcript_text(text) if status == "success" else ""
    resolved_error_code = (
        _normalize_native_cache_string(
            error_code,
            field_name="error_code",
            maximum_bytes=_MAX_NATIVE_ERROR_CODE_BYTES,
            required=True,
        )
        if status == "error"
        else ""
    )
    resolved_error_message = (
        _normalize_native_cache_string(
            error_message,
            field_name="error_message",
            maximum_bytes=_MAX_NATIVE_ERROR_MESSAGE_BYTES,
            required=False,
        )
        if status == "error"
        else ""
    )
    updated_at = time.time()
    expires_at = _native_voice_cache_expiry(updated_at, ttl_seconds)
    key_params = (
        account_key,
        resolved_conversation,
        str(resolved_server_id),
        resolved_local_id,
    )

    with _NATIVE_TRANSCRIPT_CACHE_LOCK:
        conn = _open_native_voice_cache(account_path, create=True)
        assert conn is not None
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM native_voice_transcript "
                "WHERE account_key = ? AND conversation = ? AND server_id = ? AND local_id = ?",
                key_params,
            ).fetchone()
            current = _native_voice_cache_entry_from_row(account_path, row) if row else None
            current_is_live = bool(
                current is not None
                and (current.expires_at is None or current.expires_at > updated_at)
            )

            # A synchronous callback may win the race against the caller writing
            # pending. Never downgrade a completed result, and never let a stale
            # callback overwrite a different in-flight request for the same row.
            preserve_current = bool(
                current_is_live
                and (
                    current.status == "success"
                    or (
                        status == "pending"
                        and current.status in {"pending", "error"}
                        and current.request_id == resolved_request_id
                    )
                    or (
                        status != "pending"
                        and current.request_id != resolved_request_id
                    )
                )
            )
            if preserve_current:
                conn.commit()
                assert current is not None
                return current

            conn.execute(
                """
                INSERT INTO native_voice_transcript (
                    account_key, conversation, server_id, local_id, status,
                    request_id, text, error_code, error_message, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (account_key, conversation, server_id, local_id) DO UPDATE SET
                    status = excluded.status,
                    request_id = excluded.request_id,
                    text = excluded.text,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (
                    *key_params,
                    status,
                    resolved_request_id,
                    resolved_text,
                    resolved_error_code,
                    resolved_error_message,
                    updated_at,
                    expires_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return NativeVoiceTranscriptCacheEntry(
        account_dir=account_path,
        conversation=resolved_conversation,
        server_id=resolved_server_id,
        local_id=resolved_local_id,
        status=status,
        request_id=resolved_request_id,
        text=resolved_text,
        error_code=resolved_error_code,
        error_message=resolved_error_message,
        updated_at=updated_at,
        expires_at=expires_at,
    )


def mark_native_voice_transcript_pending(
    *,
    account_dir: Path,
    conversation: str,
    server_id: int,
    local_id: int,
    request_id: str,
    ttl_seconds: float = _NATIVE_TRANSCRIPT_PENDING_TTL_SECONDS,
) -> NativeVoiceTranscriptCacheEntry:
    return _write_native_voice_transcript_cache(
        account_dir=account_dir,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
        status="pending",
        request_id=request_id,
        ttl_seconds=ttl_seconds,
    )


def mark_native_voice_transcript_success(
    *,
    account_dir: Path,
    conversation: str,
    server_id: int,
    local_id: int,
    request_id: str,
    text: str,
    ttl_seconds: Optional[float] = None,
) -> NativeVoiceTranscriptCacheEntry:
    return _write_native_voice_transcript_cache(
        account_dir=account_dir,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
        status="success",
        request_id=request_id,
        text=text,
        ttl_seconds=ttl_seconds,
    )


def mark_native_voice_transcript_error(
    *,
    account_dir: Path,
    conversation: str,
    server_id: int,
    local_id: int,
    request_id: str,
    error_code: str,
    error_message: str = "",
    ttl_seconds: float = _NATIVE_TRANSCRIPT_ERROR_TTL_SECONDS,
) -> NativeVoiceTranscriptCacheEntry:
    return _write_native_voice_transcript_cache(
        account_dir=account_dir,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
        status="error",
        request_id=request_id,
        error_code=error_code,
        error_message=error_message,
        ttl_seconds=ttl_seconds,
    )


def lookup_native_voice_transcript_cache(
    account_dir: Path,
    server_id: int,
    *,
    conversation: str = "",
    local_id: int = 0,
    request_id: str = "",
    now: Optional[float] = None,
    include_expired: bool = False,
    strict: bool = False,
) -> Optional[NativeVoiceTranscriptCacheEntry]:
    account_path = Path(account_dir)
    account_key = _native_voice_cache_account_key(account_path)
    resolved_server_id = _normalize_native_cache_id(
        server_id,
        field_name="server_id",
        allow_zero=False,
    )
    resolved_local_id = _normalize_native_cache_id(
        local_id,
        field_name="local_id",
        allow_zero=True,
    )
    resolved_conversation = (
        normalize_native_voice_conversation(conversation) if conversation else ""
    )
    resolved_request_id = (
        _normalize_native_request_id(request_id)
        if request_id
        else ""
    )
    current_time = time.time() if now is None else float(now)
    if not math.isfinite(current_time):
        raise ValueError("now must be finite")

    sql = (
        "SELECT * FROM native_voice_transcript "
        "WHERE account_key = ? AND server_id = ?"
    )
    params: list[object] = [account_key, str(resolved_server_id)]
    if not include_expired:
        sql += " AND (expires_at IS NULL OR expires_at > ?)"
        params.append(current_time)
    if resolved_conversation:
        sql += " AND conversation = ?"
        params.append(resolved_conversation)
    if resolved_local_id > 0:
        sql += " AND local_id = ?"
        params.append(resolved_local_id)
    if resolved_request_id:
        sql += " AND request_id = ?"
        params.append(resolved_request_id)
    sql += " ORDER BY updated_at DESC LIMIT 1"

    with _NATIVE_TRANSCRIPT_CACHE_LOCK:
        try:
            conn = _open_native_voice_cache(account_path, create=False)
        except (OSError, sqlite3.Error) as exc:
            if strict:
                raise NativeVoiceTriggerError(
                    "native_result_store_unavailable",
                    "微信原生语音转写结果缓存暂时不可用。",
                ) from exc
            return None
        if conn is None:
            return None
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            return _native_voice_cache_entry_from_row(account_path, row) if row else None
        except (TypeError, ValueError, sqlite3.Error) as exc:
            if strict:
                raise NativeVoiceTriggerError(
                    "native_result_store_unavailable",
                    "微信原生语音转写结果缓存暂时不可用。",
                ) from exc
            return None
        finally:
            conn.close()


def lookup_cached_native_voice_transcript(
    account_dir: Path,
    server_id: int,
    *,
    conversation: str = "",
    local_id: int = 0,
    request_id: str = "",
    strict: bool = False,
) -> str:
    entry = lookup_native_voice_transcript_cache(
        account_dir,
        server_id,
        conversation=conversation,
        local_id=local_id,
        request_id=request_id,
        strict=strict,
    )
    return entry.text if entry is not None and entry.status == "success" else ""


def _message_db_paths(root: Path, conversation: str) -> list[Path]:
    normal = _numbered_db_shards(root, "message")
    business = _numbered_db_shards(root, "biz_message")
    return (business + normal) if conversation.startswith("gh_") else (normal + business)


@dataclass
class _VoiceTargetQueryResult:
    rows: set[tuple[int, int]]
    transcripts: dict[tuple[int, int], str]
    successful_queries: int
    failures: list[str]


def _target_where_sql(*, server_id: int, local_id: int, parameterized: bool) -> tuple[str, tuple[int, ...]]:
    clauses: list[str] = []
    values: list[int] = []
    for column, value in (("server_id", server_id), ("local_id", local_id)):
        if int(value) <= 0:
            continue
        clauses.append(f"{column} = {'?' if parameterized else int(value)}")
        values.append(int(value))
    return " OR ".join(clauses), tuple(values)


def _query_local_voice_targets(
    account_dir: Path,
    *,
    conversation: str,
    server_id: int,
    local_id: int,
) -> _VoiceTargetQueryResult:
    table_name = f"Msg_{hashlib.md5(conversation.encode('utf-8')).hexdigest()}"
    quoted_table = '"' + table_name.replace('"', '""') + '"'
    targets: set[tuple[int, int]] = set()
    transcripts: dict[tuple[int, int], str] = {}
    successful_queries = 0
    failures: list[str] = []
    where_sql, params = _target_where_sql(
        server_id=server_id,
        local_id=local_id,
        parameterized=True,
    )
    for db_path in _message_db_paths(Path(account_dir), conversation):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower(?) LIMIT 1",
                (table_name,),
            ).fetchone()
            if not table_row:
                successful_queries += 1
                continue
            try:
                rows = conn.execute(
                    f"SELECT local_id, server_id, packed_info_data FROM {quoted_table} "
                    f"WHERE local_type = 34 AND ({where_sql}) LIMIT 4",
                    params,
                )
            except sqlite3.OperationalError:
                rows = conn.execute(
                    f"SELECT local_id, server_id, NULL AS packed_info_data FROM {quoted_table} "
                    f"WHERE local_type = 34 AND ({where_sql}) LIMIT 4",
                    params,
                )
            for row_local_id, row_server_id, packed_info in rows:
                target = (int(row_local_id or 0), int(row_server_id or 0))
                targets.add(target)
                text = _extract_voice_transcript_from_packed_info(packed_info)
                if text:
                    transcripts[target] = text
            successful_queries += 1
        except Exception as exc:
            failures.append(f"local:{db_path.name}:{type(exc).__name__}")
            continue
        finally:
            if conn is not None:
                conn.close()
    return _VoiceTargetQueryResult(targets, transcripts, successful_queries, failures)


def _query_realtime_voice_targets(
    account_dir: Path,
    *,
    conversation: str,
    server_id: int,
    local_id: int,
) -> _VoiceTargetQueryResult:
    targets: set[tuple[int, int]] = set()
    transcripts: dict[tuple[int, int], str] = {}
    successful_queries = 0
    failures: list[str] = []
    try:
        from .wcdb_realtime import WCDB_REALTIME, exec_query as wcdb_exec_query

        realtime = WCDB_REALTIME.ensure_connected(Path(account_dir))
        message_dir = Path(realtime.db_storage_dir) / "message"
        table_name = f"Msg_{hashlib.md5(conversation.encode('utf-8')).hexdigest()}"
        quoted_table = '"' + table_name.replace('"', '""') + '"'
        where_sql, _params = _target_where_sql(
            server_id=server_id,
            local_id=local_id,
            parameterized=False,
        )
        for db_path in _message_db_paths(message_dir, conversation):
            try:
                with realtime.lock:
                    table_rows = wcdb_exec_query(
                        realtime.handle,
                        kind="message",
                        path=str(db_path),
                        sql=(
                            "SELECT name FROM sqlite_master WHERE type='table' AND lower(name)=lower("
                            f"'{table_name}') LIMIT 1"
                        ),
                    )
                if not table_rows:
                    successful_queries += 1
                    continue
                try:
                    with realtime.lock:
                        rows = wcdb_exec_query(
                            realtime.handle,
                            kind="message",
                            path=str(db_path),
                            sql=(
                                f"SELECT local_id, server_id, packed_info_data FROM {quoted_table} "
                                f"WHERE local_type = 34 AND ({where_sql}) LIMIT 4"
                            ),
                        )
                except Exception:
                    with realtime.lock:
                        rows = wcdb_exec_query(
                            realtime.handle,
                            kind="message",
                            path=str(db_path),
                            sql=(
                                f"SELECT local_id, server_id, NULL AS packed_info_data FROM {quoted_table} "
                                f"WHERE local_type = 34 AND ({where_sql}) LIMIT 4"
                            ),
                        )
                successful_queries += 1
            except Exception as exc:
                failures.append(f"realtime:{db_path.name}:{type(exc).__name__}")
                continue
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                values = {str(key).lower(): value for key, value in row.items()}
                try:
                    target = (
                        int(values.get("local_id") or 0),
                        int(values.get("server_id") or 0),
                    )
                    targets.add(target)
                    text = _extract_voice_transcript_from_packed_info(
                        values.get("packed_info_data")
                    )
                    if text:
                        transcripts[target] = text
                except Exception:
                    continue
    except Exception as exc:
        failures.append(f"realtime:connect:{type(exc).__name__}")
    return _VoiceTargetQueryResult(targets, transcripts, successful_queries, failures)


def resolve_native_voice_target(
    account_dir: Path,
    *,
    conversation: str,
    server_id: int,
    local_id: int,
) -> tuple[int, int, str]:
    """Validate one voice row inside the selected account and conversation."""

    local_result = _query_local_voice_targets(
        account_dir,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
    )
    if account_prefers_decrypted_snapshot(Path(account_dir)):
        # Imported snapshots are intentionally isolated from the currently
        # logged-in local WeChat account.  Never fill a snapshot lookup from
        # the process-wide realtime WCDB connection.
        realtime_result = _VoiceTargetQueryResult(set(), {}, 0, [])
    else:
        realtime_result = _query_realtime_voice_targets(
            account_dir,
            conversation=conversation,
            server_id=server_id,
            local_id=local_id,
        )
    combined_rows = local_result.rows | realtime_result.rows
    successful_queries = local_result.successful_queries + realtime_result.successful_queries
    if successful_queries <= 0:
        raise NativeVoiceTriggerError(
            "native_message_lookup_unavailable",
            "当前无法读取指定账号的微信消息数据，未触发原生转写。",
        )

    requested_rows = {
        row for row in combined_rows
        if (server_id > 0 and row[1] == server_id)
        or (local_id > 0 and row[0] == local_id)
    }
    positive_targets = {
        row for row in requested_rows if row[0] > 0 and row[1] > 0
    }
    if server_id > 0 and local_id > 0:
        exact = (local_id, server_id)
        # local_id is scoped to a message shard and can legitimately be reused
        # by the same conversation in another message_*.db.  Once the exact
        # pair exists, only a conflicting mapping for the globally stable
        # server_id invalidates it; a row that merely reuses local_id does not.
        conflicting_server_rows = {
            row for row in requested_rows
            if row[1] == server_id and row != exact
        }
        if exact not in combined_rows or conflicting_server_rows:
            raise NativeVoiceTriggerError(
                "voice_message_id_mismatch",
                "server_id 与 local_id 未映射到指定会话中的同一条语音消息。",
            )
        target = exact
    elif len(positive_targets) > 1:
        raise NativeVoiceTriggerError(
            "voice_message_ambiguous",
            "同一会话中找到了多条冲突的语音消息，请改用 server_id。",
        )
    elif len(positive_targets) == 1:
        target = next(iter(positive_targets))
    elif local_id > 0 and any(
        row_local_id == local_id and row_server_id <= 0
        for row_local_id, row_server_id in requested_rows
    ):
        raise NativeVoiceTriggerError(
            "voice_message_unsynced",
            "该语音消息尚无 server_id，暂不能触发微信原生转写。",
        )
    else:
        raise NativeVoiceTriggerError(
            "voice_message_not_found",
            "在指定账号和会话中未找到该语音消息。",
        )

    text = str(
        lookup_cached_native_voice_transcript(
            account_dir,
            target[1],
            conversation=conversation,
            local_id=target[0],
        )
        or realtime_result.transcripts.get(target)
        or local_result.transcripts.get(target)
        or ""
    ).strip()
    return target[0], target[1], text


def trigger_native_voice_transcription(
    *,
    account_dir: Path,
    conversation: str,
    server_id: Optional[str] = None,
    local_id: Optional[str] = None,
    transport: Optional[NativeVoiceTriggerTransport] = None,
) -> dict[str, object]:
    """Resolve, fast-path, and dispatch once; never poll or sleep in the POST path."""

    resolved_conversation = normalize_native_voice_conversation(conversation)
    parsed_server_id = parse_native_voice_message_id(server_id, "server_id")
    parsed_local_id = parse_native_voice_message_id(local_id, "local_id")
    if parsed_server_id <= 0 and parsed_local_id <= 0:
        raise NativeVoiceTriggerError(
            "missing_message_id",
            "server_id 和 local_id 至少需要提供一个。",
        )
    parsed_local_id, parsed_server_id, existing_text = resolve_native_voice_target(
        Path(account_dir),
        conversation=resolved_conversation,
        server_id=parsed_server_id,
        local_id=parsed_local_id,
    )

    account_path = Path(account_dir)
    response_base: dict[str, object] = {
        "serverId": str(parsed_server_id),
        "localId": str(parsed_local_id) if parsed_local_id > 0 else "",
        "account": account_path.name,
        "conversation": resolved_conversation,
        "language": "",
    }
    if existing_text:
        return {
            "status": "success",
            **response_base,
            "text": existing_text,
            "model": "wechat-native",
            "requestId": "",
            "pollAfterMs": 0,
        }

    command = NativeVoiceTriggerCommand(
        account_dir=account_path,
        account=resolve_account_self_username(account_path),
        conversation=resolved_conversation,
        server_id=parsed_server_id,
        local_id=parsed_local_id,
    )
    try:
        receipt = (transport or get_native_voice_trigger_transport()).trigger(command)
    except NativeVoiceTriggerError:
        raise
    except Exception as exc:
        raise NativeVoiceTriggerError(
            "native_transport_failed",
            "微信原生语音转写桥接调用失败。",
        ) from exc
    receipt_status = str(getattr(receipt, "status", "") or "").strip().lower()
    if receipt_status not in _TRIGGER_RECEIPT_STATUSES:
        raise NativeVoiceTriggerError(
            "native_transport_invalid_response",
            "微信原生语音转写桥接返回了无效状态。",
        )
    try:
        receipt_request_id = _normalize_native_request_id(
            str(getattr(receipt, "request_id", "") or "")
        )
    except (TypeError, ValueError) as exc:
        raise NativeVoiceTriggerError(
            "native_transport_invalid_response",
            "微信原生语音转写桥接未返回有效的 requestId。",
        ) from exc
    return {
        "status": receipt_status,
        **response_base,
        "text": "",
        "model": "",
        "requestId": receipt_request_id,
        "pollAfterMs": 1200,
    }
