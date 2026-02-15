import os
import json
import hashlib
import sqlite3
import sys
import unittest
import zipfile
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatExportHtmlPaging(unittest.TestCase):
    def _reload_export_modules(self):
        import wechat_decrypt_tool.app_paths as app_paths
        import wechat_decrypt_tool.chat_helpers as chat_helpers
        import wechat_decrypt_tool.media_helpers as media_helpers
        import wechat_decrypt_tool.chat_export_service as chat_export_service

        importlib.reload(app_paths)
        importlib.reload(chat_helpers)
        importlib.reload(media_helpers)
        importlib.reload(chat_export_service)
        return chat_export_service

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
                (account, "", "Me", "", 1, 0, "", ""),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (username, "", "Friend", "", 1, 0, "", ""),
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
            conn.execute(
                "INSERT INTO SessionTable VALUES (?, ?, ?)",
                (username, 0, 1735689600),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_message_db(self, path: Path, *, account: str, username: str, total: int) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (1, account))
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (2, username))

            table_name = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
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

            # Generate lots of plain text messages with unique markers.
            rows = []
            base_ts = 1735689600
            for i in range(1, total + 1):
                marker = f"MSG{i:04d}"
                real_sender_id = 1 if (i % 2 == 0) else 2
                rows.append((i, 100000 + i, 1, i, real_sender_id, base_ts + i, marker, None))

            conn.executemany(
                f"INSERT INTO {table_name} (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def _prepare_account(self, root: Path, *, account: str, username: str, total: int) -> Path:
        account_dir = root / "output" / "databases" / account
        account_dir.mkdir(parents=True, exist_ok=True)
        self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
        self._seed_session_db(account_dir / "session.db", username=username)
        self._seed_message_db(account_dir / "message_0.db", account=account, username=username, total=total)
        return account_dir

    def _create_job(self, manager, *, account: str, username: str, html_page_size: int):
        job = manager.create_job(
            account=account,
            scope="selected",
            usernames=[username],
            export_format="html",
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
            html_page_size=html_page_size,
            privacy_mode=False,
            file_name=None,
        )

        # Export is async (thread). Allow enough time for a few thousand messages + zip writes.
        for _ in range(600):
            latest = manager.get_job(job.export_id)
            if latest and latest.status in {"done", "error", "cancelled"}:
                return latest
            import time as _time

            _time.sleep(0.05)
        self.fail("export job did not finish in time")

    def test_html_export_paging_inlines_latest_page_only(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"

            total_messages = 2300
            page_size = 1000
            self._prepare_account(root, account=account, username=username, total=total_messages)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    html_page_size=page_size,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                self.assertTrue(job.zip_path and job.zip_path.exists())
                with zipfile.ZipFile(job.zip_path, "r") as zf:
                    names = set(zf.namelist())

                    html_path = next((n for n in names if n.endswith("/messages.html")), "")
                    self.assertTrue(html_path, msg="missing messages.html")
                    html_text = zf.read(html_path).decode("utf-8", errors="ignore")

                    # Paging UI + meta should exist for multi-page exports.
                    self.assertIn('id="wcePageMeta"', html_text)
                    self.assertIn('id="wcePager"', html_text)
                    self.assertIn('id="wceMessageList"', html_text)
                    self.assertIn('id="wceLoadPrevBtn"', html_text)

                    # Latest page is inlined; earliest page should not be present in messages.html.
                    self.assertIn("MSG2300", html_text)
                    self.assertNotIn("MSG0001", html_text)

                    conv_dir = html_path.rsplit("/", 1)[0]
                    page1_js = f"{conv_dir}/pages/page-0001.js"
                    self.assertIn(page1_js, names)
                    page1_text = zf.read(page1_js).decode("utf-8", errors="ignore")
                    self.assertIn("MSG0001", page1_text)
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data
