import importlib.util
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _contact(**fields):
    # username 用纯数字，避免字母关键词被 username 的普通子串匹配命中。
    contact = {
        "username": "10001",
        "displayName": "",
        "remark": "",
        "nickname": "",
        "alias": "",
        "region": "",
        "source": "",
        "country": "",
        "province": "",
        "city": "",
    }
    contact.update(fields)
    return contact


# (username, remark, nick_name, sort_timestamp)：字面命中的会话最旧，仅拼音命中的会话更新且多于 MCP 默认的 10 条。
_RANKED_ROWS = [
    ("wxid_n01", "", "Lily", 20),
    ("wxid_n02", "HR 小王", "王小明", 10),
    ("wxid_n03", "", "Bob", 0),
    *[
        (f"wxid_p{index:02d}", "", name, 1000 + index)
        for index, name in enumerate(
            ("李娜", "丽丽", "黎明", "立华", "林涛", "刘洋", "梁静", "廖凡", "凌风", "连胜", "力宏", "莉莉")
        )
    ],
    ("wxid_q01", "", "胡蓉", 2001),
    ("wxid_q02", "", "何瑞", 2000),
]
_RANKED_PINYIN_LI = [f"wxid_p{index:02d}" for index in range(11, -1, -1)]


def _write_account(account_dir, rows):
    account_dir.mkdir()
    conn = sqlite3.connect(str(account_dir / "contact.db"))
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
        conn.executemany(
            "INSERT INTO contact VALUES (?, ?, ?, '', 1, 0, '', '')",
            [row[:3] for row in rows],
        )
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(str(account_dir / "session.db"))
    try:
        conn.execute("CREATE TABLE SessionTable (username TEXT, sort_timestamp INTEGER)")
        conn.executemany("INSERT INTO SessionTable VALUES (?, ?)", [(row[0], row[3]) for row in rows])
        conn.commit()
    finally:
        conn.close()


@unittest.skipUnless(importlib.util.find_spec("pypinyin"), "pypinyin is not installed")
class TestContactsKeywordPinyin(unittest.TestCase):
    def assertMatches(self, contact, *keywords):
        from wechat_decrypt_tool.routers.chat_contacts import _matches_keyword

        for keyword in keywords:
            with self.subTest(keyword=keyword):
                self.assertTrue(_matches_keyword(contact, keyword))

    def assertNotMatches(self, contact, *keywords):
        from wechat_decrypt_tool.routers.chat_contacts import _matches_keyword

        for keyword in keywords:
            with self.subTest(keyword=keyword):
                self.assertFalse(_matches_keyword(contact, keyword))

    def test_initials_match(self):
        contact = _contact(displayName="张伟", nickname="张伟")
        self.assertMatches(contact, "zw", "z", "w", "ZW", " zw ")
        self.assertNotMatches(contact, "wz", "zz", "zwx", "h", "a", "g", "e")

    def test_full_pinyin_matches_only_at_syllable_boundaries(self):
        contact = _contact(displayName="张伟", nickname="张伟")
        self.assertMatches(contact, "zhang", "zhangw", "zhangwei", "zha", "wei", "we", "ZhangWei")
        self.assertNotMatches(contact, "an", "hang", "ang", "angwei", "gw", "ei", "zhangweii", "weizhang")

    def test_remark_and_nickname_are_both_searchable(self):
        contact = _contact(displayName="老板", remark="老板", nickname="张伟")
        self.assertMatches(contact, "lb", "laoban", "zw", "zhangwei")

        only_display_name = _contact(displayName="相亲相爱一家人")
        self.assertMatches(only_display_name, "xqxa", "yjr", "xiangqin", "qinxiangai", "yijiaren")
        self.assertNotMatches(only_display_name, "iang", "inxiangai")

    def test_mixed_chinese_and_latin_names(self):
        self.assertMatches(_contact(displayName="A张伟"), "azw", "azhangwei", "zw", "zhangw")
        self.assertNotMatches(_contact(displayName="A张伟"), "azhw", "aw", "ab")

        self.assertMatches(_contact(displayName="张伟Bob"), "zwb", "zwbob", "weibob", "zhangweib")
        self.assertMatches(_contact(displayName="Lily妈妈"), "lilymm", "lilymama", "mm", "mama")
        self.assertNotMatches(_contact(displayName="Lily妈妈"), "lilyam", "am")

        # 空格、标点、表情、数字不参与拼音匹配，也不会隔断前后的字。
        self.assertMatches(_contact(displayName="张伟(公司)"), "zwgs", "gs", "gongsi", "weigong")
        self.assertMatches(_contact(displayName="张 伟🎉"), "zw", "zhangwei")
        self.assertMatches(_contact(displayName="王5哥"), "wg", "wangge", "5")
        self.assertMatches(_contact(displayName="A1张伟"), "azw", "a1")

    def test_names_without_chinese_keep_plain_substring_matching(self):
        # 不含汉字的名称即使带表情、标点或重音字母，也不会因为去掉分隔符而变宽松。
        for name in ("Li Wei", "Li Wei🌸", "John Smith 🎉", "José García", "Mr.Li🌙"):
            contact = _contact(displayName=name, nickname=name)
            self.assertNotMatches(contact, "liwei", "lw", "iw", "hns", "ns", "js", "garca", "sg", "rl")
        self.assertMatches(_contact(displayName="Li Wei🌸"), "li wei", "wei")
        self.assertMatches(_contact(displayName="José García"), "garc", "jos")

    def test_polyphone_readings(self):
        # 词语读音由 pypinyin 按词典消歧：重庆是 chong qing 而不是 zhong qing。
        chongqing = _contact(displayName="重庆客户")
        self.assertMatches(chongqing, "cq", "cqkh", "chongqing", "chongqingkehu")
        self.assertNotMatches(chongqing, "zq", "zhongqing")

        # 多音字姓氏按姓氏读音命中，与列表里的拼音分组一致。
        self.assertMatches(_contact(displayName="曾国藩"), "zgf", "zengguofan", "zeng")
        self.assertMatches(_contact(displayName="单田芳"), "stf", "shantianfang")

        # 首字不是姓氏用法时，默认读音仍可命中。
        self.assertMatches(_contact(displayName="乐乐"), "ll", "lele")
        self.assertMatches(_contact(displayName="单车少年"), "dcsn", "danche")

    def test_u_umlaut_syllables(self):
        # pypinyin 把 ü 记作 v：lüe / nüe 同时接受 lue / nue 拼法。
        self.assertMatches(_contact(displayName="侵略者"), "qlz", "qinlve", "qinlue", "lvezhe", "luezhe")
        self.assertMatches(_contact(displayName="虐心"), "nx", "nvexin", "nuexin")
        self.assertMatches(_contact(displayName="曾略"), "zl", "zenglue", "zenglve", "cenglue")
        # lü / nü 与输入法一致，只接受 lv / nv。
        self.assertMatches(_contact(displayName="吕布"), "lb", "lv", "lvbu")
        self.assertNotMatches(_contact(displayName="吕布"), "lu", "lubu")

    def test_non_letter_keywords_are_not_pinyin_matched(self):
        contact = _contact(displayName="张伟", nickname="张伟")
        self.assertNotMatches(contact, "zw1", "z w", "zhang wei", "zw_", "z.w", "张w", "张wei", "9", "_")
        self.assertMatches(contact, "张", "伟", "张伟")
        self.assertNotMatches(contact, "李", "伟张")

    def test_only_name_fields_are_pinyin_matched(self):
        contact = _contact(
            displayName="Bob",
            nickname="Bob",
            region="中国大陆·北京",
            country="中国大陆",
            province="北京",
            city="海淀",
            source="通过扫一扫添加",
        )
        self.assertMatches(contact, "北京", "海淀", "扫一扫", "bob")
        self.assertNotMatches(contact, "bj", "beijing", "hd", "haidian", "sys", "zgdl")

    def test_existing_substring_matching_is_unchanged(self):
        contact = _contact(
            username="wxid_Abc01",
            displayName="三哥",
            remark="三哥",
            nickname="Zhang San",
            alias="ZS_Alias",
            region="中国大陆·四川·成都",
            source="通过搜索微信号添加",
        )
        self.assertMatches(
            contact,
            "",
            None,
            "   ",
            "wxid_abc",
            "ABC01",
            "三",
            "zhang san",
            "ang s",
            "zs_alias",
            "s_al",
            "成都",
            "微信号",
        )
        # 纯 ASCII 名称仍只做普通子串匹配，不会因拼音逻辑变宽松。
        self.assertNotMatches(contact, "zhangsan", "zs1", "wxid_san", "重庆")

    def test_pinyin_conversion_is_cached_per_name(self):
        from wechat_decrypt_tool.routers import chat_contacts

        # 每次运行使用新的名称，保证断言不受进程内已有缓存影响。
        suffix = uuid.uuid4().hex
        remark, nickname = f"缓存备注{suffix}", f"缓存昵称{suffix}"
        contact = _contact(displayName=remark, remark=remark, nickname=nickname)
        with patch.object(chat_contacts, "lazy_pinyin", wraps=chat_contacts.lazy_pinyin) as spy:
            for keyword in ("hcbz", "huancun", "nicheng", "qq", "zzz"):
                chat_contacts._matches_keyword(contact, keyword)
                chat_contacts._matches_keyword(dict(contact), keyword)

        converted = sorted(call.args[0] for call in spy.call_args_list)
        self.assertEqual(converted, sorted([remark, nickname]))

    def test_pinyin_conversion_is_skipped_when_it_cannot_help(self):
        from wechat_decrypt_tool.routers import chat_contacts

        contact = _contact(displayName="免转换专用名", remark="免转换专用名", nickname="Plain Ascii", alias="mzh_alias")
        with patch.object(
            chat_contacts,
            "lazy_pinyin",
            side_effect=AssertionError("unexpected pinyin conversion"),
        ) as spy:
            # 非 ASCII / 含非字母字符的关键词。
            self.assertTrue(chat_contacts._matches_keyword(contact, "专用"))
            self.assertFalse(chat_contacts._matches_keyword(contact, "李"))
            self.assertFalse(chat_contacts._matches_keyword(contact, "mzh1"))
            self.assertFalse(chat_contacts._matches_keyword(contact, "m z"))
            # 普通字段已命中的字母关键词。
            self.assertTrue(chat_contacts._matches_keyword(contact, "mzh"))
            self.assertTrue(chat_contacts._matches_keyword(contact, "ascii"))
            # 名称全是 ASCII 的联系人。
            ascii_contact = _contact(displayName="Plain Ascii", nickname="Plain Ascii")
            self.assertFalse(chat_contacts._matches_keyword(ascii_contact, "pa"))

        spy.assert_not_called()

    def test_contacts_api_filters_by_pinyin_keyword(self):
        from wechat_decrypt_tool.routers import chat_contacts

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            _write_account(
                account_dir,
                [
                    ("wxid_a1", "", "张伟", 0),
                    ("wxid_b2", "重庆客户", "李娜", 0),
                    ("wxid_c3", "", "Bob", 0),
                    ("11@chatroom", "", "相亲相爱一家人", 0),
                ],
            )

            def search(keyword):
                with patch.object(chat_contacts, "_resolve_account_dir", return_value=account_dir):
                    payload = chat_contacts.list_chat_contacts(
                        SimpleNamespace(base_url="http://test/"),
                        account="wxid_account",
                        source="decrypted",
                        keyword=keyword,
                    )
                self.assertEqual(payload["total"], len(payload["contacts"]))
                return sorted(item["username"] for item in payload["contacts"])

            self.assertEqual(search(None), ["11@chatroom", "wxid_a1", "wxid_b2", "wxid_c3"])
            self.assertEqual(search("zw"), ["wxid_a1"])
            self.assertEqual(search("zhangw"), ["wxid_a1"])
            self.assertEqual(search("wei"), ["wxid_a1"])
            self.assertEqual(search("cq"), ["wxid_b2"])
            self.assertEqual(search("ln"), ["wxid_b2"])
            self.assertEqual(search("yijiaren"), ["11@chatroom"])
            self.assertEqual(search("bob"), ["wxid_c3"])
            self.assertEqual(search("张"), ["wxid_a1"])
            self.assertEqual(search("an"), [])
            self.assertEqual(search("hang"), [])
            self.assertEqual(search("zw1"), [])

    def test_literal_matches_are_listed_before_pinyin_only_matches(self):
        from wechat_decrypt_tool.routers import chat_contacts

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            _write_account(account_dir, _RANKED_ROWS)

            def search(keyword):
                with patch.object(chat_contacts, "_resolve_account_dir", return_value=account_dir):
                    payload = chat_contacts.list_chat_contacts(
                        SimpleNamespace(base_url="http://test/"),
                        account="wxid_account",
                        source="decrypted",
                        keyword=keyword,
                    )
                return [item["username"] for item in payload["contacts"]]

            # 字面命中的联系人会话再旧也排在仅拼音命中的之前，其余仍按最近会话排序。
            self.assertEqual(search("li"), ["wxid_n01", *_RANKED_PINYIN_LI])
            self.assertEqual(search("hr"), ["wxid_n02", "wxid_q01", "wxid_q02"])
            # 没有拼音命中参与时，顺序与原来一致（只按最近会话）。
            self.assertEqual(search("小王"), ["wxid_n02"])
            self.assertEqual(
                search(None),
                ["wxid_q01", "wxid_q02", *_RANKED_PINYIN_LI, "wxid_n01", "wxid_n02", "wxid_n03"],
            )

    def test_realtime_literal_matches_are_listed_before_pinyin_only_matches(self):
        from wechat_decrypt_tool.routers import chat_contacts

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        contact_rows = [
            {"username": username, "remark": remark, "nick_name": nick_name, "local_type": 1, "flag": 0}
            for username, remark, nick_name, _ in _RANKED_ROWS
        ]
        sessions = [{"username": row[0], "sort_timestamp": row[3]} for row in _RANKED_ROWS]

        def search(keyword):
            with (
                patch.object(
                    chat_contacts.WCDB_REALTIME,
                    "ensure_connected",
                    return_value=SimpleNamespace(handle=1, lock=DummyLock()),
                ),
                patch.object(chat_contacts, "_wcdb_get_sessions", return_value=sessions),
                patch.object(chat_contacts, "_query_realtime_contact_rows", return_value=contact_rows),
                patch.object(chat_contacts, "_query_realtime_official_account_type_map", return_value={}),
                patch.object(chat_contacts, "_query_realtime_enterprise_group_usernames", return_value=set()),
                patch.object(chat_contacts, "_wcdb_get_display_names", return_value={}),
                patch.object(chat_contacts, "_wcdb_get_avatar_urls", return_value={}),
            ):
                contacts = chat_contacts._collect_contacts_for_account_realtime(
                    account_dir=Path("account"),
                    base_url="http://test",
                    keyword=keyword,
                    include_friends=True,
                    include_groups=True,
                    include_officials=True,
                )
            return [item["username"] for item in contacts]

        self.assertEqual(search("li"), ["wxid_n01", *_RANKED_PINYIN_LI])
        self.assertEqual(search("hr"), ["wxid_n02", "wxid_q01", "wxid_q02"])
        self.assertEqual(
            search(None),
            ["wxid_q01", "wxid_q02", *_RANKED_PINYIN_LI, "wxid_n01", "wxid_n02", "wxid_n03"],
        )

    def test_mcp_resolve_contact_keeps_literal_match_ahead_of_pinyin_matches(self):
        from wechat_decrypt_tool.mcp import tools
        from wechat_decrypt_tool.mcp.registry import McpToolContext
        from wechat_decrypt_tool.routers import chat_contacts

        ctx = McpToolContext(request=SimpleNamespace(base_url="http://test/"))
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_account"
            _write_account(account_dir, _RANKED_ROWS)

            def resolve(query, **extra):
                args = {"account": "wxid_account", "source": "decrypted", "query": query, **extra}
                with patch.object(chat_contacts, "_resolve_account_dir", return_value=account_dir):
                    return [item["username"] for item in tools._resolve_contact(args, ctx)["candidates"]]

            # 默认只取 10 条：比字面命中更新的 12 个拼音命中不能把 Lily 挤出结果。
            usernames = resolve("li")
            self.assertEqual(len(usernames), 10)
            self.assertEqual(usernames[0], "wxid_n01")
            self.assertLessEqual(set(usernames[1:]), set(_RANKED_PINYIN_LI))
            self.assertEqual(resolve("li", limit=1), ["wxid_n01"])

            usernames = resolve("hr")
            self.assertEqual(usernames[0], "wxid_n02")
            self.assertEqual(set(usernames[1:]), {"wxid_q01", "wxid_q02"})


if __name__ == "__main__":
    unittest.main()
