import json
import os
import sqlite3
import sys
import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestContactsExport(unittest.TestCase):
    @staticmethod
    def _encode_varint(value: int) -> bytes:
        v = int(value)
        out = bytearray()
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        return bytes(out)

    @classmethod
    def _encode_field_len(cls, field_no: int, raw: bytes) -> bytes:
        tag = (int(field_no) << 3) | 2
        payload = bytes(raw)
        return cls._encode_varint(tag) + cls._encode_varint(len(payload)) + payload

    @classmethod
    def _encode_field_varint(cls, field_no: int, value: int) -> bytes:
        tag = int(field_no) << 3
        return cls._encode_varint(tag) + cls._encode_varint(int(value))

    @classmethod
    def _build_extra_buffer(cls, *, country: str, province: str, city: str, source_scene: int) -> bytes:
        return b"".join(
            [
                cls._encode_field_len(5, country.encode("utf-8")),
                cls._encode_field_len(6, province.encode("utf-8")),
                cls._encode_field_len(7, city.encode("utf-8")),
                cls._encode_field_varint(8, source_scene),
            ]
        )

    def _seed_contact_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE contact (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT,
                    extra_buffer BLOB
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE stranger (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT,
                    extra_buffer BLOB
                )
                """
            )

            friend_extra_buffer = self._build_extra_buffer(
                country="CN",
                province="Sichuan",
                city="Chengdu",
                source_scene=14,
            )

            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "wxid_friend",
                    "好友备注",
                    "好友昵称",
                    "friend_alias",
                    1,
                    0,
                    "https://cdn.example.com/friend_big.jpg",
                    "https://cdn.example.com/friend_small.jpg",
                    friend_extra_buffer,
                ),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "room@chatroom",
                    "",
                    "测试群",
                    "",
                    0,
                    0,
                    "https://cdn.example.com/group_big.jpg",
                    "",
                    b"",
                ),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "gh_official",
                    "",
                    "公众号",
                    "",
                    4,
                    8,
                    "",
                    "https://cdn.example.com/official_small.jpg",
                    b"",
                ),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "wxid_local_type_3",
                    "",
                    "不应计入联系人",
                    "",
                    3,
                    0,
                    "",
                    "",
                    b"",
                ),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "weixin",
                    "",
                    "微信团队",
                    "",
                    1,
                    56,
                    "",
                    "",
                    b"",
                ),
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "filehelper",
                    "",
                    "文件传输助手",
                    "",
                    0,
                    0,
                    "",
                    "",
                    b"",
                ),
            )
            conn.execute(
                "INSERT INTO stranger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "stranger_verified",
                    "",
                    "陌生人认证号",
                    "",
                    4,
                    24,
                    "",
                    "",
                    b"",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_session_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE SessionTable (
                    username TEXT,
                    sort_timestamp INTEGER,
                    last_timestamp INTEGER
                )
                """
            )
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("room@chatroom", 300, 300))
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("wxid_friend", 200, 200))
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("gh_official", 100, 100))
            conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", ("missing@chatroom", 250, 250))
            conn.commit()
        finally:
            conn.close()

    def _seed_contact_db_legacy(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE contact (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE stranger (
                    username TEXT,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    local_type INTEGER,
                    verify_flag INTEGER,
                    big_head_url TEXT,
                    small_head_url TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "wxid_legacy_friend",
                    "旧版好友备注",
                    "旧版好友昵称",
                    "legacy_friend_alias",
                    1,
                    0,
                    "",
                    "",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def test_export_json_and_csv(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db")
            self._seed_session_db(account_dir / "session.db")

            prev = None
            try:
                prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)

                client = TestClient(app)

                list_resp = client.get(
                    "/api/chat/contacts",
                    params={
                        "account": account,
                        "include_friends": True,
                        "include_groups": True,
                        "include_officials": True,
                    },
                )
                self.assertEqual(list_resp.status_code, 200)
                list_payload = list_resp.json()
                self.assertEqual(list_payload["status"], "success")
                self.assertEqual(list_payload["total"], 6)
                self.assertEqual(list_payload["counts"]["friends"], 1)
                self.assertEqual(list_payload["counts"]["groups"], 2)
                self.assertEqual(list_payload["counts"]["officials"], 3)
                usernames = {str(x.get("username")) for x in list_payload.get("contacts", [])}
                self.assertIn("missing@chatroom", usernames)
                self.assertIn("weixin", usernames)
                self.assertNotIn("wxid_local_type_3", usernames)
                first = list_payload["contacts"][0]
                self.assertIn("avatarLink", first)

                friend_contact = next(
                    (x for x in list_payload.get("contacts", []) if str(x.get("username")) == "wxid_friend"),
                    {},
                )
                self.assertEqual(friend_contact.get("country"), "CN")
                self.assertEqual(friend_contact.get("province"), "Sichuan")
                self.assertEqual(friend_contact.get("city"), "Chengdu")
                self.assertEqual(friend_contact.get("region"), "中国大陆·Sichuan·Chengdu")
                self.assertEqual(friend_contact.get("sourceScene"), 14)
                self.assertEqual(friend_contact.get("source"), "通过群聊添加")

                export_dir = root / "exports"
                export_dir.mkdir(parents=True, exist_ok=True)

                json_resp = client.post(
                    "/api/chat/contacts/export",
                    json={
                        "account": account,
                        "output_dir": str(export_dir),
                        "format": "json",
                        "include_avatar_link": True,
                        "contact_types": {
                            "friends": True,
                            "groups": True,
                            "officials": True,
                        },
                    },
                )
                self.assertEqual(json_resp.status_code, 200)
                json_payload = json_resp.json()
                self.assertEqual(json_payload["status"], "success")
                self.assertEqual(json_payload["count"], 6)
                json_path = Path(json_payload["outputPath"])
                self.assertTrue(json_path.exists())

                data = json.loads(json_path.read_text(encoding="utf-8"))
                self.assertEqual(data["count"], 6)
                self.assertIn("avatarLink", data["contacts"][0])
                self.assertIn("region", data["contacts"][0])
                self.assertIn("country", data["contacts"][0])
                self.assertIn("province", data["contacts"][0])
                self.assertIn("city", data["contacts"][0])
                self.assertIn("source", data["contacts"][0])
                self.assertIn("sourceScene", data["contacts"][0])
                export_usernames = {str(x.get("username")) for x in data.get("contacts", [])}
                self.assertIn("missing@chatroom", export_usernames)
                self.assertNotIn("wxid_local_type_3", export_usernames)

                friend_export = next(
                    (x for x in data.get("contacts", []) if str(x.get("username")) == "wxid_friend"),
                    {},
                )
                self.assertEqual(friend_export.get("region"), "中国大陆·Sichuan·Chengdu")
                self.assertEqual(friend_export.get("sourceScene"), 14)
                self.assertEqual(friend_export.get("source"), "通过群聊添加")

                csv_resp = client.post(
                    "/api/chat/contacts/export",
                    json={
                        "account": account,
                        "output_dir": str(export_dir),
                        "format": "csv",
                        "include_avatar_link": False,
                        "contact_types": {
                            "friends": True,
                            "groups": False,
                            "officials": False,
                        },
                    },
                )
                self.assertEqual(csv_resp.status_code, 200)
                csv_payload = csv_resp.json()
                self.assertEqual(csv_payload["count"], 1)
                csv_path = Path(csv_payload["outputPath"])
                text = csv_path.read_text(encoding="utf-8-sig")
                self.assertIn("用户名,显示名称,备注,昵称,微信号,类型,地区,国家/地区码,省份,城市,来源,来源场景码", text.splitlines()[0])
                self.assertNotIn("头像链接", text.splitlines()[0])
                self.assertIn("wxid_friend", text)
                self.assertIn("中国大陆·Sichuan·Chengdu", text)
                self.assertIn("通过群聊添加", text)
                self.assertIn(",14", text)
                self.assertNotIn("wxid_local_type_3", text)
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev

    def test_export_invalid_format_returns_400(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db")
            self._seed_session_db(account_dir / "session.db")

            prev = None
            try:
                prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)

                client = TestClient(app)
                resp = client.post(
                    "/api/chat/contacts/export",
                    json={
                        "account": account,
                        "output_dir": str(root / "exports"),
                        "format": "vcf",
                        "include_avatar_link": True,
                        "contact_types": {
                            "friends": True,
                            "groups": True,
                            "officials": True,
                        },
                    },
                )
                self.assertEqual(resp.status_code, 400)
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev

    def test_missing_contact_db_returns_404(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)

            # only session.db exists
            self._seed_session_db(account_dir / "session.db")

            prev = None
            try:
                prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)
                client = TestClient(app)

                resp = client.get("/api/chat/contacts", params={"account": account})
                self.assertEqual(resp.status_code, 404)
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev

    def test_legacy_schema_without_extra_buffer_is_compatible(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_legacy"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db_legacy(account_dir / "contact.db")
            self._seed_session_db(account_dir / "session.db")

            prev = None
            try:
                prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)
                client = TestClient(app)

                resp = client.get(
                    "/api/chat/contacts",
                    params={
                        "account": account,
                        "include_friends": True,
                        "include_groups": False,
                        "include_officials": False,
                    },
                )
                self.assertEqual(resp.status_code, 200)
                payload = resp.json()
                self.assertEqual(payload.get("status"), "success")
                self.assertEqual(int(payload.get("total", 0)), 1)

                contact = payload.get("contacts", [])[0]
                self.assertEqual(contact.get("username"), "wxid_legacy_friend")
                self.assertEqual(contact.get("country"), "")
                self.assertEqual(contact.get("province"), "")
                self.assertEqual(contact.get("city"), "")
                self.assertEqual(contact.get("region"), "")
                self.assertIsNone(contact.get("sourceScene"))
                self.assertEqual(contact.get("source"), "")
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev


if __name__ == "__main__":
    unittest.main()
