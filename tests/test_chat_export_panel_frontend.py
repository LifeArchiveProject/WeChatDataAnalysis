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

    def test_incremental_folder_mode_keeps_zip_as_default_and_writes_baseline_last(self):
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")
        export_state = (ROOT / "frontend" / "composables" / "chat" / "useChatExport.js").read_text(encoding="utf-8")
        api_state = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")

        self.assertIn("const exportOutputMode = ref('zip')", export_state)
        self.assertIn("ZIP 全量", dialog)
        self.assertIn("增量目录", dialog)
        self.assertIn("output_mode: exportOutputMode.value", export_state)
        self.assertIn("folder_name:", export_state)
        self.assertIn("repair_usernames:", export_state)
        self.assertIn("recheck_media:", export_state)
        self.assertIn("重新探测缺失媒体", dialog)
        self.assertIn("修复可恢复差异", dialog)
        self.assertIn("微信聊天记录_隐私_${privacyAccountToken(account)}", export_state)
        self.assertIn("output_mode: data.output_mode === 'folder' ? 'folder' : 'zip'", api_state)
        self.assertIn("baseline: data.baseline && typeof data.baseline === 'object'", api_state)
        self.assertIn("repair_usernames: Array.isArray(data.repair_usernames)", api_state)
        self.assertIn("recheck_media: !!data.recheck_media", api_state)
        file_loop = export_state.index("for (const entry of files)")
        stale_loop = export_state.index("for (const stalePath")
        state_write = export_state.index("writeResponseToBrowserFile(root, CHAT_EXPORT_BASELINE_FILE")
        commit = export_state.index("/commit`, { method: 'POST' }")
        self.assertLess(file_loop, stale_loop)
        self.assertLess(stale_loop, state_write)
        self.assertLess(state_write, commit)

    def test_incremental_result_separates_success_repair_and_unavailable_media(self):
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")

        summary = dialog.index('class="chat-export-folder-result__summary"')
        followups = dialog.index('class="chat-export-folder-result__followups"')
        details = dialog.index('class="chat-export-folder-result__details"')
        self.assertLess(summary, followups)
        self.assertLess(followups, details)
        self.assertIn("已确认修复会产生变化，仅重建对应会话。", dialog)
        self.assertIn("源端暂不可用，重复修复不会改变结果。", dialog)
        self.assertIn("查看完整任务说明", dialog)

    def test_incremental_baseline_card_uses_compact_status_and_custom_checkbox(self):
        dialog = (ROOT / "frontend" / "components" / "chat" / "ChatExportDialog.vue").read_text(encoding="utf-8")

        self.assertIn('class="chat-export-incremental-card__folder"', dialog)
        self.assertIn('class="chat-export-baseline-status"', dialog)
        self.assertIn(':data-status="exportBaselineStatus"', dialog)
        self.assertIn("auto: '自动检查基线'", dialog)
        self.assertIn('type="checkbox" class="sr-only"', dialog)
        self.assertIn(".chat-export-reset-option:focus-within", dialog)


if __name__ == "__main__":
    unittest.main()
