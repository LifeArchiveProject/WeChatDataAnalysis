import asyncio
import json
import logging
import os
import sqlite3
import sys
import threading
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close_logging_handlers() -> None:
    for logger_name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(logger_name)
        for handler in lg.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            try:
                lg.removeHandler(handler)
            except Exception:
                pass


class TestDecryptStreamSSE(unittest.TestCase):
    def test_cancelled_while_waiting_for_guard_releases_guard_after_acquire(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            db_storage = root / "db_storage"
            db_storage.mkdir(parents=True)
            db_path = db_storage / "MSG0.db"
            db_path.write_bytes(b"source")

            import wechat_decrypt_tool.routers.decrypt as decrypt_router

            acquire_started = threading.Event()
            allow_acquire_finish = threading.Event()
            acquire_finished = threading.Event()
            guard_released = threading.Event()
            release_calls = []

            class ConnectedRequest:
                async def is_disconnected(self):
                    return False

            scan_result = {
                "status": "success",
                "account_databases": {
                    "wxid_waiting_guard": [{"path": str(db_path), "name": db_path.name}],
                },
                "account_sources": {
                    "wxid_waiting_guard": {
                        "db_storage_path": str(db_storage),
                        "wxid_dir": str(db_storage.parent),
                    },
                },
            }
            fake_guards = [("wxid_waiting_guard", object())]

            def acquire_guard(_accounts, *, reason):
                self.assertEqual(reason, "decrypt:sse")
                acquire_started.set()
                if not allow_acquire_finish.wait(timeout=5):
                    raise TimeoutError("test guard acquisition was not released")
                acquire_finished.set()
                return fake_guards

            def record_guard_release(guards, *, reason):
                release_calls.append((guards, reason))
                guard_released.set()

            async def scenario():
                response = await decrypt_router.decrypt_databases_stream(
                    ConnectedRequest(),
                    key="00" * 32,
                    db_storage_path=str(db_storage),
                )

                async def consume_stream():
                    async for _chunk in response.body_iterator:
                        pass

                consumer = asyncio.create_task(consume_stream())
                try:
                    started = await asyncio.to_thread(acquire_started.wait, 2)
                    self.assertTrue(started, "guard acquisition did not start")

                    consumer.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await consumer

                    self.assertFalse(guard_released.is_set())
                    allow_acquire_finish.set()

                    finished = await asyncio.to_thread(acquire_finished.wait, 2)
                    self.assertTrue(finished, "guard acquisition did not finish")
                    released = await asyncio.to_thread(guard_released.wait, 2)
                    self.assertTrue(released, "acquired guard was leaked after stream cancellation")
                    self.assertEqual(release_calls, [(fake_guards, "decrypt:sse-disconnected")])
                finally:
                    allow_acquire_finish.set()
                    if not consumer.done():
                        consumer.cancel()
                    await asyncio.gather(consumer, return_exceptions=True)
                    pending_cleanups = list(decrypt_router._DEFERRED_DECRYPT_CLEANUPS)
                    if pending_cleanups:
                        await asyncio.gather(*pending_cleanups, return_exceptions=True)

            with (
                mock.patch.object(decrypt_router, "scan_account_databases_from_path", return_value=scan_result),
                mock.patch.object(decrypt_router, "_acquire_decrypt_account_guards", side_effect=acquire_guard),
                mock.patch.object(decrypt_router, "_release_decrypt_account_guards", side_effect=record_guard_release),
            ):
                asyncio.run(scenario())

    def test_cancelled_stream_holds_guard_until_worker_finishes(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            db_storage = root / "db_storage"
            db_storage.mkdir(parents=True)
            db_path = db_storage / "MSG0.db"
            db_path.write_bytes(b"source")

            import wechat_decrypt_tool.routers.decrypt as decrypt_router

            worker_started = threading.Event()
            allow_worker_finish = threading.Event()
            guard_released = threading.Event()
            release_calls = []

            class ConnectedRequest:
                async def is_disconnected(self):
                    return False

            class BlockingDecryptor:
                def __init__(self, _key):
                    self.last_result = {}

                def decrypt_database(self, _source, _target):
                    worker_started.set()
                    if not allow_worker_finish.wait(timeout=5):
                        raise TimeoutError("test worker was not released")
                    self.last_result = {"success": True, "diagnostic_status": "ok"}
                    return True

            scan_result = {
                "status": "success",
                "account_databases": {
                    "wxid_guard": [{"path": str(db_path), "name": db_path.name}],
                },
                "account_sources": {
                    "wxid_guard": {
                        "db_storage_path": str(db_storage),
                        "wxid_dir": str(db_storage.parent),
                    },
                },
            }
            fake_guards = [("wxid_guard", object())]

            def record_guard_release(guards, *, reason):
                release_calls.append((guards, reason))
                guard_released.set()

            async def scenario():
                response = await decrypt_router.decrypt_databases_stream(
                    ConnectedRequest(),
                    key="00" * 32,
                    db_storage_path=str(db_storage),
                )

                async def consume_stream():
                    async for _chunk in response.body_iterator:
                        pass

                consumer = asyncio.create_task(consume_stream())
                try:
                    started = await asyncio.to_thread(worker_started.wait, 2)
                    self.assertTrue(started, "decrypt worker did not start")

                    consumer.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await consumer

                    self.assertFalse(guard_released.is_set())
                    self.assertEqual(len(decrypt_router._DEFERRED_DECRYPT_CLEANUPS), 1)

                    allow_worker_finish.set()
                    released = await asyncio.to_thread(guard_released.wait, 2)
                    self.assertTrue(released, "guard was not released after worker completion")
                    self.assertEqual(release_calls, [(fake_guards, "decrypt:sse-disconnected")])

                    for _ in range(20):
                        if not decrypt_router._DEFERRED_DECRYPT_CLEANUPS:
                            break
                        await asyncio.sleep(0)
                    self.assertFalse(decrypt_router._DEFERRED_DECRYPT_CLEANUPS)
                finally:
                    allow_worker_finish.set()
                    if not consumer.done():
                        consumer.cancel()
                    await asyncio.gather(consumer, return_exceptions=True)
                    pending_cleanups = list(decrypt_router._DEFERRED_DECRYPT_CLEANUPS)
                    if pending_cleanups:
                        await asyncio.gather(*pending_cleanups, return_exceptions=True)

            prev_build_cache = os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE")
            try:
                os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = "0"
                with (
                    mock.patch.object(decrypt_router, "scan_account_databases_from_path", return_value=scan_result),
                    mock.patch.object(decrypt_router, "get_output_databases_dir", return_value=root / "output"),
                    mock.patch.object(decrypt_router, "WeChatDatabaseDecryptor", BlockingDecryptor),
                    mock.patch.object(decrypt_router, "_acquire_decrypt_account_guards", return_value=fake_guards),
                    mock.patch.object(decrypt_router, "_release_decrypt_account_guards", side_effect=record_guard_release),
                ):
                    asyncio.run(scenario())
            finally:
                if prev_build_cache is None:
                    os.environ.pop("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", None)
                else:
                    os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = prev_build_cache

    def test_decrypt_stream_reports_progress(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            prev_build_cache = os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = "0"

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.routers.decrypt as decrypt_router

                importlib.reload(app_paths)
                importlib.reload(decrypt_router)

                db_storage = root / "xwechat_files" / "wxid_foo_bar" / "db_storage"
                db_storage.mkdir(parents=True, exist_ok=True)

                db_path = db_storage / "MSG0.db"
                conn = sqlite3.connect(str(db_path))
                try:
                    conn.execute("CREATE TABLE demo(id INTEGER PRIMARY KEY, value TEXT)")
                    conn.execute("INSERT INTO demo(value) VALUES ('ok')")
                    conn.commit()
                finally:
                    conn.close()

                app = FastAPI()
                app.include_router(decrypt_router.router)
                client = TestClient(app)

                events: list[dict] = []
                with mock.patch.object(decrypt_router, "upsert_account_keys_in_store") as upsert_mock:
                    with client.stream(
                        "GET",
                        "/api/decrypt_stream",
                        params={"key": "00" * 32, "db_storage_path": str(db_storage)},
                    ) as resp:
                        self.assertEqual(resp.status_code, 200)
                        self.assertIn("text/event-stream", resp.headers.get("content-type", ""))

                        for line in resp.iter_lines():
                            if not line:
                                continue
                            if isinstance(line, bytes):
                                line = line.decode("utf-8", errors="ignore")
                            line = str(line)

                            if line.startswith(":"):
                                continue
                            if not line.startswith("data: "):
                                continue
                            payload = json.loads(line[len("data: ") :])
                            events.append(payload)
                            if payload.get("type") in {"complete", "error"}:
                                break

                types = {e.get("type") for e in events}
                self.assertIn("start", types)
                self.assertIn("progress", types)
                self.assertEqual(events[-1].get("type"), "complete")
                self.assertEqual(events[-1].get("status"), "completed")
                upsert_mock.assert_called_once_with(
                    "wxid_foo",
                    db_key="00" * 32,
                    aliases=["wxid_foo_bar"],
                    db_key_source_wxid_dir=str(db_storage.parent),
                    db_key_source_db_storage_path=str(db_storage),
                )

                out = root / "output" / "databases" / "wxid_foo" / "MSG0.db"
                self.assertTrue(out.exists())
            finally:
                _close_logging_handlers()
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir
                if prev_build_cache is None:
                    os.environ.pop("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", None)
                else:
                    os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = prev_build_cache

    def test_decrypt_stream_marks_invalid_output_as_failed(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            prev_build_cache = os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = "0"

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.routers.decrypt as decrypt_router

                importlib.reload(app_paths)
                importlib.reload(decrypt_router)

                db_storage = root / "xwechat_files" / "wxid_bad_case" / "db_storage"
                db_storage.mkdir(parents=True, exist_ok=True)
                (db_storage / "MSG0.db").write_bytes(b"\x01" * 4096)

                app = FastAPI()
                app.include_router(decrypt_router.router)
                client = TestClient(app)

                events: list[dict] = []
                with mock.patch.object(decrypt_router, "upsert_account_keys_in_store") as upsert_mock:
                    with client.stream(
                        "GET",
                        "/api/decrypt_stream",
                        params={"key": "00" * 32, "db_storage_path": str(db_storage)},
                    ) as resp:
                        self.assertEqual(resp.status_code, 200)
                        self.assertIn("text/event-stream", resp.headers.get("content-type", ""))

                        for line in resp.iter_lines():
                            if not line:
                                continue
                            if isinstance(line, bytes):
                                line = line.decode("utf-8", errors="ignore")
                            line = str(line)

                            if line.startswith(":"):
                                continue
                            if not line.startswith("data: "):
                                continue
                            payload = json.loads(line[len("data: ") :])
                            events.append(payload)
                            if payload.get("type") in {"complete", "error"}:
                                break

                self.assertEqual(events[-1].get("type"), "complete")
                self.assertEqual(events[-1].get("status"), "failed")
                self.assertEqual(events[-1].get("success_count"), 0)
                self.assertEqual(events[-1].get("failure_count"), 1)
                self.assertIn("密钥可能不匹配", str(events[-1].get("message") or ""))
                upsert_mock.assert_not_called()

                out = root / "output" / "databases" / "wxid_bad" / "MSG0.db"
                self.assertFalse(out.exists())
            finally:
                _close_logging_handlers()
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir
                if prev_build_cache is None:
                    os.environ.pop("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", None)
                else:
                    os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = prev_build_cache


if __name__ == "__main__":
    unittest.main()

