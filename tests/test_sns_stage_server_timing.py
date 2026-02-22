import sys
import unittest
from pathlib import Path

from starlette.responses import Response


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.sns_stage_timing import add_sns_stage_timing_headers  # noqa: E402  pylint: disable=wrong-import-position


class TestSnsStageServerTiming(unittest.TestCase):
    def test_injects_server_timing_when_missing(self):
        resp = Response(content=b"ok")
        add_sns_stage_timing_headers(resp.headers, source="proxy")
        st = str(resp.headers.get("Server-Timing") or "")
        self.assertIn("sns_source_", st)
        self.assertIn("proxy", st)

    def test_appends_when_upstream_server_timing_exists(self):
        resp = Response(content=b"ok")
        resp.headers["Server-Timing"] = "edge;dur=1"
        add_sns_stage_timing_headers(resp.headers, source="proxy")
        st = str(resp.headers.get("Server-Timing") or "")
        self.assertIn("edge;dur=1", st)
        self.assertIn("sns_source_", st)

    def test_does_not_duplicate_existing_sns_source_metric(self):
        resp = Response(content=b"ok")
        resp.headers["Server-Timing"] = 'sns_source_proxy;dur=0;desc="proxy"'
        add_sns_stage_timing_headers(resp.headers, source="proxy")
        st = str(resp.headers.get("Server-Timing") or "")
        self.assertEqual(st.count("sns_source_"), 1)


if __name__ == "__main__":
    unittest.main()
