"""SNS (Moments) realtime -> decrypted sqlite incremental sync.

Why:
- We can read the latest Moments via WCDB realtime, but the decrypted snapshot (`output/databases/{account}/sns.db`)
  can lag behind or miss data (e.g. you viewed it when it was visible, then it became "only last 3 days").
- For export/offline browsing, we want to keep a local append-only cache of Moments that were visible at some point.

This module runs a lightweight background poller that watches db_storage/sns*.db mtime changes and triggers a cheap
incremental sync of the latest N Moments into the decrypted snapshot.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from .chat_helpers import _list_decrypted_accounts, _resolve_account_dir
from .logging_config import get_logger
from .wcdb_realtime import WCDB_REALTIME

logger = get_logger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = str(os.environ.get(name, "") or "").strip()
    try:
        v = int(raw)
    except Exception:
        v = int(default)
    if v < min_v:
        v = min_v
    if v > max_v:
        v = max_v
    return v


def _mtime_ns(path: Path) -> int:
    try:
        st = path.stat()
        m_ns = int(getattr(st, "st_mtime_ns", 0) or 0)
        if m_ns <= 0:
            m_ns = int(float(getattr(st, "st_mtime", 0.0) or 0.0) * 1_000_000_000)
        return int(m_ns)
    except Exception:
        return 0


def _scan_sns_db_mtime_ns(db_storage_dir: Path) -> int:
    """Best-effort "latest mtime" signal for sns.db buckets."""
    base = Path(db_storage_dir)
    candidates: list[Path] = [
        base / "sns" / "sns.db",
        base / "sns" / "sns.db-wal",
        base / "sns" / "sns.db-shm",
        base / "sns.db",
        base / "sns.db-wal",
        base / "sns.db-shm",
    ]
    max_ns = 0
    for p in candidates:
        v = _mtime_ns(p)
        if v > max_ns:
            max_ns = v
    return int(max_ns)


@dataclass
class _AccountState:
    last_mtime_ns: int = 0
    due_at: float = 0.0
    last_sync_end_at: float = 0.0
    thread: Optional[threading.Thread] = None


class SnsRealtimeAutoSyncService:
    def __init__(self) -> None:
        self._enabled = _env_bool("WECHAT_TOOL_SNS_AUTOSYNC", True)
        self._interval_ms = _env_int("WECHAT_TOOL_SNS_AUTOSYNC_INTERVAL_MS", 2000, min_v=500, max_v=60_000)
        self._debounce_ms = _env_int("WECHAT_TOOL_SNS_AUTOSYNC_DEBOUNCE_MS", 800, min_v=0, max_v=60_000)
        self._min_sync_interval_ms = _env_int(
            "WECHAT_TOOL_SNS_AUTOSYNC_MIN_SYNC_INTERVAL_MS", 5000, min_v=0, max_v=300_000
        )
        self._workers = _env_int("WECHAT_TOOL_SNS_AUTOSYNC_WORKERS", 1, min_v=1, max_v=4)
        self._max_scan = _env_int("WECHAT_TOOL_SNS_AUTOSYNC_MAX_SCAN", 200, min_v=20, max_v=2000)

        self._mu = threading.Lock()
        self._states: dict[str, _AccountState] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self._enabled:
            logger.info("[sns-autosync] disabled by env WECHAT_TOOL_SNS_AUTOSYNC=0")
            return
        with self._mu:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            th = threading.Thread(target=self._run, name="sns-realtime-autosync", daemon=True)
            self._thread = th
            th.start()
        logger.info(
            "[sns-autosync] started interval_ms=%s debounce_ms=%s min_sync_interval_ms=%s max_scan=%s workers=%s",
            int(self._interval_ms),
            int(self._debounce_ms),
            int(self._min_sync_interval_ms),
            int(self._max_scan),
            int(self._workers),
        )

    def stop(self) -> None:
        self._stop.set()
        with self._mu:
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            tick_t0 = time.perf_counter()
            try:
                self._tick()
            except Exception:
                logger.exception("[sns-autosync] tick failed")

            elapsed_ms = (time.perf_counter() - tick_t0) * 1000.0
            sleep_ms = max(200.0, float(self._interval_ms) - elapsed_ms)
            self._stop.wait(timeout=sleep_ms / 1000.0)

    def _tick(self) -> None:
        accounts = _list_decrypted_accounts()
        now = time.time()
        if not accounts:
            return

        for acc in accounts:
            if self._stop.is_set():
                break
            try:
                account_dir = _resolve_account_dir(acc)
            except HTTPException:
                continue
            except Exception:
                continue

            info = WCDB_REALTIME.get_status(account_dir)
            available = bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))
            if not available:
                continue

            db_storage_dir = Path(str(info.get("db_storage_dir") or "").strip())
            if not db_storage_dir.exists() or not db_storage_dir.is_dir():
                continue

            mtime_ns = _scan_sns_db_mtime_ns(db_storage_dir)
            with self._mu:
                st = self._states.setdefault(acc, _AccountState())
                if mtime_ns and mtime_ns != st.last_mtime_ns:
                    st.last_mtime_ns = int(mtime_ns)
                    st.due_at = now + (float(self._debounce_ms) / 1000.0)

        # Schedule daemon threads.
        to_start: list[threading.Thread] = []
        with self._mu:
            keep = set(accounts)
            for acc in list(self._states.keys()):
                if acc not in keep:
                    self._states.pop(acc, None)

            running = 0
            for st in self._states.values():
                th = st.thread
                if th is not None and th.is_alive():
                    running += 1
                elif th is not None and (not th.is_alive()):
                    st.thread = None

            for acc, st in self._states.items():
                if running >= int(self._workers):
                    break
                if st.due_at <= 0 or st.due_at > now:
                    continue
                if st.thread is not None and st.thread.is_alive():
                    continue

                since = now - float(st.last_sync_end_at or 0.0)
                min_interval = float(self._min_sync_interval_ms) / 1000.0
                if min_interval > 0 and since < min_interval:
                    st.due_at = now + (min_interval - since)
                    continue

                st.due_at = 0.0
                th = threading.Thread(
                    target=self._sync_account_runner,
                    args=(acc,),
                    name=f"sns-autosync-{acc}",
                    daemon=True,
                )
                st.thread = th
                to_start.append(th)
                running += 1

        for th in to_start:
            if self._stop.is_set():
                break
            try:
                th.start()
            except Exception:
                with self._mu:
                    for acc, st in self._states.items():
                        if st.thread is th:
                            st.thread = None
                            break

    def _sync_account_runner(self, account: str) -> None:
        account = str(account or "").strip()
        try:
            if self._stop.is_set() or (not account):
                return
            res = self._sync_account(account)
            upserted = int((res or {}).get("upserted") or 0)
            logger.info("[sns-autosync] sync done account=%s upserted=%s", account, upserted)
        except Exception:
            logger.exception("[sns-autosync] sync failed account=%s", account)
        finally:
            with self._mu:
                st = self._states.get(account)
                if st is not None:
                    st.thread = None
                    st.last_sync_end_at = time.time()

    def _sync_account(self, account: str) -> dict[str, Any]:
        account = str(account or "").strip()
        if not account:
            return {"status": "skipped", "reason": "missing account"}

        try:
            account_dir = _resolve_account_dir(account)
        except Exception as e:
            return {"status": "skipped", "reason": f"resolve account failed: {e}"}

        info = WCDB_REALTIME.get_status(account_dir)
        available = bool(info.get("dll_present") and info.get("key_present") and info.get("db_storage_dir"))
        if not available:
            return {"status": "skipped", "reason": "realtime not available"}

        # Import lazily to avoid startup import ordering issues.
        from .routers.sns import sync_sns_realtime_timeline_latest

        try:
            return sync_sns_realtime_timeline_latest(
                account=account,
                max_scan=int(self._max_scan),
                force=0,
            )
        except HTTPException as e:
            return {"status": "error", "error": str(e.detail or "")}
        except Exception as e:
            return {"status": "error", "error": str(e)}


SNS_REALTIME_AUTOSYNC = SnsRealtimeAutoSyncService()

