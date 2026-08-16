from __future__ import annotations

import hashlib
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_voice_transcription as native  # noqa: E402


def _varint(value: int) -> bytes:
    encoded = bytearray()
    remaining = int(value)
    while True:
        byte = remaining & 0x7F
        remaining >>= 7
        encoded.append(byte | (0x80 if remaining else 0))
        if not remaining:
            return bytes(encoded)


def _completed_native_payload(text: str) -> bytes:
    text_bytes = text.encode("utf-8")
    nested = b"\x08\x02\x12" + _varint(len(text_bytes)) + text_bytes
    return b"\x2a" + _varint(len(nested)) + nested


def _seed_voice_row(
    account_dir: Path,
    *,
    conversation: str,
    local_id: int,
    server_id: int,
    packed_info_data: bytes,
) -> None:
    table = f"Msg_{hashlib.md5(conversation.encode('utf-8')).hexdigest()}"
    conn = sqlite3.connect(str(account_dir / "message_0.db"))
    try:
        conn.execute(
            f'CREATE TABLE "{table}" '
            "(local_id INTEGER, server_id INTEGER, local_type INTEGER, packed_info_data BLOB)"
        )
        conn.execute(
            f'INSERT INTO "{table}" VALUES (?, ?, 34, ?)',
            (local_id, server_id, packed_info_data),
        )
        conn.commit()
    finally:
        conn.close()


def test_success_cache_is_persistent_normalized_and_scoped(tmp_path: Path):
    account_dir = tmp_path / "wxid_first"
    account_dir.mkdir()
    other_account = tmp_path / "wxid_second"
    server_id = (1 << 64) - 1

    stored = native.mark_native_voice_transcript_success(
        account_dir=account_dir,
        conversation="room@chatroom",
        server_id=server_id,
        local_id=7279,
        request_id="request-1",
        text="  Cafe\u0301\r\n第二行  ",
    )

    assert stored.status == "success"
    assert stored.text == "Café\n第二行"
    assert stored.expires_at is None
    assert native.lookup_cached_native_voice_transcript(account_dir, server_id) == "Café\n第二行"
    assert native.lookup_native_voice_transcript_cache(
        account_dir,
        server_id,
        conversation="room@chatroom",
        local_id=7279,
        now=stored.updated_at + 10 * 365 * 24 * 60 * 60,
    ) == stored
    assert native.lookup_native_voice_transcript_cache(
        account_dir,
        server_id,
        conversation="wxid_wrong",
        local_id=7279,
    ) is None
    assert native.lookup_native_voice_transcript_cache(
        account_dir,
        server_id,
        conversation="room@chatroom",
        local_id=7280,
    ) is None
    assert native.lookup_native_voice_transcript_cache(other_account, server_id) is None
    assert not (other_account / "_cache").exists()
    assert (account_dir / "_cache" / "native_voice_transcripts.sqlite3").is_file()


def test_pending_and_error_expire_while_success_does_not(monkeypatch, tmp_path: Path):
    account_dir = tmp_path / "wxid_ttl"
    account_dir.mkdir()
    clock = [100.0]
    monkeypatch.setattr(native.time, "time", lambda: clock[0])
    key = {
        "account_dir": account_dir,
        "conversation": "wxid_friend",
        "server_id": 123,
        "local_id": 7,
        "request_id": "request-ttl",
    }

    pending = native.mark_native_voice_transcript_pending(**key, ttl_seconds=2.0)
    assert native.lookup_native_voice_transcript_cache(account_dir, 123, now=101.9) == pending
    assert native.lookup_native_voice_transcript_cache(account_dir, 123, now=102.0) is None
    assert native.lookup_native_voice_transcript_cache(
        account_dir,
        123,
        request_id="request-ttl",
        now=102.0,
        include_expired=True,
    ) == pending
    assert native.lookup_native_voice_transcript_cache(
        account_dir,
        123,
        request_id="different-request",
        include_expired=True,
    ) is None

    clock[0] = 200.0
    error = native.mark_native_voice_transcript_error(
        **key,
        error_code="native_failed",
        error_message="temporary failure",
        ttl_seconds=3.0,
    )
    assert error.status == "error"
    assert error.text == ""
    clock[0] = 201.0
    assert native.mark_native_voice_transcript_pending(**key) == error
    assert native.lookup_native_voice_transcript_cache(account_dir, 123, now=202.9) == error
    assert native.lookup_native_voice_transcript_cache(account_dir, 123, now=203.0) is None

    clock[0] = 300.0
    success = native.mark_native_voice_transcript_success(**key, text="永久结果")
    assert success.expires_at is None
    assert native.lookup_native_voice_transcript_cache(account_dir, 123, now=10**12) == success


def test_callback_race_cannot_downgrade_success_or_overwrite_new_request(monkeypatch, tmp_path: Path):
    account_dir = tmp_path / "wxid_race"
    account_dir.mkdir()
    clock = [100.0]
    monkeypatch.setattr(native.time, "time", lambda: clock[0])
    common = {
        "account_dir": account_dir,
        "conversation": "wxid_friend",
        "server_id": 456,
        "local_id": 8,
    }

    success = native.mark_native_voice_transcript_success(
        **common,
        request_id="request-a",
        text="先完成",
    )
    clock[0] = 101.0
    assert native.mark_native_voice_transcript_pending(
        **common,
        request_id="request-a",
    ) == success

    second = {**common, "server_id": 457}
    native.mark_native_voice_transcript_pending(
        **second,
        request_id="request-old",
        ttl_seconds=1.0,
    )
    clock[0] = 102.0
    pending_new = native.mark_native_voice_transcript_pending(
        **second,
        request_id="request-new",
    )
    clock[0] = 103.0
    stale = native.mark_native_voice_transcript_error(
        **second,
        request_id="request-old",
        error_code="late_error",
    )
    assert stale == pending_new
    assert native.lookup_native_voice_transcript_cache(account_dir, 457) == pending_new


def test_new_pending_request_replaces_live_orphan_after_backend_restart(monkeypatch, tmp_path: Path):
    account_dir = tmp_path / "wxid_restart"
    account_dir.mkdir()
    clock = [100.0]
    monkeypatch.setattr(native.time, "time", lambda: clock[0])
    common = {
        "account_dir": account_dir,
        "conversation": "wxid_friend",
        "server_id": 458,
        "local_id": 9,
    }
    native.mark_native_voice_transcript_pending(
        **common,
        request_id="request-before-restart",
    )

    clock[0] = 101.0
    after_restart = native.mark_native_voice_transcript_pending(
        **common,
        request_id="request-after-restart",
    )
    stale_callback = native.mark_native_voice_transcript_success(
        **common,
        request_id="request-before-restart",
        text="过期任务的回调",
    )

    assert after_restart.status == "pending"
    assert after_restart.request_id == "request-after-restart"
    assert stale_callback == after_restart
    assert native.lookup_native_voice_transcript_cache(account_dir, 458) == after_restart


def test_concurrent_pending_and_success_writes_finish_as_success(tmp_path: Path):
    account_dir = tmp_path / "wxid_threads"
    account_dir.mkdir()
    common = {
        "account_dir": account_dir,
        "conversation": "wxid_friend",
        "server_id": 789,
        "local_id": 9,
        "request_id": "request-threaded",
    }

    def write(index: int):
        if index % 2:
            return native.mark_native_voice_transcript_success(**common, text="并发完成")
        return native.mark_native_voice_transcript_pending(**common)

    with ThreadPoolExecutor(max_workers=8) as executor:
        entries = list(executor.map(write, range(24)))

    assert len(entries) == 24
    final = native.lookup_native_voice_transcript_cache(account_dir, 789)
    assert final is not None
    assert final.status == "success"
    assert final.text == "并发完成"


def test_resolve_prefers_project_callback_success_over_packed_info(monkeypatch, tmp_path: Path):
    conversation = "wxid_friend"
    local_id = 7279
    server_id = 9007199254740993
    _seed_voice_row(
        tmp_path,
        conversation=conversation,
        local_id=local_id,
        server_id=server_id,
        packed_info_data=_completed_native_payload("packed_info 旧结果"),
    )
    native.mark_native_voice_transcript_success(
        account_dir=tmp_path,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
        request_id="request-callback",
        text="项目回调结果",
    )
    monkeypatch.setattr(
        native,
        "_query_realtime_voice_targets",
        lambda *_args, **_kwargs: native._VoiceTargetQueryResult(set(), {}, 0, []),
    )

    assert native.resolve_native_voice_target(
        tmp_path,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
    ) == (local_id, server_id, "项目回调结果")


def test_corrupt_project_cache_falls_back_to_packed_info(monkeypatch, tmp_path: Path):
    conversation = "wxid_friend"
    local_id = 42
    server_id = 2468
    _seed_voice_row(
        tmp_path,
        conversation=conversation,
        local_id=local_id,
        server_id=server_id,
        packed_info_data=_completed_native_payload("packed_info 可用结果"),
    )
    cache_path = tmp_path / "_cache" / "native_voice_transcripts.sqlite3"
    cache_path.parent.mkdir()
    cache_path.write_bytes(b"not a sqlite database")
    monkeypatch.setattr(
        native,
        "_query_realtime_voice_targets",
        lambda *_args, **_kwargs: native._VoiceTargetQueryResult(set(), {}, 0, []),
    )

    assert native.resolve_native_voice_target(
        tmp_path,
        conversation=conversation,
        server_id=server_id,
        local_id=local_id,
    ) == (local_id, server_id, "packed_info 可用结果")

    with pytest.raises(native.NativeVoiceTriggerError) as raised:
        native.lookup_native_voice_transcript_cache(tmp_path, server_id, strict=True)
    assert raised.value.code == "native_result_store_unavailable"
