import os
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


class TestChatExportImageMd5PrefersMessageResource(unittest.TestCase):
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

    def _seed_source_info(self, account_dir: Path) -> None:
        wxid_dir = account_dir / "_wxid_dummy"
        db_storage_dir = account_dir / "_db_storage_dummy"
        wxid_dir.mkdir(parents=True, exist_ok=True)
        db_storage_dir.mkdir(parents=True, exist_ok=True)
        (account_dir / "_source.json").write_text(
            '{"wxid_dir": "' + str(wxid_dir).replace("\\", "\\\\") + '", "db_storage_path": "' + str(db_storage_dir).replace("\\", "\\\\") + '"}',
            encoding="utf-8",
        )

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
            conn.execute(
                "INSERT INTO SessionTable VALUES (?, ?, ?)",
                (username, 0, 1735689600),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_message_db(self, path: Path, *, account: str, username: str, bad_md5: str) -> None:
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

            image_xml = f'<msg><img md5="{bad_md5}" /></msg>'
            conn.execute(
                f"INSERT INTO {table_name} (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 1001, 3, 1, 2, 1735689601, image_xml, None),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_message_resource_db(self, path: Path, *, good_md5: str) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE MessageResourceInfo (
                    message_id INTEGER,
                    message_svr_id INTEGER,
                    message_local_type INTEGER,
                    chat_id INTEGER,
                    message_local_id INTEGER,
                    message_create_time INTEGER,
                    packed_info BLOB
                )
                """
            )
            # packed_info may contain multiple tokens; include a realistic *.dat reference so the extractor prefers it.
            packed_info = f"{good_md5}_t.dat".encode("ascii")
            conn.execute(
                "INSERT INTO MessageResourceInfo VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, 1001, 3, 0, 1, 1735689601, packed_info),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_decrypted_resource(self, account_dir: Path, *, good_md5: str) -> None:
        resource_root = account_dir / "resource"
        (resource_root / good_md5[:2]).mkdir(parents=True, exist_ok=True)
        # Minimal JPEG payload (valid SOI/EOI).
        (resource_root / good_md5[:2] / f"{good_md5}.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    def _prepare_account(self, root: Path, *, account: str, username: str, bad_md5: str, good_md5: str) -> Path:
        account_dir = root / "output" / "databases" / account
        account_dir.mkdir(parents=True, exist_ok=True)
        self._seed_source_info(account_dir)
        self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
        self._seed_session_db(account_dir / "session.db", username=username)
        self._seed_message_db(account_dir / "message_0.db", account=account, username=username, bad_md5=bad_md5)
        self._seed_message_resource_db(account_dir / "message_resource.db", good_md5=good_md5)
        self._seed_decrypted_resource(account_dir, good_md5=good_md5)
        return account_dir

    def _create_job(self, manager, *, account: str, username: str):
        job = manager.create_job(
            account=account,
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
            import time as _time

            _time.sleep(0.05)
        self.fail("export job did not finish in time")

    def test_prefers_message_resource_md5_over_xml_md5(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            bad_md5 = "ffffffffffffffffffffffffffffffff"
            good_md5 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            self._prepare_account(root, account=account, username=username, bad_md5=bad_md5, good_md5=good_md5)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(svc.CHAT_EXPORT_MANAGER, account=account, username=username)
                self.assertEqual(job.status, "done", msg=job.error)

                with zipfile.ZipFile(job.zip_path, "r") as zf:
                    names = set(zf.namelist())
                    self.assertIn(f"media/images/{good_md5}.jpg", names)

                    html_path = next((n for n in names if n.endswith("/messages.html")), "")
                    self.assertTrue(html_path)
                    html_text = zf.read(html_path).decode("utf-8", errors="ignore")
                    self.assertIn(f"../../media/images/{good_md5}.jpg", html_text)
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

