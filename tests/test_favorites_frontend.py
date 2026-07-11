import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestFavoritesFrontend(unittest.TestCase):
    def test_api_always_requests_realtime_favorites(self):
        source = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")
        self.assertIn("const listFavorites = async", source)
        self.assertIn("query.set('source', 'realtime')", source)
        self.assertIn("request('/favorites'", source)
        self.assertIn("listFavorites,", source)

    def test_sidebar_has_favorites_route(self):
        source = (ROOT / "frontend" / "components" / "SidebarRail.vue").read_text(encoding="utf-8")
        self.assertIn('title="收藏"', source)
        self.assertIn("isFavoritesRoute", source)
        self.assertIn("navigateTo('/favorites')", source)

    def test_favorites_page_uses_realtime_api_wrapper(self):
        source = (ROOT / "frontend" / "pages" / "favorites.vue").read_text(encoding="utf-8")
        self.assertIn("api.listFavorites", source)
        self.assertIn("kind: kindFilter.value", source)
        self.assertIn("tagId: Number(tagFilter.value", source)
        self.assertIn("item.textBlocks", source)
        self.assertIn("item.attachments", source)
        self.assertIn("MessageContent", source)
        self.assertIn("ChatHistoryFloatingWindows", source)
        self.assertIn("useChatHistoryWindows", source)
        self.assertIn(":message=\"message\"", source)
        self.assertIn("senderContact", source)
        self.assertIn("RecordExportDialog", source)
        self.assertIn("renderType: 'chatHistory'", source)
        self.assertIn("historyState.openChatHistoryModal(message)", source)
        self.assertIn("historyState.onFloatingWindowMouseMove", source)
        self.assertNotIn(':hide-type-footer="true"', source)
        self.assertNotIn("favorite-history-dialog", source)
        self.assertNotIn("favorite-message-meta", source)

    def test_shared_chat_history_window_handles_voice_and_dragging(self):
        overlay = (ROOT / "frontend" / "components" / "chat" / "ChatOverlays.vue").read_text(encoding="utf-8")
        shared = (ROOT / "frontend" / "components" / "chat" / "ChatHistoryFloatingWindows.vue").read_text(encoding="utf-8")
        parser = (ROOT / "frontend" / "lib" / "chat" / "chat-history.js").read_text(encoding="utf-8")

        self.assertIn("ChatHistoryFloatingWindows", overlay)
        self.assertIn("startFloatingWindowDrag", shared)
        self.assertIn("rec.renderType === 'voice'", shared)
        self.assertIn("<MessageContent", shared)
        self.assertIn("audioFormats.has(fmt)", parser)
        self.assertIn("output.voiceUrl", parser)

    def test_record_export_dialog_is_connected_to_all_requested_pages(self):
        pages = {
            "favorites.vue": 'dataset="favorites"',
            "contacts.vue": 'dataset="friend-verifications"',
            "mini-programs.vue": 'dataset="mini-programs"',
            "finder.vue": 'dataset="finder"',
            "payments.vue": 'dataset="payments"',
        }
        for file_name, marker in pages.items():
            source = (ROOT / "frontend" / "pages" / file_name).read_text(encoding="utf-8")
            self.assertIn("RecordExportDialog", source, file_name)
            self.assertIn(marker, source, file_name)

        component = (ROOT / "frontend" / "components" / "RecordExportDialog.vue").read_text(encoding="utf-8")
        self.assertIn("HTML", component)
        self.assertIn("JSON", component)
        self.assertIn("TXT", component)
        self.assertIn("api.exportRecords", component)
        self.assertNotIn("实时库 ·", component)
        self.assertNotIn("未选择账号", component)

    def test_payment_page_filters_and_exports_terminal_transfer_states(self):
        source = (ROOT / "frontend" / "pages" / "payments.vue").read_text(encoding="utf-8")
        self.assertIn('aria-label="按转账状态筛选"', source)
        export_types = source.split("const paymentExportTypes = [", 1)[1].split("]", 1)[0]
        self.assertIn("{ value: 'received', label: '已收款'", export_types)
        self.assertIn("{ value: 'expired', label: '已过期'", export_types)
        self.assertIn("{ value: 'returned', label: '已退还'", export_types)
        self.assertIn("{ value: 'redpacket', label: '红包'", export_types)
        self.assertNotIn("value: 'transfer'", export_types)

    def test_mini_program_export_has_no_redundant_type_selector(self):
        source = (ROOT / "frontend" / "pages" / "mini-programs.vue").read_text(encoding="utf-8")
        self.assertIn('dataset="mini-programs"', source)
        self.assertNotIn(":type-options=", source)
        self.assertNotIn("miniProgramExportTypes", source)


if __name__ == "__main__":
    unittest.main()
