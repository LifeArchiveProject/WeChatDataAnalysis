import hashlib
import importlib
import os
import sqlite3
import sys
import time
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatExportImagePackedInfo(unittest.TestCase):
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

    def _prepare_account(self, root: Path, *, account: str, username: str, image_md5: str) -> None:
        account_dir = root / "output" / "databases" / account
        account_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(account_dir / "contact.db"))
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
            conn.execute("INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (account, "", "我", "", 1, 0, "", ""))
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (username, "", "文件传输助手", "", 1, 0, "", ""),
            )
            conn.commit()
        finally:
            conn.close()

        conn = sqlite3.connect(str(account_dir / "session.db"))
        try:
            conn.execute("CREATE TABLE SessionTable (username TEXT, is_hidden INTEGER, sort_timestamp INTEGER)")
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", (username, 0, 1783152107))
            conn.commit()
        finally:
            conn.close()

        table_name = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
        conn = sqlite3.connect(str(account_dir / "message_0.db"))
        try:
            conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (1, account))
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (2, username))
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
                    compress_content BLOB,
                    packed_info_data BLOB
                )
                """
            )
            # Clipboard/pasted images can have sparse XML while the usable local basename lives in packed_info_data.
            conn.execute(
                f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    44,
                    3327480211342082097,
                    3,
                    44,
                    1,
                    1783152107,
                    "<msg><img /></msg>",
                    None,
                    f"{image_md5}_t.dat".encode("ascii"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        resource_dir = account_dir / "resource" / image_md5[:2]
        resource_dir.mkdir(parents=True, exist_ok=True)
        resource_dir.joinpath(f"{image_md5}.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    def _create_job(self, manager, *, account: str, username: str):
        job = manager.create_job(
            account=account,
            source="decrypted",
            scope="selected",
            usernames=[username],
            export_format="html",
            start_time=None,
            end_time=None,
            include_hidden=False,
            include_official=False,
            include_media=True,
            media_kinds=["image"],
            message_types=["image"],
            output_dir=None,
            allow_process_key_extract=False,
            download_remote_media=False,
            privacy_mode=False,
            file_name=None,
        )

        for _ in range(200):
            latest = manager.get_job(job.export_id)
            if latest and latest.status in {"done", "error", "cancelled"}:
                return latest
            time.sleep(0.05)
        self.fail("export job did not finish in time")

    def test_html_export_materializes_image_md5_from_packed_info_data(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            account = "wxid_test"
            username = "filehelper"
            image_md5 = "4c5a64f5aff224ae5c04ce0df516a425"
            self._prepare_account(root, account=account, username=username, image_md5=image_md5)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(svc.CHAT_EXPORT_MANAGER, account=account, username=username)
                self.assertEqual(job.status, "done", msg=job.error)
                self.assertEqual(job.progress.media_missing, 0)

                with zipfile.ZipFile(job.zip_path, "r") as zf:
                    names = set(zf.namelist())
                    self.assertIn(f"media/images/{image_md5}.jpg", names)

                    html_path = next((n for n in names if n.endswith("/messages.html")), "")
                    self.assertTrue(html_path)
                    html_text = zf.read(html_path).decode("utf-8", errors="ignore")
                    self.assertIn(f"../../media/images/{image_md5}.jpg", html_text)
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data
