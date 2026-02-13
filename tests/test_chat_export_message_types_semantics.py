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


class TestChatExportMessageTypesSemantics(unittest.TestCase):
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
            video_xml = '<msg><videomsg md5="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" cdnthumbmd5="cccccccccccccccccccccccccccccccc" cdnvideourl="video_file_id_1" cdnthumburl="video_thumb_id_1" /></msg>'

            rows = [
                (1, 1001, 3, 1, 2, 1735689601, image_xml, None),
                (2, 1002, 43, 2, 2, 1735689602, video_xml, None),
                (3, 1003, 49, 3, 2, 1735689603, '<msg><appmsg><type>2000</type><des>收到转账0.01元</des></appmsg></msg>', None),
                (4, 1004, 1, 4, 2, 1735689604, '普通文本消息', None),
                (5, 1005, 10000, 5, 2, 1735689605, '系统提示消息', None),
                (
                    6,
                    1006,
                    10000,
                    6,
                    2,
                    1735689606,
                    '<sysmsg type="revokemsg"><revokemsg><replacemsg><![CDATA[“测试好友”撤回了一条消息]]></replacemsg></revokemsg></sysmsg>',
                    None,
                ),
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
        (resource_root / "bb").mkdir(parents=True, exist_ok=True)
        (resource_root / "cc").mkdir(parents=True, exist_ok=True)

        (resource_root / "aa" / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (resource_root / "bb" / "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.mp4").write_bytes(b"video-bytes")
        (resource_root / "cc" / "cccccccccccccccccccccccccccccccc.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    def _seed_source_info(self, account_dir: Path, wxid_dir: Path) -> None:
        payload = {
            "wxid_dir": str(wxid_dir),
            "db_storage_path": str(wxid_dir / "db_storage"),
        }
        (account_dir / "_source.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _seed_wxid_media_files(self, wxid_dir: Path) -> None:
        (wxid_dir / "msg" / "video").mkdir(parents=True, exist_ok=True)
        (wxid_dir / "msg" / "attach").mkdir(parents=True, exist_ok=True)
        (wxid_dir / "cache").mkdir(parents=True, exist_ok=True)
        (wxid_dir / "db_storage").mkdir(parents=True, exist_ok=True)

        (wxid_dir / "msg" / "video" / "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.mp4").write_bytes(b"video-bytes")
        (wxid_dir / "msg" / "video" / "cccccccccccccccccccccccccccccccc.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    def _prepare_account(self, root: Path, *, account: str, username: str) -> Path:
        account_dir = root / "output" / "databases" / account
        account_dir.mkdir(parents=True, exist_ok=True)
        wxid_dir = root / "wxid_data" / account

        self._seed_contact_db(account_dir / "contact.db", account=account, username=username)
        self._seed_session_db(account_dir / "session.db", username=username)
        self._seed_message_db(account_dir / "message_0.db", account=account, username=username)
        self._seed_media_files(account_dir)
        self._seed_wxid_media_files(wxid_dir)
        self._seed_source_info(account_dir, wxid_dir)
        return account_dir

    def _create_job(self, manager, *, account: str, username: str, message_types, include_media=True, media_kinds=None, privacy_mode=False):
        if media_kinds is None:
            media_kinds = ["image", "emoji", "video", "video_thumb", "voice", "file"]

        job = manager.create_job(
            account=account,
            scope="selected",
            usernames=[username],
            export_format="json",
            start_time=None,
            end_time=None,
            include_hidden=False,
            include_official=False,
            include_media=include_media,
            media_kinds=media_kinds,
            message_types=message_types,
            output_dir=None,
            allow_process_key_extract=False,
            download_remote_media=False,
            privacy_mode=privacy_mode,
            file_name=None,
        )

        for _ in range(200):
            latest = manager.get_job(job.export_id)
            if latest and latest.status in {"done", "error", "cancelled"}:
                return latest
            import time as _time

            _time.sleep(0.05)
        self.fail("export job did not finish in time")

    def _load_export_payload(self, zip_path: Path):
        self.assertTrue(zip_path.exists())
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            msg_path = next((n for n in names if n.endswith("/messages.json")), "")
            self.assertTrue(msg_path)
            import json as _json

            payload = _json.loads(zf.read(msg_path).decode("utf-8"))
            manifest = _json.loads(zf.read("manifest.json").decode("utf-8"))
        return payload, manifest, names

    def test_unchecked_image_is_filtered_out(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["text", "transfer"],
                    include_media=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, _, names = self._load_export_payload(job.zip_path)
                image_msg = next((m for m in payload.get("messages", []) if int(m.get("type") or 0) == 3), None)
                self.assertIsNone(image_msg)
                render_types = {str(m.get("renderType") or "") for m in payload.get("messages", [])}
                self.assertTrue(render_types.issubset({"text", "transfer"}))
                self.assertFalse(any(n.startswith("media/images/") for n in names))
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_checked_image_exports_media_file(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["image", "text"],
                    include_media=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, _, names = self._load_export_payload(job.zip_path)
                image_msg = next((m for m in payload.get("messages", []) if int(m.get("type") or 0) == 3), None)
                self.assertIsNotNone(image_msg)
                self.assertEqual(str(image_msg.get("renderType") or ""), "image")
                self.assertTrue(isinstance(image_msg.get("offlineMedia"), list) and image_msg.get("offlineMedia"))
                self.assertTrue(any(n.startswith("media/images/") for n in names))
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_unchecked_non_media_type_is_filtered_out(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["text"],
                    include_media=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, manifest, _ = self._load_export_payload(job.zip_path)
                system_msg = next((m for m in payload.get("messages", []) if int(m.get("type") or 0) == 10000), None)
                self.assertIsNone(system_msg)
                self.assertTrue(all(str(m.get("renderType") or "") == "text" for m in payload.get("messages", [])))
                self.assertEqual(manifest.get("filters", {}).get("messageTypes"), ["text"])
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_checked_video_exports_video_and_thumb(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["video", "text"],
                    include_media=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, _, names = self._load_export_payload(job.zip_path)
                video_msg = next((m for m in payload.get("messages", []) if int(m.get("type") or 0) == 43), None)
                self.assertIsNotNone(video_msg)
                self.assertEqual(str(video_msg.get("renderType") or ""), "video")
                image_msg = next((m for m in payload.get("messages", []) if int(m.get("type") or 0) == 3), None)
                self.assertIsNone(image_msg)
                media_items = video_msg.get("offlineMedia") or []
                kinds = sorted(str(x.get("kind") or "") for x in media_items)
                self.assertIn("video", kinds)
                self.assertIn("video_thumb", kinds)
                self.assertTrue(any(n.startswith("media/videos/") for n in names))
                self.assertTrue(any(n.startswith("media/video_thumbs/") for n in names))
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_privacy_mode_never_exports_media(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["image", "video", "text"],
                    include_media=True,
                    privacy_mode=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, manifest, names = self._load_export_payload(job.zip_path)
                self.assertFalse(any(n.startswith("media/images/") for n in names))
                self.assertFalse(any(n.startswith("media/videos/") for n in names))
                self.assertFalse(any(n.startswith("media/video_thumbs/") for n in names))

                for msg in payload.get("messages", []):
                    self.assertFalse(msg.get("offlineMedia"))

                self.assertFalse(bool(manifest.get("options", {}).get("includeMedia")))
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_transfer_only_exports_transfer_messages(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["transfer"],
                    include_media=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, manifest, _ = self._load_export_payload(job.zip_path)
                messages = list(payload.get("messages", []))
                self.assertEqual(len(messages), 1)
                self.assertTrue(all(str(m.get("renderType") or "") == "transfer" for m in messages))
                self.assertEqual(manifest.get("filters", {}).get("messageTypes"), ["transfer"])
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data

    def test_system_revoke_exports_readable_revoker_content(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)

            prev_data = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                svc = self._reload_export_modules()
                job = self._create_job(
                    svc.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    message_types=["system"],
                    include_media=False,
                )
                self.assertEqual(job.status, "done", msg=job.error)

                payload, _, _ = self._load_export_payload(job.zip_path)
                revoke_msg = next((m for m in payload.get("messages", []) if int(m.get("serverId") or 0) == 1006), None)
                self.assertIsNotNone(revoke_msg)
                self.assertEqual(str(revoke_msg.get("renderType") or ""), "system")
                self.assertEqual(str(revoke_msg.get("content") or ""), "“测试好友”撤回了一条消息")
            finally:
                if prev_data is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data


if __name__ == "__main__":
    unittest.main()
