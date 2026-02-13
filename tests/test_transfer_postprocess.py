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

    def test_pending_transfer_marked_expired_by_system_message(self):
        merged = [
            {
                "id": "message_0:Msg_x:100",
                "renderType": "transfer",
                "paySubType": "1",
                "transferId": "t-expired-1",
                "amount": "￥500.00",
                "createTime": 1770742598,
                "isSent": True,
                "transferStatus": "转账",
            },
            {
                "id": "message_0:Msg_x:101",
                "renderType": "system",
                "type": 10000,
                "createTime": 1770829000,
                "content": "收款方24小时内未接收你的转账，已过期",
            },
        ]

        chat_router._postprocess_transfer_messages(merged)

        self.assertEqual(merged[0].get("paySubType"), "10")
        self.assertEqual(merged[0].get("transferStatus"), "已过期")

    def test_expired_matching_wins_over_amount_time_received_fallback(self):
        merged = [
            {
                "id": "message_0:Msg_x:200",
                "renderType": "transfer",
                "paySubType": "1",
                "transferId": "t-expired-2",
                "amount": "￥500.00",
                "createTime": 1770742598,
                "isSent": True,
                "transferStatus": "",
            },
            {
                "id": "message_0:Msg_x:201",
                "renderType": "transfer",
                "paySubType": "3",
                "transferId": "t-other",
                "amount": "￥500.00",
                "createTime": 1770828800,
                "isSent": False,
                "transferStatus": "已收款",
            },
            {
                "id": "message_0:Msg_x:202",
                "renderType": "system",
                "type": 10000,
                "createTime": 1770829000,
                "content": "收款方24小时内未接收你的转账，已过期",
            },
        ]

        chat_router._postprocess_transfer_messages(merged)

        self.assertEqual(merged[0].get("paySubType"), "10")
        self.assertEqual(merged[0].get("transferStatus"), "已过期")


if __name__ == "__main__":
    unittest.main()
