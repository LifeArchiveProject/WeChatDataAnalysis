import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import chat as chat_router


class _DummyRequest:
    base_url = "http://testserver/"


class _DummyConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


class TestChatRealtimeVideoThumbMd5FromPackedInfo(unittest.TestCase):
    def test_video_thumb_md5_filled_from_packed_info(self):
        packed_md5 = "faff984641f9dd174e01c74f0796c9ae"
        file_id = "3057020100044b3049020100020445eb9d5102032f54690204749999db0204698c336b0424deadbeef"
        video_md5 = "22e6612411898b6d43b7e773e504d506"
        xml = (
            '<?xml version="1.0"?>\n'
            "<msg>\n"
            f'  <videomsg fromusername="wxid_sender" md5="{video_md5}" cdnthumburl="{file_id}" cdnvideourl="{file_id}" />\n'
            "</msg>\n"
        )

        wcdb_rows = [
            {
                "localId": 1,
                "serverId": 123,
                "localType": 43,
                "sortSeq": 1700000000000,
                "realSenderId": 1,
                "createTime": 1700000000,
                "messageContent": xml,
                "compressContent": None,
                "packedInfoData": packed_md5.encode("ascii"),
                "senderUsername": "wxid_sender",
            }
        ]

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            conn = _DummyConn()

            with (
                patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(chat_router, "_wcdb_get_messages", return_value=wcdb_rows),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                resp = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username="demo@chatroom",
                    account="acc",
                    limit=50,
                    offset=0,
                    order="asc",
                    render_types=None,
                    source="realtime",
                )

        self.assertEqual(resp.get("status"), "success")
        messages = resp.get("messages") or []
        self.assertEqual(len(messages), 1)
        msg = messages[0]
        self.assertEqual(msg.get("renderType"), "video")
        self.assertEqual(msg.get("videoThumbMd5"), packed_md5)
        thumb_url = str(msg.get("videoThumbUrl") or "")
        self.assertIn(f"md5={packed_md5}", thumb_url)
        self.assertNotIn("file_id=", thumb_url)


if __name__ == "__main__":
    unittest.main()

