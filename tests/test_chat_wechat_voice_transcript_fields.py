from __future__ import annotations

import sqlite3
from pathlib import Path

from wechat_decrypt_tool.routers.chat import _append_full_messages_from_rows


def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def test_chat_voice_message_exposes_official_transcript_without_whisper() -> None:
    text = "微信官方语音转写"
    child = _varint(0x12) + _varint(len(text.encode())) + text.encode()
    packed = _varint(0x2A) + _varint(len(child)) + child

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT 1 AS local_id, 2 AS server_id, 3 AS create_time, 4 AS sort_seq,
               34 AS local_type, 0 AS real_sender_id, '' AS sender_username,
               NULL AS compress_content, '' AS message_content, '' AS msg_source,
               ? AS packed_info_data
        """,
        (packed,),
    ).fetchone()
    assert row is not None

    merged: list[dict] = []
    _append_full_messages_from_rows(
        merged=merged,
        sender_usernames=[],
        quote_usernames=[],
        pat_usernames=set(),
        rows=[row],
        db_path=Path("Msg.db"),
        table_name="Msg_1",
        username="wxid_friend",
        account_dir=Path("wxid_me"),
        is_group=False,
        my_rowid=None,
        resource_conn=None,
        resource_chat_id=None,
    )

    assert merged[0]["wechatTranscript"] == text
    assert merged[0]["transcriptSource"] == "wechat"
    assert merged[0].get("voiceTranscript", "") == ""

    empty_row = conn.execute(
        """
        SELECT 2 AS local_id, 0 AS server_id, 3 AS create_time, 4 AS sort_seq,
               34 AS local_type, 0 AS real_sender_id, '' AS sender_username,
               NULL AS compress_content, '' AS message_content, '' AS msg_source,
               X'2A0180' AS packed_info_data
        """
    ).fetchone()
    assert empty_row is not None
    empty: list[dict] = []
    _append_full_messages_from_rows(
        merged=empty,
        sender_usernames=[],
        quote_usernames=[],
        pat_usernames=set(),
        rows=[empty_row],
        db_path=Path("Msg.db"),
        table_name="Msg_1",
        username="wxid_friend",
        account_dir=Path("wxid_me"),
        is_group=False,
        my_rowid=None,
        resource_conn=None,
        resource_chat_id=None,
    )
    assert empty[0]["wechatTranscript"] == ""
    assert empty[0]["transcriptSource"] == ""
