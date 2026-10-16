import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestMessageLinksFrontend(unittest.TestCase):
    def test_plain_message_urls_are_clickable_external_links(self):
        content = (ROOT / "frontend" / "components" / "chat" / "MessageContent.vue").read_text(encoding="utf-8")
        helper = (ROOT / "frontend" / "lib" / "chat" / "message-links.js").read_text(encoding="utf-8")

        self.assertIn("linkifyMessageSegments", content)
        self.assertIn("seg.type === 'link'", content)
        self.assertIn('@click.prevent.stop="openMessageUrl(seg.url)"', content)
        self.assertIn("window.wechatDesktop?.openExternalUrl", helper)
        self.assertIn("window.open(url, '_blank'", helper)
        self.assertIn("parsed.protocol === 'http:' || parsed.protocol === 'https:'", helper)

    def test_chat_history_plain_text_uses_the_same_linkification(self):
        shared = (ROOT / "frontend" / "components" / "chat" / "ChatHistoryFloatingWindows.vue").read_text(encoding="utf-8")
        self.assertIn("linkifyMessageSegments", shared)
        self.assertIn("chat-history-text-link", shared)
        self.assertIn('@click.prevent.stop="openRecordUrl(segment.url)"', shared)


if __name__ == "__main__":
    unittest.main()
