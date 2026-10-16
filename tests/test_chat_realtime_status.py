import asyncio
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import chat as chat_router


class TestChatRealtimeStatus(unittest.TestCase):
    def test_initial_status_inspection_obeys_endpoint_deadline(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_initial_status_timeout"
            account_dir.mkdir()
            status_started = threading.Event()
            release_status = threading.Event()

            def blocking_status(*_args, **_kwargs):
                status_started.set()
                release_status.wait(timeout=2.0)
                return {"connected": False}

            async def run_status():
                result = await chat_router.get_chat_realtime_status(account_dir.name)
                release_status.set()
                for _ in range(100):
                    if not chat_router._REALTIME_STATUS_PROBE_TASKS:
                        break
                    await asyncio.sleep(0.01)
                return result

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", side_effect=blocking_status),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected") as ensure_connected,
                patch.object(chat_router, "_REALTIME_STATUS_PROBE_WAIT_SECONDS", 0.2),
            ):
                started_at = time.monotonic()
                result = asyncio.run(run_status())
                elapsed = time.monotonic() - started_at

        self.assertTrue(status_started.is_set())
        self.assertLess(elapsed, 1.0)
        ensure_connected.assert_not_called()
        self.assertIs(result["available"], False)
        self.assertIn("status inspection timed out", result["realtime"]["probe_error"])
        self.assertFalse(chat_router._REALTIME_STATUS_PROBE_TASKS)

    def test_final_status_refresh_obeys_remaining_endpoint_deadline(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_final_status_timeout"
            account_dir.mkdir()
            ready = {
                "dll_present": True,
                "key_present": True,
                "db_storage_dir": str(account_dir / "db_storage"),
                "session_db_path": str(account_dir / "db_storage" / "session.db"),
                "connected": False,
            }
            status_calls = 0
            refresh_started = threading.Event()
            release_refresh = threading.Event()

            def status_then_block(*_args, **_kwargs):
                nonlocal status_calls
                status_calls += 1
                if status_calls == 1:
                    return ready
                refresh_started.set()
                release_refresh.wait(timeout=2.0)
                return {**ready, "connected": True}

            async def run_status():
                result = await chat_router.get_chat_realtime_status(account_dir.name)
                release_refresh.set()
                for _ in range(100):
                    if not chat_router._REALTIME_STATUS_PROBE_TASKS:
                        break
                    await asyncio.sleep(0.01)
                return result

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", side_effect=status_then_block),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=object()) as ensure_connected,
                patch.object(chat_router, "_REALTIME_STATUS_PROBE_WAIT_SECONDS", 1.0),
            ):
                started_at = time.monotonic()
                result = asyncio.run(run_status())
                elapsed = time.monotonic() - started_at

        self.assertTrue(refresh_started.is_set())
        self.assertLess(elapsed, 1.8)
        ensure_connected.assert_called_once()
        self.assertIs(result["available"], False)
        self.assertIn("status refresh timed out", result["realtime"]["probe_error"])
        self.assertFalse(chat_router._REALTIME_STATUS_PROBE_TASKS)

    def test_status_probe_has_wall_clock_timeout_and_reaps_background_task(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_timeout"
            account_dir.mkdir()
            ready = {
                "dll_present": True,
                "key_present": True,
                "db_storage_dir": str(account_dir / "db_storage"),
                "session_db_path": str(account_dir / "db_storage" / "session.db"),
                "connected": False,
            }
            probe_started = threading.Event()
            release_probe = threading.Event()

            def blocking_probe(*_args, **_kwargs):
                probe_started.set()
                release_probe.wait(timeout=2.0)
                return object()

            async def run_probe():
                result = await chat_router.get_chat_realtime_status("wxid_timeout")
                release_probe.set()
                for _ in range(100):
                    if not chat_router._REALTIME_STATUS_PROBE_TASKS:
                        break
                    await asyncio.sleep(0.01)
                return result

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", side_effect=[ready, ready]),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", side_effect=blocking_probe),
                patch.object(chat_router, "_REALTIME_STATUS_PROBE_WAIT_SECONDS", 1.0),
            ):
                started_at = time.monotonic()
                result = asyncio.run(run_probe())
                elapsed = time.monotonic() - started_at

        self.assertTrue(probe_started.is_set())
        self.assertLess(elapsed, 1.8)
        self.assertIs(result["available"], False)
        self.assertIn("timed out", result["realtime"]["probe_error"])
        self.assertFalse(chat_router._REALTIME_STATUS_PROBE_TASKS)

    def test_status_opens_wcdb_before_reporting_available(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir()
            ready = {
                "dll_present": True,
                "key_present": True,
                "db_storage_dir": str(account_dir / "db_storage"),
                "session_db_path": str(account_dir / "db_storage" / "session.db"),
                "connected": False,
            }
            connected = {**ready, "connected": True}

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", side_effect=[ready, connected]),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=object()) as ensure,
            ):
                result = asyncio.run(chat_router.get_chat_realtime_status("wxid_demo"))

        ensure.assert_called_once_with(account_dir, timeout=5.0)
        self.assertIs(result["available"], True)
        self.assertIs(result["realtime"]["probe_attempted"], True)
        self.assertIs(result["realtime"]["probe_succeeded"], True)

    def test_status_reports_open_failure_as_unavailable(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir()
            ready = {
                "dll_present": True,
                "key_present": True,
                "db_storage_dir": str(account_dir / "db_storage"),
                "session_db_path": str(account_dir / "db_storage" / "session.db"),
                "connected": False,
            }

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", side_effect=[ready, ready]),
                patch.object(
                    chat_router.WCDB_REALTIME,
                    "ensure_connected",
                    side_effect=chat_router.WCDBRealtimeError("native library load failed"),
                ),
            ):
                result = asyncio.run(chat_router.get_chat_realtime_status("wxid_demo"))

        self.assertIs(result["available"], False)
        self.assertIs(result["realtime"]["probe_attempted"], True)
        self.assertIs(result["realtime"]["probe_succeeded"], False)
        self.assertIn("native library load failed", result["realtime"]["probe_error"])

    def test_status_skips_probe_when_prerequisites_are_missing(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir()
            missing_key = {
                "dll_present": True,
                "key_present": False,
                "db_storage_dir": str(account_dir / "db_storage"),
                "session_db_path": str(account_dir / "db_storage" / "session.db"),
                "connected": False,
            }

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "get_status", return_value=missing_key),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected") as ensure,
            ):
                result = asyncio.run(chat_router.get_chat_realtime_status("wxid_demo"))

        ensure.assert_not_called()
        self.assertIs(result["available"], False)
        self.assertIs(result["realtime"]["probe_attempted"], False)


if __name__ == "__main__":
    unittest.main()
