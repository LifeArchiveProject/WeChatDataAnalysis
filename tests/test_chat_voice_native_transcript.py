import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wechat_decrypt_tool.chat_helpers import _extract_voice_transcript_from_packed_info
from wechat_decrypt_tool.routers.chat import _append_full_messages_from_rows
from wechat_decrypt_tool.voice_transcription import (
    VoiceTranscriptionConfig,
    VoiceTranscriptionService,
    delete_voice_transcript_cache,
)


SYNTHETIC_TRANSCRIPT = "这是一条合成测试转写。"
SYNTHETIC_TRANSCRIPT_BLOB = bytes.fromhex(
    "084310042a2508021221e8bf99e698afe4b880e69da1e59088e68890e6b58be8af95e8bdace58699e38082"
)


class NativeVoiceTranscriptTest(unittest.TestCase):
    def test_extracts_exact_wechat_native_transcript(self):
        self.assertEqual(
            _extract_voice_transcript_from_packed_info(SYNTHETIC_TRANSCRIPT_BLOB),
            SYNTHETIC_TRANSCRIPT,
        )
        self.assertEqual(
            _extract_voice_transcript_from_packed_info(SYNTHETIC_TRANSCRIPT_BLOB.hex()),
            SYNTHETIC_TRANSCRIPT,
        )

    def test_rejects_non_final_or_malformed_payloads(self):
        # Top-level field 5 contains nested status=0/text and status=3/text.
        self.assertEqual(
            _extract_voice_transcript_from_packed_info(bytes.fromhex("2a0708001203616263")),
            "",
        )
        self.assertEqual(
            _extract_voice_transcript_from_packed_info(bytes.fromhex("2a0708031203616263")),
            "",
        )
        self.assertEqual(_extract_voice_transcript_from_packed_info(b"\x2a\x7fbroken"), "")

    def test_chat_message_exposes_native_transcript_without_whisper(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE message (
                local_id INTEGER,
                server_id INTEGER,
                create_time INTEGER,
                sort_seq INTEGER,
                local_type INTEGER,
                sender_username TEXT,
                real_sender_id INTEGER,
                compress_content BLOB,
                message_content BLOB,
                msg_source BLOB,
                packed_info_data BLOB
            )
            """
        )
        conn.execute(
            """
            INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                9007199254740993,
                1700000000,
                1700000000,
                34,
                "wxid_sender_fixture",
                9,
                b'<msg><voicemsg voicelength="1234" /></msg>',
                b"",
                b"",
                SYNTHETIC_TRANSCRIPT_BLOB,
            ),
        )
        rows = conn.execute("SELECT * FROM message").fetchall()

        merged = []
        _append_full_messages_from_rows(
            merged=merged,
            sender_usernames=[],
            quote_usernames=[],
            pat_usernames=set(),
            rows=rows,
            db_path=Path("message_0.db"),
            table_name="Msg_voice_fixture",
            username="fixture@chatroom",
            account_dir=Path("wxid_voice_fixture"),
            is_group=True,
            my_rowid=1,
            resource_conn=None,
            resource_chat_id=None,
        )

        self.assertEqual(len(merged), 1)
        message = merged[0]
        self.assertEqual(message["voiceTranscript"], SYNTHETIC_TRANSCRIPT)
        self.assertEqual(message["voiceTranscriptStatus"], "success")
        self.assertEqual(message["voiceTranscriptModel"], "wechat-native")
        self.assertEqual(message["voiceTranscriptLanguage"], "")

    def test_deleting_project_transcripts_preserves_wechat_packed_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "wxid_native_fixture"
            account_dir.mkdir()
            service = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
            with patch(
                "wechat_decrypt_tool.voice_transcription.normalize_transcript_text",
                side_effect=lambda value: str(value or "").strip(),
            ):
                service._write_cache(
                    account_dir,
                    9007199254740993,
                    "project-cache",
                    {"text": "本项目转写", "language": "zh", "duration": 1.0},
                )
            message_db = account_dir / "message_0.db"
            conn = sqlite3.connect(str(message_db))
            try:
                conn.execute("CREATE TABLE message (server_id INTEGER, packed_info_data BLOB)")
                conn.execute(
                    "INSERT INTO message VALUES (?, ?)",
                    (9007199254740993, SYNTHETIC_TRANSCRIPT_BLOB),
                )
                conn.commit()
            finally:
                conn.close()

            deleted = delete_voice_transcript_cache(account_dir)
            conn = sqlite3.connect(str(message_db))
            try:
                packed_info = conn.execute(
                    "SELECT packed_info_data FROM message WHERE server_id = ?",
                    (9007199254740993,),
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(deleted["deletedRows"], 1)
        self.assertEqual(deleted["nativeDeleted"], 0)
        self.assertEqual(packed_info, SYNTHETIC_TRANSCRIPT_BLOB)
        self.assertEqual(_extract_voice_transcript_from_packed_info(packed_info), SYNTHETIC_TRANSCRIPT)


if __name__ == "__main__":
    unittest.main()
