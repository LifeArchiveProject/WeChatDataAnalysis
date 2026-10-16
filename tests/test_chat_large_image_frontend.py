from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manual_large_image_request_includes_remote_fallback_context() -> None:
    source = (ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js").read_text(
        encoding="utf-8"
    )
    start = source.index("const buildManualLargeImageUrl")
    end = source.index("const isSameMessageIdentity", start)
    builder = source[start:end]

    assert "if (serverId) query.set('server_id', serverId)" in builder
    assert "query.set('fetch_remote', 'true')" in builder
