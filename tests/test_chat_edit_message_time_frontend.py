import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNAVAILABLE_MESSAGE = "当前环境无法完成此操作，请联系开发者协助处理。"


class TestChatEditSurfaceFrontend(unittest.TestCase):
    def test_only_text_messages_expose_the_single_modify_text_action(self):
        overlays = (ROOT / "frontend" / "components" / "chat" / "ChatOverlays.vue").read_text(
            encoding="utf-8"
        )

        self.assertEqual(overlays.count("修改文字"), 1)
        self.assertIn('v-if="isLikelyTextMessage(contextMenu.message)"', overlays)
        self.assertIn('@click="onEditMessageClick"', overlays)
        for label in (
            "修改消息",
            "编辑源码",
            "修改时间",
            "字段编辑",
            "恢复原消息",
            "修复为我发送",
            "反转微信气泡位置",
            "检查修改状态",
        ):
            self.assertNotIn(label, overlays)

    def test_modify_text_closes_the_menu_and_only_shows_generic_error(self):
        editing = (ROOT / "frontend" / "composables" / "chat" / "useChatEditing.js").read_text(
            encoding="utf-8"
        )
        overlays = (ROOT / "frontend" / "components" / "chat" / "ChatOverlays.vue").read_text(
            encoding="utf-8"
        )
        handler = editing.split("const onEditMessageClick = () => {", 1)[1].split(
            "const closeModifyTextUnavailableDialog", 1
        )[0]
        close_handler = editing.split("const closeModifyTextUnavailableDialog = () => {", 1)[1].split(
            "const onLocateQuotedMessageClick", 1
        )[0]

        self.assertIn("if (!isLikelyTextMessage(message)) return", handler)
        self.assertIn("modifyTextUnavailableDialogOpen.value = true", handler)
        self.assertNotIn("showErrorAlert", handler)
        self.assertNotIn("window.alert", handler)
        self.assertNotIn("api.", handler)
        self.assertLess(handler.index("closeContextMenu()"), handler.index("modifyTextUnavailableDialogOpen.value = true"))
        self.assertIn("modifyTextUnavailableDialogOpen.value = false", close_handler)
        self.assertIn(f"const MODIFY_TEXT_UNAVAILABLE_MESSAGE = '{UNAVAILABLE_MESSAGE}'", editing)
        self.assertIn(UNAVAILABLE_MESSAGE, editing)
        self.assertIn("<GuideDialog", overlays)
        self.assertIn(':open="modifyTextUnavailableDialogOpen"', overlays)
        self.assertIn(':description="modifyTextUnavailableMessage"', overlays)
        self.assertIn('@primary="closeModifyTextUnavailableDialog"', overlays)
        self.assertIn('@close="closeModifyTextUnavailableDialog"', overlays)

        for symbol in (
            "editChatMessage",
            "getChatEditStatus",
            "resetChatEditedMessage",
            "resetChatEditedSession",
            "repairChatMessageSender",
            "flipChatMessageDirection",
            "messageEditModal",
            "messageTimeModal",
            "messageFieldsModal",
        ):
            self.assertNotIn(symbol, editing)

    def test_edit_history_page_navigation_and_backend_routes_are_removed(self):
        sidebar = (ROOT / "frontend" / "components" / "SidebarRail.vue").read_text(encoding="utf-8")
        app = (ROOT / "frontend" / "app.vue").read_text(encoding="utf-8")
        client = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")
        backend = (ROOT / "src" / "wechat_decrypt_tool" / "routers" / "chat.py").read_text(
            encoding="utf-8"
        )

        self.assertFalse((ROOT / "frontend" / "pages" / "edits" / "[[username]].vue").exists())
        for source in (sidebar, app):
            self.assertNotIn("/edits", source)
        self.assertNotIn("goEdits", sidebar)
        self.assertNotIn("isEditsRoute", sidebar)
        self.assertNotIn("编辑记录", sidebar)
        self.assertNotIn("修改记录", sidebar)

        for route in (
            "/api/chat/messages/edit",
            "/api/chat/edits/sessions",
            "/api/chat/edits/messages",
            "/api/chat/edits/message_status",
            "/api/chat/messages/repair_sender",
            "/api/chat/messages/flip_direction",
            "/api/chat/edits/reset_message",
            "/api/chat/edits/reset_session",
        ):
            self.assertNotIn(route, backend)
            self.assertNotIn(route.removeprefix("/api"), client)

        for route in (
            "/chat/messages/add_text",
            "/chat/messages/add_image",
            "/chat/messages/add_file",
        ):
            self.assertNotIn(route, client)

    def test_edit_only_backend_helpers_are_removed_but_read_compatibility_remains(self):
        backend = (ROOT / "src" / "wechat_decrypt_tool" / "routers" / "chat.py").read_text(
            encoding="utf-8"
        )
        native_realtime = (
            ROOT / "src" / "wechat_decrypt_tool" / "native_core_realtime.py"
        ).read_text(encoding="utf-8")
        native_client = (
            ROOT / "src" / "wechat_decrypt_tool" / "native_core_client.py"
        ).read_text(encoding="utf-8")
        development_lease = (
            ROOT / "src" / "wechat_decrypt_tool" / "native_core_dev_lease.py"
        ).read_text(encoding="utf-8")
        realtime_api = (ROOT / "src" / "wechat_decrypt_tool" / "wcdb_realtime.py").read_text(
            encoding="utf-8"
        )
        smoke_tool = (ROOT / "tools" / "smoke_native_core_real_database.py").read_text(
            encoding="utf-8"
        )

        for symbol in (
            "update_message as _wcdb_update_message",
            "def _sql_literal",
            "def _normalize_edit_value",
            "def _is_safe_edit_column",
            "def _pb_read_varint",
            "def _pb_write_varint",
            "def _swap_packed_info_from_to",
            "def _table_info_columns",
            "def _has_column",
            "def _lookup_output_my_rowid",
            "def _lookup_output_username_by_rowid",
            "def _select_output_message_row",
            "def _build_wcdb_update_sql",
            "def _build_sqlite_update_sql",
        ):
            self.assertNotIn(symbol, backend)

        self.assertFalse((ROOT / "src" / "wechat_decrypt_tool" / "chat_edit_store.py").exists())
        self.assertFalse((ROOT / "tests" / "test_chat_edit_store.py").exists())
        self.assertNotIn("chat_edit_store", backend)
        self.assertNotIn("removed_edit_count", backend)
        for source in (native_realtime, realtime_api):
            self.assertNotIn("def update_message(", source)
            self.assertNotIn("def delete_message(", source)
        self.assertNotIn("def _execute(", native_realtime)
        self.assertNotIn("_WRITE_PREFIXES", native_realtime)
        self.assertNotIn("NativeCoreRealtimeWriteRequired", native_realtime)
        self.assertIn('raise NativeCoreRealtimeError("Native-core raw SQL is read-only.")', native_realtime)
        for symbol in (
            "DATABASE_WRITE",
            "READ_WRITE",
            "execute_dml",
            "wce_database_execute_dml",
            "_WceDatabaseExecuteOptions",
        ):
            self.assertNotIn(symbol, native_client)
        self.assertNotIn("DATABASE_WRITE", development_lease)
        self.assertNotIn("--write-copy", smoke_tool)
        self.assertNotIn("execute_dml", smoke_tool)

        self.assertIn('@router.get("/api/chat/messages/raw"', backend)
        self.assertIn("def _normalize_table_name_case", backend)
        self.assertIn("def _resolve_db_storage_message_paths", backend)


if __name__ == "__main__":
    unittest.main()
