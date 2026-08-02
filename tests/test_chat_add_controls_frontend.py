import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestChatAddControlsFrontend(unittest.TestCase):
    def test_chat_header_has_no_add_message_controls(self):
        source = (ROOT / "frontend" / "components" / "chat" / "ConversationPane.vue").read_text(
            encoding="utf-8"
        )

        for symbol in (
            "添加文字记录",
            "添加图片记录",
            "添加文件记录",
            "openAddTextMessageModal",
            "openAddImageMessageModal",
            "openAddFileMessageModal",
        ):
            self.assertNotIn(symbol, source)

    def test_add_message_modals_and_wiring_are_removed(self):
        overlays = (ROOT / "frontend" / "components" / "chat" / "ChatOverlays.vue").read_text(
            encoding="utf-8"
        )
        editing = (ROOT / "frontend" / "composables" / "chat" / "useChatEditing.js").read_text(
            encoding="utf-8"
        )
        page = (ROOT / "frontend" / "pages" / "chat" / "[[username]].vue").read_text(
            encoding="utf-8"
        )

        for symbol in (
            "addTextMessageModal",
            "imageMessageModal",
            "fileMessageModal",
            "openAddTextMessageModal",
            "saveAddTextMessageModal",
            "openAddImageMessageModal",
            "saveImageMessageModal",
            "openAddFileMessageModal",
            "saveFileMessageModal",
            "addChatTextMessage",
            "addChatImageMessage",
            "addChatFileMessage",
        ):
            self.assertNotIn(symbol, overlays)
            self.assertNotIn(symbol, editing)
            self.assertNotIn(symbol, page)


if __name__ == "__main__":
    unittest.main()
