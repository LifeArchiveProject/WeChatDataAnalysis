import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestVoipIconsFrontend(unittest.TestCase):
    def test_chat_uses_svg_call_icons_and_only_mirrors_sent_video(self):
        content = (ROOT / "frontend" / "components" / "chat" / "MessageContent.vue").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "assets" / "css" / "chat.css").read_text(encoding="utf-8")
        asset_dir = ROOT / "frontend" / "public" / "assets" / "images" / "wechat"

        self.assertTrue((asset_dir / "wechat-audio-call.svg").is_file())
        self.assertTrue((asset_dir / "wechat-video-call.svg").is_file())
        self.assertIn("/assets/images/wechat/wechat-audio-call.svg", content)
        self.assertIn("/assets/images/wechat/wechat-video-call.svg", content)
        self.assertIn("message.voipType === 'video' && message.isSent", content)
        self.assertIn("'wechat-voip-icon--video': message.voipType === 'video'", content)
        self.assertIn(".wechat-voip-icon--video", css)
        self.assertIn("transform: scale(1.5)", css)
        self.assertIn(".wechat-voip-icon--mirrored", css)
        self.assertIn("transform: scaleX(-1)", css)
        self.assertNotIn("wechat-audio-light.png", content)
        self.assertNotIn("wechat-video-light.png", content)


if __name__ == "__main__":
    unittest.main()
