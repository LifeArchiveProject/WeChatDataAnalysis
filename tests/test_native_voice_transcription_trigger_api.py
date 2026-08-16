from __future__ import annotations

import hashlib
import sqlite3
import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_voice_transcription  # noqa: E402
from wechat_decrypt_tool.native_voice_transcription import (  # noqa: E402
    NativeVoiceTriggerError,
    NativeVoiceTriggerReceipt,
    parse_native_voice_message_id,
    trigger_native_voice_transcription,
)
from wechat_decrypt_tool.routers import chat_media  # noqa: E402


class FakeNativeVoiceTriggerTransport:
    def __init__(self, status: str = "accepted", request_id: str = "native-request-1") -> None:
        self.status = status
        self.request_id = request_id
        self.commands = []

    def trigger(self, command):
        self.commands.append(command)
        return NativeVoiceTriggerReceipt(status=self.status, request_id=self.request_id)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_media.router)
    return TestClient(
        app,
        base_url="http://127.0.0.1:10392",
        client=("127.0.0.1", 50000),
    )


def _seed_voice_row(
    account_dir: Path,
    *,
    conversation: str,
    local_id: int,
    server_id: int,
    local_type: int = 34,
    packed_info_data: bytes | None = None,
    db_name: str = "message_0.db",
) -> None:
    table = f"Msg_{hashlib.md5(conversation.encode('utf-8')).hexdigest()}"
    db_path = account_dir / db_name
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{table}" '
            "(local_id INTEGER, server_id INTEGER, local_type INTEGER, packed_info_data BLOB)"
        )
        conn.execute(
            f'INSERT INTO "{table}" VALUES (?, ?, ?, ?)',
            (local_id, server_id, local_type, packed_info_data),
        )
        conn.commit()
    finally:
        conn.close()


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


def test_trigger_fast_path_returns_existing_native_text_without_transport(monkeypatch, tmp_path: Path):
    server_id = "9007199254740993"
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=7279,
        server_id=int(server_id),
        packed_info_data=_completed_native_payload("微信已有文字"),
    )

    class MustNotRun:
        def trigger(self, _command):
            raise AssertionError("transport must not run for an existing transcript")

    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        native_voice_transcription,
        "get_native_voice_trigger_transport",
        lambda: MustNotRun(),
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={
            "account": "wxid_account",
            "username": "wxid_friend",
            "server_id": server_id,
        },
    )

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    assert response.json() == {
        "status": "success",
        "serverId": server_id,
        "localId": "7279",
        "account": tmp_path.name,
        "conversation": "wxid_friend",
        "language": "",
        "text": "微信已有文字",
        "model": "wechat-native",
        "requestId": "",
        "pollAfterMs": 0,
    }


def test_trigger_dispatches_once_and_returns_accepted_without_polling(monkeypatch, tmp_path: Path):
    transport = FakeNativeVoiceTriggerTransport()
    (tmp_path / "account.json").write_text(
        '{"username":"wxid_native_account"}',
        encoding="utf-8",
    )
    _seed_voice_row(
        tmp_path,
        conversation="room@chatroom",
        local_id=7279,
        server_id=9038636853230485365,
    )
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        native_voice_transcription,
        "get_native_voice_trigger_transport",
        lambda: transport,
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={
            "account": "wxid_account",
            "username": "room@chatroom",
            "server_id": "9038636853230485365",
            "local_id": "7279",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["serverId"] == "9038636853230485365"
    assert payload["localId"] == "7279"
    assert payload["requestId"] == "native-request-1"
    assert payload["pollAfterMs"] == 1200
    assert len(transport.commands) == 1
    command = transport.commands[0]
    assert command.account_dir == tmp_path
    assert command.account == "wxid_native_account"
    assert command.conversation == "room@chatroom"
    assert command.server_id == 9038636853230485365
    assert command.local_id == 7279


def test_imported_snapshot_lookup_never_falls_through_to_realtime(monkeypatch, tmp_path: Path):
    transport = FakeNativeVoiceTriggerTransport()
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=7279,
        server_id=9038636853230485365,
    )
    (tmp_path / "session.db").touch()
    (tmp_path / "contact.db").touch()
    (tmp_path / "_source.json").write_text(
        '{"import_mode":"manual_import"}',
        encoding="utf-8",
    )

    def fail_realtime(*_args, **_kwargs):
        raise AssertionError("imported snapshot must not query realtime WCDB")

    monkeypatch.setattr(
        native_voice_transcription,
        "_query_realtime_voice_targets",
        fail_realtime,
    )

    result = trigger_native_voice_transcription(
        account_dir=tmp_path,
        conversation="wxid_friend",
        server_id="9038636853230485365",
        local_id="7279",
        transport=transport,
    )

    assert result["status"] == "accepted"
    assert len(transport.commands) == 1


def test_local_id_is_resolved_in_the_selected_conversation_before_dispatch(tmp_path: Path):
    conversation = "wxid_friend"
    server_id = 9038636853230485365
    table = f"Msg_{hashlib.md5(conversation.encode('utf-8')).hexdigest()}"
    db_path = tmp_path / "message_0.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            f'CREATE TABLE "{table}" (local_id INTEGER, server_id INTEGER, local_type INTEGER)'
        )
        conn.executemany(
            f'INSERT INTO "{table}" VALUES (?, ?, ?)',
            [
                (7279, server_id, 34),
                (7279, server_id + 1, 3),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    transport = FakeNativeVoiceTriggerTransport(status="pending", request_id="already-running")

    result = trigger_native_voice_transcription(
        account_dir=tmp_path,
        conversation=conversation,
        local_id="7279",
        transport=transport,
    )

    assert result["status"] == "pending"
    assert result["serverId"] == str(server_id)
    assert result["localId"] == "7279"
    assert result["requestId"] == "already-running"
    assert len(transport.commands) == 1
    assert transport.commands[0].server_id == server_id


@pytest.mark.parametrize("request_id", ["", "x" * 257, "bad\nrequest"])
def test_transport_must_return_a_valid_request_id(tmp_path: Path, request_id: str):
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=7,
        server_id=123,
    )
    transport = FakeNativeVoiceTriggerTransport(request_id=request_id)

    with pytest.raises(NativeVoiceTriggerError) as caught:
        trigger_native_voice_transcription(
            account_dir=tmp_path,
            conversation="wxid_friend",
            server_id="123",
            local_id="7",
            transport=transport,
        )

    assert caught.value.code == "native_transport_invalid_response"
    assert len(transport.commands) == 1


def test_trigger_request_rejects_json_numbers_instead_of_coercing_them():
    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={
            "account": "wxid_account",
            "username": "wxid_friend",
            "server_id": 9007199254740993,
        },
    )

    assert response.status_code == 422


def test_unavailable_transport_is_explicitly_reported(monkeypatch, tmp_path: Path):
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=7,
        server_id=123,
    )
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        native_voice_transcription,
        "get_native_voice_trigger_transport",
        lambda: native_voice_transcription.UnavailableNativeVoiceTriggerTransport(),
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"account": "wxid_account", "username": "wxid_friend", "server_id": "123"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "native_transport_unavailable"


@pytest.mark.parametrize(
    "error_code",
    ["native_weixin_not_running", "native_weixin_version_unsupported"],
)
def test_native_weixin_unavailable_errors_are_503(monkeypatch, tmp_path: Path, error_code: str):
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=7,
        server_id=123,
    )

    class RejectingTransport:
        def trigger(self, _command):
            raise NativeVoiceTriggerError(error_code, "native unavailable")

    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        native_voice_transcription,
        "get_native_voice_trigger_transport",
        lambda: RejectingTransport(),
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"account": "wxid_account", "username": "wxid_friend", "server_id": "123"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == error_code


def test_trigger_rejects_noncanonical_or_missing_string_ids(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    client = _client()

    leading_zero = client.post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"account": "wxid_account", "username": "wxid_friend", "server_id": "00123"},
    )
    missing = client.post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"account": "wxid_account", "username": "wxid_friend"},
    )

    assert leading_zero.status_code == 400
    assert leading_zero.json()["detail"]["code"] == "invalid_message_id"
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "missing_message_id"


def test_fast_path_cannot_read_a_server_id_from_another_conversation(monkeypatch, tmp_path: Path):
    server_id = 9007199254740993
    _seed_voice_row(
        tmp_path,
        conversation="wxid_other_friend",
        local_id=8,
        server_id=server_id,
        packed_info_data=_completed_native_payload("不应跨会话读取"),
    )
    transport = FakeNativeVoiceTriggerTransport()
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        native_voice_transcription,
        "get_native_voice_trigger_transport",
        lambda: transport,
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={
            "account": "wxid_account",
            "username": "wxid_selected_friend",
            "server_id": str(server_id),
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "voice_message_not_found"
    assert transport.commands == []


def test_two_supplied_ids_must_map_to_the_same_voice_row(monkeypatch, tmp_path: Path):
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=7,
        server_id=101,
    )
    _seed_voice_row(
        tmp_path,
        conversation="wxid_friend",
        local_id=8,
        server_id=102,
    )
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={
            "account": "wxid_account",
            "username": "wxid_friend",
            "server_id": "102",
            "local_id": "7",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "voice_message_id_mismatch"


def test_two_supplied_ids_allow_local_id_reuse_in_another_message_shard(
    monkeypatch,
    tmp_path: Path,
):
    conversation = "wxid_friend"
    exact_server_id = 1265681483748099968
    _seed_voice_row(
        tmp_path,
        conversation=conversation,
        local_id=342,
        server_id=5067469402983745468,
        db_name="message_1.db",
    )
    _seed_voice_row(
        tmp_path,
        conversation=conversation,
        local_id=342,
        server_id=exact_server_id,
        db_name="message_5.db",
    )
    transport = FakeNativeVoiceTriggerTransport()
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        native_voice_transcription,
        "get_native_voice_trigger_transport",
        lambda: transport,
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={
            "account": "wxid_account",
            "username": conversation,
            "server_id": str(exact_server_id),
            "local_id": "342",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["serverId"] == str(exact_server_id)
    assert response.json()["localId"] == "342"
    assert len(transport.commands) == 1
    assert transport.commands[0].server_id == exact_server_id
    assert transport.commands[0].local_id == 342


def test_account_is_required_and_blank_account_is_rejected():
    client = _client()

    missing = client.post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"username": "wxid_friend", "server_id": "123"},
    )
    blank = client.post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"account": "   ", "username": "wxid_friend", "server_id": "123"},
    )

    assert missing.status_code == 422
    assert blank.status_code == 400
    assert blank.json()["detail"]["code"] == "invalid_account"


def test_server_id_validation_falls_back_to_realtime_wcdb(monkeypatch, tmp_path: Path):
    conversation = "wxid_realtime_friend"
    server_id = 9038636853230485365
    (tmp_path / "message_0.db").write_bytes(b"not a sqlite database")
    message_dir = tmp_path / "raw" / "message"
    message_dir.mkdir(parents=True)
    (message_dir / "message_0.db").touch()
    realtime = Mock(db_storage_dir=message_dir.parent, handle=1, lock=threading.Lock())
    table = f"Msg_{hashlib.md5(conversation.encode('utf-8')).hexdigest()}"
    sql_calls = []

    def exec_query(_handle, *, kind, path, sql):
        assert kind == "message"
        assert str(path).endswith("message_0.db")
        sql_calls.append(sql)
        if "sqlite_master" in sql:
            return [{"name": table}]
        assert f"server_id = {server_id}" in sql
        return [{"local_id": 7279, "server_id": server_id}]

    monkeypatch.setattr(
        "wechat_decrypt_tool.wcdb_realtime.WCDB_REALTIME.ensure_connected",
        lambda _account_dir: realtime,
    )
    monkeypatch.setattr("wechat_decrypt_tool.wcdb_realtime.exec_query", exec_query)
    transport = FakeNativeVoiceTriggerTransport()

    result = trigger_native_voice_transcription(
        account_dir=tmp_path,
        conversation=conversation,
        server_id=str(server_id),
        transport=transport,
    )

    assert result["status"] == "accepted"
    assert result["serverId"] == str(server_id)
    assert result["localId"] == "7279"
    assert len(sql_calls) == 2
    assert len(transport.commands) == 1


def test_all_message_sources_failing_returns_explicit_503(monkeypatch, tmp_path: Path):
    (tmp_path / "message_0.db").write_bytes(b"not a sqlite database")
    monkeypatch.setattr(chat_media, "_resolve_account_dir", lambda _account: tmp_path)
    monkeypatch.setattr(
        "wechat_decrypt_tool.wcdb_realtime.WCDB_REALTIME.ensure_connected",
        lambda _account_dir: (_ for _ in ()).throw(RuntimeError("wcdb unavailable")),
    )

    response = _client().post(
        "/api/chat/media/voice/transcription/native/trigger",
        json={"account": "wxid_account", "username": "wxid_friend", "server_id": "123"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "native_message_lookup_unavailable"


def test_server_and_local_id_abi_boundaries_are_enforced():
    assert parse_native_voice_message_id(str((1 << 64) - 1), "server_id") == (1 << 64) - 1
    assert parse_native_voice_message_id(str((1 << 32) - 1), "local_id") == (1 << 32) - 1

    with pytest.raises(NativeVoiceTriggerError) as server_error:
        parse_native_voice_message_id(str(1 << 64), "server_id")
    with pytest.raises(NativeVoiceTriggerError) as local_error:
        parse_native_voice_message_id(str(1 << 32), "local_id")

    assert server_error.value.code == "invalid_message_id"
    assert local_error.value.code == "invalid_message_id"
