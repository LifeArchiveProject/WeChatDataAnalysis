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


def _char_tokens(s: str) -> str:
    # Mirror chat_helpers._to_char_token_text: lowercased chars joined by spaces.
    return " ".join(ch for ch in str(s).lower() if not ch.isspace())


class TestWrappedGlobalOverviewPeakDay(unittest.TestCase):
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

    def _seed_index_db(self, path: Path, rows: list[dict]) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_fts (
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
                    is_official INTEGER,
                    payload_json TEXT
                )
                """
            )
            for r in rows:
                conn.execute(
                    """
                    INSERT INTO message_fts(
                        text, username, render_type, create_time, sort_seq, local_id,
                        server_id, local_type, db_stem, table_name, sender_username,
                        is_hidden, is_official, payload_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.get("text", ""),
                        r["username"],
                        r.get("render_type", "text"),
                        int(r["create_time"]),
                        int(r.get("sort_seq", r.get("local_id", 0))),
                        int(r.get("local_id", 0)),
                        int(r.get("server_id", 0)),
                        int(r.get("local_type", 1)),
                        str(r.get("db_stem", "message_0")),
                        str(r.get("table_name", "msg_abc")),
                        r["sender_username"],
                        0,
                        0,
                        r.get("payload_json"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def test_peak_day_payload_and_highlights(self):
        from wechat_decrypt_tool.wrapped.cards.card_00_global_overview import (
            build_card_00_global_overview,
        )

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            friend = "wxid_friend"
            group = "12345@chatroom"
            official = "gh_service"
            self._seed_contact_db(account_dir / "contact.db", [friend, group])

            rows: list[dict] = []
            lid = 1

            def add(username: str, sender: str, ts: int, text: str = "hi", payload: bool = True) -> None:
                nonlocal lid
                rows.append(
                    {
                        "username": username,
                        "sender_username": sender,
                        "create_time": ts,
                        "local_id": lid,
                        "sort_seq": lid,
                        "text": _char_tokens(text),
                        "payload_json": json.dumps({"content": text}, ensure_ascii=False) if payload else None,
                    }
                )
                lid += 1

            # 普通日：2025-01-10 / 2025-02-01 各发 1 条。
            add(friend, account, self._ts(2025, 1, 10, 12, 0), "普通日消息")
            add(friend, account, self._ts(2025, 2, 1, 12, 0), "普通日消息")

            # 峰值日 2025-03-05（周三，doy0=63）：本人发 6 条。
            long_first = "好" * 80
            add(group, account, self._ts(2025, 3, 5, 8, 15), long_first)
            add(group, account, self._ts(2025, 3, 5, 10, 0), "上午继续聊")
            add(friend, account, self._ts(2025, 3, 5, 12, 0), "中午的消息")
            add(group, account, self._ts(2025, 3, 5, 15, 0), "下午的消息")
            add(friend, account, self._ts(2025, 3, 5, 20, 0), "晚上的消息")
            # 末条文本消息缺 payload_json：应回退到去空格拼接 token text。
            add(group, account, self._ts(2025, 3, 5, 23, 30), "晚安啦", payload=False)

            # 峰值日他人发来的消息：群聊 3 条、好友 1 条 -> 群聊全天 7 条为当日主角。
            add(group, "wxid_other1", self._ts(2025, 3, 5, 9, 0), "群友消息1")
            add(group, "wxid_other2", self._ts(2025, 3, 5, 9, 5), "群友消息2")
            add(group, "wxid_other3", self._ts(2025, 3, 5, 9, 10), "群友消息3")
            add(friend, friend, self._ts(2025, 3, 5, 12, 5), "好友回复")

            # 公众号消息更多，但必须被会话过滤规则排除，不能成为当日主角。
            for i in range(20):
                add(official, official, self._ts(2025, 3, 5, 11, i), f"推送{i}")

            self._seed_index_db(account_dir / "chat_search_index.db", rows)

            card = build_card_00_global_overview(account_dir=account_dir, year=2025)
            data = card["data"]

            peak = data["peakDay"]
            self.assertIsNotNone(peak)
            self.assertEqual(peak["date"], "2025-03-05")
            self.assertEqual(peak["weekdayName"], "周三")
            self.assertEqual(peak["count"], 6)

            # multiple = count / messagesPerDay（保留 1 位小数）。
            mpd = float(data["messagesPerDay"])
            self.assertGreater(mpd, 0)
            self.assertAlmostEqual(peak["multiple"], round(6 / mpd, 1))

            top = peak["topContact"]
            self.assertIsNotNone(top)
            self.assertEqual(top["username"], group)
            self.assertTrue(top["isGroup"])
            self.assertEqual(top["messages"], 7)
            self.assertEqual(top["displayName"], f"Nick_{group}")
            self.assertTrue(top["maskedName"])
            self.assertTrue(top["avatarUrl"])

            # 首条：超长文本截断到 60 字；末条：无 payload 时回退 token 拼接。
            self.assertEqual(peak["firstTime"], "08:15")
            self.assertEqual(peak["firstText"], "好" * 60)
            self.assertEqual(peak["lastTime"], "23:30")
            self.assertEqual(peak["lastText"], "晚安啦")

            highlights = data["annualHeatmap"]["highlights"]
            self.assertEqual(len(highlights), 1)
            h = highlights[0]
            self.assertEqual(h["key"], "sent_messages_max")
            self.assertEqual(h["doy"], 63)
            self.assertTrue(str(h["label"]).strip())
            self.assertIn("6", str(h["valueLabel"]))

    def test_peak_day_null_when_no_messages(self):
        from wechat_decrypt_tool.wrapped.cards.card_00_global_overview import (
            build_card_00_global_overview,
        )

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)
            self._seed_contact_db(account_dir / "contact.db", [])
            self._seed_index_db(account_dir / "chat_search_index.db", [])

            card = build_card_00_global_overview(account_dir=account_dir, year=2025)
            data = card["data"]
            self.assertIsNone(data["peakDay"])
            self.assertEqual(data["annualHeatmap"]["highlights"], [])


if __name__ == "__main__":
    unittest.main()
