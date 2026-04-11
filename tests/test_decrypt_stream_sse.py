import json
import logging
import os
import sqlite3
import sys
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory


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

