import os
import sqlite3
import sys
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestAvatarCacheChatMedia(unittest.TestCase):
    def _seed_contact_db(self, path: Path, *, username: str = "wxid_friend") -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE contact (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE stranger (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    username,
                    "",
                    "测试好友",
                    "",
                    1,
                    0,
                    "https://wx.qlogo.cn/mmhead/ver_1/test_remote_avatar/132",
                    "",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_session_db(self, path: Path, *, username: str = "wxid_friend") -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE SessionTable (
                    username TEXT,
                    sort_timestamp INTEGER,
                    last_timestamp INTEGER
                )
                """
            )
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", (username, 200, 200))
            conn.commit()
        finally:
            conn.close()

    def _seed_head_image_db(self, path: Path, *, username: str = "wxid_friend") -> None:
        # 1x1 PNG
        png = bytes.fromhex(
            "89504E470D0A1A0A"
            "0000000D49484452000000010000000108060000001F15C489"
            "0000000D49444154789C6360606060000000050001A5F64540"
            "0000000049454E44AE426082"
        )
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE head_image(username TEXT PRIMARY KEY, md5 TEXT, image_buffer BLOB, update_time INTEGER)")
            conn.execute(
                "INSERT INTO head_image VALUES (?, ?, ?, ?)",
                (username, "0123456789abcdef0123456789abcdef", sqlite3.Binary(png), 1735689600),
            )
            conn.commit()
        finally:
            conn.close()

    def test_chat_avatar_caches_to_output_avatar_cache(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", username=username)
            self._seed_session_db(account_dir / "session.db", username=username)
            self._seed_head_image_db(account_dir / "head_image.db", username=username)

            prev_data = None
            prev_cache = None
            try:
                prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
                prev_cache = os.environ.get("WECHAT_TOOL_AVATAR_CACHE_ENABLED")
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                os.environ["WECHAT_TOOL_AVATAR_CACHE_ENABLED"] = "1"

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.avatar_cache as avatar_cache
                import wechat_decrypt_tool.routers.chat_media as chat_media

                importlib.reload(app_paths)
                importlib.reload(chat_helpers)
                importlib.reload(avatar_cache)
                importlib.reload(chat_media)

                app = FastAPI()
                app.include_router(chat_media.router)
                client = TestClient(app)

                resp = client.get("/api/chat/avatar", params={"account": account, "username": username})
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.headers.get("content-type", "").startswith("image/"))

                cache_db = root / "output" / "avatar_cache" / account / "avatar_cache.db"
                self.assertTrue(cache_db.exists())

                conn = sqlite3.connect(str(cache_db))
                try:
                    row = conn.execute(
                        "SELECT cache_key, source_kind, username, rel_path, media_type FROM avatar_cache_entries WHERE source_kind = 'user' LIMIT 1"
                    ).fetchone()
                    self.assertIsNotNone(row)
                    rel_path = str(row[3] or "")
                finally:
                    conn.close()

                self.assertTrue(rel_path)
                cache_file = (root / "output" / "avatar_cache" / account / rel_path).resolve()
                self.assertTrue(cache_file.exists())

                resp2 = client.get("/api/chat/avatar", params={"account": account, "username": username})
                self.assertEqual(resp2.status_code, 200)
                self.assertEqual(resp2.content, resp.content)
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

