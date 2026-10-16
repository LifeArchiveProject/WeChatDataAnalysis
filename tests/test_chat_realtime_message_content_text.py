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


class TestChatRealtimeMessageContentText(unittest.TestCase):
    def test_realtime_api_preserves_plain_numeric_message_content(self):
        wcdb_rows = [
            {
                "localId": 1367,
                "serverId": 123,
                "localType": 1,
                "sortSeq": 1700000000000,
                "realSenderId": 1,
                "createTime": 1700000000,
                "messageContent": "123123",
                "compressContent": None,
                "packedInfoData": None,
                "senderUsername": "wxid_sender",
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
                patch.object(
                    chat_router,
                    "_fetch_realtime_message_rows_via_cursor",
                    side_effect=RuntimeError("cursor unavailable in regression test"),
                ),
                patch.object(chat_router, "_wcdb_get_messages", return_value=wcdb_rows),
                patch.object(chat_router, "_load_contact_rows", return_value={}),
                patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
                patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
                patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
                patch.object(chat_router, "_load_group_nickname_map", return_value={}),
            ):
                response = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username="wxid_contact",
                    account="acc",
                    limit=50,
                    offset=0,
                    order="asc",
                    render_types=None,
                    source="realtime",
                )

        messages = response.get("messages") or []
        self.assertEqual(len(messages), 1)
        self.assertTrue(str(messages[0].get("id") or "").endswith(":1367"))
        self.assertEqual(messages[0].get("content"), "123123")

    def test_realtime_normalization_only_decodes_explicit_hex_for_message_content(self):
        normalized = chat_router._normalize_realtime_message_item(
            {
                "message_content": "123123",
                "compress_content": "123123",
                "packed_info_data": "313233",
            }
        )
        explicit_hex = chat_router._normalize_realtime_message_item(
            {"message_content": "0x313233"}
        )

        self.assertEqual(normalized["message_content"], "123123")
        self.assertEqual(normalized["compress_content"], b"\x12\x31\x23")
        self.assertEqual(normalized["packed_info_data"], b"123")
        self.assertEqual(explicit_hex["message_content"], b"123")


if __name__ == "__main__":
    unittest.main()
