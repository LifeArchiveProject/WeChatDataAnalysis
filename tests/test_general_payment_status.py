import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import general


class TestGeneralPaymentStatus(unittest.TestCase):
    def test_second_transfer_message_marks_returned_instead_of_received(self):
        item = {
            "kind": "transfer",
            "sessionName": "wxid_friend",
            "messageServerId": 1001,
            "secondMessageServerId": 1002,
            "paySubType": 4,
            "invalidTime": 9999999999,
        }
        details = {
            "wxid_friend|s:1001|l:0": {
                "serverId": 1001,
                "amount": "¥10.00",
                "content": "¥10.00",
                "transferStatus": "转账",
            },
            "wxid_friend|s:1002|l:0": {
                "serverId": 1002,
                "amount": "¥10.00",
                "content": "¥10.00",
                "transferStatus": "已退还",
                "paySubType": "4",
            },
        }
        with patch.object(general, "_lookup_messages_for_requests", return_value=details):
            general._attach_payment_message_details(Path("."), [item], source="realtime")

        self.assertEqual(item["initialMessage"]["serverId"], 1001)
        self.assertEqual(item["statusMessage"]["serverId"], 1002)
        self.assertEqual(item["transferState"], "returned")
        self.assertEqual(item["transferStatus"], "已退还")
        self.assertEqual(item["amountText"], "¥10.00")

    def test_table_subtypes_distinguish_received_returned_and_expired(self):
        items = [
            {"kind": "transfer", "paySubType": 3},
            {"kind": "transfer", "paySubType": 4},
            {"kind": "transfer", "paySubType": 2, "invalidTime": 1},
        ]
        with patch.object(general, "_lookup_messages_for_requests", return_value={}):
            general._attach_payment_message_details(Path("."), items, source="realtime")

        self.assertEqual([item["transferState"] for item in items], ["received", "returned", "expired"])
        self.assertEqual([item["transferStatus"] for item in items], ["已收款", "已退还", "已过期"])


if __name__ == "__main__":
    unittest.main()
