import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import chat as chat_router


class TestTransferPostprocess(unittest.TestCase):
    def test_backfilled_pending_and_received_confirmation_have_expected_titles(self):
        transfer_id = "1000050001202601152035503031545"
        merged = [
            {
                "id": "message_0:Msg_x:60",
                "renderType": "transfer",
                "paySubType": "1",
                "transferId": transfer_id,
                "amount": "￥100.00",
                "createTime": 1768463200,
                "isSent": False,
                "transferStatus": "",
            },
            {
                "id": "message_0:Msg_x:65",
                "renderType": "transfer",
                "paySubType": "3",
                "transferId": transfer_id,
                "amount": "￥100.00",
                "createTime": 1768463246,
                "isSent": True,
                # Pre-inferred value (may be "已被接收") should be corrected by postprocess.
                "transferStatus": "已被接收",
            },
        ]

        chat_router._postprocess_transfer_messages(merged)

        self.assertEqual(merged[0].get("paySubType"), "3")
        self.assertEqual(merged[0].get("transferStatus"), "已被接收")
        self.assertEqual(merged[1].get("paySubType"), "3")
        self.assertEqual(merged[1].get("transferStatus"), "已收款")

    def test_received_message_without_pending_is_left_unchanged(self):
        merged = [
            {
                "id": "message_0:Msg_x:65",
                "renderType": "transfer",
                "paySubType": "3",
                "transferId": "t1",
                "amount": "￥100.00",
                "createTime": 1,
                "isSent": True,
                "transferStatus": "已被接收",
            }
        ]

        chat_router._postprocess_transfer_messages(merged)

        self.assertEqual(merged[0].get("transferStatus"), "已被接收")


if __name__ == "__main__":
    unittest.main()

