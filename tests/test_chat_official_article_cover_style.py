import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _parse_app_message


class TestChatOfficialArticleCoverStyle(unittest.TestCase):
    def test_mp_weixin_feed_url_is_cover_style(self):
        raw_text = (
            "<msg>"
            "<appmsg>"
            "<title>时尚穿搭：「这样的jk你喜欢吗」</title>"
            "<des>这样的jk你喜欢吗？</des>"
            "<type>5</type>"
            "<url>"
            "http://mp.weixin.qq.com/s?__biz=MzkxOTY4MjIxOA==&amp;mid=2247508015&amp;idx=1&amp;sn=931dce677c6e70b4365792b14e7e8ff0"
            "&amp;exptype=masonry_feed_brief_content_elite_for_pcfeeds_u2i&amp;ranksessionid=1770868256_1&amp;req_id=1770867949535989#rd"
            "</url>"
            "<thumburl>https://mmbiz.qpic.cn/sz_mmbiz_jpg/foo/640?wx_fmt=jpeg&amp;wxfrom=401</thumburl>"
            "<sourcedisplayname>甜图社</sourcedisplayname>"
            "<sourceusername>gh_abc123</sourceusername>"
            "</appmsg>"
            "</msg>"
        )

        parsed = _parse_app_message(raw_text)
        self.assertEqual(parsed.get("renderType"), "link")
        self.assertEqual(parsed.get("linkType"), "official_article")
        self.assertEqual(parsed.get("linkStyle"), "cover")

    def test_mp_weixin_non_feed_url_keeps_default_style(self):
        raw_text = (
            "<msg>"
            "<appmsg>"
            "<title>普通分享</title>"
            "<des>这样的jk你喜欢吗？</des>"
            "<type>5</type>"
            "<url>http://mp.weixin.qq.com/s?__biz=foo&amp;mid=1&amp;idx=1&amp;sn=bar#rd</url>"
            "<sourcedisplayname>甜图社</sourcedisplayname>"
            "<sourceusername>gh_abc123</sourceusername>"
            "</appmsg>"
            "</msg>"
        )

        parsed = _parse_app_message(raw_text)
        self.assertEqual(parsed.get("renderType"), "link")
        self.assertEqual(parsed.get("linkType"), "official_article")
        self.assertEqual(parsed.get("linkStyle"), "default")


if __name__ == "__main__":
    unittest.main()

