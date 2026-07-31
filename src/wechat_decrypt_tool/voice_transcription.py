from __future__ import annotations

import hashlib
import gc
import importlib.util
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional


TRANSCRIPT_TEXT_VERSION = 1
_OPENCC_CONVERTER: Any = None
_OPENCC_LOOKED_UP = False
_CUDA_PROBE_CACHE_TTL_SECONDS = 5.0
_CUDA_PROBE_CACHE_LOCK = threading.Lock()
_CUDA_PROBE_CACHE: Optional[tuple[float, dict[str, Any]]] = None

from .runtime_settings import (
    VOICE_TRANSCRIPTION_DEVICE_CPU,
    VOICE_TRANSCRIPTION_DEVICE_CUDA,
    read_effective_voice_transcription_device,
    write_voice_transcription_device_setting,
)

class VoiceTranscriptionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "voice_transcription_failed")
        self.user_message = str(message or "Voice transcription failed.")


@dataclass(frozen=True)
class VoiceTranscriptionConfig:
    enabled: bool = True
    model: str = "medium"
    language: str = "zh"
    device: str = "cpu"
    compute_type: str = "int8"
    device_source: str = "default"
    allow_download: bool = False
    beam_size: int = 5

    @classmethod
    def from_env(cls) -> "VoiceTranscriptionConfig":
        enabled = _env_bool("WECHAT_TOOL_WHISPER_ENABLED", True)
        model = str(os.environ.get("WECHAT_TOOL_WHISPER_MODEL") or "medium").strip()
        language = str(os.environ.get("WECHAT_TOOL_WHISPER_LANGUAGE") or "zh").strip() or "zh"
        device, device_source = read_effective_voice_transcription_device()
        compute_type = str(os.environ.get("WECHAT_TOOL_WHISPER_COMPUTE_TYPE") or "").strip()
        if not compute_type:
            compute_type = "float16" if device == VOICE_TRANSCRIPTION_DEVICE_CUDA else "int8"
        allow_download = _env_bool("WECHAT_TOOL_WHISPER_ALLOW_DOWNLOAD", False)
        try:
            beam_size = max(1, min(10, int(os.environ.get("WECHAT_TOOL_WHISPER_BEAM_SIZE") or 5)))
        except Exception:
            beam_size = 5
        return cls(
            enabled=enabled,
            model=model,
            language=language,
            device=device,
            compute_type=compute_type,
            device_source=device_source,
            allow_download=allow_download,
            beam_size=beam_size,
        )

    def cpu_fallback(self) -> "VoiceTranscriptionConfig":
        return replace(
            self,
            device=VOICE_TRANSCRIPTION_DEVICE_CPU,
            compute_type="int8",
            device_source="fallback",
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _find_nvidia_smi() -> Optional[str]:
    executable = shutil.which("nvidia-smi")
    if executable:
        return executable
    if os.name == "nt":
        candidate = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        if candidate.is_file():
            return str(candidate)
        candidate = Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")
        if candidate.is_file():
            return str(candidate)
    return None


def _read_nvidia_smi_devices() -> list[dict[str, str]]:
    executable = _find_nvidia_smi()
    if not executable:
        return []
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []

    devices: list[dict[str, str]] = []
    for line in str(completed.stdout or "").splitlines():
        fields = [part.strip() for part in line.split(",")]
        if not fields or not fields[0]:
            continue
        devices.append(
            {
                "name": fields[0],
                "driverVersion": fields[1] if len(fields) > 1 else "",
                "memoryTotal": fields[2] if len(fields) > 2 else "",
            }
        )
    return devices


def _probe_cuda_uncached() -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "deviceCount": 0,
        "devices": _read_nvidia_smi_devices(),
        "reason": "",
    }
    try:
        import ctranslate2
    except Exception:
        result["reason"] = "未安装 CTranslate2 CUDA 运行依赖。"
        return result

    try:
        count = max(0, int(ctranslate2.get_cuda_device_count()))
    except Exception:
        result["reason"] = "未检测到可用的 NVIDIA CUDA 设备或驱动。"
        return result

    result["deviceCount"] = count
    if count <= 0:
        result["reason"] = "未检测到可用的 NVIDIA CUDA 设备或驱动。"
        return result

    result["available"] = True
    return result


def _copy_cuda_report(report: dict[str, Any]) -> dict[str, Any]:
    copied = dict(report)
    copied["devices"] = [dict(item) for item in (report.get("devices") or [])]
    return copied


def invalidate_cuda_probe_cache() -> None:
    global _CUDA_PROBE_CACHE
    with _CUDA_PROBE_CACHE_LOCK:
        _CUDA_PROBE_CACHE = None


def probe_cuda() -> dict[str, Any]:
    """Return a short-lived CUDA capability report without loading a Whisper model."""

    global _CUDA_PROBE_CACHE
    now = time.monotonic()
    with _CUDA_PROBE_CACHE_LOCK:
        cached = _CUDA_PROBE_CACHE
        if cached is not None and now < cached[0]:
            return _copy_cuda_report(cached[1])
        report = _probe_cuda_uncached()
        _CUDA_PROBE_CACHE = (time.monotonic() + _CUDA_PROBE_CACHE_TTL_SECONDS, report)
        return _copy_cuda_report(report)


def _public_model_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "/" in raw or "\\" in raw:
        return Path(raw.rstrip("/\\")).name or "local-model"
    return raw


def _model_directory_is_ready(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        required = ("model.bin", "config.json", "tokenizer.json")
        if not all((path / name).is_file() for name in required):
            return False
        return any(candidate.is_file() for candidate in path.glob("vocabulary.*"))
    except OSError:
        return False


def _looks_like_local_model_path(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    return bool(
        expanded.exists()
        or expanded.is_absolute()
        or raw.startswith((".", "~"))
        or "\\" in raw
        or re.match(r"^[A-Za-z]:[/\\]", raw)
    )


def inspect_model_readiness(model: str) -> dict[str, Any]:
    """Inspect a local directory or Hugging Face cache without loading or downloading a model."""

    raw = str(model or "").strip()
    if not raw:
        return {
            "ready": False,
            "downloadable": False,
            "source": "unavailable",
            "reason": "未配置 Whisper 模型。",
        }

    if _looks_like_local_model_path(raw):
        model_dir = Path(os.path.expandvars(os.path.expanduser(raw)))
        if _model_directory_is_ready(model_dir):
            return {"ready": True, "downloadable": False, "source": "local-directory", "reason": ""}
        return {
            "ready": False,
            "downloadable": False,
            "source": "local-directory",
            "reason": "配置的本地 Whisper 模型目录不存在或文件不完整。",
        }

    try:
        from faster_whisper.utils import download_model
    except Exception:
        return {
            "ready": False,
            "downloadable": True,
            "source": "huggingface-cache",
            "reason": "未安装 faster-whisper，无法检查模型缓存。",
        }

    try:
        cached_dir = Path(download_model(raw, local_files_only=True))
    except ValueError:
        return {
            "ready": False,
            "downloadable": False,
            "source": "unavailable",
            "reason": "Whisper 模型名称无效。",
        }
    except Exception:
        return {
            "ready": False,
            "downloadable": True,
            "source": "huggingface-cache",
            "reason": "Whisper 模型尚未下载到本机缓存。",
        }

    if _model_directory_is_ready(cached_dir):
        return {"ready": True, "downloadable": True, "source": "huggingface-cache", "reason": ""}
    return {
        "ready": False,
        "downloadable": True,
        "source": "huggingface-cache",
        "reason": "本机 Whisper 模型缓存文件不完整。",
    }


def _join_transcript_segments(values: Any) -> str:
    output = ""
    for value in values:
        part = str(value or "").strip()
        if not part:
            continue
        needs_space = bool(
            output
            and output[-1].isascii()
            and output[-1].isalnum()
            and part[0].isascii()
            and part[0].isalnum()
        )
        output += (" " if needs_space else "") + part
    return output.strip()


def normalize_transcript_text(value: Any) -> str:
    """使用 OpenCC 将转写文本统一为简体中文。"""

    global _OPENCC_CONVERTER, _OPENCC_LOOKED_UP
    text = str(value or "").strip()
    if not text:
        return ""
    if not _OPENCC_LOOKED_UP:
        _OPENCC_LOOKED_UP = True
        try:
            from opencc import OpenCC

            _OPENCC_CONVERTER = OpenCC("t2s")
        except Exception:
            _OPENCC_CONVERTER = None
    if _OPENCC_CONVERTER is None:
        raise VoiceTranscriptionError(
            "dependency_missing",
            "未安装 OpenCC 简繁转换依赖，无法保证转写结果为简体中文。",
        )
    try:
        return str(_OPENCC_CONVERTER.convert(text) or "").strip()
    except Exception as exc:
        raise VoiceTranscriptionError("text_normalization_failed", "转写文字转换为简体中文失败。") from exc


def _is_cuda_runtime_error(exc: BaseException) -> bool:
    """只识别 CUDA/cuDNN 运行时故障，避免把普通音频错误误判为 GPU 故障。"""

    seen: set[int] = set()
    current: Optional[BaseException] = exc
    markers = (
        "cuda",
        "cudnn",
        "cublas",
        "cufft",
        "curand",
        "libcudart",
        "no kernel image",
        "device-side assert",
    )
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if any(marker in message for marker in markers):
            return True
        current = current.__cause__ or current.__context__
    return False


def _coerce_blob(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    text = str(value or "").strip()
    if not text:
        return b""
    compact = re.sub(r"\s+", "", text)
    if compact.lower().startswith("0x"):
        compact = compact[2:]
    if len(compact) >= 2 and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        try:
            return bytes.fromhex(compact)
        except Exception:
            return b""
    return text.encode("utf-8", "replace")


def _convert_silk_to_browser_audio(data: bytes, *, preferred_format: str) -> tuple[bytes, str, str]:
    from .media_helpers import _convert_silk_to_browser_audio as convert

    return convert(data, preferred_format=preferred_format)


def load_voice_data(account_dir: Path, server_id: int) -> bytes:
    account_path = Path(account_dir)
    sid = int(server_id or 0)
    if sid <= 0:
        return b""

    media_db_path = account_path / "media_0.db"
    if media_db_path.exists():
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(media_db_path))
            row = conn.execute(
                "SELECT voice_data FROM VoiceInfo WHERE svr_id = ? ORDER BY create_time DESC LIMIT 1",
                (sid,),
            ).fetchone()
            if row:
                data = _coerce_blob(row[0])
                if data:
                    return data
        except Exception:
            pass
        finally:
            if conn is not None:
                conn.close()

    try:
        from .wcdb_realtime import WCDB_REALTIME, exec_query as _wcdb_exec_query

        realtime = WCDB_REALTIME.ensure_connected(account_path)
        media_dir = Path(realtime.db_storage_dir) / "message"
        sql = f"SELECT voice_data FROM VoiceInfo WHERE svr_id = {sid} ORDER BY create_time DESC LIMIT 1"
        for realtime_db_path in sorted(media_dir.glob("media_*.db")):
            if not realtime_db_path.is_file():
                continue
            try:
                with realtime.lock:
                    rows = _wcdb_exec_query(
                        realtime.handle,
                        kind="message",
                        path=str(realtime_db_path),
                        sql=sql,
                    )
            except Exception:
                rows = []
            if rows:
                data = _coerce_blob(rows[0].get("voice_data"))
                if data:
                    return data
    except Exception:
        pass
    return b""


class VoiceTranscriptionService:
    def __init__(
        self,
        config: Optional[VoiceTranscriptionConfig] = None,
        *,
        model_loader: Optional[Callable[[VoiceTranscriptionConfig], Any]] = None,
    ) -> None:
        self.config = config or VoiceTranscriptionConfig.from_env()
        self._model_loader = model_loader or self._load_faster_whisper_model
        self._model: Any = None
        self._active_device = ""
        self._active_compute_type = ""
        self._fallback_reason = ""
        self._model_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._model_readiness_lock = threading.Lock()
        self._model_readiness_cache: Optional[tuple[float, dict[str, Any]]] = None

    def _model_readiness(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._model_readiness_lock:
            cached = self._model_readiness_cache
            if cached is not None and now < cached[0]:
                return dict(cached[1])
            result = inspect_model_readiness(self.config.model)
            self._model_readiness_cache = (time.monotonic() + 5.0, result)
            return dict(result)

    def status(self) -> dict[str, Any]:
        try:
            dependency_available = importlib.util.find_spec("faster_whisper") is not None
        except Exception:
            dependency_available = False
        try:
            text_normalizer_available = importlib.util.find_spec("opencc") is not None
        except Exception:
            text_normalizer_available = False
        model_readiness = self._model_readiness()
        model_ready = bool(model_readiness.get("ready"))
        model_downloadable = bool(model_readiness.get("downloadable"))
        can_prepare_model = bool(self.config.allow_download and model_downloadable)
        cuda = probe_cuda()
        fallback_reason = self._fallback_reason
        if not fallback_reason and self.config.device == VOICE_TRANSCRIPTION_DEVICE_CUDA and not cuda["available"]:
            fallback_reason = f"{cuda['reason']} 首次识别会自动回退到 CPU。"
        available = bool(
            self.config.enabled
            and dependency_available
            and text_normalizer_available
            and self.config.model
            and (model_ready or can_prepare_model)
        )
        reason = ""
        if not self.config.enabled:
            reason = "语音转文字功能未启用。"
        elif not dependency_available:
            reason = "未安装 faster-whisper，请安装语音转文字可选依赖。"
        elif not text_normalizer_available:
            reason = "未安装 OpenCC，无法保证输出为简体中文。"
        elif not str(self.config.model or "").strip():
            reason = "未配置 Whisper 模型。"
        elif not model_ready:
            reason = str(model_readiness.get("reason") or "Whisper 模型尚未准备好。")
            if can_prepare_model:
                reason = f"{reason} 首次转写时会联网下载模型。"
            elif model_downloadable and not self.config.allow_download:
                reason = f"{reason} 当前已禁止自动下载。"
        return {
            "enabled": bool(self.config.enabled),
            "available": available,
            "dependencyAvailable": dependency_available,
            "textNormalizerAvailable": text_normalizer_available,
            "modelReady": model_ready,
            "modelSource": str(model_readiness.get("source") or "unavailable"),
            "modelDownloadRequired": bool(not model_ready and can_prepare_model),
            "model": _public_model_name(self.config.model),
            "language": self.config.language,
            "device": self.config.device,
            "computeType": self.config.compute_type,
            "requestedDevice": self.config.device,
            "requestedComputeType": self.config.compute_type,
            "deviceSource": self.config.device_source,
            "activeDevice": self._active_device or None,
            "activeComputeType": self._active_compute_type or None,
            "modelLoaded": self._model is not None,
            "cuda": cuda,
            "requestedDeviceAvailable": bool(
                self.config.device != VOICE_TRANSCRIPTION_DEVICE_CUDA or cuda["available"]
            ),
            "usingFallback": bool(self._fallback_reason),
            "fallbackReason": fallback_reason,
            "allowDownload": bool(self.config.allow_download),
            "reason": reason,
        }

    def ensure_available(self) -> dict[str, Any]:
        status = self.status()
        if status["available"]:
            return status
        if not status["enabled"]:
            code = "disabled"
        elif not status["dependencyAvailable"] or not status["textNormalizerAvailable"]:
            code = "dependency_missing"
        elif not str(self.config.model or "").strip():
            code = "model_not_configured"
        else:
            code = "model_not_ready"
        raise VoiceTranscriptionError(code, str(status.get("reason") or "本地 Whisper 当前不可用。"))

    def transcribe_voice(
        self,
        *,
        account_dir: Path,
        server_id: int,
        force: bool = False,
        voice_data: Optional[bytes] = None,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            raise VoiceTranscriptionError("disabled", "语音转文字功能未启用。")
        if not str(self.config.model or "").strip():
            raise VoiceTranscriptionError("model_not_configured", "未配置 Whisper 模型。")

        sid = int(server_id or 0)
        if sid <= 0:
            raise VoiceTranscriptionError("invalid_server_id", "语音消息 ID 无效。")

        data = bytes(voice_data) if voice_data is not None else load_voice_data(Path(account_dir), sid)
        if not data:
            raise VoiceTranscriptionError("voice_not_found", "未找到语音数据。")

        source_hash = hashlib.sha256(data).hexdigest()
        if not force:
            cached = self._read_cache(Path(account_dir), sid, source_hash)
            if cached is not None:
                cached["cached"] = True
                return cached

        payload, ext, _media_type = _convert_silk_to_browser_audio(data, preferred_format="wav")
        if not payload or ext == "silk":
            raise VoiceTranscriptionError("voice_decode_failed", "语音解码失败，无法交给 Whisper 识别。")

        temp_path: Optional[Path] = None
        try:
            suffix = ".wav" if ext == "wav" else f".{ext}"
            with tempfile.NamedTemporaryFile(prefix="wechat_voice_", suffix=suffix, delete=False) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)

            with self._inference_lock:
                if not force:
                    cached = self._read_cache(Path(account_dir), sid, source_hash)
                    if cached is not None:
                        cached["cached"] = True
                        return cached
                model = self._get_model()
                try:
                    text, info = self._transcribe_once(model, temp_path)
                except VoiceTranscriptionError:
                    raise
                except Exception as exc:
                    if self._active_device != VOICE_TRANSCRIPTION_DEVICE_CUDA or not _is_cuda_runtime_error(exc):
                        raise VoiceTranscriptionError(
                            "transcription_failed",
                            f"语音识别失败：{type(exc).__name__}",
                        ) from exc

                    model = None
                    self._release_loaded_model()
                    cpu_model = self._load_cpu_fallback("CUDA 推理初始化失败，已自动回退到 CPU。")
                    try:
                        text, info = self._transcribe_once(cpu_model, temp_path)
                    except VoiceTranscriptionError:
                        raise
                    except Exception as retry_exc:
                        raise VoiceTranscriptionError(
                            "transcription_failed",
                            f"CPU 回退识别失败：{type(retry_exc).__name__}",
                        ) from retry_exc

            result = {
                "status": "success",
                "serverId": sid,
                "text": text,
                "language": str(getattr(info, "language", "") or self.config.language),
                "duration": float(getattr(info, "duration", 0.0) or 0.0),
                "model": _public_model_name(self.config.model),
                "device": self._active_device or self.config.device,
                "computeType": self._active_compute_type or self.config.compute_type,
                "cached": False,
            }
            try:
                self._write_cache(Path(account_dir), sid, source_hash, result)
            except Exception:
                pass
            return result
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _transcribe_once(self, model: Any, path: Path) -> tuple[str, Any]:
        segments, info = model.transcribe(
            str(path),
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = _join_transcript_segments(getattr(segment, "text", "") for segment in segments)
        return normalize_transcript_text(text), info

    def _release_loaded_model(self) -> None:
        self._model = None
        self._active_device = ""
        self._active_compute_type = ""
        gc.collect()

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model

            if self.config.device == VOICE_TRANSCRIPTION_DEVICE_CUDA:
                cuda = probe_cuda()
                if not cuda["available"]:
                    return self._load_cpu_fallback(cuda["reason"])
                try:
                    self._model = self._model_loader(self.config)
                    self._active_device = VOICE_TRANSCRIPTION_DEVICE_CUDA
                    self._active_compute_type = self.config.compute_type
                    self._fallback_reason = ""
                    return self._model
                except Exception:
                    return self._load_cpu_fallback("NVIDIA CUDA 初始化失败，已自动回退到 CPU。")

            return self._load_model(self.config)

    def _load_cpu_fallback(self, reason: str) -> Any:
        self._fallback_reason = str(reason or "NVIDIA CUDA 不可用，已自动回退到 CPU。")
        return self._load_model(self.config.cpu_fallback())

    def _load_model(self, config: VoiceTranscriptionConfig) -> Any:
        try:
            self._model = self._model_loader(config)
            self._active_device = config.device
            self._active_compute_type = config.compute_type
            return self._model
        except VoiceTranscriptionError:
            raise
        except ImportError as exc:
            raise VoiceTranscriptionError(
                "dependency_missing",
                "未安装 faster-whisper，请安装语音转文字可选依赖。",
            ) from exc
        except Exception as exc:
            raise VoiceTranscriptionError(
                "model_load_failed",
                f"Whisper 模型加载失败：{type(exc).__name__}",
            ) from exc

    @staticmethod
    def _load_faster_whisper_model(config: VoiceTranscriptionConfig) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise VoiceTranscriptionError(
                "dependency_missing",
                "未安装 faster-whisper，请安装语音转文字可选依赖。",
            ) from exc
        return WhisperModel(
            config.model,
            device=config.device,
            compute_type=config.compute_type,
            local_files_only=not config.allow_download,
        )

    def _cache_path(self, account_dir: Path) -> Path:
        return Path(account_dir) / "_cache" / "voice_transcripts.sqlite3"

    @staticmethod
    def _ensure_cache_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS transcript ("
            "server_id INTEGER NOT NULL, source_hash TEXT NOT NULL, model TEXT NOT NULL, "
            "language TEXT NOT NULL, text TEXT NOT NULL, detected_language TEXT NOT NULL, "
            "duration REAL NOT NULL, updated_at REAL NOT NULL, text_version INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY (server_id, source_hash, model, language))"
        )
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(transcript)")}
        if "text_version" not in columns:
            conn.execute("ALTER TABLE transcript ADD COLUMN text_version INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _normalize_cached_text(raw_text: Any, raw_version: Any) -> tuple[str, bool]:
        text = str(raw_text or "")
        normalized = normalize_transcript_text(text)
        try:
            version = int(raw_version or 0)
        except Exception:
            version = 0
        return normalized, normalized != text or version < TRANSCRIPT_TEXT_VERSION

    def _read_cache(self, account_dir: Path, server_id: int, source_hash: str) -> Optional[dict[str, Any]]:
        path = self._cache_path(account_dir)
        if not path.exists():
            return None
        with self._cache_lock:
            conn: Optional[sqlite3.Connection] = None
            try:
                conn = sqlite3.connect(str(path))
                self._ensure_cache_schema(conn)
                row = conn.execute(
                    "SELECT text, detected_language, duration, text_version FROM transcript "
                    "WHERE server_id = ? AND source_hash = ? AND model = ? AND language = ? LIMIT 1",
                    (int(server_id), source_hash, self.config.model, self.config.language),
                ).fetchone()
                if row:
                    normalized_text, needs_update = self._normalize_cached_text(row[0], row[3])
                    if needs_update:
                        conn.execute(
                            "UPDATE transcript SET text = ?, text_version = ?, updated_at = ? "
                            "WHERE server_id = ? AND source_hash = ? AND model = ? AND language = ?",
                            (
                                normalized_text,
                                TRANSCRIPT_TEXT_VERSION,
                                time.time(),
                                int(server_id),
                                source_hash,
                                self.config.model,
                                self.config.language,
                            ),
                        )
                    conn.commit()
                    row = (normalized_text, row[1], row[2], TRANSCRIPT_TEXT_VERSION)
            except VoiceTranscriptionError:
                raise
            except Exception:
                row = None
            finally:
                if conn is not None:
                    conn.close()
        if not row:
            return None
        return {
            "status": "success",
            "serverId": int(server_id),
            "text": str(row[0] or ""),
            "language": str(row[1] or self.config.language),
            "duration": float(row[2] or 0.0),
            "model": _public_model_name(self.config.model),
            "cached": True,
        }

    def lookup_cached_transcripts(
        self,
        account_dir: Path,
        server_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        """批量读取已缓存的转写结果，并按当前文本版本原位升级。

        不加载模型、不触发识别；旧缓存可能写回简体文本和版本号。
        缓存主键包含 source_hash（音频内容哈希），批量场景下无法预先计算，
        而同一 svr_id 的语音内容唯一，因此按 (server_id, model, language) 匹配最新记录。
        """
        result: dict[int, dict[str, Any]] = {}
        ids: list[int] = []
        seen: set[int] = set()
        for raw in server_ids or []:
            try:
                sid = int(raw)
            except Exception:
                continue
            if sid <= 0 or sid in seen:
                continue
            seen.add(sid)
            ids.append(sid)
        if not ids:
            return result

        path = self._cache_path(Path(account_dir))
        if not path.exists():
            return result

        placeholders = ",".join("?" for _ in ids)
        with self._cache_lock:
            conn: Optional[sqlite3.Connection] = None
            try:
                conn = sqlite3.connect(str(path))
                self._ensure_cache_schema(conn)
                rows = conn.execute(
                    "SELECT server_id, source_hash, text, detected_language, duration, text_version FROM transcript "
                    f"WHERE model = ? AND language = ? AND server_id IN ({placeholders}) "
                    "ORDER BY updated_at DESC",
                    (self.config.model, self.config.language, *ids),
                ).fetchall()
                normalized_rows = []
                for row in rows or []:
                    normalized_text, needs_update = self._normalize_cached_text(row[2], row[5])
                    if needs_update:
                        conn.execute(
                            "UPDATE transcript SET text = ?, text_version = ?, updated_at = ? "
                            "WHERE server_id = ? AND source_hash = ? AND model = ? AND language = ?",
                            (
                                normalized_text,
                                TRANSCRIPT_TEXT_VERSION,
                                time.time(),
                                int(row[0]),
                                str(row[1]),
                                self.config.model,
                                self.config.language,
                            ),
                        )
                    normalized_rows.append((row[0], normalized_text, row[3], row[4]))
                conn.commit()
                rows = normalized_rows
            except VoiceTranscriptionError:
                raise
            except Exception:
                rows = []
            finally:
                if conn is not None:
                    conn.close()

        for row in rows or []:
            sid = int(row[0])
            if sid in result:
                continue
            result[sid] = {
                "status": "success",
                "serverId": sid,
                "text": str(row[1] or ""),
                "language": str(row[2] or self.config.language),
                "duration": float(row[3] or 0.0),
                "model": _public_model_name(self.config.model),
                "cached": True,
            }
        return result

    def _write_cache(self, account_dir: Path, server_id: int, source_hash: str, result: dict[str, Any]) -> None:
        path = self._cache_path(account_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized_text = normalize_transcript_text(result.get("text"))
        result["text"] = normalized_text
        with self._cache_lock:
            conn = sqlite3.connect(str(path))
            try:
                self._ensure_cache_schema(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO transcript "
                    "(server_id, source_hash, model, language, text, detected_language, duration, updated_at, text_version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(server_id),
                        source_hash,
                        self.config.model,
                        self.config.language,
                        normalized_text,
                        str(result.get("language") or self.config.language),
                        float(result.get("duration") or 0.0),
                        time.time(),
                        TRANSCRIPT_TEXT_VERSION,
                    ),
                )
                conn.commit()
            finally:
                conn.close()


_VOICE_TRANSCRIPTION_SERVICE: Optional[VoiceTranscriptionService] = None
_VOICE_TRANSCRIPTION_SERVICE_LOCK = threading.Lock()


def get_voice_transcription_service() -> VoiceTranscriptionService:
    global _VOICE_TRANSCRIPTION_SERVICE
    if _VOICE_TRANSCRIPTION_SERVICE is not None:
        return _VOICE_TRANSCRIPTION_SERVICE
    with _VOICE_TRANSCRIPTION_SERVICE_LOCK:
        if _VOICE_TRANSCRIPTION_SERVICE is None:
            _VOICE_TRANSCRIPTION_SERVICE = VoiceTranscriptionService()
    return _VOICE_TRANSCRIPTION_SERVICE


def set_voice_transcription_device(device: str) -> dict[str, Any]:
    """Persist a user preference and make it effective for subsequent requests."""

    normalized = str(device or "").strip().lower()
    if normalized not in {VOICE_TRANSCRIPTION_DEVICE_CPU, VOICE_TRANSCRIPTION_DEVICE_CUDA}:
        raise VoiceTranscriptionError("invalid_device", "推理设备只支持 CPU 或 NVIDIA GPU。")

    _configured, source = read_effective_voice_transcription_device()
    if source == "env":
        raise VoiceTranscriptionError(
            "device_locked",
            "当前推理设备由 WECHAT_TOOL_WHISPER_DEVICE 环境变量锁定，无法在界面中修改。",
        )

    write_voice_transcription_device_setting(normalized)
    invalidate_cuda_probe_cache()
    global _VOICE_TRANSCRIPTION_SERVICE
    with _VOICE_TRANSCRIPTION_SERVICE_LOCK:
        _VOICE_TRANSCRIPTION_SERVICE = VoiceTranscriptionService()
        return _VOICE_TRANSCRIPTION_SERVICE.status()
