import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedMonthlyBestFriends(unittest.TestCase):
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

    def test_balanced_profile_can_beat_higher_volume(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_monthly_best_friends_wall import (
            compute_monthly_best_friends_wall_stats,
        )

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            user_volume = "wxid_volume"
            user_balanced = "wxid_balanced"
            self._seed_contact_db(account_dir / "contact.db", [user_volume, user_balanced])

            rows: list[dict] = []
            lid = 1
            # High-volume user: more messages but consistently slow replies and low continuity.
            for d in [3, 18]:
                for i in range(6):
                    t = self._ts(2025, 1, d, 21, i * 3, 0)
                    rows.append(
                        {
                            "username": user_volume,
                            "sender_username": user_volume,
                            "create_time": t,
                            "sort_seq": lid,
                            "local_id": lid,
                        }
                    )
                    lid += 1
                    rows.append(
                        {
                            "username": user_volume,
                            "sender_username": account,
                            "create_time": t + 7200,
                            "sort_seq": lid,
                            "local_id": lid,
                        }
                    )
                    lid += 1

            # Balanced user: slightly fewer interactions, but much faster and spread over more days/hours.
            day_hour = [
                (2, 1),
                (6, 8),
                (9, 13),
                (13, 19),
                (20, 10),
                (24, 22),
                (27, 7),
                (29, 16),
                (30, 12),
                (31, 20),
            ]
            for d, hh in day_hour:
                t = self._ts(2025, 1, d, hh, 10, 0)
                rows.append(
                    {
                        "username": user_balanced,
                        "sender_username": user_balanced,
                        "create_time": t,
                        "sort_seq": lid,
                        "local_id": lid,
                    }
                )
                lid += 1
                rows.append(
                    {
                        "username": user_balanced,
                        "sender_username": account,
                        "create_time": t + 20,
                        "sort_seq": lid,
                        "local_id": lid,
                    }
                )
                lid += 1

            self._seed_index_db(account_dir / "chat_search_index.db", rows)
            data = compute_monthly_best_friends_wall_stats(account_dir=account_dir, year=2025)
            jan = data["months"][0]
            self.assertIsNotNone(jan["winner"])
            self.assertEqual(jan["winner"]["username"], user_balanced)

    def test_allows_consecutive_month_wins(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_monthly_best_friends_wall import (
            compute_monthly_best_friends_wall_stats,
        )

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            buddy = "wxid_best"
            self._seed_contact_db(account_dir / "contact.db", [buddy])

            rows: list[dict] = []
            lid = 1
            for month in [1, 2]:
                for d in [3, 8, 12, 18]:
                    t = self._ts(2025, month, d, 12, 0, 0)
                    rows.append(
                        {
                            "username": buddy,
                            "sender_username": buddy,
                            "create_time": t,
                            "sort_seq": lid,
                            "local_id": lid,
                        }
                    )
                    lid += 1
                    rows.append(
                        {
                            "username": buddy,
                            "sender_username": account,
                            "create_time": t + 30,
                            "sort_seq": lid,
                            "local_id": lid,
                        }
                    )
                    lid += 1

            self._seed_index_db(account_dir / "chat_search_index.db", rows)
            data = compute_monthly_best_friends_wall_stats(account_dir=account_dir, year=2025)
            jan = data["months"][0]
            feb = data["months"][1]
            self.assertEqual(jan["winner"]["username"], buddy)
            self.assertEqual(feb["winner"]["username"], buddy)

    def test_month_without_enough_activity_is_empty(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_monthly_best_friends_wall import (
            compute_monthly_best_friends_wall_stats,
        )

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)

            user = "wxid_low"
            self._seed_contact_db(account_dir / "contact.db", [user])

            rows = []
            lid = 1
            # Only 3 reply pairs in March -> total 6 messages, below minTotalMessages=8.
            for d in [5, 11, 25]:
                t = self._ts(2025, 3, d, 10, 0, 0)
                rows.append(
                    {
                        "username": user,
                        "sender_username": user,
                        "create_time": t,
                        "sort_seq": lid,
                        "local_id": lid,
                    }
                )
                lid += 1
                rows.append(
                    {
                        "username": user,
                        "sender_username": account,
                        "create_time": t + 40,
                        "sort_seq": lid,
                        "local_id": lid,
                    }
                )
                lid += 1

            self._seed_index_db(account_dir / "chat_search_index.db", rows)
            data = compute_monthly_best_friends_wall_stats(account_dir=account_dir, year=2025)
            march = data["months"][2]
            self.assertIsNone(march["winner"])
            self.assertEqual(march["reason"], "insufficient_data")

    def test_card_shape_and_kind(self):
        from wechat_decrypt_tool.wrapped.cards.card_04_monthly_best_friends_wall import (
            build_card_04_monthly_best_friends_wall,
        )

        with TemporaryDirectory() as td:
            account = "wxid_me"
            account_dir = Path(td) / account
            account_dir.mkdir(parents=True, exist_ok=True)
            self._seed_contact_db(account_dir / "contact.db", [])
            self._seed_index_db(account_dir / "chat_search_index.db", [])

            card = build_card_04_monthly_best_friends_wall(account_dir=account_dir, year=2025)
            self.assertEqual(card["id"], 4)
            self.assertEqual(card["kind"], "chat/monthly_best_friends_wall")
            self.assertEqual(card["status"], "ok")
            self.assertEqual(len(card["data"]["months"]), 12)

if __name__ == "__main__":
    unittest.main()
