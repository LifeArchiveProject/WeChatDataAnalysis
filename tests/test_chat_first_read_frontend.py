import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestChatFirstReadFrontend(unittest.TestCase):
    def test_chat_header_exposes_first_message_reading_command(self):
        source = (ROOT / "frontend" / "components" / "chat" / "ConversationPane.vue").read_text(encoding="utf-8")
        self.assertIn("从第一条消息开始阅读", source)
        self.assertIn('@click="jumpToConversationFirst"', source)
        self.assertIn(":disabled=\"isLoadingMessages || isJumpingToFirst\"", source)
        first_button = source.split('@click="jumpToConversationFirst"', 1)[0].rsplit("<button", 1)[1]
        self.assertIn('class="header-btn-icon"', first_button)
        self.assertIn('aria-label="从第一条消息开始阅读"', first_button)
        self.assertNotIn("chat-first-read-btn", source)
        self.assertNotIn("正在定位", source)

    def test_first_message_mode_loads_forward_at_the_bottom(self):
        source = (ROOT / "frontend" / "composables" / "chat" / "useChatSearch.js").read_text(encoding="utf-8")
        jump_block = source.split("const jumpToConversationFirst = async () => {", 1)[1].split(
            "const onTimeSidebarDayClick", 1
        )[0]
        scroll_block = source.split("const onMessageScrollInContextMode = async () => {", 1)[1].split(
            "const onMessageScroll = async () => {", 1
        )[0]

        self.assertIn("kind: 'first'", jump_block)
        self.assertIn("locateByAnchorId", jump_block)
        self.assertIn("isJumpingToFirst.value = true", jump_block)
        self.assertIn("isJumpingToFirst.value = false", jump_block)
        self.assertIn("searchContext.value.hasMoreAfter", source)
        self.assertIn("container.scrollTop = 0", source)
        self.assertIn("distBottom <= 80", scroll_block)
        self.assertIn("loadMoreSearchContextAfter()", scroll_block)


if __name__ == "__main__":
    unittest.main()
