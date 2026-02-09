import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import (
    _build_group_sender_display_name_map,
    _normalize_session_preview_text,
    _replace_preview_sender_prefix,
)


class TestChatSessionPreviewFormatting(unittest.TestCase):
    def test_normalize_session_preview_emoji_label(self):
        out = _normalize_session_preview_text("[表情]", is_group=False, sender_display_names={})
        self.assertEqual(out, "[动画表情]")

    def test_normalize_group_preview_sender_display_name(self):
        out = _normalize_session_preview_text(
            "wxid_u3gwceqvne2m22: [表情]",
            is_group=True,
            sender_display_names={"wxid_u3gwceqvne2m22": "食神"},
        )
        self.assertEqual(out, "食神: [动画表情]")

    def test_build_group_sender_display_name_map_from_contact_db(self):
        with TemporaryDirectory() as td:
            contact_db_path = Path(td) / "contact.db"
            conn = sqlite3.connect(str(contact_db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE contact (
                        username TEXT,
                        remark TEXT,
                        nick_name TEXT,
                        alias TEXT,
                        big_head_url TEXT,
                        small_head_url TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?)",
                    ("wxid_u3gwceqvne2m22", "", "食神", "", "", ""),
                )
                conn.commit()
            finally:
                conn.close()

            mapping = _build_group_sender_display_name_map(
                contact_db_path,
                {"demo@chatroom": "wxid_u3gwceqvne2m22: [动画表情]"},
            )
            self.assertEqual(mapping.get("wxid_u3gwceqvne2m22"), "食神")

    def test_replace_preview_sender_prefix_uses_group_nickname(self):
        out = _replace_preview_sender_prefix("去码头整点🍟: [动画表情]", "麻辣香锅")
        self.assertEqual(out, "麻辣香锅: [动画表情]")


if __name__ == "__main__":
    unittest.main()
