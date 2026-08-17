from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.voice_transcription import (
    TRANSCRIPT_TEXT_VERSION,
    VoiceTranscriptionConfig,
    VoiceTranscriptionError,
    VoiceTranscriptionService,
    _VoiceTranscriptionCancelled,
    capture_voice_transcript_cache_generation,
    delete_all_voice_transcript_caches,
    delete_voice_transcript_cache,
    inspect_model_readiness,
    invalidate_cuda_probe_cache,
    load_voice_data,
    normalize_transcript_text,
    probe_cuda,
)
import wechat_decrypt_tool.voice_transcription as voice_transcription_module


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
        self.assertEqual(readiness["source"], "external-cache")
        self.assertFalse(readiness["deletable"])
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

    def test_inference_worker_count_has_no_fixed_cap_and_is_reported(self):
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu", num_workers=37),
            model_loader=lambda _config: _FakeModel(),
        )
        self.assertEqual(service.configure_inference_concurrency(99), 99)
        with patch.object(
            service,
            "_model_readiness",
            return_value={"ready": True, "downloadable": True, "source": "managed", "reason": ""},
        ), patch(
            "wechat_decrypt_tool.voice_transcription.probe_cuda",
            return_value={"available": False, "deviceCount": 0, "devices": [], "reason": ""},
        ):
            status = service.status()

        self.assertEqual(status["numWorkers"], 99)

    def test_faster_whisper_receives_unbounded_worker_count(self):
        model = object()
        config = VoiceTranscriptionConfig(
            model="custom-whisper-model",
            device="cpu",
            num_workers=99,
            allow_download=True,
        )
        with patch("faster_whisper.WhisperModel", return_value=model) as whisper_model:
            loaded = VoiceTranscriptionService._load_faster_whisper_model(config)

        self.assertIs(loaded, model)
        whisper_model.assert_called_once_with(
            "custom-whisper-model",
            device="cpu",
            compute_type="int8",
            num_workers=99,
            local_files_only=False,
        )

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

    def test_delete_cache_removes_all_models_and_preserves_unrelated_account_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "wxid_delete_fixture"
            account_dir.mkdir()
            small = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small", language="zh"))
            medium = VoiceTranscriptionService(VoiceTranscriptionConfig(model="medium", language="zh"))
            result = {"text": "项目转写", "language": "zh", "duration": 1.0}
            small._write_cache(account_dir, 101, "small-101", dict(result))
            medium._write_cache(account_dir, 101, "medium-101", dict(result))
            small._write_cache(account_dir, 102, "small-102", dict(result))

            cache_path = account_dir / "_cache" / "voice_transcripts.sqlite3"
            conn = sqlite3.connect(str(cache_path))
            try:
                conn.execute("CREATE TABLE unrelated_state (value TEXT NOT NULL)")
                conn.execute("INSERT INTO unrelated_state VALUES ('keep')")
                conn.commit()
            finally:
                conn.close()
            message_db = account_dir / "message_0.db"
            message_db.write_bytes(b"wechat-message-db")
            audio = account_dir / "voice.silk"
            audio.write_bytes(b"wechat-audio")
            model = account_dir / "voice_models" / "small" / "model.bin"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"whisper-model")

            deleted = delete_voice_transcript_cache(account_dir)
            small_lookup = small.lookup_cached_transcripts(account_dir, [101, 102])
            medium_lookup = medium.lookup_cached_transcripts(account_dir, [101, 102])
            conn = sqlite3.connect(str(cache_path))
            try:
                transcript_rows = conn.execute("SELECT COUNT(*) FROM transcript").fetchone()[0]
                unrelated = conn.execute("SELECT value FROM unrelated_state").fetchone()[0]
            finally:
                conn.close()
            message_bytes = message_db.read_bytes()
            audio_bytes = audio.read_bytes()
            model_bytes = model.read_bytes()

        self.assertEqual(
            deleted,
            {
                "status": "success",
                "account": "wxid_delete_fixture",
                "deletedRows": 3,
                "deletedMessages": 2,
                "nativeDeleted": 0,
            },
        )
        self.assertEqual(small_lookup, {})
        self.assertEqual(medium_lookup, {})
        self.assertEqual(transcript_rows, 0)
        self.assertEqual(unrelated, "keep")
        self.assertEqual(message_bytes, b"wechat-message-db")
        self.assertEqual(audio_bytes, b"wechat-audio")
        self.assertEqual(model_bytes, b"whisper-model")

    def test_delete_epoch_blocks_inflight_transcription_from_restoring_cache(self):
        inference_entered = threading.Event()
        release_inference = threading.Event()

        class BlockingModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    inference_entered.set()
                    release_inference.wait(2)
                    yield SimpleNamespace(text="删除前开始的转写")

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", language="zh"),
            model_loader=lambda _config: BlockingModel(),
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            account_dir = Path(tmp) / "wxid_epoch_fixture"
            account_dir.mkdir()
            with ThreadPoolExecutor(max_workers=1) as executor:
                transcription = executor.submit(
                    service.transcribe_voice,
                    account_dir=account_dir,
                    server_id=201,
                    voice_data=b"SILK-201",
                )
                self.assertTrue(inference_entered.wait(1))
                deleted = delete_voice_transcript_cache(account_dir)
                release_inference.set()
                result = transcription.result(timeout=2)

            cache_path = account_dir / "_cache" / "voice_transcripts.sqlite3"
            lookup = service.lookup_cached_transcripts(account_dir, [201])
            cache_exists = cache_path.exists()

        self.assertEqual(deleted["deletedRows"], 0)
        self.assertEqual(result["text"], "删除前开始的转写")
        self.assertEqual(lookup, {})
        self.assertFalse(cache_exists)

    def test_delete_cache_rejects_linked_cache_directory_or_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "wxid_link_fixture"
            cache_path = account_dir / "_cache" / "voice_transcripts.sqlite3"
            for unsafe_path in (cache_path.parent, cache_path):
                with self.subTest(unsafe_path=unsafe_path), patch(
                    "wechat_decrypt_tool.voice_transcription._path_is_link_or_junction",
                    side_effect=lambda path, target=unsafe_path: path == target,
                ):
                    with self.assertRaises(VoiceTranscriptionError) as raised:
                        delete_voice_transcript_cache(account_dir)
                    self.assertEqual(raised.exception.code, "unsafe_cache_path")

    def test_delete_missing_cache_is_idempotent_and_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "wxid_missing_fixture"
            account_dir.mkdir()
            first = delete_voice_transcript_cache(account_dir)
            second = delete_voice_transcript_cache(account_dir)
            cache_dir_exists = (account_dir / "_cache").exists()

        self.assertEqual(first["deletedRows"], 0)
        self.assertEqual(second["deletedRows"], 0)
        self.assertFalse(cache_dir_exists)

    def test_global_delete_aggregates_all_safe_application_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            databases_root = Path(tmp) / "output" / "databases"
            first_account = databases_root / "wxid_global_first"
            second_account = databases_root / "wxid_global_second"
            empty_account = databases_root / "wxid_global_empty"
            first_account.mkdir(parents=True)
            second_account.mkdir()
            empty_account.mkdir()
            small = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
            medium = VoiceTranscriptionService(VoiceTranscriptionConfig(model="medium"))
            cached = {"text": "项目转写", "language": "zh", "duration": 1.0}
            small._write_cache(first_account, 301, "small-301", dict(cached))
            medium._write_cache(first_account, 301, "medium-301", dict(cached))
            small._write_cache(second_account, 302, "small-302", dict(cached))
            small._write_cache(second_account, 303, "small-303", dict(cached))
            (databases_root / "not-an-account.txt").write_text("keep", encoding="utf-8")

            with patch(
                "wechat_decrypt_tool.voice_transcription.get_output_databases_dir",
                return_value=databases_root,
            ):
                deleted = delete_all_voice_transcript_caches()

            first_lookup = small.lookup_cached_transcripts(first_account, [301])
            second_lookup = small.lookup_cached_transcripts(second_account, [302, 303])
            empty_cache_exists = (empty_account / "_cache").exists()

        self.assertEqual(
            deleted,
            {
                "status": "success",
                "deletedRows": 4,
                "deletedMessages": 3,
                "accountsScanned": 3,
                "accountsChanged": 2,
                "nativeDeleted": 0,
            },
        )
        self.assertEqual(first_lookup, {})
        self.assertEqual(second_lookup, {})
        self.assertFalse(empty_cache_exists)

    def test_global_delete_reports_partial_failure_and_continues_other_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            databases_root = Path(tmp) / "output" / "databases"
            good_account = databases_root / "wxid_global_good"
            broken_account = databases_root / "wxid_global_broken"
            good_account.mkdir(parents=True)
            (broken_account / "_cache").mkdir(parents=True)
            service = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
            service._write_cache(
                good_account,
                401,
                "small-401",
                {"text": "项目转写", "language": "zh", "duration": 1.0},
            )
            broken_cache = broken_account / "_cache" / "voice_transcripts.sqlite3"
            broken_cache.write_bytes(b"not-a-sqlite-database")

            with patch(
                "wechat_decrypt_tool.voice_transcription.get_output_databases_dir",
                return_value=databases_root,
            ):
                deleted = delete_all_voice_transcript_caches()

            good_lookup = service.lookup_cached_transcripts(good_account, [401])
            broken_bytes = broken_cache.read_bytes()

        self.assertEqual(deleted["status"], "partial")
        self.assertEqual(deleted["deletedRows"], 1)
        self.assertEqual(deleted["deletedMessages"], 1)
        self.assertEqual(deleted["accountsScanned"], 2)
        self.assertEqual(deleted["accountsChanged"], 1)
        self.assertEqual(
            deleted["failures"],
            [{"account": "wxid_global_broken", "code": "cache_delete_failed"}],
        )
        self.assertEqual(good_lookup, {})
        self.assertEqual(broken_bytes, b"not-a-sqlite-database")

    def test_global_delete_rejects_linked_root_account_cache_or_database(self):
        unsafe_codes = {
            "root": "unsafe_cache_root",
            "account": "unsafe_account_path",
            "cache": "unsafe_cache_path",
            "database": "unsafe_cache_path",
        }
        for boundary, expected_code in unsafe_codes.items():
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                databases_root = Path(tmp) / "output" / "databases"
                account_dir = databases_root / "wxid_global_link"
                account_dir.mkdir(parents=True)
                service = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
                service._write_cache(
                    account_dir,
                    451,
                    "small-451",
                    {"text": "必须保留", "language": "zh", "duration": 1.0},
                )
                cache_dir = account_dir / "_cache"
                cache_path = cache_dir / "voice_transcripts.sqlite3"
                unsafe_path = {
                    "root": databases_root,
                    "account": account_dir,
                    "cache": cache_dir,
                    "database": cache_path,
                }[boundary]
                outside = Path(tmp) / "outside.sqlite3"
                outside.write_bytes(b"outside-must-remain")

                with patch(
                    "wechat_decrypt_tool.voice_transcription.get_output_databases_dir",
                    return_value=databases_root,
                ), patch(
                    "wechat_decrypt_tool.voice_transcription._path_is_link_or_junction",
                    side_effect=lambda path, target=unsafe_path: Path(path) == target,
                ):
                    if boundary == "root":
                        with self.assertRaises(VoiceTranscriptionError) as raised:
                            delete_all_voice_transcript_caches()
                        self.assertEqual(raised.exception.code, expected_code)
                    else:
                        deleted = delete_all_voice_transcript_caches()
                        self.assertEqual(deleted["status"], "partial")
                        self.assertEqual(deleted["accountsScanned"], 1)
                        self.assertEqual(deleted["failures"][0]["code"], expected_code)

                conn = sqlite3.connect(str(cache_path))
                try:
                    remaining = conn.execute("SELECT COUNT(*) FROM transcript").fetchone()[0]
                finally:
                    conn.close()
                self.assertEqual(remaining, 1)
                self.assertEqual(outside.read_bytes(), b"outside-must-remain")

    def test_global_delete_revalidates_account_after_enumeration(self):
        with tempfile.TemporaryDirectory() as tmp:
            databases_root = Path(tmp) / "output" / "databases"
            account_dir = databases_root / "wxid_replaced_after_scan"
            account_dir.mkdir(parents=True)
            service = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
            service._write_cache(
                account_dir,
                452,
                "small-452",
                {"text": "必须保留", "language": "zh", "duration": 1.0},
            )
            account_checks = 0

            def becomes_linked(path):
                nonlocal account_checks
                if Path(path) == account_dir:
                    account_checks += 1
                    return account_checks >= 2
                return False

            with patch(
                "wechat_decrypt_tool.voice_transcription.get_output_databases_dir",
                return_value=databases_root,
            ), patch(
                "wechat_decrypt_tool.voice_transcription._path_is_link_or_junction",
                side_effect=becomes_linked,
            ):
                deleted = delete_all_voice_transcript_caches()

            cache_path = account_dir / "_cache" / "voice_transcripts.sqlite3"
            conn = sqlite3.connect(str(cache_path))
            try:
                remaining = conn.execute("SELECT COUNT(*) FROM transcript").fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(deleted["status"], "partial")
        self.assertEqual(deleted["failures"], [
            {"account": "wxid_replaced_after_scan", "code": "unsafe_account_path"}
        ])
        self.assertEqual(remaining, 1)

    def test_global_delete_epoch_blocks_inflight_write_across_sweep(self):
        inference_entered = threading.Event()
        release_inference = threading.Event()

        class BlockingModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    inference_entered.set()
                    release_inference.wait(2)
                    yield SimpleNamespace(text="全局删除前开始")

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small"),
            model_loader=lambda _config: BlockingModel(),
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            databases_root = Path(tmp) / "output" / "databases"
            account_dir = databases_root / "wxid_global_epoch"
            account_dir.mkdir(parents=True)
            with ThreadPoolExecutor(max_workers=1) as executor:
                transcription = executor.submit(
                    service.transcribe_voice,
                    account_dir=account_dir,
                    server_id=501,
                    voice_data=b"SILK-501",
                )
                self.assertTrue(inference_entered.wait(1))
                with patch(
                    "wechat_decrypt_tool.voice_transcription.get_output_databases_dir",
                    return_value=databases_root,
                ):
                    deleted = delete_all_voice_transcript_caches()
                release_inference.set()
                transcription.result(timeout=2)
            cache_exists = (account_dir / "_cache" / "voice_transcripts.sqlite3").exists()

        self.assertEqual(deleted["status"], "success")
        self.assertEqual(deleted["accountsScanned"], 1)
        self.assertFalse(cache_exists)

    def test_global_generation_rejects_later_items_from_predelete_operation(self):
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small"),
            model_loader=lambda _config: _FakeModel(),
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            databases_root = Path(tmp) / "output" / "databases"
            account_dir = databases_root / "wxid_operation_generation"
            account_dir.mkdir(parents=True)
            old_generation = capture_voice_transcript_cache_generation()
            with patch(
                "wechat_decrypt_tool.voice_transcription.get_output_databases_dir",
                return_value=databases_root,
            ):
                delete_all_voice_transcript_caches()

            old_operation_result = service.transcribe_voice(
                account_dir=account_dir,
                server_id=601,
                voice_data=b"SILK-601",
                cache_generation=old_generation,
            )
            after_old_operation = service.lookup_cached_transcripts(account_dir, [601])
            new_generation = capture_voice_transcript_cache_generation()
            service.transcribe_voice(
                account_dir=account_dir,
                server_id=602,
                voice_data=b"SILK-602",
                cache_generation=new_generation,
            )
            after_new_operation = service.lookup_cached_transcripts(account_dir, [602])

        self.assertEqual(old_operation_result["text"], "你好世界")
        self.assertEqual(after_old_operation, {})
        self.assertIn(602, after_new_operation)

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

    def test_opencc_initialization_and_conversion_are_serialized(self):
        constructor_entered = threading.Event()
        release_constructor = threading.Event()
        state_lock = threading.Lock()
        constructor_calls = 0
        active_conversions = 0
        maximum_conversions = 0

        class BlockingOpenCC:
            def __init__(self, mode):
                nonlocal constructor_calls
                self.assert_mode = mode
                constructor_calls += 1
                constructor_entered.set()
                release_constructor.wait(2)

            def convert(self, value):
                nonlocal active_conversions, maximum_conversions
                with state_lock:
                    active_conversions += 1
                    maximum_conversions = max(maximum_conversions, active_conversions)
                try:
                    time.sleep(0.02)
                    return str(value).replace("繁體", "繁体").replace("資料", "资料")
                finally:
                    with state_lock:
                        active_conversions -= 1

        fake_opencc = SimpleNamespace(OpenCC=BlockingOpenCC)
        with (
            patch.dict(sys.modules, {"opencc": fake_opencc}),
            patch.object(voice_transcription_module, "_OPENCC_CONVERTER", None),
            patch.object(voice_transcription_module, "_OPENCC_LOOKED_UP", False),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(normalize_transcript_text, "繁體")
            self.assertTrue(constructor_entered.wait(1))
            second = executor.submit(normalize_transcript_text, "資料")
            time.sleep(0.05)
            self.assertFalse(second.done())
            release_constructor.set()
            self.assertEqual(first.result(timeout=2), "繁体")
            self.assertEqual(second.result(timeout=2), "资料")

        self.assertEqual(constructor_calls, 1)
        self.assertEqual(maximum_conversions, 1)

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

    def test_concurrent_cuda_failures_wait_for_all_leases_and_fallback_once(self):
        barrier = threading.Barrier(2)

        class ConcurrentCudaModel:
            def __init__(self):
                self.lock = threading.Lock()
                self.active = 0

            def transcribe(self, _path, **_kwargs):
                def fail_during_iteration():
                    with self.lock:
                        self.active += 1
                    try:
                        barrier.wait(timeout=2)
                        raise RuntimeError("CUDA concurrent inference failed")
                        yield None
                    finally:
                        with self.lock:
                            self.active -= 1

                return fail_during_iteration(), SimpleNamespace(language="zh", duration=2.5)

        cuda_model = ConcurrentCudaModel()
        cpu_model = _FakeModel()
        loads = []

        def model_loader(config):
            loads.append((config.device, config.compute_type, config.num_workers))
            return cuda_model if config.device == "cuda" else cpu_model

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cuda", compute_type="float16"),
            model_loader=model_loader,
        )
        self.assertEqual(service.configure_inference_concurrency(2), 2)
        release_active_counts = []
        original_release = service._release_loaded_model_unlocked

        def checked_release():
            with cuda_model.lock:
                release_active_counts.append(cuda_model.active)
            original_release()

        service._release_loaded_model_unlocked = checked_release
        cuda_report = {"available": True, "deviceCount": 1, "devices": [], "reason": ""}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ), patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value=cuda_report):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        service.transcribe_voice,
                        account_dir=Path(tmp),
                        server_id=server_id,
                        voice_data=f"SILK-{server_id}".encode(),
                    )
                    for server_id in (101, 102)
                ]
                results = [future.result(timeout=3) for future in futures]

        self.assertEqual(loads, [("cuda", "float16", 2), ("cpu", "int8", 2)])
        self.assertEqual(release_active_counts, [0])
        self.assertEqual([result["device"] for result in results], ["cpu", "cpu"])
        self.assertEqual([result["text"] for result in results], ["你好世界", "你好世界"])

    def test_cuda_failure_survives_concurrent_worker_reconfigure(self):
        inference_entered = threading.Event()
        release_failure = threading.Event()
        loads = []
        cuda_model_ref = None
        cuda_collected_before_cpu_load = []

        class FailingCudaModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    inference_entered.set()
                    release_failure.wait(2)
                    raise RuntimeError("CUDA worker failed")
                    yield None

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        def model_loader(config):
            nonlocal cuda_model_ref
            loads.append((config.device, config.num_workers))
            if config.device == "cuda":
                model = FailingCudaModel()
                cuda_model_ref = weakref.ref(model)
                return model
            cuda_collected_before_cpu_load.append(cuda_model_ref() is None)
            return _FakeModel()

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cuda", compute_type="float16"),
            model_loader=model_loader,
        )
        cuda_report = {"available": True, "deviceCount": 1, "devices": [], "reason": ""}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ), patch("wechat_decrypt_tool.voice_transcription.probe_cuda", return_value=cuda_report):
            with ThreadPoolExecutor(max_workers=2) as executor:
                inference = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=151,
                    voice_data=b"SILK-151",
                )
                self.assertTrue(inference_entered.wait(1))
                reconfigure = executor.submit(service.configure_inference_concurrency, 2)
                deadline = time.time() + 1
                while time.time() < deadline:
                    with service._inference_condition:
                        if service._model_transitioning:
                            break
                    time.sleep(0.01)
                self.assertTrue(service._model_transitioning)
                release_failure.set()
                self.assertEqual(reconfigure.result(timeout=2), 2)
                result = inference.result(timeout=3)

        self.assertEqual(loads, [("cuda", 1), ("cpu", 2)])
        self.assertEqual(cuda_collected_before_cpu_load, [True])
        self.assertEqual(result["device"], "cpu")

    def test_concurrency_reconfigure_wait_can_be_cancelled(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    entered.set()
                    release.wait(2)
                    yield SimpleNamespace(text="完成")

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu"),
            model_loader=lambda _config: BlockingModel(),
        )
        cancel_event = threading.Event()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                inference = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=201,
                    voice_data=b"SILK",
                )
                self.assertTrue(entered.wait(1))
                reconfigure = executor.submit(
                    service.configure_inference_concurrency,
                    2,
                    cancel_event=cancel_event,
                )
                time.sleep(0.05)
                cancel_event.set()
                try:
                    with self.assertRaises(_VoiceTranscriptionCancelled):
                        reconfigure.result(timeout=1)
                finally:
                    release.set()
                result = inference.result(timeout=2)

        self.assertEqual(result["text"], "完成")

    def test_retire_waits_for_active_inference_and_blocks_old_service_reload(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    entered.set()
                    release.wait(2)
                    yield SimpleNamespace(text="完成")

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu"),
            model_loader=lambda _config: BlockingModel(),
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                inference = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=301,
                    voice_data=b"SILK-301",
                )
                self.assertTrue(entered.wait(1))
                retiring = executor.submit(service.retire)
                time.sleep(0.05)
                self.assertFalse(retiring.done())
                release.set()
                self.assertEqual(inference.result(timeout=2)["text"], "完成")
                retiring.result(timeout=2)

            with self.assertRaises(VoiceTranscriptionError) as raised:
                service.transcribe_voice(
                    account_dir=Path(tmp),
                    server_id=302,
                    voice_data=b"SILK-302",
                    force=True,
                )

        self.assertEqual(raised.exception.code, "service_retired")
        self.assertIsNone(service._model)

    def test_retired_service_cannot_return_a_cached_transcript(self):
        model = _FakeModel()
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu"),
            model_loader=lambda _config: model,
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            account_dir = Path(tmp)
            service.transcribe_voice(account_dir=account_dir, server_id=351, voice_data=b"SILK-351")
            service.retire()
            with self.assertRaises(VoiceTranscriptionError) as raised:
                service.transcribe_voice(account_dir=account_dir, server_id=351, voice_data=b"SILK-351")

        self.assertEqual(raised.exception.code, "service_retired")
        self.assertEqual(model.calls, 1)

    def test_service_generation_lease_delays_reset_until_release(self):
        old_service = SimpleNamespace(
            config=VoiceTranscriptionConfig(model="small", device="cpu"),
            retire=Mock(),
        )
        new_service = SimpleNamespace(config=VoiceTranscriptionConfig(model="small", device="cpu"))
        module = voice_transcription_module
        with (
            patch.object(module, "_VOICE_TRANSCRIPTION_SERVICE", old_service),
            patch.object(module, "_VOICE_TRANSCRIPTION_SERVICE_RESETTING", False),
            patch.object(module, "_VOICE_TRANSCRIPTION_SERVICE_LEASES", 0),
            patch.object(module, "VoiceTranscriptionService", return_value=new_service),
        ):
            lease = module.acquire_voice_transcription_service_lease()
            with ThreadPoolExecutor(max_workers=1) as executor:
                resetting = executor.submit(module._reset_voice_transcription_service)
                deadline = time.time() + 1
                while time.time() < deadline:
                    with module._VOICE_TRANSCRIPTION_SERVICE_CONDITION:
                        if module._VOICE_TRANSCRIPTION_SERVICE_RESETTING:
                            break
                    time.sleep(0.01)
                self.assertTrue(module._VOICE_TRANSCRIPTION_SERVICE_RESETTING)
                self.assertFalse(resetting.done())
                old_service.retire.assert_not_called()
                lease.release()
                self.assertIs(resetting.result(timeout=2), new_service)

            old_service.retire.assert_called_once_with()
            self.assertIs(module.get_voice_transcription_service(), new_service)

    def test_cache_lock_is_shared_across_service_generations(self):
        first = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
        second = VoiceTranscriptionService(VoiceTranscriptionConfig(model="small"))
        self.assertIs(first._cache_lock, second._cache_lock)

    def test_duplicate_concurrent_transcription_uses_singleflight_cache(self):
        entered = threading.Event()
        release = threading.Event()

        class BlockingModel:
            def __init__(self):
                self.calls = 0

            def transcribe(self, _path, **_kwargs):
                self.calls += 1

                def segments():
                    entered.set()
                    release.wait(2)
                    yield SimpleNamespace(text="唯一结果")

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        model = BlockingModel()
        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu"),
            model_loader=lambda _config: model,
        )
        service.configure_inference_concurrency(2)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=401,
                    voice_data=b"SAME-SILK",
                )
                self.assertTrue(entered.wait(1))
                second = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=401,
                    voice_data=b"SAME-SILK",
                )
                time.sleep(0.05)
                self.assertEqual(model.calls, 1)
                release.set()
                results = [first.result(timeout=2), second.result(timeout=2)]

        self.assertEqual(model.calls, 1)
        self.assertEqual(sorted(result["cached"] for result in results), [False, True])

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

    def test_non_cuda_error_releases_traceback_model_before_reconfigure_reload(self):
        inference_entered = threading.Event()
        release_failure = threading.Event()
        first_model_ref = None
        old_model_collected_before_reload = []
        load_count = 0

        class FailingModel:
            def transcribe(self, _path, **_kwargs):
                def segments():
                    inference_entered.set()
                    release_failure.wait(2)
                    raise ValueError("invalid audio")
                    yield None

                return segments(), SimpleNamespace(language="zh", duration=1.0)

        def model_loader(_config):
            nonlocal first_model_ref, load_count
            load_count += 1
            if load_count == 1:
                model = FailingModel()
                first_model_ref = weakref.ref(model)
                return model
            old_model_collected_before_reload.append(first_model_ref() is None)
            return _FakeModel()

        service = VoiceTranscriptionService(
            VoiceTranscriptionConfig(model="small", device="cpu"),
            model_loader=model_loader,
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "wechat_decrypt_tool.voice_transcription._convert_silk_to_browser_audio",
            return_value=(b"RIFF-WAV", "wav", "audio/wav"),
        ):
            with ThreadPoolExecutor(max_workers=3) as executor:
                failing = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=601,
                    voice_data=b"SILK-601",
                )
                self.assertTrue(inference_entered.wait(1))
                reconfigure = executor.submit(service.configure_inference_concurrency, 2)
                deadline = time.time() + 1
                while time.time() < deadline:
                    with service._inference_condition:
                        if service._model_transitioning:
                            break
                    time.sleep(0.01)
                succeeding = executor.submit(
                    service.transcribe_voice,
                    account_dir=Path(tmp),
                    server_id=602,
                    voice_data=b"SILK-602",
                )
                release_failure.set()
                with self.assertRaises(VoiceTranscriptionError) as raised:
                    failing.result(timeout=2)
                self.assertEqual(reconfigure.result(timeout=2), 2)
                result = succeeding.result(timeout=2)

        self.assertEqual(raised.exception.code, "transcription_failed")
        self.assertEqual(old_model_collected_before_reload, [True])
        self.assertEqual(result["text"], "你好世界")

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
