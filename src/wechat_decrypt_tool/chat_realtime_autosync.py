"""Background auto-sync from WCDB realtime (db_storage) into decrypted sqlite.

Why:
- The UI can read "latest" messages from WCDB realtime (`source=realtime`), but most APIs default to the
  decrypted sqlite snapshot (`source=decrypted`).
- Previously we only synced realtime -> decrypted when the UI toggled realtime off, which caused `/api/chat/messages`
  to lag behind while realtime was enabled.

This module runs a lightweight background poller that watches db_storage mtime changes and triggers an incremental
sync_all into decrypted sqlite. It is intentionally conservative (debounced + rate-limited) to avoid hammering the
backend or the sqlite files.
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


def _scan_db_storage_mtime_ns(db_storage_dir: Path) -> int:
    """Best-effort scan of db_storage for a "latest mtime" signal.

    We intentionally restrict to common database buckets to reduce walk cost.
    """

    try:
        base = str(db_storage_dir)
    except Exception:
        return 0

    max_ns = 0
    try:
        for root, dirs, files in os.walk(base):
            if root == base:
                allow = {"message", "session", "contact", "head_image", "bizchat", "sns", "general", "favorite"}
                dirs[:] = [d for d in dirs if str(d or "").lower() in allow]

            for fn in files:
                name = str(fn or "").lower()
                if not name.endswith((".db", ".db-wal", ".db-shm")):
                    continue
                if not (
                    ("message" in name)
                    or ("session" in name)
                    or ("contact" in name)
                    or ("name2id" in name)
                    or ("head_image" in name)
                ):
                    continue

                try:
                    st = os.stat(os.path.join(root, fn))
                    m_ns = int(getattr(st, "st_mtime_ns", 0) or 0)
                    if m_ns <= 0:
                        m_ns = int(float(getattr(st, "st_mtime", 0.0) or 0.0) * 1_000_000_000)
                    if m_ns > max_ns:
                        max_ns = m_ns
                except Exception:
                    continue
    except Exception:
        return 0

    return max_ns


@dataclass
class _AccountState:
    last_mtime_ns: int = 0
    due_at: float = 0.0
    last_sync_end_at: float = 0.0
    thread: Optional[threading.Thread] = None


class ChatRealtimeAutoSyncService:
    def __init__(self) -> None:
        self._enabled = _env_bool("WECHAT_TOOL_REALTIME_AUTOSYNC", True)
        self._interval_ms = _env_int("WECHAT_TOOL_REALTIME_AUTOSYNC_INTERVAL_MS", 1000, min_v=200, max_v=10_000)
        self._debounce_ms = _env_int("WECHAT_TOOL_REALTIME_AUTOSYNC_DEBOUNCE_MS", 600, min_v=0, max_v=10_000)
        self._min_sync_interval_ms = _env_int(
            "WECHAT_TOOL_REALTIME_AUTOSYNC_MIN_SYNC_INTERVAL_MS", 800, min_v=0, max_v=60_000
        )
        self._workers = _env_int("WECHAT_TOOL_REALTIME_AUTOSYNC_WORKERS", 1, min_v=1, max_v=4)

        # Sync strategy defaults: cheap incremental write into decrypted sqlite.
        self._sync_max_scan = _env_int("WECHAT_TOOL_REALTIME_AUTOSYNC_MAX_SCAN", 200, min_v=20, max_v=5000)
        self._priority_max_scan = _env_int("WECHAT_TOOL_REALTIME_AUTOSYNC_PRIORITY_MAX_SCAN", 600, min_v=20, max_v=5000)
        self._backfill_limit = _env_int("WECHAT_TOOL_REALTIME_AUTOSYNC_BACKFILL_LIMIT", 0, min_v=0, max_v=5000)
        # Default to the same conservative filtering as the chat UI sidebar (avoid hammering gh_/hidden sessions).
        self._include_hidden = _env_bool("WECHAT_TOOL_REALTIME_AUTOSYNC_INCLUDE_HIDDEN", False)
        self._include_official = _env_bool("WECHAT_TOOL_REALTIME_AUTOSYNC_INCLUDE_OFFICIAL", False)

        self._mu = threading.Lock()
        self._states: dict[str, _AccountState] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self._enabled:
            logger.info("[realtime-autosync] disabled by env WECHAT_TOOL_REALTIME_AUTOSYNC=0")
            return

        with self._mu:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="realtime-autosync", daemon=True)
            self._thread.start()

        logger.info(
            "[realtime-autosync] started interval_ms=%s debounce_ms=%s min_sync_interval_ms=%s max_scan=%s backfill_limit=%s workers=%s",
            int(self._interval_ms),
            int(self._debounce_ms),
            int(self._min_sync_interval_ms),
            int(self._sync_max_scan),
            int(self._backfill_limit),
            int(self._workers),
        )

    def stop(self) -> None:
        with self._mu:
            th = self._thread
            self._thread = None

        if th is None:
            return

        self._stop.set()
        try:
            th.join(timeout=5.0)
        except Exception:
            pass

        logger.info("[realtime-autosync] stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            tick_t0 = time.perf_counter()
            try:
                self._tick()
            except Exception:
                logger.exception("[realtime-autosync] tick failed")

            # Avoid busy looping on exceptions; keep a minimum sleep.
            elapsed_ms = (time.perf_counter() - tick_t0) * 1000.0
            sleep_ms = max(100.0, float(self._interval_ms) - elapsed_ms)
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

            scan_t0 = time.perf_counter()
            mtime_ns = _scan_db_storage_mtime_ns(db_storage_dir)
            scan_ms = (time.perf_counter() - scan_t0) * 1000.0
            if scan_ms > 2000:
                logger.warning("[realtime-autosync] scan slow account=%s ms=%.1f", acc, scan_ms)

            with self._mu:
                st = self._states.setdefault(acc, _AccountState())
                if mtime_ns and mtime_ns != st.last_mtime_ns:
                    st.last_mtime_ns = int(mtime_ns)
                    st.due_at = now + (float(self._debounce_ms) / 1000.0)

        # Schedule daemon threads. (Important: do NOT use ThreadPoolExecutor here; its threads are non-daemon on
        # Windows/Python 3.12 and can prevent Ctrl+C from stopping the process.)
        to_start: list[threading.Thread] = []
        with self._mu:
            # Drop state for removed accounts to keep memory bounded.
            keep = set(accounts)
            for acc in list(self._states.keys()):
                if acc not in keep:
                    self._states.pop(acc, None)

            # Clean up finished threads and compute current concurrency.
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
                    name=f"realtime-autosync-{acc}",
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
                # Best-effort: if a thread fails to start, clear the state so we can retry later.
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
            inserted = int((res or {}).get("inserted_total") or (res or {}).get("insertedTotal") or 0)
            synced = int((res or {}).get("synced") or (res or {}).get("sessionsSynced") or 0)
            logger.info("[realtime-autosync] sync done account=%s synced=%s inserted=%s", account, synced, inserted)
        except Exception:
            logger.exception("[realtime-autosync] sync failed account=%s", account)
        finally:
            with self._mu:
                st = self._states.get(account)
                if st is not None:
                    st.thread = None
                    st.last_sync_end_at = time.time()

    def _sync_account(self, account: str) -> dict[str, Any]:
        """Run a cheap incremental sync_all for one account."""

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

        # Import lazily to avoid any startup import ordering issues.
        from .routers.chat import sync_chat_realtime_messages_all

        try:
            return sync_chat_realtime_messages_all(
                request=None,  # not used by the handler logic; we run it as an internal job
                account=account,
                max_scan=int(self._sync_max_scan),
                priority_username=None,
                priority_max_scan=int(self._priority_max_scan),
                include_hidden=bool(self._include_hidden),
                include_official=bool(self._include_official),
                backfill_limit=int(self._backfill_limit),
            )
        except HTTPException as e:
            return {"status": "error", "error": str(e.detail or "")}
        except Exception as e:
            return {"status": "error", "error": str(e)}


CHAT_REALTIME_AUTOSYNC = ChatRealtimeAutoSyncService()
