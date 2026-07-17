import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend" / path).read_text(encoding="utf-8")


class ErrorNoticeFrontendTest(unittest.TestCase):
    def test_error_notice_keeps_the_error_and_opens_log_settings(self):
        notice = read_frontend("components/ErrorNotice.vue")
        helper = read_frontend("composables/useErrorNotice.js")

        self.assertIn("message:", notice)
        self.assertIn("compact:", notice)
        self.assertIn("manual:", notice)
        self.assertIn("{{ normalizedMessage }}", notice)
        self.assertIn("openDialog('log-file')", notice)
        self.assertIn("打开设置", notice)
        self.assertIn("日志文件", helper)
        self.assertIn("发送给开发者", helper)

    def test_error_notice_can_focus_the_log_file_row(self):
        state = read_frontend("composables/useSettingsDialog.js")
        app = read_frontend("app.vue")
        settings = read_frontend("components/SettingsDialog.vue")

        self.assertIn("settings-dialog-focus-target", state)
        self.assertIn("focusTarget.value = String(target || '').trim()", state)
        self.assertIn(':focus-target="settingsDialogFocusTarget"', app)
        self.assertIn('ref="desktopLogFileRef"', settings)
        self.assertIn("props.focusTarget", settings)
        self.assertIn("scrollToFocusTarget", settings)
        self.assertIn("scrollHost.scrollTop + targetRect.top - scrollRect.top", settings)
        self.assertIn("z-[20000]", settings)
        self.assertIn("targetIsVisible", settings)
        self.assertIn("compact manual", settings)

    def test_compact_notice_preserves_call_site_container_styles(self):
        notice = read_frontend("components/ErrorNotice.vue")
        compact_rule = re.search(
            r"\.error-notice--compact\s*\{(?P<body>[^}]*)\}",
            notice,
        )

        self.assertIn(".error-notice:not(.error-notice--compact)", notice)
        for declaration in (
            "display:",
            "flex-direction:",
            "padding:",
            "border:",
            "background:",
            "color:",
            "font-size:",
        ):
            if compact_rule is not None:
                self.assertNotIn(declaration, compact_rule.group("body"))

    def test_shared_notice_is_the_only_alert_in_wrapped_error_states(self):
        forbidden = {
            "components/chat/ChatExportDialog.vue": [
                'class="chat-export-alert chat-export-alert--error" role="alert"',
                'class="chat-export-result chat-export-result--error" role="alert"',
            ],
            "components/GlobalExportDialog.vue": [
                'class="app-export-alert app-export-alert--error" role="alert"',
                'class="app-export-result app-export-result--error" role="alert"',
            ],
            "pages/favorites.vue": ['class="records-state records-state--error" role="alert"'],
            "pages/finder.vue": ['class="records-state records-state--error" role="alert"'],
            "pages/mini-programs.vue": ['class="records-state records-state--error" role="alert"'],
            "pages/payments.vue": ['class="records-state records-state--error" role="alert"'],
        }

        for path, markers in forbidden.items():
            source = read_frontend(path)
            for marker in markers:
                self.assertNotIn(marker, source, f"{path}: {marker}")

    def test_operational_error_surfaces_use_the_shared_notice(self):
        expected = {
            "pages/decrypt.vue": [':message="error"', ':message="warning"'],
            "pages/import.vue": [':message="importError"'],
            "pages/detection-result.vue": [':message="detectionResult.error"'],
            "pages/favorites.vue": [':message="error"'],
            "pages/contacts.vue": [':message="friendVerificationError"'],
            "components/BizMessages.vue": [':message="accountsError"', ':message="messagesError"'],
            "components/chat/ChatOverlays.vue": [':message="messageSearchError"'],
            "components/chat/ChatExportDialog.vue": [':message="exportError"'],
            "components/GlobalExportDialog.vue": [':message="globalError"'],
        }

        for path, markers in expected.items():
            source = read_frontend(path)
            self.assertIn("<ErrorNotice", source, path)
            for marker in markers:
                self.assertIn(marker, source, f"{path}: {marker}")

    def test_native_operational_failures_use_the_shared_helper(self):
        paths = (
            "stores/imgHelper.js",
            "stores/chatRealtime.js",
            "composables/chat/useChatEditing.js",
            "composables/chat/useChatMessages.js",
            "composables/chat/useChatSearch.js",
        )
        combined = "\n".join(read_frontend(path) for path in paths)

        self.assertIn("showErrorAlert", combined)
        for message in (
            "window.alert('复制失败",
            "window.alert('定位引用消息失败",
            "window.alert(e?.message || '定位失败')",
            "window.alert(e?.message || '加载更多消息失败')",
            "window.alert(error?.message || '下载失败')",
        ):
            self.assertNotIn(message, combined)

        # Empty states and user-correctable preconditions stay concise.
        self.assertIn("window.alert('暂无聊天记录')", combined)
        self.assertIn("window.alert('该表情没有可用的下载地址')", combined)

    def test_hover_only_errors_include_the_shared_guidance(self):
        message_content = read_frontend("components/chat/MessageContent.vue")
        sidebar = read_frontend("components/SidebarRail.vue")

        self.assertIn('v-if="message._imageLargeError"', message_content)
        self.assertIn(':message="message._imageLargeError"', message_content)
        self.assertIn("withErrorLogGuidance(imgHelperError.value)", sidebar)


if __name__ == "__main__":
    unittest.main()
