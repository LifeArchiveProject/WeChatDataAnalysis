import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestContactTypeDetection(unittest.TestCase):
    def test_infer_group(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("123@chatroom", row), "group")

    def test_infer_official_by_prefix(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 1, "verify_flag": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("gh_xxx", row), "official")

    def test_infer_none_for_residual_official_prefix_without_contact_flag(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "verify_flag": 0, "alias": "", "remark": "", "nick_name": ""}
        self.assertIsNone(_infer_contact_type("gh_xxx", row))

    def test_infer_none_for_gh_verify_flag_without_local_type_1(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 0, "verify_flag": 24, "alias": "", "remark": "", "nick_name": ""}
        self.assertIsNone(_infer_contact_type("gh_xxx", row))

    def test_infer_friend_for_non_gh_verify_flag_contact(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        row = {"local_type": 1, "verify_flag": 24, "alias": "", "remark": "", "nick_name": ""}
        self.assertEqual(_infer_contact_type("wxid_xxx", row), "friend")

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

    def test_infer_friend_for_allowed_enterprise_openim(self):
        from wechat_decrypt_tool.routers.chat_contacts import _infer_contact_type

        self.assertEqual(_infer_contact_type("corp@openim", {"local_type": 5}), "friend")
        self.assertIsNone(_infer_contact_type("corp@openim", {"local_type": 1}))

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

    def test_realtime_session_private_rows_are_not_counted_as_contacts(self):
        from wechat_decrypt_tool.routers import chat_contacts

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_conn = SimpleNamespace(handle=1, lock=DummyLock())
        fake_sessions = [
            {"username": "wxid_orphan_private", "sort_timestamp": 10},
            {"username": "123@chatroom", "sort_timestamp": 20},
        ]

        with (
            patch.object(chat_contacts.WCDB_REALTIME, "ensure_connected", return_value=fake_conn),
            patch.object(chat_contacts, "_wcdb_get_sessions", return_value=fake_sessions),
            patch.object(chat_contacts, "_wcdb_get_contacts_compact", return_value=[]),
            patch.object(chat_contacts, "_query_realtime_contact_rows", return_value=[]),
            patch.object(chat_contacts, "_query_realtime_official_account_type_map", return_value={}),
            patch.object(
                chat_contacts,
                "_wcdb_get_display_names",
                return_value={"wxid_orphan_private": "历史私聊", "123@chatroom": "群聊"},
            ),
            patch.object(chat_contacts, "_wcdb_get_avatar_urls", return_value={}),
        ):
            contacts = chat_contacts._collect_contacts_for_account_realtime(
                account_dir=Path("account"),
                base_url="http://test",
                keyword=None,
                include_friends=True,
                include_groups=True,
                include_officials=True,
                include_official_subscriptions=True,
                include_official_services=True,
                include_former_friends=True,
                include_blocked=True,
            )

        self.assertEqual([item["username"] for item in contacts], ["123@chatroom"])
        self.assertEqual(contacts[0]["type"], "group")

    def test_realtime_contact_rows_do_not_default_unknown_rows_to_friends(self):
        from wechat_decrypt_tool.routers import chat_contacts

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_conn = SimpleNamespace(handle=1, lock=DummyLock())
        contact_rows = [
            {"username": "wxid_real_friend", "local_type": 1, "flag": 0},
            {"username": "wxid_residual_unknown", "local_type": 0, "flag": 0, "quan_pin": "", "alias": "", "remark": ""},
            {"username": "room@chatroom", "local_type": 0, "flag": 0},
        ]

        with (
            patch.object(chat_contacts.WCDB_REALTIME, "ensure_connected", return_value=fake_conn),
            patch.object(chat_contacts, "_wcdb_get_sessions", return_value=[]),
            patch.object(chat_contacts, "_wcdb_get_contacts_compact", return_value=contact_rows),
            patch.object(chat_contacts, "_query_realtime_official_account_type_map", return_value={}),
            patch.object(
                chat_contacts,
                "_wcdb_get_display_names",
                return_value={
                    "wxid_real_friend": "真实好友",
                    "wxid_residual_unknown": "未知残留",
                    "room@chatroom": "群聊",
                },
            ),
            patch.object(chat_contacts, "_wcdb_get_avatar_urls", return_value={}),
        ):
            contacts = chat_contacts._collect_contacts_for_account_realtime(
                account_dir=Path("account"),
                base_url="http://test",
                keyword=None,
                include_friends=True,
                include_groups=True,
                include_officials=True,
                include_official_subscriptions=True,
                include_official_services=True,
                include_former_friends=True,
                include_blocked=True,
            )

        by_username = {item["username"]: item["type"] for item in contacts}
        self.assertEqual(by_username, {"wxid_real_friend": "friend", "room@chatroom": "group"})


if __name__ == "__main__":
    unittest.main()
