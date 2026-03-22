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

    def test_chatroom_top_message_uses_response_name_by_default(self):
        raw_text = (
            "<!-- ChatRoomTopMsgRequest --> 17990148862@chatroom 1 3546361838777087323 49 "
            "wxid_7iazcmpjn90k22 <!-- ChatRoomTopMsgResponse --> 21 新青年 68"
        )
        self.assertEqual(_parse_system_message_content(raw_text), "新青年置顶了一条消息")

    def test_chatroom_top_message_prefers_resolved_display_name(self):
        raw_text = (
            "<!-- ChatRoomTopMsgRequest --> 17990148862@chatroom 2 3546361838777087323 0 "
            "wxid_k7zhjk9xvzsk22 <!-- ChatRoomTopMsgResponse --> 21 A 69"
        )

        def resolve_display_name(username: str, fallback: str) -> str:
            self.assertEqual(username, "wxid_k7zhjk9xvzsk22")
            self.assertEqual(fallback, "A")
            return "周鑫"

        self.assertEqual(
            _parse_system_message_content(raw_text, resolve_display_name=resolve_display_name),
            "周鑫移除了一条置顶消息",
        )

    def test_chatroom_top_message_without_comment_markers_still_parses(self):
        raw_text = "17990148862@chatroom 1 3546361838777087323 49 wxid_7iazcmpjn90k22 21 新青年 68"
        self.assertEqual(_parse_system_message_content(raw_text), "新青年置顶了一条消息")

    def test_chatroom_top_message_without_comment_markers_still_prefers_resolved_name(self):
        raw_text = "17990148862@chatroom 2 3546361838777087323 0 wxid_k7zhjk9xvzsk22 21 A 69"

        def resolve_display_name(username: str, fallback: str) -> str:
            self.assertEqual(username, "wxid_k7zhjk9xvzsk22")
            self.assertEqual(fallback, "A")
            return "周鑫"

        self.assertEqual(
            _parse_system_message_content(raw_text, resolve_display_name=resolve_display_name),
            "周鑫移除了一条置顶消息",
        )

    def test_chatroom_top_message_xml_payload_still_parses(self):
        raw_text = (
            '<sysmsg type="mmchatroomtopmsg"><mmchatroomtopmsg>'
            '<chatroomname><![CDATA[17990148862@chatroom]]></chatroomname>'
            '<op><![CDATA[1]]></op>'
            '<newmsgid><![CDATA[3546361838777087323]]></newmsgid>'
            '<msgtype><![CDATA[49]]></msgtype>'
            '<username><![CDATA[wxid_7iazcmpjn90k22]]></username>'
            '<id><![CDATA[21]]></id>'
            '<nickname><![CDATA[新青年]]></nickname>'
            '</mmchatroomtopmsg><chatroominfoversion><![CDATA[68]]></chatroominfoversion></sysmsg>'
        )
        self.assertEqual(_parse_system_message_content(raw_text), "新青年置顶了一条消息")

    def test_chatroom_top_message_xml_payload_prefers_resolved_name(self):
        raw_text = (
            '<sysmsg type="mmchatroomtopmsg"><mmchatroomtopmsg>'
            '<chatroomname><![CDATA[17990148862@chatroom]]></chatroomname>'
            '<op><![CDATA[2]]></op>'
            '<newmsgid><![CDATA[3546361838777087323]]></newmsgid>'
            '<msgtype><![CDATA[0]]></msgtype>'
            '<username><![CDATA[wxid_k7zhjk9xvzsk22]]></username>'
            '<id><![CDATA[21]]></id>'
            '<nickname><![CDATA[A]]></nickname>'
            '</mmchatroomtopmsg><chatroominfoversion><![CDATA[69]]></chatroominfoversion></sysmsg>'
        )

        def resolve_display_name(username: str, fallback: str) -> str:
            self.assertEqual(username, "wxid_k7zhjk9xvzsk22")
            self.assertEqual(fallback, "A")
            return "周鑫"

        self.assertEqual(
            _parse_system_message_content(raw_text, resolve_display_name=resolve_display_name),
            "周鑫移除了一条置顶消息",
        )


if __name__ == "__main__":
    unittest.main()
