import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestContactProfileVerificationFrontend(unittest.TestCase):
    def test_friend_verifications_require_explicit_action_and_are_cached(self):
        source = (ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js").read_text(encoding="utf-8")
        card = (ROOT / "frontend" / "components" / "chat" / "ContactProfileCard.vue").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")

        self.assertIn("api.listFriendVerifications", source)
        self.assertIn("source: 'realtime'", source)
        self.assertIn("String(item?.userName || '').trim() === username", source)
        self.assertIn("const contactVerificationCache = new Map()", source)
        self.assertIn("const contactVerificationInflight = new Map()", source)
        self.assertIn("CONTACT_VERIFICATION_CACHE_TTL_MS", source)
        self.assertIn("const loadContactFriendVerifications = async () =>", source)
        self.assertIn("contactProfileIsFriend", source)
        self.assertIn("contactProfileFriendVerifications", source)
        fetch_profile = source.split("const fetchContactProfile", 1)[1].split(
            "const clearContactProfileHoverIntentTimer", 1
        )[0]
        self.assertNotIn("loadContactFriendVerifications(", fetch_profile)

        self.assertIn('@click.stop="loadContactFriendVerifications"', card)
        self.assertIn("查看好友验证", card)
        self.assertIn("contactProfileVerificationLoaded", card)
        self.assertIn(
            "buildGeneralUrl('friend-verifications', params),", api
        )
        self.assertIn("params?.signal ? { signal: params.signal } : {}", api)

    def test_profile_hover_has_intent_cache_deduplication_and_abort(self):
        source = (ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")

        self.assertIn("const CONTACT_PROFILE_HOVER_INTENT_MS = 250", source)
        self.assertIn("const contactProfileCache = new Map()", source)
        self.assertIn("const contactProfileInflight = new Map()", source)
        self.assertIn("makeContactProfileCacheKey(account, username)", source)
        self.assertIn("const pending = contactProfileInflight.get(key)", source)
        self.assertIn("return pending.promise", source)
        self.assertIn("clearContactProfileHoverIntentTimer()", source)
        self.assertIn("}, CONTACT_PROFILE_HOVER_INTENT_MS)", source)
        self.assertIn("abortActiveContactProfileRequest()", source)
        self.assertIn("abortActiveContactVerificationRequest()", source)
        timeout = source.split("const withContactProfileTimeout", 1)[1].split(
            "const abortInflightRequest", 1
        )[0]
        self.assertIn("controller.abort()", timeout)
        self.assertIn("params.signal = controller.signal", source)
        self.assertIn(
            "return await request(url, params?.signal ? { signal: params.signal } : {})",
            api,
        )

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
