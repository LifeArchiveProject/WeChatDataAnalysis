from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Any, Optional

from .logging_config import get_logger
from .sns_realtime_autosync import SNS_REALTIME_AUTOSYNC
from .wcdb_realtime import WCDB_REALTIME, exec_query as _wcdb_exec_query


logger = get_logger(__name__)

_BATCH_SIZE = 200
_ACTIVE_STATUSES = {"queued", "running"}
_SAFE_ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")


@dataclass
class _FullSyncProgress:
    phase: str = "connecting"
    source_rows_total: int = 0
    source_rows_scanned: int = 0
    batches_completed: int = 0
    prepared: int = 0
    changed: int = 0
    unchanged: int = 0
    skipped: int = 0


@dataclass
class _FullSyncJob:
    account_dir: Path
    sync_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    cancel_requested: bool = False
    snapshot_version: str = ""
    progress: _FullSyncProgress = field(default_factory=_FullSyncProgress)
    error: Optional[dict[str, str]] = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)


class SnsFullSyncManager:
    """朋友圈全量缓存同步任务管理器。

    每个账号只保留一个活动任务，同时通过全局信号量保证任意时刻只扫描一个账号。
    """

    def __init__(self) -> None:
        self._mu = threading.RLock()
        self._global_slot = threading.BoundedSemaphore(1)
        self._latest_by_account: dict[str, _FullSyncJob] = {}

    @staticmethod
    def _account_key(account_dir: Path) -> str:
        # 账号仅作为内存索引，不进入日志或公开任务结构。
        return str(Path(account_dir).resolve())

    @staticmethod
    def _safe_error_type(exc: BaseException) -> str:
        name = type(exc).__name__
        return name if _SAFE_ERROR_TYPE_RE.fullmatch(name) else "Exception"

    def _public_job_locked(self, job: _FullSyncJob) -> dict[str, Any]:
        progress = job.progress
        total = max(0, int(progress.source_rows_total))
        scanned = max(0, int(progress.source_rows_scanned))
        if job.status == "done":
            percent = 100
        elif total <= 0:
            percent = 0
        else:
            percent = min(99, int(scanned * 100 / total))

        payload: dict[str, Any] = {
            "syncId": job.sync_id,
            "status": job.status,
            "createdAt": job.created_at,
            "startedAt": job.started_at,
            "finishedAt": job.finished_at,
            "cancelRequested": bool(job.cancel_requested),
            "snapshotVersion": job.snapshot_version,
            "progress": {
                "phase": progress.phase,
                "sourceRowsTotal": total,
                "sourceRowsScanned": scanned,
                "batchesCompleted": int(progress.batches_completed),
                "prepared": int(progress.prepared),
                "changed": int(progress.changed),
                "unchanged": int(progress.unchanged),
                "skipped": int(progress.skipped),
                "percent": percent,
            },
        }
        if job.error is not None:
            payload["error"] = dict(job.error)
        return payload

    def get(self, account_dir: Path) -> Optional[dict[str, Any]]:
        key = self._account_key(account_dir)
        with self._mu:
            job = self._latest_by_account.get(key)
            return self._public_job_locked(job) if job is not None else None

    def start(self, account_dir: Path) -> tuple[dict[str, Any], bool]:
        resolved = Path(account_dir).resolve()
        key = self._account_key(resolved)
        with self._mu:
            current = self._latest_by_account.get(key)
            if current is not None and current.status in _ACTIVE_STATUSES:
                return self._public_job_locked(current), True

            job = _FullSyncJob(account_dir=resolved)
            self._latest_by_account[key] = job
            public = self._public_job_locked(job)

        worker = threading.Thread(
            target=self._run_job,
            args=(key, job),
            name=f"sns-full-sync-{job.sync_id[:8]}",
            daemon=True,
        )
        logger.info(
            "[sns.full-sync] status=queued sync_id=%s phase=connecting",
            job.sync_id,
        )
        self._publish(job, "full_sync_progress")
        try:
            worker.start()
        except Exception as exc:
            self._finish_error(
                job,
                code="sync_worker_unavailable",
                message="朋友圈同步线程不可用，请稍后重试",
                exc=exc,
                started_monotonic=time.monotonic(),
            )
        # 极小数据集可能在线程启动后立即完成，返回最新状态避免旧 queued 覆盖 SSE 终态。
        return self.get(resolved) or public, False

    def cancel(self, account_dir: Path, sync_id: str) -> tuple[Optional[dict[str, Any]], bool]:
        key = self._account_key(account_dir)
        requested_id = str(sync_id or "").strip()
        with self._mu:
            job = self._latest_by_account.get(key)
            if (
                job is None
                or job.sync_id != requested_id
                or job.status not in _ACTIVE_STATUSES
            ):
                return (self._public_job_locked(job) if job is not None else None), False
            job.cancel_requested = True
            job.cancel_event.set()
            return self._public_job_locked(job), True

    def _publish(self, job: _FullSyncJob, event_type: str) -> None:
        with self._mu:
            public = self._public_job_locked(job)
        SNS_REALTIME_AUTOSYNC.publish_external_event(
            Path(job.account_dir).name,
            {
                "type": event_type,
                "account": Path(job.account_dir).name,
                "job": public,
                "snapshotVersion": public.get("snapshotVersion") or "",
                "timestamp": int(time.time() * 1000),
            },
        )

    def _finish_cancelled(self, job: _FullSyncJob, started_monotonic: float) -> None:
        with self._mu:
            job.status = "cancelled"
            job.finished_at = int(time.time() * 1000)
        logger.info(
            "[sns.full-sync] status=cancelled sync_id=%s phase=%s batches=%s scanned=%s prepared=%s changed=%s unchanged=%s skipped=%s elapsed_ms=%s",
            job.sync_id,
            job.progress.phase,
            job.progress.batches_completed,
            job.progress.source_rows_scanned,
            job.progress.prepared,
            job.progress.changed,
            job.progress.unchanged,
            job.progress.skipped,
            int((time.monotonic() - started_monotonic) * 1000),
        )
        self._publish(job, "full_sync_cancelled")

    def _finish_error(
        self,
        job: _FullSyncJob,
        *,
        code: str,
        message: str,
        exc: Optional[BaseException],
        started_monotonic: float,
    ) -> None:
        error_type = self._safe_error_type(exc) if exc is not None else "SyncError"
        with self._mu:
            job.status = "error"
            job.finished_at = int(time.time() * 1000)
            job.error = {"code": code, "message": message}
        logger.error(
            "[sns.full-sync] status=error sync_id=%s phase=%s code=%s error_type=%s batches=%s scanned=%s prepared=%s changed=%s unchanged=%s skipped=%s elapsed_ms=%s",
            job.sync_id,
            job.progress.phase,
            code,
            error_type,
            job.progress.batches_completed,
            job.progress.source_rows_scanned,
            job.progress.prepared,
            job.progress.changed,
            job.progress.unchanged,
            job.progress.skipped,
            int((time.monotonic() - started_monotonic) * 1000),
        )
        self._publish(job, "full_sync_error")

    @staticmethod
    def _row_value(row: dict[str, Any], name: str, default: Any = None) -> Any:
        if name in row:
            return row.get(name)
        lowered = name.lower()
        for key, value in row.items():
            if str(key).lower() == lowered:
                return value
        return default

    @staticmethod
    def _source_db_path(connection: Any) -> Optional[Path]:
        try:
            root = Path(connection.db_storage_dir)
            candidates = (root / "sns" / "sns.db", root / "sns.db")
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
        except Exception:
            return None
        return None

    def _query(self, connection: Any, source_path: Path, sql: str) -> list[dict[str, Any]]:
        with connection.lock:
            rows = _wcdb_exec_query(
                connection.handle,
                kind="media",
                path=str(source_path),
                sql=sql,
            )
        return [row for row in (rows or []) if isinstance(row, dict)]

    def _count_and_bounds(
        self,
        connection: Any,
        source_path: Path,
    ) -> tuple[str, int, Optional[int], Optional[int]]:
        valid_where = (
            "tid IS NOT NULL AND user_name IS NOT NULL AND user_name != '' "
            "AND content IS NOT NULL AND content != ''"
        )
        last_exc: Optional[BaseException] = None
        for cursor_column in ("rowid", "tid"):
            sql = (
                "SELECT COUNT(*) AS source_rows_total, "
                f"MIN({cursor_column}) AS min_cursor, MAX({cursor_column}) AS max_cursor "
                f"FROM SnsTimeLine WHERE {valid_where}"
            )
            try:
                rows = self._query(connection, source_path, sql)
                row = rows[0] if rows else {}
                total = int(self._row_value(row, "source_rows_total", 0) or 0)
                min_raw = self._row_value(row, "min_cursor")
                max_raw = self._row_value(row, "max_cursor")
                min_cursor = int(min_raw) if min_raw is not None else None
                max_cursor = int(max_raw) if max_raw is not None else None
                return cursor_column, total, min_cursor, max_cursor
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("SnsTimeLine cursor is unavailable")

    def _read_batch(
        self,
        connection: Any,
        source_path: Path,
        *,
        cursor_column: str,
        min_cursor: int,
        max_cursor: int,
        after_cursor: Optional[int],
        include_pack: bool,
    ) -> tuple[list[dict[str, Any]], bool]:
        lower = (
            f"{cursor_column} >= {int(min_cursor)}"
            if after_cursor is None
            else f"{cursor_column} > {int(after_cursor)}"
        )
        where_sql = (
            f"{lower} AND {cursor_column} <= {int(max_cursor)} "
            "AND tid IS NOT NULL AND user_name IS NOT NULL AND user_name != '' "
            "AND content IS NOT NULL AND content != ''"
        )
        select_pack = ", pack_info_buf" if include_pack else ""
        sql = (
            f"SELECT {cursor_column} AS source_cursor, tid, user_name, content{select_pack} "
            f"FROM SnsTimeLine WHERE {where_sql} "
            f"ORDER BY {cursor_column} ASC LIMIT {_BATCH_SIZE}"
        )
        try:
            return self._query(connection, source_path, sql), include_pack
        except Exception:
            if not include_pack:
                raise
            # 老版本源表没有 pack_info_buf，保持主记录同步能力。
            return self._read_batch(
                connection,
                source_path,
                cursor_column=cursor_column,
                min_cursor=min_cursor,
                max_cursor=max_cursor,
                after_cursor=after_cursor,
                include_pack=False,
            )

    def _run_job(self, _key: str, job: _FullSyncJob) -> None:
        started_monotonic = time.monotonic()
        slot_acquired = False
        try:
            while not job.cancel_event.is_set():
                if self._global_slot.acquire(timeout=0.1):
                    slot_acquired = True
                    break
            if not slot_acquired:
                self._finish_cancelled(job, started_monotonic)
                return

            with self._mu:
                job.status = "running"
                job.started_at = int(time.time() * 1000)
                job.progress.phase = "connecting"
            logger.info(
                "[sns.full-sync] status=running sync_id=%s phase=connecting",
                job.sync_id,
            )
            self._publish(job, "full_sync_progress")

            if job.cancel_event.is_set():
                self._finish_cancelled(job, started_monotonic)
                return

            try:
                connection = WCDB_REALTIME.ensure_connected(job.account_dir, timeout=15.0)
            except Exception as exc:
                self._finish_error(
                    job,
                    code="realtime_not_available",
                    message="朋友圈实时组件未连接，请确认微信已登录且数据库密钥有效",
                    exc=exc,
                    started_monotonic=started_monotonic,
                )
                return
            source_path = self._source_db_path(connection)
            if source_path is None:
                self._finish_error(
                    job,
                    code="sns_source_not_found",
                    message="未找到微信本地朋友圈数据库",
                    exc=None,
                    started_monotonic=started_monotonic,
                )
                return

            with self._mu:
                job.progress.phase = "counting"
            self._publish(job, "full_sync_progress")

            try:
                cursor_column, total, min_cursor, max_cursor = self._count_and_bounds(
                    connection,
                    source_path,
                )
            except Exception as exc:
                self._finish_error(
                    job,
                    code="sns_source_schema_unsupported",
                    message="当前朋友圈数据库结构暂不支持全量同步",
                    exc=exc,
                    started_monotonic=started_monotonic,
                )
                return

            with self._mu:
                job.progress.source_rows_total = total
                job.progress.phase = "scanning"
            self._publish(job, "full_sync_progress")

            # 延迟导入路由辅助函数，避免模块加载时形成循环依赖。
            from .routers.sns import (
                _build_sns_snapshot_status,
                _decode_sns_text_blob,
                _looks_like_xml_text,
                _read_sns_realtime_sync_state,
                _upsert_sns_timeline_rows_to_decrypted_db,
                _write_sns_realtime_sync_state,
            )

            after_cursor: Optional[int] = None
            include_pack = True
            max_tid_unsigned = 0

            while min_cursor is not None and max_cursor is not None:
                if job.cancel_event.is_set():
                    self._finish_cancelled(job, started_monotonic)
                    return

                rows, include_pack = self._read_batch(
                    connection,
                    source_path,
                    cursor_column=cursor_column,
                    min_cursor=min_cursor,
                    max_cursor=max_cursor,
                    after_cursor=after_cursor,
                    include_pack=include_pack,
                )
                if not rows:
                    break

                prepared_rows: list[tuple[int, str, str, Optional[Any]]] = []
                skipped = 0
                for row in rows:
                    try:
                        source_cursor = int(self._row_value(row, "source_cursor"))
                        tid = int(self._row_value(row, "tid"))
                        username = str(self._row_value(row, "user_name", "") or "").strip()
                        content = _decode_sns_text_blob(self._row_value(row, "content"))
                        if (
                            not username
                            or not _looks_like_xml_text(content)
                            or "<type>7</type>" in content
                        ):
                            skipped += 1
                            continue
                        pack = self._row_value(row, "pack_info_buf") if include_pack else None
                        prepared_rows.append((tid, username, content, pack))
                        max_tid_unsigned = max(max_tid_unsigned, tid & 0xFFFFFFFFFFFFFFFF)
                    except Exception:
                        skipped += 1
                        continue

                result = _upsert_sns_timeline_rows_to_decrypted_db(
                    job.account_dir,
                    prepared_rows,
                    source="sns.full-sync",
                )
                if not bool(result.get("success")):
                    self._finish_error(
                        job,
                        code="snapshot_write_failed",
                        message="朋友圈本地快照写入失败，可稍后重试",
                        exc=None,
                        started_monotonic=started_monotonic,
                    )
                    return

                after_cursor = max(
                    int(self._row_value(row, "source_cursor")) for row in rows
                )
                snapshot = _build_sns_snapshot_status(job.account_dir)
                with self._mu:
                    job.progress.source_rows_scanned += len(rows)
                    job.progress.batches_completed += 1
                    job.progress.prepared += int(result.get("prepared") or 0)
                    job.progress.changed += int(result.get("changed") or 0)
                    job.progress.unchanged += int(result.get("unchanged") or 0)
                    job.progress.skipped += skipped
                    job.snapshot_version = str(snapshot.get("version") or "")

                logger.info(
                    "[sns.full-sync] status=running sync_id=%s phase=scanning batches=%s scanned=%s total=%s prepared=%s changed=%s unchanged=%s skipped=%s elapsed_ms=%s",
                    job.sync_id,
                    job.progress.batches_completed,
                    job.progress.source_rows_scanned,
                    job.progress.source_rows_total,
                    job.progress.prepared,
                    job.progress.changed,
                    job.progress.unchanged,
                    job.progress.skipped,
                    int((time.monotonic() - started_monotonic) * 1000),
                )
                self._publish(job, "full_sync_progress")

                if len(rows) < _BATCH_SIZE:
                    break

            if job.cancel_event.is_set():
                self._finish_cancelled(job, started_monotonic)
                return

            with self._mu:
                job.progress.phase = "finalizing"
            self._publish(job, "full_sync_progress")

            if max_tid_unsigned > 0:
                state = _read_sns_realtime_sync_state(job.account_dir)
                state["maxId"] = str(max_tid_unsigned)
                state["updatedAt"] = int(time.time() * 1000)
                if not _write_sns_realtime_sync_state(job.account_dir, state):
                    self._finish_error(
                        job,
                        code="sync_state_write_failed",
                        message="朋友圈同步状态写入失败，可安全重试",
                        exc=None,
                        started_monotonic=started_monotonic,
                    )
                    return

            snapshot = _build_sns_snapshot_status(job.account_dir)
            with self._mu:
                job.status = "done"
                job.finished_at = int(time.time() * 1000)
                job.snapshot_version = str(snapshot.get("version") or "")
            logger.info(
                "[sns.full-sync] status=done sync_id=%s phase=finalizing batches=%s scanned=%s total=%s prepared=%s changed=%s unchanged=%s skipped=%s elapsed_ms=%s",
                job.sync_id,
                job.progress.batches_completed,
                job.progress.source_rows_scanned,
                job.progress.source_rows_total,
                job.progress.prepared,
                job.progress.changed,
                job.progress.unchanged,
                job.progress.skipped,
                int((time.monotonic() - started_monotonic) * 1000),
            )
            self._publish(job, "full_sync_done")
        except Exception as exc:
            self._finish_error(
                job,
                code="full_sync_failed",
                message="朋友圈全量同步失败，请稍后重试",
                exc=exc,
                started_monotonic=started_monotonic,
            )
        finally:
            if slot_acquired:
                try:
                    self._global_slot.release()
                except Exception:
                    pass


SNS_FULL_SYNC = SnsFullSyncManager()
