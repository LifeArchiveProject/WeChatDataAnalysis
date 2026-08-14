from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.voice_transcription import (
    TRANSCRIPT_TEXT_VERSION,
    VoiceTranscriptionConfig,
    VoiceTranscriptionError,
    VoiceTranscriptionService,
    inspect_model_readiness,
    invalidate_cuda_probe_cache,
    load_voice_data,
    normalize_transcript_text,
    probe_cuda,
)


class _FakeModel:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, path, **kwargs):
        self.calls += 1
        self.last_path = path
        self.last_kwargs = kwargs
        return iter([SimpleNamespace(text=" 你好"), SimpleNamespace(text="世界 ")]), SimpleNamespace(
            language="zh",
            duration=2.5,
        )


class TestVoiceTranscription(unittest.TestCase):
    @staticmethod
    def _create_ready_model_dir(path: Path) -> None:
        for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
            (path / name).write_bytes(b"test")

    def test_local_model_directory_is_detected_without_loading_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            self._create_ready_model_dir(model_dir)
            readiness = inspect_model_readiness(str(model_dir))
            service = VoiceTranscriptionService(VoiceTranscriptionConfig(model=str(model_dir)))
            with patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value={
                "available": False, "deviceCount": 0, "devices": [], "reason": ""
            }):
                status = service.status()

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["source"], "local-directory")
        self.assertTrue(status["modelReady"])
        self.assertTrue(status["available"])

    def test_missing_local_model_is_unavailable_even_when_download_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-model"
            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(model=str(missing), allow_download=True)
            )
            with patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value={
                "available": False, "deviceCount": 0, "devices": [], "reason": ""
            }):
                status = service.status()

        self.assertFalse(status["modelReady"])
        self.assertFalse(status["available"])
        self.assertFalse(status["modelDownloadRequired"])
        self.assertIn("本地 Whisper 模型目录", status["reason"])

    def test_huggingface_cached_model_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            self._create_ready_model_dir(model_dir)
            with patch("faster_whisper.utils.download_model", return_value=str(model_dir)) as resolver:
                readiness = inspect_model_readiness("medium")

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["source"], "huggingface-cache")
        resolver.assert_called_once_with("medium", local_files_only=True)

    def test_missing_huggingface_model_is_blocked_when_download_is_disabled(self):
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="medium", allow_download=False)
        )
        with patch("faster_whisper.utils.download_model", side_effect=OSError("cache miss")), patch(
            "wechat_decrypt_tool.voice_transcription.probe_cuda",
            return_value={"available": False, "deviceCount": 0, "devices": [], "reason": ""},
        ):
            status = service.status()

        self.assertFalse(status["modelReady"])
        self.assertFalse(status["available"])
        self.assertFalse(status["allowDownload"])
        self.assertIn("禁止自动下载", status["reason"])

    def test_missing_huggingface_model_can_be_prepared_when_download_is_allowed(self):
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="medium", allow_download=True)
        )
        with patch("faster_whisper.utils.download_model", side_effect=OSError("cache miss")), patch(
            "wechat_decrypt_tool.voice_transcription.probe_cuda",
            return_value={"available": False, "deviceCount": 0, "devices": [], "reason": ""},
        ):
            status = service.status()

        self.assertFalse(status["modelReady"])
        self.assertTrue(status["available"])
        self.assertTrue(status["allowDownload"])
        self.assertTrue(status["modelDownloadRequired"])
        self.assertIn("联网下载", status["reason"])

    def test_load_voice_data_from_decrypted_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            conn = sqlite3.connect(str(account_dir / "media_0.db"))
            try:
                conn.execute("CREATE TABLE VoiceInfo (svr_id INTEGER, create_time INTEGER, voice_data BLOB)")
                conn.execute("INSERT INTO VoiceInfo VALUES (?, ?, ?)", (123, 456, b"voice-data"))
                conn.commit()
            finally:
                conn.close()

            self.assertEqual(load_voice_data(account_dir, 123), b"voice-data")

    def test_transcription_is_cached_by_message_audio_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            fake_model = _FakeModel()
            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(model="small", language="zh"),
                model_loader=lambda _config: fake_model,
            )

            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ):
                first = service.transcribe_voice(account_dir=account_dir, server_id=99, voice_data=b"SILK")
                second = service.transcribe_voice(account_dir=account_dir, server_id=99, voice_data=b"SILK")

            self.assertEqual(first["text"], "你好世界")
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertEqual(fake_model.calls, 1)
            self.assertEqual(fake_model.last_kwargs["language"], "zh")
            self.assertTrue((account_dir / "_cache" / "voice_transcripts.sqlite3").exists())

    def test_transcript_is_normalized_to_simplified_chinese_before_cache(self):
        class TraditionalModel(_FakeModel):
            def transcribe(self, path, **kwargs):
                self.calls += 1
                return iter([SimpleNamespace(text=" 這是一段繁體中文，"), SimpleNamespace(text="後臺服務已經啟動。")]), SimpleNamespace(
                    language="zh",
                    duration=2.5,
                )

        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(model="small", language="zh"),
                model_loader=lambda _config: TraditionalModel(),
            )
            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ):
                first = service.transcribe_voice(account_dir=account_dir, server_id=99, voice_data=b"SILK")
                second = service.transcribe_voice(account_dir=account_dir, server_id=99, voice_data=b"SILK")

        self.assertEqual(normalize_transcript_text("這是一段繁體中文，後臺服務已經啟動。"), "这是一段繁体中文，后台服务已经启动。")
        self.assertEqual(first["text"], "这是一段繁体中文，后台服务已经启动。")
        self.assertEqual(second["text"], first["text"])
        self.assertTrue(second["cached"])

    def test_opencc_t2s_conversion_uses_character_level_rules(self):
        self.assertEqual(normalize_transcript_text("繁體中文"), "繁体中文")
        self.assertEqual(normalize_transcript_text("軟體與資料庫"), "软体与资料库")

    def test_old_cache_is_normalized_and_migrated_on_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            cache_path = account_dir / "_cache" / "voice_transcripts.sqlite3"
            cache_path.parent.mkdir(parents=True)
            conn = sqlite3.connect(str(cache_path))
            try:
                conn.execute(
                    "CREATE TABLE transcript ("
                    "server_id INTEGER NOT NULL, source_hash TEXT NOT NULL, model TEXT NOT NULL, "
                    "language TEXT NOT NULL, text TEXT NOT NULL, detected_language TEXT NOT NULL, "
                    "duration REAL NOT NULL, updated_at REAL NOT NULL, "
                    "PRIMARY KEY (server_id, source_hash, model, language))"
                )
                conn.execute(
                    "INSERT INTO transcript VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (99, "old-hash", "small", "zh", "後臺服務已經啟動。", "zh", 1.5, 1.0),
                )
                conn.commit()
            finally:
                conn.close()

            service = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small", language="zh"))
            restored = service.lookup_cached_transcripts(account_dir, [99])
            cached = service._read_cache(account_dir, 99, "old-hash")

            conn = sqlite3.connect(str(cache_path))
            try:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(transcript)")}
                stored_text, stored_version = conn.execute(
                    "SELECT text, text_version FROM transcript WHERE server_id = 99"
                ).fetchone()
            finally:
                conn.close()

        self.assertEqual(restored[99]["text"], "后台服务已经启动。")
        self.assertEqual(cached["text"], "后台服务已经启动。")
        self.assertIn("text_version", columns)
        self.assertEqual(stored_text, cached["text"])
        self.assertEqual(stored_version, TRANSCRIPT_TEXT_VERSION)

    def test_force_retranscribes_cached_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp)
            fake_model = _FakeModel()
            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(model="small"),
                model_loader=lambda _config: fake_model,
            )
            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ):
                service.transcribe_voice(account_dir=account_dir, server_id=99, voice_data=b"SILK")
                result = service.transcribe_voice(account_dir=account_dir, server_id=99, voice_data=b"SILK", force=True)

            self.assertFalse(result["cached"])
            self.assertEqual(fake_model.calls, 2)

    def test_raw_silk_is_rejected_when_decode_fails(self):
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small"),
            model_loader=lambda _config: _FakeModel(),
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"SILK", "silk", "audio/silk"),
        ):
            with self.assertRaises(VoiceTranscriptionError) as cm:
                service.transcribe_voice(account_dir=Path(tmp), server_id=99, voice_data=b"SILK")

        self.assertEqual(cm.exception.code, "voice_decode_failed")

    def test_disabled_service_does_not_load_model(self):
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(enabled=False),
            model_loader=lambda _config: self.fail("model must not load"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VoiceTranscriptionError) as cm:
                service.transcribe_voice(account_dir=Path(tmp), server_id=99, voice_data=b"SILK")
        self.assertEqual(cm.exception.code, "disabled")

    def test_cache_write_failure_does_not_discard_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(model="small"),
                model_loader=lambda _config: _FakeModel(),
            )
            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ), patch.object(service, "_write_cache", side_effect=OSError("read only")):
                result = service.transcribe_voice(
                    account_dir=Path(tmp),
                    server_id=99,
                    voice_data=b"SILK",
                )
        self.assertEqual(result["text"], "你好世界")

    def test_public_result_does_not_expose_local_model_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(model=r"D:\models\faster-whisper-small"),
                model_loader=lambda _config: _FakeModel(),
            )
            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ):
                result = service.transcribe_voice(
                    account_dir=Path(tmp),
                    server_id=99,
                    voice_data=b"SILK",
                )
        self.assertEqual(result["model"], "faster-whisper-small")

    def test_cuda_initialization_failure_falls_back_to_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            fake_model = _FakeModel()

            def model_loader(config):
                calls.append((config.device, config.compute_type))
                if config.device == "cuda":
                    raise RuntimeError("CUDA initialization failed")
                return fake_model

            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(device="cuda", compute_type="float16"),
                model_loader=model_loader,
            )
            cuda_report = {"available": True, "deviceCount": 1, "devices": [], "reason": ""}
            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ), patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value=cuda_report):
                result = service.transcribe_voice(
                    account_dir=Path(tmp),
                    server_id=99,
                    voice_data=b"SILK",
                )
                status = service.status()

            self.assertEqual(calls, [("cuda", "float16"), ("cpu", "int8")])
            self.assertEqual(result["device"], "cpu")
            self.assertEqual(result["computeType"], "int8")
            self.assertTrue(status["usingFallback"])
            self.assertEqual(status["activeDevice"], "cpu")

    def test_cuda_first_inference_failure_falls_back_to_cpu_once(self):
        class CudaModel:
            calls = 0

            def transcribe(self, _path, **_kwargs):
                self.calls += 1

                def fail_during_iteration():
                    raise RuntimeError("cuDNN CUDA initialization failed")
                    yield None

                return fail_during_iteration(), SimpleNamespace(language="zh", duration=2.5)

        cuda_model = CudaModel()
        cpu_model = _FakeModel()
        loads = []

        def model_loader(config):
            loads.append((config.device, config.compute_type))
            return cuda_model if config.device == "cuda" else cpu_model

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(device="cuda", compute_type="float16"),
            model_loader=model_loader,
        )
        cuda_report = {"available": True, "deviceCount": 1, "devices": [], "reason": ""}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ), patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value=cuda_report):
            result = service.transcribe_voice(account_dir=Path(tmp), server_id=99, voice_data=b"SILK")

        self.assertEqual(loads, [("cuda", "float16"), ("cpu", "int8")])
        self.assertEqual(cuda_model.calls, 1)
        self.assertEqual(cpu_model.calls, 1)
        self.assertEqual(result["device"], "cpu")
        self.assertEqual(result["text"], "你好世界")

    def test_non_cuda_inference_error_does_not_trigger_cpu_fallback(self):
        class InvalidAudioModel:
            def transcribe(self, _path, **_kwargs):
                raise ValueError("invalid audio frame")

        loads = []

        def model_loader(config):
            loads.append(config.device)
            return InvalidAudioModel()

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(device="cuda", compute_type="float16"),
            model_loader=model_loader,
        )
        cuda_report = {"available": True, "deviceCount": 1, "devices": [], "reason": ""}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ), patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value=cuda_report):
            with self.assertRaises(VoiceTranscriptionError) as cm:
                service.transcribe_voice(account_dir=Path(tmp), server_id=99, voice_data=b"SILK")

        self.assertEqual(cm.exception.code, "transcription_failed")
        self.assertEqual(loads, ["cuda"])

    def test_cuda_probe_reports_available_nvidia_device(self):
        fake_ctranslate2 = SimpleNamespace(get_cuda_device_count=lambda: 1)
        invalidate_cuda_probe_cache()
        try:
            with patch.dict(sys.modules, {"ctranslate2": fake_ctranslate2}), patch(
                "wechat_decrypt_tool.voice_transcription._read_nvidia_smi_devices",
                return_value=[{"name": "NVIDIA GeForce RTX 5060", "driverVersion": "570.0", "memoryTotal": "8192 MiB"}],
            ):
                report = probe_cuda()
        finally:
            invalidate_cuda_probe_cache()

        self.assertTrue(report["available"])
        self.assertEqual(report["deviceCount"], 1)
        self.assertEqual(report["devices"][0]["name"], "NVIDIA GeForce RTX 5060")

    def test_cuda_probe_uses_short_lived_cache(self):
        fake_ctranslate2 = SimpleNamespace(get_cuda_device_count=lambda: 1)
        invalidate_cuda_probe_cache()
        try:
            with patch.dict(sys.modules, {"ctranslate2": fake_ctranslate2}), patch(
                "wechat_decrypt_tool.voice_transcription._read_nvidia_smi_devices",
                return_value=[],
            ) as nvidia_smi:
                first = probe_cuda()
                second = probe_cuda()
        finally:
            invalidate_cuda_probe_cache()

        self.assertTrue(first["available"])
        self.assertEqual(second, first)
        nvidia_smi.assert_called_once_with()

    def test_model_load_error_can_be_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_model = _FakeModel()
            attempts = 0

            def model_loader(_config):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("temporary failure")
                return fake_model

            service = VoiceTranscriptionService(
                VoiceTranscriptionConfig(),
                model_loader=model_loader,
            )
            with patch(
                "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
                return_value=(b"RIFF-WAV", "wav", "audio/wav"),
            ):
                with self.assertRaises(VoiceTranscriptionError) as cm:
                    service.transcribe_voice(account_dir=Path(tmp), server_id=99, voice_data=b"SILK")
                result = service.transcribe_voice(account_dir=Path(tmp), server_id=99, voice_data=b"SILK")

            self.assertEqual(cm.exception.code, "model_load_failed")
            self.assertEqual(attempts, 2)
            self.assertEqual(result["text"], "你好世界")


if __name__ == "__main__":
    unittest.main()
