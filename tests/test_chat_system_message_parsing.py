import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _parse_system_message_content


class TestChatSystemMessageParsing(unittest.TestCase):
    def test_extract_replacemsg_for_revoke(self):
        raw_text = (
            '<sysmsg type="revokemsg"><revokemsg><replacemsg><![CDATA[“张三”撤回了一条消息]]>'
            "</replacemsg></revokemsg></sysmsg>"
        )
        self.assertEqual(_parse_system_message_content(raw_text), "“张三”撤回了一条消息")

    def test_extract_nested_content_in_replacemsg(self):
        raw_text = (
            '<sysmsg type="revokemsg"><revokemsg><replacemsg><![CDATA['
            '<content>"黄智欢" 撤回了一条消息</content><revoketime>0</revoketime>'
            ']]></replacemsg></revokemsg></sysmsg>'
        )
        self.assertEqual(_parse_system_message_content(raw_text), '"黄智欢" 撤回了一条消息')

    def test_extract_revokemsg_text_when_replacemsg_missing(self):
        raw_text = "<revokemsg>你撤回了一条消息</revokemsg>"
        self.assertEqual(_parse_system_message_content(raw_text), "你撤回了一条消息")

    def test_revoke_fallback_when_no_readable_text(self):
        raw_text = '<sysmsg type="revokemsg"></sysmsg>'
        self.assertEqual(_parse_system_message_content(raw_text), "撤回了一条消息")

    def test_normal_system_message_still_cleaned(self):
        raw_text = "<sysmsg><template><![CDATA[ 张三  加入了群聊 ]]></template></sysmsg>"
        self.assertEqual(_parse_system_message_content(raw_text), "张三 加入了群聊")


if __name__ == "__main__":
    unittest.main()
