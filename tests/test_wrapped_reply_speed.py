import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedReplySpeedScoring(unittest.TestCase):
    def test_score_prefers_more_chat_when_speed_similar(self):
        from wechat_decrypt_tool.wrapped.cards.card_03_reply_speed import _ConvAgg, _score_conv

        tau = 30 * 60  # 30min, keep in sync with production default

        # A: 秒回，但聊天很少
        a = _ConvAgg(
            username="wxid_a",
            incoming=3,
            outgoing=3,
            replies=3,
            sum_gap=30,
            sum_gap_capped=30,
            min_gap=5,
            max_gap=15,
        )

        # B: 稍慢，但聊天明显更多
        b = _ConvAgg(
            username="wxid_b",
            incoming=50,
            outgoing=50,
            replies=50,
            sum_gap=3000,  # avg 60s
            sum_gap_capped=3000,
            min_gap=10,
            max_gap=120,
        )

        self.assertGreater(_score_conv(agg=b, tau_seconds=tau), _score_conv(agg=a, tau_seconds=tau))

    def test_score_penalizes_extremely_slow_reply(self):
        from wechat_decrypt_tool.wrapped.cards.card_03_reply_speed import _ConvAgg, _score_conv

        tau = 30 * 60

        fast_few = _ConvAgg(
            username="wxid_fast",
            incoming=5,
            outgoing=5,
            replies=5,
            sum_gap=50,  # avg 10s
            sum_gap_capped=50,
            min_gap=1,
            max_gap=20,
        )

        slow_many = _ConvAgg(
            username="wxid_slow",
            incoming=80,
            outgoing=80,
            replies=80,
            sum_gap=80 * 7200,  # avg 2h
            sum_gap_capped=80 * 7200,
            min_gap=60,
            max_gap=100000,
        )

        self.assertGreater(_score_conv(agg=fast_few, tau_seconds=tau), _score_conv(agg=slow_many, tau_seconds=tau))


class TestWrappedReplySpeedInitiative(unittest.TestCase):
    """「谁先开口 + 势均力敌」（data.initiative）统计口径。"""

    ACCOUNT = "wxid_me"

    def _ts(self, y: int, m: int, d: int, hh: int, mm: int, ss: int) -> int:
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
                    username TEXT,
                    sender_username TEXT,
                    create_time INTEGER,
                    sort_seq INTEGER,
                    local_id INTEGER,
                    local_type INTEGER,
                    db_stem TEXT
                )
                """
            )
            for r in rows:
                conn.execute(
                    """
                    INSERT INTO message_fts(
                        username, sender_username, create_time, sort_seq, local_id, local_type, db_stem
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["username"],
                        r["sender_username"],
                        int(r["create_time"]),
                        int(r["sort_seq"]),
                        int(r["local_id"]),
                        int(r.get("local_type", 1)),
                        str(r.get("db_stem", "message_0")),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _make_row(self, username: str, sender: str, ts: int, lid: int, **extra) -> dict:
        return {
            "username": username,
            "sender_username": sender,
            "create_time": ts,
            "sort_seq": lid,
            "local_id": lid,
            **extra,
        }

    def _compute_initiative(self, rows: list[dict], contacts: list[str]) -> dict:
        from wechat_decrypt_tool.wrapped.cards.card_03_reply_speed import compute_reply_speed_stats

        with TemporaryDirectory() as td:
            account_dir = Path(td) / self.ACCOUNT
            account_dir.mkdir(parents=True, exist_ok=True)
            self._seed_contact_db(account_dir / "contact.db", contacts)
            self._seed_index_db(account_dir / "chat_search_index.db", rows)
            stats = compute_reply_speed_stats(account_dir=account_dir, year=2025)
            return stats["initiative"]

    def test_conversation_split_boundary_exactly_3600(self):
        buddy = "wxid_x"
        base = self._ts(2025, 3, 1, 8, 0, 0)
        rows = [
            # 对方开启第一次对话；间隔 3599 秒不切分，恰好 3600 秒切分为新对话。
            self._make_row(buddy, buddy, base, 1),
            self._make_row(buddy, self.ACCOUNT, base + 3599, 2),
            self._make_row(buddy, buddy, base + 3599 + 3600, 3),
            # 群聊与 biz 分片不参与统计。
            self._make_row("123@chatroom", buddy, base + 100, 4),
            self._make_row("wxid_biz", "wxid_biz", base + 200, 5, db_stem="biz_message_0"),
        ]
        initiative = self._compute_initiative(rows, [buddy])

        self.assertEqual(initiative["conversationCount"], 2)
        self.assertEqual(initiative["initiatedByMe"], 0)
        self.assertEqual(initiative["initiatedByOthers"], 2)
        self.assertEqual(initiative["initiationRatePct"], 0.0)

    def test_initiator_attribution_and_rate(self):
        a = "wxid_aaa"
        b = "wxid_bbb"
        rows = []
        lid = 0

        def add(username: str, sender: str, t: int) -> None:
            nonlocal lid
            lid += 1
            rows.append(self._make_row(username, sender, t, lid))

        # A 会话：我先开口 2 次（10:00 / 14:00），A 先开口 1 次（18:00）。
        t1 = self._ts(2025, 5, 1, 10, 0, 0)
        add(a, self.ACCOUNT, t1)
        add(a, a, t1 + 60)
        t2 = self._ts(2025, 5, 1, 14, 0, 0)
        add(a, self.ACCOUNT, t2)
        add(a, a, t2 + 30)
        t3 = self._ts(2025, 5, 1, 18, 0, 0)
        add(a, a, t3)
        add(a, self.ACCOUNT, t3 + 30)

        # B 会话：B 先开口 1 次。
        t4 = self._ts(2025, 5, 2, 9, 0, 0)
        add(b, b, t4)
        add(b, self.ACCOUNT, t4 + 60)

        initiative = self._compute_initiative(rows, [a, b])

        self.assertEqual(initiative["conversationCount"], 4)
        self.assertEqual(initiative["initiatedByMe"], 2)
        self.assertEqual(initiative["initiatedByOthers"], 2)
        self.assertEqual(initiative["initiationRatePct"], 50.0)

        top_by_me = initiative["topInitiatedByMe"]
        self.assertEqual(len(top_by_me), 1)
        self.assertEqual(top_by_me[0]["username"], a)
        self.assertEqual(top_by_me[0]["count"], 2)
        self.assertEqual(top_by_me[0]["displayName"], f"Nick_{a}")
        self.assertTrue(top_by_me[0]["maskedName"].startswith("N"))
        self.assertIn("*", top_by_me[0]["maskedName"])

        top_to_me = initiative["topInitiatedToMe"]
        self.assertEqual([(x["username"], x["count"]) for x in top_to_me], [(a, 1), (b, 1)])

    def test_initiation_rate_rounding_one_decimal(self):
        buddy = "wxid_rate"
        rows = []
        lid = 0
        # 3 次对话（间隔 2 小时），其中 2 次由我先开口 -> 66.7%。
        starts = [
            (self._ts(2025, 6, 1, 9, 0, 0), self.ACCOUNT),
            (self._ts(2025, 6, 1, 11, 0, 0), self.ACCOUNT),
            (self._ts(2025, 6, 1, 13, 0, 0), buddy),
        ]
        for t, first_sender in starts:
            other = buddy if first_sender == self.ACCOUNT else self.ACCOUNT
            lid += 1
            rows.append(self._make_row(buddy, first_sender, t, lid))
            lid += 1
            rows.append(self._make_row(buddy, other, t + 20, lid))

        initiative = self._compute_initiative(rows, [buddy])
        self.assertEqual(initiative["conversationCount"], 3)
        self.assertEqual(initiative["initiationRatePct"], 66.7)

    def _mutual_pair_rows(self, buddy: str, base: int, lid: int, sent: int, received: int) -> tuple[list[dict], int]:
        rows = []
        n = max(sent, received)
        for i in range(n):
            t = base + i * 40
            if i < received:
                lid += 1
                rows.append(self._make_row(buddy, buddy, t, lid))
            if i < sent:
                lid += 1
                rows.append(self._make_row(buddy, self.ACCOUNT, t + 10, lid))
        return rows, lid

    def test_mutual_friend_threshold_and_pick(self):
        a = "wxid_even"      # 50 / 50 -> ratio 1.0，达标且最接近 1
        b = "wxid_short"     # 49 / 60 -> 我方不足 50，不达标
        c = "wxid_biased"    # 60 / 80 -> ratio 0.75，达标但更不均衡
        rows = []
        lid = 1
        part, lid = self._mutual_pair_rows(a, self._ts(2025, 7, 1, 8, 0, 0), lid, sent=50, received=50)
        rows += part
        part, lid = self._mutual_pair_rows(b, self._ts(2025, 7, 2, 8, 0, 0), lid, sent=49, received=60)
        rows += part
        part, lid = self._mutual_pair_rows(c, self._ts(2025, 7, 3, 8, 0, 0), lid, sent=60, received=80)
        rows += part

        initiative = self._compute_initiative(rows, [a, b, c])
        mutual = initiative["mutualFriend"]
        self.assertIsNotNone(mutual)
        self.assertEqual(mutual["username"], a)
        self.assertEqual(mutual["sentCount"], 50)
        self.assertEqual(mutual["receivedCount"], 50)
        self.assertEqual(mutual["ratio"], 1.0)
        self.assertEqual(mutual["displayName"], f"Nick_{a}")

    def test_mutual_friend_none_when_below_threshold(self):
        buddy = "wxid_onesided"
        rows, _ = self._mutual_pair_rows(buddy, self._ts(2025, 8, 1, 8, 0, 0), 1, sent=49, received=120)
        initiative = self._compute_initiative(rows, [buddy])
        self.assertIsNone(initiative["mutualFriend"])

    def test_empty_index_still_returns_initiative_shape(self):
        initiative = self._compute_initiative([], [])
        self.assertEqual(initiative["conversationCount"], 0)
        self.assertEqual(initiative["initiatedByMe"], 0)
        self.assertEqual(initiative["initiatedByOthers"], 0)
        self.assertIsNone(initiative["initiationRatePct"])
        self.assertEqual(initiative["topInitiatedByMe"], [])
        self.assertEqual(initiative["topInitiatedToMe"], [])
        self.assertIsNone(initiative["mutualFriend"])


if __name__ == "__main__":
    unittest.main()
