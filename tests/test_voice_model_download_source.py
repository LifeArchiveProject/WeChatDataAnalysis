"""语音模型下载源的持久化、接口边界与单次下载一致性。"""
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wechat_decrypt_tool import runtime_settings as settings
from wechat_decrypt_tool import voice_transcription as voice
from wechat_decrypt_tool.routers import chat_media


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("WECHAT_TOOL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(voice.httpx, "head", Mock(return_value=httpx.Response(200)))


def test_download_source_persists_without_changing_model_or_device():
    settings.write_voice_transcription_model_setting("turbo")
    settings.write_voice_transcription_device_setting("cuda")
    assert settings.read_voice_model_download_source() == "huggingface"
    for source in ("hf-mirror", "huggingface"):
        settings.write_voice_model_download_source(source)
        assert settings.read_voice_model_download_source() == source
        assert settings._read_runtime_settings()[settings.VOICE_MODEL_DOWNLOAD_SOURCE_KEY] == source
        assert settings.read_voice_transcription_model_setting() == "turbo"
        assert settings.read_voice_transcription_device_setting() == "cuda"


@pytest.mark.parametrize("value", ["unknown", "https://example.com", [], None])
def test_invalid_saved_source_falls_back_to_official(value):
    settings._write_runtime_settings({settings.VOICE_MODEL_DOWNLOAD_SOURCE_KEY: value})
    assert settings.read_voice_model_download_source() == "huggingface"


@pytest.mark.parametrize("model", list(voice.VOICE_MODEL_REPOSITORIES))
@pytest.mark.parametrize("source", ["huggingface", "hf-mirror"])
def test_all_models_use_selected_source_for_metadata_and_files(model, source, tmp_path, monkeypatch):
    from huggingface_hub import constants

    settings.write_voice_model_download_source(source)
    monkeypatch.setenv("HF_ENDPOINT", "https://example.com")
    original_endpoint = constants.ENDPOINT
    calls = []

    def snapshot(repo, **kwargs):
        calls.append((repo, kwargs))
        if kwargs.get("dry_run"):
            # 下载期间切换设置，当前文件请求仍应使用原先选定的源。
            settings.write_voice_model_download_source("huggingface" if source == "hf-mirror" else "hf-mirror")
            return [SimpleNamespace(file_size=100)]
        return kwargs["local_dir"]

    monkeypatch.setattr("huggingface_hub.snapshot_download", snapshot)
    result = voice._download_voice_model_snapshot(model, output_dir=tmp_path, progress_callback=lambda **_: None)
    assert result == tmp_path
    assert len(calls) == 2
    for repo, kwargs in calls:
        assert repo == voice.VOICE_MODEL_REPOSITORIES[model]
        assert kwargs["endpoint"] == settings.VOICE_MODEL_DOWNLOAD_ENDPOINTS[source]
        assert kwargs["token"] is False
        if model in voice.ASR_MODEL_SPECS:
            assert kwargs["revision"] == voice.ASR_MODEL_SPECS[model]["revision"]
            assert set(kwargs["allow_patterns"]) == set(voice.ASR_MODEL_SPECS[model]["files"])
    assert constants.ENDPOINT == original_endpoint
    assert os.environ["HF_ENDPOINT"] == "https://example.com"

    calls.clear()
    voice._download_voice_model_snapshot(model, output_dir=tmp_path, progress_callback=lambda **_: None)
    assert calls[0][1]["endpoint"] != settings.VOICE_MODEL_DOWNLOAD_ENDPOINTS[source]


def test_failed_metadata_probe_keeps_mirror_for_actual_download(tmp_path, monkeypatch):
    settings.write_voice_model_download_source("hf-mirror")
    snapshot = Mock(side_effect=[TimeoutError("metadata timeout"), str(tmp_path)])
    monkeypatch.setattr("huggingface_hub.snapshot_download", snapshot)
    assert voice._download_voice_model_snapshot("turbo", output_dir=tmp_path, progress_callback=lambda **_: None) == tmp_path
    assert all(call.kwargs["endpoint"] == "https://hf-mirror.com" for call in snapshot.call_args_list)


@pytest.mark.parametrize("status, location, expected", [
    (308, "https://huggingface.co/api/models/pkufool/zipformer-small", "https://huggingface.co"),
    (301, "https://huggingface.co/api/models/pkufool/zipformer-small", "https://huggingface.co"),
    (302, "https://huggingface.co/api/models/pkufool/zipformer-small", "https://hf-mirror.com"),
    (308, "https://example.com/api/models/pkufool/zipformer-small", "https://hf-mirror.com"),
    (308, "https://huggingface.co/api/models/other/repo", "https://hf-mirror.com"),
])
def test_mirror_permanent_redirect_is_limited_to_same_official_repo(status, location, expected, monkeypatch):
    head = Mock(return_value=httpx.Response(status, headers={"location": location}))
    monkeypatch.setattr(voice.httpx, "head", head)
    assert voice._voice_model_download_endpoint("hf-mirror", "pkufool/zipformer-small") == expected
    head.assert_called_once_with("https://hf-mirror.com/api/models/pkufool/zipformer-small", follow_redirects=False, timeout=5.0)


def test_failed_probe_does_not_switch_sources(monkeypatch):
    head = Mock(side_effect=httpx.ConnectTimeout("probe timeout"))
    monkeypatch.setattr(voice.httpx, "head", head)
    assert voice._voice_model_download_endpoint("hf-mirror", "pkufool/zipformer-small") == "https://hf-mirror.com"
    head.reset_mock()
    assert voice._voice_model_download_endpoint("huggingface", "pkufool/zipformer-small") == "https://huggingface.co"
    head.assert_not_called()


@pytest.fixture
def client(monkeypatch):
    service = SimpleNamespace(status=lambda: {"modelDownloadSource": settings.read_voice_model_download_source()})
    monkeypatch.setattr(voice, "get_voice_transcription_service", lambda: service)
    reset = Mock(side_effect=AssertionError("切换下载源不应重建推理服务"))
    monkeypatch.setattr(voice, "_reset_voice_transcription_service", reset)
    app = FastAPI()
    app.include_router(chat_media.router)
    with TestClient(app, base_url="http://127.0.0.1:10392", client=("127.0.0.1", 50000)) as client:
        yield client


def test_settings_api_saves_and_returns_download_source(client):
    for source in ("hf-mirror", "huggingface"):
        response = client.put("/api/chat/media/voice/transcription/settings", json={"download_source": source})
        assert response.status_code == 200
        assert response.json()["configuration"]["modelDownloadSource"] == source
        assert settings.read_voice_model_download_source() == source


@pytest.mark.parametrize("body, status", [
    ({"download_source": "https://example.com"}, 422),
    ({"download_source": ""}, 422),
    ({"download_source": "hf-mirror", "device": "cpu"}, 400),
    ({"download_source": "hf-mirror", "model": "turbo"}, 400),
    ({}, 400),
])
def test_settings_api_rejects_invalid_or_combined_source_updates(client, body, status):
    response = client.put("/api/chat/media/voice/transcription/settings", json=body)
    assert response.status_code == status
    assert settings.read_voice_model_download_source() == "huggingface"


def test_save_failure_does_not_report_success(client, monkeypatch):
    monkeypatch.setattr(settings, "_write_runtime_settings", lambda _: None)
    response = client.put("/api/chat/media/voice/transcription/settings", json={"download_source": "hf-mirror"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "download_source_save_failed"
    assert settings.read_voice_model_download_source() == "huggingface"
