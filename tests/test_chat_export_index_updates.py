import unittest


from wechat_decrypt_tool.chat_export_service import _replace_ordered_export_index_item
from wechat_decrypt_tool.chat_incremental_export import ordered_conversation_keys


class TestChatExportIndexUpdates(unittest.TestCase):
    def test_replace_preserves_existing_conversation_position(self):
        index = {}
        _replace_ordered_export_index_item(index, {"convDir": "conversations/a", "value": "old-a"})
        _replace_ordered_export_index_item(index, {"convDir": "conversations/b", "value": "b"})
        _replace_ordered_export_index_item(index, {"convDir": "conversations/a", "value": "new-a"})

        self.assertEqual(list(index), ["conversations/a", "conversations/b"])
        self.assertEqual(index["conversations/a"]["value"], "new-a")

    def test_new_conversations_are_added_without_reordering_existing_items(self):
        index = {}
        for name in ("a", "b", "c"):
            _replace_ordered_export_index_item(index, {"convDir": f"conversations/{name}"})

        self.assertEqual(list(index), ["conversations/a", "conversations/b", "conversations/c"])

    def test_saved_order_deduplicates_known_keys_and_appends_unlisted_conversations(self):
        state = {
            "conversationOrder": ["c", "missing", "c", None, "a"],
            "conversations": {"a": {}, "b": {}, "c": {}},
        }
        self.assertEqual(ordered_conversation_keys(state), ["c", "a", "b"])

    def test_legacy_order_is_used_only_without_a_persisted_order(self):
        state = {"legacyConversationOrder": ["b", "a"], "conversations": {"a": {}, "b": {}}}
        self.assertEqual(ordered_conversation_keys(state), ["b", "a"])
        state["conversationOrder"] = ["a", "b"]
        self.assertEqual(ordered_conversation_keys(state), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
