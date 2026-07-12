import json
import os
import sqlite3
import sys
import unittest
import importlib
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestContactsExport(unittest.TestCase):
    def test_html_export_renders_contact_profile_cards(self):
        from wechat_decrypt_tool.routers.chat_contacts import _build_export_contacts, _write_html_export

        built_contacts = _build_export_contacts(
            [{"username": "missing_remote_avatar", "avatarLink": "", "avatar": "http://example.test/local-avatar"}],
            include_avatar_link=True,
        )
        self.assertEqual(built_contacts[0]["avatarLink"], "http://example.test/local-avatar")

        with TemporaryDirectory() as td:
            output_path = Path(td) / "contacts.html"
            _write_html_export(
                output_path,
                export_id="contacts-html-test",
                account="wxid_account",
                source="decrypted",
                contacts=[
                    {
                        "username": "wxid_friend",
                        "displayName": "小明 <好友>",
                        "remark": "项目联系人",
                        "nickname": "明明",
                        "alias": "wechat-ming",
                        "type": "friend",
                        "officialAccountKind": "",
                        "officialAccountType": 0,
                        "region": "中国大陆·四川·成都",
                        "country": "CN",
                        "province": "Sichuan",
                        "city": "Chengdu",
                        "source": "通过名片分享添加",
                        "sourceScene": 17,
                        "avatarLink": "https://example.test/avatar?id=1&size=0",
                    }
                ],
                include_avatar_link=True,
            )

            document = output_path.read_text(encoding="utf-8")
            self.assertIn('class="contact-card"', document)
            self.assertIn('class="contact-avatar"', document)
            self.assertIn('src="https://example.test/avatar?id=1&amp;size=0"', document)
            self.assertNotIn("<table", document)
            self.assertIn("小明 &lt;好友&gt;", document)
            self.assertIn('data-wce-protected-root="1"', document)
            self.assertIn('data-wce-integrity-bundle="1"', document)
            self.assertIn('data-wce-runtime="1"', document)
            self.assertIn('id="wceBrandAttribution"', document)
            for label in ("用户名", "显示名称", "备注", "昵称", "微信号", "地区", "来源"):
                self.assertIn(f">{label}<", document)
                self.assertEqual(document.count(f">{label}<"), 1, label)
            for label in ("头像", "类型", "公众号类型", "公众号类型码", "国家/地区码", "省份", "城市", "来源场景码"):
                self.assertNotIn(f">{label}<", document)
            self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", document)
            self.assertIn("width:50px;height:50px", document)

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
    def _build_extra_buffer(
        cls,
        *,
        country: str,
        province: str,
        city: str,
        source_scene: int,
        gender: int = 0,
        signature: str = "",
    ) -> bytes:
        return b"".join(
            [
                cls._encode_field_varint(2, gender),
                cls._encode_field_len(4, signature.encode("utf-8")),
                cls._encode_field_len(5, country.encode("utf-8")),
                cls._encode_field_len(6, province.encode("utf-8")),
                cls._encode_field_len(7, city.encode("utf-8")),
                cls._encode_field_varint(8, source_scene),
            ]
        )

    def test_region_lookup_uses_generated_dictionary(self):
        from wechat_decrypt_tool.routers.chat_contacts import _build_region

        # `Ziyang` is not in the small hand-maintained fallback map; it comes
        # from the generated province-city dictionary bundled with the backend.
        self.assertEqual(_build_region("CN", "Sichuan", "Ziyang"), "中国大陆·四川·资阳")
        self.assertEqual(_build_region("China", "Sichuan", "Ziyang"), "中国大陆·四川·资阳")

    def test_source_scene_17_is_card_share_for_profiles_and_exports(self):
        from wechat_decrypt_tool.routers.chat_contacts import _contact_item_from_profile_row, _source_scene_label

        self.assertEqual(_source_scene_label(17), "通过名片分享添加")
        profile = _contact_item_from_profile_row(
            account_dir=Path("wxid_account"),
            base_url="http://example.test",
            username="wxid_friend",
            row={"username": "wxid_friend", "source_scene": 17},
        )
        self.assertEqual(profile.get("sourceScene"), 17)
        self.assertEqual(profile.get("source"), "通过名片分享添加")

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
                source_scene=17,
                gender=1,
                signature="自助者天助！！！",
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
                        "source": "decrypted",
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
                self.assertEqual(friend_contact.get("region"), "中国大陆·四川·成都")
                self.assertEqual(friend_contact.get("gender"), 1)
                self.assertEqual(friend_contact.get("signature"), "自助者天助！！！")
                self.assertEqual(friend_contact.get("sourceScene"), 17)
                self.assertEqual(friend_contact.get("source"), "通过名片分享添加")

                export_dir = root / "exports"
                export_dir.mkdir(parents=True, exist_ok=True)

                json_resp = client.post(
                    "/api/chat/contacts/export",
                    json={
                        "account": account,
                        "source": "decrypted",
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
                self.assertEqual(friend_export.get("region"), "中国大陆·四川·成都")
                self.assertEqual(friend_export.get("sourceScene"), 17)
                self.assertEqual(friend_export.get("source"), "通过名片分享添加")

                csv_resp = client.post(
                    "/api/chat/contacts/export",
                    json={
                        "account": account,
                        "source": "decrypted",
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
                self.assertIn("用户名,显示名称,备注,昵称,微信号,类型,公众号类型,公众号类型码,地区,国家/地区码,省份,城市,来源,来源场景码", text.splitlines()[0])
                self.assertNotIn("头像链接", text.splitlines()[0])
                self.assertIn("wxid_friend", text)
                self.assertIn("中国大陆·四川·成都", text)
                self.assertIn("通过名片分享添加", text)
                self.assertIn(",17", text)
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
                        "source": "decrypted",
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

                resp = client.get("/api/chat/contacts", params={"account": account, "source": "decrypted"})
                self.assertEqual(resp.status_code, 404)
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev

    def test_auto_contacts_uses_realtime_without_local_contact_or_session_db(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            account = "wxid_direct"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)
            (account_dir / "_source.json").write_text(
                json.dumps({"db_storage_path": str(root / "WeChat" / "db_storage")}, ensure_ascii=False),
                encoding="utf-8",
            )

            prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
            os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
            try:
                import wechat_decrypt_tool.chat_accounts as chat_accounts
                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_accounts)
                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)
                client = TestClient(app)

                rt_conn = SimpleNamespace(handle=1, lock=threading.Lock())
                sessions = [
                    {"username": "wxid_friend", "is_hidden": 0, "sort_timestamp": 300},
                    {"username": "room@chatroom", "is_hidden": 0, "sort_timestamp": 200},
                    {"username": "gh_service", "is_hidden": 0, "sort_timestamp": 100},
                ]
                with (
                    patch.object(chat_contacts.WCDB_REALTIME, "ensure_connected", return_value=rt_conn),
                    patch.object(chat_contacts, "_wcdb_get_sessions", return_value=sessions),
                    patch.object(
                        chat_contacts,
                        "_wcdb_get_display_names",
                        return_value={
                            "wxid_friend": "好友A",
                            "room@chatroom": "群A",
                            "gh_service": "服务号A",
                        },
                    ),
                    patch.object(chat_contacts, "_wcdb_get_avatar_urls", return_value={"wxid_friend": "https://avatar/a.jpg"}),
                ):
                    resp = client.get(
                        "/api/chat/contacts",
                        params={
                            "account": account,
                            "source": "auto",
                            "include_friends": True,
                            "include_groups": True,
                            "include_officials": True,
                        },
                    )

                self.assertEqual(resp.status_code, 200)
                payload = resp.json()
                self.assertEqual(payload.get("source"), "realtime")
                self.assertEqual(payload.get("total"), 3)
                self.assertEqual(payload.get("counts", {}).get("friends"), 1)
                self.assertEqual(payload.get("counts", {}).get("groups"), 1)
                self.assertEqual(payload.get("counts", {}).get("officials"), 1)
                self.assertFalse((account_dir / "contact.db").exists())
                self.assertFalse((account_dir / "session.db").exists())
                names = {x.get("username"): x.get("displayName") for x in payload.get("contacts", [])}
                self.assertEqual(names.get("wxid_friend"), "好友A")
                self.assertEqual(names.get("room@chatroom"), "群A")
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev

    def test_contact_profile_auto_reads_realtime_contact_table_without_session_match(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            account = "wxid_direct"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)
            (account_dir / "_source.json").write_text(
                json.dumps({"db_storage_path": str(root / "WeChat" / "db_storage")}, ensure_ascii=False),
                encoding="utf-8",
            )

            prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
            os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
            try:
                import wechat_decrypt_tool.chat_accounts as chat_accounts
                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_accounts)
                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)
                client = TestClient(app)

                username = "wxid_group_member"
                common_room = "shared_room@chatroom"
                extra_buffer = self._build_extra_buffer(
                    country="CN",
                    province="Jiangsu",
                    city="Nanjing",
                    source_scene=14,
                    gender=2,
                    signature="签名来自 extra_buffer",
                )
                contact_row = {
                    "username": username,
                    "remark": "",
                    "nick_name": "群成员昵称",
                    "alias": "member_alias",
                    "local_type": 3,
                    "verify_flag": 0,
                    "big_head_url": "https://cdn.example.com/member_big.jpg",
                    "small_head_url": "",
                    # realtime exec_query JSON 通常把 BLOB 转成十六进制字符串。
                    "extra_buffer": extra_buffer.hex(),
                }

                def fake_exec_query(_handle, *, kind, path, sql):
                    self.assertEqual(kind, "contact")
                    self.assertIsNone(path)
                    if "FROM contact" in sql and username in sql:
                        return [contact_row]
                    if "FROM chatroom_member" in sql and username in sql:
                        return [{"username": common_room, "roomId": 42}]
                    return []

                rt_conn = SimpleNamespace(handle=1, lock=threading.Lock())
                with (
                    patch.object(chat_contacts.WCDB_REALTIME, "ensure_connected", return_value=rt_conn),
                    patch.object(chat_contacts, "_wcdb_get_contact", side_effect=RuntimeError("native API missing")),
                    patch.object(chat_contacts, "_wcdb_exec_query", side_effect=fake_exec_query),
                    patch.object(chat_contacts, "_wcdb_get_display_names", return_value={common_room: "共同群聊"}),
                    patch.object(chat_contacts, "_wcdb_get_avatar_urls", return_value={common_room: "https://cdn.example.com/shared-room.jpg"}),
                    patch.object(chat_contacts, "_wcdb_get_sessions", side_effect=AssertionError("profile must not depend on sessions")),
                ):
                    resp = client.get(
                        "/api/chat/contacts/profile",
                        params={
                            "account": account,
                            "source": "auto",
                            "username": username,
                        },
                    )

                self.assertEqual(resp.status_code, 200)
                payload = resp.json()
                self.assertEqual(payload.get("source"), "realtime")
                self.assertTrue(payload.get("found"))
                contact = payload.get("contact") or {}
                self.assertEqual(contact.get("username"), username)
                self.assertEqual(contact.get("displayName"), "群成员昵称")
                self.assertEqual(contact.get("nickname"), "群成员昵称")
                self.assertEqual(contact.get("alias"), "member_alias")
                self.assertEqual(contact.get("type"), "friend")
                self.assertEqual(contact.get("gender"), 2)
                self.assertEqual(contact.get("signature"), "签名来自 extra_buffer")
                self.assertEqual(contact.get("region"), "中国大陆·江苏·南京")
                self.assertEqual(contact.get("sourceScene"), 14)
                self.assertEqual(contact.get("source"), "通过群聊添加")
                self.assertEqual(contact.get("avatarLink"), "https://cdn.example.com/member_big.jpg")
                self.assertEqual(contact.get("commonChatroomCount"), 1)
                common_chatrooms = contact.get("commonChatrooms") or []
                self.assertEqual(len(common_chatrooms), 1)
                self.assertEqual(common_chatrooms[0].get("username"), common_room)
                self.assertEqual(common_chatrooms[0].get("displayName"), "共同群聊")
                self.assertEqual(common_chatrooms[0].get("avatarLink"), "https://cdn.example.com/shared-room.jpg")
                self.assertIn(common_room.replace("@", "%40"), common_chatrooms[0].get("avatar", ""))
            finally:
                if prev is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev

    def test_contact_profile_decrypted_does_not_reuse_contact_list_filters(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_test"
            account_dir = root / "output" / "databases" / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db")
            self._seed_session_db(account_dir / "session.db")

            prev = os.environ.get("WECHAT_TOOL_DATA_DIR")
            os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
            try:
                import wechat_decrypt_tool.chat_helpers as chat_helpers
                import wechat_decrypt_tool.routers.chat_contacts as chat_contacts

                importlib.reload(chat_helpers)
                importlib.reload(chat_contacts)

                app = FastAPI()
                app.include_router(chat_contacts.router)
                client = TestClient(app)

                resp = client.get(
                    "/api/chat/contacts/profile",
                    params={
                        "account": account,
                        "source": "decrypted",
                        "username": "wxid_local_type_3",
                    },
                )

                self.assertEqual(resp.status_code, 200)
                payload = resp.json()
                self.assertTrue(payload.get("found"))
                contact = payload.get("contact") or {}
                self.assertEqual(contact.get("username"), "wxid_local_type_3")
                self.assertEqual(contact.get("displayName"), "不应计入联系人")
                self.assertEqual(contact.get("nickname"), "不应计入联系人")
                self.assertEqual(contact.get("type"), "friend")
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
                        "source": "decrypted",
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
