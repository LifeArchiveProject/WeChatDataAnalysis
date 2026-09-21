"""新后端的资产发布、配置兼容、缓存隔离和进程取消回归。"""
import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from wechat_decrypt_tool import asr_models as assets
from wechat_decrypt_tool import voice_transcription as voice
from wechat_decrypt_tool.asr_backends import audio_chunks, log_mel, mel_filters
from wechat_decrypt_tool.asr_worker import AsrCancelled, AsrError, ProcessBackend

CTC = "zipformer-small-ctc-int8"
CPU = "qwen3-asr-06b-onnx-int4"
GPU = "qwen3-asr-06b-hf"


@pytest.fixture
def small_asset(monkeypatch):
    files = {"ctc.int8.onnx": b"model", "data/tokens.txt": b"tokens"}
    spec = {**assets.SPECS[CTC], "files": {name: dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
                                         for name, data in files.items()}}
    monkeypatch.setitem(assets.SPECS, CTC, spec)
    return files


def write_assets(path, files):
    for name, data in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_new_asset_readiness_requires_exact_files(tmp_path, small_asset):
    assert not voice._model_directory_is_ready(tmp_path, CTC)
    write_assets(tmp_path, small_asset)
    assert voice._model_directory_is_ready(tmp_path, CTC)
    (tmp_path / "ctc.int8.onnx").write_bytes(b"bad")
    assert not voice._model_directory_is_ready(tmp_path, CTC)


@pytest.mark.parametrize("corrupt", [False, True])
def test_download_verifies_hash_before_publish(tmp_path, monkeypatch, small_asset, corrupt):
    root = tmp_path / "models"
    monkeypatch.setattr(voice, "get_voice_model_storage_root", lambda: root)
    monkeypatch.setattr(voice, "get_voice_transcription_service", lambda: SimpleNamespace(config=voice.VoiceTranscriptionConfig()))
    def download(model, *, output_dir, progress_callback):
        write_assets(output_dir, small_asset)
        if corrupt:
            (output_dir / "ctc.int8.onnx").write_bytes(b"wrong")
        return output_dir
    monkeypatch.setattr(voice, "_download_voice_model_snapshot", download)
    manager = voice.VoiceModelDownloadManager()
    job = manager.start(CTC)
    assert manager._completion_events[job["jobId"]].wait(5)
    result = manager.get(job["jobId"])
    assert result["status"] == ("error" if corrupt else "done")
    assert (root / CTC).exists() is not corrupt
    if corrupt:
        assert "校验失败" in result["error"]


def test_download_uses_pinned_revision_and_variant_files(tmp_path, monkeypatch):
    calls = []
    def snapshot(repo, **kwargs):
        calls.append((repo, kwargs))
        return [] if kwargs.get("dry_run") else str(tmp_path)
    monkeypatch.setattr("huggingface_hub.snapshot_download", snapshot)
    voice._download_voice_model_snapshot(CPU, output_dir=tmp_path, progress_callback=lambda **_: None)
    for repo, kwargs in calls:
        assert repo == assets.SPECS[CPU]["repo"]
        assert kwargs["revision"] == assets.SPECS[CPU]["revision"]
        assert set(kwargs["allow_patterns"]) == set(assets.SPECS[CPU]["files"])
        assert not any("fp16" in name for name in kwargs["allow_patterns"])


def test_cache_isolated_by_model_and_revision(tmp_path, monkeypatch):
    result = dict(text="测试文本", language="zh", duration=1)
    service = voice.VoiceTranscriptionService(voice.VoiceTranscriptionConfig(model=CTC))
    service._write_cache(tmp_path, 1, "hash", result)
    assert service._read_cache(tmp_path, 1, "hash")["text"] == "测试文本"
    assert service.lookup_cached_transcripts(tmp_path, [1])[1]["model"] == CTC
    whisper = voice.VoiceTranscriptionService(voice.VoiceTranscriptionConfig(model="tiny"))
    assert whisper._read_cache(tmp_path, 1, "hash") is None
    monkeypatch.setitem(assets.SPECS, CTC, {**assets.SPECS[CTC], "revision": "updated"})
    updated = voice.VoiceTranscriptionService(voice.VoiceTranscriptionConfig(model=CTC))
    assert updated._read_cache(tmp_path, 1, "hash") is None
    assert updated.lookup_cached_transcripts(tmp_path, [1]) == {}


def test_select_new_model_matches_device_without_remapping_legacy(monkeypatch):
    monkeypatch.setattr(voice, "read_effective_voice_transcription_model", lambda: ("medium", "settings"))
    monkeypatch.setattr(voice, "read_effective_voice_transcription_device", lambda: ("cpu", "settings"))
    monkeypatch.setattr(voice, "get_voice_transcription_service", lambda: SimpleNamespace(config=voice.VoiceTranscriptionConfig()))
    monkeypatch.setattr(voice, "dependency_status", lambda _: (True, ""))
    monkeypatch.setattr(voice, "inspect_model_readiness", lambda _: dict(ready=True))
    monkeypatch.setattr(voice, "probe_qwen_cuda", lambda: dict(available=True))
    monkeypatch.setattr(voice, "_reset_voice_transcription_service", lambda: SimpleNamespace(status=lambda: {}))
    save_model, save_device = Mock(), Mock()
    monkeypatch.setattr(voice, "write_voice_transcription_model_setting", save_model)
    monkeypatch.setattr(voice, "write_voice_transcription_device_setting", save_device)
    voice.set_voice_transcription_model(GPU)
    save_model.assert_called_once_with(GPU)
    save_device.assert_called_once_with("cuda")
    voice.set_voice_transcription_model("tiny")
    assert save_device.call_count == 1
    assert save_model.call_args.args == ("tiny",)


def test_env_device_lock_rejects_incompatible_model(monkeypatch):
    monkeypatch.setattr(voice, "read_effective_voice_transcription_model", lambda: ("medium", "settings"))
    monkeypatch.setattr(voice, "read_effective_voice_transcription_device", lambda: ("cpu", "env"))
    monkeypatch.setattr(voice, "get_voice_transcription_service", lambda: SimpleNamespace(config=voice.VoiceTranscriptionConfig()))
    with pytest.raises(voice.VoiceTranscriptionError, match="不兼容") as caught:
        voice.set_voice_transcription_model(GPU)
    assert caught.value.code == "device_locked"


def test_qwen_gpu_failure_does_not_fall_back_to_cpu(monkeypatch):
    fake = SimpleNamespace(transcribe_audio=Mock(side_effect=AsrError("gpu_unavailable", "CUDA unavailable")))
    loader = Mock(return_value=fake)
    service = voice.VoiceTranscriptionService(voice.VoiceTranscriptionConfig(model=GPU, device="cuda"), model_loader=loader)
    fallback = Mock()
    monkeypatch.setattr(service, "_load_cpu_fallback", fallback)
    with pytest.raises(voice.VoiceTranscriptionError) as caught:
        service._transcribe_with_fallback(Path("test.wav"), cancel_event=None)
    assert caught.value.code == "gpu_unavailable"
    assert not fallback.called
    assert loader.call_count == 1
    service.retire()


def test_gpu_status_uses_torch_probe_not_ctranslate(monkeypatch):
    monkeypatch.setattr(voice, "dependency_status", lambda _: (True, ""))
    monkeypatch.setattr(voice, "probe_cuda", lambda: dict(available=True, devices=[], reason=""))
    monkeypatch.setattr(voice, "probe_qwen_cuda", lambda: dict(available=False, devices=[], reason="PyTorch CUDA missing"))
    monkeypatch.setattr(voice, "get_voice_model_catalog", lambda **_: [])
    service = voice.VoiceTranscriptionService(voice.VoiceTranscriptionConfig(model=GPU, device="cuda"))
    monkeypatch.setattr(service, "_model_readiness", lambda: dict(ready=True))
    status = service.status()
    assert not status["available"]
    assert not status["usingFallback"]
    assert "PyTorch" in status["reason"]


@pytest.mark.parametrize("model", [CTC, CPU, GPU, "qwen3-asr-17b-hf"])
def test_new_backends_bound_concurrency(model):
    config = voice.VoiceTranscriptionConfig(model=model, num_workers=99)
    assert voice.resolve_voice_transcription_batch_concurrency(99, config) == (99, 1)
    service = voice.VoiceTranscriptionService(config)
    assert service.configure_inference_concurrency(99) == 1


def test_long_audio_chunks_preserve_every_sample_and_bound_length():
    audio = np.linspace(-0.2, 0.2, 16000 * 61, dtype=np.float32)
    chunks = list(audio_chunks(audio, 15))
    assert all(0 < len(x) <= 15 * 16000 for x in chunks)
    np.testing.assert_array_equal(np.concatenate(chunks), audio)


def test_silence_features_are_finite_and_expected_shape():
    features = log_mel(np.zeros(16000, dtype=np.float32), mel_filters())
    assert features.shape == (1, 128, 100)
    assert np.isfinite(features).all()
    np.testing.assert_allclose(features, -1.5)


def test_cancel_terminates_worker_during_pending_inference(monkeypatch):
    backend = ProcessBackend("zipformer", "unused", "int8")
    cancelled = threading.Event()
    connection = Mock()
    connection.poll.side_effect = lambda _: (cancelled.set() or False)
    backend.connection = connection
    backend.process = Mock()
    monkeypatch.setattr(backend, "_start", lambda: None)
    close = Mock()
    monkeypatch.setattr(backend, "close", close)
    with pytest.raises(AsrCancelled):
        backend.transcribe_audio("test.wav", "zh", cancelled)
    close.assert_called_once()


def test_close_reaps_worker_and_releases_connection():
    backend = ProcessBackend("zipformer", "unused", "int8")
    process = Mock(pid=123)
    process.is_alive.side_effect = [True, False]
    connection = Mock()
    backend.process, backend.connection = process, connection
    backend.close()
    process.terminate.assert_called_once()
    process.join.assert_called_once_with(timeout=5)
    connection.close.assert_called_once()
    assert backend.process is None and backend.connection is None
