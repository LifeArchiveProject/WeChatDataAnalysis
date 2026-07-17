import sqlite3
import sys
import threading
import unittest
import re
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import sns as sns_router
from wechat_decrypt_tool.routers import chat_media as chat_media_router


class TestSnsPageDecryptedSource(unittest.TestCase):
    def test_self_info_decrypted_sources_never_open_wcdb(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            conn = sqlite3.connect(str(account_dir / "contact.db"))
            try:
                conn.execute(
                    "CREATE TABLE contact ("
                    "username TEXT, remark TEXT, nick_name TEXT, alias TEXT"
                    ")"
                )
                conn.execute(
                    "INSERT INTO contact VALUES (?, ?, ?, ?)",
                    (account_dir.name, "", "Local nickname", "local_alias"),
                )
                conn.commit()
            finally:
                conn.close()

            for requested_source in ("decrypted", "local", "sqlite"):
                with self.subTest(source=requested_source):
                    with (
                        mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                        mock.patch.object(sns_router.WCDB_REALTIME, "get_status") as get_status,
                        mock.patch.object(
                            sns_router.WCDB_REALTIME,
                            "ensure_connected",
                            side_effect=AssertionError("decrypted self_info must not open WCDB"),
                        ) as ensure_connected,
                        mock.patch.object(sns_router, "_wcdb_get_display_names") as get_display_names,
                    ):
                        response = sns_router.api_sns_self_info(
                            account=account_dir.name,
                            source=requested_source,
                        )

                    get_status.assert_not_called()
                    ensure_connected.assert_not_called()
                    get_display_names.assert_not_called()
                    self.assertEqual(response.get("nickname"), "Local nickname")
                    self.assertEqual(response.get("source"), "contact_db_nickname")

    def test_timeline_decrypted_source_skips_wcdb_for_cover_and_posts(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            conn = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                conn.execute(
                    "CREATE TABLE SnsTimeLine ("
                    "tid INTEGER, user_name TEXT, content TEXT"
                    ")"
                )
                conn.execute(
                    "INSERT INTO SnsTimeLine VALUES (?, ?, ?)",
                    (
                        42,
                        "wxid_friend",
                        "<TimelineObject><id>42</id><username>wxid_friend</username>"
                        "<createTime>1700000000</createTime><contentDesc>Hello</contentDesc>"
                        "<ContentObject><contentStyle>1</contentStyle></ContentObject>"
                        "</TimelineObject>",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            for requested_source in ("decrypted", "local", "sqlite"):
                with self.subTest(source=requested_source):
                    with (
                        mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                        mock.patch.object(sns_router.WCDB_REALTIME, "is_connected", return_value=True) as is_connected,
                        mock.patch.object(
                            sns_router.WCDB_REALTIME,
                            "ensure_connected",
                            side_effect=AssertionError("decrypted timeline must not open WCDB"),
                        ) as ensure_connected,
                        mock.patch.object(sns_router, "_wcdb_exec_query") as exec_query,
                        mock.patch.object(sns_router, "_wcdb_get_sns_timeline") as get_sns_timeline,
                        mock.patch.object(sns_router.WCDB_REALTIME, "get_recent_failure") as get_recent_failure,
                    ):
                        response = sns_router.list_sns_timeline(
                            account=account_dir.name,
                            limit=20,
                            offset=0,
                            source=requested_source,
                        )

                    is_connected.assert_not_called()
                    ensure_connected.assert_not_called()
                    exec_query.assert_not_called()
                    get_sns_timeline.assert_not_called()
                    get_recent_failure.assert_not_called()
                    self.assertEqual(response.get("source"), "decrypted")
                    self.assertEqual(response.get("sourceRequested"), "decrypted")
                    self.assertEqual(len(response.get("timeline") or []), 1)
                    self.assertEqual((response.get("timeline") or [])[0].get("username"), "wxid_friend")

    def test_sns_page_requests_decrypted_source(self):
        page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")

        self.assertRegex(
            page,
            re.compile(r"api\.listSnsTimeline\(\{[\s\S]{0,300}source: 'decrypted'", re.MULTILINE),
        )
        self.assertRegex(
            page,
            re.compile(r"/sns/self_info\?account=.*?&source=decrypted", re.MULTILINE),
        )
        self.assertIn("query.set('source', params.source)", api)
        self.assertRegex(
            page,
            re.compile(r"/chat/avatar\?account=.*?&username=.*?&source=decrypted", re.MULTILINE),
        )
        self.assertIn("const resetSnsMediaErrors", page)
        self.assertRegex(page, re.compile(r"if \(reset\) \{\s*resetSnsMediaErrors\(\)"))

    def test_http_route_defaults_preserve_auto_contract(self):
        self.assertEqual(
            inspect.signature(sns_router.api_sns_self_info).parameters["source"].default,
            "auto",
        )
        self.assertEqual(
            inspect.signature(sns_router.list_sns_timeline).parameters["source"].default,
            "auto",
        )
        self.assertEqual(
            inspect.signature(chat_media_router.get_chat_avatar).parameters["source"].default,
            "auto",
        )

    def test_sns_avatar_route_decrypted_source_skips_wcdb_fallback(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            conn = sqlite3.connect(str(account_dir / "head_image.db"))
            try:
                conn.execute(
                    "CREATE TABLE head_image ("
                    "username TEXT, md5 TEXT, update_time INTEGER, image_buffer BLOB"
                    ")"
                )
                conn.commit()
            finally:
                conn.close()

            app = FastAPI()
            app.include_router(chat_media_router.router)
            client = TestClient(app)
            with (
                mock.patch.object(chat_media_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(chat_media_router, "is_avatar_cache_enabled", return_value=False),
                mock.patch.object(
                    chat_media_router.WCDB_REALTIME,
                    "ensure_connected",
                    side_effect=AssertionError("decrypted avatar must not open WCDB"),
                ) as ensure_connected,
            ):
                for requested_source in ("decrypted", "local", "sqlite"):
                    with self.subTest(source=requested_source):
                        params = {
                            "account": account_dir.name,
                            "username": "wxid_friend",
                        }
                        params["source"] = requested_source
                        response = client.get("/api/chat/avatar", params=params)
                        self.assertEqual(response.status_code, 404)

        ensure_connected.assert_not_called()

    def test_timeline_explicit_auto_preserves_realtime_behavior(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            realtime_storage = Path(td) / "live" / "db_storage"
            realtime_storage.mkdir(parents=True)
            realtime_connection = SimpleNamespace(
                handle=7,
                lock=threading.Lock(),
                db_storage_dir=realtime_storage,
            )
            realtime_rows = [
                {
                    "id": "42",
                    "username": "wxid_friend",
                    "nickname": "Friend",
                    "createTime": 1700000000,
                    "contentDesc": "Realtime post",
                    "media": [],
                    "likes": [],
                    "comments": [],
                }
            ]

            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router.WCDB_REALTIME, "is_connected", return_value=False),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "ensure_connected",
                    return_value=realtime_connection,
                ) as ensure_connected,
                mock.patch.object(sns_router, "_wcdb_get_sns_timeline", return_value=realtime_rows),
            ):
                response = sns_router.list_sns_timeline(account=account_dir.name, source="auto")

        ensure_connected.assert_called_once_with(account_dir)
        self.assertEqual(response.get("source"), "wcdb")
        self.assertEqual((response.get("timeline") or [])[0].get("contentDesc"), "Realtime post")

    def test_timeline_auto_falls_back_to_decrypted_snapshot(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            conn = sqlite3.connect(str(account_dir / "sns.db"))
            try:
                conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
                conn.execute(
                    "INSERT INTO SnsTimeLine VALUES (?, ?, ?)",
                    (
                        42,
                        "wxid_friend",
                        "<TimelineObject><createTime>1700000000</createTime>"
                        "<contentDesc>Cached post</contentDesc></TimelineObject>",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            realtime_error = sns_router.WCDBRealtimeError("WCDB sidecar unavailable")
            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router.WCDB_REALTIME, "is_connected", return_value=False),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "ensure_connected",
                    side_effect=realtime_error,
                ),
                mock.patch.object(
                    sns_router.WCDB_REALTIME,
                    "get_recent_failure",
                    return_value={"retry_after_seconds": 30},
                ),
            ):
                response = sns_router.list_sns_timeline(account=account_dir.name, source="auto")

        self.assertEqual(response.get("source"), "sqlite")
        self.assertEqual(response.get("sourceRequested"), "auto")
        self.assertTrue(response.get("sourceFallback"))
        self.assertIn("sidecar unavailable", response.get("sourceFallbackReason") or "")

    def test_timeline_decrypted_missing_snapshot_returns_404(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router.WCDB_REALTIME, "ensure_connected") as ensure_connected,
            ):
                with self.assertRaises(sns_router.HTTPException) as raised:
                    sns_router.list_sns_timeline(
                        account=account_dir.name,
                        source="decrypted",
                    )

        ensure_connected.assert_not_called()
        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("sns.db not found", str(raised.exception.detail))

    def test_invalid_sns_source_returns_400(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me"
            account_dir.mkdir(parents=True)
            with mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir):
                with self.assertRaises(sns_router.HTTPException) as self_info_error:
                    sns_router.api_sns_self_info(account=account_dir.name, source="invalid")
                with self.assertRaises(sns_router.HTTPException) as timeline_error:
                    sns_router.list_sns_timeline(account=account_dir.name, source="invalid")

        self.assertEqual(self_info_error.exception.status_code, 400)
        self.assertEqual(timeline_error.exception.status_code, 400)

    def test_source_aliases_match_existing_api_contract(self):
        aliases = {
            "sqlite": "decrypted",
            "local": "decrypted",
            "wcdb": "realtime",
            "real-time": "realtime",
            "default": "decrypted",
        }
        for raw, expected in aliases.items():
            with self.subTest(source=raw):
                self.assertEqual(sns_router.normalize_data_source(raw, "decrypted"), expected)


if __name__ == "__main__":
    unittest.main()
