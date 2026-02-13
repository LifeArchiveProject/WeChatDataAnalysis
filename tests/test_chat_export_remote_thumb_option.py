import os
import hashlib
import sqlite3
import sys
import unittest
import zipfile
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _FakeResponse:
    def __init__(self, body: bytes, *, content_type: str) -> None:
        self.status_code = 200
        self.headers = {
            "Content-Type": str(content_type or "").strip(),
            "Content-Length": str(len(body)),
        }
        self._body = body

    def iter_content(self, chunk_size=65536):
        data = self._body or b""
        for i in range(0, len(data), int(chunk_size or 65536)):
            yield data[i : i + int(chunk_size or 65536)]

    def close(self):
        return None


class TestChatExportRemoteThumbOption(unittest.TestCase):
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

    def _seed_message_db(self, path: Path, *, account: str, username: str) -> tuple[str, str]:
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

            link_thumb = "https://1.1.1.1/thumb.png"
            quote_thumb = "https://1.1.1.1/quote.png"

            link_xml = (
                "<msg><appmsg>"
                "<type>5</type>"
                "<title>示例链接</title>"
                "<des>这是描述</des>"
                "<url>https://example.com/</url>"
                f"<thumburl>{link_thumb}</thumburl>"
                "</appmsg></msg>"
            )
            quote_xml = (
                "<msg><appmsg>"
                "<type>57</type>"
                "<title>回复</title>"
                "<refermsg>"
                "<type>49</type>"
                "<svrid>8888</svrid>"
                "<fromusr>wxid_other</fromusr>"
                "<displayname>对方</displayname>"
                "<content>"
                "<msg><appmsg><type>5</type><title>被引用链接</title><url>https://example.com/</url>"
                f"<thumburl>{quote_thumb}</thumburl>"
                "</appmsg></msg>"
                "</content>"
                "</refermsg>"
                "</appmsg></msg>"
            )

            rows = [
                (1, 1001, 49, 1, 2, 1735689601, link_xml, None),
                (2, 1002, 49, 2, 2, 1735689602, quote_xml, None),
            ]
            conn.executemany(
                f"INSERT INTO {table_name} (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            return link_thumb, quote_thumb
        finally:
            conn.close()

    def _prepare_account(self, root: Path, *, account: str, username: str) -> tuple[Path, str, str]:
        account_dir = root / "output" / "databases" / account
        account_dir.mkdir(parents=True, exist_ok=True)

        self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
        self._seed_session_db(account_dir / "session.db", username=username)
        link_thumb, quote_thumb = self._seed_message_db(account_dir / "message_0.db", account=account, username=username)
        return account_dir, link_thumb, quote_thumb

    def _create_job(self, manager, *, account: str, username: str, download_remote_media: bool):
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
            media_kinds=["image", "emoji", "video", "video_thumb", "voice", "file"],
            message_types=["link", "quote", "image"],
            output_dir=None,
            allow_process_key_extract=False,
            download_remote_media=download_remote_media,
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

    def test_remote_thumb_disabled_does_not_download(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            _, link_thumb, quote_thumb = self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()

                with mock.patch.object(
                    svc.requests,
                    "get",
                    side_effect=AssertionError("requests.get should not be called when download_remote_media=False"),
                ) as m_get:
                    job = self._create_job(
                        svc.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        download_remote_media=False,
                    )
                    self.assertEqual(job.status, "done", msg=job.error)
                    self.assertEqual(m_get.call_count, 0)

                with zipfile.ZipFile(job.zip_path, "r") as zf:
                    names = set(zf.namelist())
                    html_path = next((n for n in names if n.endswith("/messages.html")), "")
                    self.assertTrue(html_path)
                    html_text = zf.read(html_path).decode("utf-8")
                    self.assertIn(f'src="{link_thumb}"', html_text)
                    self.assertIn(f'src="{quote_thumb}"', html_text)
                    self.assertFalse(any(n.startswith("media/remote/") for n in names))
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_remote_thumb_enabled_downloads_and_rewrites(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            _, link_thumb, quote_thumb = self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()

                fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"

                def _fake_get(url, **_kwargs):
                    return _FakeResponse(fake_png, content_type="image/png")

                with mock.patch.object(svc.requests, "get", side_effect=_fake_get) as m_get:
                    job = self._create_job(
                        svc.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        download_remote_media=True,
                    )
                    self.assertEqual(job.status, "done", msg=job.error)
                    self.assertGreaterEqual(m_get.call_count, 1)

                with zipfile.ZipFile(job.zip_path, "r") as zf:
                    names = set(zf.namelist())
                    html_path = next((n for n in names if n.endswith("/messages.html")), "")
                    self.assertTrue(html_path)
                    html_text = zf.read(html_path).decode("utf-8")

                    h1 = hashlib.sha256(link_thumb.encode("utf-8", errors="ignore")).hexdigest()
                    arc1 = f"media/remote/{h1[:32]}.png"
                    self.assertIn(arc1, names)
                    self.assertIn(f"../../{arc1}", html_text)
                    self.assertNotIn(f'src="{link_thumb}"', html_text)

                    h2 = hashlib.sha256(quote_thumb.encode("utf-8", errors="ignore")).hexdigest()
                    arc2 = f"media/remote/{h2[:32]}.png"
                    self.assertIn(arc2, names)
                    self.assertIn(f"../../{arc2}", html_text)
                    self.assertNotIn(f'src="{quote_thumb}"', html_text)
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

