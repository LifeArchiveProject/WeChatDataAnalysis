import unittest
from pathlib import Path
import sys

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedKeywordsWordCloud(unittest.TestCase):
    def test_extract_keywords_jieba_basic(self):
        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import extract_keywords_jieba

        texts = [
            "火锅 火锅",
            "火锅太好吃了！！！",
            "movie night movie",
            "2024-01-01 12:30",
            "哈哈哈哈",
        ]

        out = extract_keywords_jieba(texts, top_n=40)
        self.assertIsInstance(out, list)
        self.assertLessEqual(len(out), 40)

        # Must be sorted by count descending (tie-break by word).
        counts = [int(x.get("count") or 0) for x in out]
        self.assertEqual(counts, sorted(counts, reverse=True))

        # Weights are normalized into [0.2, 1.0] when multiple items exist.
        for x in out:
            w = float(x.get("weight") or 0)
            self.assertGreaterEqual(w, 0.0)
            self.assertLessEqual(w, 1.0)

        words = [str(x.get("word") or "") for x in out]
        self.assertTrue(any("火锅" == w for w in words))
        self.assertTrue(any("movie" == w for w in words))
        self.assertTrue(all(not w.isdigit() for w in words if w))

    def test_extract_keywords_jieba_short_phrases(self):
        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import extract_keywords_jieba

        # Jieba may split short chat phrases into single characters ("在吗" -> ["在","吗"]),
        # which would be filtered out by our tokenizer. Ensure we still extract meaningful
        # 2-char phrases as a fallback.
        texts = ["在吗"] * 30 + ["好的"] * 25 + ["嗯"] * 40 + ["哈哈"] * 40
        out = extract_keywords_jieba(texts, top_n=10)

        words = [str(x.get("word") or "") for x in out]
        self.assertIn("在吗", words)
        self.assertIn("好的", words)

    def test_list_message_tables_decodes_bytes(self):
        import sqlite3

        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import _list_message_tables

        conn = sqlite3.connect(":memory:")
        try:
            conn.text_factory = bytes
            conn.execute("CREATE TABLE Msg_abc (id INTEGER)")
            conn.execute("CREATE TABLE Chat_def (id INTEGER)")
            conn.execute("CREATE TABLE Other (id INTEGER)")
            tables = _list_message_tables(conn)
        finally:
            conn.close()

        self.assertIn("Msg_abc", tables)
        self.assertIn("Chat_def", tables)
        self.assertTrue(all(isinstance(x, str) for x in tables))

    def test_pick_examples_contains_word(self):
        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import pick_examples

        keywords = [
            {"word": "火锅", "count": 3, "weight": 1.0},
            {"word": "movie", "count": 2, "weight": 0.6},
        ]
        pool = [
            "今晚火锅走起",
            "火锅太好吃了",
            "no",
            "<msg>xml</msg>",
            "Movie night is fun",
            "MOVIE time",
            "https://example.com/movie",
        ]

        out = pick_examples(keywords, pool, per_word=3)
        self.assertEqual(len(out), 2)

        m_hotpot = next(x for x in out if x["word"] == "火锅")
        self.assertTrue(all("火锅" in m for m in m_hotpot["messages"]))

        m_movie = next(x for x in out if x["word"] == "movie")
        self.assertTrue(all("movie" in m.lower() for m in m_movie["messages"]))

    def test_build_keywords_payload_structure(self):
        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import build_keywords_payload

        texts = [
            "今晚吃火锅吗？",
            "火锅太好吃了！！！",
            "一起去看电影吧",
            "一起一起",
            "movie night movie",
        ]

        payload = build_keywords_payload(texts=texts, seed=123456)
        self.assertIn("keywords", payload)
        self.assertIn("bubbleMessages", payload)
        self.assertIn("examples", payload)
        self.assertIn("topKeyword", payload)

        self.assertIsInstance(payload["keywords"], list)
        self.assertIsInstance(payload["bubbleMessages"], list)
        self.assertIsInstance(payload["examples"], list)
        self.assertTrue(payload["topKeyword"] is None or isinstance(payload["topKeyword"], dict))

        # bubble messages are unique and within limit
        b = payload["bubbleMessages"]
        self.assertLessEqual(len(b), 180)
        self.assertEqual(len(b), len(list(dict.fromkeys(b))))


if __name__ == "__main__":
    unittest.main()
