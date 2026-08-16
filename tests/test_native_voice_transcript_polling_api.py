from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import voice_transcription  # noqa: E402
from wechat_decrypt_tool.routers import chat_media  # noqa: E402


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


class NativeVoiceTranscriptPollingApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(chat_media.router)
        self.client = TestClient(
            app,
            base_url="http://127.0.0.1:10392",
            client=("127.0.0.1", 50000),
        )

    def test_targeted_lookup_reads_only_requested_completed_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            conn = sqlite3.connect(str(account_dir / "message_0.db"))
            try:
                conn.execute(
                    "CREATE TABLE Msg_demo (server_id INTEGER, local_type INTEGER, packed_info_data BLOB)"
                )
                conn.executemany(
                    "INSERT INTO Msg_demo VALUES (?, 34, ?)",
                    [
                        (111, _completed_native_payload("不是目标")),
                        (222, _completed_native_payload("目标微信原生文字")),
                    ],
                )
                conn.commit()
            finally:
                conn.close()

            with patch.object(
                voice_transcription,
                "_list_realtime_native_voice_transcripts",
            ) as realtime_lookup:
                text = voice_transcription.lookup_native_voice_transcript(account_dir, 222)

        self.assertEqual(text, "目标微信原生文字")
        realtime_lookup.assert_not_called()

    def test_native_poll_endpoint_preserves_large_server_id_and_does_not_use_whisper(self):
        server_id = 9007199254740993
        account_dir = Path("wxid_native_poll")
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=account_dir) as resolve,
            patch.object(
                chat_media,
                "resolve_native_voice_target",
                return_value=(4294967295, server_id, "微信已经生成的文字"),
            ) as lookup,
            patch.object(chat_media, "get_voice_transcription_service") as whisper,
        ):
            response = self.client.get(
                "/api/chat/media/voice/transcription/native",
                params={
                    "account": "wxid_native_poll",
                    "username": "wxid_friend",
                    "server_id": str(server_id),
                    "local_id": "4294967295",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "success",
                "serverId": str(server_id),
                "localId": "4294967295",
                "requestId": "",
                "text": "微信已经生成的文字",
                "language": "",
                "model": "wechat-native",
            },
        )
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        resolve.assert_called_once_with("wxid_native_poll")
        lookup.assert_called_once_with(
            account_dir,
            conversation="wxid_friend",
            server_id=server_id,
            local_id=4294967295,
        )
        whisper.assert_not_called()

    def test_native_status_is_passive_and_scoped_to_selected_account(self):
        account_dir = Path("wxid_native_status")
        expected = {
            "available": False,
            "reason": "runtime_trigger_e2e_not_validated",
            "version": "4.1.12.26",
            "pid": 42,
        }
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=account_dir) as resolve,
            patch.object(chat_media, "native_bridge_status", return_value=expected) as status,
        ):
            response = self.client.get(
                "/api/chat/media/voice/transcription/native/status",
                params={"account": "wxid_native_status"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        resolve.assert_called_once_with("wxid_native_status")
        status.assert_called_once_with(account_dir)

    def test_targeted_lookup_uses_exact_server_id_in_realtime_wcdb(self):
        server_id = 9007199254740993
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "account"
            message_dir = Path(tmp) / "raw" / "message"
            message_dir.mkdir(parents=True)
            (message_dir / "message_0.db").touch()
            realtime = Mock(db_storage_dir=message_dir.parent, handle=1, lock=threading.Lock())

            def exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertTrue(str(path).endswith("message_0.db"))
                if "sqlite_master" in sql:
                    return [{"name": "Msg_demo"}]
                self.assertIn(f"server_id = {server_id}", sql)
                return [{
                    "server_id": server_id,
                    "packed_info_data": _completed_native_payload("realtime 定向结果").hex(),
                }]

            with (
                patch(
                    "wechat_decrypt_tool.wcdb_realtime.WCDB_REALTIME.ensure_connected",
                    return_value=realtime,
                ),
                patch(
                    "wechat_decrypt_tool.wcdb_realtime.exec_query",
                    side_effect=exec_query,
                ),
            ):
                text = voice_transcription.lookup_native_voice_transcript(account_dir, server_id)

        self.assertEqual(text, "realtime 定向结果")

    def test_native_poll_endpoint_returns_pending_without_triggering_recognition(self):
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_pending")),
            patch.object(chat_media, "resolve_native_voice_target", return_value=(9, 123, "")),
        ):
            response = self.client.get(
                "/api/chat/media/voice/transcription/native",
                params={
                    "account": "wxid_pending",
                    "username": "wxid_friend",
                    "server_id": "123",
                    "local_id": "9",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "pending",
                "serverId": "123",
                "localId": "9",
                "requestId": "",
                "text": "",
                "language": "",
                "model": "",
            },
        )

    def test_native_poll_endpoint_rejects_non_positive_server_id(self):
        response = self.client.get(
            "/api/chat/media/voice/transcription/native",
            params={
                "account": "wxid_pending",
                "username": "wxid_friend",
                "server_id": "0",
                "local_id": "9",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_native_poll_reads_only_the_exact_callback_request(self):
        server_id = 9007199254740993
        entry = SimpleNamespace(
            request_id="request-current",
            status="success",
            text="bridge 回调文字",
            error_code="",
            error_message="",
        )
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_callback")),
            patch.object(
                chat_media,
                "lookup_native_voice_transcript_cache",
                return_value=entry,
            ) as lookup,
        ):
            response = self.client.get(
                "/api/chat/media/voice/transcription/native",
                params={
                    "account": "wxid_callback",
                    "username": "wxid_friend",
                    "server_id": str(server_id),
                    "local_id": "7",
                    "request_id": "request-current",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["model"], "wechat-native")
        self.assertEqual(response.json()["requestId"], "request-current")
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        lookup.assert_called_once_with(
            Path("wxid_callback"),
            server_id,
            conversation="wxid_friend",
            local_id=7,
            request_id="request-current",
            strict=True,
        )

    def test_native_poll_does_not_return_a_different_request_generation(self):
        entry = SimpleNamespace(
            request_id="request-newer",
            status="success",
            text="不应返回",
            error_code="",
            error_message="",
        )
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_callback")),
            patch.object(chat_media, "lookup_native_voice_transcript_cache", return_value=entry),
        ):
            response = self.client.get(
                "/api/chat/media/voice/transcription/native",
                params={
                    "account": "wxid_callback",
                    "username": "wxid_friend",
                    "server_id": "123",
                    "local_id": "7",
                    "request_id": "request-old",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "expired")
        self.assertEqual(response.json()["text"], "")
        self.assertEqual(response.json()["code"], "native_result_expired")

    def test_native_poll_surfaces_cached_terminal_error_without_text(self):
        entry = SimpleNamespace(
            request_id="request-error",
            status="error",
            text="",
            error_code="native_callback_released",
            error_message="微信原生语音转文字未返回结果。",
        )
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_callback")),
            patch.object(chat_media, "lookup_native_voice_transcript_cache", return_value=entry),
        ):
            response = self.client.get(
                "/api/chat/media/voice/transcription/native",
                params={
                    "account": "wxid_callback",
                    "username": "wxid_friend",
                    "server_id": "123",
                    "local_id": "7",
                    "request_id": "request-error",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["text"], "")
        self.assertEqual(response.json()["code"], "native_callback_released")

    def test_native_poll_rejects_malformed_request_id_without_touching_cache(self):
        with patch.object(chat_media, "lookup_native_voice_transcript_cache") as lookup:
            response = self.client.get(
                "/api/chat/media/voice/transcription/native",
                params={
                    "account": "wxid_callback",
                    "username": "wxid_friend",
                    "server_id": "123",
                    "local_id": "7",
                    "request_id": "x" * 257,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "invalid_request_id")
        lookup.assert_not_called()

    def test_native_result_get_requires_loopback_client(self):
        remote = TestClient(
            self.client.app,
            base_url="http://127.0.0.1:10392",
            client=("192.0.2.10", 50000),
        )
        response = remote.get(
            "/api/chat/media/voice/transcription/native",
            params={
                "account": "wxid_callback",
                "username": "wxid_friend",
                "server_id": "123",
                "local_id": "7",
                "request_id": "request-1",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_native_cache_batch_restores_only_exact_conversation_and_local_id(self):
        account_dir = Path("wxid_callback")
        entry = SimpleNamespace(
            status="success",
            request_id="request-success",
            text="持久 callback 结果",
            error_code="",
            error_message="",
        )
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=account_dir),
            patch.object(
                chat_media,
                "lookup_native_voice_transcript_cache",
                return_value=entry,
            ) as lookup,
            patch.object(chat_media, "get_voice_transcription_service") as whisper,
        ):
            response = self.client.post(
                "/api/chat/media/voice/transcription/native/cache_lookup",
                json={
                    "account": "wxid_callback",
                    "username": "wxid_friend",
                    "items": [{"server_id": "9007199254740993", "local_id": "7"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json(),
            {
                "status": "success",
                "items": [{
                    "serverId": "9007199254740993",
                    "localId": "7",
                    "status": "success",
                    "requestId": "request-success",
                    "text": "持久 callback 结果",
                    "language": "",
                    "model": "wechat-native",
                }],
            },
        )
        lookup.assert_called_once_with(
            account_dir,
            9007199254740993,
            conversation="wxid_friend",
            local_id=7,
            strict=True,
        )
        whisper.assert_not_called()

    def test_native_cache_batch_restores_pending_and_error_generations(self):
        account_dir = Path("wxid_callback")
        cases = (
            (
                SimpleNamespace(
                    status="pending",
                    request_id="request-pending",
                    text="",
                    error_code="",
                    error_message="",
                ),
                {
                    "serverId": "9007199254740993",
                    "localId": "7",
                    "status": "pending",
                    "requestId": "request-pending",
                    "pollAfterMs": 1200,
                },
            ),
            (
                SimpleNamespace(
                    status="error",
                    request_id="request-error",
                    text="",
                    error_code="native_trigger_timeout",
                    error_message="微信原生语音转文字等待超时。",
                ),
                {
                    "serverId": "9007199254740993",
                    "localId": "7",
                    "status": "error",
                    "requestId": "request-error",
                    "code": "native_trigger_timeout",
                    "message": "微信原生语音转文字等待超时。",
                },
            ),
        )
        for entry, expected in cases:
            with (
                self.subTest(status=entry.status),
                patch.object(chat_media, "_resolve_account_dir", return_value=account_dir),
                patch.object(
                    chat_media,
                    "lookup_native_voice_transcript_cache",
                    return_value=entry,
                ),
                patch.object(chat_media, "get_voice_transcription_service") as whisper,
            ):
                response = self.client.post(
                    "/api/chat/media/voice/transcription/native/cache_lookup",
                    json={
                        "account": "wxid_callback",
                        "username": "wxid_friend",
                        "items": [{"server_id": "9007199254740993", "local_id": "7"}],
                    },
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "success", "items": [expected]})
            whisper.assert_not_called()


if __name__ == "__main__":
    unittest.main()
