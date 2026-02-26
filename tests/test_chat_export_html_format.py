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


class TestChatExportHtmlFormat(unittest.TestCase):
    _FILE_MD5 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    _VOICE_SERVER_ID = 2001

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

    def _seed_message_db(self, path: Path, *, account: str, username: str) -> None:
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

            image_xml = '<msg><img md5="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" cdnthumburl="img_file_id_1" /></msg>'
            voice_xml = '<msg><voicemsg voicelength="3000" /></msg>'
            file_md5 = self._FILE_MD5
            file_xml = (
                "<msg><appmsg>"
                "<type>6</type>"
                "<title>demo.pdf</title>"
                "<totallen>2048</totallen>"
                f"<md5>{file_md5}</md5>"
                "</appmsg></msg>"
            )
            link_xml = (
                "<msg><appmsg>"
                "<type>5</type>"
                "<title>示例链接</title>"
                "<des>这是描述</des>"
                "<url>https://example.com/</url>"
                "<thumburl>https://example.com/thumb.jpg</thumburl>"
                "<sourceusername>gh_test</sourceusername>"
                "<sourcedisplayname>测试公众号</sourcedisplayname>"
                "</appmsg></msg>"
            )
            chat_history_xml = (
                "<msg><appmsg>"
                "<type>19</type>"
                "<title>聊天记录</title>"
                "<des>记录预览</des>"
                "<recorditem><desc>张三: hi\n李四: ok</desc></recorditem>"
                "</appmsg></msg>"
            )
            transfer_xml = (
                "<msg><appmsg>"
                "<type>2000</type>"
                "<title>微信转账</title>"
                "<wcpayinfo>"
                "<pay_memo>转账备注</pay_memo>"
                "<feedesc>￥1.23</feedesc>"
                "<paysubtype>3</paysubtype>"
                "<transferid>transfer_123</transferid>"
                "</wcpayinfo>"
                "</appmsg></msg>"
            )
            red_packet_xml = (
                "<msg><appmsg>"
                "<type>2001</type>"
                "<title>红包</title>"
                "<wcpayinfo>"
                "<sendertitle>恭喜发财，大吉大利</sendertitle>"
                "<senderdes>微信红包</senderdes>"
                "</wcpayinfo>"
                "</appmsg></msg>"
            )
            voip_xml = (
                "<msg><VoIPBubbleMsg>"
                "<room_type>1</room_type>"
                "<msg>语音通话</msg>"
                "</VoIPBubbleMsg></msg>"
            )
            quote_voice_xml = (
                "<msg><appmsg>"
                "<type>57</type>"
                "<title>回复语音</title>"
                "<refermsg>"
                "<type>34</type>"
                f"<svrid>{self._VOICE_SERVER_ID}</svrid>"
                "<fromusr>wxid_friend</fromusr>"
                "<displayname>测试好友</displayname>"
                "<content>wxid_friend:3000:1:</content>"
                "</refermsg>"
                "</appmsg></msg>"
            )
            rows = [
                (1, 1001, 3, 1, 2, 1735689601, image_xml, None),
                (2, 1002, 1, 2, 2, 1735689602, "普通文本消息[微笑]", None),
                (3, 1003, 49, 3, 1, 1735689603, transfer_xml, None),
                (4, 1004, 49, 4, 2, 1735689604, red_packet_xml, None),
                (5, 1005, 49, 5, 1, 1735689605, file_xml, None),
                (6, 1006, 49, 6, 2, 1735689606, link_xml, None),
                (7, 1007, 49, 7, 2, 1735689607, chat_history_xml, None),
                (8, 1008, 50, 8, 2, 1735689608, voip_xml, None),
                (9, self._VOICE_SERVER_ID, 34, 9, 1, 1735689609, voice_xml, None),
                (10, 1010, 49, 10, 1, 1735689610, quote_voice_xml, None),
            ]
            conn.executemany(
                f"INSERT INTO {table_name} (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_media_files(self, account_dir: Path) -> None:
        resource_root = account_dir / "resource"
        (resource_root / "aa").mkdir(parents=True, exist_ok=True)
        (resource_root / "aa" / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (resource_root / "bb").mkdir(parents=True, exist_ok=True)
        (resource_root / "bb" / f"{self._FILE_MD5}.dat").write_bytes(b"dummy")

        conn = sqlite3.connect(str(account_dir / "media_0.db"))
        try:
            conn.execute(
                """
                CREATE TABLE VoiceInfo (
                    svr_id INTEGER,
                    create_time INTEGER,
                    voice_data BLOB
                )
                """
            )
            conn.execute(
                "INSERT INTO VoiceInfo VALUES (?, ?, ?)",
                (self._VOICE_SERVER_ID, 1735689609, b"SILK_VOICE_DATA"),
            )
            conn.commit()
        finally:
            conn.close()

    def _prepare_account(self, root: Path, *, account: str, username: str) -> Path:
        account_dir = root / "output" / "databases" / account
        account_dir.mkdir(parents=True, exist_ok=True)

        self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
        self._seed_session_db(account_dir / "session.db", username=username)
        self._seed_message_db(account_dir / "message_0.db", account=account, username=username)
        self._seed_media_files(account_dir)
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
            media_kinds=["image", "emoji", "video", "video_thumb", "voice", "file"],
            message_types=[],
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

    def test_html_export_contains_index_and_conversation_page(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(svc.CHAT_EXPORT_MANAGER, account=account, username=username)
                self.assertEqual(job.status, "done", msg=job.error)

                self.assertTrue(job.zip_path and job.zip_path.exists())
                with zipfile.ZipFile(job.zip_path, "r") as zf:
                    names = set(zf.namelist())

                    self.assertIn("index.html", names)
                    self.assertIn("assets/wechat-chat-export.css", names)
                    self.assertIn("assets/wechat-chat-export.js", names)

                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                    self.assertEqual(manifest.get("format"), "html")

                    html_path = next((n for n in names if n.endswith("/messages.html")), "")
                    self.assertTrue(html_path)

                    html_text = zf.read(html_path).decode("utf-8")
                    self.assertIn('data-wce-rail-avatar="1"', html_text)
                    self.assertIn('data-wce-session-list="1"', html_text)
                    self.assertIn('id="sessionSearchInput"', html_text)
                    self.assertIn('data-wce-time-divider="1"', html_text)
                    self.assertIn('id="messageTypeFilter"', html_text)
                    self.assertIn('value="chatHistory"', html_text)
                    self.assertIn('data-wce-chat-history="1"', html_text)
                    self.assertIn('data-record-item-b64="', html_text)
                    self.assertIn('id="wceMediaIndex"', html_text)
                    self.assertIn('data-wce-quote-voice-btn="1"', html_text)
                    self.assertNotIn('title="刷新消息"', html_text)
                    self.assertNotIn('title="导出聊天记录"', html_text)
                    self.assertNotIn("搜索聊天记录", html_text)
                    self.assertNotIn("朋友圈", html_text)
                    self.assertNotIn("年度总结", html_text)
                    self.assertNotIn("设置", html_text)
                    self.assertNotIn("隐私模式", html_text)

                    self.assertTrue(any(n.startswith("media/images/") for n in names))
                    self.assertIn("../../media/images/", html_text)

                    self.assertIn("wechat-transfer-card", html_text)
                    self.assertIn("wechat-redpacket-card", html_text)
                    self.assertIn("wechat-chat-history-card", html_text)
                    self.assertIn("wechat-voip-bubble", html_text)
                    self.assertIn("wechat-link-card", html_text)
                    self.assertIn("wechat-file-card", html_text)
                    self.assertIn("wechat-voice-wrapper", html_text)

                    css_text = zf.read("assets/wechat-chat-export.css").decode("utf-8", errors="ignore")
                    self.assertIn("wechat-transfer-card", css_text)
                    self.assertNotIn("wechat-transfer-card[data-v-", css_text)
                    self.assertNotIn("bento-container", css_text)

                    js_text = zf.read("assets/wechat-chat-export.js").decode("utf-8", errors="ignore")
                    self.assertIn("wechat-voice-bubble", js_text)
                    self.assertIn("voice-playing", js_text)
                    self.assertIn("data-wce-quote-voice-btn", js_text)

                    self.assertIn("assets/images/wechat/wechat-trans-icon1.png", names)
                    self.assertIn("assets/images/wechat/zip.png", names)
                    self.assertIn("assets/images/wechat/WeChat-Icon-Logo.wine.svg", names)
                    self.assertIn("wxemoji/Expression_1@2x.png", names)
                    self.assertIn("../../wxemoji/Expression_1@2x.png", html_text)
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data
