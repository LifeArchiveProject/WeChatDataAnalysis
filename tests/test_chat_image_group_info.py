import hashlib
import sqlite3
import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.chat_helpers import _extract_image_group_info
from wechat_decrypt_tool.routers import chat as chat_router


GROUP_ID_INPUT = "A1B2C3D4-E5F6-47A8-90BC-1234567890AB"
GROUP_ID = GROUP_ID_INPUT.lower()


def _image_xml(*, group_type: str = "1", group_id: str = GROUP_ID_INPUT, count: int = 4) -> str:
    return (
        '<?xml version="1.0"?>'
        "<msg>"
        '<type>unrelated-message-type</type>'
        '<img md5="0123456789abcdef0123456789abcdef" />'
        "<GROUPINFO>"
        f"<TYPE>  {group_type}  </TYPE>"
        f"<ID><![CDATA[\n{group_id}\n]]></ID>"
        f"<COUNT>  {count}  </COUNT>"
        "</GROUPINFO>"
        "</msg>"
    )


class _DummyRequest:
    base_url = "http://testserver/"


class _DummyConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


class TestImageGroupInfoParser(unittest.TestCase):
    def test_reads_case_insensitive_children_only_from_groupinfo(self):
        parsed = _extract_image_group_info(_image_xml(group_type="album"))

        self.assertEqual(
            parsed,
            {"type": "album", "id": GROUP_ID, "count": 4},
        )

    def test_rejects_missing_invalid_or_single_item_group_metadata(self):
        cases = (
            "<msg><type>1</type><id>" + GROUP_ID + "</id><count>4</count></msg>",
            "<msg><id>" + GROUP_ID + "</id><groupinfo><type>1</type><count>4</count></groupinfo></msg>",
            "<msg><groupinfo><id>" + GROUP_ID + "</id><count>4</count></groupinfo></msg>",
            "<msg><groupinfo><type>1</type><id>" + GROUP_ID + "</id></groupinfo></msg>",
            "<msg><groupinfo><type>1</type><id>not-a-uuid</id><count>4</count></groupinfo></msg>",
            "<msg><groupinfo><type>1</type><id>" + GROUP_ID + "</id><count>many</count></groupinfo></msg>",
            "<msg><groupinfo><type>1</type><id>" + GROUP_ID + "</id><count>1</count></groupinfo></msg>",
            "<msg><groupinfo><type>1</type><id>" + GROUP_ID.replace("-", "") + "</id><count>4</count></groupinfo></msg>",
        )

        for xml in cases:
            with self.subTest(xml=xml):
                self.assertEqual(_extract_image_group_info(xml), {})


class TestImageGroupInfoChatApi(unittest.TestCase):
    def _common_patches(self, account_dir: Path, conn: _DummyConn):
        return (
            patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
            patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
            patch.object(chat_router, "_load_contact_rows", return_value={}),
            patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
            patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
            patch.object(chat_router, "_wcdb_get_avatar_urls", return_value={}),
            patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
            patch.object(chat_router, "_load_group_nickname_map", return_value={}),
        )

    def _assert_group_fields(self, response):
        self.assertEqual(response.get("status"), "success")
        messages = response.get("messages") or []
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].get("renderType"), "image")
        self.assertEqual(messages[0].get("imageGroupType"), "1")
        self.assertEqual(messages[0].get("imageGroupId"), GROUP_ID)
        self.assertEqual(messages[0].get("imageGroupCount"), 4)

    def test_realtime_messages_expose_image_group_metadata(self):
        row = chat_router._normalize_realtime_message_item(
            {
                "localId": 1,
                "serverId": 123,
                "localType": 3,
                "sortSeq": 1700000000000,
                "realSenderId": 2,
                "createTime": 1700000000,
                "messageContent": _image_xml(),
                "compressContent": None,
                "packedInfoData": None,
                "senderUsername": "wxid_friend",
            }
        )

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True)
            conn = _DummyConn()
            common = self._common_patches(account_dir, conn)
            with ExitStack() as stack:
                for context in common:
                    stack.enter_context(context)
                stack.enter_context(patch.object(
                    chat_router,
                    "_fetch_realtime_message_rows_via_exec",
                    return_value=([], False, None, "", None),
                ))
                stack.enter_context(patch.object(
                    chat_router,
                    "_fetch_realtime_message_rows_via_cursor",
                    return_value=([row], False),
                ))
                response = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username="wxid_friend",
                    account="acc",
                    source="realtime",
                )

        self._assert_group_fields(response)

    def test_decrypted_messages_expose_image_group_metadata(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True)
            username = "wxid_friend"
            table_name = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()
            db_path = account_dir / "message_0.db"
            db = sqlite3.connect(str(db_path))
            try:
                db.execute("CREATE TABLE Name2Id (user_name TEXT)")
                db.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (1, ?)", (account_dir.name,))
                db.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (2, ?)", (username,))
                db.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        local_id INTEGER,
                        server_id INTEGER,
                        local_type INTEGER,
                        sort_seq INTEGER,
                        real_sender_id INTEGER,
                        create_time INTEGER,
                        message_content TEXT,
                        compress_content BLOB
                    )
                    """
                )
                db.execute(
                    f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (1, 123, 3, 1700000000000, 2, 1700000000, _image_xml(), None),
                )
                db.commit()
            finally:
                db.close()

            conn = _DummyConn()
            common = self._common_patches(account_dir, conn)
            with ExitStack() as stack:
                for context in common:
                    stack.enter_context(context)
                response = chat_router.list_chat_messages(
                    _DummyRequest(),
                    username=username,
                    account="acc",
                    source="decrypted",
                )

        self._assert_group_fields(response)


if __name__ == "__main__":
    unittest.main()
