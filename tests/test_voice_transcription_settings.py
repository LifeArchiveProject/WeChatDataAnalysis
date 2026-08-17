from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close_logging_handlers() -> None:
    for logger_name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            try:
                logger.removeHandler(handler)
            except Exception:
                pass


def _local_client(app: FastAPI) -> TestClient:
    return TestClient(
        app,
        base_url="http://127.0.0.1:10392",
        client=("127.0.0.1", 50000),
    )


class TestVoiceTranscriptionSettings(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self._previous_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
        self._previous_device = os.environ.get("WECHAT_TOOL_WHISPER_DEVICE")
        os.environ["WECHAT_TOOL_DATA_DIR"] = self._tmp.name
        os.environ.pop("WECHAT_TOOL_WHISPER_DEVICE", None)

        import wechat_decrypt_tool.runtime_settings as runtime_settings
        import wechat_decrypt_tool.voice_transcription as voice_transcription
        import wechat_decrypt_tool.routers.chat_export as chat_export
        import wechat_decrypt_tool.routers.chat_media as chat_media

        self.runtime_settings = runtime_settings
        self.voice_transcription = voice_transcription
        self.chat_media = chat_media
        self.chat_export = chat_export

    def tearDown(self) -> None:
        _close_logging_handlers()

        if self._previous_data_dir is None:
            os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
        else:
            os.environ["WECHAT_TOOL_DATA_DIR"] = self._previous_data_dir

        if self._previous_device is None:
            os.environ.pop("WECHAT_TOOL_WHISPER_DEVICE", None)
        else:
            os.environ["WECHAT_TOOL_WHISPER_DEVICE"] = self._previous_device
        self._tmp.cleanup()

    def test_runtime_setting_is_used_when_environment_is_not_set(self):
        self.runtime_settings.write_voice_transcription_device_setting("cuda")

        device, source = self.runtime_settings.read_effective_voice_transcription_device()
        config = self.voice_transcription.VoiceTranscriptionConfig.from_env()

        self.assertEqual((device, source), ("cuda", "settings"))
        self.assertEqual(config.device, "cuda")
        self.assertEqual(config.compute_type, "float16")
        self.assertEqual(config.device_source, "settings")

    def test_default_model_is_medium(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WECHAT_TOOL_WHISPER_MODEL", None)
            config = self.voice_transcription.VoiceTranscriptionConfig.from_env()

        self.assertEqual(config.model, "medium")

    def test_environment_device_takes_precedence_over_saved_setting(self):
        self.runtime_settings.write_voice_transcription_device_setting("cuda")
        os.environ["WECHAT_TOOL_WHISPER_DEVICE"] = "cpu"

        device, source = self.runtime_settings.read_effective_voice_transcription_device()

        self.assertEqual((device, source), ("cpu", "env"))

    def test_setting_api_returns_updated_configuration(self):
        app = FastAPI()
        app.include_router(self.chat_media.router)
        configuration = {
            "requestedDevice": "cuda",
            "deviceSource": "settings",
            "cuda": {"available": True, "deviceCount": 1, "devices": [], "reason": ""},
        }
        with patch.object(self.chat_media, "set_voice_transcription_device", return_value=configuration) as setter:
            client = _local_client(app)
            response = client.put("/api/chat/media/voice/transcription/settings", json={"device": "cuda"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["configuration"], configuration)
        setter.assert_called_once_with("cuda")

    def test_setting_api_maps_locked_environment_to_conflict(self):
        app = FastAPI()
        app.include_router(self.chat_media.router)
        with patch.object(
            self.chat_media,
            "set_voice_transcription_device",
            side_effect=self.voice_transcription.VoiceTranscriptionError("device_locked", "设备已锁定"),
        ):
            client = _local_client(app)
            response = client.put("/api/chat/media/voice/transcription/settings", json={"device": "cuda"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "device_locked")

    def test_status_api_executes_service_status(self):
        app = FastAPI()
        app.include_router(self.chat_media.router)
        status = {
            "available": False,
            "modelReady": False,
            "allowDownload": False,
            "reason": "Whisper 模型尚未下载到本机缓存。 当前已禁止自动下载。",
        }
        service = SimpleNamespace(status=Mock(return_value=status))
        with patch.object(self.chat_media, "get_voice_transcription_service", return_value=service):
            response = _local_client(app).get("/api/chat/media/voice/transcription/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), status)
        service.status.assert_called_once_with()

    def test_transcription_api_blocks_missing_model_before_reading_voice(self):
        app = FastAPI()
        app.include_router(self.chat_media.router)
        service = SimpleNamespace(
            ensure_available=Mock(side_effect=self.voice_transcription.VoiceTranscriptionError(
                "model_not_ready", "模型未准备好"
            )),
            transcribe_voice=Mock(),
        )
        service_lease = SimpleNamespace(service=service, release=Mock())
        with patch.object(
            self.chat_media,
            "acquire_voice_transcription_service_lease",
            return_value=service_lease,
        ):
            response = _local_client(app).post(
                "/api/chat/media/voice/transcription",
                json={"account": "test", "server_id": "123", "force": False},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "model_not_ready")
        service.transcribe_voice.assert_not_called()
        service_lease.release.assert_called_once_with()

    def test_export_api_blocks_missing_model_before_creating_job(self):
        app = FastAPI()
        app.include_router(self.chat_export.router)
        service = SimpleNamespace(
            ensure_available=Mock(side_effect=self.voice_transcription.VoiceTranscriptionError(
                "model_not_ready", "模型未准备好"
            ))
        )
        with patch.object(self.chat_export, "get_voice_transcription_service", return_value=service), patch.object(
            self.chat_export.CHAT_EXPORT_MANAGER, "create_job"
        ) as create_job:
            response = _local_client(app).post("/api/chat/exports", json={"transcribe_voice": True})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "model_not_ready")
        create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
