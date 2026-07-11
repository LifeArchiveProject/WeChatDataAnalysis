import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import favorites as favorites_router


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/api/favorites",
            "headers": [],
        }
    )


class TestFavorites(unittest.TestCase):
    def _seed_favorite_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.executescript(
                """
                CREATE TABLE fav_db_item(
                    local_id INTEGER PRIMARY KEY,
                    server_id INTEGER,
                    type INTEGER,
                    update_time INTEGER,
                    content TEXT,
                    source_id TEXT,
                    sync_status INTEGER,
                    upload_status INTEGER,
                    fromusr TEXT,
                    realchatname TEXT
                );
                CREATE TABLE fav_tag_db_item(
                    local_id INTEGER PRIMARY KEY,
                    server_id INTEGER,
                    name TEXT,
                    seq INTEGER
                );
                CREATE TABLE fav_bind_tag_db_item(
                    tag_local_id INTEGER,
                    tag_server_id INTEGER,
                    fav_local_id INTEGER,
                    fav_server_id INTEGER,
                    op_code INTEGER
                );
                """
            )
            note_xml = """
                <favitem type="18">
                  <source sourcetype="1"><fromusr>wxid_friend</fromusr></source>
                  <datalist>
                    <dataitem datatype="8" dataid="internal-note">
                      <datatitle>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.htm</datatitle>
                      <datafmt>.htm</datafmt>
                      <fullmd5>bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb</fullmd5>
                      <cdn_dataurl>001122</cdn_dataurl>
                    </dataitem>
                    <dataitem datatype="1"><datadesc>项目会议纪要\n第二行</datadesc></dataitem>
                    <dataitem datatype="6">
                      <datatitle>相关资料</datatitle>
                      <datadesc>会议链接</datadesc>
                      <weburlitem><link>https://example.test/note</link></weburlitem>
                    </dataitem>
                  </datalist>
                </favitem>
            """
            conn.execute(
                "INSERT INTO fav_db_item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, 101, 18, 1735689600, note_xml, "source-1", 3, 2, "wxid_friend", ""),
            )
            conn.execute(
                "INSERT INTO fav_db_item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (2, 102, 5, 1735689500, "<broken", "source-2", 3, 2, "", ""),
            )
            conn.execute("INSERT INTO fav_tag_db_item VALUES (7, 700, '工作', 1)")
            conn.execute("INSERT INTO fav_bind_tag_db_item VALUES (7, 700, 1, 101, 0)")
            conn.commit()
        finally:
            conn.close()

    def _call(self, account_dir: Path, **kwargs):
        ctx = SimpleNamespace(
            name="wxid_test",
            account_dir=account_dir,
            db_key_present=False,
            db_storage_path="",
            wxid_dir="",
        )
        params = {
            "request": _request(),
            "account": "wxid_test",
            "q": "",
            "kind": "all",
            "tag_id": 0,
            "source": "decrypted",
            "limit": 80,
            "offset": 0,
        }
        params.update(kwargs)
        with (
            patch.object(favorites_router, "resolve_chat_account_context", return_value=ctx),
            patch.object(
                favorites_router,
                "_resolve_general_contacts",
                return_value={
                    "wxid_friend": {
                        "username": "wxid_friend",
                        "displayName": "测试好友",
                        "avatar": "/api/chat/avatar?username=wxid_friend",
                        "isGroup": False,
                    }
                },
            ),
        ):
            return favorites_router.list_favorites(**params)

    def test_parses_note_tags_source_and_hides_internal_note_file(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._seed_favorite_db(account_dir / "favorite.db")
            response = self._call(account_dir)

        self.assertEqual(response["status"], "success")
        self.assertEqual(response["databaseTotal"], 2)
        self.assertEqual(response["typeCounts"], {"18": 1, "5": 1})
        note = response["items"][0]
        self.assertEqual(note["typeLabel"], "笔记")
        self.assertEqual(note["title"], "笔记")
        self.assertEqual(note["textBlocks"], ["项目会议纪要\n第二行"])
        self.assertEqual([item["typeLabel"] for item in note["attachments"]], ["链接"])
        self.assertEqual(note["attachments"][0]["url"], "https://example.test/note")
        self.assertEqual([tag["name"] for tag in note["tags"]], ["工作"])
        self.assertEqual(note["sourceContact"]["displayName"], "测试好友")

    def test_filters_by_query_type_and_tag(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._seed_favorite_db(account_dir / "favorite.db")

            by_query = self._call(account_dir, q="会议纪要")
            by_type = self._call(account_dir, kind="18")
            by_tag = self._call(account_dir, tag_id=7)

        self.assertEqual(by_query["total"], 1)
        self.assertEqual(by_type["total"], 1)
        self.assertEqual(by_tag["total"], 1)
        self.assertEqual(by_tag["items"][0]["localId"], 1)

    def test_malformed_xml_still_returns_a_safe_row(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._seed_favorite_db(account_dir / "favorite.db")
            response = self._call(account_dir, kind="5")

        self.assertEqual(response["total"], 1)
        item = response["items"][0]
        self.assertFalse(item["parsed"])
        self.assertEqual(item["title"], "链接")
        self.assertEqual(item["attachments"], [])

    def test_endpoint_defaults_to_realtime_source(self):
        parameter = favorites_router.list_favorites.__signature__.parameters["source"] if hasattr(
            favorites_router.list_favorites, "__signature__"
        ) else None
        if parameter is not None:
            default = parameter.default
        else:
            import inspect

            default = inspect.signature(favorites_router.list_favorites).parameters["source"].default
        self.assertEqual(default.default, "realtime")

    def test_direct_favorite_types_do_not_use_recorditem_numbering(self):
        voice = favorites_router._parse_favorite_row(
            {
                "local_id": 3,
                "type": 3,
                "content": (
                    '<favitem type="3"><source><fromusr>wxid_friend</fromusr></source><datalist>'
                    '<dataitem datatype="3"><datafmt>silk</datafmt><duration>13540</duration>'
                    '<fullmd5>11111111111111111111111111111111</fullmd5></dataitem>'
                    '</datalist></favitem>'
                ),
            },
            [],
            account_name="wxid_test",
        )
        video = favorites_router._parse_favorite_row(
            {
                "local_id": 4,
                "type": 4,
                "content": (
                    '<favitem type="4"><source><fromusr>12345@chatroom</fromusr>'
                    '<realchatname>wxid_sender</realchatname></source><datalist>'
                    '<dataitem datatype="4"><duration>11</duration>'
                    '<fullmd5>22222222222222222222222222222222</fullmd5>'
                    '<thumbfullmd5>33333333333333333333333333333333</thumbfullmd5></dataitem>'
                    '</datalist></favitem>'
                ),
            },
            [],
            account_name="wxid_test",
        )

        self.assertEqual(voice["attachments"][0]["renderType"], "voice")
        self.assertEqual(video["attachments"][0]["renderType"], "video")
        self.assertEqual(video["senderUsername"], "wxid_sender")
        self.assertEqual(video["conversationUsername"], "12345@chatroom")

    def test_record_items_preserve_sender_identity_for_chat_renderer(self):
        item = favorites_router._parse_favorite_row(
            {
                "local_id": 14,
                "type": 14,
                "content": (
                    '<favitem type="14"><datalist><dataitem datatype="1">'
                    '<sourcename>测试好友</sourcename><sourceusername>wxid_friend</sourceusername>'
                    '<sourceavatar>https://example.test/avatar.jpg</sourceavatar>'
                    '<sourcetime>2026-07-11 10:00:00</sourcetime><datadesc>第一条消息</datadesc>'
                    '</dataitem></datalist></favitem>'
                ),
            },
            [],
        )

        record = item["displayItems"][0]
        self.assertEqual(record["sourceName"], "测试好友")
        self.assertEqual(record["sourceUsername"], "wxid_friend")
        self.assertEqual(record["sourceAvatar"], "https://example.test/avatar.jpg")
        self.assertEqual(record["sourceTime"], "2026-07-11 10:00:00")

    def test_record_mp4_item_is_rendered_as_video(self):
        item = favorites_router._parse_favorite_row(
            {
                "local_id": 15,
                "type": 14,
                "content": (
                    '<favitem type="14"><datalist><dataitem datatype="4">'
                    '<datafmt>.mp4</datafmt><duration>38</duration><datasize>5327967</datasize>'
                    '<fullmd5>11111111111111111111111111111111</fullmd5>'
                    '<thumbfullmd5>22222222222222222222222222222222</thumbfullmd5>'
                    '</dataitem></datalist></favitem>'
                ),
            },
            [],
        )

        record = item["displayItems"][0]
        self.assertEqual(record["typeLabel"], "视频")
        self.assertEqual(record["renderType"], "video")
        self.assertEqual(record["dataFormat"], ".mp4")

    def test_top_level_location_link_and_finder_are_renderable(self):
        location = favorites_router._parse_favorite_row(
            {
                "local_id": 6,
                "type": 6,
                "content": (
                    '<favitem type="6"><locitem><lng>104.02</lng><lat>30.52</lat>'
                    '<label>四川省成都市</label><poiname>河畔</poiname></locitem></favitem>'
                ),
            },
            [],
        )
        link = favorites_router._parse_favorite_row(
            {
                "local_id": 5,
                "type": 5,
                "content": (
                    '<favitem type="5"><source><link>https://example.test/page</link></source>'
                    '<datalist><dataitem datatype="5"><thumbfullmd5>'
                    '44444444444444444444444444444444</thumbfullmd5></dataitem></datalist>'
                    '<weburlitem><pagetitle>示例页面</pagetitle><pagedesc>页面摘要</pagedesc>'
                    '<clean_url>https://example.test/page</clean_url></weburlitem></favitem>'
                ),
            },
            [],
        )
        finder = favorites_router._parse_favorite_row(
            {
                "local_id": 20,
                "type": 20,
                "content": (
                    '<favitem type="20"><finderFeed><objectId>100</objectId><nickname>作者</nickname>'
                    '<avatar>https://example.test/avatar.jpg</avatar><desc>视频正文</desc>'
                    '<username>v2_test@finder</username><mediaList><media>'
                    '<url>https://example.test/video.mp4</url><coverUrl>https://example.test/cover.jpg</coverUrl>'
                    '</media></mediaList></finderFeed></favitem>'
                ),
            },
            [],
        )

        self.assertEqual(location["attachments"][0]["renderType"], "location")
        self.assertEqual(location["attachments"][0]["location"]["poiname"], "河畔")
        self.assertEqual(link["attachments"][0]["title"], "示例页面")
        self.assertEqual(link["attachments"][0]["renderType"], "link")
        self.assertEqual(finder["attachments"][0]["linkType"], "finder")
        self.assertEqual(finder["attachments"][0]["preview"], "https://example.test/cover.jpg")


if __name__ == "__main__":
    unittest.main()
