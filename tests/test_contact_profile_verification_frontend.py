import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestContactProfileVerificationFrontend(unittest.TestCase):
    def test_friend_profile_loads_realtime_verification_records(self):
        source = (ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js").read_text(encoding="utf-8")
        self.assertIn("api.listFriendVerifications", source)
        self.assertIn("source: 'realtime'", source)
        self.assertIn("String(item?.userName || '').trim() === username", source)
        self.assertIn("contactProfileIsFriend", source)
        self.assertIn("contactProfileFriendVerifications", source)

    def test_profile_card_renders_direction_content_and_external_links(self):
        source = (ROOT / "frontend" / "components" / "chat" / "ContactProfileCard.vue").read_text(encoding="utf-8")
        self.assertIn("好友验证", source)
        self.assertIn("我方发起", source)
        self.assertIn("对方发起", source)
        self.assertIn("verificationContentSegments", source)
        self.assertIn("contact-verification-link", source)
        self.assertIn("window.wechatDesktop?.openExternalUrl", source)
        self.assertIn("window.open(url, '_blank'", source)


if __name__ == "__main__":
    unittest.main()
