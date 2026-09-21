"""新语音模型的固定版本、资产校验和能力声明；旧 Whisper ID 保持原含义。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Callable

SPECS = json.loads((Path(__file__).parent / "resources/voice_models.json").read_text(encoding="utf-8"))
NEW_MODEL_CATALOG = (
    dict(id="zipformer-small-ctc-int8", name="Zipformer CTC", size="约 29 MB", speed="CPU 极速",
         quality="低配优先", description="中英文短语音，低内存占用；长语音自动分段，输出不含标点。", recommended=True),
    dict(id="qwen3-asr-06b-onnx-int4", name="Qwen3-ASR 0.6B · CPU", size="约 2.03 GB", speed="CPU",
         quality="质量优先", description="无需独显；本机实测进程内存约 3.65 GiB，建议 16 GB 内存。"),
    dict(id="qwen3-asr-06b-hf", name="Qwen3-ASR 0.6B · GPU", size="约 1.58 GB", speed="NVIDIA GPU",
         quality="质量优先", description="需 Qwen GPU 运行组件；本机文本差异较少，速度慢于 Turbo。"),
    dict(id="qwen3-asr-17b-hf", name="Qwen3-ASR 1.7B · GPU", size="约 4.09 GB", speed="NVIDIA GPU",
         quality="大模型", description="需 Qwen GPU 运行组件；本机分配显存约 4 GiB，需另留运行余量。"),
)


def cache_identity(model: str) -> str:
    spec = SPECS.get(model)
    if not spec:
        return model
    return f"{model}@{spec['revision']}:{spec['backend']}:v{spec['cacheVersion']}"


def model_files_ready(path: Path, model: str) -> bool:
    """状态轮询只检查路径和大小，完整哈希在模型安装前校验。"""
    spec = SPECS[model]
    try:
        root = path.resolve()
        if not path.is_dir() or path.is_symlink():
            return False
        for name, entry in spec["files"].items():
            target = path / name
            if not target.resolve().is_relative_to(root) or target.is_symlink():
                return False
            if not target.is_file() or target.stat().st_size != entry["size"]:
                return False
        return True
    except OSError:
        return False


def verify_model_files(path: Path, model: str, checkpoint: Callable[[], None] = lambda: None) -> None:
    if not model_files_ready(path, model):
        raise ValueError("模型文件缺失或大小不符")
    for name, entry in SPECS[model]["files"].items():
        digest = hashlib.sha256()
        with (path / name).open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                checkpoint()
                digest.update(chunk)
        if digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"模型文件校验失败：{name}")


def dependency_status(model: str) -> tuple[bool, str]:
    backend = SPECS.get(model, {}).get("backend", "whisper")
    packages = {
        "whisper": ("faster_whisper",),
        "zipformer": ("sherpa_onnx", "av", "numpy"),
        "qwen-onnx": ("onnxruntime", "tokenizers", "av", "numpy"),
        "qwen-hf": ("torch", "transformers", "av", "numpy"),
    }[backend]
    try:
        ready = all(importlib.util.find_spec(name) is not None for name in packages)
    except (ImportError, ValueError):
        ready = False
    if ready:
        return True, ""
    if backend == "qwen-hf":
        return False, "当前未安装 Qwen GPU 运行组件，请使用含 Qwen GPU 组件的版本，或选择 CPU 模型 / Turbo。"
    return False, "缺少语音识别运行组件，请安装语音转文字可选依赖或更新应用。"
