import json
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedCyberScheduleNightCompanion(unittest.TestCase):
    def _ts(self, y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> int:
        return int(datetime(y, m, d, hh, mm, ss).timestamp())

    def _seed_contact_db(self, path: Path, usernames: list[str]) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contact (
                    username TEXT PRIMARY KEY,
                    remark TEXT,
                    nick_name TEXT,
                    alias TEXT,
                    big_head_url TEXT,
                    small_head_url TEXT
                )
                """
            )
            for u in usernames:
                conn.execute(
                    "INSERT INTO contact(username, nick_name) VALUES(?, ?)",
                    (u, f"Nick_{u}"),
                )
            conn.commit()
        finally:
            conn.close()

    def _seed_index_db(self, path: Path, rows: list[dict], *, with_payload: bool = True) -> None:
        # 模拟真实索引：text 列存逐字符分词文本，原文保留在 payload_json（旧索引无该列）。
        from wechat_decrypt_tool.chat_helpers import _to_char_token_text

        conn = sqlite3.connect(str(path))
        try:
            payload_col = ",\n                    payload_json TEXT" if with_payload else ""
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS message_fts (
                    text TEXT,
                    username TEXT,
                    sender_username TEXT,
                    create_time INTEGER,
                    sort_seq INTEGER,
                    local_id INTEGER,
                    local_type INTEGER,
                    db_stem TEXT,
                    table_name TEXT{payload_col}
                )
                """
            )
            for r in rows:
                original = str(r.get("text", "hi"))
                values = [
                    _to_char_token_text(original),
                    r["username"],
                    r["sender_username"],
                    int(r["create_time"]),
                    int(r.get("sort_seq", r["local_id"])),
                    int(r["local_id"]),
                    int(r.get("local_type", 1)),
                    str(r.get("db_stem", "message_0")),
                    str(r.get("table_name", "msg_abc")),
                ]
                cols = (
                    "text, username, sender_username, create_time, sort_seq, "
                    "local_id, local_type, db_stem, table_name"
                )
                if with_payload:
                    cols += ", payload_json"
                    values.append(json.dumps({"content": original}, ensure_ascii=False))
                placeholders = ", ".join("?" for _ in values)
                conn.execute(f"INSERT INTO message_fts({cols}) VALUES({placeholders})", values)
            conn.commit()
        finally:
            conn.close()

    def _row(self, username: str, sender: str, t: int, lid: int, **kw) -> dict:
        return {
            "username": username,
            "sender_username": sender,
            "create_time": t,
            "local_id": lid,
            **kw,
        }

    def test_aggregation_excludes_group_biz_and_system_messages(self):
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import _compute_night_companion

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend_a = "wxid_friend_a"
            friend_b = "wxid_friend_b"
            group = "12345678@chatroom"
            self._seed_contact_db(account_dir / "contact.db", [friend_a, friend_b])

            rows: list[dict] = []
            lid = 1

            # friend_a 深夜双向消息 6 条：4 条对方发来 + 2 条本人发出。
            for hh, mm in [(0, 30), (1, 10), (2, 5), (3, 40)]:
                rows.append(self._row(friend_a, friend_a, self._ts(2025, 3, 8, hh, mm), lid))
                lid += 1
            for hh, mm in [(1, 20), (2, 15)]:
                rows.append(self._row(friend_a, account, self._ts(2025, 3, 9, hh, mm), lid))
                lid += 1

            # friend_b 深夜双向消息 2 条：1 条对方 + 1 条本人。
            rows.append(self._row(friend_b, friend_b, self._ts(2025, 5, 1, 0, 45), lid))
            lid += 1
            rows.append(self._row(friend_b, account, self._ts(2025, 5, 1, 0, 50), lid))
            lid += 1

            # 应排除：群聊、biz 分片、系统消息、白天消息、非目标年份。
            rows.append(self._row(group, friend_a, self._ts(2025, 3, 8, 1, 0), lid))
            lid += 1
            rows.append(self._row(friend_a, friend_a, self._ts(2025, 3, 8, 2, 0), lid, db_stem="biz_message_0"))
            lid += 1
            rows.append(self._row(friend_a, friend_a, self._ts(2025, 3, 8, 3, 0), lid, local_type=10000))
            lid += 1
            rows.append(self._row(friend_a, friend_a, self._ts(2025, 3, 8, 12, 0), lid))
            lid += 1
            rows.append(self._row(friend_a, friend_a, self._ts(2024, 3, 8, 1, 0), lid))
            lid += 1

            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            data = _compute_night_companion(account_dir=account_dir, year=2025, my_username=account)
            self.assertEqual(data["nightMessagesTotal"], 8)
            self.assertEqual(data["myNightMessages"], 3)

            partner = data["partner"]
            self.assertIsNotNone(partner)
            self.assertEqual(partner["username"], friend_a)
            self.assertEqual(partner["nightMessages"], 6)
            self.assertAlmostEqual(partner["sharePct"], 75.0)
            self.assertEqual(partner["displayName"], f"Nick_{friend_a}")
            # 打码：首尾保留，中间打星。
            self.assertTrue(partner["maskedName"].startswith("N"))
            self.assertIn("*", partner["maskedName"])
            self.assertTrue(partner["avatarUrl"])

    def test_latest_moment_uses_late_night_scoring(self):
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import _compute_night_companion

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_night_friend"
            self._seed_contact_db(account_dir / "contact.db", [friend])

            rows = [
                # 5:30 的消息按 +24h 计分反而排最前（最接近清晨），不应被选中。
                self._row(friend, friend, self._ts(2025, 7, 2, 5, 30), 1, text="快天亮了"),
                self._row(friend, friend, self._ts(2025, 7, 2, 0, 20), 2, text="刚过零点"),
                # 3:45 本人发出，+24h 计分最大，应为“最晚一刻”。
                self._row(friend, account, self._ts(2025, 7, 3, 3, 45), 3, text="还没睡"),
            ]
            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            data = _compute_night_companion(account_dir=account_dir, year=2025, my_username=account)
            moment = data["latestMoment"]
            self.assertIsNotNone(moment)
            self.assertEqual(moment["time"], "03:45")
            self.assertEqual(moment["direction"], "sent")
            self.assertEqual(moment["content"], "还没睡")
            self.assertEqual(moment["date"], "2025-07-03")

    def test_latest_moment_content_truncated_to_60(self):
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import _compute_night_companion

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_talkative"
            self._seed_contact_db(account_dir / "contact.db", [friend])

            long_text = "夜" * 70
            rows = [self._row(friend, friend, self._ts(2025, 1, 5, 2, 0), 1, text=long_text)]
            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            data = _compute_night_companion(account_dir=account_dir, year=2025, my_username=account)
            moment = data["latestMoment"]
            self.assertIsNotNone(moment)
            self.assertEqual(moment["content"], "夜" * 57 + "...")
            self.assertEqual(len(moment["content"]), 60)
            self.assertEqual(moment["direction"], "received")

    def test_latest_moment_readable_on_legacy_index_without_payload(self):
        # 旧索引没有 payload_json 列：分词文本应去空格还原（小写/空格损失可接受），不得逐字带空格展示。
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import _compute_night_companion

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_legacy_friend"
            self._seed_contact_db(account_dir / "contact.db", [friend])

            rows = [self._row(friend, friend, self._ts(2025, 6, 1, 2, 0), 1, text="晚安 Good Night")]
            self._seed_index_db(account_dir / "chat_search_index.db", rows, with_payload=False)

            data = _compute_night_companion(account_dir=account_dir, year=2025, my_username=account)
            moment = data["latestMoment"]
            self.assertIsNotNone(moment)
            self.assertEqual(moment["content"], "晚安goodnight")

    def test_excludes_official_and_service_sessions(self):
        # 公众号/企业微信/服务号会话不得成为守夜人，也不得进入 sharePct 分母。
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import _compute_night_companion

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_real_friend"
            self._seed_contact_db(account_dir / "contact.db", [friend])

            rows: list[dict] = []
            lid = 1
            for hh, mm in [(1, 0), (2, 0)]:
                rows.append(self._row(friend, friend, self._ts(2025, 9, 9, hh, mm), lid))
                lid += 1
            # 企业微信联系人 5 条、服务推送 3 条、公众号 2 条，全部应被排除。
            for hh in range(5):
                rows.append(self._row("1688850001@openim", "1688850001@openim", self._ts(2025, 9, 10, 1, hh), lid))
                lid += 1
            for hh in range(3):
                rows.append(self._row("notifymessage", "notifymessage", self._ts(2025, 9, 11, 2, hh), lid))
                lid += 1
            for hh in range(2):
                rows.append(self._row("gh_news123", "gh_news123", self._ts(2025, 9, 12, 3, hh), lid))
                lid += 1

            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            data = _compute_night_companion(account_dir=account_dir, year=2025, my_username=account)
            self.assertEqual(data["nightMessagesTotal"], 2)
            partner = data["partner"]
            self.assertIsNotNone(partner)
            self.assertEqual(partner["username"], friend)
            self.assertAlmostEqual(partner["sharePct"], 100.0)

    def test_no_night_messages_returns_zero_shape(self):
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import _compute_night_companion

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_day_friend"
            self._seed_contact_db(account_dir / "contact.db", [friend])

            # 只有白天消息。
            rows = [
                self._row(friend, friend, self._ts(2025, 4, 1, 9, 0), 1),
                self._row(friend, account, self._ts(2025, 4, 1, 21, 30), 2),
            ]
            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            data = _compute_night_companion(account_dir=account_dir, year=2025, my_username=account)
            self.assertEqual(data["nightMessagesTotal"], 0)
            self.assertEqual(data["myNightMessages"], 0)
            self.assertIsNone(data["partner"])
            self.assertIsNone(data["latestMoment"])

    def test_card_payload_contains_night_companion(self):
        from wechat_decrypt_tool.wrapped.cards.card_01_cyber_schedule import build_card_01_cyber_schedule

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_friend"
            self._seed_contact_db(account_dir / "contact.db", [friend])

            rows = [
                self._row(friend, friend, self._ts(2025, 2, 2, 1, 0), 1),
                self._row(friend, account, self._ts(2025, 2, 2, 1, 5), 2),
                self._row(friend, account, self._ts(2025, 2, 2, 14, 0), 3),
            ]
            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            card = build_card_01_cyber_schedule(account_dir=account_dir, year=2025)
            self.assertEqual(card["id"], 1)
            nc = card["data"]["nightCompanion"]
            self.assertEqual(nc["nightMessagesTotal"], 2)
            self.assertEqual(nc["myNightMessages"], 1)
            self.assertEqual(nc["partner"]["username"], friend)
            self.assertAlmostEqual(nc["partner"]["sharePct"], 100.0)


if __name__ == "__main__":
    unittest.main()
