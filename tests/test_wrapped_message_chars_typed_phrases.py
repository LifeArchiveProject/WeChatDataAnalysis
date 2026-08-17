import hashlib
import sqlite3
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedMessageCharsTypedPhrases(unittest.TestCase):
    def test_shard_fallback_keeps_ime_phrases_without_search_index(self):
        from wechat_decrypt_tool.wrapped.cards.card_02_message_chars import build_card_02_message_chars

        with TemporaryDirectory() as td:
            account = "wxid_me"
            friend = "wxid_friend"
            account_dir = Path(td) / account
            account_dir.mkdir()
            db_path = account_dir / "message_0.db"
            table_name = f"msg_{hashlib.md5(friend.encode('utf-8')).hexdigest()}"

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
                conn.executemany(
                    "INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)",
                    [(1, account), (2, friend)],
                )
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
                rows = [
                    (1, 1, 1, 1, 1, int(datetime(2025, 2, 1).timestamp()), "早点休息", None),
                    (2, 2, 1, 2, 1, int(datetime(2025, 3, 1).timestamp()), "明天见", None),
                    # Received, punctuated, and out-of-year messages must not become IME samples.
                    (3, 3, 1, 3, 2, int(datetime(2025, 4, 1).timestamp()), "不该出现", None),
                    (4, 4, 1, 4, 1, int(datetime(2025, 5, 1).timestamp()), "带标点！", None),
                    (5, 5, 1, 5, 1, int(datetime(2024, 6, 1).timestamp()), "去年短语", None),
                ]
                conn.executemany(
                    f"""
                    INSERT INTO {table_name}
                    (local_id, server_id, local_type, sort_seq, real_sender_id, create_time, message_content, compress_content)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
            finally:
                conn.close()

            self.assertFalse((account_dir / "chat_search_index.db").exists())

            card = build_card_02_message_chars(account_dir=account_dir, year=2025)
            phrases = card["data"]["typedPhrases"]
            by_text = {item["text"]: item["pinyin"] for item in phrases}

            self.assertEqual(set(by_text), {"早点休息", "明天见"})
            self.assertEqual(by_text["早点休息"], "zao dian xiu xi")
            self.assertEqual(by_text["明天见"], "ming tian jian")


if __name__ == "__main__":
    unittest.main()
