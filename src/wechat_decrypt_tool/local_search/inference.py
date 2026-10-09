"""隔离推理进程：CUDA 故障后销毁进程，再用 CPU 重放未提交批次。"""
from ..ai.diagnostics import observed, event as diagnostic_event
import ipaddress
import logging
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from ..ai.diagnostics import exception_fields
from urllib.parse import urlparse


class InferenceFailure(RuntimeError):
    def __init__(self, message, category='runtime'):
        super().__init__(message)
        self.category = category


def is_lan_endpoint(endpoint):
    """判断远端向量服务地址是否属于局域网/回环，用于决定要不要绕过系统代理。

    Windows 上代理客户端会把代理写进注册表，httpx 会自动读取并使用它；不绕过的话，
    发往局域网 GPU 的请求会被本机代理拦下，表现为 502 或超时，报错看不出真正原因。
    """
    host = urlparse(str(endpoint or '')).hostname
    if not host:
        return False
    host = host.strip('[]').lower()
    if host == 'localhost' or host.endswith('.local'):
        return True
    from ..ai.providers import is_proxy_bypass_host
    # 私有网段、Tailscale 等 100.64/10 覆盖网络、链路本地都直连；只有真正对外的
    # 地址才让代理参与。
    if is_proxy_bypass_host(host):
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # 单标签主机名（如 gpu-server）按局域网处理。
        return '.' not in host
    return False


def remote_api_base(endpoint):
    """OpenAI 兼容服务的基地址：接受 .../v1、.../v1/embeddings 或裸主机地址。

    用户填的地址形态不统一，这里统一归一到 `.../v1`，再拼 /embeddings 与 /models。
    """
    endpoint = str(endpoint or '').strip().rstrip('/')
    if not endpoint:
        return ''
    if endpoint.endswith('/embeddings'):
        endpoint = endpoint[:-len('/embeddings')]
    if not re.search(r'/v\d+$', endpoint):
        endpoint += '/v1'
    return endpoint


def decode_remote_vector(value):
    """向量既可能是浮点数组，也可能是 base64 编码的 float32 小端数据。"""
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        import base64
        import struct
        raw = base64.b64decode(value)
        if not raw or len(raw) % 4:
            raise InferenceFailure('远端返回的 base64 向量长度不合法', 'remote')
        return list(struct.unpack('<%df' % (len(raw) // 4), raw))
    raise InferenceFailure('远端返回的向量格式无法识别', 'remote')


def parse_remote_vectors(data, expected, dimension=None):
    """按 OpenAI 规范的 index 排序取向量：不能假设服务端按返回顺序对齐请求顺序。"""
    items = data.get('data') if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise InferenceFailure('远端返回不是 OpenAI 兼容的向量结构', 'remote')
    ordered = sorted(items, key=lambda item: item.get('index', 0) if isinstance(item, dict) else 0)
    vectors = []
    for item in ordered:
        value = item.get('embedding') if isinstance(item, dict) else item
        vector = decode_remote_vector(value)
        if dimension and len(vector) != dimension:
            raise InferenceFailure('远端向量维度与索引不一致（%d ≠ %d），请重新建立索引' % (len(vector), dimension), 'remote')
        vectors.append(vector)
    if len(vectors) != expected:
        raise InferenceFailure('远端向量数量不匹配', 'remote')
    return vectors


def inference_worker(pipe, root, spec, device, device_id, gpu_root):
    # 子进程只经 Pipe 回传元数据，由父进程统一落盘。
    logging.disable(logging.CRITICAL)
    try:
        os.environ['TOKENIZERS_PARALLELISM']='false'
        from .catalog import verify_model
        try: verify_model(root,spec,report=lambda name, fields:pipe.send({'diagnostic_event':name, **fields}))
        except (ValueError,OSError): raise InferenceFailure('模型文件缺失或损坏，请重新下载或导入','model') from None
        device_name='CPU'
        if device == 'cuda':
            from .gpu import gpu_devices,MANIFEST_PATH
            selected=next((d for d in gpu_devices() if int(d['id'])==device_id),None)
            if not selected: raise InferenceFailure('未发现所选 NVIDIA GPU','gpu')
            minimum=json.loads(MANIFEST_PATH.read_text())['minimum_windows_driver']
            if tuple(map(int,selected['driver'].split('.'))) < tuple(map(int,minimum.split('.'))):
                raise InferenceFailure('NVIDIA 驱动未达到本组件发布基线','gpu')
            device_name=selected['name']
            # 子进程启动前没有导入 ORT；附加组件只对本进程生效。
            sys.path.insert(0, gpu_root)
            dll_handles = []
            for folder in Path(gpu_root).rglob('bin'):
                if os.name == 'nt':
                    dll_handles.append(os.add_dll_directory(str(folder)))
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        if device == 'cuda' and 'CUDAExecutionProvider' not in ort.get_available_providers():
            raise InferenceFailure('NVIDIA 加速组件不可用', 'gpu')
        tokenizer = Tokenizer.from_file(str(Path(root) / 'tokenizer.json'))
        tokenizer.enable_padding(pad_id=tokenizer.token_to_id('[PAD]') or tokenizer.token_to_id('<pad>') or 0)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        providers = ['CPUExecutionProvider']
        profile_dir = None
        if device == 'cuda':
            if hasattr(ort, 'preload_dlls'):
                ort.preload_dlls(directory='')
            providers = [('CUDAExecutionProvider', {'device_id': device_id, 'use_tf32': 0, 'arena_extend_strategy': 'kSameAsRequested', 'gpu_mem_limit': 2 * 1024**3}), 'CPUExecutionProvider']
            profile_dir = tempfile.TemporaryDirectory(prefix='wechat-semantic-probe-')
            options.enable_profiling = True
            options.profile_file_prefix = str(Path(profile_dir.name) / 'probe')
        session = ort.InferenceSession(str(Path(root) / 'onnx/model.onnx'), sess_options=options, providers=providers)

        def encode(texts, query=False):
            prefix = spec['query_prefix'] if query else spec['passage_prefix']
            tokens = tokenizer.encode_batch([prefix + text for text in texts])
            if any(len(t.ids) > spec['max_tokens'] for t in tokens):
                raise InferenceFailure('检索内容超过模型输入长度，请缩短搜索条件', 'input')
            arrays = {'input_ids': np.array([t.ids for t in tokens], dtype=np.int64),
                      'attention_mask': np.array([t.attention_mask for t in tokens], dtype=np.int64),
                      'token_type_ids': np.array([t.type_ids for t in tokens], dtype=np.int64)}
            outputs = session.run(None, {i.name: arrays[i.name] for i in session.get_inputs()})
            vectors = outputs[0]
            if vectors.ndim == 3:
                if spec['pooling'] == 'cls':
                    vectors = vectors[:, 0]
                else:
                    mask = arrays['attention_mask'][..., None]
                    vectors = (vectors * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            vectors = vectors.astype(np.float32)
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True).clip(min=1e-12)
            if vectors.shape[1] != spec['dimension'] or not np.isfinite(vectors).all():
                raise InferenceFailure('模型输出维度或数值异常', 'model')
            return vectors.tolist()

        encode(['本地模型连接测试'])
        if device == 'cuda':
            profile = json.loads(Path(session.end_profiling()).read_text(encoding='utf-8'))
            if not any(e.get('args', {}).get('provider') == 'CUDAExecutionProvider' for e in profile):
                raise InferenceFailure('显卡未实际参与推理', 'gpu')
            profile_dir.cleanup()
        pipe.send({'ready': True, 'device': device, 'device_name':device_name, 'runtime': ort.__version__})
        while True:
            request = pipe.recv()
            if request is None:
                break
            try:
                pipe.send({'vectors': encode(request['texts'], request.get('query', False))})
            except Exception as error:
                category = getattr(error, 'category', 'gpu' if device == 'cuda' else 'runtime')
                pipe.send({'error': category, 'diagnostic_fields': exception_fields(error)})
    except Exception as error:
        try:
            pipe.send({'error': getattr(error, 'category', 'gpu' if device == 'cuda' else 'model'), 'diagnostic': str(error) if isinstance(error,InferenceFailure) else type(error).__name__, 'diagnostic_fields': exception_fields(error)})
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()


class LocalInference:
    def __init__(self, gpu_root=None, callback=None):
        self.gpu_root = gpu_root
        self.callback = callback or (lambda status: None)
        self.lock = threading.RLock()
        self.process = self.pipe = None
        self.key = None
        self.gpu_failed = False
        self.last_used = 0
        self.status = {'actual_device': None, 'using_fallback': False, 'reason': ''}
        self.runtime_info={}
        self.query_waiting=0
        self.priority=threading.Condition()

    def close(self):
        with self.lock:
            self._close()

    def _close(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=3)
            diagnostic_event('inference.process.exited', pid=getattr(self.process,'pid',None), exit_code=getattr(self.process,'exitcode',None))
        if self.pipe:
            self.pipe.close()
        self.process = self.pipe = self.key = None

    def _receive(self, cancelled, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                self.close()
                raise InferenceFailure('处理已暂停', 'cancelled')
            if self.pipe.poll(.1):
                try:
                    result = self.pipe.recv()
                except (EOFError, OSError):
                    raise InferenceFailure('推理进程已退出', 'process') from None
                if result.get('diagnostic_event') in {'model.file.verify.started','model.file.verify.finished'}:
                    diagnostic_event(result['diagnostic_event'], level=logging.ERROR if result.get('validation_status')=='failed' else logging.INFO,
                                     file=result.get('file'), total=result.get('total'), model=result.get('model'), validation_status=result.get('validation_status'))
                    continue
                if 'error' in result:
                    diagnostic_event('inference.process.failed', level=logging.WARNING, reason_code=result['error'], **result.get('diagnostic_fields', {}))
                    raise InferenceFailure('本地推理未完成：' + result.get('diagnostic', result['error']), result['error'])
                return result
            if not self.process.is_alive():
                raise InferenceFailure('推理进程已退出', 'process')
        raise InferenceFailure('模型响应超时', 'timeout')

    QUERY_MAX_CHARS = 2000

    def _remote_encode(self, spec, texts, query=False, cancelled=None):
        """调用 OpenAI 兼容的 /v1/embeddings。

        协议固定为 `{model, input, encoding_format}` → `data[].embedding`，Ollama、LM Studio、
        vLLM 等服务都提供这个入口，不需要用户另行为本工具实现一套接口。
        """
        import httpx

        def status_message(exc):
            response = getattr(exc, 'response', None)
            status = getattr(response, 'status_code', 0)
            detail = ''
            try:
                body = (response.text or '').strip()
                if body:
                    detail = '：' + body[:180]
            except Exception:
                detail = ''
            if status in (401, 403):
                return '远端服务拒绝访问（密钥无效或未授权）%s' % detail
            if status == 404:
                return '远端服务没有 /v1/embeddings（检查地址是否缺少 /v1，或该服务不提供向量接口）%s' % detail
            if status == 400:
                return '远端服务拒绝了这批文本（模型名不存在或文本超出上下文）%s' % detail
            if status == 429:
                return '远端服务限流，请稍后重试%s' % detail
            if status >= 500:
                return '远端服务返回 %d%s' % (status, detail)
            return '远端服务返回 %d%s' % (status, detail)

        endpoint = str(spec.get('endpoint') or '').strip()
        base = remote_api_base(endpoint)
        if not base:
            raise InferenceFailure('远端模型未配置服务地址', 'remote')
        model = str(spec.get('model') or '').strip()
        if not model:
            raise InferenceFailure('远端模型未配置模型名', 'remote')
        if cancelled and cancelled():
            raise InferenceFailure('处理已暂停', 'cancelled')
        values = [str(text) for text in texts]
        if query:
            # 查询串按字符上界收口：上下文小的模型遇到长句会直接 400。
            values = [text[:self.QUERY_MAX_CHARS] for text in values]
        headers = {}
        key = str(spec.get('api_key') or '').strip()
        if key:
            headers['Authorization'] = 'Bearer ' + key
        payload = {'model': model, 'input': values, 'encoding_format': 'float'}
        timeout = httpx.Timeout(float(spec.get('timeout') or 300.0), connect=10.0)
        try:
            # 局域网与覆盖网络地址绕过系统代理，否则请求会被本机代理拦下；
            # 自签名证书只在用户显式允许时跳过校验。
            with httpx.Client(timeout=timeout, trust_env=not is_lan_endpoint(endpoint),
                              verify=not bool(spec.get('allow_self_signed'))) as client:
                response = client.post(base + '/embeddings', json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise InferenceFailure(status_message(exc), 'remote') from None
        except httpx.HTTPError as exc:
            raise InferenceFailure('无法连接远端向量服务：%s' % exc, 'remote') from None
        except ValueError as exc:
            raise InferenceFailure('远端返回不是有效 JSON：%s' % exc, 'remote') from None
        if cancelled and cancelled():
            raise InferenceFailure('处理已暂停', 'cancelled')
        return parse_remote_vectors(data, len(values), spec.get('dimension') or None)

    @observed('inference.encode')
    def encode(self, root, spec, texts, strategy='auto', device_id=0, query=False, cancelled=None):
        if spec.get('backend') == 'remote':
            return self._remote_encode(spec, texts, query=query, cancelled=cancelled)
        queued = time.monotonic()
        with self.priority:
            if query: self.query_waiting+=1
            else:
                while self.query_waiting:
                    if cancelled and cancelled(): raise InferenceFailure('处理已暂停','cancelled')
                    self.priority.wait(.1)
        with self.lock:
            if query:
                with self.priority:
                    self.query_waiting-=1
                    self.priority.notify_all()
            if cancelled and cancelled(): raise InferenceFailure('处理已暂停','cancelled')
            # 完整模型的加载错误不按显卡故障反复重试。
            if not (Path(root)/'onnx/model.onnx').is_file() or not (Path(root)/'tokenizer.json').is_file():
                raise InferenceFailure('本地模型文件缺失，请重新下载或导入','model')
            cuda_supported = sys.platform == 'win32'
            device = 'cuda' if cuda_supported and strategy != 'cpu' and self.gpu_root and not self.gpu_failed else 'cpu'
            # Mac 的自动模式本来就使用 CPU，不能误报为缺少 NVIDIA 组件或 GPU 故障。
            fallback = device == 'cpu' and (strategy == 'cuda' or (cuda_supported and strategy == 'auto'))
            diagnostic_event('inference.batch.acquired', queue_ms=(time.monotonic()-queued)*1000, actual_device=device, purpose='query' if query else 'index',
                             reason_code='gpu_unavailable' if fallback else 'platform_cpu' if not cuda_supported else 'configured', count=len(texts))
            for attempt in range(2):
                try:
                    key = (str(root), spec['revision'], device, device_id)
                    if self.key != key:
                        self.close()
                        parent, child = mp.get_context('spawn').Pipe()
                        self.pipe = parent
                        self.process = mp.get_context('spawn').Process(target=inference_worker,
                            args=(child, str(root), spec, device, device_id, str(self.gpu_root or '')), daemon=True)
                        self.process.start()
                        diagnostic_event('inference.process.started', pid=getattr(self.process,'pid',None), actual_device=device, device_id=device_id)
                        child.close()
                        ready=self._receive(cancelled)
                        diagnostic_event('inference.process.ready', actual_device=device, runtime=ready.get('runtime'), model=spec.get('id'))
                        self.runtime_info={k:ready.get(k) for k in ('device_name','runtime')}
                        self.key = key
                    self.pipe.send({'texts': texts, 'query': query})
                    vectors = self._receive(cancelled)['vectors']
                    diagnostic_event('inference.batch.finished', actual_device=device, count=len(vectors), using_fallback=fallback)
                    self.last_used = time.monotonic()
                    previous_status = self.status
                    self.status = {**self.runtime_info,'actual_device': device, 'using_fallback': fallback,
                        'device_id': device_id if device=='cuda' else None,
                        'diagnostic': self.status.get('diagnostic') if fallback else None,
                        'reason': ('当前系统使用 CPU 本地推理，不支持 NVIDIA 加速组件' if not cuda_supported else '显卡暂不可用，已使用 CPU 继续处理' if self.gpu_failed else 'NVIDIA 加速组件尚未就绪，当前使用 CPU') if fallback else ''}
                    # 设备未变时不逐批写入相同事件，避免快速推理淹没进度推送。
                    if self.status != previous_status:
                        self.callback(self.status)
                    return vectors
                except InferenceFailure as error:
                    self.close()
                    if device == 'cuda' and error.category not in {'cancelled', 'input', 'model'}:
                        diagnostic_event('inference.cpu.fallback', level=logging.WARNING, error=error, reason_code=error.category)
                        self.gpu_failed, fallback, device = True, True, 'cpu'
                        self.status = {'actual_device': 'switching', 'using_fallback': True, 'reason': 'GPU 推理失败，正在使用 CPU 恢复当前批次', 'diagnostic': str(error)}
                        self.callback(self.status)
                        continue
                    raise
            raise InferenceFailure('CPU 恢复失败')
