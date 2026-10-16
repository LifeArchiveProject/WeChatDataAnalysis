"""按需下载 Qwen GPU 组件；只在隔离语音进程中加载，不修改系统 Python。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
import threading
import time
from urllib.parse import urlparse
import zipfile

from .app_paths import get_data_dir

MANIFEST_PATH = Path(__file__).parent / "resources/qwen_gpu_runtime.json"
MODEL_ID = "qwen3-asr-06b-hf"
_DLL_HANDLES = []
_MANAGER = None
_MANAGER_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def runtime_root():
    return get_data_dir() / "voice_runtimes" / manifest()["id"] / f"cp{sys.version_info.major}{sys.version_info.minor}"


def runtime_files():
    return manifest()["variants"].get(f"cp{sys.version_info.major}{sys.version_info.minor}", [])


def supported():
    return sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"} and bool(runtime_files())


def installed():
    root = runtime_root()
    try:
        saved = json.loads((root / "installed.json").read_text(encoding="utf-8"))
        return (saved == dict(id=manifest()["id"], files=runtime_files()) and
                not root.is_symlink() and (root / "torch/lib/torch_cuda.dll").is_file() and
                (root / "transformers/__init__.py").is_file())
    except (OSError, ValueError):
        return False


def activate_for_worker(root=None):
    """父进程不导入组件；DLL 目录句柄保留到工作进程退出。"""
    folder = Path(root) if root else runtime_root() if installed() else None
    if folder is None:
        return
    sys.path.insert(0, str(folder))
    if os.name == "nt":
        for directory in (folder / "torch/lib", folder / "numpy.libs"):
            if directory.is_dir():
                _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
    # 外置 wheel 的元数据也必须可见，Transformers 会检查其依赖版本。
    import importlib
    importlib.invalidate_caches()


class Paused(Exception):
    pass


class QwenRuntimeManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.thread = None
        self.job_path = get_data_dir() / "voice_runtimes/qwen-job.json"
        try:
            self.job = json.loads(self.job_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.job = dict(status="idle", stage="idle", bytes=0, total=0, error="")
        if self.job.get("status") in {"queued", "running"}:
            self.job.update(status="paused", stage="paused", error="上次安装已中断，点击继续。")

    def update(self, **values):
        with self.lock:
            self.job.update(values, updated=time.time())
            self.job_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.job_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.job, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.job_path)

    def status(self):
        with self.lock:
            return dict(installed=installed(), supported=supported(),
                        size=sum(f["size"] for f in runtime_files()), version=manifest()["id"],
                        job=dict(self.job), reason="" if supported() else "此组件支持 Windows x64 的 Python 3.11–3.13，请选择 CPU 模型。")

    def start(self):
        from .runtime_settings import read_effective_voice_transcription_model, read_effective_voice_transcription_device
        if read_effective_voice_transcription_model()[1] == "env":
            raise ValueError("语音模型由启动环境变量固定，无法安装并启用其他模型。")
        device, device_source = read_effective_voice_transcription_device()
        if device_source == "env" and device != "cuda":
            raise ValueError("启动环境变量固定为 CPU，无法启用 Qwen GPU，请选择 CPU 模型。")
        if not supported():
            raise ValueError(self.status()["reason"])
        from .local_search.gpu import gpu_devices
        if not gpu_devices():
            raise ValueError("未检测到 NVIDIA 显卡，请检查显卡驱动或选择 CPU 模型。")
        with self.lock:
            if self.thread and self.thread.is_alive():
                return self.status()
            self.cancelled.clear()
            self.update(status="queued", stage="preparing", error="", bytes=0,
                        total=sum(f["size"] for f in runtime_files()), modelJobId="")
            self.thread = threading.Thread(target=self.run, name="qwen-runtime-install", daemon=True)
            self.thread.start()
            return self.status()

    def checkpoint(self):
        if self.cancelled.is_set():
            raise Paused()

    def pause(self):
        with self.lock:
            self.cancelled.set()
            job_id = self.job.get("modelJobId")
        if job_id:
            from .voice_transcription import VOICE_MODEL_DOWNLOAD_MANAGER
            # 已完成的模型不会删除；暂停时只终止当前尚未完成的模型下载。
            with VOICE_MODEL_DOWNLOAD_MANAGER._lock:
                event = VOICE_MODEL_DOWNLOAD_MANAGER._cancel_events.get(job_id)
                if event:
                    event.set()
        return self.status()

    def hash_file(self, path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(4 * 1024 * 1024):
                self.checkpoint()
                digest.update(block)
        return digest.hexdigest()

    def download(self, client, item, path, completed):
        import httpx
        if urlparse(item["url"]).hostname not in {"files.pythonhosted.org", "download-r2.pytorch.org", "download.pytorch.org"}:
            raise ValueError("组件下载地址不在固定发布清单中。")
        for attempt in range(5):
            self.checkpoint()
            offset = path.stat().st_size if path.exists() else 0
            if offset == item["size"]:
                break
            if offset > item["size"]:
                path.unlink()
                offset = 0
            try:
                with client.stream("GET", item["url"], headers={"Range": f"bytes={offset}-"} if offset else {}) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        if not response.headers.get("content-range", "").startswith(f"bytes {offset}-"):
                            raise ValueError("组件下载续传位置不正确，请重试。")
                    elif offset:
                        offset = 0
                    self.update(stage="downloading", file=item["package"], bytes=completed + offset)
                    last_update = 0.0
                    with path.open("ab" if offset else "wb") as output:
                        for block in response.iter_bytes(256 * 1024):
                            self.checkpoint()
                            output.write(block)
                            offset += len(block)
                            if offset > item["size"]:
                                raise ValueError("组件下载大小超过清单，请重试。")
                            if time.monotonic() - last_update > .3:
                                self.update(bytes=completed + offset)
                                last_update = time.monotonic()
                if offset != item["size"]:
                    raise httpx.ReadError("下载文件不完整")
                break
            except httpx.HTTPError:
                if attempt == 4:
                    raise ValueError("组件下载失败，检查网络后点击重试；已下载部分会保留。") from None
                self.update(stage="retry_wait")
                if self.cancelled.wait(min(15, 2 ** attempt)):
                    raise Paused()
        self.update(stage="verifying")
        if self.hash_file(path) != item["sha256"]:
            path.unlink(missing_ok=True)
            raise ValueError("组件校验失败，损坏文件已清除，请重试。")

    def install(self):
        import httpx
        root = runtime_root()
        cache = root.parent / "downloads"
        cache.mkdir(parents=True, exist_ok=True)
        stage = root.with_name(root.name + ".staging")
        # 清理路径必须是此版本下固定的临时目录，且拒绝目录联接。
        if stage.exists():
            self.ensure_owned(stage)
            shutil.rmtree(stage)
        stage.mkdir()
        completed = 0
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            for item in runtime_files():
                path = cache / item["name"]
                self.ensure_owned(path)
                self.download(client, item, path, completed)
                self.update(stage="installing", file=item["package"])
                with zipfile.ZipFile(path) as archive:
                    for member in archive.infolist():
                        self.checkpoint()
                        target = stage / member.filename
                        if (not target.resolve().is_relative_to(stage.resolve()) or
                                (member.external_attr >> 16) & 0o170000 == 0o120000):
                            raise ValueError("组件包含无效文件路径。")
                        archive.extract(member, stage)
                completed += item["size"]
                self.update(bytes=completed)
        self.checkpoint()
        self.update(stage="checking_runtime")
        from .asr_worker import check_qwen_runtime
        result = check_qwen_runtime(str(stage), cancel_event=self.cancelled)
        if not result["available"]:
            raise ValueError(result["reason"])
        self.checkpoint()
        (stage / "installed.json").write_text(json.dumps(dict(id=manifest()["id"], files=runtime_files())), encoding="utf-8")
        if root.exists():
            self.ensure_owned(root)
            shutil.rmtree(root)
        stage.rename(root)

    def ensure_owned(self, path):
        base = get_data_dir().resolve()
        if not path.resolve().is_relative_to(base):
            raise ValueError("组件目录位于应用数据目录之外。")
        for ancestor in (path, *path.parents):
            if ancestor == base:
                break
            try:
                reparse = bool(getattr(ancestor.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            except FileNotFoundError:
                reparse = False
            if ancestor.is_symlink() or reparse:
                raise ValueError("组件目录不能使用符号链接或目录联接。")

    def run(self):
        try:
            self.update(status="running")
            self.ensure_owned(runtime_root())
            if not installed():
                needed = sum(f["size"] for f in runtime_files()) * 3
                get_data_dir().mkdir(parents=True, exist_ok=True)
                if shutil.disk_usage(get_data_dir()).free < needed:
                    raise ValueError("磁盘空间不足，组件下载和解压需要约 9 GB 可用空间。")
                self.install()
            self.checkpoint()
            from .voice_transcription import (VOICE_MODEL_DOWNLOAD_MANAGER, inspect_model_readiness,
                                              set_voice_transcription_model, _managed_voice_model_dir, _legacy_voice_model_dir,
                                              _model_directory_is_ready)
            if not inspect_model_readiness(MODEL_ID)["ready"]:
                model_job = VOICE_MODEL_DOWNLOAD_MANAGER.start(MODEL_ID)
                self.update(stage="downloading_model", modelJobId=model_job["jobId"])
                while True:
                    self.checkpoint()
                    job = VOICE_MODEL_DOWNLOAD_MANAGER.get(model_job["jobId"])
                    self.update(modelPercent=job["percent"])
                    if job["status"] == "done":
                        break
                    if job["status"] in {"error", "cancelled"}:
                        raise ValueError(job["error"] or "模型下载已停止，请重试。")
                    self.cancelled.wait(.5)
            self.checkpoint()
            self.update(stage="checking_model")
            from .asr_worker import check_qwen_runtime, invalidate_qwen_probe
            folder = _managed_voice_model_dir(MODEL_ID)
            if not _model_directory_is_ready(folder, MODEL_ID):
                folder = _legacy_voice_model_dir(MODEL_ID)
            result = check_qwen_runtime(folder=str(folder), cancel_event=self.cancelled)
            if not result["available"]:
                raise ValueError(result["reason"])
            # 最后一步才改设置；暂停与启用互斥，失败保留原来的模型。
            with self.lock:
                self.checkpoint()
                invalidate_qwen_probe()
                set_voice_transcription_model(MODEL_ID)
                self.update(status="done", stage="done", error="", modelJobId="")
        except Paused:
            self.update(status="paused", stage="paused", error="", modelJobId="")
        except Exception as exc:
            logger.exception("Qwen GPU 组件准备失败")
            message = str(exc) if isinstance(exc, ValueError) else getattr(exc, "user_message", "")
            self.update(status="error", stage="error", error=message or
                        "GPU 组件安装或加载失败，请重试或选择 CPU 模型。", modelJobId="")


def get_qwen_runtime():
    global _MANAGER
    with _MANAGER_LOCK:
        # 测试和用户数据目录变更时，不复用另一个目录的任务。
        if _MANAGER is None or _MANAGER.job_path.parent != get_data_dir() / "voice_runtimes":
            _MANAGER = QwenRuntimeManager()
        return _MANAGER
