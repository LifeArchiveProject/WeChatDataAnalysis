import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestChatExportPanelFrontend(unittest.TestCase):
    def test_export_settings_stay_in_one_panel(self):
        overlay = (ROOT / "frontend" / "components" / "chat" / "ChatOverlays.vue").read_text(encoding="utf-8")
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")

        self.assertIn("ChatExportDialog", overlay)
        self.assertIn('id="chat-export-panel-scope"', dialog)
        self.assertIn('id="chat-export-panel-content"', dialog)
        self.assertIn('id="chat-export-panel-output"', dialog)
        self.assertNotIn("exportPanelTab", dialog)
        self.assertNotIn('role="tablist"', dialog)

    def test_advanced_html_defaults_are_hidden_and_reset(self):
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")
        export_state = (ROOT / "frontend" / "composables" / "chat" / "useChatExport.js").read_text(encoding="utf-8")

        self.assertNotIn("引用缩略图", dialog)
        self.assertNotIn("每页消息", dialog)
        self.assertIn("exportDownloadRemoteMedia.value = true", export_state)
        self.assertIn("exportHtmlPageSize.value = 1000", export_state)

    def test_scope_bulk_selection_button_never_wraps(self):
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")

        self.assertIn(".chat-export-scope-toolbar > .chat-export-secondary-button", dialog)
        self.assertIn("min-width: 88px", dialog)
        self.assertIn("white-space: nowrap", dialog)


if __name__ == "__main__":
    unittest.main()
