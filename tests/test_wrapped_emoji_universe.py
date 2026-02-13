import hashlib
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedEmojiUniverse(unittest.TestCase):
    def _ts(self, y: int, m: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> int:
        return int(datetime(y, m, d, h, mi, s).timestamp())

    def _seed_contact_db(self, path: Path, *, account: str, usernames: list[str]) -> None:
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
                (account, "", "我", "", 1, 0, "", ""),
            )
            for idx, username in enumerate(usernames):
                conn.execute(
                    "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (username, "", f"好友{idx + 1}", "", 1, 0, "", ""),
                )
            conn.commit()
        finally:
            conn.close()

    def _seed_session_db(self, path: Path, *, usernames: list[str]) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE SessionTable (
                    username TEXT,
                    is_hidden INTEGER,
                    sort_timestamp INTEGER
                )
                """
            )
            for username in usernames:
                conn.execute("INSERT INTO SessionTable VALUES (?, ?, ?)", (username, 0, 1735689600))
            conn.commit()
        finally:
            conn.close()

    def _seed_message_db(
        self,
        path: Path,
        *,
        account: str,
        username: str,
        rows: list[dict[str, object]],
    ) -> None:
        table_name = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (1, account))
            conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (2, username))
            conn.execute(
                f"""
                CREATE TABLE {table_name} (
                    local_id INTEGER,
                    server_id INTEGER,
                    local_type INTEGER,
                    sort_seq INTEGER,
                    real_sender_id INTEGER,
                    create_time INTEGER,
                    message_content TEXT,
                    compress_content BLOB,
                    packed_info_data BLOB
                )
                """
            )
            for row in rows:
                conn.execute(
                    f"""
                    INSERT INTO {table_name}
                    (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content, packed_info_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(row.get("local_id", 0)),
                        int(row.get("server_id", 0)),
                        int(row.get("local_type", 0)),
                        int(row.get("sort_seq", row.get("local_id", 0))),
                        int(row.get("real_sender_id", 1)),
                        int(row.get("create_time", 0)),
                        str(row.get("message_content", "")),
                        row.get("compress_content"),
                        row.get("packed_info_data"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _seed_index_db(self, path: Path, *, rows: list[dict[str, object]]) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE message_fts (
                    text TEXT,
                    username TEXT,
                    render_type TEXT,
                    create_time INTEGER,
                    sort_seq INTEGER,
                    local_id INTEGER,
                    server_id INTEGER,
                    local_type INTEGER,
                    db_stem TEXT,
                    table_name TEXT,
                    sender_username TEXT,
                    is_hidden INTEGER,
                    is_official INTEGER
                )
                """
            )
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO message_fts (
                        text, username, render_type, create_time, sort_seq, local_id, server_id, local_type,
                        db_stem, table_name, sender_username, is_hidden, is_official
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(row.get("text", "")),
                        str(row.get("username", "")),
                        str(row.get("render_type", "")),
                        int(row.get("create_time", 0)),
                        int(row.get("sort_seq", 0)),
                        int(row.get("local_id", 0)),
                        int(row.get("server_id", 0)),
                        int(row.get("local_type", 0)),
                        str(row.get("db_stem", "message_0")),
                        str(row.get("table_name", "")),
                        str(row.get("sender_username", "")),
                        int(row.get("is_hidden", 0)),
                        int(row.get("is_official", 0)),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _seed_resource_db(
        self,
        path: Path,
        *,
        username: str,
        md5: str,
        server_id: int,
        local_id: int,
        create_time: int,
    ) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE ChatName2Id (user_name TEXT)")
            conn.execute("INSERT INTO ChatName2Id (rowid, user_name) VALUES (?, ?)", (7, username))
            conn.execute(
                """
                CREATE TABLE MessageResourceInfo (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_svr_id INTEGER,
                    chat_id INTEGER,
                    message_local_type INTEGER,
                    packed_info BLOB,
                    message_local_id INTEGER,
                    message_create_time INTEGER
                )
                """
            )
            packed = f"/tmp/{md5}.dat".encode("utf-8")
            conn.execute(
                """
                INSERT INTO MessageResourceInfo
                (message_svr_id, chat_id, message_local_type, packed_info, message_local_id, message_create_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(server_id), 7, 47, packed, int(local_id), int(create_time)),
            )
            conn.commit()
        finally:
            conn.close()

    def test_only_sticker_messages_outputs_core_stats(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_a"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            md5_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            md5_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            rows = [
                {
                    "local_id": 1,
                    "server_id": 1001,
                    "local_type": 47,
                    "create_time": self._ts(2025, 1, 1, 10, 5, 0),
                    "message_content": f'<msg><emoji md5="{md5_a}" cdnurl="http://cdn/a.gif"/></msg>',
                },
                {
                    "local_id": 2,
                    "server_id": 1002,
                    "local_type": 47,
                    "create_time": self._ts(2025, 1, 1, 10, 30, 0),
                    "message_content": f'<msg><emoji md5="{md5_a}" cdnurl="http://cdn/a2.gif"/></msg>',
                },
                {
                    "local_id": 3,
                    "server_id": 1003,
                    "local_type": 47,
                    "create_time": self._ts(2025, 1, 2, 22, 10, 0),
                    "message_content": f'<msg><emoji md5="{md5_b}" cdnurl="http://cdn/b.gif"/></msg>',
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, username=friend, rows=rows)

            table_name = f"msg_{hashlib.md5(friend.encode('utf-8')).hexdigest()}"
            fts_rows = []
            for row in rows:
                fts_rows.append(
                    {
                        "text": "[表情]",
                        "username": friend,
                        "render_type": "emoji",
                        "create_time": row["create_time"],
                        "sort_seq": row["local_id"],
                        "local_id": row["local_id"],
                        "server_id": row["server_id"],
                        "local_type": 47,
                        "db_stem": "message_0",
                        "table_name": table_name,
                        "sender_username": account,
                    }
                )
            self._seed_index_db(account_dir / "chat_search_index.db", rows=fts_rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)

            self.assertTrue(data["settings"]["usedIndex"])
            self.assertEqual(data["sentStickerCount"], 3)
            self.assertEqual(data["peakHour"], 10)
            self.assertIsNotNone(data["peakWeekday"])
            self.assertEqual(data["topBattlePartner"]["username"], friend)
            self.assertEqual(data["topBattlePartner"]["stickerCount"], 3)
            self.assertEqual(data["topBattlePartner"]["maskedName"], data["topBattlePartner"]["displayName"])
            self.assertEqual(data["topStickers"][0]["md5"], md5_a)
            self.assertEqual(data["topStickers"][0]["count"], 2)
            self.assertTrue(str(data["topStickers"][0].get("sampleDisplayName") or "").strip())
            self.assertTrue(str(data["topStickers"][0].get("sampleAvatarUrl") or "").startswith("/api/chat/avatar"))

    def test_fallback_to_resource_md5_when_xml_missing(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_b"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            ts = self._ts(2025, 3, 8, 21, 0, 0)
            rows = [
                {
                    "local_id": 11,
                    "server_id": 220011,
                    "local_type": 47,
                    "create_time": ts,
                    "message_content": '<msg><emoji cdnurl="http://cdn/no_md5.gif"/></msg>',
                }
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, username=friend, rows=rows)

            md5_fallback = "cccccccccccccccccccccccccccccccc"
            self._seed_resource_db(
                account_dir / "message_resource.db",
                username=friend,
                md5=md5_fallback,
                server_id=220011,
                local_id=11,
                create_time=ts,
            )

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)

            self.assertFalse(data["settings"]["usedIndex"])
            self.assertEqual(data["sentStickerCount"], 1)
            self.assertEqual(data["topStickers"][0]["md5"], md5_fallback)
            self.assertEqual(data["topStickers"][0]["count"], 1)

    def test_text_emoji_mapping_from_wechat_emojis_ts(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_c"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            table_name = f"msg_{hashlib.md5(friend.encode('utf-8')).hexdigest()}"
            fts_rows = [
                {
                    "text": "早上好[微笑][微笑]🙂🙂",
                    "username": friend,
                    "render_type": "text",
                    "create_time": self._ts(2025, 4, 1, 9, 0, 0),
                    "local_id": 1,
                    "server_id": 901,
                    "local_type": 1,
                    "db_stem": "message_0",
                    "table_name": table_name,
                    "sender_username": account,
                },
                {
                    "text": "晚上见[微笑][发呆]😂",
                    "username": friend,
                    "render_type": "text",
                    "create_time": self._ts(2025, 4, 1, 22, 0, 0),
                    "local_id": 2,
                    "server_id": 902,
                    "local_type": 1,
                    "db_stem": "message_0",
                    "table_name": table_name,
                    "sender_username": account,
                },
            ]
            self._seed_index_db(account_dir / "chat_search_index.db", rows=fts_rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)
            self.assertTrue(data["settings"]["usedIndex"])
            self.assertGreaterEqual(len(data["topTextEmojis"]), 1)
            self.assertEqual(data["topTextEmojis"][0]["key"], "[微笑]")
            self.assertEqual(data["topTextEmojis"][0]["count"], 3)
            self.assertTrue(data["topTextEmojis"][0]["assetPath"].endswith("Expression_1@2x.png"))
            self.assertGreaterEqual(len(data["topUnicodeEmojis"]), 1)
            self.assertEqual(data["topUnicodeEmojis"][0]["emoji"], "🙂")
            self.assertEqual(data["topUnicodeEmojis"][0]["count"], 2)

    def test_wechat_builtin_emoji_from_packed_info_data(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_e"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            # packed_info_data protobuf varints:
            # 08 04 => field#1=4
            # 10 33 => field#2=51 (Expression_51@2x)
            rows = [
                {
                    "local_id": 1,
                    "server_id": 501,
                    "local_type": 47,
                    "create_time": self._ts(2025, 7, 1, 10, 0, 0),
                    "message_content": "binary_emoji_payload_a",
                    "packed_info_data": bytes.fromhex("08041033"),
                },
                {
                    "local_id": 2,
                    "server_id": 502,
                    "local_type": 47,
                    "create_time": self._ts(2025, 7, 1, 10, 1, 0),
                    "message_content": "binary_emoji_payload_b",
                    "packed_info_data": bytes.fromhex("08041033"),
                },
                {
                    "local_id": 3,
                    "server_id": 503,
                    "local_type": 47,
                    "create_time": self._ts(2025, 7, 1, 11, 0, 0),
                    "message_content": "binary_emoji_payload_c",
                    "packed_info_data": bytes.fromhex("0804104a"),
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, username=friend, rows=rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)

            self.assertFalse(data["settings"]["usedIndex"])
            self.assertEqual(data["sentStickerCount"], 3)
            self.assertGreaterEqual(len(data["topWechatEmojis"]), 1)
            self.assertEqual(data["topWechatEmojis"][0]["id"], 51)
            self.assertEqual(data["topWechatEmojis"][0]["count"], 2)
            self.assertTrue(data["topWechatEmojis"][0]["assetPath"].endswith("Expression_51@2x.png"))
            self.assertGreaterEqual(len(data["topStickers"]), 1)
            self.assertEqual(data["topStickers"][0]["emojiId"], 51)
            self.assertEqual(data["topStickers"][0]["count"], 2)
            self.assertTrue(str(data["topStickers"][0].get("emojiAssetPath") or "").endswith("Expression_51@2x.png"))

    def test_index_counts_only_sent_messages(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_sent_only"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            rows = [
                {
                    "text": "[ 微 笑 ]",
                    "username": friend,
                    "render_type": "text",
                    "create_time": self._ts(2025, 6, 2, 9, 0, 0),
                    "local_id": 101,
                    "server_id": 4001,
                    "local_type": 1,
                    "table_name": "msg_dummy",
                    "sender_username": account,
                },
                {
                    "text": "[ 发 呆 ]",
                    "username": friend,
                    "render_type": "text",
                    "create_time": self._ts(2025, 6, 2, 9, 1, 0),
                    "local_id": 102,
                    "server_id": 4002,
                    "local_type": 1,
                    "table_name": "msg_dummy",
                    "sender_username": friend,
                },
                {
                    "text": "[表情]",
                    "username": friend,
                    "render_type": "emoji",
                    "create_time": self._ts(2025, 6, 2, 9, 2, 0),
                    "local_id": 201,
                    "server_id": 5001,
                    "local_type": 47,
                    "table_name": "msg_dummy",
                    "sender_username": account,
                },
                {
                    "text": "[表情]",
                    "username": friend,
                    "render_type": "emoji",
                    "create_time": self._ts(2025, 6, 2, 9, 3, 0),
                    "local_id": 202,
                    "server_id": 5002,
                    "local_type": 47,
                    "table_name": "msg_dummy",
                    "sender_username": friend,
                },
            ]
            self._seed_index_db(account_dir / "chat_search_index.db", rows=rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)
            self.assertTrue(data["settings"]["usedIndex"])

            self.assertEqual(data["sentStickerCount"], 1)

            keys = {x.get("key") for x in data.get("topTextEmojis") or []}
            self.assertIn("[微笑]", keys)
            self.assertNotIn("[发呆]", keys)

    def test_raw_db_counts_only_sent_messages(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_raw_dir"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            rows = [
                {
                    "local_id": 1,
                    "server_id": 1001,
                    "local_type": 1,
                    "real_sender_id": 1,
                    "create_time": self._ts(2025, 7, 1, 8, 0, 0),
                    "message_content": "/::B",
                },
                {
                    "local_id": 2,
                    "server_id": 1002,
                    "local_type": 1,
                    "real_sender_id": 2,
                    "create_time": self._ts(2025, 7, 1, 8, 1, 0),
                    "message_content": "/::B",
                },
                {
                    "local_id": 3,
                    "server_id": 1101,
                    "local_type": 47,
                    "real_sender_id": 1,
                    "create_time": self._ts(2025, 7, 1, 9, 0, 0),
                    "message_content": "binary_emoji_payload_a",
                    "packed_info_data": bytes.fromhex("08031033"),
                },
                {
                    "local_id": 4,
                    "server_id": 1102,
                    "local_type": 47,
                    "real_sender_id": 2,
                    "create_time": self._ts(2025, 7, 1, 9, 1, 0),
                    "message_content": "binary_emoji_payload_b",
                    "packed_info_data": bytes.fromhex("08031033"),
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, username=friend, rows=rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)

            self.assertFalse(data["settings"]["usedIndex"])
            self.assertEqual(data["sentStickerCount"], 1)
            self.assertEqual(data["topWechatEmojis"][0]["id"], 51)
            self.assertEqual(data["topWechatEmojis"][0]["count"], 1)

            self.assertGreaterEqual(len(data["topTextEmojis"]), 1)
            self.assertEqual(data["topTextEmojis"][0]["key"], "[色]")
            self.assertEqual(data["topTextEmojis"][0]["count"], 1)
            self.assertTrue(data["topTextEmojis"][0]["assetPath"].endswith("Expression_3@2x.png"))

    def test_new_and_revived_sticker_metrics(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_new_revived"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            md5_revived = "dddddddddddddddddddddddddddddddd"
            md5_recent = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
            md5_new = "ffffffffffffffffffffffffffffffff"
            rows = [
                {
                    "local_id": 1,
                    "server_id": 5001,
                    "local_type": 47,
                    "create_time": self._ts(2024, 1, 1, 9, 0, 0),
                    "message_content": f'<msg><emoji md5="{md5_revived}" /></msg>',
                },
                {
                    "local_id": 2,
                    "server_id": 5002,
                    "local_type": 47,
                    "create_time": self._ts(2024, 12, 28, 10, 0, 0),
                    "message_content": f'<msg><emoji md5="{md5_recent}" /></msg>',
                },
                {
                    "local_id": 3,
                    "server_id": 5003,
                    "local_type": 47,
                    "create_time": self._ts(2025, 1, 5, 11, 0, 0),
                    "message_content": f'<msg><emoji md5="{md5_recent}" /></msg>',
                },
                {
                    "local_id": 4,
                    "server_id": 5004,
                    "local_type": 47,
                    "create_time": self._ts(2025, 3, 15, 12, 0, 0),
                    "message_content": f'<msg><emoji md5="{md5_revived}" /></msg>',
                },
                {
                    "local_id": 5,
                    "server_id": 5005,
                    "local_type": 47,
                    "create_time": self._ts(2025, 5, 10, 13, 0, 0),
                    "message_content": f'<msg><emoji md5="{md5_new}" /></msg>',
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, username=friend, rows=rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)

            self.assertEqual(data["sentStickerCount"], 3)
            self.assertEqual(data["uniqueStickerTypeCount"], 3)
            self.assertEqual(data["newStickerCountThisYear"], 1)
            self.assertEqual(data["revivedStickerCount"], 1)
            self.assertEqual(data["revivedMinGapDays"], 60)
            self.assertGreaterEqual(int(data.get("revivedMaxGapDays") or 0), 400)
            new_samples = list(data.get("newStickerSamples") or [])
            revived_samples = list(data.get("revivedStickerSamples") or [])
            self.assertTrue(any(str(x.get("md5") or "") == md5_new for x in new_samples))
            self.assertTrue(any(str(x.get("md5") or "") == md5_revived for x in revived_samples))
            revived_item = next((x for x in revived_samples if str(x.get("md5") or "") == md5_revived), {})
            self.assertGreaterEqual(int(revived_item.get("gapDays") or 0), 400)

    def test_empty_year_returns_safe_empty_state(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import build_card_04_emoji_universe

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)
            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[])
            self._seed_session_db(account_dir / "session.db", usernames=[])

            card = build_card_04_emoji_universe(account_dir=account_dir, year=2025)
            self.assertEqual(card["id"], 4)
            self.assertEqual(card["status"], "ok")
            self.assertEqual(card["data"]["sentStickerCount"], 0)
            self.assertIn("几乎没用表情表达", card["narrative"])
            self.assertIsInstance(card["data"]["lines"], list)
            self.assertGreaterEqual(len(card["data"]["lines"]), 1)
            self.assertEqual(card["data"].get("topUnicodeEmojis"), [])

    def test_tie_break_is_stable_by_key(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_emoji_universe import compute_emoji_universe_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_d"
            account_dir = root / account
            account_dir.mkdir(parents=True, exist_ok=True)

            self._seed_contact_db(account_dir / "contact.db", account=account, usernames=[friend])
            self._seed_session_db(account_dir / "session.db", usernames=[friend])

            md5_a = "11111111111111111111111111111111"
            md5_b = "22222222222222222222222222222222"
            rows = [
                {
                    "local_id": 1,
                    "server_id": 301,
                    "local_type": 47,
                    "create_time": self._ts(2025, 6, 1, 8, 0, 0),
                    "message_content": f'<msg><emoji md5="{md5_a}" /></msg>',
                },
                {
                    "local_id": 2,
                    "server_id": 302,
                    "local_type": 47,
                    "create_time": self._ts(2025, 6, 1, 8, 1, 0),
                    "message_content": f'<msg><emoji md5="{md5_b}" /></msg>',
                },
                {
                    "local_id": 3,
                    "server_id": 303,
                    "local_type": 47,
                    "create_time": self._ts(2025, 6, 1, 8, 2, 0),
                    "message_content": f'<msg><emoji md5="{md5_a}" /></msg>',
                },
                {
                    "local_id": 4,
                    "server_id": 304,
                    "local_type": 47,
                    "create_time": self._ts(2025, 6, 1, 8, 3, 0),
                    "message_content": f'<msg><emoji md5="{md5_b}" /></msg>',
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, username=friend, rows=rows)

            table_name = f"msg_{hashlib.md5(friend.encode('utf-8')).hexdigest()}"
            fts_rows = []
            for row in rows:
                fts_rows.append(
                    {
                        "text": "[表情]",
                        "username": friend,
                        "render_type": "emoji",
                        "create_time": row["create_time"],
                        "local_id": row["local_id"],
                        "server_id": row["server_id"],
                        "local_type": 47,
                        "db_stem": "message_0",
                        "table_name": table_name,
                        "sender_username": account,
                    }
                )
            fts_rows.extend(
                [
                    {
                        # `chat_search_index` stores text as char-tokens: "[微笑][发呆]" -> "[ 微 笑 ] [ 发 呆 ]"
                        "text": "[ 微 笑 ] [ 发 呆 ]",
                        "username": friend,
                        "render_type": "text",
                        "create_time": self._ts(2025, 6, 2, 9, 0, 0),
                        "local_id": 101,
                        "server_id": 4001,
                        "local_type": 1,
                        "db_stem": "message_0",
                        "table_name": table_name,
                        "sender_username": account,
                    },
                    {
                        "text": "[ 发 呆 ] [ 微 笑 ]",
                        "username": friend,
                        "render_type": "text",
                        "create_time": self._ts(2025, 6, 2, 9, 1, 0),
                        "local_id": 102,
                        "server_id": 4002,
                        "local_type": 1,
                        "db_stem": "message_0",
                        "table_name": table_name,
                        "sender_username": account,
                    },
                ]
            )
            self._seed_index_db(account_dir / "chat_search_index.db", rows=fts_rows)

            data = compute_emoji_universe_stats(account_dir=account_dir, year=2025)

            self.assertEqual(data["topStickers"][0]["md5"], md5_a)
            expected_emoji_key = sorted(["[微笑]", "[发呆]"])[0]
            self.assertEqual(data["topTextEmojis"][0]["key"], expected_emoji_key)


if __name__ == "__main__":
    unittest.main()
