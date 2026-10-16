import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestChatRealtimeScopeFrontend(unittest.TestCase):
    def test_chat_page_requests_chat_only_realtime_scope(self):
        source = (ROOT / "frontend" / "pages" / "chat" / "[[username]].vue").read_text(encoding="utf-8")

        self.assertIn("scope: 'chat'", source)

        payments = (ROOT / "frontend" / "pages" / "payments.vue").read_text(encoding="utf-8")
        biz_messages = (ROOT / "frontend" / "components" / "BizMessages.vue").read_text(encoding="utf-8")
        self.assertIn("scope: 'all'", payments)
        self.assertIn("scope: 'all'", biz_messages)

    def test_realtime_store_pauses_stream_while_page_is_hidden(self):
        source = (ROOT / "frontend" / "stores" / "chatRealtime.js").read_text(encoding="utf-8")

        self.assertIn("const streamScope = ref('all')", source)
        self.assertIn("scope=${encodeURIComponent(streamScope.value)}", source)
        self.assertIn("document.visibilityState === 'hidden'", source)
        self.assertIn("document.addEventListener('visibilitychange'", source)


if __name__ == "__main__":
    unittest.main()
