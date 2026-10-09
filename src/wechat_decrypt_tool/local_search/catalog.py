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

def remote_spec(id, endpoint=None):
    # 远端模型的地址由账号配置覆盖，目录里的地址只是默认值。
    spec = model_spec(id)
    endpoint = str(endpoint or '').strip().rstrip('/')
    return {**spec, 'endpoint': endpoint} if endpoint and spec.get('backend') == 'remote' else spec

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
