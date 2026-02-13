import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _parse_app_message


class TestChatAppMessageType4PatMsgRegression(unittest.TestCase):
    def test_type4_link_with_patmsg_metadata_is_not_misclassified_as_pat(self):
        raw_text = (
            "<msg>"
            '<appmsg appid="wxcb8d4298c6a09bcb" sdkver="0">'
            "<title>【中配】抽象可能让你的代码变差 - CodeAesthetic</title>"
            "<des>UP主：黑纹白斑马</des>"
            "<type>4</type>"
            "<url>https://b23.tv/au68guF</url>"
            "<appname>哔哩哔哩</appname>"
            "<appattach><cdnthumburl>3057020100044b30</cdnthumburl></appattach>"
            "<patMsg><chatUser /></patMsg>"
            "</appmsg>"
            "</msg>"
        )

        parsed = _parse_app_message(raw_text)
        self.assertEqual(parsed.get("renderType"), "link")
        self.assertEqual(parsed.get("url"), "https://b23.tv/au68guF")
        self.assertEqual(parsed.get("title"), "【中配】抽象可能让你的代码变差 - CodeAesthetic")
        self.assertEqual(parsed.get("from"), "哔哩哔哩")
        self.assertNotEqual(parsed.get("content"), "[拍一拍]")

    def test_type62_is_still_pat(self):
        raw_text = '<msg><appmsg><title>"A" 拍了拍 "B"</title><type>62</type></appmsg></msg>'
        parsed = _parse_app_message(raw_text)
        self.assertEqual(parsed.get("renderType"), "system")
        self.assertEqual(parsed.get("content"), "[拍一拍]")

    def test_sysmsg_type_patmsg_attr_is_still_pat(self):
        raw_text = '<sysmsg type="patmsg"><foo>bar</foo></sysmsg>'
        parsed = _parse_app_message(raw_text)
        self.assertEqual(parsed.get("renderType"), "system")
        self.assertEqual(parsed.get("content"), "[拍一拍]")


if __name__ == "__main__":
    unittest.main()

