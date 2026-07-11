import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import record_export


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/api/records/export",
            "headers": [],
        }
    )


class TestRecordExport(unittest.TestCase):
    def test_favorites_loader_always_requests_realtime(self):
        calls = []

        def fake_list_favorites(**kwargs):
            calls.append(kwargs)
            return {
                "account": "wxid_test",
                "dataSource": "realtime",
                "items": [],
                "hasMore": False,
            }

        req = record_export.RecordExportRequest(
            account="wxid_test",
            dataset="favorites",
            format="json",
            output_dir="C:\\temp",
        )
        with patch.object(record_export, "list_favorites", side_effect=fake_list_favorites):
            items, meta = record_export._load_records(_request(), req)

        self.assertEqual(items, [])
        self.assertEqual(meta["dataSource"], "realtime")
        self.assertEqual(calls[0]["source"], "realtime")
        self.assertEqual(calls[0]["kind"], "all")

    def test_type_filter_uses_natural_dataset_types(self):
        favorite = {
            "textBlocks": ["hello"],
            "attachments": [{"renderType": "video"}, {"renderType": "file"}],
        }
        self.assertEqual(record_export._record_types("favorites", favorite), {"text", "video", "file"})
        self.assertEqual(record_export._record_types("friend-verifications", {"isSender": True}), {"outgoing"})
        self.assertEqual(record_export._record_types("payments", {"kind": "redpacket"}), {"redpacket"})
        for state in ("received", "expired", "returned"):
            with self.subTest(state=state):
                self.assertEqual(
                    record_export._record_types("payments", {"kind": "transfer", "transferState": state}),
                    {state},
                )

        payments = [
            {"kind": "transfer", "transferState": "received"},
            {"kind": "transfer", "transferState": "expired"},
            {"kind": "transfer", "transferState": "returned"},
            {"kind": "redpacket"},
        ]
        self.assertEqual(
            record_export._filter_records("payments", payments, {"expired", "returned"}),
            payments[1:3],
        )
        self.assertEqual(record_export._filter_records("payments", payments, {"transfer"}), [])

    def test_json_txt_and_html_exports_are_written_and_escaped(self):
        source_items = [
            {
                "localId": 1,
                "type": 1,
                "typeLabel": "文本",
                "textBlocks": ["<script>alert(1)</script>"],
                "attachments": [],
                "sourceUsername": "wxid_friend",
                "senderContact": {"displayName": "测试好友", "avatar": ""},
                "updateTimeText": "2026-07-10 10:00",
            },
            {
                "localId": 2,
                "type": 4,
                "typeLabel": "视频",
                "textBlocks": [],
                "attachments": [{"renderType": "video", "typeLabel": "视频", "fullMd5": "a" * 32}],
                "sourceUsername": "wxid_friend",
            },
        ]
        source_meta = {"account": "wxid_test", "dataSource": "realtime", "database": "live/favorite.db"}

        with TemporaryDirectory() as td:
            for fmt in ("json", "txt", "html"):
                req = record_export.RecordExportRequest(
                    account="wxid_test",
                    dataset="favorites",
                    format=fmt,
                    types=["text"],
                    output_dir=td,
                    file_name=f"unsafe/name.{fmt}",
                )
                with patch.object(record_export, "_load_records", return_value=(source_items, source_meta)):
                    response = record_export.export_records(_request(), req)
                path = Path(response["outputPath"])
                self.assertTrue(path.exists())
                self.assertEqual(response["count"], 1)
                content = path.read_text(encoding="utf-8")
                if fmt == "json":
                    payload = json.loads(content)
                    self.assertEqual(payload["dataSource"], "realtime")
                    self.assertEqual(payload["count"], 1)
                elif fmt == "html":
                    self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
                    self.assertNotIn("<script>alert(1)</script>", content)
                else:
                    self.assertIn("<script>alert(1)</script>", content)


if __name__ == "__main__":
    unittest.main()
