import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatListMessagesReScope(unittest.TestCase):
    def test_list_chat_messages_does_not_shadow_re(self):
        from starlette.requests import Request

        import wechat_decrypt_tool.routers.chat as chat

        class _Sentinel(Exception):
            pass

        def fake_collect_chat_messages(**_kwargs):
            merged = [
                {
                    "id": "1",
                    "sortSeq": 0,
                    "createTime": 1,
                    "localId": 1,
                    "type": 266287972401,
                    "_rawText": "<msg><template>${wxid_abc}</template></msg>",
                    "renderType": "appmsg",
                }
            ]
            return merged, False, [], [], set()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/chat/messages",
            "raw_path": b"/api/chat/messages",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
        request = Request(scope)

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            sentinel = _Sentinel("stop-after-template-parse")

            with patch.object(chat, "_resolve_account_dir", return_value=account_dir), patch.object(
                chat, "_iter_message_db_paths", return_value=[account_dir / "msg_0.db"]
            ), patch.object(chat, "_collect_chat_messages", side_effect=fake_collect_chat_messages), patch.object(
                chat, "_postprocess_transfer_messages", lambda _merged: None
            ), patch.object(chat, "_extract_xml_tag_text", return_value="${wxid_abc}"), patch.object(
                chat, "_load_contact_rows", side_effect=sentinel
            ):
                with self.assertRaises(_Sentinel):
                    chat.list_chat_messages(request=request, username="44372432598@chatroom", account="acc")


if __name__ == "__main__":
    unittest.main()

