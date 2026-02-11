import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _extract_sender_from_group_xml


class TestGroupXmlSenderExtraction(unittest.TestCase):
    def test_prefers_outer_fromusername_over_nested_refermsg(self):
        xml_text = (
            '<msg><appmsg><type>57</type>'
            '<refermsg><fromusername>quoted_user@chatroom</fromusername></refermsg>'
            '</appmsg><fromusername>actual_sender@chatroom</fromusername></msg>'
        )
        self.assertEqual(_extract_sender_from_group_xml(xml_text), "actual_sender@chatroom")


if __name__ == "__main__":
    unittest.main()
