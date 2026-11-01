import unittest
from pathlib import Path
import sys

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedKeywordsWordCloud(unittest.TestCase):
    def test_weflow_common_phrase_filter(self):
        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import _weflow_common_phrase_or_empty

        self.assertEqual(_weflow_common_phrase_or_empty("  在吗  "), "在吗")
        self.assertEqual(_weflow_common_phrase_or_empty("ok"), "ok")
        self.assertEqual(_weflow_common_phrase_or_empty("a"), "")  # too short
        self.assertEqual(_weflow_common_phrase_or_empty("x" * 21), "")  # too long
        self.assertEqual(_weflow_common_phrase_or_empty("看看 http://x.com"), "")  # contains http
        self.assertEqual(_weflow_common_phrase_or_empty("<msg>xml</msg>"), "")  # contains "<"
        self.assertEqual(_weflow_common_phrase_or_empty("[捂脸]"), "")  # bracketed payload
        self.assertEqual(_weflow_common_phrase_or_empty("<?xml version='1.0'?>"), "")  # xml payload

    def test_build_common_phrases_payload_structure(self):
        from collections import Counter

        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import build_common_phrases_payload

        phrase_counts = Counter({"好的": 5, "在吗": 2, "movie": 2, "单次": 1})
        example_texts = [
            "好的收到",
            "好的好的，明白了",
            "你好的呀",
            "在吗宝贝",
            "movie night is fun",
            "MOVIE time now",
        ]
        payload = build_common_phrases_payload(
            phrase_counts=phrase_counts,
            seed=123456,
            top_n=32,
            bubble_limit=50,
            example_texts=example_texts,
            examples_per_word=3,
        )

        self.assertIn("keywords", payload)
        self.assertIn("bubbleMessages", payload)
        self.assertIn("examples", payload)
        self.assertIn("topKeyword", payload)

        self.assertEqual(payload["topKeyword"]["word"], "好的")
        self.assertEqual(int(payload["topKeyword"]["count"]), 5)

        self.assertTrue(all(int(x.get("count") or 0) >= 2 for x in payload["keywords"]))
        self.assertTrue(all(isinstance(x.get("word"), str) and x.get("word") for x in payload["keywords"]))

        # Examples should contain real message samples with an upper bound.
        for ex in payload["examples"]:
            msgs = ex.get("messages") or []
            self.assertGreaterEqual(len(msgs), 1)
            self.assertLessEqual(len(msgs), 3)
            word = str(ex.get("word") or "")
            if any("\u4e00" <= ch <= "\u9fff" for ch in word):
                self.assertTrue(any(word in str(m) for m in msgs))
            else:
                self.assertTrue(any(word.lower() in str(m).lower() for m in msgs))

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

    def test_pick_examples_short_phrase_can_fill_three(self):
        from wechat_decrypt_tool.wrapped.cards.card_05_keywords_wordcloud import pick_examples

        keywords = [{"word": "在吗", "count": 9, "weight": 1.0}]
        pool = [
            "在吗",
            "在吗",
            "在吗",
            "在吗？",
            "ok",
        ]

        out = pick_examples(keywords, pool, per_word=3)
        self.assertEqual(len(out), 1)
        msgs = out[0]["messages"]
        self.assertEqual(len(msgs), 3)
        self.assertTrue(all("在吗" in m for m in msgs))

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
