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


class TestChatRealtimeSystemMessageDisplayName(unittest.TestCase):
    def test_realtime_chatroom_top_message_prefers_remark_name(self):
        raw_text = (
            "17990148862@chatroom 2 3546361838777087323 0 "
            "wxid_k7zhjk9xvzsk22 21 A 69"
        )
        wcdb_rows = [
            {
                "localId": 1,
                "serverId": 123,
                "localType": 10000,
                "sortSeq": 1700000000000,
                "realSenderId": 0,
                "createTime": 1700000000,
                "messageContent": raw_text,
                "compressContent": None,
                "packedInfoData": None,
                "senderUsername": "",
                "isSent": False,
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
                patch.object(
                    chat_router,
                    "_load_contact_rows",
                    return_value={
                        "wxid_k7zhjk9xvzsk22": {
                            "remark": "周鑫",
                            "nick_name": "A",
                            "alias": "",
                        }
                    },
                ),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                resp = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username="17990148862@chatroom",
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
        self.assertEqual(msg.get("renderType"), "system")
        self.assertEqual(msg.get("content"), "周鑫移除了一条置顶消息")
        self.assertNotIn("_rawText", msg)


if __name__ == "__main__":
    unittest.main()
