import importlib
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close_logging_handlers() -> None:
    import logging

    for logger_name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(logger_name)
        for h in lg.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            try:
                lg.removeHandler(h)
            except Exception:
                pass


class TestAdminServerErrorLogging(unittest.TestCase):
    def setUp(self):
        self._prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
        self._td = TemporaryDirectory()
        os.environ["WECHAT_TOOL_DATA_DIR"] = self._td.name

        import wechat_decrypt_tool.app_paths as app_paths
        import wechat_decrypt_tool.logging_config as logging_config
        import wechat_decrypt_tool.request_logging as request_logging
        import wechat_decrypt_tool.routers.admin as admin_router

        importlib.reload(app_paths)
        importlib.reload(logging_config)
        importlib.reload(request_logging)
        importlib.reload(admin_router)

        self.logging_config = logging_config
        self.request_logging = request_logging
        self.admin_router = admin_router
        self.log_file = self.logging_config.setup_logging()

    def tearDown(self):
        _close_logging_handlers()

        if self._prev_data_dir is None:
            os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
        else:
            os.environ["WECHAT_TOOL_DATA_DIR"] = self._prev_data_dir

        self._td.cleanup()

    def _read_log(self) -> str:
        return self.log_file.read_text(encoding="utf-8")

    def _make_admin_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(self.admin_router.router)
        return app

    def _make_logged_app(self) -> FastAPI:
        app = FastAPI()

        @app.middleware("http")
        async def _log_server_errors(request, call_next):
            return await self.request_logging.log_server_errors_middleware(
                self.logging_config.get_logger("tests.server_error_logging"),
                request,
                call_next,
            )

        @app.get("/boom-http")
        async def _boom_http():
            raise HTTPException(status_code=500, detail="planned http failure")

        @app.get("/boom-exception")
        async def _boom_exception():
            raise RuntimeError("planned unhandled failure")

        return app

    def test_get_log_file_returns_current_backend_log_path(self):
        client = TestClient(self._make_admin_app(), client=("127.0.0.1", 52000))

        resp = client.get("/api/admin/log-file")

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(Path(payload["path"]), self.log_file)
        self.assertTrue(payload["exists"])
        self.assertTrue(self.log_file.is_relative_to(Path(self._td.name) / "output" / "logs"))

    def test_open_log_file_requires_loopback(self):
        client = TestClient(self._make_admin_app(), client=("203.0.113.8", 52001))

        resp = client.post("/api/admin/log-file/open")

        self.assertEqual(resp.status_code, 403)

    def test_open_log_file_uses_default_opener_for_loopback(self):
        client = TestClient(self._make_admin_app(), client=("127.0.0.1", 52002))

        with patch.object(self.admin_router, "_open_path_with_default_app") as mocked_open:
            resp = client.post("/api/admin/log-file/open")

        self.assertEqual(resp.status_code, 200)
        mocked_open.assert_called_once_with(self.log_file)
        self.assertEqual(resp.json()["path"], str(self.log_file))

    def test_frontend_server_error_endpoint_writes_log(self):
        client = TestClient(self._make_admin_app(), client=("127.0.0.1", 52003))

        resp = client.post(
            "/api/admin/log-frontend-server-error",
            json={
                "status": 503,
                "method": "GET",
                "request_url": "http://127.0.0.1:10392/api/chat/accounts",
                "message": "fetch failed",
                "backend_detail": "upstream timeout",
                "source": "useApi",
                "page_url": "http://127.0.0.1:10392/chat",
            },
        )

        self.assertEqual(resp.status_code, 200)
        text = self._read_log()
        self.assertIn("[frontend-server-error]", text)
        self.assertIn("status=503", text)
        self.assertIn("source=useApi", text)
        self.assertIn("upstream timeout", text)

    def test_http_500_response_is_logged(self):
        client = TestClient(self._make_logged_app(), client=("127.0.0.1", 52004))

        resp = client.get("/boom-http")

        self.assertEqual(resp.status_code, 500)
        text = self._read_log()
        self.assertIn("[server-5xx]", text)
        self.assertIn("status=500", text)
        self.assertIn("path=/boom-http", text)
        self.assertIn("planned http failure", text)

    def test_unhandled_exception_is_logged_with_traceback(self):
        client = TestClient(
            self._make_logged_app(),
            client=("127.0.0.1", 52005),
            raise_server_exceptions=False,
        )

        resp = client.get("/boom-exception")

        self.assertEqual(resp.status_code, 500)
        text = self._read_log()
        self.assertIn("[server-exception]", text)
        self.assertIn("path=/boom-exception", text)
        self.assertIn("planned unhandled failure", text)
        self.assertIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
