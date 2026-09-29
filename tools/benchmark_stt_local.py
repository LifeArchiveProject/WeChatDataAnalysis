"""在本机固定语音集上测 ASR，参考文本只用于事后评分，不传入模型。"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import random
import statistics
import sys
import threading
import time
import unicodedata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--tag', default='')
    parser.add_argument('--chunk-seconds', type=float, default=0)
    args = parser.parse_args()
    # 所有模型均先下载到本地；正式推理期间禁止模型库联网。
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OMP_NUM_THREADS=str(args.threads), MKL_NUM_THREADS=str(args.threads))
    import numpy as np
    import psutil
    import soundfile as sf
    from opencc import OpenCC
    from rapidfuzz.distance import Levenshtein
    root = args.root.resolve()
    samples = json.loads((root / 'manifest.private.json').read_text(encoding='utf-8'))['samples']
    if args.limit:
        samples = samples[:args.limit]
    audio = {s['id']: sf.read(s['path'], dtype='float32')[0] for s in samples}
    converter = OpenCC('t2s')

    def normalize(text):
        return ''.join(c for c in converter.convert(unicodedata.normalize('NFKC', text)).lower()
                       if unicodedata.category(c)[0] in 'LN')

    proc = psutil.Process()
    baseline_rss = proc.memory_info().rss
    peak_rss = [baseline_rss]
    stop = threading.Event()

    def monitor():
        while not stop.wait(0.05):
            try:
                peak_rss[0] = max(peak_rss[0], proc.memory_info().rss)
            except psutil.Error:
                pass

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    load_start = time.perf_counter()
    sync = lambda: None
    details = {}
    key = args.model
    if key.startswith('whisper-'):
        # 使用项目原有的 beam=5、中文、VAD 和关闭前文条件配置。
        from faster_whisper import WhisperModel
        name, device = key[len('whisper-'):].rsplit('-', 1)
        if device == 'cuda':
            # CUDA DLL 仅添加到测试进程，不修改系统 PATH。
            torch_lib = Path(sys.prefix) / 'Lib/site-packages/torch/lib'
            handles = [os.add_dll_directory(str(torch_lib))] if torch_lib.exists() else []
            os.environ['PATH'] = str(torch_lib) + os.pathsep + os.environ['PATH']
        model = WhisperModel(str(root / 'models' / ('whisper-' + name)), device=device,
                             compute_type='int8' if device == 'cpu' else 'float16',
                             cpu_threads=args.threads, num_workers=1, local_files_only=True)
        def transcribe(waveform):
            segments, _ = model.transcribe(waveform, language='zh', beam_size=5,
                                           vad_filter=True, condition_on_previous_text=False)
            return ''.join(s.text for s in segments)
        details = dict(device=device, precision='int8' if device == 'cpu' else 'float16',
                       beam_size=5, vad_filter=True)
    elif key.startswith('zipformer-'):
        import sherpa_onnx
        folder = root / 'models/zipformer'
        common = dict(tokens=str(folder / 'data/tokens.txt'), num_threads=args.threads,
                      sample_rate=16000, feature_dim=80, provider='cpu')
        if key == 'zipformer-ctc':
            model = sherpa_onnx.OfflineRecognizer.from_zipformer_ctc(
                model=str(folder / 'ctc.int8.onnx'), **common)
        else:
            model = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(folder / 'encoder.int8.onnx'), decoder=str(folder / 'decoder.onnx'),
                joiner=str(folder / 'joiner.int8.onnx'), **common)
        def transcribe(waveform):
            stream = model.create_stream()
            stream.accept_waveform(16000, waveform)
            model.decode_stream(stream)
            return stream.result.text
        details = dict(device='cpu', precision='mixed-int8', decoder='greedy_search')
    elif key == 'qwen-onnx-cpu':
        import onnxruntime as ort
        import librosa
        from tokenizers import Tokenizer
        sys.path.insert(0, str(root / 'qwen-onnx-source'))
        from src.inference import greedy_decode_onnx
        folder = root / 'models/qwen-onnx'
        cfg = json.loads((folder / 'config.json').read_text())
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = args.threads
        opts.inter_op_num_threads = 1
        sessions = {name: ort.InferenceSession(str(folder / (name + '.int4.onnx')), opts,
                                             providers=['CPUExecutionProvider'])
                    for name in ['encoder', 'decoder_init', 'decoder_step']}
        embedding = np.memmap(folder / 'embed_tokens.bin', mode='r', dtype=cfg['embed_tokens_dtype'],
                              shape=(cfg['decoder']['vocab_size'], cfg['decoder']['hidden_size']))
        class Embeddings:
            def __getitem__(self, index):
                return np.asarray(embedding[index], dtype=np.float32)
        tokens = Tokenizer.from_file(str(folder / 'tokenizer.json'))
        filters = librosa.filters.mel(sr=16000, n_fft=400, n_mels=128, fmin=0, fmax=8000, norm='slaney')
        # 按实际分词器编码角色名；上游示例硬编码的 system/user ID 与本模型不符。
        prompt_prefix = tokens.encode('<|im_start|>system\n<|im_end|>\n<|im_start|>user\n<|audio_start|>', add_special_tokens=False).ids
        prompt_suffix = tokens.encode('<|audio_end|><|im_end|>\n<|im_start|>assistant\nlanguage Chinese<asr_text>', add_special_tokens=False).ids
        def transcribe(waveform):
            stft = librosa.stft(waveform, n_fft=400, hop_length=160, window='hann', center=True, pad_mode='reflect')
            mel = filters @ (np.abs(stft) ** 2)
            mel = np.log10(np.maximum(mel, 1e-10))
            mel = (np.maximum(mel, mel.max() - 8) + 4) / 4
            features = sessions['encoder'].run(['audio_features'], {'mel': mel[None, :, :-1].astype(np.float32)})[0]
            prompt = prompt_prefix + [cfg['special_tokens']['audio_pad_token_id']] * features.shape[1] + prompt_suffix
            generated = greedy_decode_onnx(sessions, Embeddings(), features, prompt, max_tokens=512)
            return tokens.decode(generated, skip_special_tokens=True).split('<asr_text>')[-1].strip()
        details = dict(device='cpu', precision='fp32-encoder/int4-decoder', language='Chinese', max_tokens=512)
    elif key in ('qwen-06-cuda', 'qwen-17-cuda'):
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        assert torch.cuda.is_available(), '当前测试环境的 PyTorch CUDA 不可用'
        torch.set_num_threads(args.threads)
        folder = root / 'models' / key.removesuffix('-cuda')
        processor = AutoProcessor.from_pretrained(folder, local_files_only=True)
        model = AutoModelForMultimodalLM.from_pretrained(folder, dtype=torch.bfloat16,
                    attn_implementation='sdpa', local_files_only=True).to('cuda').eval()
        sync = torch.cuda.synchronize
        torch.cuda.reset_peak_memory_stats()
        def transcribe(waveform):
            with torch.inference_mode():
                inputs = processor.apply_transcription_request(audio=waveform, language='Chinese').to(model.device, model.dtype)
                ids = model.generate(**inputs, max_new_tokens=512, do_sample=False)
                generated = ids[:, inputs['input_ids'].shape[1]:]
                return processor.decode(generated, return_format='transcription_only')[0]
        details = dict(device='cuda', precision='bfloat16', language='Chinese', max_tokens=512, attention='sdpa')
    else:
        raise ValueError(key)

    if args.chunk_seconds:
        original_transcribe = transcribe
        def transcribe(waveform):
            # 在窗口末端附近寻找低能量位置，限制导出模型的最大输入长度。
            remaining = waveform
            texts = []
            maximum = int(args.chunk_seconds * 16000)
            while len(remaining) > maximum:
                candidates = range(int(maximum * 0.7), maximum - 320, 320)
                cut = min(candidates, key=lambda p: float(np.mean(remaining[p:p+320] ** 2)))
                texts.append(original_transcribe(remaining[:cut]))
                remaining = remaining[cut:]
            if len(remaining):
                texts.append(original_transcribe(remaining))
            return ''.join(texts)
        details['chunk_max_seconds'] = args.chunk_seconds
        details['chunk_method'] = 'minimum RMS in last 30% of window'
    sync()
    load_seconds = time.perf_counter() - load_start
    # 第一条单独预热；所有模型使用相同样本，不计入热运行速度。
    started = time.perf_counter()
    warmup_text = transcribe(audio[samples[0]['id']])
    sync()
    warmup_seconds = time.perf_counter() - started
    print(json.dumps(dict(event='loaded', model=key, load_seconds=load_seconds,
                          first_inference_seconds=warmup_seconds)), flush=True)
    rows = []
    result_dir = root / 'results'
    result_dir.mkdir(exist_ok=True)
    target = result_dir / (key + args.tag + '.private.json')
    for round_index in range(args.rounds):
        order = list(samples)
        random.Random(20260921 + round_index).shuffle(order)
        for sample in order:
            sync()
            started = time.perf_counter()
            text = transcribe(audio[sample['id']])
            sync()
            elapsed = time.perf_counter() - started
            ref, hyp = normalize(sample['reference']), normalize(text)
            row = dict(id=sample['id'], round=round_index, audio_seconds=sample['duration'],
                       seconds=elapsed, transcript=text, reference=sample['reference'],
                       edits=Levenshtein.distance(ref, hyp), reference_chars=len(ref))
            rows.append(row)
            target.write_text(json.dumps(dict(model=key, complete=False, rows=rows), ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(dict(event='sample', model=key, round=round_index,
                                  done=len(rows), seconds=round(elapsed, 3))), flush=True)
    stop.set()
    monitor_thread.join()
    first_round = [x for x in rows if x['round'] == 0]
    per_sample = [statistics.median([r['seconds'] for r in rows if r['id'] == s['id']]) for s in samples]
    versions = {}
    for package in ['faster-whisper', 'ctranslate2', 'sherpa-onnx', 'onnxruntime', 'torch', 'transformers', 'numpy']:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    result = dict(model=key, complete=True, sample_count=len(samples), rounds=args.rounds,
        audio_seconds=sum(s['duration'] for s in samples),
        hot_seconds=sum(per_sample), rtf=sum(per_sample)/sum(s['duration'] for s in samples),
        p50_seconds=float(np.percentile(per_sample, 50)), p95_seconds=float(np.percentile(per_sample, 95)),
        silver_cer=sum(r['edits'] for r in first_round)/max(1,sum(r['reference_chars'] for r in first_round)),
        exact_matches=sum(r['edits']==0 for r in first_round),
        load_seconds=load_seconds, first_inference_seconds=warmup_seconds,
        peak_rss_bytes=peak_rss[0], baseline_rss_bytes=baseline_rss,
        details=details, threads=args.threads, versions=versions,
        reference_type='WeChat native ASR; not human verified; CER measures disagreement, not proven error rate', rows=rows)
    if key.startswith('qwen-') and key.endswith('-cuda'):
        result['torch_peak_allocated_bytes'] = torch.cuda.max_memory_allocated()
        result['torch_peak_reserved_bytes'] = torch.cuda.max_memory_reserved()
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
