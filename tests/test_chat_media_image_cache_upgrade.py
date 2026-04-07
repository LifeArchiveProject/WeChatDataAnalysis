import hashlib
import importlib
import json
import logging
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatMediaImageCacheUpgrade(unittest.TestCase):
    def assert_cacheable_chat_image_response(self, resp) -> None:
        self.assertEqual(resp.headers.get("cache-control"), "private, max-age=86400")
        self.assertTrue(str(resp.headers.get("etag") or "").strip())

    def _seed_contact_db(self, path: Path, *, account: str, username: str) -> None:
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
                (account, "", "我", "", 1, 0, "", ""),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (username, "", "测试好友", "", 1, 0, "", ""),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_session_db(self, path: Path, *, username: str) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE SessionTable (
                    username TEXT,
                    is_hidden INTEGER,
                    sort_timestamp INTEGER
                )
                """
            )
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", (username, 0, 1735689600))
            conn.commit()
        finally:
            conn.close()

    def _seed_source_info(self, account_dir: Path, *, wxid_dir: Path) -> None:
        payload = {
            "wxid_dir": str(wxid_dir),
            "db_storage_path": "",
        }
        (account_dir / "_source.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _seed_cached_resource(self, account_dir: Path, *, md5: str, payload: bytes) -> Path:
        resource_dir = account_dir / "resource" / md5[:2]
        resource_dir.mkdir(parents=True, exist_ok=True)
        target = resource_dir / f"{md5}.jpg"
        target.write_bytes(payload)
        return target

    def _seed_live_variant(self, wxid_dir: Path, *, username: str, md5: str, suffix: str, payload: bytes) -> Path:
        chat_hash = hashlib.md5(username.encode("utf-8")).hexdigest()
        target = wxid_dir / "msg" / "attach" / chat_hash / "2026-03" / "Img" / f"{md5}{suffix}.dat"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target

    def _build_client(self):
        import wechat_decrypt_tool.logging_config as logging_config
        import wechat_decrypt_tool.app_paths as app_paths
        import wechat_decrypt_tool.media_helpers as media_helpers
        import wechat_decrypt_tool.routers.chat_media as chat_media

        logging.shutdown()
        importlib.reload(logging_config)
        importlib.reload(app_paths)
        importlib.reload(media_helpers)
        importlib.reload(chat_media)

        app = FastAPI()
        app.include_router(chat_media.router)
        return TestClient(app)

    def test_live_high_variant_replaces_stale_cached_thumb(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            md5 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

            account_dir = root / "output" / "databases" / account
            wxid_dir = root / "wxid_source"
            account_dir.mkdir(parents=True, exist_ok=True)
            wxid_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
            self._seed_session_db(account_dir / "session.db", username=username)
            self._seed_source_info(account_dir, wxid_dir=wxid_dir)

            cached_thumb = b"\xff\xd8\xff\xd9"
            live_original = b"\xff\xd8\xff\xe0" + (b"\x00" * 48) + b"\xff\xd9"
            cache_path = self._seed_cached_resource(account_dir, md5=md5, payload=cached_thumb)
            self._seed_live_variant(wxid_dir, username=username, md5=md5, suffix="_h", payload=live_original)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            client = None
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                client = self._build_client()
                resp = client.get(
                    "/api/chat/media/image",
                    params={"account": account, "md5": md5, "username": username},
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.content, live_original)
                self.assert_cacheable_chat_image_response(resp)
                self.assertEqual(cache_path.read_bytes(), live_original)
            finally:
                try:
                    client.close()
                except Exception:
                    pass
                logging.shutdown()
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_cached_original_is_not_downgraded_by_live_thumb(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            md5 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

            account_dir = root / "output" / "databases" / account
            wxid_dir = root / "wxid_source"
            account_dir.mkdir(parents=True, exist_ok=True)
            wxid_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
            self._seed_session_db(account_dir / "session.db", username=username)
            self._seed_source_info(account_dir, wxid_dir=wxid_dir)

            cached_original = b"\xff\xd8\xff\xe0" + (b"\x11" * 64) + b"\xff\xd9"
            live_thumb = b"\xff\xd8\xff\xd9"
            cache_path = self._seed_cached_resource(account_dir, md5=md5, payload=cached_original)
            self._seed_live_variant(wxid_dir, username=username, md5=md5, suffix="_t", payload=live_thumb)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            client = None
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                client = self._build_client()
                resp = client.get(
                    "/api/chat/media/image",
                    params={"account": account, "md5": md5, "username": username},
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.content, cached_original)
                self.assert_cacheable_chat_image_response(resp)
                self.assertEqual(cache_path.read_bytes(), cached_original)
            finally:
                try:
                    client.close()
                except Exception:
                    pass
                logging.shutdown()
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_chat_image_supports_etag_revalidation(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            md5 = "cccccccccccccccccccccccccccccccc"

            account_dir = root / "output" / "databases" / account
            wxid_dir = root / "wxid_source"
            account_dir.mkdir(parents=True, exist_ok=True)
            wxid_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
            self._seed_session_db(account_dir / "session.db", username=username)
            self._seed_source_info(account_dir, wxid_dir=wxid_dir)

            cached_original = b"\xff\xd8\xff\xe0" + (b"\x22" * 64) + b"\xff\xd9"
            self._seed_cached_resource(account_dir, md5=md5, payload=cached_original)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            client = None
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                client = self._build_client()
                first = client.get(
                    "/api/chat/media/image",
                    params={"account": account, "md5": md5, "username": username},
                )
                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.content, cached_original)
                self.assert_cacheable_chat_image_response(first)

                etag = str(first.headers.get("etag") or "").strip()
                second = client.get(
                    "/api/chat/media/image",
                    params={"account": account, "md5": md5, "username": username},
                    headers={"If-None-Match": etag},
                )
                self.assertEqual(second.status_code, 304)
                self.assertEqual(second.content, b"")
                self.assertEqual(second.headers.get("etag"), etag)
                self.assertEqual(second.headers.get("cache-control"), "private, max-age=86400")
            finally:
                try:
                    client.close()
                except Exception:
                    pass
                logging.shutdown()
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data


if __name__ == "__main__":
    unittest.main()
