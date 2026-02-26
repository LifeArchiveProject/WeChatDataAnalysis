import sys
import unittest
from pathlib import Path

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedBentoSummaryTopEmoji(unittest.TestCase):
    def _build_sources(self, *, emoji_data):
        # Keep sources minimal: card_07_bento_summary only needs a handful of keys.
        overview = {"data": {"totalMessages": 100, "addedFriends": 0}}
        heatmap = {"data": {"totalMessages": 100, "weekdayLabels": [], "hourLabels": [], "matrix": []}}
        message_chars = {"data": {"sentChars": 0}}
        reply_speed = {"data": {}}
        monthly = {"data": {"months": []}}
        emoji = {"data": emoji_data}
        return overview, heatmap, message_chars, reply_speed, monthly, emoji

    def test_top_emoji_prefers_wechat_when_count_higher(self):
        from wechat_decrypt_tool.wrapped.cards.card_07_bento_summary import build_card_07_bento_summary_from_sources

        overview, heatmap, message_chars, reply_speed, monthly, emoji = self._build_sources(
            emoji_data={
                "topWechatEmojis": [{"key": "[微笑]", "count": 5, "assetPath": "/wxemoji/Expression_1@2x.png"}],
                "topTextEmojis": [],
                "topUnicodeEmojis": [{"emoji": "🙂", "count": 2}],
            }
        )
        card = build_card_07_bento_summary_from_sources(
            year=2025,
            overview=overview,
            heatmap=heatmap,
            message_chars=message_chars,
            reply_speed=reply_speed,
            monthly=monthly,
            emoji=emoji,
        )
        snap = card["data"]["snapshot"]
        self.assertEqual(snap["topEmoji"]["kind"], "wechat")
        self.assertEqual(snap["topEmoji"]["key"], "[微笑]")
        self.assertEqual(snap["topEmoji"]["count"], 5)
        self.assertTrue(str(snap["topEmoji"]["assetPath"]).startswith("/wxemoji/"))

    def test_top_emoji_prefers_unicode_when_count_higher(self):
        from wechat_decrypt_tool.wrapped.cards.card_07_bento_summary import build_card_07_bento_summary_from_sources

        overview, heatmap, message_chars, reply_speed, monthly, emoji = self._build_sources(
            emoji_data={
                "topWechatEmojis": [{"key": "[微笑]", "count": 5, "assetPath": "/wxemoji/Expression_1@2x.png"}],
                "topTextEmojis": [],
                "topUnicodeEmojis": [{"emoji": "🙂", "count": 9}],
            }
        )
        card = build_card_07_bento_summary_from_sources(
            year=2025,
            overview=overview,
            heatmap=heatmap,
            message_chars=message_chars,
            reply_speed=reply_speed,
            monthly=monthly,
            emoji=emoji,
        )
        snap = card["data"]["snapshot"]
        self.assertEqual(snap["topEmoji"]["kind"], "unicode")
        self.assertEqual(snap["topEmoji"]["emoji"], "🙂")
        self.assertEqual(snap["topEmoji"]["count"], 9)

    def test_top_emoji_includes_top_text_emojis(self):
        from wechat_decrypt_tool.wrapped.cards.card_07_bento_summary import build_card_07_bento_summary_from_sources

        overview, heatmap, message_chars, reply_speed, monthly, emoji = self._build_sources(
            emoji_data={
                "topWechatEmojis": [{"key": "[表情1]", "count": 2, "assetPath": "/wxemoji/Expression_1@2x.png"}],
                "topTextEmojis": [{"key": "[嘿哈]", "count": 4, "assetPath": "/wxemoji/Expression_99@2x.png"}],
                "topUnicodeEmojis": [{"emoji": "🙂", "count": 3}],
            }
        )
        card = build_card_07_bento_summary_from_sources(
            year=2025,
            overview=overview,
            heatmap=heatmap,
            message_chars=message_chars,
            reply_speed=reply_speed,
            monthly=monthly,
            emoji=emoji,
        )
        snap = card["data"]["snapshot"]
        self.assertEqual(snap["topEmoji"]["kind"], "wechat")
        self.assertEqual(snap["topEmoji"]["key"], "[嘿哈]")
        self.assertEqual(snap["topEmoji"]["count"], 4)
        self.assertTrue(str(snap["topEmoji"]["assetPath"]).endswith("Expression_99@2x.png"))

    def test_top_emoji_none_when_no_emoji_stats(self):
        from wechat_decrypt_tool.wrapped.cards.card_07_bento_summary import build_card_07_bento_summary_from_sources

        overview, heatmap, message_chars, reply_speed, monthly, emoji = self._build_sources(
            emoji_data={"topWechatEmojis": [], "topTextEmojis": [], "topUnicodeEmojis": []}
        )
        card = build_card_07_bento_summary_from_sources(
            year=2025,
            overview=overview,
            heatmap=heatmap,
            message_chars=message_chars,
            reply_speed=reply_speed,
            monthly=monthly,
            emoji=emoji,
        )
        snap = card["data"]["snapshot"]
        self.assertIsNone(snap.get("topEmoji"))


if __name__ == "__main__":
    unittest.main()

