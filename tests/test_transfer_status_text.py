import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _infer_transfer_status_text


class TestTransferStatusText(unittest.TestCase):
    def test_paysubtype_3_sent_side(self):
        status = _infer_transfer_status_text(
            is_sent=True,
            paysubtype="3",
            receivestatus="",
            sendertitle="",
            receivertitle="",
            senderdes="",
            receiverdes="",
        )
        self.assertEqual(status, "已被接收")

    def test_paysubtype_3_received_side(self):
        status = _infer_transfer_status_text(
            is_sent=False,
            paysubtype="3",
            receivestatus="",
            sendertitle="",
            receivertitle="",
            senderdes="",
            receiverdes="",
        )
        self.assertEqual(status, "已收款")

    def test_receivestatus_1_sent_side(self):
        status = _infer_transfer_status_text(
            is_sent=True,
            paysubtype="1",
            receivestatus="1",
            sendertitle="",
            receivertitle="",
            senderdes="",
            receiverdes="",
        )
        self.assertEqual(status, "已被接收")

    def test_receivestatus_1_received_side(self):
        status = _infer_transfer_status_text(
            is_sent=False,
            paysubtype="1",
            receivestatus="1",
            sendertitle="",
            receivertitle="",
            senderdes="",
            receiverdes="",
        )
        self.assertEqual(status, "已收款")


if __name__ == "__main__":
    unittest.main()
