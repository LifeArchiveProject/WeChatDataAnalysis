import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestContactTypeDetection(unittest.TestCase):
    def test_infer_group(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("123@chatroom", row), "group")

    def test_infer_official_by_prefix(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "verify_flag": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("gh_xxx", row), "official")

    def test_infer_official_by_verify_flag(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 1, "verify_flag": 24, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("wxid_xxx", row), "official")

    def test_infer_none_for_local_type_3_without_verify(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 3, "verify_flag": 0, "alias": "", "remark": "", "nick_name": "普通联系人"}
        self.assertIsNone(_infer_contact_type("wxid_xxx", row))

    def test_infer_none_from_wxid_alias_when_local_type_not_1(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "verify_flag": 0, "alias": "wechat_id", "remark": "", "nick_name": ""}
        self.assertIsNone(_infer_contact_type("wxid_xxx", row))

    def test_infer_friend_from_local_type_1(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 1, "verify_flag": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("wxid_xxx", row), "friend")

    def test_infer_none_from_local_type_2(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 2, "verify_flag": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertIsNone(_infer_contact_type("wxid_xxx", row))

    def test_infer_none_when_empty_type_0(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "verify_flag": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertIsNone(_infer_contact_type("wxid_xxx", row))

    def test_valid_contact_username_filters_system_accounts(self):
        from wechat_decrypt_tool.routers.chat_contacts import _is_valid_contact_username

        self.assertFalse(_is_valid_contact_username("filehelper"))
        self.assertFalse(_is_valid_contact_username("notifymessage"))
        self.assertFalse(_is_valid_contact_username("fake_abc"))
        self.assertTrue(_is_valid_contact_username("weixin"))
        self.assertTrue(_is_valid_contact_username("wxid_abc"))
        self.assertTrue(_is_valid_contact_username("123@chatroom"))


if __name__ == "__main__":
    unittest.main()
