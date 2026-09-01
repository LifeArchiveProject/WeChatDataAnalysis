import unittest


from wechat_decrypt_tool.chat_export_service import _replace_ordered_export_index_item


class TestChatExportIndexUpdates(unittest.TestCase):
    def test_replace_moves_existing_conversation_to_end(self):
        index = {}
        _replace_ordered_export_index_item(index, {"convDir": "conversations/a", "value": "old-a"})
        _replace_ordered_export_index_item(index, {"convDir": "conversations/b", "value": "b"})
        _replace_ordered_export_index_item(index, {"convDir": "conversations/a", "value": "new-a"})

        self.assertEqual(list(index), ["conversations/b", "conversations/a"])
        self.assertEqual(index["conversations/a"]["value"], "new-a")

    def test_new_conversations_are_added_without_reordering_existing_items(self):
        index = {}
        for name in ("a", "b", "c"):
            _replace_ordered_export_index_item(index, {"convDir": f"conversations/{name}"})

        self.assertEqual(list(index), ["conversations/a", "conversations/b", "conversations/c"])


if __name__ == "__main__":
    unittest.main()
