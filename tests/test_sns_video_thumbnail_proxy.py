import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestSnsVideoThumbnailProxy(unittest.TestCase):
    def test_video_qq_thumbnail_uses_backend_media_proxy(self):
        page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
        media_url_block = page.split("const getSnsMediaUrl =", 1)[1].split(
            "const getMediaThumbSrc =", 1
        )[0]

        self.assertIn("host.endsWith('.video.qq.com')", media_url_block)
        self.assertIn("host.endsWith('.video.qq.com') && isThumbRequest", media_url_block)
        self.assertIn("return `${apiBase}/sns/media?${parts.toString()}`", media_url_block)

    def test_video_thumbnail_prefers_video_decryption_key(self):
        page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
        media_url_block = page.split("const getSnsMediaUrl =", 1)[1].split(
            "const getMediaThumbSrc =", 1
        )[0]

        self.assertRegex(
            media_url_block,
            re.compile(
                r"const videoKey = Number\(m\?\.type \|\| 0\) === 6"
                r"[\s\S]{0,160}String\(m\?\.videoKey \|\| ''\)\.trim\(\)"
            ),
        )
        self.assertRegex(
            media_url_block,
            re.compile(r"isThumbRequest[\s\S]{0,100}\? \(videoKey \|\| m\?\.thumbKey"),
        )
        self.assertIn("parts.set('v', '14')", media_url_block)


if __name__ == "__main__":
    unittest.main()
