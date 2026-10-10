import hashlib
import json
from pathlib import Path
from ..ai.diagnostics import event as diagnostic_event
import logging

CATALOG = json.loads((Path(__file__).parents[1] / 'resources/local_search_models.json').read_text(encoding='utf-8'))

def model_spec(id):
    for model in CATALOG:
        if model['id'] == id:
            return model
    raise ValueError('不支持的检索模型')

def remote_spec(id, endpoint=None, model=None, api_key=None, allow_self_signed=False, dimension=None):
    """远端模型的地址、模型名和密钥都由账号配置覆盖，目录里的值只是预设。

    协议固定为 OpenAI 兼容的 /v1/embeddings，所以这里不再区分服务商。
    """
    spec = model_spec(id)
    if spec.get('backend') != 'remote':
        return spec
    spec = {**spec}
    endpoint = str(endpoint or '').strip().rstrip('/')
    if endpoint:
        spec['endpoint'] = endpoint
    model = str(model or '').strip()
    if model:
        spec['model'] = model
    key = str(api_key or '').strip()
    if key:
        spec['api_key'] = key
    if allow_self_signed:
        spec['allow_self_signed'] = True
    if dimension:
        try:
            spec['dimension'] = int(dimension)
        except (TypeError, ValueError):
            pass
    return spec


def remote_identity(spec):
    """索引身份指纹。

    同一个模型 id 下换了服务地址、模型名或维度，索引里的旧向量就和新查询不在同一个
    向量空间，余弦距离算出来只是无意义的数字，所以这些字段必须参与「要不要重建」的判断。
    """
    if spec.get('backend') != 'remote':
        return None
    fields = [str(spec.get('protocol') or 'openai'), str(spec.get('endpoint') or ''), str(spec.get('model') or ''),
              str(spec.get('dimension') or '')]
    return hashlib.sha256('\n'.join(fields).encode()).hexdigest()[:32]

def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()

def verify_model(root, spec, report=None):
    root = Path(root).resolve()
    for item in spec['files']:
        path = (root / item['path']).resolve()
        fields = {'file': item['path'], 'total': item['size'], 'model': spec.get('id')}
        if report: report('model.file.verify.started', fields)
        else: diagnostic_event('model.file.verify.started', **fields)
        valid = path.is_relative_to(root) and path.is_file() and path.stat().st_size == item['size'] and file_hash(path) == item['sha256']
        fields['validation_status'] = 'success' if valid else 'failed'
        if report: report('model.file.verify.finished', fields)
        else: diagnostic_event('model.file.verify.finished', level=logging.INFO if valid else logging.ERROR, **fields)
        if not valid:
            raise ValueError('模型文件缺失或校验失败：' + item['path'])

def model_dir(root, id):
    spec = model_spec(id)
    return Path(root) / spec['id'] / spec['revision']
