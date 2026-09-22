"""可取消、空闲自动退出的本地语音工作进程；模型和语音不会联网。"""
from __future__ import annotations

import multiprocessing
import os
import threading
import time


class AsrCancelled(RuntimeError):
    pass


class AsrError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _worker(connection, backend: str, folder: str, threads: int):
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      HF_HUB_DISABLE_PROGRESS_BARS="1", OMP_NUM_THREADS=str(threads),
                      MKL_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS=str(threads))
    model = None
    try:
        from .asr_backends import audio_chunks, load_backend, read_audio
        import numpy as np
        while connection.poll(120):
            request = connection.recv()
            try:
                if model is None:
                    model = load_backend(backend, folder, threads)
                audio = read_audio(request["path"])
                texts = []
                for chunk in audio_chunks(audio, model.chunk_seconds):
                    # 跳过纯静音，避免自回归模型无中生有。
                    if float(np.max(np.abs(chunk))) > 1e-6:
                        texts.append(model.transcribe(chunk, request["language"]))
                separator = " " if request["language"] not in ("zh", "yue", "ja") else ""
                connection.send(dict(text=separator.join(texts), duration=len(audio) / 16000,
                                     language=request["language"], precision=model.precision))
            except Exception as exc:
                code = "dependency_missing" if isinstance(exc, ImportError) else "transcription_failed"
                connection.send(dict(error=str(exc)[:500], code=code))
                # 错误后退出，释放可能处于半初始化状态的模型和 CUDA 显存。
                break
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class ProcessBackend:
    def __init__(self, backend: str, folder: str, precision: str, threads: int = 4):
        self.backend, self.folder, self.precision = backend, folder, precision
        self.threads = max(1, min(threads, os.cpu_count() or 1))
        self.process = None
        self.connection = None

    @property
    def is_loaded(self):
        return self.process is not None and self.process.is_alive()

    def _start(self):
        if self.process is not None and self.process.is_alive():
            return
        self.close()
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_worker, args=(child, self.backend, self.folder, self.threads), daemon=True)
        try:
            self.process.start()
        finally:
            child.close()

    def transcribe_audio(self, path: str, language: str, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise AsrCancelled()
        self._start()
        deadline = time.monotonic() + 900
        try:
            self.connection.send(dict(path=path, language=language))
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise AsrCancelled()
                if time.monotonic() >= deadline:
                    raise AsrError("transcription_timeout", "识别等待超时，请改用 Zipformer CTC 或较小模型。")
                if self.connection.poll(0.05):
                    result = self.connection.recv()
                    if "error" in result:
                        raise AsrError(result["code"], result["error"])
                    self.precision = result["precision"]
                    return result
                if not self.process.is_alive():
                    raise AsrError("worker_exited", "语音工作进程已退出，可能内存不足；请重试或选择较小模型。")
        except (EOFError, BrokenPipeError, OSError) as exc:
            self.close()
            raise AsrError("worker_exited", "语音工作进程中断，请重试或选择较小模型。") from exc
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.process is not None:
            if self.process.pid is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=5)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(timeout=2)
            self.process.close()
            self.process = None


def _torch_probe(connection):
    try:
        import torch
        count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        connection.send(dict(available=count > 0, deviceCount=count,
            devices=[dict(name=torch.cuda.get_device_name(i)) for i in range(count)],
            reason="" if count else "PyTorch CUDA 不可用，请安装 GPU 运行组件和显卡驱动，或选择 CPU 模型。"))
    except Exception:
        connection.send(dict(available=False, deviceCount=0, devices=[], reason="Qwen GPU 运行组件无法加载，请更新 GPU 组件或选择 CPU 模型。"))
    finally:
        connection.close()


_PROBE_LOCK = threading.Lock()
_PROBE_CACHE = None


def probe_qwen_cuda():
    global _PROBE_CACHE
    with _PROBE_LOCK:
        if _PROBE_CACHE and time.monotonic() < _PROBE_CACHE[0]:
            return dict(_PROBE_CACHE[1])
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_torch_probe, args=(child,), daemon=True)
        result = dict(available=False, deviceCount=0, devices=[], reason="Qwen GPU 检测未完成，请检查运行组件或改用 CPU 模型。")
        try:
            process.start()
            child.close()
            if parent.poll(30):
                result = parent.recv()
        except (EOFError, OSError, RuntimeError):
            pass
        finally:
            parent.close()
            child.close()
            if process.pid is not None:
                process.join(timeout=1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
                process.close()
        _PROBE_CACHE = (time.monotonic() + 60, result)
        return dict(result)
