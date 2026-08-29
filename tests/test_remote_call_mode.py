import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestRemoteCallMode(unittest.TestCase):
    def setUp(self) -> None:
        self._previous = os.environ.get("WECHAT_TOOL_ALLOW_REMOTE_CALLS")
        os.environ["WECHAT_TOOL_ALLOW_REMOTE_CALLS"] = "1"

        import wechat_decrypt_tool.runtime_settings as runtime_settings
        import wechat_decrypt_tool.routers.admin as admin_router
        import wechat_decrypt_tool.routers.chat_media as chat_media

        importlib.reload(runtime_settings)
        importlib.reload(admin_router)
        importlib.reload(chat_media)
        self.runtime_settings = runtime_settings
        self.admin_router = admin_router
        self.chat_media = chat_media

    def tearDown(self) -> None:
        if self._previous is None:
            os.environ.pop("WECHAT_TOOL_ALLOW_REMOTE_CALLS", None)
        else:
            os.environ["WECHAT_TOOL_ALLOW_REMOTE_CALLS"] = self._previous

    def test_remote_mode_uses_lan_default_and_relaxes_caller_location_guards(self) -> None:
        self.assertEqual(self.runtime_settings.default_backend_host(), "0.0.0.0")

        app = FastAPI()
        app.include_router(self.admin_router.router)
        client = TestClient(app, client=("203.0.113.8", 52001))
        with patch.object(self.admin_router, "_open_path_with_default_app"):
            response = client.post("/api/admin/log-file/open")
        self.assertEqual(response.status_code, 200)

        request = type("Request", (), {"client": type("Client", (), {"host": "203.0.113.8"})(), "headers": {"origin": "https://remote.example"}})()
        self.chat_media._require_local_voice_mutation(request)


if __name__ == "__main__":
    unittest.main()
