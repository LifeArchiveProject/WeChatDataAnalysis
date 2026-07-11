import json
import hashlib
import os
import sqlite3
import sys
import threading
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import record_export


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/api/records/export",
            "headers": [],
        }
    )


class TestRecordExport(unittest.TestCase):
    def test_favorites_loader_always_requests_realtime(self):
        calls = []

        def fake_list_favorites(**kwargs):
            calls.append(kwargs)
            return {
                "account": "wxid_test",
                "dataSource": "realtime",
                "items": [],
                "hasMore": False,
            }

        req = record_export.RecordExportRequest(
            account="wxid_test",
            dataset="favorites",
            format="json",
            output_dir="C:\\temp",
        )
        with patch.object(record_export, "list_favorites", side_effect=fake_list_favorites):
            items, meta = record_export._load_records(_request(), req)

        self.assertEqual(items, [])
        self.assertEqual(meta["dataSource"], "realtime")
        self.assertEqual(calls[0]["source"], "realtime")
        self.assertEqual(calls[0]["kind"], "all")

    def test_type_filter_uses_natural_dataset_types(self):
        favorite = {
            "textBlocks": ["hello"],
            "attachments": [{"renderType": "video"}, {"renderType": "file"}],
        }
        self.assertEqual(record_export._record_types("favorites", favorite), {"text", "video", "file"})
        self.assertEqual(record_export._record_types("friend-verifications", {"isSender": True}), {"outgoing"})
        self.assertEqual(record_export._record_types("payments", {"kind": "redpacket"}), {"redpacket"})
        for state in ("received", "expired", "returned"):
            with self.subTest(state=state):
                self.assertEqual(
                    record_export._record_types("payments", {"kind": "transfer", "transferState": state}),
                    {state},
                )

        payments = [
            {"kind": "transfer", "transferState": "received"},
            {"kind": "transfer", "transferState": "expired"},
            {"kind": "transfer", "transferState": "returned"},
            {"kind": "redpacket"},
        ]
        self.assertEqual(
            record_export._filter_records("payments", payments, {"expired", "returned"}),
            payments[1:3],
        )
        self.assertEqual(record_export._filter_records("payments", payments, {"transfer"}), [])

    def test_favorite_adapter_keeps_summary_when_text_blocks_are_empty(self):
        messages = record_export._favorite_chat_messages(
            [
                {
                    "localId": 9,
                    "type": 1,
                    "summary": "收藏摘要",
                    "textBlocks": ["", "   "],
                    "attachments": [],
                    "sourceUsername": "wxid_friend",
                }
            ]
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["renderType"], "text")
        self.assertEqual(messages[0]["content"], "收藏摘要")

    def test_favorite_voice_uses_source_message_server_id(self):
        messages = record_export._favorite_chat_messages(
            [
                {
                    "localId": 10,
                    "serverId": 100,
                    "sourceId": "700",
                    "type": 3,
                    "textBlocks": [],
                    "attachments": [
                        {
                            "dataId": "999",
                            "dataType": 3,
                            "renderType": "voice",
                            "typeLabel": "语音",
                        }
                    ],
                    "originalMessage": {"isSent": True},
                    "sourceUsername": "wxid_friend",
                }
            ]
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["renderType"], "voice")
        self.assertEqual(messages[0]["serverId"], 700)
        self.assertTrue(messages[0]["isSent"])

    def test_favorite_adapter_keeps_attachment_data_ids_for_media_lookup(self):
        messages = record_export._favorite_chat_messages(
            [
                {
                    "localId": 11,
                    "type": 4,
                    "attachments": [
                        {
                            "dataId": "video-data-id",
                            "dataType": 4,
                            "renderType": "video",
                            "fullMd5": "a" * 32,
                            "thumbMd5": "b" * 32,
                        },
                        {
                            "dataId": "file-data-id",
                            "dataType": 8,
                            "renderType": "file",
                            "fullMd5": "c" * 32,
                        },
                    ],
                    "sourceUsername": "wxid_friend",
                }
            ]
        )

        video, file = messages
        self.assertEqual(video["videoFileId"], "video-data-id")
        self.assertEqual(video["videoThumbFileId"], "video-data-id")
        self.assertEqual(file["fileFileId"], "file-data-id")

    def test_chat_history_favorite_keeps_one_embedded_archive(self):
        record_item = "<recordinfo><datalist><dataitem datatype=\"4\"><fullmd5>{}</fullmd5></dataitem></datalist></recordinfo>".format("d" * 32)
        messages = record_export._favorite_chat_messages(
            [
                {
                    "localId": 12,
                    "type": 14,
                    "title": "聊天记录",
                    "originalMessage": {"recordItem": record_item},
                    "textBlocks": ["不应作为合集外的独立消息导出"],
                    "attachments": [
                        {
                            "dataId": "embedded-video",
                            "dataType": 5,
                            "renderType": "video",
                            "fullMd5": "d" * 32,
                        }
                    ],
                    "sourceUsername": "wxid_friend",
                }
            ]
        )

        self.assertEqual([message["renderType"] for message in messages], ["chatHistory"])
        self.assertEqual(messages[0]["recordItem"], record_item)

    def test_biz_export_collects_all_scanned_pages_for_one_account(self):
        calls = []

        def fake_biz_messages(**kwargs):
            calls.append(kwargs)
            if kwargs["offset"] == 0:
                return {
                    "status": "success",
                    "account": "wxid_test",
                    "source": "realtime",
                    "data": [{"local_id": 1, "title": "第一篇"}],
                    "scanned": 2,
                    "hasMore": True,
                }
            return {
                "status": "success",
                "account": "wxid_test",
                "source": "realtime",
                "data": [{"local_id": 3, "title": "第二篇"}],
                "scanned": 1,
                "hasMore": False,
            }

        req = record_export.RecordExportRequest(
            account="wxid_test",
            dataset="biz",
            username="gh_test",
            subject_name="测试服务号",
            format="json",
            output_dir="C:\\temp",
        )
        with patch.object(record_export, "get_biz_messages", side_effect=fake_biz_messages):
            items, meta = record_export._load_records(_request(), req)

        self.assertEqual([item["local_id"] for item in items], [1, 3])
        self.assertEqual([call["offset"] for call in calls], [0, 2])
        self.assertEqual(meta["dataSource"], "realtime")

    def test_general_record_html_uses_the_same_dataset_layouts_as_the_app(self):
        fixtures = {
            "mini-programs": {
                "titles": ["示例小程序"],
                "brandIconUrl": "https://example.test/mini.png",
                "summary": {"registerBody": "服务说明", "categories": ["工具"]},
            },
            "finder": {
                "finderUsername": "示例视频号",
                "finderLiveId": 123,
                "liveStatus": 1,
                "coverUrl": "https://example.test/finder.png",
            },
            "payments": {
                "kind": "redpacket",
                "sessionName": "wxid_friend",
                "senderUserName": "wxid_friend",
                "messageCreateTimeText": "2026-07-11 12:00:00",
            },
        }
        expected_classes = {
            "mini-programs": 'class="mini-entry"',
            "finder": 'class="finder-entry"',
            "payments": 'class="ledger-row"',
        }

        for dataset, item in fixtures.items():
            with self.subTest(dataset=dataset):
                rendered = record_export._render_html(
                    {
                        "dataset": dataset,
                        "account": "wxid_test",
                        "dataSource": "realtime",
                        "generatedAt": "2026-07-11T12:00:00+08:00",
                        "items": [item],
                    }
                )
                self.assertIn('class="records-frame"', rendered)
                self.assertIn(expected_classes[dataset], rendered)
                self.assertNotIn('class="message"', rendered)

    def test_biz_html_export_uses_selected_service_account_identity(self):
        rendered = record_export._render_html(
            {
                "dataset": "biz",
                "account": "wxid_test",
                "subjectName": "测试服务号",
                "dataSource": "realtime",
                "generatedAt": "2026-07-11T12:00:00+08:00",
                "items": [{"title": "文章标题", "des": "文章摘要", "create_time": 100}],
            }
        )

        self.assertIn("测试服务号", rendered)
        self.assertIn("文章标题", rendered)
        self.assertIn('class="records-grid biz"', rendered)

    def test_json_txt_and_html_exports_are_written_and_escaped(self):
        source_items = [
            {
                "localId": 1,
                "type": 1,
                "typeLabel": "文本",
                "textBlocks": ["<script>alert(1)</script>"],
                "attachments": [],
                "sourceUsername": "wxid_friend",
                "senderContact": {"displayName": "测试好友", "avatar": ""},
                "updateTimeText": "2026-07-10 10:00",
            },
            {
                "localId": 2,
                "type": 4,
                "typeLabel": "视频",
                "textBlocks": [],
                "attachments": [{"renderType": "video", "typeLabel": "视频", "fullMd5": "a" * 32}],
                "sourceUsername": "wxid_friend",
            },
        ]
        source_meta = {"account": "wxid_test", "dataSource": "realtime", "database": "live/favorite.db"}

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "output" / "databases" / "wxid_test"
            output_dir = root / "exports"
            account_dir.mkdir(parents=True)
            (account_dir / "_source.json").write_text(
                json.dumps({"db_storage_path": str(root / "missing-db-storage")}),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"WECHAT_TOOL_DATA_DIR": str(root)}):
                for fmt in ("json", "txt", "html"):
                    with self.subTest(format=fmt):
                        req = record_export.RecordExportRequest(
                            account="wxid_test",
                            dataset="favorites",
                            format=fmt,
                            types=["text"],
                            output_dir=str(output_dir),
                            file_name=f"unsafe/name.{fmt}",
                        )
                        with patch.object(record_export, "_load_records", return_value=(source_items, source_meta)):
                            response = record_export.export_records(_request(), req)

                        path = Path(response["outputPath"])
                        self.assertTrue(path.exists())
                        self.assertEqual(path.suffix, ".zip")
                        self.assertEqual(response["count"], 1)
                        self.assertEqual(response["dataSource"], "realtime")
                        with zipfile.ZipFile(path, "r") as zf:
                            message_path = next(name for name in zf.namelist() if name.endswith(f"/messages.{fmt}"))
                            content = zf.read(message_path).decode("utf-8")

                        if fmt == "json":
                            payload = json.loads(content)
                            self.assertEqual(payload["conversation"]["displayName"], "收藏")
                            self.assertEqual(len(payload["messages"]), 1)
                            self.assertEqual(payload["messages"][0]["content"], "<script>alert(1)</script>")
                        elif fmt == "html":
                            self.assertIn('class="wce-root', content)
                            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
                            self.assertNotIn("<script>alert(1)</script>", content)
                        else:
                            self.assertIn("<script>alert(1)</script>", content)

    def test_favorites_html_export_uses_chat_archive_adapter(self):
        source_items = [
            {
                "localId": 7,
                "serverId": 70,
                "sourceId": "700",
                "type": 2,
                "textBlocks": [],
                "attachments": [
                    {
                        "renderType": "image",
                        "typeLabel": "图片",
                        "fullMd5": "a" * 32,
                    }
                ],
                "conversationUsername": "wxid_friend",
                "senderUsername": "wxid_friend",
                "senderContact": {"displayName": "测试好友"},
                "updateTime": 1735689600,
                "updateTimeText": "2025-01-01 08:00:00",
            }
        ]
        source_meta = {"account": "wxid_test", "dataSource": "realtime"}

        with TemporaryDirectory() as td:
            archive_path = Path(td) / "favorites.zip"
            archive_path.write_bytes(b"PK")
            fake_job = SimpleNamespace(
                status="done",
                error="",
                zip_path=archive_path,
                progress=SimpleNamespace(messages_exported=1, media_copied=1, media_missing=0),
            )
            req = record_export.RecordExportRequest(
                account="wxid_test",
                dataset="favorites",
                format="html",
                types=["image"],
                output_dir=td,
                file_name="收藏备份",
            )
            with (
                patch.object(record_export, "_load_records", return_value=(source_items, source_meta)),
                patch.object(record_export, "export_prepared_chat_archive", return_value=fake_job) as archive_export,
            ):
                response = record_export.export_records(_request(), req)

        self.assertEqual(response["outputPath"], str(archive_path))
        self.assertEqual(response["mediaCopied"], 1)
        self.assertEqual(response["mediaMissing"], 0)
        kwargs = archive_export.call_args.kwargs
        self.assertEqual(kwargs["export_format"], "html")
        self.assertEqual(kwargs["title"], "收藏")
        self.assertEqual(kwargs["message_types"], ["image"])
        prepared = kwargs["conversations"][0]["messages"]
        self.assertEqual(prepared[0]["renderType"], "image")
        self.assertEqual(prepared[0]["imageMd5"], "a" * 32)
        self.assertEqual(prepared[0]["_mediaUsername"], "wxid_friend")

    def test_prepared_chat_archive_contains_selected_favorite_media(self):
        from wechat_decrypt_tool import chat_export_service

        image_md5 = "a" * 32
        file_md5 = "b" * 32
        emoji_md5 = "c" * 32
        video_md5 = "d" * 32
        video_thumb_md5 = "e" * 32
        voice_server_id = 9191
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
            b"\x1f\x15\xc4\x89"
        )
        media_files = {
            image_md5: ("png", png),
            file_md5: ("dat", b"favorite-file"),
            emoji_md5: ("gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00"),
            video_md5: ("mp4", b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom"),
            video_thumb_md5: ("jpg", b"\xff\xd8\xff\xd9"),
        }

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            output_dir = root / "exports"
            for md5, (extension, content) in media_files.items():
                resource_dir = account_dir / "resource" / md5[:2]
                resource_dir.mkdir(parents=True, exist_ok=True)
                (resource_dir / f"{md5}.{extension}").write_bytes(content)
            conn = sqlite3.connect(account_dir / "media_0.db")
            try:
                conn.execute("CREATE TABLE VoiceInfo (svr_id INTEGER, create_time INTEGER, voice_data BLOB)")
                conn.execute("INSERT INTO VoiceInfo VALUES (?, ?, ?)", (voice_server_id, 1735689602, b"SILK"))
                conn.commit()
            finally:
                conn.close()

            messages = [
                {
                    "id": "favorite-image",
                    "renderType": "image",
                    "isSent": False,
                    "content": "[图片]",
                    "imageMd5": image_md5,
                    "senderUsername": "wxid_friend",
                    "senderDisplayName": "测试好友",
                    "_mediaUsername": "wxid_friend",
                    "createTime": 1735689600,
                    "createTimeText": "2025-01-01 08:00:00",
                },
                {
                    "id": "favorite-emoji",
                    "renderType": "emoji",
                    "isSent": False,
                    "content": "[表情]",
                    "emojiMd5": emoji_md5,
                    "senderUsername": "wxid_friend",
                    "senderDisplayName": "测试好友",
                    "_mediaUsername": "wxid_friend",
                    "createTime": 1735689601,
                },
                {
                    "id": "favorite-video",
                    "renderType": "video",
                    "isSent": False,
                    "content": "[视频]",
                    "videoMd5": video_md5,
                    "videoThumbMd5": video_thumb_md5,
                    "senderUsername": "wxid_friend",
                    "senderDisplayName": "测试好友",
                    "_mediaUsername": "wxid_friend",
                    "createTime": 1735689602,
                },
                {
                    "id": "favorite-voice",
                    "renderType": "voice",
                    "isSent": False,
                    "content": "[语音]",
                    "serverId": voice_server_id,
                    "voiceLength": 2300,
                    "senderUsername": "wxid_friend",
                    "senderDisplayName": "测试好友",
                    "_mediaUsername": "wxid_friend",
                    "createTime": 1735689603,
                },
                {
                    "id": "favorite-file",
                    "renderType": "file",
                    "isSent": False,
                    "content": "资料.dat",
                    "title": "资料.dat",
                    "fileMd5": file_md5,
                    "fileSize": 13,
                    "senderUsername": "wxid_friend",
                    "senderDisplayName": "测试好友",
                    "_mediaUsername": "wxid_friend",
                    "createTime": 1735689604,
                    "createTimeText": "2025-01-01 08:00:04",
                },
            ]
            with patch.object(
                chat_export_service,
                "_convert_silk_to_browser_audio",
                return_value=(b"MP3", "mp3", "audio/mpeg"),
            ):
                job = chat_export_service.export_prepared_chat_archive(
                    account_dir=account_dir,
                    output_dir=output_dir,
                    file_name="favorites.zip",
                    title="收藏",
                    export_format="html",
                    conversations=[
                        {
                            "username": "__favorites__",
                            "displayName": "收藏",
                            "messages": messages,
                        }
                    ],
                    include_media=True,
                    media_kinds=["image", "emoji", "video", "video_thumb", "voice", "file"],
                    message_types=["image", "emoji", "video", "voice", "file"],
                )

            self.assertEqual(job.status, "done", msg=job.error)
            self.assertTrue(job.zip_path and job.zip_path.exists())
            with zipfile.ZipFile(job.zip_path, "r") as zf:
                names = set(zf.namelist())
                html_path = next(name for name in names if name.endswith("/messages.html"))
                html_text = zf.read(html_path).decode("utf-8")
                self.assertIn('class="wce-root', html_text)
                self.assertIn('data-render-type="image"', html_text)
                self.assertIn('data-render-type="emoji"', html_text)
                self.assertIn('data-render-type="video"', html_text)
                self.assertIn('data-render-type="voice"', html_text)
                self.assertIn('data-render-type="file"', html_text)
                self.assertTrue(any(name.startswith("media/images/") for name in names))
                self.assertTrue(any(name.startswith("media/emojis/") for name in names))
                self.assertTrue(any(name.startswith("media/videos/") for name in names))
                self.assertTrue(any(name.startswith("media/video_thumbs/") for name in names))
                self.assertTrue(any(name.startswith("media/voices/") for name in names))
                self.assertTrue(any(name.startswith("media/files/") for name in names))
            self.assertEqual(job.progress.media_copied, 6)

    def test_favorite_media_index_resolves_opaque_favorite_file_by_content_md5(self):
        from wechat_decrypt_tool.media_helpers import MediaPathIndex

        content = b"%PDF-1.7\nopaque favorite attachment\n"
        media_md5 = hashlib.md5(content).hexdigest()
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "output" / "databases" / "wxid_test"
            wxid_dir = root / "wxid_source"
            source = wxid_dir / "business" / "favorite" / "data" / "aa" / "opaque-resource-name"
            source.parent.mkdir(parents=True)
            source.write_bytes(content)
            account_dir.mkdir(parents=True)
            (account_dir / "_source.json").write_text(
                json.dumps({"wxid_dir": str(wxid_dir)}),
                encoding="utf-8",
            )

            index = MediaPathIndex.build(account_dir=account_dir, media_kinds=["file"])

            self.assertEqual(index.resolve(kind="file", md5=media_md5), source)

    def test_favorite_media_index_resolves_opaque_image_as_emoji(self):
        from wechat_decrypt_tool.media_helpers import MediaPathIndex

        image = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        media_md5 = hashlib.md5(image).hexdigest()
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "output" / "databases" / "wxid_test"
            wxid_dir = root / "wxid_source"
            source = wxid_dir / "business" / "favorite" / "thumb" / "bb" / "opaque-thumbnail"
            source.parent.mkdir(parents=True)
            source.write_bytes(image)
            account_dir.mkdir(parents=True)
            (account_dir / "_source.json").write_text(
                json.dumps({"wxid_dir": str(wxid_dir)}),
                encoding="utf-8",
            )

            index = MediaPathIndex.build(account_dir=account_dir, media_kinds=["emoji"])

            self.assertEqual(index.resolve(kind="emoji", md5=media_md5), source)

    def test_materialize_encrypted_favorite_file_writes_decrypted_payload(self):
        from wechat_decrypt_tool import chat_export_service

        media_md5 = "a" * 32
        decrypted = b"%PDF-1.7\nexported favorite attachment\n"
        with TemporaryDirectory() as td:
            root = Path(td)
            source = root / "opaque-favorite-resource"
            source.write_bytes(b"\x07\x08V2\x08\x07encrypted")
            zip_path = root / "favorite.zip"
            media_index = SimpleNamespace(
                is_known_missing=lambda **_kwargs: False,
                resolve=lambda **_kwargs: source,
            )

            with (
                zipfile.ZipFile(zip_path, "w") as zf,
                patch.object(
                    chat_export_service,
                    "_read_and_maybe_decrypt_media",
                    return_value=(decrypted, "application/octet-stream"),
                ),
            ):
                arc, is_new = chat_export_service._materialize_media(
                    zf=zf,
                    account_dir=root,
                    conv_username="__favorites__",
                    kind="file",
                    md5=media_md5,
                    file_id="",
                    media_written={},
                    suggested_name="资料.pdf",
                    media_index=media_index,
                )

            self.assertTrue(is_new)
            self.assertTrue(arc.endswith(".pdf"))
            with zipfile.ZipFile(zip_path, "r") as zf:
                self.assertEqual(zf.read(arc), decrypted)

    def test_prepared_favorite_location_uses_chat_location_card(self):
        from wechat_decrypt_tool import chat_export_service

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            job = chat_export_service.export_prepared_chat_archive(
                account_dir=account_dir,
                output_dir=root / "exports",
                file_name="favorites-location.zip",
                title="收藏",
                export_format="html",
                conversations=[
                    {
                        "username": "__favorites__",
                        "displayName": "收藏",
                        "messages": [
                            {
                                "id": "favorite-location",
                                "renderType": "location",
                                "content": "人民广场",
                                "locationPoiname": "人民广场",
                                "locationLabel": "上海市黄浦区人民大道",
                                "locationLat": "31.2304",
                                "locationLng": "121.4737",
                                "senderUsername": "wxid_friend",
                                "senderDisplayName": "测试好友",
                                "createTime": 1735689600,
                            }
                        ],
                    }
                ],
                include_media=True,
                media_kinds=[],
                message_types=["location"],
            )

            self.assertEqual(job.status, "done", msg=job.error)
            with zipfile.ZipFile(job.zip_path, "r") as zf:
                html_path = next(name for name in zf.namelist() if name.endswith("/messages.html"))
                html_text = zf.read(html_path).decode("utf-8")
            self.assertIn('<option value="location">位置</option>', html_text)
            self.assertIn('class="wechat-location-card', html_text)
            self.assertIn("人民广场", html_text)
            self.assertIn("uri.amap.com/marker", html_text)

    def test_materialize_voice_falls_back_to_realtime_media_database(self):
        from wechat_decrypt_tool import chat_export_service

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            realtime_storage = root / "live" / "db_storage"
            realtime_media_dir = realtime_storage / "message"
            realtime_media_dir.mkdir(parents=True)
            realtime_db = realtime_media_dir / "media_0.db"
            realtime_db.touch()
            realtime = SimpleNamespace(
                handle=7,
                db_storage_dir=realtime_storage,
                lock=threading.Lock(),
            )
            zip_path = root / "voice.zip"

            with (
                zipfile.ZipFile(zip_path, "w") as zf,
                patch.object(chat_export_service.WCDB_REALTIME, "ensure_connected", return_value=realtime),
                patch.object(
                    chat_export_service,
                    "_wcdb_exec_query",
                    return_value=[{"voice_data": "53494c4b5f564f494345"}],
                ) as realtime_query,
                patch.object(
                    chat_export_service,
                    "_convert_silk_to_browser_audio",
                    return_value=(b"MP3_VOICE", "mp3", "audio/mpeg"),
                ),
            ):
                arc, is_new = chat_export_service._materialize_voice(
                    zf=zf,
                    account_dir=account_dir,
                    media_db_path=account_dir / "media_0.db",
                    server_id=123456,
                    media_written={},
                )

            self.assertTrue(is_new)
            self.assertEqual(arc, "media/voices/voice_123456.mp3")
            with zipfile.ZipFile(zip_path, "r") as zf:
                self.assertEqual(zf.read(arc), b"MP3_VOICE")
            self.assertEqual(realtime_query.call_args.kwargs["path"], str(realtime_db))
            self.assertIn("svr_id = 123456", realtime_query.call_args.kwargs["sql"])


if __name__ == "__main__":
    unittest.main()
