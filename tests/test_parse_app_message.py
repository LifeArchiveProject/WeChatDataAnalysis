import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _parse_app_message


class TestParseAppMessage(unittest.TestCase):
    def test_quote_type_57_nested_refermsg_uses_inner_title(self):
        raw_text = (
            '<msg><appmsg appid="" sdkver="0">'
            '<title>一松一紧</title><des></des><action></action><type>57</type>'
            '<showtype>0</showtype><soundtype>0</soundtype><mediatagname></mediatagname>'
            '<messageext></messageext><messageaction></messageaction><content></content>'
            '<url></url><appattach><totallen>0</totallen><attachid></attachid><fileext></fileext></appattach>'
            '<extinfo></extinfo><sourceusername></sourceusername><sourcedisplayname></sourcedisplayname>'
            '<commenturl></commenturl><refermsg>'
            '<type>57</type><svrid>1173057991425172913</svrid>'
            '<fromusr>44372432598@chatroom</fromusr><chatusr>44372432598@chatroom</chatusr>'
            '<displayname><![CDATA[ㅤ磁父]]></displayname>'
            '<content><![CDATA[<msg><appmsg appid="" sdkver="0"><title>那里紧？哪里张？</title><des></des>'
            '<action></action><type>57</type><showtype>0</showtype><soundtype>0</soundtype>'
            '<mediatagname></mediatagname><messageext></messageext><messageaction></messageaction>'
            '<content></content><url></url><appattach><totallen>0</totallen><attachid></attachid>'
            '<fileext></fileext></appattach><extinfo></extinfo><sourceusername></sourceusername>'
            '<sourcedisplayname></sourcedisplayname><commenturl></commenturl></appmsg></msg>]]></content>'
            '</refermsg></appmsg></msg>'
        )

        parsed = _parse_app_message(raw_text)

        self.assertEqual(parsed.get("renderType"), "quote")
        self.assertEqual(parsed.get("content"), "一松一紧")
        self.assertEqual(parsed.get("quoteType"), "57")
        self.assertEqual(parsed.get("quoteContent"), "那里紧？哪里张？")

    def test_quote_type_57_plain_text_refermsg_keeps_text(self):
        raw_text = (
            '<msg><appmsg appid="" sdkver="0">'
            '<title>回复</title><type>57</type>'
            '<refermsg><type>57</type><content><![CDATA[普通文本引用]]></content></refermsg>'
            '</appmsg></msg>'
        )

        parsed = _parse_app_message(raw_text)

        self.assertEqual(parsed.get("renderType"), "quote")
        self.assertEqual(parsed.get("quoteContent"), "普通文本引用")

    def test_quote_type_49_nested_xml_refermsg_uses_inner_title(self):
        raw_text = (
            '<msg><appmsg appid="" sdkver="0">'
            '<title>这种傻逼公众号怎么还在看</title><type>57</type>'
            '<refermsg><type>49</type><displayname><![CDATA[水豚喧喧]]></displayname>'
            '<content><![CDATA[wxid_gryaI8aopjio22: <?xml version="1.0"?><msg><appmsg appid="" sdkver="0">'
            '<title>为自己的美丽漂亮善良知性发声😊</title><des></des>'
            '<type>5</type><url>https://mp.weixin.qq.com/s/example</url>'
            '<thumburl>https://mmbiz.qpic.cn/some-thumb.jpg</thumburl>'
            '</appmsg></msg>]]></content></refermsg></appmsg></msg>'
        )

        parsed = _parse_app_message(raw_text)

        self.assertEqual(parsed.get("renderType"), "quote")
        self.assertEqual(parsed.get("quoteType"), "49")
        self.assertEqual(parsed.get("quoteTitle"), "水豚喧喧")
        self.assertEqual(parsed.get("quoteContent"), "[链接] 为自己的美丽漂亮善良知性发声😊")
        self.assertEqual(parsed.get("quoteThumbUrl"), "https://mmbiz.qpic.cn/some-thumb.jpg")

    def test_public_account_link_exposes_link_type_and_style(self):
        raw_text = (
            '<msg><appmsg appid="" sdkver="0">'
            '<title>为自己的美丽漂亮善良知性发声😊</title>'
            '<des>#日常穿搭灵感 #白色蕾丝裙穿搭 #知性美女</des>'
            '<type>5</type>'
            '<url>http://mp.weixin.qq.com/s?__biz=xx&mid=1</url>'
            '<thumburl>http://mmbiz.qpic.cn/abc/640?wx_fmt=jpeg</thumburl>'
            '<sourceusername>gh_0cef8eaa987d</sourceusername>'
            '<sourcedisplayname>草莓不甜芒果甜</sourcedisplayname>'
            '</appmsg></msg>'
        )

        parsed = _parse_app_message(raw_text)

        self.assertEqual(parsed.get("renderType"), "link")
        self.assertEqual(parsed.get("linkType"), "official_article")
        self.assertEqual(parsed.get("linkStyle"), "cover")

    def test_quote_type_5_nested_xml_refermsg_uses_inner_title(self):
        raw_text = (
            '<msg><appmsg appid="" sdkver="0">'
            '<title>这个年龄有点大啊</title><type>57</type>'
            '<refermsg><type>5</type><displayname><![CDATA[水豚噜噜]]></displayname>'
            '<content><![CDATA[wxid_qrval8aopiio22:\n<?xml version="1.0"?>\n<msg><appmsg appid="" sdkver="0">'
            '<title>谁说冬天不能穿裙子？</title><des></des><type>5</type>'
            '<thumburl>https://mmbiz.qpic.cn/some-thumb2.jpg</thumburl>'
            '<url>https://mp.weixin.qq.com/s/example2</url>'
            '</appmsg></msg>]]></content></refermsg></appmsg></msg>'
        )

        parsed = _parse_app_message(raw_text)

        self.assertEqual(parsed.get("renderType"), "quote")
        self.assertEqual(parsed.get("quoteType"), "5")
        self.assertEqual(parsed.get("quoteTitle"), "水豚噜噜")
        self.assertEqual(parsed.get("quoteContent"), "[链接] 谁说冬天不能穿裙子？")
        self.assertEqual(parsed.get("quoteThumbUrl"), "https://mmbiz.qpic.cn/some-thumb2.jpg")


if __name__ == "__main__":
    unittest.main()
