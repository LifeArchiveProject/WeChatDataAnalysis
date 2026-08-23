from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import chat_media  # noqa: E402


class TestVoiceTranscriptionManagementApi(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(chat_media.router)
        self.client = TestClient(
            app,
            base_url="http://127.0.0.1:10392",
            client=("127.0.0.1", 50000),
        )

    def test_model_can_be_selected_from_settings_endpoint(self):
        configuration = {"model": "small", "modelReady": True}
        with patch.object(chat_media, "set_voice_transcription_model", return_value=configuration) as setter:
            response = self.client.put(
                "/api/chat/media/voice/transcription/settings",
                json={"model": "small"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["configuration"], configuration)
        setter.assert_called_once_with("small")

    def test_model_download_and_delete_endpoints_use_bounded_manager(self):
        download = {
            "jobId": "model-small-1",
            "model": "small",
            "status": "running",
            "percent": 37,
            "downloadedBytes": 370,
            "totalBytes": 1000,
            "stage": "downloading",
        }
        with patch.object(chat_media.VOICE_MODEL_DOWNLOAD_MANAGER, "start", return_value=download) as start:
            response = self.client.post(
                "/api/chat/media/voice/transcription/models/small/download"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), download)
        start.assert_called_once_with("small")

        with patch.object(chat_media.VOICE_MODEL_DOWNLOAD_MANAGER, "get", return_value=download) as get:
            response = self.client.get(
                "/api/chat/media/voice/transcription/models/downloads/model-small-1"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), download)
        get.assert_called_once_with("model-small-1")

        deleted = {"status": "success", "model": "small", "deleted": True, "freedBytes": 12}
        with patch.object(chat_media, "delete_voice_model", return_value=deleted) as delete:
            response = self.client.delete(
                "/api/chat/media/voice/transcription/models/small"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), deleted)
        delete.assert_called_once_with("small")

    def test_model_busy_conflicts_are_reported_as_http_409(self):
        busy = chat_media.VoiceTranscriptionError("model_busy", "模型正在使用")
        with patch.object(chat_media.VOICE_MODEL_DOWNLOAD_MANAGER, "start", side_effect=busy):
            response = self.client.post(
                "/api/chat/media/voice/transcription/models/small/download"
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "model_busy")

        with patch.object(chat_media, "set_voice_transcription_model", side_effect=busy):
            response = self.client.put(
                "/api/chat/media/voice/transcription/settings",
                json={"model": "small"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "model_busy")

        with patch.object(chat_media, "delete_voice_model", side_effect=busy):
            response = self.client.delete(
                "/api/chat/media/voice/transcription/models/small"
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "model_busy")

    def test_direct_transcription_uses_and_releases_current_service_lease(self):
        result = {"status": "success", "serverId": 123, "text": "完成", "cached": False}
        service = SimpleNamespace(
            ensure_available=Mock(return_value={"available": True}),
            transcribe_voice=Mock(return_value=result),
        )
        service_lease = SimpleNamespace(service=service, release=Mock())
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")),
            patch.object(chat_media, "capture_voice_transcript_cache_generation", return_value=42),
            patch.object(
                chat_media,
                "acquire_voice_transcription_service_lease",
                return_value=service_lease,
            ) as acquire,
        ):
            response = self.client.post(
                "/api/chat/media/voice/transcription",
                json={"account": "wxid_demo", "server_id": 123, "force": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        acquire.assert_called_once_with()
        service.ensure_available.assert_called_once_with()
        service.transcribe_voice.assert_called_once_with(
            account_dir=Path("wxid_demo"),
            server_id=123,
            force=False,
            cache_generation=42,
        )
        service_lease.release.assert_called_once_with()

    def test_direct_transcription_maps_retired_service_to_conflict_and_releases_lease(self):
        retired = chat_media.VoiceTranscriptionError("service_retired", "配置已更新")
        service = SimpleNamespace(ensure_available=Mock(side_effect=retired), transcribe_voice=Mock())
        service_lease = SimpleNamespace(service=service, release=Mock())
        with patch.object(
            chat_media,
            "acquire_voice_transcription_service_lease",
            return_value=service_lease,
        ):
            response = self.client.post(
                "/api/chat/media/voice/transcription",
                json={"account": "wxid_demo", "server_id": 123, "force": False},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "service_retired")
        service.transcribe_voice.assert_not_called()
        service_lease.release.assert_called_once_with()

    def test_batch_endpoint_starts_and_reports_progress(self):
        job = {
            "jobId": "voice-batch-1",
            "account": "wxid_demo",
            "status": "running",
            "total": 10,
            "completed": 2,
            "percent": 20,
        }
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")),
            patch.object(chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER, "start", return_value=job) as start,
        ):
            response = self.client.post(
                "/api/chat/media/voice/transcription/batch",
                json={"account": "wxid_demo", "force": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), job)
        start.assert_called_once_with(
            account="wxid_demo",
            account_dir=Path("wxid_demo"),
            force=False,
            concurrency=None,
        )

    def test_batch_endpoint_forwards_requested_concurrency(self):
        job = {
            "jobId": "voice-batch-2",
            "account": "wxid_demo",
            "status": "queued",
            "requestedConcurrency": 37,
            "concurrency": 37,
        }
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")),
            patch.object(chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER, "start", return_value=job) as start,
        ):
            response = self.client.post(
                "/api/chat/media/voice/transcription/batch",
                json={"account": "wxid_demo", "force": False, "concurrency": 37},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), job)
        start.assert_called_once_with(
            account="wxid_demo",
            account_dir=Path("wxid_demo"),
            force=False,
            concurrency=37,
        )

    def test_batch_endpoint_forwards_wechat_native_engine(self):
        job = {"jobId": "voice-native-1", "engine": "wechat-native", "status": "queued"}
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")),
            patch.object(chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER, "start", return_value=job) as start,
        ):
            response = self.client.post(
                "/api/chat/media/voice/transcription/batch",
                json={"account": "wxid_demo", "engine": "wechat-native"},
            )

        self.assertEqual(response.status_code, 200)
        start.assert_called_once_with(
            account="wxid_demo",
            account_dir=Path("wxid_demo"),
            force=False,
            concurrency=None,
            engine="wechat-native",
        )

    def test_batch_endpoint_rejects_negative_or_non_integer_concurrency(self):
        for concurrency in (-1, 1.5, "5", True):
            with self.subTest(concurrency=concurrency):
                response = self.client.post(
                    "/api/chat/media/voice/transcription/batch",
                    json={"account": "wxid_demo", "concurrency": concurrency},
                )
                self.assertEqual(response.status_code, 422)

    def test_cache_delete_requires_account_and_forwards_resolved_account(self):
        missing = self.client.delete("/api/chat/media/voice/transcription/cache")
        self.assertEqual(missing.status_code, 422)

        deleted = {
            "status": "success",
            "account": "wxid_demo",
            "deletedRows": 4,
            "deletedMessages": 3,
            "nativeDeleted": 0,
        }
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")) as resolve,
            patch.object(
                chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER,
                "delete_cache_if_idle",
                return_value=deleted,
            ) as delete,
        ):
            response = self.client.delete(
                "/api/chat/media/voice/transcription/cache?account=wxid_demo"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), deleted)
        resolve.assert_called_once_with("wxid_demo")
        delete.assert_called_once_with(account="wxid_demo", account_dir=Path("wxid_demo"))

    def test_cache_delete_rejects_active_batch_and_maps_storage_failure_safely(self):
        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")),
            patch.object(
                chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER,
                "delete_cache_if_idle",
                side_effect=chat_media.VoiceTranscriptionError("batch_busy", "正在转写"),
            ),
        ):
            busy = self.client.delete(
                "/api/chat/media/voice/transcription/cache?account=wxid_demo"
            )
        self.assertEqual(busy.status_code, 409)
        self.assertEqual(busy.json()["detail"]["code"], "batch_busy")

        with (
            patch.object(chat_media, "_resolve_account_dir", return_value=Path("wxid_demo")),
            patch.object(
                chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER,
                "delete_cache_if_idle",
                side_effect=chat_media.VoiceTranscriptionError("cache_delete_failed", "删除失败"),
            ),
        ):
            failed = self.client.delete(
                "/api/chat/media/voice/transcription/cache?account=wxid_demo"
            )
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(failed.json()["detail"], {"code": "cache_delete_failed", "message": "删除失败"})

    def test_cache_delete_is_local_only(self):
        response = self.client.delete(
            "/api/chat/media/voice/transcription/cache?account=wxid_demo",
            headers={"Origin": "https://example.invalid"},
        )
        self.assertEqual(response.status_code, 403)

    def test_global_cache_delete_uses_explicit_endpoint(self):
        deleted = {
            "status": "success",
            "deletedRows": 7,
            "deletedMessages": 5,
            "accountsScanned": 3,
            "accountsChanged": 2,
            "nativeDeleted": 0,
        }
        with patch.object(
            chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER,
            "delete_all_caches_if_idle",
            return_value=deleted,
        ) as delete:
            response = self.client.delete(
                "/api/chat/media/voice/transcription/cache/all"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), deleted)
        delete.assert_called_once_with()

    def test_global_cache_delete_rejects_active_batch_and_nonlocal_origin(self):
        with patch.object(
            chat_media.VOICE_TRANSCRIPTION_BATCH_MANAGER,
            "delete_all_caches_if_idle",
            side_effect=chat_media.VoiceTranscriptionError("batch_busy", "正在转写"),
        ):
            busy = self.client.delete(
                "/api/chat/media/voice/transcription/cache/all"
            )
        self.assertEqual(busy.status_code, 409)
        self.assertEqual(busy.json()["detail"]["code"], "batch_busy")

        remote = self.client.delete(
            "/api/chat/media/voice/transcription/cache/all",
            headers={"Origin": "https://example.invalid"},
        )
        self.assertEqual(remote.status_code, 403)

    def test_expensive_mutations_reject_nonlocal_origin(self):
        response = self.client.post(
            "/api/chat/media/voice/transcription/models/small/download",
            headers={"Origin": "https://example.invalid"},
        )
        self.assertEqual(response.status_code, 403)

    def test_expensive_mutations_reject_nonlocal_client(self):
        remote_client = TestClient(
            self.client.app,
            base_url="http://192.0.2.1:10392",
            client=("192.0.2.55", 50000),
        )
        response = remote_client.post(
            "/api/chat/media/voice/transcription/models/small/download"
        )
        self.assertEqual(response.status_code, 403)

    def test_settings_rejects_non_atomic_model_and_device_update(self):
        response = self.client.put(
            "/api/chat/media/voice/transcription/settings",
            json={"model": "small", "device": "cpu"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
