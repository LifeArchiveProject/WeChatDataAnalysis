import hashlib
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from wechat_decrypt_tool.native_voice_transcription import (
    NativeVoiceBatchTarget,
    list_native_voice_batch_targets,
)
from wechat_decrypt_tool.voice_transcription import VoiceTranscriptionBatchManager


def test_native_batch_maps_voice_rows_back_to_conversations():
    with tempfile.TemporaryDirectory() as tmp:
        account_dir = Path(tmp)
        conversation = "demo@chatroom"
        table = f"Msg_{hashlib.md5(conversation.encode()).hexdigest()}"
        conn = sqlite3.connect(str(account_dir / "message_0.db"))
        conn.execute("CREATE TABLE Name2Id (user_name TEXT, is_session INTEGER)")
        conn.execute("INSERT INTO Name2Id VALUES (?, 1)", (conversation,))
        conn.execute(
            f'CREATE TABLE "{table}" '
            "(local_id INTEGER, server_id INTEGER, local_type INTEGER, packed_info_data BLOB)"
        )
        conn.execute(f'INSERT INTO "{table}" VALUES (7, 9, 34, NULL)')
        conn.commit()
        conn.close()

        with patch(
            "wechat_decrypt_tool.native_voice_transcription.account_prefers_decrypted_snapshot",
            return_value=True,
        ):
            targets = list_native_voice_batch_targets(account_dir)

    assert targets == [NativeVoiceBatchTarget(conversation, 9, 7, "")]


def test_native_batch_runs_serial_native_items_without_loading_whisper():
    manager = VoiceTranscriptionBatchManager()
    target = NativeVoiceBatchTarget("demo@chatroom", 9, 7, "微信已有文字")
    with (
        tempfile.TemporaryDirectory() as tmp,
        patch(
            "wechat_decrypt_tool.native_core_voice_asr.native_core_voice_asr_status",
            return_value={"available": True},
        ),
        patch(
            "wechat_decrypt_tool.native_voice_transcription.list_native_voice_batch_targets",
            return_value=[target],
        ),
        patch(
            "wechat_decrypt_tool.voice_transcription.has_voice_transcript_cache",
            return_value=False,
        ),
    ):
        job = manager.start(account="wxid_demo", account_dir=Path(tmp), engine="wechat-native")
        deadline = time.time() + 2
        while time.time() < deadline:
            job = manager.get(job["jobId"])
            if job["status"] not in {"queued", "running"}:
                break
            time.sleep(0.01)

    assert job["status"] == "done"
    assert job["engine"] == "wechat-native"
    assert job["concurrency"] == 1
    assert job["completed"] == job["success"] == job["native"] == 1
