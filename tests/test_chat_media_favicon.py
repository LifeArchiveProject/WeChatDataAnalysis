import os
import sqlite3
import sys
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, headers: dict | None = None, url: str = "", body: bytes = b""):
        self.status_code = int(status_code)
        self.headers = dict(headers or {})
        self.url = str(url or "")
        self._body = bytes(body or b"")

    def iter_content(self, chunk_size: int = 64 * 1024):
        yield self._body

    def close(self) -> None:
        return None


class TestChatMediaFavicon(unittest.TestCase):
    def test_chat_media_favicon_caches(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # 1x1 PNG (same as other avatar cache tests)
        png = bytes.fromhex(
            "89504E470D0A1A0A"
            "0000000D49484452000000010000000108060000001F15C489"
            "0000000D49444154789C6360606060000000050001A5F64540"
            "0000000049454E44AE426082"
        )

        with TemporaryDirectory() as td:
            root = Path(td)

            prev_data = None
            prev_cache = None
            try:
                prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
                prev_cache = os.environ.get("WECHAT_TOOL_AVATAR_CACHE_ENABLED")
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                os.environ["WECHAT_TOOL_AVATAR_CACHE_ENABLED"] = "1"

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.avatar_cache as avatar_cache
                import wechat_decrypt_tool.routers.chat_media as chat_media

                importlib.reload(app_paths)
                importlib.reload(avatar_cache)
                importlib.reload(chat_media)

                def fake_head(url, **_kwargs):
                    # Pretend short-link resolves to bilibili.
                    return _FakeResponse(
                        status_code=200,
                        headers={},
                        url="https://www.bilibili.com/video/BV1Au4tzNEq2",
                        body=b"",
                    )

                def fake_get(url, **_kwargs):
                    u = str(url or "")
                    if "www.bilibili.com/favicon.ico" in u:
                        return _FakeResponse(
                            status_code=200,
                            headers={"Content-Type": "image/png", "content-length": str(len(png))},
                            url=u,
                            body=png,
                        )
                    return _FakeResponse(
                        status_code=404,
                        headers={"Content-Type": "text/html"},
                        url=u,
                        body=b"",
                    )

                app = FastAPI()
                app.include_router(chat_media.router)
                client = TestClient(app)

                with patch("wechat_decrypt_tool.routers.chat_media.requests.head", side_effect=fake_head) as mock_head, patch(
                    "wechat_decrypt_tool.routers.chat_media.requests.get", side_effect=fake_get
                ) as mock_get:
                    resp = client.get("/api/chat/media/favicon", params={"url": "https://b23.tv/au68guF"})
                    self.assertEqual(resp.status_code, 200)
                    self.assertTrue(resp.headers.get("content-type", "").startswith("image/"))
                    self.assertEqual(resp.content, png)

                    # Second call should hit disk cache (no extra favicon download).
                    resp2 = client.get("/api/chat/media/favicon", params={"url": "https://b23.tv/au68guF"})
                    self.assertEqual(resp2.status_code, 200)
                    self.assertEqual(resp2.content, png)

                    self.assertGreaterEqual(mock_head.call_count, 1)
                    self.assertEqual(mock_get.call_count, 1)

                cache_db = root / "output" / "avatar_cache" / "favicon" / "avatar_cache.db"
                self.assertTrue(cache_db.exists())

                conn = sqlite3.connect(str(cache_db))
                try:
                    row = conn.execute(
                        "SELECT source_kind, source_url, media_type FROM avatar_cache_entries WHERE source_kind = 'url' LIMIT 1"
                    ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(str(row[0] or ""), "url")
                    self.assertIn("favicon.ico", str(row[1] or ""))
                    self.assertTrue(str(row[2] or "").startswith("image/"))
                finally:
                    conn.close()
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data
                if prev_cache is None:
                    os.environ.pop("WECHAT_TOOL_AVATAR_CACHE_ENABLED", None)
                else:
                    os.environ["WECHAT_TOOL_AVATAR_CACHE_ENABLED"] = prev_cache


if __name__ == "__main__":
    unittest.main()

