"""覆盖组件续传、文件校验、暂停恢复及失败时保留模型设置。"""
import hashlib
import io
import json
from pathlib import Path
import threading
import zipfile

import httpx
import pytest

from wechat_decrypt_tool import qwen_gpu_runtime as runtime


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("WECHAT_TOOL_DATA_DIR", str(tmp_path))
    return runtime.QwenRuntimeManager()


def item(data):
    return dict(name="test.whl", package="test", size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                url="https://files.pythonhosted.org/test.whl")


def test_range_resume_verifies_complete_file(manager, tmp_path):
    data = b"real-file-content"
    target = tmp_path / "test.whl"
    target.write_bytes(data[:5])
    def handler(request):
        assert request.headers["range"] == "bytes=5-"
        return httpx.Response(206, content=data[5:], headers={"content-range": f"bytes 5-{len(data)-1}/{len(data)}"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        manager.download(client, item(data), target, 0)
    assert target.read_bytes() == data


def test_server_ignoring_range_restarts_file(manager, tmp_path):
    data = b"new-content"
    target = tmp_path / "test.whl"
    target.write_bytes(b"new")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=data))) as client:
        manager.download(client, item(data), target, 0)
    assert target.read_bytes() == data


def test_invalid_range_is_rejected(manager, tmp_path):
    target = tmp_path / "test.whl"
    target.write_bytes(b"x")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(206, content=b"x", headers={"content-range": "bytes 0-1/2"}))) as client:
        with pytest.raises(ValueError, match="续传位置"):
            manager.download(client, item(b"xx"), target, 0)


def test_corrupt_download_is_removed(manager, tmp_path):
    target = tmp_path / "test.whl"
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"bad"))) as client:
        with pytest.raises(ValueError, match="校验失败"):
            manager.download(client, item(b"yes"), target, 0)
    assert not target.exists()


def test_pause_preserves_partial_file(manager, tmp_path):
    target = tmp_path / "test.whl"
    target.write_bytes(b"partial")
    manager.cancelled.set()
    with httpx.Client() as client, pytest.raises(runtime.Paused):
        manager.download(client, item(b"partial-data"), target, 0)
    assert target.read_bytes() == b"partial"


def test_restart_requires_explicit_resume(manager):
    manager.update(status="running", stage="downloading", bytes=123)
    restarted = runtime.QwenRuntimeManager()
    assert restarted.status()["job"]["status"] == "paused"
    assert restarted.status()["job"]["bytes"] == 123
    assert restarted.thread is None


def test_manifest_has_compatible_pinned_windows_wheels():
    from packaging.tags import compatible_tags, cpython_tags
    from packaging.utils import parse_wheel_filename
    for abi, files in runtime.manifest()["variants"].items():
        minor = int(abi[3:])
        tags = set(cpython_tags((3, minor), abis=[abi], platforms=["win_amd64"]))
        tags.update(compatible_tags((3, minor), interpreter=abi, platforms=["win_amd64"]))
        assert {f["package"] for f in files} >= {"torch", "transformers", "numpy", "tokenizers", "safetensors"}
        for f in files:
            assert parse_wheel_filename(f["name"])[3] & tags
            assert len(f["sha256"]) == 64 and f["size"] > 0


def test_archive_escape_is_refused_before_publishing(manager, tmp_path, monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escaped.txt", "no")
    data = payload.getvalue()
    root = tmp_path / "voice_runtimes/version/cp311"
    monkeypatch.setattr(runtime, "runtime_root", lambda: root)
    monkeypatch.setattr(runtime, "runtime_files", lambda: [item(data)])
    def download(client, entry, path, completed):
        path.write_bytes(data)
    monkeypatch.setattr(manager, "download", download)
    with pytest.raises(ValueError, match="文件路径"):
        manager.install()
    assert not (root / "installed.json").exists()
    assert not (root.parent / "escaped.txt").exists()


def test_failed_install_keeps_current_model(manager, monkeypatch):
    from wechat_decrypt_tool import voice_transcription as voice
    selections = []
    monkeypatch.setattr(runtime, "installed", lambda: False)
    monkeypatch.setattr(manager, "install", lambda: (_ for _ in ()).throw(ValueError("检查失败")))
    monkeypatch.setattr(voice, "set_voice_transcription_model", selections.append)
    manager.run()
    assert selections == []
    assert manager.status()["job"]["status"] == "error"


def test_outside_application_directory_is_refused(manager, tmp_path):
    with pytest.raises(ValueError, match="数据目录之外"):
        manager.ensure_owned(tmp_path.parent / "outside-runtime")


def test_duplicate_start_reuses_active_task(manager, monkeypatch):
    from wechat_decrypt_tool.local_search import gpu
    monkeypatch.setattr(runtime, "supported", lambda: True)
    monkeypatch.setattr(gpu, "gpu_devices", lambda: [dict(name="test")])
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(manager, "run", lambda: (entered.set(), release.wait(2)))
    manager.start()
    assert entered.wait(1)
    thread = manager.thread
    manager.start()
    assert manager.thread is thread
    release.set()
    thread.join(2)


def test_cpu_device_locked_rejects_before_download(manager, monkeypatch):
    monkeypatch.setenv("WECHAT_TOOL_WHISPER_DEVICE", "cpu")
    with pytest.raises(ValueError, match="固定为 CPU"):
        manager.start()
    assert manager.thread is None


def test_cancelled_model_download_does_not_hang_or_switch_model(manager, monkeypatch):
    from wechat_decrypt_tool import voice_transcription as voice
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(voice, "inspect_model_readiness", lambda _: dict(ready=False))
    monkeypatch.setattr(voice.VOICE_MODEL_DOWNLOAD_MANAGER, "start", lambda _: dict(jobId="cancelled-test"))
    monkeypatch.setattr(voice.VOICE_MODEL_DOWNLOAD_MANAGER, "get", lambda _: dict(status="cancelled", percent=5, error=""))
    selections=[]
    monkeypatch.setattr(voice, "set_voice_transcription_model", selections.append)
    manager.run()
    assert manager.status()["job"]["status"] == "error"
    assert "下载已停止" in manager.status()["job"]["error"]
    assert selections == []


def test_missing_model_is_downloaded_and_checked_before_selection(manager, monkeypatch):
    from wechat_decrypt_tool import voice_transcription as voice, asr_worker
    calls=[]
    monkeypatch.setattr(runtime, "installed", lambda: True)
    monkeypatch.setattr(voice, "inspect_model_readiness", lambda _: dict(ready=False))
    monkeypatch.setattr(voice, "_model_directory_is_ready", lambda *args: True)
    monkeypatch.setattr(voice.VOICE_MODEL_DOWNLOAD_MANAGER, "start", lambda _: (calls.append('download') or dict(jobId='test')))
    monkeypatch.setattr(voice.VOICE_MODEL_DOWNLOAD_MANAGER, "get", lambda _: dict(status='done', percent=100))
    monkeypatch.setattr(asr_worker, "check_qwen_runtime", lambda **kwargs: (calls.append('check_model') or dict(available=True)))
    monkeypatch.setattr(voice, "set_voice_transcription_model", lambda _: calls.append('select'))
    manager.run()
    assert calls == ['download', 'check_model', 'select']
    assert manager.status()['job']['status'] == 'done'


