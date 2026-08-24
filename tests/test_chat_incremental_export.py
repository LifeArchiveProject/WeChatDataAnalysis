import hashlib
import io
import json
import os
import sqlite3
import threading
import time
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from test_chat_export_message_types_semantics import TestChatExportMessageTypesSemantics as _BaseChatExportTest


class TestChatIncrementalExport(unittest.TestCase):
    _prepare_account = _BaseChatExportTest._prepare_account
    _reload_export_modules = _BaseChatExportTest._reload_export_modules
    _seed_contact_db = _BaseChatExportTest._seed_contact_db
    _seed_session_db = _BaseChatExportTest._seed_session_db
    _seed_message_db = _BaseChatExportTest._seed_message_db
    _seed_media_files = _BaseChatExportTest._seed_media_files
    _seed_wxid_media_files = _BaseChatExportTest._seed_wxid_media_files
    _seed_source_info = _BaseChatExportTest._seed_source_info

    def _wait_for_job(self, manager, export_id: str):
        for _ in range(400):
            job = manager.get_job(export_id)
            if job and job.status in {"done", "error", "cancelled"}:
                return job
            time.sleep(0.05)
        self.fail("incremental export job did not finish in time")

    def _create_folder_job(
        self,
        manager,
        *,
        account: str,
        username: str | None = None,
        usernames=None,
        output_dir: Path,
        export_format: str = "json",
        privacy_mode: bool = False,
        reset_baseline: bool = False,
        repair_usernames=None,
        message_types=None,
        include_media: bool = False,
        missing_files=None,
        baseline=None,
    ):
        selected_usernames = list(usernames or ([username] if username else []))
        job = manager.create_job(
            account=account,
            source="decrypted",
            scope="selected",
            usernames=selected_usernames,
            export_format=export_format,
            start_time=None,
            end_time=None,
            include_hidden=False,
            include_official=False,
            include_media=include_media,
            media_kinds=["image", "emoji", "video", "video_thumb", "voice", "file"] if include_media else [],
            message_types=list(message_types or ["text"]),
            output_dir=str(output_dir) if output_dir is not None else None,
            allow_process_key_extract=False,
            download_remote_media=False,
            html_page_size=1000,
            privacy_mode=privacy_mode,
            file_name=None,
            output_mode="folder",
            folder_name="聊天增量测试",
            reset_baseline=reset_baseline,
            repair_usernames=list(repair_usernames or []),
            missing_files=list(missing_files or []),
            baseline=baseline,
        )
        return self._wait_for_job(manager, job.export_id)

    @staticmethod
    def _message_table(username: str) -> str:
        return f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"

    def _add_conversation(self, account_dir: Path, *, username: str, display_name: str, local_id: int = 20) -> None:
        connection = sqlite3.connect(str(account_dir / "contact.db"))
        try:
            connection.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (username, "", display_name, "", 1, 0, "", ""),
            )
            connection.commit()
        finally:
            connection.close()

        connection = sqlite3.connect(str(account_dir / "session.db"))
        try:
            connection.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", (username, 0, 1735689700))
            connection.commit()
        finally:
            connection.close()

        table = self._message_table(username)
        connection = sqlite3.connect(str(account_dir / "message_0.db"))
        try:
            connection.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (local_id, username))
            connection.execute(
                f"""
                CREATE TABLE {table} (
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
            connection.execute(
                f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 2001, 1, 1, local_id, 1735689701, f"{display_name}的文本", None),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _managed_message_file(folder: Path, suffix: str) -> Path:
        matches = list((folder / "conversations").glob(f"*/messages.{suffix}"))
        assert len(matches) == 1
        return matches[0]

    def test_unavailable_pending_media_is_deduplicated_without_repair_prompt(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_pending_account"
            username = "wxid_pending_friend"
            self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"
            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(first.status, "done", msg=first.error)
                state_path = first.folder_path / ".wechat-chat-export.json"
                baseline = json.loads(state_path.read_text(encoding="utf-8"))
                conversation = next(iter(baseline["conversations"].values()))
                missing_id = "f" * 32
                conversation["pendingMedia"] = [
                    {"kind": "emoji", "id": missing_id, "messageId": "1"},
                    {"kind": "emoji", "id": missing_id, "messageId": "2"},
                    {"kind": "emoji", "id": missing_id, "messageId": "3"},
                ]
                state_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

                checked = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(checked.status, "done", msg=checked.error)
                self.assertFalse(checked.repair_candidates)
                self.assertEqual(checked.unresolved_media.get("uniqueCount"), 1)
                self.assertEqual(checked.unresolved_media.get("referenceCount"), 3)
                self.assertIn("重复修复不会产生变化", checked.warning)

                migrated = json.loads(state_path.read_text(encoding="utf-8"))
                pending = next(iter(migrated["conversations"].values()))["pendingMedia"]
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0].get("occurrenceCount"), 3)
                self.assertEqual(pending[0].get("state"), "source_unavailable")
                self.assertFalse(pending[0].get("repairable"))

                before_repeat = (state_path.stat().st_mtime_ns, state_path.read_bytes())
                repeated = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(repeated.status, "done", msg=repeated.error)
                self.assertFalse(repeated.repair_candidates)
                self.assertEqual(repeated.unresolved_media.get("uniqueCount"), 1)
                self.assertEqual((state_path.stat().st_mtime_ns, state_path.read_bytes()), before_repeat)
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_html_direct_emoji_uses_remote_download_before_marking_missing(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_remote_emoji"
            account_dir.mkdir(parents=True)
            service = self._reload_export_modules()
            job = service.ExportJob(
                export_id="remote-emoji",
                account=account_dir.name,
                options={"outputMode": "folder", "downloadRemoteMedia": True},
            )
            message = {
                "id": "1",
                "renderType": "emoji",
                "emojiMd5": "f" * 32,
                "emojiUrl": "https://example.com/emoji.png",
            }
            report = {"missingMedia": [], "errors": []}
            with io.BytesIO() as buffer, zipfile.ZipFile(buffer, "w") as archive:
                with mock.patch.object(
                    service,
                    "_download_remote_image_to_zip",
                    return_value="media/remote/emoji.png",
                ) as downloader:
                    service._attach_offline_media(
                        zf=archive,
                        account_dir=account_dir,
                        conv_username="wxid_friend",
                        owner_username="wxid_friend",
                        msg=message,
                        media_written={},
                        report=report,
                        media_kinds=["emoji"],
                        allow_process_key_extract=False,
                        media_db_path=account_dir / "media.db",
                        media_index=None,
                        remote_written={},
                        lock=threading.Lock(),
                        job=job,
                    )
            downloader.assert_called_once()
            self.assertEqual(message["offlineMedia"][0]["path"], "media/remote/emoji.png")
            self.assertEqual(job.progress.media_copied, 1)
            self.assertEqual(job.progress.media_missing, 0)
            self.assertFalse(report["missingMedia"])

    def test_repair_prompt_only_appears_after_pending_media_becomes_recoverable(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_recoverable_account"
            username = "wxid_recoverable_friend"
            self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"
            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    include_media=True,
                    message_types=["text", "image"],
                )
                self.assertEqual(first.status, "done", msg=first.error)
                state_path = first.folder_path / ".wechat-chat-export.json"
                baseline = json.loads(state_path.read_text(encoding="utf-8"))
                conversation = next(iter(baseline["conversations"].values()))
                conversation["pendingMedia"] = [
                    {"kind": "image", "id": "a" * 32, "messageId": "2"},
                ]
                state_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

                checked = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    include_media=True,
                    message_types=["text", "image"],
                )
                self.assertEqual(checked.status, "done", msg=checked.error)
                self.assertEqual(len(checked.repair_candidates), 1)
                self.assertEqual(checked.repair_candidates[0].get("reasons"), ["media_recoverable"])
                self.assertEqual(checked.unresolved_media.get("uniqueCount"), 0)

                repaired = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    include_media=True,
                    message_types=["text", "image"],
                    repair_usernames=[username],
                )
                self.assertEqual(repaired.status, "done", msg=repaired.error)
                self.assertFalse(repaired.repair_candidates)
                repaired_state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertFalse(next(iter(repaired_state["conversations"].values()))["pendingMedia"])
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_folder_missing_progress_is_unique_but_zip_keeps_legacy_reference_count(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_missing_counts"
            account_dir.mkdir(parents=True)
            service = self._reload_export_modules()
            for output_mode, expected_missing in (("folder", 1), ("zip", 2)):
                with self.subTest(output_mode=output_mode):
                    job = service.ExportJob(
                        export_id=f"missing-{output_mode}",
                        account=account_dir.name,
                        options={"outputMode": output_mode, "downloadRemoteMedia": False},
                    )
                    report = {"missingMedia": [], "errors": []}
                    media_written = {}
                    with io.BytesIO() as buffer, zipfile.ZipFile(buffer, "w") as archive:
                        for message_id in ("1", "2"):
                            service._attach_offline_media(
                                zf=archive,
                                account_dir=account_dir,
                                conv_username="wxid_friend",
                                owner_username="wxid_friend",
                                msg={
                                    "id": message_id,
                                    "renderType": "emoji",
                                    "emojiMd5": "f" * 32,
                                },
                                media_written=media_written,
                                report=report,
                                media_kinds=["emoji"],
                                allow_process_key_extract=False,
                                media_db_path=account_dir / "media.db",
                                media_index=None,
                                lock=threading.Lock(),
                                job=job,
                            )
                    self.assertEqual(job.progress.media_missing, expected_missing)
                    self.assertEqual(job.progress.media_missing_references, 2)
                    self.assertEqual(len(report["missingMedia"]), 2)

    def test_first_run_and_no_change_reuse_all_formats(self):
        for export_format, suffix in (("html", "html"), ("json", "json"), ("txt", "txt"), ("excel", "xlsx")):
            with self.subTest(export_format=export_format), TemporaryDirectory() as td:
                root = Path(td)
                account = "wxid_incremental"
                username = "wxid_friend"
                self._prepare_account(root, account=account, username=username)
                output_dir = root / "exports"

                previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
                try:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                    service = self._reload_export_modules()
                    first = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=output_dir,
                        export_format=export_format,
                    )
                    self.assertEqual(first.status, "done", msg=first.error)
                    folder = output_dir / "聊天增量测试"
                    message_file = self._managed_message_file(folder, suffix)
                    before = (message_file.stat().st_mtime_ns, message_file.read_bytes())

                    second = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=output_dir,
                        export_format=export_format,
                    )
                    self.assertEqual(second.status, "done", msg=second.error)
                    after = (message_file.stat().st_mtime_ns, message_file.read_bytes())
                    self.assertEqual(before, after)
                    self.assertEqual(second.incremental.get("filesChanged"), 0)
                    self.assertEqual(second.incremental.get("conversationsUpdated"), 0)
                    self.assertEqual(second.incremental.get("conversationsReused"), 1)

                    if export_format == "json":
                        json.loads(message_file.read_text(encoding="utf-8"))
                    elif export_format == "txt":
                        message_file.read_text(encoding="utf-8")
                    elif export_format == "excel":
                        import zipfile

                        self.assertTrue(zipfile.is_zipfile(message_file))
                    else:
                        html_text = message_file.read_text(encoding="utf-8").lower()
                        self.assertIn("<!doctype html>", html_text)
                        self.assertNotIn("data-wce-sri", html_text)
                        self.assertTrue((folder / "assets" / "chat-export.css").is_file())
                        self.assertTrue((folder / "assets" / "chat-export.js").is_file())
                        self.assertFalse((folder / "_integrity").exists())
                finally:
                    if previous is None:
                        os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                    else:
                        os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_html_folder_runtime_disables_zip_integrity_and_migrates_old_asset(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(first.status, "done", msg=first.error)
                folder = output_dir / "聊天增量测试"
                runtime_path = folder / "assets" / "chat-export.js"
                folder_runtime = runtime_path.read_text(encoding="utf-8")
                self.assertIn("data-wce-folder-mode", folder_runtime)
                self.assertIn("window.__WCE_VERIFY_FRAGMENT__ = () => true", folder_runtime)
                self.assertNotIn("const integrityOk = await initExportIntegrity()", folder_runtime)

                html_files = [folder / "index.html", self._managed_message_file(folder, "html")]
                for html_file in html_files:
                    html_text = html_file.read_text(encoding="utf-8")
                    self.assertNotIn("data-wce-sri", html_text)
                    self.assertNotIn("data-wce-integrity-bundle", html_text)
                message_before = (html_files[1].stat().st_mtime_ns, html_files[1].read_bytes())

                # 模拟已经导出的旧版目录：文件存在且基线摘要也匹配，但运行时仍会阻断目录页。
                old_runtime = service._html_export_runtime_js(service._load_wce_integrity_native())
                old_runtime_bytes = old_runtime.encode("utf-8")
                runtime_path.write_bytes(old_runtime_bytes)
                state_path = folder / ".wechat-chat-export.json"
                baseline = json.loads(state_path.read_text(encoding="utf-8"))
                baseline["files"]["assets/chat-export.js"] = {
                    "sha256": hashlib.sha256(old_runtime_bytes).hexdigest(),
                    "size": len(old_runtime_bytes),
                }
                state_path.write_text(
                    json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

                migrated = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(migrated.status, "done", msg=migrated.error)
                self.assertEqual(runtime_path.read_text(encoding="utf-8"), folder_runtime)
                self.assertEqual((html_files[1].stat().st_mtime_ns, html_files[1].read_bytes()), message_before)
                self.assertEqual(migrated.incremental.get("filesChanged"), 1)
                migrated_baseline = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    migrated_baseline["files"]["assets/chat-export.js"]["sha256"],
                    hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
                )

                no_change = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(no_change.status, "done", msg=no_change.error)
                self.assertEqual(no_change.incremental.get("filesChanged"), 0)
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_html_folder_uses_one_shared_session_catalog_across_incremental_pages(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            first_username = "wxid_friend"
            second_username = "wxid_second_friend"
            account_dir = self._prepare_account(root, account=account, username=first_username)
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=first_username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(first.status, "done", msg=first.error)
                folder = output_dir / "聊天增量测试"
                first_page = self._managed_message_file(folder, "html")

                # 模拟旧版增量页：聊天正文仍受基线管理，但页面本身还没有公共目录脚本标签。
                legacy_text = first_page.read_text(encoding="utf-8").replace(
                    '  <script defer src="../../assets/chat-sessions.js" data-wce-folder-sessions="1"></script>\n',
                    "",
                )
                self.assertNotIn("data-wce-folder-sessions", legacy_text)
                first_page.write_text(legacy_text, encoding="utf-8")
                state_path = folder / ".wechat-chat-export.json"
                baseline = json.loads(state_path.read_text(encoding="utf-8"))
                first_page_relative = first_page.relative_to(folder).as_posix()
                first_page_bytes = first_page.read_bytes()
                baseline["files"][first_page_relative] = {
                    "sha256": hashlib.sha256(first_page_bytes).hexdigest(),
                    "size": len(first_page_bytes),
                }
                state_path.write_text(
                    json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                legacy_before = (first_page.stat().st_mtime_ns, first_page_bytes)

                self._add_conversation(
                    account_dir,
                    username=second_username,
                    display_name="第二个联系人",
                )
                updated = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=second_username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(updated.status, "done", msg=updated.error)
                self.assertEqual((first_page.stat().st_mtime_ns, first_page.read_bytes()), legacy_before)

                catalog_path = folder / "assets" / "chat-sessions.js"
                catalog_text = catalog_path.read_text(encoding="utf-8")
                prefix = "window.__WCE_FOLDER_SESSIONS__="
                self.assertTrue(catalog_text.startswith(prefix))
                catalog = json.loads(catalog_text[len(prefix):].rstrip(";\r\n"))
                self.assertEqual(len(catalog.get("items") or []), 2)
                catalog_directories = {
                    str(item.get("convDir") or "")
                    for item in catalog.get("items") or []
                }
                current_baseline = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    catalog_directories,
                    {
                        str(value.get("directory") or "")
                        for value in current_baseline.get("conversations", {}).values()
                    },
                )

                runtime_text = (folder / "assets" / "chat-export.js").read_text(encoding="utf-8")
                self.assertIn("loadFolderSessionCatalog", runtime_text)
                self.assertIn("syncFolderSessionCatalog", runtime_text)
                self.assertIn("new URL('chat-sessions.js', wceFolderRuntimeSrc)", runtime_text)

                second_page = next(
                    page
                    for page in (folder / "conversations").glob("*/messages.html")
                    if page != first_page
                )
                self.assertIn("data-wce-folder-sessions", second_page.read_text(encoding="utf-8"))

                no_change = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=second_username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(no_change.status, "done", msg=no_change.error)
                self.assertEqual(no_change.incremental.get("filesChanged"), 0)
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_html_folder_shared_session_catalog_respects_privacy_mode(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_private_account"
            username = "wxid_private_friend"
            self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                job = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    export_format="html",
                    privacy_mode=True,
                )
                self.assertEqual(job.status, "done", msg=job.error)
                catalog_text = (job.folder_path / "assets" / "chat-sessions.js").read_text(encoding="utf-8")
                self.assertNotIn(account, catalog_text)
                self.assertNotIn(username, catalog_text)
                self.assertNotIn("测试好友", catalog_text)
                self.assertNotIn("普通文本消息", catalog_text)
                catalog = json.loads(
                    catalog_text.removeprefix("window.__WCE_FOLDER_SESSIONS__=").rstrip(";\r\n")
                )
                self.assertEqual(len(catalog.get("items") or []), 1)
                item = catalog["items"][0]
                self.assertEqual(item.get("username"), "")
                self.assertEqual(item.get("avatarPath"), "")
                self.assertEqual(item.get("previewText"), "")
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_html_existing_conversation_reads_and_renders_only_new_messages(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            username = "wxid_friend"
            account_dir = self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    export_format="html",
                )
                self.assertEqual(first.status, "done", msg=first.error)
                folder = output_dir / "聊天增量测试"
                message_file = self._managed_message_file(folder, "html")
                self.assertIn("普通文本消息", message_file.read_text(encoding="utf-8"))
                first_baseline = json.loads((folder / ".wechat-chat-export.json").read_text(encoding="utf-8"))
                first_conversation = next(iter(first_baseline["conversations"].values()))
                first_watermark_time = int(first_conversation["watermark"][0])

                table = self._message_table(username)
                connection = sqlite3.connect(str(account_dir / "message_0.db"))
                try:
                    connection.execute(
                        f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (8, 1008, 1, 8, 2, 1735689608, "只渲染这一条增量消息", None),
                    )
                    connection.commit()
                finally:
                    connection.close()

                original_full_probe = service._probe_incremental_conversation
                original_estimator = service._estimate_conversation_message_count
                estimate_start_times = []

                def reject_full_probe(**_kwargs):
                    raise AssertionError("已有分页会话不应重新扫描完整历史")

                def track_incremental_estimate(**kwargs):
                    estimate_start_times.append(kwargs.get("start_time"))
                    return original_estimator(**kwargs)

                service._probe_incremental_conversation = reject_full_probe
                service._estimate_conversation_message_count = track_incremental_estimate
                try:
                    appended = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=output_dir,
                        export_format="html",
                    )
                    self.assertEqual(appended.status, "done", msg=appended.error)
                    self.assertEqual(appended.incremental.get("messagesAdded"), 1)
                    self.assertEqual(appended.progress.messages_exported, 1)
                    self.assertEqual(appended.progress.current_conversation_messages_total, 1)
                    self.assertTrue(estimate_start_times)
                    self.assertEqual(estimate_start_times[0], first_watermark_time)

                    current_html = message_file.read_text(encoding="utf-8")
                    self.assertIn("只渲染这一条增量消息", current_html)
                    self.assertNotIn("普通文本消息", current_html)
                    page_file = message_file.parent / "pages" / "page-0001.js"
                    self.assertTrue(page_file.is_file())
                    self.assertIn("普通文本消息", page_file.read_text(encoding="utf-8"))
                    self.assertIn('"totalPages": 2', current_html)

                    before_noop = (message_file.stat().st_mtime_ns, message_file.read_bytes())
                    no_change = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=output_dir,
                        export_format="html",
                    )
                    self.assertEqual(no_change.status, "done", msg=no_change.error)
                    self.assertEqual(no_change.incremental.get("filesChanged"), 0)
                    self.assertEqual((message_file.stat().st_mtime_ns, message_file.read_bytes()), before_noop)
                finally:
                    service._probe_incremental_conversation = original_full_probe
                    service._estimate_conversation_message_count = original_estimator
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_new_message_then_history_repair(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            username = "wxid_friend"
            account_dir = self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(first.status, "done", msg=first.error)
                message_file = self._managed_message_file(output_dir / "聊天增量测试", "json")

                table = self._message_table(username)
                connection = sqlite3.connect(str(account_dir / "message_0.db"))
                try:
                    connection.execute(
                        f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (8, 1008, 1, 8, 2, 1735689608, "增量新增消息", None),
                    )
                    connection.commit()
                finally:
                    connection.close()

                appended = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(appended.status, "done", msg=appended.error)
                self.assertEqual(appended.incremental.get("messagesAdded"), 1)
                payload = json.loads(message_file.read_text(encoding="utf-8"))
                contents = [str(item.get("content") or "") for item in payload.get("messages", [])]
                self.assertEqual(contents.count("增量新增消息"), 1)

                before_repair = message_file.read_bytes()
                connection = sqlite3.connect(str(account_dir / "message_0.db"))
                try:
                    connection.execute(
                        f"UPDATE {table} SET message_content = ? WHERE local_id = 4",
                        ("历史消息已修改",),
                    )
                    connection.commit()
                finally:
                    connection.close()

                detected = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(detected.status, "done", msg=detected.error)
                self.assertEqual(message_file.read_bytes(), before_repair)
                self.assertEqual(len(detected.repair_candidates), 1)

                repaired = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    repair_usernames=[username],
                )
                self.assertEqual(repaired.status, "done", msg=repaired.error)
                payload = json.loads(message_file.read_text(encoding="utf-8"))
                contents = [str(item.get("content") or "") for item in payload.get("messages", [])]
                self.assertIn("历史消息已修改", contents)

                connection = sqlite3.connect(str(account_dir / "message_0.db"))
                try:
                    connection.execute(
                        f"UPDATE {table} SET message_content = ? WHERE local_id = 4",
                        ("历史消息再次修改",),
                    )
                    connection.execute(
                        f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (9, 1009, 1, 9, 2, 1735689609, "历史变化并存的新消息", None),
                    )
                    connection.commit()
                finally:
                    connection.close()
                synchronized = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                )
                self.assertEqual(synchronized.status, "done", msg=synchronized.error)
                self.assertEqual(synchronized.incremental.get("messagesAdded"), 1)
                self.assertEqual(synchronized.incremental.get("historyChangesSynced"), 1)
                self.assertFalse(synchronized.repair_candidates)
                payload = json.loads(message_file.read_text(encoding="utf-8"))
                contents = [str(item.get("content") or "") for item in payload.get("messages", [])]
                self.assertIn("历史消息再次修改", contents)
                self.assertEqual(contents.count("历史变化并存的新消息"), 1)
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous
    def test_config_conflict_and_privacy_baseline(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_private_account"
            username = "wxid_private_friend"
            self._prepare_account(root, account=account, username=username)
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    privacy_mode=True,
                )
                self.assertEqual(first.status, "done", msg=first.error)
                baseline_text = (first.folder_path / ".wechat-chat-export.json").read_text(encoding="utf-8")
                self.assertNotIn(account, baseline_text)
                self.assertNotIn(username, baseline_text)
                self.assertNotIn("测试好友", baseline_text)
                self.assertNotIn("普通文本消息", baseline_text)
                user_file = first.folder_path / "用户保留文件.txt"
                user_file.write_text("不要删除", encoding="utf-8")

                with self.assertRaises(service.ChatIncrementalError) as captured:
                    self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=output_dir,
                        privacy_mode=True,
                        message_types=["text", "system"],
                    )
                self.assertEqual(captured.exception.code, "incremental_config_mismatch")
                rebuilt = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=output_dir,
                    privacy_mode=True,
                    message_types=["text", "system"],
                    reset_baseline=True,
                )
                self.assertEqual(rebuilt.status, "done", msg=rebuilt.error)
                self.assertEqual(user_file.read_text(encoding="utf-8"), "不要删除")
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_unselected_conversation_is_preserved_and_missing_file_is_restored(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            first_username = "wxid_friend"
            second_username = "wxid_friend_two"
            account_dir = self._prepare_account(root, account=account, username=first_username)
            self._add_conversation(account_dir, username=second_username, display_name="第二位好友")
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    usernames=[first_username, second_username],
                    output_dir=output_dir,
                )
                self.assertEqual(first.status, "done", msg=first.error)
                folder = output_dir / "聊天增量测试"
                baseline = json.loads((folder / ".wechat-chat-export.json").read_text(encoding="utf-8"))
                self.assertEqual(len(baseline["conversations"]), 2)
                with self.assertRaises(service.ChatIncrementalError) as incomplete_reset:
                    self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=first_username,
                        output_dir=output_dir,
                        reset_baseline=True,
                    )
                self.assertEqual(incomplete_reset.exception.code, "incremental_reset_incomplete")

                second_state = next(
                    state
                    for state in baseline["conversations"].values()
                    if state.get("displayName") == "第二位好友"
                )
                second_message = folder / Path(second_state["directory"]) / "messages.json"
                second_before = (second_message.stat().st_mtime_ns, second_message.read_bytes())
                user_file = folder / "我的说明.txt"
                user_file.write_text("不能删除", encoding="utf-8")

                table = self._message_table(first_username)
                connection = sqlite3.connect(str(account_dir / "message_0.db"))
                try:
                    connection.execute(
                        f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (8, 1008, 1, 8, 2, 1735689800, "只更新第一个会话", None),
                    )
                    connection.commit()
                finally:
                    connection.close()

                updated = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=first_username,
                    output_dir=output_dir,
                )
                self.assertEqual(updated.status, "done", msg=updated.error)
                self.assertEqual((second_message.stat().st_mtime_ns, second_message.read_bytes()), second_before)
                self.assertEqual(user_file.read_text(encoding="utf-8"), "不能删除")

                current_baseline = json.loads((folder / ".wechat-chat-export.json").read_text(encoding="utf-8"))
                first_state = next(
                    state
                    for state in current_baseline["conversations"].values()
                    if state.get("displayName") == "测试好友"
                )
                first_message = folder / Path(first_state["directory"]) / "messages.json"
                first_message.unlink()

                restored = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=second_username,
                    output_dir=folder,
                )
                self.assertEqual(restored.status, "done", msg=restored.error)
                self.assertTrue(first_message.is_file())
                self.assertEqual((second_message.stat().st_mtime_ns, second_message.read_bytes()), second_before)
                self.assertEqual(restored.incremental.get("filesRecovered"), 1)
                self.assertFalse((folder / "聊天增量测试").exists())
                self.assertTrue(user_file.is_file())

                connection = sqlite3.connect(str(account_dir / "contact.db"))
                try:
                    connection.execute(
                        "UPDATE contact SET nick_name = ? WHERE username = ?",
                        ("改名后的好友", first_username),
                    )
                    connection.commit()
                finally:
                    connection.close()
                renamed = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=first_username,
                    output_dir=output_dir,
                )
                self.assertEqual(renamed.status, "done", msg=renamed.error)
                self.assertFalse(renamed.repair_candidates)
                renamed_baseline = json.loads((folder / ".wechat-chat-export.json").read_text(encoding="utf-8"))
                renamed_state = next(
                    state
                    for state in renamed_baseline["conversations"].values()
                    if state.get("displayName") == "改名后的好友"
                )
                self.assertEqual(renamed_state.get("directory"), first_state.get("directory"))
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_missing_chat_and_media_are_restored_for_all_formats(self):
        format_suffixes = (
            ("html", "html"),
            ("json", "json"),
            ("txt", "txt"),
            ("excel", "xlsx"),
        )
        for export_format, suffix in format_suffixes:
            with self.subTest(export_format=export_format), TemporaryDirectory() as td:
                root = Path(td)
                account = "wxid_incremental"
                first_username = "wxid_friend"
                second_username = "wxid_friend_two"
                account_dir = self._prepare_account(root, account=account, username=first_username)
                self._add_conversation(account_dir, username=second_username, display_name="第二位好友")
                output_dir = root / "exports"

                previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
                try:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                    service = self._reload_export_modules()
                    initial = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        usernames=[first_username, second_username],
                        output_dir=output_dir,
                        export_format=export_format,
                        message_types=["text", "image"],
                        include_media=True,
                    )
                    self.assertEqual(initial.status, "done", msg=initial.error)

                    folder = output_dir / "聊天增量测试"
                    baseline = json.loads((folder / ".wechat-chat-export.json").read_text(encoding="utf-8"))
                    first_state = next(
                        state
                        for state in baseline["conversations"].values()
                        if state.get("displayName") == "测试好友"
                    )
                    second_state = next(
                        state
                        for state in baseline["conversations"].values()
                        if state.get("displayName") == "第二位好友"
                    )
                    first_message = folder / Path(first_state["directory"]) / f"messages.{suffix}"
                    second_message = folder / Path(second_state["directory"]) / f"messages.{suffix}"
                    second_before = (second_message.stat().st_mtime_ns, second_message.read_bytes())
                    media_paths = [
                        path for path in baseline["files"]
                        if path.startswith("media/images/")
                    ]
                    self.assertTrue(media_paths)

                    first_message.unlink()
                    for media_path in media_paths:
                        (folder / Path(media_path)).unlink()

                    restored = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=second_username,
                        output_dir=output_dir,
                        export_format=export_format,
                        message_types=["text", "image"],
                        include_media=True,
                    )
                    self.assertEqual(restored.status, "done", msg=restored.error)
                    self.assertTrue(first_message.is_file())
                    for media_path in media_paths:
                        self.assertTrue((folder / Path(media_path)).is_file())
                    self.assertEqual(
                        (second_message.stat().st_mtime_ns, second_message.read_bytes()),
                        second_before,
                    )
                    self.assertEqual(
                        restored.incremental.get("filesRecovered"),
                        1 + len(media_paths),
                    )
                    self.assertEqual(
                        restored.incremental.get("conversationsUpdated"),
                        1,
                        msg=export_format,
                    )
                    self.assertEqual(restored.incremental.get("conversationsReused"), 1)
                finally:
                    if previous is None:
                        os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                    else:
                        os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_shared_media_is_removed_only_after_last_owner_is_rebuilt(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            first_username = "wxid_friend"
            second_username = "wxid_friend_two"
            account_dir = self._prepare_account(root, account=account, username=first_username)
            self._add_conversation(account_dir, username=second_username, display_name="第二位好友")
            table_two = self._message_table(second_username)
            image_xml = '<msg><img md5="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" cdnthumburl="img_file_id_1" /></msg>'
            connection = sqlite3.connect(str(account_dir / "message_0.db"))
            try:
                connection.execute(
                    f"INSERT INTO {table_two} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (2, 2002, 3, 2, 20, 1735689702, image_xml, None),
                )
                connection.commit()
            finally:
                connection.close()
            output_dir = root / "exports"

            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                first = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    usernames=[first_username, second_username],
                    output_dir=output_dir,
                    message_types=["image"],
                    include_media=True,
                )
                self.assertEqual(first.status, "done", msg=first.error)
                folder = output_dir / "聊天增量测试"
                state_path = folder / ".wechat-chat-export.json"
                baseline = json.loads(state_path.read_text(encoding="utf-8"))
                media_paths = [path for path in baseline["files"] if path.startswith("media/images/")]
                self.assertEqual(len(media_paths), 1)
                media_path = media_paths[0]
                self.assertEqual(len(baseline["files"][media_path].get("owners") or []), 2)

                media_file = folder / Path(media_path)
                media_file.unlink()
                restored = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=second_username,
                    output_dir=output_dir,
                    message_types=["image"],
                    include_media=True,
                )
                self.assertEqual(restored.status, "done", msg=restored.error)
                self.assertTrue(media_file.is_file())
                self.assertEqual(restored.incremental.get("filesRecovered"), 1)
                self.assertEqual(restored.incremental.get("conversationsUpdated"), 1)

                for username in (first_username, second_username):
                    table = self._message_table(username)
                    connection = sqlite3.connect(str(account_dir / "message_0.db"))
                    try:
                        connection.execute(f"DELETE FROM {table} WHERE local_type = 3")
                        connection.commit()
                    finally:
                        connection.close()
                    repaired = self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=output_dir,
                        message_types=["image"],
                        include_media=True,
                        repair_usernames=[username],
                    )
                    self.assertEqual(repaired.status, "done", msg=repaired.error)
                    if username == first_username:
                        self.assertTrue(media_file.is_file())
                        baseline = json.loads(state_path.read_text(encoding="utf-8"))
                        self.assertEqual(len(baseline["files"][media_path].get("owners") or []), 1)
                    else:
                        self.assertFalse(media_file.exists())
                        baseline = json.loads(state_path.read_text(encoding="utf-8"))
                        self.assertNotIn(media_path, baseline["files"])
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_nonempty_unknown_corrupt_and_unsafe_baselines_are_rejected(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)
            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                direct = root / "聊天增量测试"
                direct.mkdir()
                (direct / "用户文件.txt").write_text("保留", encoding="utf-8")
                with self.assertRaises(service.ChatIncrementalError) as unknown:
                    self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=direct,
                    )
                self.assertEqual(unknown.exception.code, "incremental_directory_not_empty")
                with self.assertRaises(service.ChatIncrementalError) as unsafe_reset:
                    self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=direct,
                        reset_baseline=True,
                    )
                self.assertEqual(unsafe_reset.exception.code, "incremental_directory_not_empty")

                (direct / ".wechat-chat-export.json").write_text("{broken", encoding="utf-8")
                with self.assertRaises(service.ChatIncrementalError) as corrupt:
                    self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=direct,
                        reset_baseline=True,
                    )
                self.assertEqual(corrupt.exception.code, "incremental_baseline_invalid")

                malicious = {
                    "schemaVersion": 1,
                    "artifactType": "wechat-chat-incremental-folder",
                    "account": account,
                    "folderName": "聊天增量测试",
                    "configFingerprint": "unused",
                    "conversations": {},
                    "files": {"../outside.txt": {"size": 1, "sha256": "x"}},
                }
                with self.assertRaises(service.ChatIncrementalError) as unsafe:
                    self._create_folder_job(
                        service.CHAT_EXPORT_MANAGER,
                        account=account,
                        username=username,
                        output_dir=None,
                        baseline=malicious,
                    )
                self.assertEqual(unsafe.exception.code, "incremental_unsafe_path")
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous

    def test_browser_patch_manifest_keeps_state_last_and_commit_cleans_staging(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_incremental"
            username = "wxid_friend"
            self._prepare_account(root, account=account, username=username)
            previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                service = self._reload_export_modules()
                job = self._create_folder_job(
                    service.CHAT_EXPORT_MANAGER,
                    account=account,
                    username=username,
                    output_dir=None,
                )
                self.assertEqual(job.status, "done", msg=job.error)
                self.assertIsNone(job.folder_path)
                self.assertTrue(job.staged_files)
                manifest = job.change_manifest
                self.assertTrue(manifest.get("files"))
                self.assertEqual(manifest.get("state", {}).get("path"), ".wechat-chat-export.json")
                self.assertFalse(manifest.get("state", {}).get("unchanged"))
                for entry in manifest["files"]:
                    self.assertNotIn("..", str(entry.get("path") or "").split("/"))
                    self.assertTrue(service.CHAT_EXPORT_MANAGER.get_staged_file(job.export_id, entry["fileId"]).is_file())
                state_file = service.CHAT_EXPORT_MANAGER.get_staged_file(
                    job.export_id,
                    manifest["state"]["fileId"],
                )
                state = json.loads(state_file.read_text(encoding="utf-8"))
                self.assertEqual(state.get("artifactType"), "wechat-chat-incremental-folder")
                staging_dir = job.staging_dir
                self.assertTrue(service.CHAT_EXPORT_MANAGER.commit_staged_files(job.export_id))
                self.assertFalse(staging_dir.exists())
                self.assertFalse(job.staged_files)
            finally:
                if previous is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = previous


# 仅借用既有测试的数据构造方法，避免 pytest 重复收集原测试类。
del _BaseChatExportTest
