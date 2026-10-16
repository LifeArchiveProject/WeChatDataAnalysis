from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend" / path).read_text(encoding="utf-8")


def test_session_list_uses_css_pixels_instead_of_dividing_by_dpr():
    panel = read_frontend("components/chat/SessionListPanel.vue")
    styles = read_frontend("assets/css/chat.css")

    assert "width: var(--session-list-width, 264px)" in styles
    assert "session-list-width, 295px) / var(--dpr)" not in styles
    assert "calc(80px/var(--dpr))" not in panel
    assert "calc(45px/var(--dpr))" not in panel
    assert 'class="session-list-avatar h-9 w-9' in panel
    assert 'class="session-list-item flex h-[56px]' in panel


def test_session_list_width_migrates_to_css_pixels_and_resizes_without_dpr_multiplier():
    source = read_frontend("composables/chat/useChatSessions.js")

    assert "ui.chat.session_list_width_css_v2" in source
    assert "ui.chat.session_list_width_css" in source
    assert "ui.chat.session_list_width_physical" in source
    assert "physicalValue / dpr" in source
    assert "cssV1Value === 320 ? SESSION_LIST_WIDTH_DEFAULT" in source
    assert "SESSION_LIST_WIDTH_DEFAULT = 264" in source
    assert "SESSION_LIST_WIDTH_MIN = 220" in source
    assert "(clientX - sessionListResizeStartX) *" not in source


def test_session_name_and_time_have_bounded_independent_columns():
    panel = read_frontend("components/chat/SessionListPanel.vue")
    formatters = read_frontend("lib/chat/formatters.js")

    assert "grid-cols-[minmax(0,1fr)_auto]" in panel
    assert "max-w-[92px] truncate whitespace-nowrap" in panel
    assert "max-w-[46%]" not in panel
    assert ":title=\"contact.lastMessageTime\"" in panel
    assert "formatSessionListTime(contact.lastMessageTime)" in panel
    assert "export const formatSessionListTime" in formatters


def test_chat_message_avatars_use_css_pixels_on_retina_displays():
    message_item = read_frontend("components/chat/MessageItem.vue")
    edited_preview = read_frontend("components/EditedMessagePreview.vue")

    for source in (message_item, edited_preview):
        assert "message-avatar h-[34px] w-[34px]" in source
        assert "34px/var(--dpr" not in source
