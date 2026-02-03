import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
