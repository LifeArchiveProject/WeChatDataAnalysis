import hashlib
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _voice_xml(voicelength: str) -> str:
    return f'<msg><voicemsg endflag="1" length="1024" voicelength="{voicelength}" fromusername="wxid_x" /></msg>'


def _voip_xml(*, room_type: str, msg: str) -> str:
    return (
        '<msg><voipmsg type="VoIPBubbleMsg"><VoIPBubbleMsg>'
        "<roomid>42</roomid>"
        f"<msg><![CDATA[{msg}]]></msg>"
        f"<room_type>{room_type}</room_type>"
        "</VoIPBubbleMsg></voipmsg></msg>"
    )


class TestWrappedMessageCharsVoiceCalls(unittest.TestCase):
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
        rows_by_username: dict[str, list[dict[str, object]]],
        include_account_in_name2id: bool = True,
    ) -> None:
        """
        为每个会话 username 建一张 msg_<md5(username)> 表。

        行内用 direction: "sent"/"received" 表达方向：
        - sent -> real_sender_id = 1（account 在 Name2Id 的 rowid）
        - received -> real_sender_id = 该会话好友的 rowid
        """
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
            if include_account_in_name2id:
                conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (1, account))
            for idx, (username, rows) in enumerate(rows_by_username.items()):
                friend_rowid = idx + 2
                conn.execute("INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)", (friend_rowid, username))
                table_name = f"msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
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
                        compress_content BLOB
                    )
                    """
                )
                for row in rows:
                    direction = str(row.get("direction", "sent"))
                    real_sender_id = 1 if direction == "sent" else friend_rowid
                    conn.execute(
                        f"""
                        INSERT INTO {table_name}
                        (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(row.get("local_id", 0)),
                            int(row.get("server_id", 0)),
                            int(row.get("local_type", 0)),
                            int(row.get("sort_seq", row.get("local_id", 0))),
                            int(real_sender_id),
                            int(row.get("create_time", 0)),
                            str(row.get("message_content", "")),
                            row.get("compress_content"),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def _make_account_dir(self, root: Path, *, account: str, usernames: list[str]) -> Path:
        account_dir = root / account
        account_dir.mkdir(parents=True, exist_ok=True)
        self._seed_contact_db(account_dir / "contact.db", account=account, usernames=usernames)
        self._seed_session_db(account_dir / "session.db", usernames=usernames)
        return account_dir

    def test_voicelength_ms_and_seconds_units_with_direction(self):
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import compute_voice_call_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_voice"
            account_dir = self._make_account_dir(root, account=account, usernames=[friend])

            rows = [
                {
                    # 毫秒口径：6080ms -> 6s
                    "local_id": 1,
                    "local_type": 34,
                    "direction": "sent",
                    "create_time": self._ts(2025, 3, 1, 10, 0, 0),
                    "message_content": _voice_xml("6080"),
                },
                {
                    # 秒口径防御：45 -> 45s（且 create_time 为毫秒，验证毫秒/秒防御）
                    "local_id": 2,
                    "local_type": 34,
                    "direction": "sent",
                    "create_time": self._ts(2025, 3, 2, 11, 0, 0) * 1000,
                    "message_content": _voice_xml("45"),
                },
                {
                    # 对方发来的语音：12000ms -> 12s
                    "local_id": 3,
                    "local_type": 34,
                    "direction": "received",
                    "create_time": self._ts(2025, 3, 3, 12, 0, 0),
                    "message_content": _voice_xml("12000"),
                },
                {
                    # 年份外消息：不计
                    "local_id": 4,
                    "local_type": 34,
                    "direction": "sent",
                    "create_time": self._ts(2024, 6, 1, 9, 0, 0),
                    "message_content": _voice_xml("30000"),
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, rows_by_username={friend: rows})

            data = compute_voice_call_stats(account_dir=account_dir, year=2025)
            voice = data["voice"]

            self.assertEqual(voice["sentCount"], 2)
            self.assertEqual(voice["sentSeconds"], 6 + 45)
            self.assertEqual(voice["receivedCount"], 1)
            self.assertEqual(voice["receivedSeconds"], 12)

            top_sent = voice["topSentPartner"]
            self.assertIsNotNone(top_sent)
            self.assertEqual(top_sent["username"], friend)
            self.assertEqual(top_sent["seconds"], 51)
            self.assertEqual(top_sent["count"], 2)
            self.assertEqual(top_sent["displayName"], "好友1")
            self.assertTrue(str(top_sent["avatarUrl"]).startswith("/api/chat/avatar"))

            top_recv = voice["topReceivedPartner"]
            self.assertIsNotNone(top_recv)
            self.assertEqual(top_recv["username"], friend)
            self.assertEqual(top_recv["seconds"], 12)
            self.assertEqual(top_recv["count"], 1)

            # 没有任何通话消息时 calls 仍存在且为空值状态
            self.assertEqual(data["calls"]["totalCount"], 0)
            self.assertIsNone(data["calls"]["topPartner"])

    def test_longest_voice_attribution(self):
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import compute_voice_call_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend_a = "wxid_friend_a"
            friend_b = "wxid_friend_b"
            account_dir = self._make_account_dir(root, account=account, usernames=[friend_a, friend_b])

            rows_by_username = {
                friend_a: [
                    {
                        "local_id": 1,
                        "local_type": 34,
                        "direction": "sent",
                        "create_time": self._ts(2025, 2, 1, 8, 0, 0),
                        "message_content": _voice_xml("6080"),
                    },
                ],
                friend_b: [
                    {
                        "local_id": 2,
                        "local_type": 34,
                        "direction": "received",
                        "create_time": self._ts(2025, 5, 20, 21, 30, 0),
                        "message_content": _voice_xml("58000"),
                    },
                ],
            }
            self._seed_message_db(account_dir / "message_0.db", account=account, rows_by_username=rows_by_username)

            data = compute_voice_call_stats(account_dir=account_dir, year=2025)
            longest = data["voice"]["longest"]

            self.assertIsNotNone(longest)
            self.assertEqual(longest["seconds"], 58)
            self.assertEqual(longest["direction"], "received")
            self.assertEqual(longest["username"], friend_b)
            self.assertEqual(longest["displayName"], "好友2")
            self.assertEqual(longest["maskedName"], "好*2")
            self.assertTrue(str(longest["avatarUrl"]).startswith("/api/chat/avatar"))
            self.assertEqual(longest["date"], "2025-05-20")

    def test_call_types_duration_regex_and_missed(self):
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import compute_voice_call_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_call"
            account_dir = self._make_account_dir(root, account=account, usernames=[friend])

            rows = [
                {
                    # 视频通话，时:分:秒 -> 3723s
                    "local_id": 1,
                    "local_type": 50,
                    "direction": "sent",
                    "create_time": self._ts(2025, 4, 1, 20, 0, 0),
                    "message_content": _voip_xml(room_type="0", msg="通话时长 1:02:03"),
                },
                {
                    # 语音通话，分:秒 -> 19s
                    "local_id": 2,
                    "local_type": 50,
                    "direction": "received",
                    "create_time": self._ts(2025, 4, 2, 20, 0, 0),
                    "message_content": _voip_xml(room_type="1", msg="通话时长 00:19"),
                },
                {
                    "local_id": 3,
                    "local_type": 50,
                    "direction": "sent",
                    "create_time": self._ts(2025, 4, 3, 20, 0, 0),
                    "message_content": _voip_xml(room_type="1", msg="已取消"),
                },
                {
                    "local_id": 4,
                    "local_type": 50,
                    "direction": "sent",
                    "create_time": self._ts(2025, 4, 4, 20, 0, 0),
                    "message_content": _voip_xml(room_type="0", msg="对方已拒绝"),
                },
                {
                    "local_id": 5,
                    "local_type": 50,
                    "direction": "received",
                    "create_time": self._ts(2025, 4, 5, 20, 0, 0),
                    "message_content": _voip_xml(room_type="1", msg="未接听"),
                },
                {
                    # 自己拒接：文案「已拒绝」（不含「对方」前缀）也须计入未接通。
                    "local_id": 6,
                    "local_type": 50,
                    "direction": "received",
                    "create_time": self._ts(2025, 4, 6, 20, 0, 0),
                    "message_content": _voip_xml(room_type="0", msg="已拒绝"),
                },
                {
                    # 拨出无人接听：「对方无应答」。
                    "local_id": 7,
                    "local_type": 50,
                    "direction": "sent",
                    "create_time": self._ts(2025, 4, 7, 20, 0, 0),
                    "message_content": _voip_xml(room_type="1", msg="对方无应答"),
                },
            ]
            self._seed_message_db(account_dir / "message_0.db", account=account, rows_by_username={friend: rows})

            data = compute_voice_call_stats(account_dir=account_dir, year=2025)
            calls = data["calls"]

            self.assertEqual(calls["totalCount"], 7)
            self.assertEqual(calls["videoCount"], 3)
            self.assertEqual(calls["voiceCount"], 4)
            self.assertEqual(calls["connectedCount"], 2)
            self.assertEqual(calls["totalSeconds"], 3723 + 19)
            self.assertEqual(calls["missedOrCanceledCount"], 5)
            # 恒等式：任何文案变体都不得让通话在两侧计数中同时丢失。
            self.assertEqual(calls["totalCount"], calls["connectedCount"] + calls["missedOrCanceledCount"])

            top = calls["topPartner"]
            self.assertIsNotNone(top)
            self.assertEqual(top["username"], friend)
            self.assertEqual(top["seconds"], 3742)
            self.assertEqual(top["count"], 7)
            self.assertEqual(top["displayName"], "好友1")
            self.assertEqual(top["maskedName"], "好*1")

    def test_shard_without_my_name2id_still_counts_received(self):
        # 本人不在某分片的 Name2Id（该分片里从未发过消息）时，收到的语音/通话不得丢失。
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import compute_voice_call_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_recv_only"
            account_dir = self._make_account_dir(root, account=account, usernames=[friend])

            rows = [
                {
                    "local_id": 1,
                    "local_type": 34,
                    "direction": "received",
                    "create_time": self._ts(2025, 8, 1, 10, 0, 0),
                    "message_content": _voice_xml("15000"),
                },
                {
                    "local_id": 2,
                    "local_type": 50,
                    "direction": "received",
                    "create_time": self._ts(2025, 8, 2, 10, 0, 0),
                    "message_content": _voip_xml(room_type="1", msg="通话时长 02:00"),
                },
            ]
            self._seed_message_db(
                account_dir / "message_0.db",
                account=account,
                rows_by_username={friend: rows},
                include_account_in_name2id=False,
            )

            data = compute_voice_call_stats(account_dir=account_dir, year=2025)
            voice = data["voice"]
            calls = data["calls"]

            self.assertEqual(voice["receivedCount"], 1)
            self.assertEqual(voice["receivedSeconds"], 15)
            self.assertEqual(voice["sentCount"], 0)
            self.assertEqual(calls["totalCount"], 1)
            self.assertEqual(calls["connectedCount"], 1)
            self.assertEqual(calls["totalSeconds"], 120)

    def test_chatroom_messages_are_excluded(self):
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import compute_voice_call_stats

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            friend = "wxid_friend_single"
            chatroom = "123456789@chatroom"
            account_dir = self._make_account_dir(root, account=account, usernames=[friend, chatroom])

            rows_by_username = {
                friend: [
                    {
                        "local_id": 1,
                        "local_type": 34,
                        "direction": "sent",
                        "create_time": self._ts(2025, 6, 1, 10, 0, 0),
                        "message_content": _voice_xml("5000"),
                    },
                ],
                chatroom: [
                    {
                        "local_id": 2,
                        "local_type": 34,
                        "direction": "sent",
                        "create_time": self._ts(2025, 6, 1, 11, 0, 0),
                        "message_content": _voice_xml("20000"),
                    },
                    {
                        "local_id": 3,
                        "local_type": 34,
                        "direction": "received",
                        "create_time": self._ts(2025, 6, 1, 12, 0, 0),
                        "message_content": _voice_xml("30000"),
                    },
                    {
                        "local_id": 4,
                        "local_type": 50,
                        "direction": "sent",
                        "create_time": self._ts(2025, 6, 1, 13, 0, 0),
                        "message_content": _voip_xml(room_type="1", msg="通话时长 10:00"),
                    },
                ],
            }
            self._seed_message_db(account_dir / "message_0.db", account=account, rows_by_username=rows_by_username)

            data = compute_voice_call_stats(account_dir=account_dir, year=2025)
            voice = data["voice"]
            calls = data["calls"]

            self.assertEqual(voice["sentCount"], 1)
            self.assertEqual(voice["sentSeconds"], 5)
            self.assertEqual(voice["receivedCount"], 0)
            self.assertEqual(voice["receivedSeconds"], 0)
            self.assertEqual(voice["longest"]["username"], friend)
            self.assertEqual(calls["totalCount"], 0)
            self.assertEqual(calls["totalSeconds"], 0)
            self.assertIsNone(calls["topPartner"])

    def test_empty_state_keeps_fields_with_zero_and_null(self):
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import build_card_02_message_chars

        with TemporaryDirectory() as td:
            root = Path(td)
            account = "wxid_me"
            account_dir = self._make_account_dir(root, account=account, usernames=[])

            card = build_card_02_message_chars(account_dir=account_dir, year=2025)
            self.assertEqual(card["id"], 2)
            self.assertEqual(card["status"], "ok")

            voice = card["data"]["voice"]
            calls = card["data"]["calls"]

            self.assertEqual(voice["sentCount"], 0)
            self.assertEqual(voice["sentSeconds"], 0)
            self.assertEqual(voice["receivedCount"], 0)
            self.assertEqual(voice["receivedSeconds"], 0)
            self.assertIsNone(voice["longest"])
            self.assertIsNone(voice["topSentPartner"])
            self.assertIsNone(voice["topReceivedPartner"])

            self.assertEqual(calls["totalCount"], 0)
            self.assertEqual(calls["videoCount"], 0)
            self.assertEqual(calls["voiceCount"], 0)
            self.assertEqual(calls["connectedCount"], 0)
            self.assertEqual(calls["totalSeconds"], 0)
            self.assertEqual(calls["missedOrCanceledCount"], 0)
            self.assertIsNone(calls["topPartner"])


if __name__ == "__main__":
    unittest.main()
