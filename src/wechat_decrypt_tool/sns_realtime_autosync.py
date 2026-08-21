"""基于系统文件事件的朋友圈实时增量同步服务。"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from watchfiles import watch

from .chat_helpers import _list_decrypted_accounts, _resolve_account_dir
from .logging_config import get_logger
from .wcdb_realtime import WCDB_REALTIME

logger = get_logger(__name__)

_SNS_SOURCE_FILE_NAMES = frozenset({"sns.db", "sns.db-wal", "sns.db-shm"})
_PUBLIC_ERROR_CODE_RE = re.compile(r"^[a-z0-9_\-]{1,80}$", flags=re.IGNORECASE)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = str(os.environ.get(name, "") or "").strip()
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    return max(int(min_v), min(int(max_v), value))


def _normalize_watch_key(path: Path) -> str:
    try:
        value = str(Path(path).resolve())
    except Exception:
        value = str(Path(path))
    return os.path.normcase(value)


def _is_sns_source_path(path: str | Path) -> bool:
    return Path(path).name.lower() in _SNS_SOURCE_FILE_NAMES


def _resolve_sns_watch_dir(db_storage_dir: Path) -> Path:
    """解析微信源朋友圈目录，绝不监听程序自己的解密输出目录。"""
    base = Path(db_storage_dir)
    nested = base / "sns"
    if nested.exists() and nested.is_dir():
        return nested
    return base


@dataclass
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


@dataclass
class _AccountState:
    source_revision: int = 0
    sequence: int = 0
    sync_running: bool = False
    pending_revision: int = 0
    pending_reason: str = ""
    worker: Optional[threading.Thread] = None
    watch_key: str = ""
    watcher_available: bool = False
    watcher_error: str = ""
    startup_scheduled: bool = False
    ignore_shm_until: float = 0.0
    subscribers: dict[str, _Subscriber] = field(default_factory=dict)


@dataclass
class _WatchState:
    path: Path
    accounts: set[str] = field(default_factory=set)
    thread: Optional[threading.Thread] = None


class SnsRealtimeAutoSyncService:
    """用操作系统文件通知触发朋友圈同步，并向 SSE 订阅者广播结果。"""

    def __init__(self) -> None:
        self._enabled = _env_bool("WECHAT_TOOL_SNS_AUTOSYNC", True)
        self._debounce_ms = _env_int(
            "WECHAT_TOOL_SNS_AUTOSYNC_DEBOUNCE_MS",
            300,
            min_v=50,
            max_v=5000,
        )
        self._workers = _env_int("WECHAT_TOOL_SNS_AUTOSYNC_WORKERS", 1, min_v=1, max_v=4)
        self._max_scan = _env_int("WECHAT_TOOL_SNS_AUTOSYNC_MAX_SCAN", 200, min_v=20, max_v=2000)
        self._retry_delays = (0.8, 2.0)

        self._mu = threading.RLock()
        self._states: dict[str, _AccountState] = {}
        self._watchers: dict[str, _WatchState] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._worker_slots = threading.BoundedSemaphore(self._workers)

    def start(self) -> None:
        if not self._enabled:
            logger.info("[sns-autosync] 已通过 WECHAT_TOOL_SNS_AUTOSYNC=0 禁用")
            return
        with self._mu:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            thread = threading.Thread(
                target=self._bootstrap_accounts,
                name="sns-event-autosync-bootstrap",
                daemon=True,
            )
            self._thread = thread
            thread.start()
        logger.info(
            "[sns-autosync] 文件事件同步已启动 debounce_ms=%s max_scan=%s workers=%s",
            self._debounce_ms,
            self._max_scan,
            self._workers,
        )

    def stop(self) -> None:
        self._stop.set()
        current = threading.current_thread()
        with self._mu:
            threads: list[threading.Thread] = []
            if self._thread is not None and self._thread is not current:
                threads.append(self._thread)
            for watcher in self._watchers.values():
                if watcher.thread is not None and watcher.thread is not current:
                    threads.append(watcher.thread)
            for state in self._states.values():
                if state.worker is not None and state.worker is not current:
                    threads.append(state.worker)

        for thread in list(dict.fromkeys(threads)):
            try:
                thread.join(timeout=5.0)
            except Exception:
                pass

        with self._mu:
            self._thread = None
            self._started = False
            self._watchers.clear()
            for state in self._states.values():
                state.sync_running = False
                state.worker = None
                state.watch_key = ""
                state.watcher_available = False
                state.startup_scheduled = False
                state.subscribers.clear()

    def _bootstrap_accounts(self) -> None:
        """启动时只枚举一次账号；后续账号由 SSE 连接动态注册。"""
        try:
            accounts = list(_list_decrypted_accounts() or [])
        except Exception:
            logger.exception("[sns-autosync] 初始账号枚举失败")
            return
        for account in accounts:
            if self._stop.is_set():
                return
            self.ensure_account(account, schedule_startup=True)

    def ensure_account(self, account: str, *, schedule_startup: bool = True) -> dict[str, Any]:
        account = str(account or "").strip()
        if not self._enabled:
            return {
                "available": False,
                "code": "sns_event_sync_disabled",
                "message": "朋友圈文件事件同步已禁用",
            }
        if not account:
            return {"available": False, "code": "missing_account", "message": "缺少账号参数"}

        try:
            account_dir = _resolve_account_dir(account)
        except HTTPException:
            return {"available": False, "code": "account_not_found", "message": "账号不存在"}
        except Exception:
            return {"available": False, "code": "account_not_found", "message": "账号不存在"}

        info = WCDB_REALTIME.get_status(account_dir)
        available = bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))
        if not available:
            return {
                "available": False,
                "code": "realtime_not_available",
                "message": "实时组件未连接，请使用手动刷新",
            }

        db_storage_dir = Path(str(info.get("db_storage_dir") or "").strip())
        watch_dir = _resolve_sns_watch_dir(db_storage_dir)
        if not watch_dir.exists() or not watch_dir.is_dir():
            return {
                "available": False,
                "code": "sns_watch_directory_unavailable",
                "message": "朋友圈源数据库目录不可用，请使用手动刷新",
            }

        watch_key = _normalize_watch_key(watch_dir)
        watcher_thread: Optional[threading.Thread] = None
        should_schedule_startup = False
        with self._mu:
            state = self._states.setdefault(account, _AccountState())
            state.watch_key = watch_key
            state.watcher_available = True
            state.watcher_error = ""

            watcher = self._watchers.get(watch_key)
            if watcher is None:
                watcher = _WatchState(path=watch_dir)
                self._watchers[watch_key] = watcher
            watcher.accounts.add(account)
            if watcher.thread is None:
                watcher_thread = threading.Thread(
                    target=self._watch_directory,
                    args=(watch_key,),
                    name=f"sns-file-watch-{len(self._watchers)}",
                    daemon=True,
                )
                watcher.thread = watcher_thread

            if schedule_startup and not state.startup_scheduled:
                state.startup_scheduled = True
                should_schedule_startup = True

        if watcher_thread is not None:
            try:
                watcher_thread.start()
            except Exception:
                with self._mu:
                    watcher = self._watchers.get(watch_key)
                    if watcher is not None and watcher.thread is watcher_thread:
                        watcher.thread = None
                self._mark_watcher_failed(watch_key, "sns_file_watch_unavailable")
                return {
                    "available": False,
                    "code": "sns_file_watch_unavailable",
                    "message": "系统文件通知不可用，请使用手动刷新",
                }

        if should_schedule_startup:
            self._schedule_sync(account, reason="startup")
        return {"available": True, "watchDirectory": str(watch_dir)}

    def _watch_directory(self, watch_key: str) -> None:
        with self._mu:
            watcher = self._watchers.get(watch_key)
            if watcher is None:
                return
            watch_dir = watcher.path

        try:
            for changes in watch(
                str(watch_dir),
                watch_filter=lambda _change, path: _is_sns_source_path(path),
                debounce=int(self._debounce_ms),
                step=min(100, int(self._debounce_ms)),
                stop_event=self._stop,
                recursive=False,
                force_polling=False,
                yield_on_timeout=False,
            ):
                if self._stop.is_set():
                    return
                if not changes:
                    continue
                changed_names = {
                    Path(path).name.lower()
                    for _change, path in changes
                    if _is_sns_source_path(path)
                }
                pure_shm_change = bool(changed_names) and changed_names <= {"sns.db-shm"}
                with self._mu:
                    current = self._watchers.get(watch_key)
                    accounts = list(current.accounts) if current is not None else []
                for account in accounts:
                    with self._mu:
                        state = self._states.get(account)
                        suppress_own_shm = bool(
                            pure_shm_change
                            and state is not None
                            and (
                                state.sync_running
                                or time.monotonic() < float(state.ignore_shm_until or 0.0)
                            )
                        )
                    if suppress_own_shm:
                        continue
                    self._schedule_sync(account, reason="file_event")
            if not self._stop.is_set():
                logger.error("[sns-autosync] 系统文件监听意外结束")
                self._mark_watcher_failed(watch_key, "sns_file_watch_unavailable")
        except Exception:
            if not self._stop.is_set():
                logger.exception("[sns-autosync] 系统文件监听失败")
                self._mark_watcher_failed(watch_key, "sns_file_watch_unavailable")

    def _mark_watcher_failed(self, watch_key: str, code: str) -> None:
        with self._mu:
            watcher = self._watchers.get(watch_key)
            accounts = list(watcher.accounts) if watcher is not None else []
            if watcher is not None:
                watcher.thread = None
            for account in accounts:
                state = self._states.get(account)
                if state is not None:
                    state.watcher_available = False
                    state.watcher_error = code
        for account in accounts:
            self._publish_error(
                account,
                source_revision=0,
                code=code,
                message="系统文件通知不可用，请使用手动刷新",
                retryable=False,
            )

    def _schedule_sync(self, account: str, *, reason: str) -> None:
        account = str(account or "").strip()
        if not account or self._stop.is_set():
            return

        worker: Optional[threading.Thread] = None
        with self._mu:
            state = self._states.setdefault(account, _AccountState())
            state.source_revision += 1
            revision = state.source_revision
            if state.sync_running:
                state.pending_revision = revision
                state.pending_reason = reason
                return

            state.sync_running = True
            worker = threading.Thread(
                target=self._sync_account_runner,
                args=(account, reason, revision),
                name=f"sns-event-sync-{account}",
                daemon=True,
            )
            state.worker = worker

        try:
            worker.start()
        except Exception:
            with self._mu:
                state = self._states.get(account)
                if state is not None and state.worker is worker:
                    state.sync_running = False
                    state.worker = None
            logger.exception("[sns-autosync] 启动同步线程失败 account=%s", account)
            self._publish_error(
                account,
                source_revision=revision,
                code="sns_sync_worker_unavailable",
                message="朋友圈实时同步线程不可用，请使用手动刷新",
                retryable=False,
            )

    def _sync_account_runner(self, account: str, reason: str, revision: int) -> None:
        current_thread = threading.current_thread()
        try:
            while not self._stop.is_set():
                result, superseded = self._sync_with_bounded_retries(account, revision)
                # WCDB 读取可能刷新共享内存文件；短暂忽略纯 -shm 事件，防止读取自身形成事件环。
                with self._mu:
                    state = self._states.get(account)
                    if state is not None:
                        state.ignore_shm_until = max(
                            float(state.ignore_shm_until or 0.0),
                            time.monotonic() + max(1.0, float(self._debounce_ms) / 500.0),
                        )
                if not superseded and not self._stop.is_set():
                    self._publish_sync_result(account, reason, revision, result)

                with self._mu:
                    state = self._states.get(account)
                    if state is None:
                        return
                    if state.pending_revision > revision:
                        revision = state.pending_revision
                        reason = state.pending_reason or "file_event"
                        state.pending_revision = 0
                        state.pending_reason = ""
                        continue
                    state.sync_running = False
                    if state.worker is current_thread:
                        state.worker = None
                    return
        finally:
            with self._mu:
                state = self._states.get(account)
                if state is not None and state.worker is current_thread:
                    state.sync_running = False
                    state.worker = None

    def _sync_with_bounded_retries(self, account: str, revision: int) -> tuple[dict[str, Any], bool]:
        last_result: dict[str, Any] = {"status": "error", "error": "sns_sync_failed"}
        for attempt in range(len(self._retry_delays) + 1):
            if self._stop.is_set():
                return {"status": "skipped", "reason": "service_stopping"}, False
            try:
                with self._worker_slots:
                    if self._stop.is_set():
                        return {"status": "skipped", "reason": "service_stopping"}, False
                    last_result = dict(self._sync_account(account) or {})
            except Exception:
                logger.exception("[sns-autosync] 同步失败 account=%s", account)
                last_result = {"status": "error", "error": "sns_sync_failed"}

            if not self._should_retry(last_result) or attempt >= len(self._retry_delays):
                return last_result, False

            with self._mu:
                state = self._states.get(account)
                if state is not None and state.pending_revision > revision:
                    return last_result, True
            if self._stop.wait(timeout=float(self._retry_delays[attempt])):
                return last_result, False
        return last_result, False

    @staticmethod
    def _should_retry(result: dict[str, Any]) -> bool:
        status = str((result or {}).get("status") or "error").strip().lower()
        if status == "error":
            return True
        if status == "noop":
            try:
                return int((result or {}).get("scanned") or 0) <= 0
            except Exception:
                return True
        return False

    def _sync_account(self, account: str) -> dict[str, Any]:
        account = str(account or "").strip()
        if not account:
            return {"status": "skipped", "reason": "missing_account"}

        try:
            account_dir = _resolve_account_dir(account)
        except Exception:
            return {"status": "skipped", "reason": "account_not_found"}

        info = WCDB_REALTIME.get_status(account_dir)
        available = bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))
        if not available:
            return {"status": "skipped", "reason": "realtime_not_available"}

        # 延迟导入，避免路由模块初始化时产生循环依赖。
        from .routers.sns import sync_sns_realtime_timeline_latest

        try:
            return sync_sns_realtime_timeline_latest(
                account=account,
                max_scan=int(self._max_scan),
                # 文件事件也可能只是更新已有动态的评论或点赞，因此必须强制核对。
                force=1,
            )
        except HTTPException as exc:
            return {"status": "error", "error": str(exc.detail or "sns_sync_failed")}
        except Exception:
            logger.exception("[sns-autosync] 增量同步调用失败 account=%s", account)
            return {"status": "error", "error": "sns_sync_failed"}

    def subscribe(
        self,
        account: str,
        *,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[str, asyncio.Queue, dict[str, Any]]:
        account = str(account or "").strip()
        availability = self.ensure_account(account, schedule_startup=True)
        token = uuid.uuid4().hex
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        with self._mu:
            state = self._states.setdefault(account, _AccountState())
            state.subscribers[token] = _Subscriber(loop=loop, queue=queue)
            sequence = state.sequence
            watcher_available = bool(state.watcher_available and availability.get("available"))

        ready = {
            "type": "ready",
            "account": account,
            "sequence": int(sequence),
            "snapshotVersion": self._current_snapshot_version(account),
            "watcherAvailable": watcher_available,
            "timestamp": int(time.time() * 1000),
        }
        if not watcher_available:
            ready["code"] = str(availability.get("code") or "sns_file_watch_unavailable")
            ready["message"] = str(availability.get("message") or "系统文件通知不可用，请使用手动刷新")
        return token, queue, ready

    def unsubscribe(self, account: str, token: str) -> None:
        with self._mu:
            state = self._states.get(str(account or "").strip())
            if state is not None:
                state.subscribers.pop(str(token or ""), None)

    def _current_snapshot_version(self, account: str) -> str:
        try:
            account_dir = _resolve_account_dir(account)
            from .routers.sns import _build_sns_snapshot_status

            return str(_build_sns_snapshot_status(account_dir).get("version") or "")
        except Exception:
            return ""

    def _publish_sync_result(self, account: str, reason: str, revision: int, result: dict[str, Any]) -> None:
        status = str((result or {}).get("status") or "error").strip().lower()
        if status in {"ok", "noop"}:
            event = {
                "type": "change",
                "account": account,
                "sourceRevision": int(revision),
                "reason": reason,
                "status": status,
                "snapshotVersion": str((result or {}).get("snapshotVersion") or ""),
                "snapshotChanged": bool((result or {}).get("snapshotChanged")),
                "changed": int((result or {}).get("changed") or (result or {}).get("upserted") or 0),
                "highwaterAdvanced": bool((result or {}).get("highwaterAdvanced")),
                "scanned": int((result or {}).get("scanned") or 0),
                "timestamp": int(time.time() * 1000),
            }
            self._publish_event(account, event)
            logger.info(
                "[sns-autosync] 事件同步完成 account=%s reason=%s revision=%s status=%s changed=%s",
                account,
                reason,
                revision,
                status,
                event["changed"],
            )
            return

        raw_code = str((result or {}).get("error") or (result or {}).get("reason") or "sns_sync_failed").strip()
        code = raw_code if _PUBLIC_ERROR_CODE_RE.fullmatch(raw_code) else "sns_sync_failed"
        self._publish_error(
            account,
            source_revision=revision,
            code=code,
            message="朋友圈实时同步失败，请使用手动刷新",
            retryable=False,
        )

    def _publish_error(
        self,
        account: str,
        *,
        source_revision: int,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        self._publish_event(account, {
            "type": "sync_error",
            "account": account,
            "sourceRevision": int(source_revision),
            "code": code,
            "message": message,
            "retryable": bool(retryable),
            "timestamp": int(time.time() * 1000),
        })

    @staticmethod
    def _offer_latest(queue: asyncio.Queue, event: dict[str, Any]) -> None:
        try:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
        except Exception:
            pass

    def _publish_event(self, account: str, event: dict[str, Any]) -> None:
        with self._mu:
            state = self._states.setdefault(account, _AccountState())
            state.sequence += 1
            payload = dict(event)
            payload["sequence"] = int(state.sequence)
            subscribers = list(state.subscribers.values())

        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(self._offer_latest, subscriber.queue, payload)
            except Exception:
                pass


SNS_REALTIME_AUTOSYNC = SnsRealtimeAutoSyncService()
