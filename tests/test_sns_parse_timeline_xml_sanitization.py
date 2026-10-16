import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers.sns import _parse_timeline_xml  # noqa: E402  pylint: disable=wrong-import-position


class TestSnsParseTimelineXmlSanitization(unittest.TestCase):
    def test_external_share_type5_parses_with_raw_ampersands(self):
        xml = (
            "<SnsDataItem><TimelineObject>"
            "<username>wxid_2az0agby0baa22</username>"
            "<createTime>1771500773</createTime>"
            "<contentDesc>让我看看它和suno有什么区别</contentDesc>"
            "<ContentObject>"
            "<type>5</type>"
            "<title>Google Gemini 上线了AI音乐生成功能</title>"
            "<contentUrl>https://b23.tv/lVa1lpm?share_medium=android&share_source=weixin_moments</contentUrl>"
            "</ContentObject>"
            "<appInfo><appName>哔哩哔哩</appName></appInfo>"
            "<mediaList><media>"
            "<type>4</type><id>m1</id>"
            "<url>https://b23.tv/lVa1lpm?share_medium=android&share_source=weixin_moments</url>"
            "<thumb>http://shmmsns.qpic.cn/mmsns/test/150</thumb>"
            "</media></mediaList>"
            "</TimelineObject></SnsDataItem>"
        )

        out = _parse_timeline_xml(xml, "fallback")
        self.assertEqual(out.get("type"), 5)
        self.assertEqual(out.get("title"), "Google Gemini 上线了AI音乐生成功能")
        self.assertEqual(out.get("sourceName"), "哔哩哔哩")
        self.assertIn("&share_source=weixin_moments", str(out.get("contentUrl") or ""))
        self.assertTrue(isinstance(out.get("media"), list) and len(out.get("media") or []) == 1)

    def test_external_share_type42_parses_with_raw_ampersands(self):
        xml = (
            "<SnsDataItem><TimelineObject>"
            "<username>wxid_all914izz7w222</username>"
            "<createTime>1771504315</createTime>"
            "<contentDesc>2026 恭喜自己 也恭喜你</contentDesc>"
            "<ContentObject>"
            "<type>42</type>"
            "<title>恭喜自己</title>"
            "<description>成龙/周华健</description>"
            "<contentUrl>https://i.y.qq.com/v8/playsong.html?platform=11&appshare=android_qq</contentUrl>"
            "</ContentObject>"
            "<appInfo><appName>QQ音乐</appName></appInfo>"
            "<mediaList><media>"
            "<type>5</type><id>m2</id>"
            "<url>http://c6.y.qq.com/rsc/fcgi-bin/fcg_pyq_play.fcg?songmid=002kNnX90keHGW&fromtag=46</url>"
            "<thumb>http://szmmsns.qpic.cn/mmsns/test/0</thumb>"
            "</media></mediaList>"
            "</TimelineObject></SnsDataItem>"
        )

        out = _parse_timeline_xml(xml, "fallback")
        self.assertEqual(out.get("type"), 42)
        self.assertEqual(out.get("title"), "恭喜自己")
        self.assertEqual(out.get("sourceName"), "QQ音乐")
        self.assertIn("&appshare=android_qq", str(out.get("contentUrl") or ""))
        self.assertTrue(isinstance(out.get("media"), list) and len(out.get("media") or []) == 1)


if __name__ == "__main__":
    unittest.main()

