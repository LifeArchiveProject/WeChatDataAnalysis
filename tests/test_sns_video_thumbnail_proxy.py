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
        source = (ROOT / "frontend" / "lib" / "sns-media-source.js").read_text(encoding="utf-8")
        page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
        media_url_block = page.split("const getSnsMediaUrl =", 1)[1].split(
            "const getMediaThumbSrc =", 1
        )[0]

        self.assertIn("const isVideo = Number(value.type || 0) === 6", source)
        self.assertRegex(source, re.compile(r"key: isVideo[\s\S]{0,120}value\.videoKey"))
        self.assertIn("const key = String(selectedSource.key || '').trim()", media_url_block)
        self.assertIn("parts.set('v', '15')", media_url_block)

    def test_video_without_thumbnail_uses_placeholder_instead_of_image_route(self):
        page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
        source = (ROOT / "frontend" / "lib" / "sns-media-source.js").read_text(encoding="utf-8")

        self.assertIn("if (isVideo && !thumbnail.url)", source)
        self.assertIn("kind: 'placeholder'", source)
        self.assertIn("const selectedSource = selectSnsImageSource", page)


if __name__ == "__main__":
    unittest.main()
