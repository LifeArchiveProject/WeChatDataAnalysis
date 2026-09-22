"""在语音工作进程内加载新后端；不在应用启动时导入大型推理库。"""
from __future__ import annotations

import json
from pathlib import Path


LANGUAGES = {"zh": "Chinese", "en": "English", "yue": "Cantonese", "ja": "Japanese",
             "ko": "Korean", "fr": "French", "de": "German", "es": "Spanish",
             "ru": "Russian", "pt": "Portuguese", "ar": "Arabic", "it": "Italian"}


def language_name(language: str) -> str | None:
    if language in ("", "auto"):
        return None
    if language in LANGUAGES:
        return LANGUAGES[language]
    if language in LANGUAGES.values():
        return language
    raise ValueError("当前 Qwen 接口不支持该语言设置，请使用 zh、en 或 auto。")


def read_audio(path: str):
    import av
    import numpy as np
    parts = []
    with av.open(path) as container:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for output in resampler.resample(frame):
                parts.append(output.to_ndarray().reshape(-1))
        for output in resampler.resample(None):
            parts.append(output.to_ndarray().reshape(-1))
    return np.concatenate(parts).astype(np.float32) if parts else np.zeros(0, dtype=np.float32)


def audio_chunks(audio, maximum_seconds: float):
    """在窗口末尾的低能量处切分，避免导出模型长输入错误和截断。"""
    import numpy as np
    maximum = int(maximum_seconds * 16000)
    remaining = audio
    while len(remaining) > maximum:
        candidates = range(int(maximum * 0.7), maximum - 320, 320)
        cut = min(candidates, key=lambda p: float(np.mean(remaining[p:p + 320] ** 2)))
        yield remaining[:cut]
        remaining = remaining[cut:]
    if len(remaining):
        yield remaining


def mel_filters():
    """Slaney 归一化三角滤波器，与 Qwen 导出时的 128 维特征一致。"""
    import numpy as np
    log_step = np.log(6.4) / 27.0
    maximum = 15.0 + np.log(8000.0 / 1000.0) / log_step
    mels = np.linspace(0.0, maximum, 130)
    hz = np.where(mels < 15, mels * (200.0 / 3), 1000 * np.exp(log_step * (mels - 15)))
    fft_hz = np.linspace(0, 8000, 201)
    lower = (fft_hz[None, :] - hz[:-2, None]) / np.diff(hz)[:-1, None]
    upper = (hz[2:, None] - fft_hz[None, :]) / np.diff(hz)[1:, None]
    filters = np.maximum(0, np.minimum(lower, upper)) * (2 / (hz[2:] - hz[:-2]))[:, None]
    return filters.astype(np.float32)


def log_mel(audio, filters):
    import numpy as np
    padded = np.pad(audio, (200, 200), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, 400)[::160]
    window = np.hanning(401)[:-1].astype(np.float32)
    powers = (np.abs(np.fft.rfft(frames * window, axis=-1)) ** 2).astype(np.float32).T
    mel = np.log10(np.maximum(filters @ powers, 1e-10))
    return ((np.maximum(mel, mel.max() - 8) + 4) / 4)[None, :, :-1].astype(np.float32)


class ZipformerBackend:
    precision = "int8"
    chunk_seconds = 15

    def __init__(self, folder: Path, threads: int):
        import sherpa_onnx
        self.model = sherpa_onnx.OfflineRecognizer.from_zipformer_ctc(
            model=str(folder / "ctc.int8.onnx"), tokens=str(folder / "data/tokens.txt"),
            num_threads=threads, sample_rate=16000, feature_dim=80, provider="cpu")

    def transcribe(self, audio, language):
        if language not in ("zh", "en", "auto", ""):
            raise ValueError("Zipformer CTC 仅支持中英文，请选择 Qwen 处理其他语言。")
        stream = self.model.create_stream()
        stream.accept_waveform(16000, audio)
        self.model.decode_stream(stream)
        return stream.result.text


class QwenOnnxBackend:
    precision = "int4"
    chunk_seconds = 25

    def __init__(self, folder: Path, threads: int):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.sessions = {name: ort.InferenceSession(str(folder / f"{name}.int4.onnx"), opts,
                        providers=["CPUExecutionProvider"]) for name in ("encoder", "decoder_init", "decoder_step")}
        decoder = self.config["decoder"]
        self.embeddings = np.memmap(folder / "embed_tokens.bin", mode="r", dtype=self.config["embed_tokens_dtype"],
                                   shape=(decoder["vocab_size"], decoder["hidden_size"]))
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.filters = mel_filters()

    def transcribe(self, audio, language):
        import numpy as np
        features = self.sessions["encoder"].run(["audio_features"], {"mel": log_mel(audio, self.filters)})[0]
        encode = lambda text: self.tokenizer.encode(text, add_special_tokens=False).ids
        prefix = encode('<|im_start|>system\n<|im_end|>\n<|im_start|>user\n<|audio_start|>')
        lang = language_name(language)
        suffix = '<|audio_end|><|im_end|>\n<|im_start|>assistant\n'
        if lang:
            suffix += f'language {lang}<asr_text>'
        prompt = prefix + [self.config["special_tokens"]["audio_pad_token_id"]] * features.shape[1] + encode(suffix)
        positions = np.arange(len(prompt), dtype=np.int64)[None, :]
        initial = self.sessions["decoder_init"]
        if "input_ids" in {x.name for x in initial.get_inputs()}:
            inputs = dict(input_ids=np.array([prompt], dtype=np.int64), position_ids=positions,
                          audio_features=features, audio_offset=np.array([len(prefix)], dtype=np.int64))
        else:
            embeddings = np.asarray(self.embeddings[prompt], dtype=np.float32).copy()
            embeddings[len(prefix):len(prefix) + features.shape[1]] = features[0]
            inputs = dict(input_embeds=embeddings[None], position_ids=positions)
        outputs = ["logits", "present_keys", "present_values"]
        logits, keys, values = initial.run(outputs, inputs)
        generated = []
        eos = self.config["special_tokens"]["eos_token_ids"]
        for index in range(512):
            token = int(np.argmax(logits[0, -1]))
            if token in eos:
                break
            generated.append(token)
            logits, keys, values = self.sessions["decoder_step"].run(outputs, dict(
                input_embeds=np.asarray(self.embeddings[token], dtype=np.float32)[None, None],
                position_ids=np.array([[len(prompt) + index]], dtype=np.int64), past_keys=keys, past_values=values))
        else:
            raise RuntimeError("识别输出超过长度限制，请改用其他模型。")
        return self.tokenizer.decode(generated, skip_special_tokens=True).split("<asr_text>")[-1].strip()


class QwenGpuBackend:
    chunk_seconds = 25

    def __init__(self, folder: Path, threads: int):
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        if not torch.cuda.is_available():
            raise RuntimeError("Qwen GPU 需要可用的 PyTorch CUDA 运行环境，请改用 CPU 模型或安装 GPU 组件。")
        torch.set_num_threads(threads)
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        self.precision = "bfloat16" if dtype == torch.bfloat16 else "float16"
        self.processor = AutoProcessor.from_pretrained(folder, local_files_only=True)
        self.model = AutoModelForMultimodalLM.from_pretrained(folder, dtype=dtype,
            attn_implementation="sdpa", local_files_only=True).to("cuda").eval()

    def transcribe(self, audio, language):
        import torch
        with torch.inference_mode():
            inputs = self.processor.apply_transcription_request(audio=audio, language=language_name(language))
            inputs = inputs.to(self.model.device, self.model.dtype)
            generated = self.model.generate(**inputs, max_new_tokens=512, do_sample=False)
            tokens = generated[:, inputs["input_ids"].shape[1]:]
            if tokens.shape[1] >= 512:
                raise RuntimeError("识别输出超过长度限制，请改用其他模型。")
            return self.processor.decode(tokens, return_format="transcription_only")[0]


def load_backend(backend: str, folder: str, threads: int):
    return {"zipformer": ZipformerBackend, "qwen-onnx": QwenOnnxBackend, "qwen-hf": QwenGpuBackend}[backend](Path(folder), threads)
