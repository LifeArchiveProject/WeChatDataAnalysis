from __future__ import annotations

import errno
import hashlib
import gc
import importlib.util
import logging
import os
import re
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

import httpx


TRANSCRIPT_TEXT_VERSION = 1
logger = logging.getLogger(__name__)
_OPENCC_CONVERTER: Any = None
_OPENCC_LOOKED_UP = False
_OPENCC_CONVERTER_LOCK = threading.Lock()
_CUDA_PROBE_CACHE_TTL_SECONDS = 5.0
_CUDA_PROBE_CACHE_LOCK = threading.Lock()
_CUDA_PROBE_CACHE: Optional[tuple[float, dict[str, Any]]] = None

from .runtime_settings import (
    VOICE_TRANSCRIPTION_DEVICE_CPU,
    VOICE_TRANSCRIPTION_DEVICE_CUDA,
    read_effective_voice_transcription_device,
    read_effective_voice_transcription_model,
    write_voice_transcription_device_setting,
    write_voice_transcription_model_setting,
)
from .app_paths import get_data_dir, get_output_databases_dir, get_output_dir


VOICE_MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "tiny",
        "name": "Tiny",
        "size": "约 75 MB",
        "speed": "最快",
        "quality": "基础",
        "description": "适合快速预览和低配置设备。",
    },
    {
        "id": "base",
        "name": "Base",
        "size": "约 145 MB",
        "speed": "很快",
        "quality": "入门",
        "description": "速度与基础准确率兼顾。",
    },
    {
        "id": "small",
        "name": "Small",
        "size": "约 466 MB",
        "speed": "较快",
        "quality": "良好",
        "description": "日常中文聊天的轻量选择。",
    },
    {
        "id": "medium",
        "name": "Medium",
        "size": "约 1.5 GB",
        "speed": "中等",
        "quality": "较高",
        "description": "默认推荐，兼顾中文准确率与资源占用。",
        "recommended": True,
    },
    {
        "id": "large-v3",
        "name": "Large v3",
        "size": "约 3.1 GB",
        "speed": "较慢",
        "quality": "最高",
        "description": "追求最高准确率，适合高性能设备。",
    },
    {
        "id": "turbo",
        "name": "Turbo",
        "size": "约 1.6 GB",
        "speed": "快",
        "quality": "很高",
        "description": "Large v3 的高速版本，推荐 NVIDIA GPU。",
    },
)
VOICE_MODEL_IDS = frozenset(str(item["id"]) for item in VOICE_MODEL_CATALOG)
VOICE_MODEL_STORAGE_DIRNAME = "voice_models"
VOICE_MODEL_REPOSITORIES: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
VOICE_MODEL_DOWNLOAD_ALLOW_PATTERNS = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
)
_VOICE_MODEL_PROGRESS_INTERVAL_SECONDS = 0.2
_VOICE_MODEL_HTTP_CHUNK_SIZE = 256 * 1024


def _configure_voice_model_cancellable_hf_http_download() -> None:
    """Force managed downloads through Python HTTP so cancellation can propagate.

    ``huggingface_hub`` exposes no per-request switch for Xet.  Keep this a
    one-way process setting instead of temporarily restoring global constants:
    another thread must never observe Xet being re-enabled during a managed
    download.  This backend only performs Hugging Face network downloads for
    the voice-model manager; local-only cache probes are unaffected.
    """

    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import constants as hf_constants

    hf_constants.HF_HUB_DISABLE_XET = True
    hf_constants.DOWNLOAD_CHUNK_SIZE = _VOICE_MODEL_HTTP_CHUNK_SIZE


def get_voice_model_storage_root() -> Path:
    """Return the application-owned model directory.

    Explicit downloads must not use Hugging Face's process-wide cache: deleting
    a model from this application must never remove snapshots owned by another
    application.
    """

    return get_data_dir() / VOICE_MODEL_STORAGE_DIRNAME


def get_legacy_voice_model_storage_root() -> Path:
    """Return the former output-owned model location for read-only compatibility."""

    return get_output_dir() / VOICE_MODEL_STORAGE_DIRNAME


def _managed_voice_model_dir(model: str) -> Path:
    model_id = str(model or "").strip()
    if model_id not in VOICE_MODEL_IDS:
        raise VoiceTranscriptionError("invalid_model", "不支持该 Whisper 模型。")
    return get_voice_model_storage_root() / model_id


def _legacy_voice_model_dir(model: str) -> Path:
    model_id = str(model or "").strip()
    if model_id not in VOICE_MODEL_IDS:
        raise VoiceTranscriptionError("invalid_model", "不支持该 Whisper 模型。")
    return get_legacy_voice_model_storage_root() / model_id


def _path_is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if os.name == "nt":
            attributes = int(getattr(path.lstat(), "st_file_attributes", 0) or 0)
            return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False
    return False


def _managed_model_path_is_owned(root: Path, target: Path) -> bool:
    """Validate one direct child without following a linked model root/target."""

    try:
        if root.exists() and _path_is_link_or_junction(root):
            return False
        if target.exists() and _path_is_link_or_junction(target):
            return False
        if target.absolute().parent != root.absolute():
            return False
        return target.resolve().parent == root.resolve()
    except OSError:
        return False


_VOICE_MODEL_ACTIVITY_LOCK = threading.Lock()
_VOICE_MODEL_ACTIVITY: dict[str, int] = {}
_VOICE_MODEL_DOWNLOAD_ACTIVITY: dict[str, int] = {}
_VOICE_MODELS_DELETING: set[str] = set()
_VOICE_TRANSCRIPT_CACHE_LOCK = threading.Lock()
_VOICE_TRANSCRIPT_CACHE_EPOCHS: dict[str, int] = {}
_VOICE_TRANSCRIPT_CACHE_GENERATION = 0
_VOICE_TRANSCRIPT_FLIGHT_GUARD = threading.Lock()
_VOICE_TRANSCRIPT_FLIGHTS: dict[tuple[str, int, str, str, str], tuple[threading.Lock, int]] = {}


def _voice_transcript_cache_account_key(account_dir: Path) -> str:
    try:
        value = str(Path(account_dir).resolve(strict=False))
    except OSError:
        value = str(Path(account_dir).absolute())
    return os.path.normcase(value)


def _voice_transcript_cache_path(account_dir: Path) -> Path:
    return Path(account_dir) / "_cache" / "voice_transcripts.sqlite3"


def has_voice_transcript_cache(account_dir: Path, server_id: int) -> bool:
    """Return whether any non-empty project transcript already exists for a voice."""

    path = _voice_transcript_cache_path(Path(account_dir))
    if not path.exists() or int(server_id or 0) <= 0:
        return False
    with _VOICE_TRANSCRIPT_CACHE_LOCK:
        try:
            conn = sqlite3.connect(str(path))
            try:
                row = conn.execute(
                    "SELECT 1 FROM transcript WHERE server_id = ? AND trim(text) <> '' LIMIT 1",
                    (int(server_id),),
                ).fetchone()
                return bool(row)
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            return False


def _capture_voice_transcript_cache_epoch(account_dir: Path) -> int:
    key = _voice_transcript_cache_account_key(account_dir)
    with _VOICE_TRANSCRIPT_CACHE_LOCK:
        return int(_VOICE_TRANSCRIPT_CACHE_EPOCHS.get(key, 0))


def capture_voice_transcript_cache_generation() -> int:
    """Bind a direct, batch, or export operation to the current cache generation."""

    with _VOICE_TRANSCRIPT_CACHE_LOCK:
        return int(_VOICE_TRANSCRIPT_CACHE_GENERATION)


@contextmanager
def _voice_transcript_singleflight(
    key: tuple[str, int, str, str, str],
    cancel_event: Optional[threading.Event],
):
    """Serialize duplicate work for one cached transcript across service generations."""

    with _VOICE_TRANSCRIPT_FLIGHT_GUARD:
        current = _VOICE_TRANSCRIPT_FLIGHTS.get(key)
        lock = current[0] if current is not None else threading.Lock()
        references = int(current[1]) + 1 if current is not None else 1
        _VOICE_TRANSCRIPT_FLIGHTS[key] = (lock, references)
    acquired = False
    try:
        while not acquired:
            if cancel_event is not None and cancel_event.is_set():
                raise _VoiceTranscriptionCancelled()
            acquired = lock.acquire(timeout=0.05 if cancel_event is not None else -1)
        yield
    finally:
        if acquired:
            lock.release()
        with _VOICE_TRANSCRIPT_FLIGHT_GUARD:
            current = _VOICE_TRANSCRIPT_FLIGHTS.get(key)
            if current is not None and current[0] is lock:
                remaining = int(current[1]) - 1
                if remaining > 0:
                    _VOICE_TRANSCRIPT_FLIGHTS[key] = (lock, remaining)
                else:
                    _VOICE_TRANSCRIPT_FLIGHTS.pop(key, None)


def _voice_model_activity_key(model: str) -> str:
    raw = str(model or "").strip()
    return raw if raw in VOICE_MODEL_IDS else _public_model_name(raw)


def acquire_voice_model_activity(model: str) -> str:
    """Claim a model before work starts, atomically against model deletion."""

    key = _voice_model_activity_key(model)
    if not key:
        return ""
    with _VOICE_MODEL_ACTIVITY_LOCK:
        if key in _VOICE_MODELS_DELETING:
            raise VoiceTranscriptionError("model_busy", "该模型正在删除，暂时不能用于语音转写。")
        _VOICE_MODEL_ACTIVITY[key] = int(_VOICE_MODEL_ACTIVITY.get(key) or 0) + 1
    return key


def release_voice_model_activity(activity_key: str) -> None:
    key = str(activity_key or "").strip()
    if not key:
        return
    with _VOICE_MODEL_ACTIVITY_LOCK:
        remaining = int(_VOICE_MODEL_ACTIVITY.get(key) or 0) - 1
        if remaining > 0:
            _VOICE_MODEL_ACTIVITY[key] = remaining
        else:
            _VOICE_MODEL_ACTIVITY.pop(key, None)


def _acquire_voice_model_download_activity(model: str) -> str:
    """Claim the manager-owned download lease separately from model consumers."""

    key = _voice_model_activity_key(model)
    if not key:
        return ""
    with _VOICE_MODEL_ACTIVITY_LOCK:
        if key in _VOICE_MODELS_DELETING:
            raise VoiceTranscriptionError("model_busy", "该模型正在删除，暂时不能下载。")
        _VOICE_MODEL_ACTIVITY[key] = int(_VOICE_MODEL_ACTIVITY.get(key) or 0) + 1
        _VOICE_MODEL_DOWNLOAD_ACTIVITY[key] = int(_VOICE_MODEL_DOWNLOAD_ACTIVITY.get(key) or 0) + 1
    return key


def _release_voice_model_download_activity(activity_key: str) -> None:
    key = str(activity_key or "").strip()
    if not key:
        return
    with _VOICE_MODEL_ACTIVITY_LOCK:
        remaining_downloads = int(_VOICE_MODEL_DOWNLOAD_ACTIVITY.get(key) or 0) - 1
        if remaining_downloads > 0:
            _VOICE_MODEL_DOWNLOAD_ACTIVITY[key] = remaining_downloads
        else:
            _VOICE_MODEL_DOWNLOAD_ACTIVITY.pop(key, None)

        remaining = int(_VOICE_MODEL_ACTIVITY.get(key) or 0) - 1
        if remaining > 0:
            _VOICE_MODEL_ACTIVITY[key] = remaining
        else:
            _VOICE_MODEL_ACTIVITY.pop(key, None)


@contextmanager
def voice_model_activity(model: str):
    activity_key = acquire_voice_model_activity(model)
    try:
        yield
    finally:
        release_voice_model_activity(activity_key)


def _begin_voice_model_deletion(model: str, *, allow_download_activity: bool = False) -> None:
    key = _voice_model_activity_key(model)
    with _VOICE_MODEL_ACTIVITY_LOCK:
        active = int(_VOICE_MODEL_ACTIVITY.get(key) or 0)
        if allow_download_activity:
            active -= int(_VOICE_MODEL_DOWNLOAD_ACTIVITY.get(key) or 0)
        if active > 0 or key in _VOICE_MODELS_DELETING:
            raise VoiceTranscriptionError("model_busy", "该模型正在用于语音转写，暂时不能删除。")
        _VOICE_MODELS_DELETING.add(key)


def _end_voice_model_deletion(model: str) -> None:
    key = _voice_model_activity_key(model)
    with _VOICE_MODEL_ACTIVITY_LOCK:
        _VOICE_MODELS_DELETING.discard(key)


class VoiceTranscriptionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code or "voice_transcription_failed")
        self.user_message = str(message or "Voice transcription failed.")


def _delete_voice_transcript_cache_unlocked(
    account_dir: Path,
    *,
    expected_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Delete one account while the process-wide transcript-cache lock is held."""

    account_path = Path(account_dir)
    account_key = _voice_transcript_cache_account_key(account_path)
    cache_path = _voice_transcript_cache_path(account_path)
    deleted_rows = 0
    deleted_messages = 0
    if expected_root is not None:
        root = Path(expected_root)
        try:
            account_is_owned = (
                not _path_is_link_or_junction(root)
                and not _path_is_link_or_junction(account_path)
                and account_path.absolute().parent == root.absolute()
                and account_path.resolve(strict=True).parent == root.resolve(strict=True)
            )
        except OSError:
            account_is_owned = False
        if not account_is_owned:
            raise VoiceTranscriptionError(
                "unsafe_account_path",
                "账号缓存目录不安全，已拒绝删除。",
            )
    if _path_is_link_or_junction(cache_path.parent) or _path_is_link_or_junction(cache_path):
        raise VoiceTranscriptionError(
            "unsafe_cache_path",
            "语音转写缓存路径不安全，已拒绝删除。",
        )
    # Invalidate every transcription that started before this deletion,
    # including direct/export work that cannot be cancelled by the batch manager.
    _VOICE_TRANSCRIPT_CACHE_EPOCHS[account_key] = int(
        _VOICE_TRANSCRIPT_CACHE_EPOCHS.get(account_key, 0)
    ) + 1
    if cache_path.is_file():
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(cache_path))
            table_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'transcript' LIMIT 1"
            ).fetchone()
            if table_exists:
                row = conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT server_id) FROM transcript"
                ).fetchone()
                deleted_rows = int(row[0] or 0) if row else 0
                deleted_messages = int(row[1] or 0) if row else 0
                conn.execute("DELETE FROM transcript")
                conn.commit()
        except (OSError, sqlite3.Error) as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            raise VoiceTranscriptionError(
                "cache_delete_failed",
                "本项目语音转写记录删除失败，请重试。",
            ) from exc
        finally:
            if conn is not None:
                conn.close()
    return {
        "status": "success",
        "account": account_path.name,
        "deletedRows": deleted_rows,
        "deletedMessages": deleted_messages,
        "nativeDeleted": 0,
    }


def delete_voice_transcript_cache(account_dir: Path) -> dict[str, Any]:
    """Delete only project-generated transcript rows for one resolved account."""

    with _VOICE_TRANSCRIPT_CACHE_LOCK:
        return _delete_voice_transcript_cache_unlocked(account_dir)


def _enumerate_voice_transcript_account_dirs() -> tuple[list[Path], list[dict[str, str]]]:
    """Return safe direct children of the application-owned account database root."""

    root = get_output_databases_dir()
    if _path_is_link_or_junction(root):
        raise VoiceTranscriptionError(
            "unsafe_cache_root",
            "账号数据目录是链接或重解析路径，已拒绝全局删除。",
        )
    if not root.exists():
        return [], []
    if not root.is_dir():
        raise VoiceTranscriptionError("unsafe_cache_root", "账号数据目录无效，已拒绝全局删除。")
    try:
        root_absolute = root.absolute()
        root_resolved = root.resolve(strict=True)
        entries = list(root.iterdir())
    except OSError as exc:
        raise VoiceTranscriptionError(
            "cache_scan_failed",
            "无法扫描账号语音转写记录，请重试。",
        ) from exc

    account_dirs: list[Path] = []
    seen_paths: set[str] = set()
    skipped: list[dict[str, str]] = []
    for entry in sorted(entries, key=lambda value: value.name.lower()):
        account_name = str(entry.name or "").strip()
        if (
            not account_name
            or account_name in {".", ".."}
            or any(char in account_name for char in ("/", "\\", ":", "\x00"))
        ):
            continue
        try:
            unsafe = _path_is_link_or_junction(entry)
        except OSError:
            unsafe = True
        if unsafe:
            skipped.append({"account": account_name, "code": "unsafe_account_path"})
            continue
        try:
            if not entry.is_dir():
                continue
            resolved_entry = entry.resolve(strict=True)
            contained = (
                entry.absolute().parent == root_absolute
                and resolved_entry.parent == root_resolved
            )
        except OSError:
            contained = False
        if not contained:
            skipped.append({"account": account_name, "code": "unsafe_account_path"})
            continue
        identity = os.path.normcase(str(resolved_entry))
        if identity in seen_paths:
            continue
        seen_paths.add(identity)
        account_dirs.append(entry)
    return account_dirs, skipped


def _delete_all_voice_transcript_caches_with_accounts() -> tuple[dict[str, Any], list[str]]:
    global _VOICE_TRANSCRIPT_CACHE_GENERATION

    deleted_rows = 0
    deleted_messages = 0
    accounts_changed = 0
    successful_accounts: list[str] = []
    with _VOICE_TRANSCRIPT_CACHE_LOCK:
        # Holding this lock for the complete sweep makes direct/export starts wait;
        # older in-flight work observes an incremented per-account epoch on write.
        account_dirs, failures = _enumerate_voice_transcript_account_dirs()
        accounts_scanned = len(account_dirs) + len(failures)
        account_root = get_output_databases_dir()
        _VOICE_TRANSCRIPT_CACHE_GENERATION += 1
        for account_dir in account_dirs:
            try:
                item = _delete_voice_transcript_cache_unlocked(
                    account_dir,
                    expected_root=account_root,
                )
            except VoiceTranscriptionError as exc:
                failures.append({"account": account_dir.name, "code": exc.code})
                continue
            rows = int(item.get("deletedRows") or 0)
            messages = int(item.get("deletedMessages") or 0)
            deleted_rows += rows
            deleted_messages += messages
            accounts_changed += int(rows > 0)
            successful_accounts.append(account_dir.name)

    result = {
        "status": "partial" if failures else "success",
        "deletedRows": deleted_rows,
        "deletedMessages": deleted_messages,
        "accountsScanned": accounts_scanned,
        "accountsChanged": accounts_changed,
        "nativeDeleted": 0,
    }
    if failures:
        result["failures"] = failures
    return result, successful_accounts


def delete_all_voice_transcript_caches() -> dict[str, Any]:
    """Delete project-generated transcripts across every safe application account."""

    result, _successful_accounts = _delete_all_voice_transcript_caches_with_accounts()
    return result


class _VoiceTranscriptionCancelled(RuntimeError):
    """Internal cooperative cancellation used by bounded batch workers."""


@dataclass(frozen=True)
class VoiceTranscriptionConfig:
    enabled: bool = True
    model: str = "medium"
    language: str = "zh"
    device: str = "cpu"
    compute_type: str = "int8"
    device_source: str = "default"
    model_source: str = "default"
    allow_download: bool = False
    beam_size: int = 5
    num_workers: int = 1

    @classmethod
    def from_env(cls) -> "VoiceTranscriptionConfig":
        enabled = _env_bool("WECHAT_TOOL_WHISPER_ENABLED", True)
        model, model_source = read_effective_voice_transcription_model()
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
            model_source=model_source,
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


def _managed_voice_model_stage_dirs(model: str) -> list[Path]:
    model_id = str(model or "").strip()
    if model_id not in VOICE_MODEL_IDS:
        return []
    root = get_voice_model_storage_root()
    try:
        if not root.is_dir() or _path_is_link_or_junction(root):
            return []
        return [
            path
            for path in root.glob(f".{model_id}.download-*")
            if path.is_dir() or _path_is_link_or_junction(path)
        ]
    except OSError:
        return []


def inspect_model_readiness(model: str) -> dict[str, Any]:
    """Inspect a local directory or Hugging Face cache without loading or downloading a model."""

    raw = str(model or "").strip()
    if not raw:
        return {
            "ready": False,
            "downloadable": False,
            "managed": False,
            "deletable": False,
            "source": "unavailable",
            "reason": "未配置 Whisper 模型。",
        }

    if _looks_like_local_model_path(raw):
        model_dir = Path(os.path.expandvars(os.path.expanduser(raw)))
        if _model_directory_is_ready(model_dir):
            return {
                "ready": True,
                "downloadable": False,
                "managed": False,
                "deletable": False,
                "source": "local-directory",
                "reason": "",
            }
        return {
            "ready": False,
            "downloadable": False,
            "managed": False,
            "deletable": False,
            "source": "local-directory",
            "reason": "配置的本地 Whisper 模型目录不存在或文件不完整。",
        }

    managed_dir: Optional[Path] = None
    managed_partial = False
    if raw in VOICE_MODEL_IDS:
        managed_dir = _managed_voice_model_dir(raw)
        managed_root = get_voice_model_storage_root()
        managed_owned = _managed_model_path_is_owned(managed_root, managed_dir)
        if managed_owned and _model_directory_is_ready(managed_dir):
            return {
                "ready": True,
                "downloadable": True,
                "managed": True,
                "deletable": True,
                "source": "app-cache",
                "reason": "",
            }
        managed_partial = bool(
            managed_owned
            and (
                managed_dir.exists()
                or _managed_voice_model_stage_dirs(raw)
            )
        )
        if managed_dir.exists() and not managed_owned:
            return {
                "ready": False,
                "downloadable": False,
                "managed": False,
                "deletable": False,
                "source": "unavailable",
                "reason": "应用模型目录是符号链接或目录联接，已拒绝使用。",
            }

        legacy_dir = _legacy_voice_model_dir(raw)
        try:
            same_location = legacy_dir.resolve() == managed_dir.resolve()
        except OSError:
            same_location = legacy_dir.absolute() == managed_dir.absolute()
        if not same_location and _model_directory_is_ready(legacy_dir):
            return {
                "ready": True,
                "downloadable": True,
                "managed": managed_partial,
                "deletable": managed_partial,
                "source": "legacy-output-cache",
                "reason": "检测到旧 output 目录中的模型；可继续使用，但本应用不会在此处删除它。",
            }

    try:
        from faster_whisper.utils import download_model
    except Exception:
        if managed_partial:
            return {
                "ready": False,
                "downloadable": True,
                "managed": True,
                "deletable": True,
                "source": "app-cache",
                "reason": "应用模型下载未完成，可删除后重新下载。",
            }
        return {
            "ready": False,
            "downloadable": True,
            "managed": False,
            "deletable": False,
            "source": "huggingface-cache",
            "reason": "未安装 faster-whisper，无法检查模型缓存。",
        }

    try:
        cached_dir = Path(download_model(raw, local_files_only=True))
    except ValueError:
        return {
            "ready": False,
            "downloadable": False,
            "managed": False,
            "deletable": False,
            "source": "unavailable",
            "reason": "Whisper 模型名称无效。",
        }
    except Exception:
        if managed_partial:
            return {
                "ready": False,
                "downloadable": True,
                "managed": True,
                "deletable": True,
                "source": "app-cache",
                "reason": "应用模型下载未完成，可删除后重新下载。",
            }
        return {
            "ready": False,
            "downloadable": True,
            "managed": False,
            "deletable": False,
            "source": "app-cache" if managed_dir is not None else "huggingface-cache",
            "reason": "Whisper 模型尚未下载到本机缓存。",
        }

    if _model_directory_is_ready(cached_dir):
        return {
            "ready": True,
            "downloadable": True,
            "managed": managed_partial,
            "deletable": managed_partial,
            "source": "external-cache",
            "reason": (
                "共享缓存可用；应用目录另有未完成下载，可单独清理。"
                if managed_partial
                else "该模型来自共享缓存，本应用不会删除它。" if managed_dir is not None else ""
            ),
        }
    if managed_partial:
        return {
            "ready": False,
            "downloadable": True,
            "managed": True,
            "deletable": True,
            "source": "app-cache",
            "reason": "应用模型下载未完成，可删除后重新下载。",
        }
    return {
        "ready": False,
        "downloadable": True,
        "managed": False,
        "deletable": False,
        "source": "app-cache" if managed_dir is not None else "huggingface-cache",
        "reason": "本机 Whisper 模型缓存文件不完整。",
    }


def get_voice_model_catalog(*, selected_model: Optional[str] = None) -> list[dict[str, Any]]:
    """Return the curated multilingual model list with current cache state."""

    selected = str(selected_model or VoiceTranscriptionConfig.from_env().model or "medium").strip()
    jobs: dict[str, dict[str, Any]] = {}
    manager = globals().get("VOICE_MODEL_DOWNLOAD_MANAGER")
    if manager is not None:
        try:
            jobs = manager.latest_by_model()
        except Exception:
            jobs = {}

    result: list[dict[str, Any]] = []
    for definition in VOICE_MODEL_CATALOG:
        model_id = str(definition["id"])
        readiness = inspect_model_readiness(model_id)
        job = jobs.get(model_id) or {}
        item = dict(definition)
        item.update(
            {
                "selected": model_id == selected,
                "downloaded": bool(readiness.get("ready")),
                "downloadable": bool(readiness.get("downloadable")),
                "managed": bool(readiness.get("managed")),
                "deletable": bool(readiness.get("deletable")),
                "source": str(readiness.get("source") or "unavailable"),
                "reason": str(readiness.get("reason") or ""),
                "downloadStatus": str(job.get("status") or "idle"),
                "downloadError": str(job.get("error") or ""),
                "downloadJobId": str(job.get("jobId") or ""),
                "downloadPercent": max(0, min(100, int(job.get("percent") or 0))),
                "downloadedBytes": max(0, int(job.get("downloadedBytes") or 0)),
                "totalBytes": max(0, int(job.get("totalBytes") or 0)),
                "downloadStage": str(job.get("stage") or "idle"),
            }
        )
        result.append(item)
    return result


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
    with _OPENCC_CONVERTER_LOCK:
        if not _OPENCC_LOOKED_UP:
            converter: Any = None
            try:
                from opencc import OpenCC

                converter = OpenCC("t2s")
                converter.convert("測試")
            except Exception:
                converter = None
            _OPENCC_CONVERTER = converter
            _OPENCC_LOOKED_UP = True
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


def _numbered_db_shards(root: Path, prefix: str) -> list[Path]:
    pattern = re.compile(rf"^{re.escape(prefix)}_[0-9]+\.db$", re.IGNORECASE)
    return [
        path
        for path in sorted(Path(root).glob(f"{prefix}_*.db"))
        if path.is_file() and pattern.fullmatch(path.name)
    ]


def _convert_silk_to_browser_audio(data: bytes, *, preferred_format: str) -> tuple[bytes, str, str]:
    from .media_helpers import _convert_silk_to_browser_audio as convert

    return convert(data, preferred_format=preferred_format)


def load_voice_data(account_dir: Path, server_id: int) -> bytes:
    account_path = Path(account_dir)
    sid = int(server_id or 0)
    if sid <= 0:
        return b""

    best_local: tuple[int, bytes] = (-1, b"")
    for media_db_path in _numbered_db_shards(account_path, "media"):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(media_db_path))
            row = conn.execute(
                "SELECT voice_data, create_time FROM VoiceInfo WHERE svr_id = ? ORDER BY create_time DESC LIMIT 1",
                (sid,),
            ).fetchone()
            if row:
                data = _coerce_blob(row[0])
                create_time = int(row[1] or 0)
                if data and create_time >= best_local[0]:
                    best_local = (create_time, data)
        except Exception:
            pass
        finally:
            if conn is not None:
                conn.close()
    if best_local[1]:
        return best_local[1]

    from .account_source_policy import account_prefers_decrypted_snapshot

    if account_prefers_decrypted_snapshot(account_path):
        return b""

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


def _list_realtime_voice_server_ids(
    account_dir: Path,
    *,
    cancel_event: Optional[threading.Event] = None,
    errors: Optional[list[str]] = None,
) -> list[int]:
    ids: set[int] = set()
    try:
        from .wcdb_realtime import WCDB_REALTIME, exec_query as _wcdb_exec_query

        realtime = WCDB_REALTIME.ensure_connected(Path(account_dir))
        media_dir = Path(realtime.db_storage_dir) / "message"
        for realtime_db_path in _numbered_db_shards(media_dir, "media"):
            if cancel_event is not None and cancel_event.is_set():
                break
            try:
                with realtime.lock:
                    rows = _wcdb_exec_query(
                        realtime.handle,
                        kind="message",
                        path=str(realtime_db_path),
                        sql="SELECT svr_id FROM VoiceInfo WHERE svr_id > 0",
                    )
            except Exception as exc:
                rows = []
                if errors is not None:
                    errors.append(f"{realtime_db_path.name}: {type(exc).__name__}")
            for row in rows or []:
                try:
                    sid = int(row.get("svr_id") or 0)
                except Exception:
                    continue
                if sid > 0:
                    ids.add(sid)
    except Exception as exc:
        if errors is not None:
            errors.append(f"realtime media: {type(exc).__name__}")
    return sorted(ids)


def list_voice_server_ids(
    account_dir: Path,
    *,
    cancel_event: Optional[threading.Event] = None,
    errors: Optional[list[str]] = None,
) -> list[int]:
    """List unique voice message IDs from every local and realtime media shard."""

    account_path = Path(account_dir)
    ids: set[int] = set()
    local_errors: list[str] = []
    local_successes = 0
    local_paths = _numbered_db_shards(account_path, "media")
    for media_db_path in local_paths:
        if cancel_event is not None and cancel_event.is_set():
            break
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(media_db_path))
            for row in conn.execute("SELECT svr_id FROM VoiceInfo WHERE svr_id > 0"):
                sid = int(row[0] or 0)
                if sid > 0:
                    ids.add(sid)
            local_successes += 1
        except Exception as exc:
            local_errors.append(f"{media_db_path.name}: {type(exc).__name__}")
        finally:
            if conn is not None:
                conn.close()
    realtime_errors: list[str] = []
    from .account_source_policy import account_prefers_decrypted_snapshot

    if not account_prefers_decrypted_snapshot(account_path):
        ids.update(
            _list_realtime_voice_server_ids(
                account_path,
                cancel_event=cancel_event,
                errors=realtime_errors,
            )
        )
    if errors is not None:
        errors.extend(local_errors)
        if local_successes == 0:
            errors.extend(realtime_errors)
    return sorted(ids)

def list_native_voice_transcripts(
    account_dir: Path,
    *,
    cancel_event: Optional[threading.Event] = None,
    errors: Optional[list[str]] = None,
    voice_server_ids: Optional[set[int]] = None,
    target_server_id: Optional[int] = None,
) -> dict[int, str]:
    """Read completed WeChat-native transcripts keyed by server ID."""

    from .chat_helpers import _extract_voice_transcript_from_packed_info

    result: dict[int, str] = {}
    account_path = Path(account_dir)
    target_id = int(target_server_id or 0)
    local_errors: list[str] = []
    local_successes = 0
    for db_path in _numbered_db_shards(account_path, "message"):
        if cancel_event is not None and cancel_event.is_set():
            break
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(str(db_path))
            tables = [
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                )
            ]
            for table in tables:
                if cancel_event is not None and cancel_event.is_set():
                    break
                quoted = '"' + table.replace('"', '""') + '"'
                try:
                    target_where = " AND server_id = ?" if target_id > 0 else ""
                    target_params = (target_id,) if target_id > 0 else ()
                    try:
                        rows = conn.execute(
                            f"SELECT server_id, packed_info_data FROM {quoted} "
                            "WHERE local_type = 34 AND server_id > 0"
                            + target_where,
                            target_params,
                        )
                    except sqlite3.OperationalError:
                        rows = conn.execute(
                            f"SELECT server_id, NULL AS packed_info_data FROM {quoted} "
                            "WHERE local_type = 34 AND server_id > 0"
                            + target_where,
                            target_params,
                        )
                    for server_id, packed_info in rows:
                        sid = int(server_id or 0)
                        if sid <= 0:
                            continue
                        if voice_server_ids is not None:
                            voice_server_ids.add(sid)
                        if sid in result or packed_info is None:
                            continue
                        text = _extract_voice_transcript_from_packed_info(packed_info)
                        if text:
                            result[sid] = text
                except Exception as exc:
                    local_errors.append(f"{db_path.name}/{table}: {type(exc).__name__}")
                    continue
            local_successes += 1
        except Exception as exc:
            local_errors.append(f"{db_path.name}: {type(exc).__name__}")
        finally:
            if conn is not None:
                conn.close()
    if target_id > 0 and target_id in result:
        return result
    realtime_errors: list[str] = []
    from .account_source_policy import account_prefers_decrypted_snapshot

    if not account_prefers_decrypted_snapshot(account_path):
        for server_id, text in _list_realtime_native_voice_transcripts(
            account_path,
            cancel_event=cancel_event,
            errors=realtime_errors,
            voice_server_ids=voice_server_ids,
            target_server_id=target_id if target_id > 0 else None,
        ).items():
            result.setdefault(server_id, text)
    if errors is not None:
        errors.extend(local_errors)
        if local_successes == 0:
            errors.extend(realtime_errors)
    return result


def _list_realtime_native_voice_transcripts(
    account_dir: Path,
    *,
    cancel_event: Optional[threading.Event] = None,
    errors: Optional[list[str]] = None,
    voice_server_ids: Optional[set[int]] = None,
    target_server_id: Optional[int] = None,
) -> dict[int, str]:
    """Best-effort native transcript lookup for direct/realtime WCDB mode."""

    from .chat_helpers import _extract_voice_transcript_from_packed_info

    result: dict[int, str] = {}
    target_id = int(target_server_id or 0)
    try:
        from .wcdb_realtime import WCDB_REALTIME, exec_query as _wcdb_exec_query

        realtime = WCDB_REALTIME.ensure_connected(Path(account_dir))
        message_dir = Path(realtime.db_storage_dir) / "message"
        for db_path in _numbered_db_shards(message_dir, "message"):
            if cancel_event is not None and cancel_event.is_set():
                break
            try:
                with realtime.lock:
                    table_rows = _wcdb_exec_query(
                        realtime.handle,
                        kind="message",
                        path=str(db_path),
                        sql="SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'",
                    )
            except Exception as exc:
                if errors is not None:
                    errors.append(f"{db_path.name}: {type(exc).__name__}")
                continue
            for table_row in table_rows or []:
                if cancel_event is not None and cancel_event.is_set():
                    break
                if not isinstance(table_row, dict):
                    continue
                table = str(
                    next(
                        (value for key, value in table_row.items() if str(key).lower() == "name"),
                        "",
                    )
                    or ""
                ).strip()
                if not table.lower().startswith("msg_"):
                    continue
                quoted = '"' + table.replace('"', '""') + '"'
                try:
                    with realtime.lock:
                        try:
                            target_where = f" AND server_id = {target_id}" if target_id > 0 else ""
                            rows = _wcdb_exec_query(
                                realtime.handle,
                                kind="message",
                                path=str(db_path),
                                sql=(
                                    f"SELECT server_id, packed_info_data FROM {quoted} "
                                    "WHERE local_type = 34 AND server_id > 0"
                                    + target_where
                                ),
                            )
                        except Exception:
                            rows = _wcdb_exec_query(
                                realtime.handle,
                                kind="message",
                                path=str(db_path),
                                sql=(
                                    f"SELECT server_id, NULL AS packed_info_data FROM {quoted} "
                                    "WHERE local_type = 34 AND server_id > 0"
                                    + target_where
                                ),
                            )
                except Exception as exc:
                    if errors is not None:
                        errors.append(f"{db_path.name}/{table}: {type(exc).__name__}")
                    continue
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    values = {str(key).lower(): value for key, value in row.items()}
                    try:
                        server_id = int(values.get("server_id") or 0)
                    except Exception:
                        continue
                    if server_id <= 0 or server_id in result:
                        continue
                    if voice_server_ids is not None:
                        voice_server_ids.add(server_id)
                    if values.get("packed_info_data") is None:
                        continue
                    text = _extract_voice_transcript_from_packed_info(values.get("packed_info_data"))
                    if text:
                        result[server_id] = text
    except Exception as exc:
        if errors is not None:
            errors.append(f"realtime message: {type(exc).__name__}")
    return result


def lookup_native_voice_transcript(
    account_dir: Path,
    server_id: int,
    *,
    errors: Optional[list[str]] = None,
) -> str:
    """Read one completed WeChat-native transcript without triggering recognition."""

    target_id = int(server_id or 0)
    if target_id <= 0:
        return ""
    return str(
        list_native_voice_transcripts(
            account_dir,
            errors=errors,
            target_server_id=target_id,
        ).get(target_id)
        or ""
    ).strip()


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
        self._cuda_fallback_pending = False
        self._model_lock = threading.Lock()
        self._inference_condition = threading.Condition(threading.Lock())
        self._active_inferences = 0
        self._model_transitioning = False
        self._model_generation = 0
        self._model_num_workers = max(1, int(self.config.num_workers or 1))
        self._retired = False
        # Service replacement can overlap with a completed inference writing its
        # cache, so all service generations must serialize the SQLite file.
        self._cache_lock = _VOICE_TRANSCRIPT_CACHE_LOCK
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
            "modelSettingSource": self.config.model_source,
            "models": get_voice_model_catalog(selected_model=self.config.model),
            "language": self.config.language,
            "device": self.config.device,
            "computeType": self.config.compute_type,
            "requestedDevice": self.config.device,
            "requestedComputeType": self.config.compute_type,
            "deviceSource": self.config.device_source,
            "activeDevice": self._active_device or None,
            "activeComputeType": self._active_compute_type or None,
            "modelLoaded": self._model is not None,
            "numWorkers": self._model_num_workers,
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
        self._raise_if_retired()
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
        cancel_event: Optional[threading.Event] = None,
        cache_generation: Optional[int] = None,
    ) -> dict[str, Any]:
        self._raise_if_retired()
        with voice_model_activity(self.config.model):
            self._raise_if_retired()
            return self._transcribe_voice_impl(
                account_dir=account_dir,
                server_id=server_id,
                force=force,
                voice_data=voice_data,
                cancel_event=cancel_event,
                cache_generation=cache_generation,
            )

    def _transcribe_voice_impl(
        self,
        *,
        account_dir: Path,
        server_id: int,
        force: bool = False,
        voice_data: Optional[bytes] = None,
        cancel_event: Optional[threading.Event] = None,
        cache_generation: Optional[int] = None,
    ) -> dict[str, Any]:
        self._raise_if_cancelled(cancel_event)
        account_path = Path(account_dir)
        operation_generation = (
            capture_voice_transcript_cache_generation()
            if cache_generation is None
            else int(cache_generation)
        )
        cache_epoch = _capture_voice_transcript_cache_epoch(account_path)
        if not self.config.enabled:
            raise VoiceTranscriptionError("disabled", "语音转文字功能未启用。")
        if not str(self.config.model or "").strip():
            raise VoiceTranscriptionError("model_not_configured", "未配置 Whisper 模型。")

        sid = int(server_id or 0)
        if sid <= 0:
            raise VoiceTranscriptionError("invalid_server_id", "语音消息 ID 无效。")

        data = bytes(voice_data) if voice_data is not None else load_voice_data(account_path, sid)
        if not data:
            raise VoiceTranscriptionError("voice_not_found", "未找到语音数据。")

        source_hash = hashlib.sha256(data).hexdigest()
        if not force:
            cached = self._read_cache(account_path, sid, source_hash)
            if cached is not None:
                cached["cached"] = True
                return cached

        flight_key = (
            str(account_path.absolute()),
            sid,
            source_hash,
            str(self.config.model),
            str(self.config.language),
        )
        with _voice_transcript_singleflight(flight_key, cancel_event):
            if not force:
                cached = self._read_cache(account_path, sid, source_hash)
                if cached is not None:
                    cached["cached"] = True
                    return cached
            self._raise_if_cancelled(cancel_event)
            payload, ext, _media_type = _convert_silk_to_browser_audio(data, preferred_format="wav")
            if not payload or ext == "silk":
                raise VoiceTranscriptionError("voice_decode_failed", "语音解码失败，无法交给 Whisper 识别。")

            temp_path: Optional[Path] = None
            try:
                suffix = ".wav" if ext == "wav" else f".{ext}"
                with tempfile.NamedTemporaryFile(prefix="wechat_voice_", suffix=suffix, delete=False) as temp_file:
                    temp_file.write(payload)
                    temp_path = Path(temp_file.name)

                text, info, result_device, result_compute_type = self._transcribe_with_fallback(
                    temp_path,
                    cancel_event=cancel_event,
                )
                result = {
                    "status": "success",
                    "serverId": sid,
                    "text": text,
                    "language": str(getattr(info, "language", "") or self.config.language),
                    "duration": float(getattr(info, "duration", 0.0) or 0.0),
                    "model": _public_model_name(self.config.model),
                    "device": result_device,
                    "computeType": result_compute_type,
                    "cached": False,
                }
                try:
                    self._write_cache(
                        account_path,
                        sid,
                        source_hash,
                        result,
                        expected_epoch=cache_epoch,
                        expected_generation=operation_generation,
                    )
                except Exception:
                    pass
                return result
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

    @staticmethod
    def _raise_if_cancelled(cancel_event: Optional[threading.Event]) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _VoiceTranscriptionCancelled()

    def _raise_if_retired(self) -> None:
        with self._inference_condition:
            if self._retired:
                raise VoiceTranscriptionError("service_retired", "语音识别配置已更新，请重试。")

    def configure_inference_concurrency(
        self,
        concurrency: int,
        *,
        cancel_event: Optional[threading.Event] = None,
    ) -> int:
        """Reload the model at a quiescent point with matching CTranslate2 workers."""

        workers = max(1, int(concurrency or 1))
        with self._inference_condition:
            while self._model_transitioning and not self._retired:
                self._raise_if_cancelled(cancel_event)
                self._inference_condition.wait(timeout=0.05 if cancel_event is not None else None)
            self._raise_if_cancelled(cancel_event)
            if self._retired:
                raise VoiceTranscriptionError("service_retired", "语音识别配置已更新，请重试。")
            if workers == self._model_num_workers:
                return workers
            self._model_transitioning = True
            while self._active_inferences > 0:
                if cancel_event is not None and cancel_event.is_set():
                    self._model_transitioning = False
                    self._inference_condition.notify_all()
                    raise _VoiceTranscriptionCancelled()
                self._inference_condition.wait(timeout=0.05 if cancel_event is not None else None)

        try:
            self._release_loaded_model_unlocked()
            self._model_num_workers = workers
        finally:
            with self._inference_condition:
                self._model_generation += 1
                self._model_transitioning = False
                self._inference_condition.notify_all()
        return workers

    def retire(self) -> None:
        """Prevent an replaced service from reloading a model after reset."""

        with self._inference_condition:
            while self._model_transitioning and not self._retired:
                self._inference_condition.wait()
            if self._retired:
                return
            self._retired = True
            self._model_transitioning = True
            while self._active_inferences > 0:
                self._inference_condition.wait()
        try:
            self._release_loaded_model_unlocked()
        finally:
            with self._inference_condition:
                self._model_generation += 1
                self._model_transitioning = False
                self._inference_condition.notify_all()

    def _acquire_inference_model(
        self,
        cancel_event: Optional[threading.Event],
    ) -> tuple[Any, int, str, str]:
        while True:
            should_load = False
            with self._inference_condition:
                while True:
                    self._raise_if_cancelled(cancel_event)
                    if self._retired:
                        raise VoiceTranscriptionError("service_retired", "语音识别配置已更新，请重试。")
                    if not self._model_transitioning and self._active_inferences < self._model_num_workers:
                        if self._model is None:
                            self._model_transitioning = True
                            should_load = True
                            break
                        self._active_inferences += 1
                        return (
                            self._model,
                            self._model_generation,
                            self._active_device or self.config.device,
                            self._active_compute_type or self.config.compute_type,
                        )
                    self._inference_condition.wait(timeout=0.05 if cancel_event is not None else None)

            if not should_load:
                continue
            try:
                self._get_model()
            finally:
                with self._inference_condition:
                    self._model_generation += 1
                    self._model_transitioning = False
                    self._inference_condition.notify_all()

    def _release_inference_model(self) -> None:
        with self._inference_condition:
            self._active_inferences = max(0, self._active_inferences - 1)
            self._inference_condition.notify_all()

    def _transcribe_with_fallback(
        self,
        path: Path,
        *,
        cancel_event: Optional[threading.Event],
    ) -> tuple[str, Any, str, str]:
        model, generation, device, compute_type = self._acquire_inference_model(cancel_event)
        inference_error_type = ""
        cuda_fallback_required = False
        try:
            try:
                text, info = self._transcribe_once(model, path, cancel_event=cancel_event)
            except _VoiceTranscriptionCancelled as exc:
                try:
                    exc.__traceback__ = None
                except Exception:
                    pass
                model = None
                raise
            except VoiceTranscriptionError as exc:
                try:
                    exc.__traceback__ = None
                except Exception:
                    pass
                model = None
                raise
            except Exception as exc:
                inference_error_type = type(exc).__name__
                if device == VOICE_TRANSCRIPTION_DEVICE_CUDA and _is_cuda_runtime_error(exc):
                    cuda_fallback_required = True
                    with self._inference_condition:
                        self._cuda_fallback_pending = True
                        self._fallback_reason = "CUDA 推理初始化失败，已自动回退到 CPU。"
                    try:
                        exc.__traceback__ = None
                    except Exception:
                        pass
                    model = None
                else:
                    try:
                        exc.__traceback__ = None
                    except Exception:
                        pass
                    model = None
        finally:
            model = None
            self._release_inference_model()

        if not cuda_fallback_required and not inference_error_type:
            return text, info, device, compute_type
        if not cuda_fallback_required:
            raise VoiceTranscriptionError(
                "transcription_failed",
                f"语音识别失败：{inference_error_type}",
            )

        self._raise_if_cancelled(cancel_event)
        self._transition_cuda_to_cpu_fallback(
            generation,
            "CUDA 推理初始化失败，已自动回退到 CPU。",
        )
        self._raise_if_cancelled(cancel_event)

        cpu_model, _generation, cpu_device, cpu_compute_type = self._acquire_inference_model(cancel_event)
        try:
            try:
                text, info = self._transcribe_once(cpu_model, path, cancel_event=cancel_event)
            except _VoiceTranscriptionCancelled:
                raise
            except VoiceTranscriptionError:
                raise
            except Exception as retry_exc:
                retry_error_type = type(retry_exc).__name__
                try:
                    retry_exc.__traceback__ = None
                except Exception:
                    pass
                cpu_model = None
                raise VoiceTranscriptionError(
                    "transcription_failed",
                    f"CPU 回退识别失败：{retry_error_type}",
                )
        finally:
            cpu_model = None
            self._release_inference_model()
        return text, info, cpu_device, cpu_compute_type

    def _transition_cuda_to_cpu_fallback(self, _expected_generation: int, reason: str) -> None:
        with self._inference_condition:
            while self._model_transitioning and not self._retired:
                self._inference_condition.wait()
            if self._retired:
                raise VoiceTranscriptionError("service_retired", "语音识别配置已更新，请重试。")
            if (
                self._active_device == VOICE_TRANSCRIPTION_DEVICE_CPU
                and self._model is not None
            ):
                return
            self._model_transitioning = True
            while self._active_inferences > 0:
                self._inference_condition.wait()

        try:
            self._release_loaded_model_unlocked()
            self._load_cpu_fallback(reason)
        finally:
            with self._inference_condition:
                self._model_generation += 1
                self._model_transitioning = False
                self._inference_condition.notify_all()

    def _transcribe_once(
        self,
        model: Any,
        path: Path,
        *,
        cancel_event: Optional[threading.Event] = None,
    ) -> tuple[str, Any]:
        self._raise_if_cancelled(cancel_event)
        segments, info = model.transcribe(
            str(path),
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        values: list[str] = []
        try:
            for segment in segments:
                self._raise_if_cancelled(cancel_event)
                values.append(str(getattr(segment, "text", "") or ""))
        finally:
            if cancel_event is not None and cancel_event.is_set():
                close = getattr(segments, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
        text = _join_transcript_segments(values)
        return normalize_transcript_text(text), info

    def _release_loaded_model_unlocked(self) -> None:
        self._model = None
        self._active_device = ""
        self._active_compute_type = ""
        gc.collect()

    def _release_loaded_model(self) -> None:
        """Release only after all leases drain; kept for internal reset callers."""

        with self._inference_condition:
            while self._model_transitioning and not self._retired:
                self._inference_condition.wait()
            if self._retired:
                return
            self._model_transitioning = True
            while self._active_inferences > 0:
                self._inference_condition.wait()
        try:
            self._release_loaded_model_unlocked()
        finally:
            with self._inference_condition:
                self._model_generation += 1
                self._model_transitioning = False
                self._inference_condition.notify_all()

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model

            runtime_config = replace(self.config, num_workers=self._model_num_workers)
            if runtime_config.device == VOICE_TRANSCRIPTION_DEVICE_CUDA:
                if self._cuda_fallback_pending:
                    return self._load_cpu_fallback(self._fallback_reason)
                cuda = probe_cuda()
                if not cuda["available"]:
                    return self._load_cpu_fallback(cuda["reason"])
                try:
                    self._model = self._model_loader(runtime_config)
                    self._active_device = VOICE_TRANSCRIPTION_DEVICE_CUDA
                    self._active_compute_type = runtime_config.compute_type
                    self._fallback_reason = ""
                    self._cuda_fallback_pending = False
                    return self._model
                except Exception:
                    return self._load_cpu_fallback("NVIDIA CUDA 初始化失败，已自动回退到 CPU。")

            return self._load_model(runtime_config)

    def _load_cpu_fallback(self, reason: str) -> Any:
        self._cuda_fallback_pending = True
        self._fallback_reason = str(reason or "NVIDIA CUDA 不可用，已自动回退到 CPU。")
        return self._load_model(replace(self.config.cpu_fallback(), num_workers=self._model_num_workers))

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
        model_source = config.model
        if config.model in VOICE_MODEL_IDS:
            managed_dir = _managed_voice_model_dir(config.model)
            managed_root = get_voice_model_storage_root()
            legacy_dir = _legacy_voice_model_dir(config.model)
            if _managed_model_path_is_owned(managed_root, managed_dir) and _model_directory_is_ready(managed_dir):
                model_source = str(managed_dir)
            elif _model_directory_is_ready(legacy_dir):
                model_source = str(legacy_dir)
        return WhisperModel(
            model_source,
            device=config.device,
            compute_type=config.compute_type,
            num_workers=max(1, int(config.num_workers or 1)),
            local_files_only=not config.allow_download,
        )

    def _cache_path(self, account_dir: Path) -> Path:
        return _voice_transcript_cache_path(account_dir)

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

    def _write_cache(
        self,
        account_dir: Path,
        server_id: int,
        source_hash: str,
        result: dict[str, Any],
        *,
        expected_epoch: Optional[int] = None,
        expected_generation: Optional[int] = None,
    ) -> bool:
        path = self._cache_path(account_dir)
        normalized_text = normalize_transcript_text(result.get("text"))
        result["text"] = normalized_text
        with self._cache_lock:
            if (
                expected_generation is not None
                and int(_VOICE_TRANSCRIPT_CACHE_GENERATION) != expected_generation
            ):
                return False
            if expected_epoch is not None:
                account_key = _voice_transcript_cache_account_key(account_dir)
                current_epoch = int(_VOICE_TRANSCRIPT_CACHE_EPOCHS.get(account_key, 0))
                if current_epoch != expected_epoch:
                    return False
            path.parent.mkdir(parents=True, exist_ok=True)
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
        return True


def _download_voice_model_snapshot(
    model_id: str,
    *,
    output_dir: Path,
    progress_callback: Callable[..., None],
) -> Path:
    """Download one curated model while reporting aggregate materialized bytes."""

    _configure_voice_model_cancellable_hf_http_download()
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm as base_tqdm

    repo_id = VOICE_MODEL_REPOSITORIES[model_id]
    common = {
        "local_dir": str(output_dir),
        "allow_patterns": list(VOICE_MODEL_DOWNLOAD_ALLOW_PATTERNS),
        # A cancelled worker must not wait for other executor workers to drain.
        "max_workers": 1,
    }

    class SilentTqdm(base_tqdm):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.pop("name", None)
            self._voice_progress_desc = str(kwargs.get("desc", "") or "")
            self._voice_progress_unit = str(kwargs.get("unit", "") or "")
            kwargs["disable"] = False
            super().__init__(*args, **kwargs)

        def display(self, *args: Any, **kwargs: Any) -> None:
            return None

        def clear(self, *args: Any, **kwargs: Any) -> None:
            return None

    total_bytes = 0
    try:
        dry_run_files = snapshot_download(repo_id, dry_run=True, tqdm_class=SilentTqdm, **common)
        total_bytes = sum(max(0, int(getattr(item, "file_size", 0) or 0)) for item in dry_run_files)
    except Exception:
        # The actual download may still succeed after a transient metadata failure.
        total_bytes = 0
    progress_callback(
        stage="preparing",
        downloaded_bytes=0,
        total_bytes=total_bytes,
        force=True,
    )

    progress_lock = threading.Lock()
    progress_failed = threading.Event()
    reported_bytes = 0

    class DownloadProgressTqdm(SilentTqdm):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._voice_progress_closed = False
            super().__init__(*args, **kwargs)

        def _report(self, *, force: bool = False) -> None:
            nonlocal reported_bytes
            if progress_failed.is_set():
                return
            is_transfer = self._voice_progress_desc == "Downloading bytes"
            is_reconstruction = self._voice_progress_desc.startswith("Reconstructing")
            if self._voice_progress_unit != "B" or not (is_transfer or is_reconstruction):
                return

            current_bytes = max(0, int(getattr(self, "n", 0) or 0))
            if total_bytes > 0:
                current_bytes = min(current_bytes, total_bytes)
            with progress_lock:
                previous_bytes = reported_bytes
                reported_bytes = max(reported_bytes, current_bytes)
                current_bytes = reported_bytes
            if current_bytes == previous_bytes and not force:
                return
            try:
                progress_callback(
                    stage="downloading",
                    downloaded_bytes=current_bytes,
                    total_bytes=total_bytes,
                    force=force,
                )
            except BaseException:
                progress_failed.set()
                raise

        def refresh(self, *args: Any, **kwargs: Any) -> Any:
            result = super().refresh(*args, **kwargs)
            self._report()
            return result

        def update(self, n: int | float | None = 1) -> Any:
            result = super().update(n)
            self._report()
            return result

        def close(self) -> None:
            if self._voice_progress_closed:
                return
            self._voice_progress_closed = True
            try:
                if not progress_failed.is_set():
                    self._report(force=True)
            finally:
                super().close()

    progress_callback(
        stage="downloading",
        downloaded_bytes=0,
        total_bytes=total_bytes,
        force=True,
    )
    downloaded_dir = snapshot_download(repo_id, tqdm_class=DownloadProgressTqdm, **common)
    return Path(downloaded_dir)


def _voice_model_download_error_message(exc: Exception) -> str:
    chain: list[BaseException] = []
    current: Optional[BaseException] = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    if any(isinstance(item, OSError) and item.errno == errno.ENOSPC for item in chain):
        return "模型下载失败：磁盘空间不足。"
    if any(
        isinstance(item, PermissionError)
        or (isinstance(item, OSError) and item.errno in {errno.EACCES, errno.EPERM, errno.EROFS})
        for item in chain
    ):
        return "模型下载失败：模型目录没有写入权限。"

    details = " ".join(f"{type(item).__name__}: {item}" for item in chain).lower()
    if any(isinstance(item, httpx.ProxyError) for item in chain) or "proxy" in details:
        return "连接模型服务器的代理失败，请检查系统代理设置后重试。"
    if any(isinstance(item, ssl.SSLError) for item in chain) or any(
        marker in details
        for marker in ("certificate", "ssl", "tls", "unexpected_eof_while_reading", "wrong version number")
    ):
        return "与模型服务器建立 HTTPS 安全连接失败，请检查系统时间、代理或安全软件证书后重试。"
    if any(isinstance(item, (httpx.TimeoutException, TimeoutError)) for item in chain):
        return "连接模型服务器超时，请检查网络或代理后重试。"
    if any(
        isinstance(item, (httpx.NetworkError, socket.gaierror, ConnectionError))
        for item in chain
    ):
        return "无法连接模型服务器，请检查网络或代理后重试。"

    status_code = next(
        (
            int(getattr(getattr(item, "response", None), "status_code", 0) or 0)
            for item in chain
            if getattr(getattr(item, "response", None), "status_code", None)
        ),
        0,
    )
    if status_code in {401, 403}:
        return "模型服务器拒绝访问，请检查网络出口或访问权限后重试。"
    if status_code == 429:
        return "模型服务器请求过于频繁，请稍后重试。"
    if status_code >= 500:
        return "模型服务器暂时不可用，请稍后重试。"
    return f"模型下载失败：{type(exc).__name__}"


class _VoiceModelDownloadCancelled(RuntimeError):
    pass


class VoiceModelDownloadManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._latest_by_model: dict[str, str] = {}
        self._last_progress_updates: dict[str, float] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._completion_events: dict[str, threading.Event] = {}
        self._models_deleting: set[str] = set()

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        return dict(job)

    def latest_by_model(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                model: self._public(self._jobs[job_id])
                for model, job_id in self._latest_by_model.items()
                if job_id in self._jobs
            }

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(job_id or ""))
            if job is None:
                raise VoiceTranscriptionError("download_job_not_found", "模型下载任务不存在。")
            return self._public(job)

    def start(self, model: str) -> dict[str, Any]:
        model_id = str(model or "").strip()
        if model_id not in VOICE_MODEL_IDS:
            raise VoiceTranscriptionError("invalid_model", "不支持该 Whisper 模型。")
        activity_key = ""
        cancel_event = threading.Event()
        completion_event = threading.Event()
        with self._lock:
            if model_id in self._models_deleting:
                raise VoiceTranscriptionError("model_busy", "该模型正在删除，暂时不能下载。")
            previous_id = self._latest_by_model.get(model_id)
            previous = self._jobs.get(previous_id or "")
            if previous and previous.get("status") in {"queued", "running"}:
                return self._public(previous)
            if any(job.get("status") in {"queued", "running"} for job in self._jobs.values()):
                raise VoiceTranscriptionError(
                    "download_busy",
                    "已有其他 Whisper 模型正在下载，请等待其完成。",
                )
            activity_key = _acquire_voice_model_download_activity(model_id)
            job_id = f"model-{model_id}-{uuid.uuid4().hex}"
            job = {
                "jobId": job_id,
                "model": model_id,
                "status": "queued",
                "percent": 0,
                "downloadedBytes": 0,
                "totalBytes": 0,
                "stage": "queued",
                "error": "",
                "createdAt": time.time(),
                "startedAt": None,
                "finishedAt": None,
            }
            self._jobs[job_id] = job
            self._latest_by_model[model_id] = job_id
            self._cancel_events[job_id] = cancel_event
            self._completion_events[job_id] = completion_event
        thread = threading.Thread(
            target=self._run,
            args=(job_id, model_id, activity_key, cancel_event, completion_event),
            name=f"whisper-download-{model_id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            _release_voice_model_download_activity(activity_key)
            self._update(
                job_id,
                status="error",
                stage="error",
                error="模型下载任务启动失败。",
                finishedAt=time.time(),
            )
            completion_event.set()
            raise
        return self.get(job_id)

    def begin_delete(self, model: str) -> bool:
        """Block new downloads, cancel the active one, and wait for its cleanup."""

        model_id = str(model or "").strip()
        if model_id not in VOICE_MODEL_IDS:
            raise VoiceTranscriptionError("invalid_model", "不支持该 Whisper 模型。")

        job_id = ""
        completion_event: Optional[threading.Event] = None
        with self._lock:
            if model_id in self._models_deleting:
                raise VoiceTranscriptionError("model_busy", "该模型正在删除。")
            self._models_deleting.add(model_id)
            latest_id = self._latest_by_model.get(model_id) or ""
            latest = self._jobs.get(latest_id)
            latest_completion = self._completion_events.get(latest_id)
            if latest is not None and latest_completion is not None and not latest_completion.is_set():
                job_id = latest_id
                cancel_event = self._cancel_events.get(job_id)
                if cancel_event is not None:
                    cancel_event.set()
                latest["stage"] = "cancelling"
                completion_event = latest_completion

        try:
            if completion_event is not None:
                completion_event.wait()
        except BaseException:
            self.end_delete(model_id)
            raise

        if job_id:
            self._update(
                job_id,
                status="cancelled",
                stage="cancelled",
                error="",
                finishedAt=time.time(),
            )
        return bool(job_id)

    def end_delete(self, model: str) -> None:
        model_id = str(model or "").strip()
        with self._lock:
            self._models_deleting.discard(model_id)

    def _update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(values)
                if job.get("status") not in {"queued", "running"}:
                    self._last_progress_updates.pop(job_id, None)

    def _update_progress(
        self,
        job_id: str,
        *,
        stage: str,
        downloaded_bytes: int,
        total_bytes: int,
        force: bool = False,
    ) -> None:
        now = time.monotonic()
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.get("status") not in {"queued", "running"}:
                return
            if (
                not force
                and now - self._last_progress_updates.get(job_id, 0.0)
                < _VOICE_MODEL_PROGRESS_INTERVAL_SECONDS
            ):
                return

            downloaded = max(
                int(job.get("downloadedBytes") or 0),
                max(0, int(downloaded_bytes or 0)),
            )
            total = max(int(job.get("totalBytes") or 0), max(0, int(total_bytes or 0)))
            if total > 0:
                total = max(total, downloaded)
                percent = min(99, int(downloaded * 100 / total))
                job["percent"] = max(int(job.get("percent") or 0), percent)
            job.update(
                downloadedBytes=downloaded,
                totalBytes=total,
                stage=str(stage or job.get("stage") or "downloading"),
            )
            self._last_progress_updates[job_id] = now

    def _run(
        self,
        job_id: str,
        model_id: str,
        activity_key: str,
        cancel_event: threading.Event,
        completion_event: threading.Event,
    ) -> None:
        stage_dir: Optional[Path] = None
        try:
            if cancel_event.is_set():
                raise _VoiceModelDownloadCancelled()
            self._update(job_id, status="running", stage="preparing", startedAt=time.time())
            model_root = get_voice_model_storage_root()
            if model_root.exists() and _path_is_link_or_junction(model_root):
                raise VoiceTranscriptionError(
                    "model_download_refused",
                    "应用模型根目录是符号链接或目录联接，已拒绝写入。",
                )
            model_root.mkdir(parents=True, exist_ok=True)
            model_dir = _managed_voice_model_dir(model_id)
            if not _managed_model_path_is_owned(model_root, model_dir):
                raise VoiceTranscriptionError(
                    "model_download_refused",
                    "拒绝写入应用模型目录之外的路径。",
                )
            if _model_directory_is_ready(model_dir):
                self._update(job_id, status="done", stage="done", percent=100, finishedAt=time.time())
                return

            if cancel_event.is_set():
                raise _VoiceModelDownloadCancelled()

            stage_dir = model_root / f".{model_id}.download-{uuid.uuid4().hex}"
            if not _managed_model_path_is_owned(model_root, stage_dir):
                raise VoiceTranscriptionError(
                    "model_download_refused",
                    "拒绝写入应用模型目录之外的临时路径。",
                )
            def update_progress(**progress: Any) -> None:
                if cancel_event.is_set():
                    raise _VoiceModelDownloadCancelled()
                self._update_progress(job_id, **progress)
                if cancel_event.is_set():
                    raise _VoiceModelDownloadCancelled()

            downloaded_dir = _download_voice_model_snapshot(
                model_id,
                output_dir=stage_dir,
                progress_callback=update_progress,
            )
            if cancel_event.is_set():
                raise _VoiceModelDownloadCancelled()
            self._update_progress(
                job_id,
                stage="verifying",
                downloaded_bytes=0,
                total_bytes=0,
                force=True,
            )
            if downloaded_dir.resolve() != stage_dir.resolve() or not _model_directory_is_ready(stage_dir):
                raise VoiceTranscriptionError("model_download_incomplete", "模型下载完成，但缓存文件不完整。")
            if cancel_event.is_set():
                raise _VoiceModelDownloadCancelled()
            self._update_progress(
                job_id,
                stage="installing",
                downloaded_bytes=0,
                total_bytes=0,
                force=True,
            )
            if model_dir.exists():
                if not _managed_model_path_is_owned(model_root, model_dir):
                    raise VoiceTranscriptionError("model_download_refused", "拒绝替换符号链接或目录联接模型路径。")
                if model_dir.is_dir():
                    shutil.rmtree(model_dir)
                else:
                    model_dir.unlink()
            if cancel_event.is_set():
                raise _VoiceModelDownloadCancelled()
            os.replace(stage_dir, model_dir)
            stage_dir = None
            if cancel_event.is_set():
                raise _VoiceModelDownloadCancelled()
            if not _model_directory_is_ready(model_dir):
                raise VoiceTranscriptionError("model_download_incomplete", "模型下载完成，但缓存文件不完整。")
            current_service = get_voice_transcription_service()
            if current_service.config.model == model_id:
                _reset_voice_transcription_service()
            final_job = self.get(job_id)
            final_total = int(final_job.get("totalBytes") or 0)
            self._update(
                job_id,
                status="done",
                stage="done",
                percent=100,
                downloadedBytes=max(int(final_job.get("downloadedBytes") or 0), final_total),
                finishedAt=time.time(),
            )
        except _VoiceModelDownloadCancelled:
            self._update(
                job_id,
                status="cancelled",
                stage="cancelled",
                error="",
                finishedAt=time.time(),
            )
        except VoiceTranscriptionError as exc:
            self._update(
                job_id,
                status="error",
                stage="error",
                error=exc.user_message,
                finishedAt=time.time(),
            )
        except Exception as exc:
            logger.exception(
                "[voice-model-download] failed model=%s job_id=%s error_type=%s",
                model_id,
                job_id,
                type(exc).__name__,
            )
            self._update(
                job_id,
                status="error",
                stage="error",
                error=_voice_model_download_error_message(exc),
                finishedAt=time.time(),
            )
        finally:
            if stage_dir is not None and stage_dir.exists() and _managed_model_path_is_owned(
                get_voice_model_storage_root(), stage_dir
            ):
                try:
                    shutil.rmtree(stage_dir) if stage_dir.is_dir() else stage_dir.unlink()
                except OSError:
                    pass
            _release_voice_model_download_activity(activity_key)
            completion_event.set()


_VOICE_TRANSCRIPTION_BATCH_AUTO_CUDA_MODELS = frozenset({"tiny", "base", "small"})


def resolve_voice_transcription_batch_concurrency(
    requested: Optional[int],
    config: VoiceTranscriptionConfig,
) -> tuple[int, int]:
    """Return the normalized request (0 means auto) and effective worker count."""

    if requested is None:
        requested_value = 0
    elif isinstance(requested, bool) or not isinstance(requested, int) or requested < 0:
        raise VoiceTranscriptionError(
            "invalid_concurrency",
            "并发线程数必须是非负整数，0 表示自动。",
        )
    else:
        requested_value = requested
    if requested_value == 0:
        model = _public_model_name(config.model)
        effective = 2 if (
            config.device == VOICE_TRANSCRIPTION_DEVICE_CUDA
            and model in _VOICE_TRANSCRIPTION_BATCH_AUTO_CUDA_MODELS
        ) else 1
    else:
        effective = requested_value
    return requested_value, effective


class VoiceTranscriptionBatchManager:
    def __init__(
        self,
        *,
        service_getter: Callable[[], VoiceTranscriptionService] = None,
    ) -> None:
        self._service_getter = service_getter or get_voice_transcription_service
        self._uses_global_service = service_getter is None
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._latest_by_account: dict[str, str] = {}

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        return dict(job)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(job_id or ""))
            if job is None:
                raise VoiceTranscriptionError("batch_job_not_found", "批量语音转写任务不存在。")
            return self._public(job)

    def latest(self, account: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job_id = self._latest_by_account.get(str(account or "").strip())
            job = self._jobs.get(job_id or "")
            return self._public(job) if job is not None else None

    def _raise_if_account_active_unlocked(self, account: str) -> None:
        if any(
            str(job.get("account") or "") == account
            and job.get("status") in {"queued", "running"}
            for job in self._jobs.values()
        ):
            raise VoiceTranscriptionError(
                "batch_busy",
                "该账号正在批量转写，请等待完成或先取消。",
            )

    def _raise_if_any_account_active_unlocked(self) -> None:
        if any(job.get("status") in {"queued", "running"} for job in self._jobs.values()):
            raise VoiceTranscriptionError(
                "batch_busy",
                "语音批量转写正在运行，请等待完成或先取消。",
            )

    def forget_finished(self, account: str) -> bool:
        """Clear only the latest-job pointer after confirming the account is idle."""

        account_name = str(account or "").strip()
        with self._lock:
            self._raise_if_account_active_unlocked(account_name)
            return self._latest_by_account.pop(account_name, None) is not None

    def delete_cache_if_idle(self, *, account: str, account_dir: Path) -> dict[str, Any]:
        """Serialize account cache deletion against batch start and latest-job state."""

        account_name = str(account or "").strip()
        with self._lock:
            self._raise_if_account_active_unlocked(account_name)
            result = delete_voice_transcript_cache(account_dir)
            self.forget_finished(account_name)
            return result

    def delete_all_caches_if_idle(self) -> dict[str, Any]:
        """Block batch starts while all application account caches are swept."""

        with self._lock:
            self._raise_if_any_account_active_unlocked()
            result, successful_accounts = _delete_all_voice_transcript_caches_with_accounts()
            for account_name in successful_accounts:
                self.forget_finished(account_name)
            return result

    def start(
        self,
        *,
        account: str,
        account_dir: Path,
        force: bool = False,
        concurrency: Optional[int] = None,
        engine: str = "local",
    ) -> dict[str, Any]:
        account_name = str(account or Path(account_dir).name or "").strip()
        engine_name = str(engine or "local").strip().lower()
        if engine_name not in {"local", "wechat-native"}:
            raise VoiceTranscriptionError("invalid_engine", "不支持的批量转写方式。")
        service_lease: Optional[_VoiceTranscriptionServiceLease] = None
        activity_key = ""
        service: Optional[VoiceTranscriptionService] = None
        cache_generation = 0
        requested_concurrency = 0
        effective_concurrency = 1
        with self._lock:
            previous_id = self._latest_by_account.get(account_name)
            previous = self._jobs.get(previous_id or "")
            if previous and previous.get("status") in {"queued", "running"}:
                return self._public(previous)
            if any(job.get("status") in {"queued", "running"} for job in self._jobs.values()):
                raise VoiceTranscriptionError(
                    "batch_busy",
                    "已有其他账号正在批量转写，请等待其完成或先取消。",
                )
            if engine_name == "local":
                if self._uses_global_service:
                    service_lease = acquire_voice_transcription_service_lease()
                    service = service_lease.service
                else:
                    service = self._service_getter()
                    activity_key = acquire_voice_model_activity(service.config.model)
                try:
                    service.ensure_available()
                    cache_generation = capture_voice_transcript_cache_generation()
                    requested_concurrency, effective_concurrency = resolve_voice_transcription_batch_concurrency(
                        concurrency,
                        service.config,
                    )
                except Exception:
                    if service_lease is not None:
                        service_lease.release()
                    else:
                        release_voice_model_activity(activity_key)
                    raise
            else:
                from .native_core_voice_asr import native_core_voice_asr_status

                native_status = native_core_voice_asr_status(Path(account_dir))
                if not native_status.get("available"):
                    reason = str(native_status.get("reason") or "bridge_unavailable")
                    raise VoiceTranscriptionError(
                        "native_not_ready",
                        f"微信原生语音转文字当前不可用（{reason}）。",
                    )
            job_id = f"voice-batch-{uuid.uuid4().hex}"
            job = {
                "jobId": job_id,
                "account": account_name,
                "engine": engine_name,
                "model": _public_model_name(service.config.model) if service is not None else "wechat-native",
                "requestedConcurrency": requested_concurrency,
                "concurrency": effective_concurrency if engine_name == "local" else 1,
                "status": "queued",
                "total": 0,
                "completed": 0,
                "success": 0,
                "native": 0,
                "cached": 0,
                "failed": 0,
                "percent": 0,
                "currentServerId": "",
                "error": "",
                "warning": "",
                "scanWarningCount": 0,
                "createdAt": time.time(),
                "startedAt": None,
                "finishedAt": None,
            }
            self._jobs[job_id] = job
            self._latest_by_account[account_name] = job_id
            self._cancel_events[job_id] = threading.Event()
        thread = threading.Thread(
            target=self._run,
            args=(
                job_id,
                Path(account_dir),
                bool(force),
                service,
                service_lease,
                activity_key,
                effective_concurrency,
                cache_generation,
            ),
            name=f"voice-batch-{account_name}",
            daemon=True,
        )
        if engine_name == "wechat-native":
            thread = threading.Thread(
                target=self._run_native,
                args=(job_id, Path(account_dir)),
                name=f"voice-native-batch-{account_name}",
                daemon=True,
            )
        try:
            thread.start()
        except Exception:
            if service_lease is not None:
                service_lease.release()
            else:
                release_voice_model_activity(activity_key)
            self._update(job_id, status="error", error="批量语音转写任务启动失败。", finishedAt=time.time())
            raise
        return self.get(job_id)

    def has_active_model(self, model: str) -> bool:
        model_id = _public_model_name(str(model or "").strip())
        with self._lock:
            return any(
                job.get("status") in {"queued", "running"}
                and str(job.get("model") or "") == model_id
                for job in self._jobs.values()
            )

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(job_id or ""))
            if job is None:
                raise VoiceTranscriptionError("batch_job_not_found", "批量语音转写任务不存在。")
            event = self._cancel_events.get(str(job_id))
            if event is not None:
                event.set()
            return self._public(job)

    def _update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(values)

    @staticmethod
    def _transcribe_batch_item(
        *,
        service: VoiceTranscriptionService,
        account_dir: Path,
        server_id: int,
        force: bool,
        native: set[int],
        cancel_event: threading.Event,
        cache_generation: int,
    ) -> dict[str, Any]:
        if cancel_event.is_set():
            raise _VoiceTranscriptionCancelled()
        if server_id in native:
            return {"success": 1, "native": 1, "cached": 0, "failed": 0, "error": ""}
        try:
            result = service.transcribe_voice(
                account_dir=account_dir,
                server_id=server_id,
                force=force,
                cancel_event=cancel_event,
                cache_generation=cache_generation,
            )
            return {
                "success": 1,
                "native": 0,
                "cached": 1 if result.get("cached") else 0,
                "failed": 0,
                "error": "",
            }
        except _VoiceTranscriptionCancelled:
            raise
        except Exception as exc:
            return {
                "success": 0,
                "native": 0,
                "cached": 0,
                "failed": 1,
                "error": exc.user_message if isinstance(exc, VoiceTranscriptionError) else str(exc),
            }

    def _record_batch_result(
        self,
        job_id: str,
        server_id: int,
        outcome: dict[str, Any],
        total: int,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["completed"] = int(job["completed"]) + 1
            job["success"] = int(job["success"]) + int(outcome.get("success") or 0)
            job["native"] = int(job["native"]) + int(outcome.get("native") or 0)
            job["cached"] = int(job["cached"]) + int(outcome.get("cached") or 0)
            job["failed"] = int(job["failed"]) + int(outcome.get("failed") or 0)
            job["percent"] = min(99, int(job["completed"]) * 100 // total) if total else 100
            job["currentServerId"] = str(server_id)
            if outcome.get("error"):
                job["error"] = str(outcome["error"])

    @staticmethod
    def _transcribe_native_batch_item(
        *,
        account_dir: Path,
        target: Any,
        cancel_event: threading.Event,
    ) -> dict[str, Any]:
        from .native_voice_transcription import (
            NativeVoiceTriggerError,
            _dispatch_resolved_native_voice_transcription,
            lookup_native_voice_transcript_cache,
        )

        if cancel_event.is_set():
            raise _VoiceTranscriptionCancelled()
        if has_voice_transcript_cache(account_dir, int(target.server_id)):
            return {"success": 1, "native": 0, "cached": 1, "failed": 0, "error": ""}

        deadline = time.monotonic() + 115.0
        while not cancel_event.is_set() and time.monotonic() < deadline:
            try:
                result = _dispatch_resolved_native_voice_transcription(
                    account_dir=account_dir,
                    conversation=target.conversation,
                    server_id=int(target.server_id),
                    local_id=int(target.local_id),
                    existing_text=str(target.text or ""),
                )
            except NativeVoiceTriggerError as exc:
                if exc.code == "native_transport_busy":
                    time.sleep(1.0)
                    continue
                return {"success": 0, "native": 0, "cached": 0, "failed": 1, "error": exc.user_message}

            if str(result.get("status") or "") == "success":
                return {"success": 1, "native": 1, "cached": 0, "failed": 0, "error": ""}
            request_id = str(result.get("requestId") or "")
            if not request_id:
                return {
                    "success": 0,
                    "native": 0,
                    "cached": 0,
                    "failed": 1,
                    "error": "微信原生语音转文字未返回任务编号。",
                }
            while not cancel_event.is_set() and time.monotonic() < deadline:
                try:
                    entry = lookup_native_voice_transcript_cache(
                        account_dir,
                        int(target.server_id),
                        conversation=target.conversation,
                        local_id=int(target.local_id),
                        request_id=request_id,
                        strict=True,
                    )
                except NativeVoiceTriggerError as exc:
                    return {"success": 0, "native": 0, "cached": 0, "failed": 1, "error": exc.user_message}
                if entry is not None and entry.status == "success" and entry.text:
                    return {"success": 1, "native": 1, "cached": 0, "failed": 0, "error": ""}
                if entry is not None and entry.status == "error":
                    return {
                        "success": 0,
                        "native": 0,
                        "cached": 0,
                        "failed": 1,
                        "error": entry.error_message or "微信原生语音转文字失败。",
                    }
                time.sleep(1.0)
            break
        if cancel_event.is_set():
            raise _VoiceTranscriptionCancelled()
        return {
            "success": 0,
            "native": 0,
            "cached": 0,
            "failed": 1,
            "error": "等待微信原生语音转文字结果超时。",
        }

    def _run_native(self, job_id: str, account_dir: Path) -> None:
        from .native_voice_transcription import list_native_voice_batch_targets

        self._update(job_id, status="running", startedAt=time.time(), stage="scan")
        try:
            cancel_event = self._cancel_events[job_id]
            scan_errors: list[str] = []
            targets = list_native_voice_batch_targets(
                account_dir,
                cancel_event=cancel_event,
                errors=scan_errors,
            )
            if cancel_event.is_set():
                self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
                return
            if scan_errors:
                self._update(
                    job_id,
                    warning=f"有 {len(set(scan_errors))} 个数据库范围未能完整扫描，结果可能不完整。",
                    scanWarningCount=len(set(scan_errors)),
                )
            self._update(
                job_id,
                total=len(targets),
                concurrency=1,
                percent=100 if not targets else 0,
                stage="transcribe",
            )
            if not targets:
                self._update(job_id, status="done", currentServerId="", finishedAt=time.time())
                return
            for target in targets:
                if cancel_event.is_set():
                    break
                self._update(job_id, currentServerId=str(target.server_id))
                try:
                    outcome = self._transcribe_native_batch_item(
                        account_dir=account_dir,
                        target=target,
                        cancel_event=cancel_event,
                    )
                except _VoiceTranscriptionCancelled:
                    break
                self._record_batch_result(job_id, int(target.server_id), outcome, len(targets))
            if cancel_event.is_set():
                self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
            else:
                self._update(job_id, status="done", percent=100, currentServerId="", finishedAt=time.time())
        except _VoiceTranscriptionCancelled:
            self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
        except Exception as exc:
            self._update(
                job_id,
                status="error",
                currentServerId="",
                error=f"微信原生批量转写失败：{type(exc).__name__}",
                finishedAt=time.time(),
            )

    def _run(
        self,
        job_id: str,
        account_dir: Path,
        force: bool,
        service: VoiceTranscriptionService,
        service_lease: Optional[_VoiceTranscriptionServiceLease],
        activity_key: str,
        concurrency: int,
        cache_generation: int,
    ) -> None:
        self._update(job_id, status="running", startedAt=time.time())
        try:
            cancel_event = self._cancel_events[job_id]
            scan_errors: list[str] = []
            server_ids = list_voice_server_ids(
                account_dir,
                cancel_event=cancel_event,
                errors=scan_errors,
            )
            if cancel_event.is_set():
                self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
                return
            message_voice_ids: set[int] = set()
            native = list_native_voice_transcripts(
                account_dir,
                cancel_event=cancel_event,
                errors=scan_errors,
                voice_server_ids=message_voice_ids,
            )
            if cancel_event.is_set():
                self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
                return
            scan_errors = list(dict.fromkeys(scan_errors))
            if scan_errors:
                self._update(
                    job_id,
                    warning=f"有 {len(scan_errors)} 个数据库范围未能完整扫描，结果可能不完整。",
                    scanWarningCount=len(scan_errors),
                )
            server_ids = sorted(set(server_ids).union(message_voice_ids).union(native))
            total = len(server_ids)
            concurrency = min(concurrency, total) if total else 0
            self._update(
                job_id,
                total=total,
                concurrency=concurrency,
                percent=100 if total == 0 else 0,
            )
            if total == 0:
                self._update(job_id, status="done", currentServerId="", finishedAt=time.time())
                return
            configure = getattr(service, "configure_inference_concurrency", None)
            if callable(configure):
                configured = configure(concurrency, cancel_event=cancel_event)
                if (
                    isinstance(configured, int)
                    and not isinstance(configured, bool)
                    and configured > 0
                ):
                    concurrency = min(configured, total)
                    self._update(job_id, concurrency=concurrency)
            if cancel_event.is_set():
                self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
                return
            server_iter = iter(server_ids)
            pending: dict[Future, int] = {}
            exhausted = False
            with ThreadPoolExecutor(
                max_workers=concurrency,
                thread_name_prefix=f"voice-inference-{job_id[-8:]}",
            ) as executor:
                while pending or not exhausted:
                    while not exhausted and len(pending) < concurrency:
                        with self._lock:
                            if cancel_event.is_set():
                                break
                            try:
                                server_id = next(server_iter)
                            except StopIteration:
                                exhausted = True
                                break
                            self._jobs[job_id]["currentServerId"] = str(server_id)
                            future = executor.submit(
                                self._transcribe_batch_item,
                                service=service,
                                account_dir=account_dir,
                                server_id=server_id,
                                force=force,
                                native=native,
                                cancel_event=cancel_event,
                                cache_generation=cache_generation,
                            )
                            pending[future] = server_id

                    if cancel_event.is_set():
                        exhausted = True
                        for future in list(pending):
                            if future.cancel():
                                pending.pop(future, None)
                    if not pending:
                        break

                    completed_futures, _ = wait(
                        tuple(pending),
                        timeout=0.1,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in completed_futures:
                        server_id = pending.pop(future)
                        try:
                            outcome = future.result()
                        except _VoiceTranscriptionCancelled:
                            continue
                        self._record_batch_result(job_id, server_id, outcome, total)

            if cancel_event.is_set():
                self._update(job_id, status="cancelled", currentServerId="", finishedAt=time.time())
            else:
                self._update(job_id, status="done", percent=100, currentServerId="", finishedAt=time.time())
        except _VoiceTranscriptionCancelled:
            self._update(
                job_id,
                status="cancelled",
                currentServerId="",
                finishedAt=time.time(),
            )
        except Exception as exc:
            self._update(
                job_id,
                status="error",
                currentServerId="",
                error=f"批量语音转写失败：{type(exc).__name__}",
                finishedAt=time.time(),
            )
        finally:
            if service_lease is not None:
                service_lease.release()
            else:
                release_voice_model_activity(activity_key)


_VOICE_TRANSCRIPTION_SERVICE: Optional[VoiceTranscriptionService] = None
_VOICE_TRANSCRIPTION_SERVICE_CONDITION = threading.Condition()
_VOICE_TRANSCRIPTION_SERVICE_RESETTING = False
_VOICE_TRANSCRIPTION_SERVICE_LEASES = 0


class _VoiceTranscriptionServiceLease:
    """Keep one service generation and its selected model stable for an operation."""

    def __init__(self, service: VoiceTranscriptionService, activity_key: str) -> None:
        self.service = service
        self._activity_key = activity_key
        self._release_lock = threading.Lock()
        self._released = False

    def release(self) -> None:
        global _VOICE_TRANSCRIPTION_SERVICE_LEASES
        with self._release_lock:
            if self._released:
                return
            self._released = True
        release_voice_model_activity(self._activity_key)
        with _VOICE_TRANSCRIPTION_SERVICE_CONDITION:
            _VOICE_TRANSCRIPTION_SERVICE_LEASES = max(0, _VOICE_TRANSCRIPTION_SERVICE_LEASES - 1)
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.notify_all()


def acquire_voice_transcription_service_lease() -> _VoiceTranscriptionServiceLease:
    """Atomically bind the current service generation and its model activity."""

    global _VOICE_TRANSCRIPTION_SERVICE, _VOICE_TRANSCRIPTION_SERVICE_LEASES
    with _VOICE_TRANSCRIPTION_SERVICE_CONDITION:
        while _VOICE_TRANSCRIPTION_SERVICE_RESETTING:
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.wait()
        if _VOICE_TRANSCRIPTION_SERVICE is None:
            _VOICE_TRANSCRIPTION_SERVICE = VoiceTranscriptionService()
        service = _VOICE_TRANSCRIPTION_SERVICE
        _VOICE_TRANSCRIPTION_SERVICE_LEASES += 1
        try:
            activity_key = acquire_voice_model_activity(service.config.model)
        except Exception:
            _VOICE_TRANSCRIPTION_SERVICE_LEASES = max(0, _VOICE_TRANSCRIPTION_SERVICE_LEASES - 1)
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.notify_all()
            raise
        return _VoiceTranscriptionServiceLease(service, activity_key)


def get_voice_transcription_service() -> VoiceTranscriptionService:
    global _VOICE_TRANSCRIPTION_SERVICE
    with _VOICE_TRANSCRIPTION_SERVICE_CONDITION:
        while _VOICE_TRANSCRIPTION_SERVICE_RESETTING:
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.wait()
        if _VOICE_TRANSCRIPTION_SERVICE is None:
            _VOICE_TRANSCRIPTION_SERVICE = VoiceTranscriptionService()
        return _VOICE_TRANSCRIPTION_SERVICE


def _reset_voice_transcription_service() -> VoiceTranscriptionService:
    global _VOICE_TRANSCRIPTION_SERVICE, _VOICE_TRANSCRIPTION_SERVICE_RESETTING
    with _VOICE_TRANSCRIPTION_SERVICE_CONDITION:
        while _VOICE_TRANSCRIPTION_SERVICE_RESETTING:
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.wait()
        _VOICE_TRANSCRIPTION_SERVICE_RESETTING = True
        while _VOICE_TRANSCRIPTION_SERVICE_LEASES > 0:
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.wait()
        previous = _VOICE_TRANSCRIPTION_SERVICE
        _VOICE_TRANSCRIPTION_SERVICE = None
    replacement: Optional[VoiceTranscriptionService] = None
    try:
        if previous is not None:
            try:
                previous.retire()
            except Exception:
                pass
        replacement = VoiceTranscriptionService()
        return replacement
    finally:
        with _VOICE_TRANSCRIPTION_SERVICE_CONDITION:
            _VOICE_TRANSCRIPTION_SERVICE = replacement
            _VOICE_TRANSCRIPTION_SERVICE_RESETTING = False
            _VOICE_TRANSCRIPTION_SERVICE_CONDITION.notify_all()


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

    current_service = get_voice_transcription_service()
    current_model = current_service.config.model
    _begin_voice_model_deletion(current_model)
    try:
        write_voice_transcription_device_setting(normalized)
        invalidate_cuda_probe_cache()
        return _reset_voice_transcription_service().status()
    finally:
        _end_voice_model_deletion(current_model)


def set_voice_transcription_model(model: str) -> dict[str, Any]:
    """Persist a curated multilingual Whisper model selection."""

    normalized = str(model or "").strip()
    if normalized not in VOICE_MODEL_IDS:
        raise VoiceTranscriptionError("invalid_model", "不支持该 Whisper 模型。")

    _configured, source = read_effective_voice_transcription_model()
    if source == "env":
        raise VoiceTranscriptionError(
            "model_locked",
            "当前模型由 WECHAT_TOOL_WHISPER_MODEL 环境变量锁定，无法在界面中修改。",
        )

    current_service = get_voice_transcription_service()
    current_model = current_service.config.model
    _begin_voice_model_deletion(current_model)
    try:
        write_voice_transcription_model_setting(normalized)
        return _reset_voice_transcription_service().status()
    finally:
        _end_voice_model_deletion(current_model)


def delete_voice_model(model: str) -> dict[str, Any]:
    """Delete only files under this application's managed model directory."""

    model_id = str(model or "").strip()
    if model_id not in VOICE_MODEL_IDS:
        raise VoiceTranscriptionError("invalid_model", "不支持该 Whisper 模型。")

    if VOICE_TRANSCRIPTION_BATCH_MANAGER.has_active_model(model_id):
        raise VoiceTranscriptionError("model_busy", "该模型正在用于批量转写，暂时不能删除。")

    _begin_voice_model_deletion(model_id, allow_download_activity=True)
    download_delete_started = False
    try:
        cancelled_download = VOICE_MODEL_DOWNLOAD_MANAGER.begin_delete(model_id)
        download_delete_started = True
        try:
            root = get_voice_model_storage_root()
            target = _managed_voice_model_dir(model_id)
            paths = [target, *_managed_voice_model_stage_dirs(model_id)]
            existing = [path for path in paths if path.exists() or _path_is_link_or_junction(path)]
            for path in existing:
                if not _managed_model_path_is_owned(root, path):
                    raise VoiceTranscriptionError(
                        "model_delete_refused",
                        "拒绝删除符号链接、目录联接或应用模型目录之外的路径。",
                    )
            if not existing:
                return {
                    "status": "success",
                    "model": model_id,
                    "deleted": bool(cancelled_download),
                    "freedBytes": 0,
                }

            freed_bytes = 0
            for path in existing:
                if path.is_dir():
                    freed_bytes += sum(
                        file.stat().st_size
                        for file in path.rglob("*")
                        if file.is_file() and not file.is_symlink()
                    )
                elif path.is_file():
                    freed_bytes += int(path.stat().st_size)

            current_service = get_voice_transcription_service()
            if current_service.config.model == model_id:
                _reset_voice_transcription_service()
            for path in existing:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            return {
                "status": "success",
                "model": model_id,
                "deleted": True,
                "freedBytes": freed_bytes,
            }
        except VoiceTranscriptionError:
            raise
        except Exception as exc:
            raise VoiceTranscriptionError("model_delete_failed", f"模型删除失败：{type(exc).__name__}") from exc
    finally:
        if download_delete_started:
            VOICE_MODEL_DOWNLOAD_MANAGER.end_delete(model_id)
        _end_voice_model_deletion(model_id)


VOICE_MODEL_DOWNLOAD_MANAGER = VoiceModelDownloadManager()
VOICE_TRANSCRIPTION_BATCH_MANAGER = VoiceTranscriptionBatchManager()
