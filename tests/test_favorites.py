import sqlite3
import struct
import sys
import threading
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import favorites as favorites_router
from wechat_decrypt_tool.routers import general as general_router
from wechat_decrypt_tool import wcdb_realtime
from wechat_decrypt_tool.native_core_client import parse_native_query_page


class _SQLiteTextBytes(bytes):
    """保留 SQLite TEXT 原始字节，同时与 BLOB 区分。"""


@contextmanager
def _native_favorite_source(db_path: Path):
    # 用合成 SQLite 数据生成原生查询协议，实际执行生产代码的严格 UTF-8 解码。
    conn = sqlite3.connect(str(db_path))
    conn.text_factory = _SQLiteTextBytes

    def execute(_handle, *, kind, path, sql):
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
        payload = bytearray(b"WQR1" + struct.pack("<HHII", 1, 0, len(columns), len(rows)))

        def append_sized(value):
            payload.extend(struct.pack("<I", len(value)))
            payload.extend(value)

        for column in columns:
            append_sized(column.encode("utf-8"))
        for row in rows:
            for value in row:
                if value is None:
                    payload.append(0)
                elif isinstance(value, int):
                    payload.append(1)
                    payload.extend(struct.pack("<q", value))
                elif isinstance(value, float):
                    payload.append(2)
                    payload.extend(struct.pack("<d", value))
                else:
                    payload.append(3 if isinstance(value, _SQLiteTextBytes) else 4)
                    append_sized(value)
        return list(parse_native_query_page(bytes(payload), has_more=False).records())

    rt_conn = SimpleNamespace(handle=1, lock=threading.RLock())
    source = general_router._WCDBDatabaseSource(rt_conn, db_path)
    try:
        with (
            patch.object(wcdb_realtime.native_core_realtime, "exec_query", side_effect=execute),
            patch.object(favorites_router, "_open_db_source", return_value=source),
        ):
            yield source
    finally:
        conn.close()


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

    def test_realtime_invalid_utf8_fields_do_not_break_the_favorite_list(self):
        cases = {
            "content": b'<favitem type="5"><desc>hello\xffworld</desc></favitem>',
            "source_id": b"source-\xff",
            "fromusr": b"wxid_\xff",
            "realchatname": b"chat_\xff",
        }
        for field, value in cases.items():
            with self.subTest(field=field), TemporaryDirectory() as td:
                account_dir = Path(td)
                db_path = account_dir / "favorite.db"
                self._seed_favorite_db(db_path)
                with closing(sqlite3.connect(str(db_path))) as conn, conn:
                    conn.execute(
                        f"UPDATE fav_db_item SET {field} = CAST(? AS TEXT) WHERE local_id = 2",
                        (value,),
                    )
                    self.assertEqual(conn.execute("PRAGMA quick_check").fetchone()[0], "ok")
                with _native_favorite_source(db_path) as source:
                    # 先证明夹具确实复现 issue 的原始异常，不能仅模拟上层返回值。
                    with self.assertRaisesRegex(wcdb_realtime.WCDBRealtimeError, "query text cell is not UTF-8"):
                        source.execute(f"SELECT {field} FROM fav_db_item WHERE local_id = 2")
                    response = self._call(account_dir, source="realtime")
                local = self._call(account_dir)
                self.assertEqual(response["items"], local["items"])
                self.assertEqual(response["dataSource"], "realtime")
                self.assertEqual(response["databaseTotal"], 2)
                self.assertEqual(response["items"][0]["textBlocks"], ["项目会议纪要\n第二行"])
                item = response["items"][1]
                if field == "content":
                    self.assertTrue(item["parsed"])
                    self.assertIn("hello\ufffdworld", item["textBlocks"])
                else:
                    output_field = {
                        "source_id": "sourceId",
                        "fromusr": "sourceUsername",
                        "realchatname": "sourceChatUsername",
                    }[field]
                    self.assertEqual(item[output_field], value.decode("utf-8", "replace"))

    def test_realtime_invalid_utf8_tag_is_preserved_and_filterable(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            db_path = account_dir / "favorite.db"
            self._seed_favorite_db(db_path)
            with closing(sqlite3.connect(str(db_path))) as conn, conn:
                conn.execute("UPDATE fav_tag_db_item SET name = CAST(? AS TEXT)", (b"tag-\xff",))
            with _native_favorite_source(db_path):
                response = self._call(account_dir, source="realtime", tag_id=7)
            self.assertEqual(response["total"], 1)
            self.assertEqual(response["tags"][0]["name"], "tag-\ufffd")
            self.assertEqual(response["items"][0]["tags"][0]["name"], "tag-\ufffd")

    def test_realtime_and_local_sources_return_the_same_normal_favorites(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            db_path = account_dir / "favorite.db"
            self._seed_favorite_db(db_path)
            local = self._call(account_dir)
            with _native_favorite_source(db_path):
                realtime = self._call(account_dir, source="realtime")
            for key in ("items", "tags", "typeCounts", "total", "databaseTotal"):
                self.assertEqual(realtime[key], local[key])

    def test_query_failure_is_not_misreported_as_unsupported_schema(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td)
            self._seed_favorite_db(account_dir / "favorite.db")
            source = MagicMock()
            source.__enter__.return_value = source
            source.execute.side_effect = wcdb_realtime.WCDBRealtimeError("query text cell is not UTF-8")
            with patch.object(favorites_router, "_open_db_source", return_value=source):
                with self.assertRaises(HTTPException) as caught:
                    self._call(account_dir, source="realtime")
            self.assertEqual(caught.exception.status_code, 500)
            self.assertNotIn("schema is not supported", caught.exception.detail)
            self.assertIn("query text cell is not UTF-8", caught.exception.detail)

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
