import importlib
import sys
import threading
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatExportCancelResponsiveness(unittest.TestCase):
    def _reload_export_module(self):
        import wechat_decrypt_tool.chat_export_service as chat_export_service

        importlib.reload(chat_export_service)
        return chat_export_service

    def test_json_writer_checks_cancel_between_messages(self):
        svc = self._reload_export_module()
        job = svc.ExportJob(export_id="exp_cancel", account="wxid_test", status="running")
        rows = [
            svc._Row(
                db_stem="message_0",
                table_name="msg_demo",
                local_id=1,
                server_id=1001,
                local_type=1,
                sort_seq=1,
                create_time=1735689601,
                raw_text="第一条",
                sender_username="wxid_friend",
                is_sent=False,
            ),
            svc._Row(
                db_stem="message_0",
                table_name="msg_demo",
                local_id=2,
                server_id=1002,
                local_type=1,
                sort_seq=2,
                create_time=1735689602,
                raw_text="第二条",
                sender_username="wxid_friend",
                is_sent=False,
            ),
        ]

        original_iter = svc._iter_rows_for_conversation
        original_parse = svc._parse_message_for_export
        try:
            def fake_iter_rows_for_conversation(**_kwargs):
                yield rows[0]
                job.cancel_requested = True
                yield rows[1]

            def fake_parse_message_for_export(**kwargs):
                row = kwargs["row"]
                return {
                    "id": f"{row.db_stem}:{row.table_name}:{row.local_id}",
                    "localId": row.local_id,
                    "serverId": row.server_id,
                    "createTime": row.create_time,
                    "createTimeText": "2025-01-01 08:00:00",
                    "sortSeq": row.sort_seq,
                    "type": row.local_type,
                    "renderType": "text",
                    "isSent": bool(row.is_sent),
                    "senderUsername": row.sender_username,
                    "conversationUsername": kwargs["conv_username"],
                    "isGroup": False,
                    "content": row.raw_text,
                    "title": "",
                    "url": "",
                    "from": "",
                    "fromUsername": "",
                    "linkType": "",
                    "linkStyle": "",
                    "objectId": "",
                    "objectNonceId": "",
                    "recordItem": "",
                    "thumbUrl": "",
                    "imageMd5": "",
                    "imageFileId": "",
                    "imageMd5Candidates": [],
                    "imageFileIdCandidates": [],
                    "imageUrl": "",
                    "emojiMd5": "",
                    "emojiUrl": "",
                    "videoMd5": "",
                    "videoThumbMd5": "",
                    "videoFileId": "",
                    "videoThumbFileId": "",
                    "videoUrl": "",
                    "videoThumbUrl": "",
                    "voiceLength": "",
                    "quoteUsername": "",
                    "quoteServerId": "",
                    "quoteType": "",
                    "quoteThumbUrl": "",
                    "quoteVoiceLength": "",
                    "quoteTitle": "",
                    "quoteContent": "",
                    "amount": "",
                    "coverUrl": "",
                    "fileSize": "",
                    "fileMd5": "",
                    "paySubType": "",
                    "transferStatus": "",
                    "transferId": "",
                    "voipType": "",
                    "locationLat": None,
                    "locationLng": None,
                    "locationPoiname": "",
                    "locationLabel": "",
                }

            svc._iter_rows_for_conversation = fake_iter_rows_for_conversation
            svc._parse_message_for_export = fake_parse_message_for_export

            with TemporaryDirectory() as td:
                zip_path = Path(td) / "out.zip"
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    with self.assertRaises(svc._JobCancelled):
                        svc._write_conversation_json(
                            zf=zf,
                            conv_dir="conversations/demo",
                            account_dir=Path(td),
                            conv_username="wxid_friend",
                            conv_name="测试好友",
                            conv_avatar_path="",
                            conv_is_group=False,
                            start_time=None,
                            end_time=None,
                            want_types=None,
                            local_types=None,
                            resource_conn=None,
                            resource_chat_id=None,
                            head_image_conn=None,
                            resolve_display_name=lambda username: username,
                            privacy_mode=False,
                            include_media=False,
                            media_kinds=[],
                            media_written={},
                            avatar_written={},
                            report={"errors": [], "missingMedia": []},
                            allow_process_key_extract=False,
                            media_db_path=Path(td) / "media_0.db",
                            media_index=None,
                            job=job,
                            lock=threading.Lock(),
                        )
            self.assertEqual(job.progress.messages_exported, 1)
            self.assertTrue(job.cancel_requested)
        finally:
            svc._iter_rows_for_conversation = original_iter
            svc._parse_message_for_export = original_parse


if __name__ == "__main__":
    unittest.main()
