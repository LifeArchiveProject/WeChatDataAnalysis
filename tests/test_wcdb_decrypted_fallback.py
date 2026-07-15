import hashlib
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import chat_export_service, wcdb_realtime
from wechat_decrypt_tool.routers import chat as chat_router
from wechat_decrypt_tool.routers import chat_contacts as contacts_router
from wechat_decrypt_tool.routers import favorites as favorites_router
from wechat_decrypt_tool.routers import general as general_router


class TestWcdbDecryptedFallback(unittest.TestCase):
    def test_recent_failure_status_preserves_original_reason(self):
        manager = wcdb_realtime.WCDBRealtimeManager()
        manager._failed["wxid_demo"] = (
            time.monotonic(),
            "open_account timed out while the database was locked",
        )

        failure = manager.get_recent_failure("wxid_demo")

        self.assertTrue(failure.get("active"))
        self.assertIn("database was locked", str(failure.get("reason") or ""))
        self.assertGreater(int(failure.get("retry_after_seconds") or 0), 0)

    def test_general_realtime_read_falls_back_to_decrypted_database(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir(parents=True)
            db_path = account_dir / "general.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("CREATE TABLE sample (value TEXT)")
                conn.execute("INSERT INTO sample VALUES ('from decrypted')")
                conn.commit()
            finally:
                conn.close()

            ctx = SimpleNamespace(
                account_dir=account_dir,
                name=account_dir.name,
                db_key_present=True,
                db_storage_path=str(Path(td) / "live" / "db_storage"),
                wxid_dir="",
            )
            error = wcdb_realtime.WCDBRealtimeError(
                "WCDB connection recently failed; retry after 60s."
            )
            with patch.object(general_router.WCDB_REALTIME, "ensure_connected", side_effect=error):
                with general_router._open_db_source(
                    ctx,
                    source="realtime",
                    db_group="general",
                    db_name="general.db",
                    decrypted_name="general.db",
                ) as source:
                    row = source.execute("SELECT value FROM sample").fetchone()
                    meta = general_router._source_meta(source)

        self.assertEqual(row[0], "from decrypted")
        self.assertEqual(meta.get("dataSource"), "decrypted")
        self.assertTrue(meta.get("sourceFallback"))
        self.assertIn("retry after 60s", str(meta.get("sourceFallbackReason") or ""))

    def test_chat_messages_fall_back_to_decrypted_database(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir(parents=True)
            username = "wxid_friend"
            table_name = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()
            db_path = account_dir / "message_0.db"
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("CREATE TABLE Name2Id (user_name TEXT)")
                conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (1, ?)", (account_dir.name,))
                conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (2, ?)", (username,))
                conn.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        local_id INTEGER,
                        server_id INTEGER,
                        local_type INTEGER,
                        sort_seq INTEGER,
                        real_sender_id INTEGER,
                        create_time INTEGER,
                        message_content TEXT,
                        compress_content BLOB
                    )
                    """
                )
                conn.execute(
                    f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (1367, 123, 1, 1700000000000, 2, 1700000000, "from decrypted", None),
                )
                conn.commit()
            finally:
                conn.close()

            error = wcdb_realtime.WCDBRealtimeError(
                "WCDB connection recently failed; retry after 60s."
            )
            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", side_effect=error),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                response = chat_router.list_chat_messages(
                    SimpleNamespace(base_url="http://testserver/"),
                    username=username,
                    account=account_dir.name,
                    limit=50,
                    offset=0,
                    order="asc",
                    source="auto",
                )

        self.assertEqual(response.get("source"), "decrypted")
        self.assertTrue(response.get("sourceFallback"))
        self.assertEqual((response.get("messages") or [])[0].get("content"), "from decrypted")

    def test_contacts_fall_back_to_decrypted_database(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir(parents=True)
            conn = sqlite3.connect(str(account_dir / "contact.db"))
            try:
                conn.execute(
                    "CREATE TABLE contact ("
                    "username TEXT, nick_name TEXT, local_type INTEGER, verify_flag INTEGER"
                    ")"
                )
                conn.execute(
                    "INSERT INTO contact VALUES (?, ?, ?, ?)",
                    ("wxid_friend", "from decrypted", 1, 0),
                )
                conn.commit()
            finally:
                conn.close()

            error = wcdb_realtime.WCDBRealtimeError(
                "WCDB connection recently failed; retry after 60s."
            )
            with (
                patch.object(contacts_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(contacts_router.WCDB_REALTIME, "ensure_connected", side_effect=error),
                patch.object(
                    contacts_router.WCDB_REALTIME,
                    "get_recent_failure",
                    return_value={"active": True, "retry_after_seconds": 60},
                ),
            ):
                response = contacts_router.list_chat_contacts(
                    SimpleNamespace(base_url="http://testserver/"),
                    account=account_dir.name,
                    source="auto",
                )

        self.assertEqual(response.get("source"), "decrypted")
        self.assertTrue(response.get("sourceFallback"))
        self.assertEqual(response.get("sourceFallbackRetryAfterSeconds"), 60)
        self.assertEqual((response.get("contacts") or [])[0].get("displayName"), "from decrypted")

    def test_favorite_voice_falls_back_to_decrypted_media_database(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir(parents=True)
            conn = sqlite3.connect(str(account_dir / "media_0.db"))
            try:
                conn.execute("CREATE TABLE VoiceInfo (svr_id INTEGER, create_time INTEGER, voice_data BLOB)")
                conn.execute("INSERT INTO VoiceInfo VALUES (?, ?, ?)", (123, 456, b"local voice"))
                conn.commit()
            finally:
                conn.close()

            ctx = SimpleNamespace(
                account_dir=account_dir,
                name=account_dir.name,
                db_key_present=True,
                db_storage_path=str(Path(td) / "live" / "db_storage"),
                wxid_dir="",
            )
            error = wcdb_realtime.WCDBRealtimeError(
                "WCDB connection recently failed; retry after 60s."
            )
            with (
                patch.object(favorites_router, "resolve_chat_account_context", return_value=ctx),
                patch.object(favorites_router.WCDB_REALTIME, "ensure_connected", side_effect=error),
                patch.object(
                    favorites_router,
                    "_convert_silk_to_browser_audio",
                    return_value=(b"converted voice", "mp3", "audio/mpeg"),
                ),
            ):
                response = favorites_router.get_favorite_voice(server_id=123, account=account_dir.name)

        self.assertEqual(response.body, b"converted voice")
        self.assertEqual(response.headers.get("x-wechat-data-source"), "decrypted")

    def test_chat_export_job_falls_back_to_decrypted_databases(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir(parents=True)
            for name in ("session.db", "contact.db"):
                conn = sqlite3.connect(str(account_dir / name))
                conn.close()

            manager = chat_export_service.ChatExportManager()
            error = wcdb_realtime.WCDBRealtimeError(
                "WCDB connection recently failed; retry after 60s."
            )
            with (
                patch.object(chat_export_service, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_export_service.WCDB_REALTIME, "ensure_connected", side_effect=error),
                patch.object(chat_export_service.threading, "Thread") as thread_cls,
            ):
                job = manager.create_job(
                    account=account_dir.name,
                    source="auto",
                    scope="selected",
                    usernames=["wxid_friend"],
                    export_format="json",
                    start_time=None,
                    end_time=None,
                    include_hidden=False,
                    include_official=False,
                    include_media=False,
                    media_kinds=[],
                    message_types=[],
                    output_dir=None,
                    allow_process_key_extract=False,
                    download_remote_media=False,
                    privacy_mode=False,
                    file_name=None,
                )

        thread_cls.return_value.start.assert_called_once()
        self.assertEqual(job.options.get("source"), "decrypted")
        self.assertTrue(job.options.get("sourceFallback"))
        self.assertIn("retry after 60s", str(job.options.get("sourceFallbackReason") or ""))

    def test_account_info_marks_decrypted_snapshot_as_active_fallback(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_demo"
            account_dir.mkdir(parents=True)
            ctx = SimpleNamespace(
                account_dir=account_dir,
                name=account_dir.name,
                mode="direct",
                db_storage_path=str(Path(td) / "live" / "db_storage"),
                wxid_dir="",
                has_decrypted_dbs=True,
                db_key_present=True,
                image_key_present=False,
                image_xor_key_present=False,
                image_aes_key_present=False,
                keys_ready=True,
                keys_updated_at="",
            )
            with (
                patch.object(chat_router, "list_countable_database_names", return_value=["session.db"]),
                patch.object(
                    chat_router.WCDB_REALTIME,
                    "get_status",
                    return_value={
                        "dll_present": True,
                        "key_present": True,
                        "db_storage_dir": str(Path(td) / "live" / "db_storage"),
                        "session_db_path": str(Path(td) / "live" / "db_storage" / "session" / "session.db"),
                        "connected": False,
                        "recent_failure": True,
                        "failure_reason": "open_account timed out",
                        "retry_after_seconds": 42,
                    },
                ),
            ):
                info = chat_router._chat_account_context_public(ctx)

        self.assertEqual(info.get("defaultSource"), "decrypted")
        self.assertTrue((info.get("dataSourceStatus") or {}).get("fallbackActive"))
        self.assertEqual((info.get("dataSourceStatus") or {}).get("retryAfterSeconds"), 42)
        self.assertIn("open_account timed out", (info.get("dataSourceStatus") or {}).get("reason", ""))


if __name__ == "__main__":
    unittest.main()
