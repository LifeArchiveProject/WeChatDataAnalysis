"""远端向量协议、索引切换和 tokenizer 缓存的隔离回归。"""
import asyncio
import base64
import json
import struct

import httpx
import pytest
from tokenizers import Tokenizer, models

from wechat_decrypt_tool.local_search.catalog import (
    configured_spec, index_model_metadata, remote_identity, remote_spec,
)
from wechat_decrypt_tool.local_search.inference import (
    InferenceFailure, LocalInference, parse_remote_vectors,
)
from wechat_decrypt_tool.local_search.service import LocalSearch


def response(vectors):
    return {'data': [{'index': index, 'embedding': vector} for index, vector in enumerate(vectors)]}


def mock_clients(monkeypatch, handler):
    """所有 HTTP 请求使用同一模拟服务，不读取账号数据、不连接外部服务。"""
    original_sync, original_async = httpx.Client, httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original_sync(transport=transport, **kwargs))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_async(transport=transport, **kwargs))


def service_fixture(tmp_path, monkeypatch, reader=None):
    service = LocalSearch(tmp_path / 'state', tmp_path / 'models', reader=reader)
    monkeypatch.setattr(service, 'enrichment_version', lambda account: [])
    monkeypatch.setattr(service, 'local_text', lambda account, messages: None)
    return service


def initial_config():
    spec = remote_spec('remote-openai', 'http://gpu-a/v1', 'model-a', 'old-key', dimension=2)
    return {'enabled': True, 'model': 'remote-openai', 'remote_endpoint': spec['endpoint'],
            'remote_model': spec['model'], 'remote_api_key': spec['api_key'], 'remote_dimension': 2,
            'days': 0, 'start': 0, 'end': 100, 'usernames': ['chat'], 'revision': 1,
            'active': {'model': 'remote-openai', 'generation': 'old', 'usernames': ['chat'],
                       'start': 0, 'end': 100, 'updated': 1, **index_model_metadata(spec)}}


@pytest.mark.parametrize('endpoint', ['http://127.0.0.1:11434', 'http://127.0.0.1:11434/v1',
                                     'http://127.0.0.1:11434/v1/embeddings'])
def test_ollama_compatible_request_and_reordered_response(monkeypatch, endpoint):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'data': [{'index': 1, 'embedding': [0., 1.]},
                                                {'index': 0, 'embedding': [1., 0.]}]})
    mock_clients(monkeypatch, handler)
    spec = remote_spec('remote-openai', endpoint, 'bge-m3', 'test-key', dimension=2)
    assert LocalInference().encode(None, spec, ['first', 'second']) == [[1., 0.], [0., 1.]]
    assert requests[0].url.path == '/v1/embeddings'
    assert json.loads(requests[0].content) == {'model': 'bge-m3', 'input': ['first', 'second'],
                                             'encoding_format': 'float'}
    assert requests[0].headers['Authorization'] == 'Bearer test-key'


def test_base64_vectors_preserve_input_order():
    encoded = base64.b64encode(struct.pack('<2f', 0., 1.)).decode()
    assert parse_remote_vectors({'data': [{'index': 1, 'embedding': encoded},
                                          {'index': 0, 'embedding': [1., 0.]}]}, 2, 2) == [[1., 0.], [0., 1.]]


@pytest.mark.parametrize('items', [
    [{'embedding': [1., 0.]}],
    [{'index': -1, 'embedding': [1., 0.]}],
    [{'index': 1, 'embedding': [1., 0.]}],
    [{'index': True, 'embedding': [1., 0.]}],
    [{'index': '0', 'embedding': [1., 0.]}],
    [[1., 0.]],
    [{'index': 0, 'embedding': [1., 0.]}, {'index': 0, 'embedding': [0., 1.]}],
])
def test_invalid_indices_are_rejected(items):
    with pytest.raises(InferenceFailure, match='序号|结构'):
        parse_remote_vectors({'data': items}, len(items), 2)


@pytest.mark.parametrize('vector', [
    [], [0., 0.], [1e-50, 0.], [float('nan'), 1.], [float('inf'), 1.],
    [float('-inf'), 1.], [1e40, 1.], [10 ** 400, 1.], ['1', 0.], [True, 0.],
    [None, 1.], '!!!', base64.b64encode(struct.pack('<2f', float('nan'), 1.)).decode(),
])
def test_invalid_vector_values_are_rejected(vector):
    with pytest.raises(InferenceFailure):
        parse_remote_vectors({'data': [{'index': 0, 'embedding': vector}]}, 1, 2)


def test_dimension_and_count_are_checked_even_without_probe():
    with pytest.raises(InferenceFailure, match='维度'):
        parse_remote_vectors(response([[1., 0.]]), 1, 2048)
    with pytest.raises(InferenceFailure, match='维度'):
        parse_remote_vectors(response([[1., 0.], [1., 0., 0.]]), 2)
    with pytest.raises(InferenceFailure, match='数量'):
        parse_remote_vectors(response([[1., 0.]]), 2, 2)


def test_cancelled_request_is_not_sent(monkeypatch):
    def handler(request):
        pytest.fail('取消后不得发送远端请求')
    mock_clients(monkeypatch, handler)
    with pytest.raises(InferenceFailure) as error:
        LocalInference().encode(None, remote_spec('remote-openai', 'http://gpu/v1', 'model'),
                                ['text'], cancelled=lambda: True)
    assert error.value.category == 'cancelled'


@pytest.mark.parametrize('account_wide', [False, True])
def test_remote_index_build_query_and_model_switch(tmp_path, monkeypatch, account_wide):
    calls, published = [], []
    def handler(request):
        if request.method == 'GET':
            if request.url.path.endswith('/models'):
                return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'}]})
            return httpx.Response(404)
        body = json.loads(request.content)
        calls.append((str(request.url), body['model'], request.headers.get('Authorization')))
        vector = [1., 0.] if body['model'] == 'model-a' else [0., 1.]
        return httpx.Response(200, json=response([vector] * len(body['input'])))
    mock_clients(monkeypatch, handler)
    def reader(account, username, start, end, offset):
        return {'messages': [dict(source='m1', anchor='m1', username='chat', sender='alice',
                                  time=50, kind='text', text='交付时间确认', media={})] if offset == 0 else [],
                'name': '测试聊天', 'has_more': False, 'source': 'snapshot'}
    async def run():
        service = service_fixture(tmp_path, monkeypatch, reader)
        original_publish = service.publish_partial
        def publish(job):
            original_publish(job)
            if account_wide:
                published.append(service.config('account')['active'])
        monkeypatch.setattr(service, 'publish_partial', publish)
        try:
            await service.configure('account', {'enabled': True, 'model': 'remote-openai',
                'remote_endpoint': 'http://gpu-a/v1', 'remote_model': 'model-a', 'remote_api_key': 'old-key',
                'agent_global': account_wide, 'usernames': ['chat'], 'start': 0, 'end': 100, 'days': 0})
            first = await service.build('account')
            await service.jobs[first['id']]
            assert first['status'] == 'done'
            assert service.config('account')['active']['remote_spec']['model'] == 'model-a'
            await service.configure('account', {'remote_endpoint': 'http://gpu-b/v1',
                                                'remote_model': 'model-b', 'remote_api_key': 'new-key'})
            result = await service.hybrid('account', {'hits': []}, '查询', ['chat'])
            assert result['retrievalMode'] == 'hybrid' and result['hits'][0]['id'] == 'm1'
            assert calls[-1] == ('http://gpu-a/v1/embeddings', 'model-a', 'Bearer old-key')
            second = await service.build('account')
            await service.jobs[second['id']]
            assert second['status'] == 'done' and second['generation'] != first['generation']
            assert service.index('account').stats(first['generation']) == {'messages': 0, 'chunks': 0}
            result = await service.hybrid('account', {'hits': []}, '新查询', ['chat'])
            assert result['retrievalMode'] == 'hybrid' and result['hits'][0]['id'] == 'm1'
            assert calls[-1] == ('http://gpu-b/v1/embeddings', 'model-b', 'Bearer new-key')
            if account_wide:
                assert [item['identity'] for item in published] == [
                    remote_identity(item['remote_spec']) for item in published]
                assert [item['remote_spec']['model'] for item in published] == ['model-a', 'model-b']
        finally:
            await service.stop()
            service.store.close()
    asyncio.run(run())


def test_partial_publication_does_not_force_rebuild(tmp_path, monkeypatch):
    async def run():
        service = service_fixture(tmp_path, monkeypatch)
        cfg = initial_config()
        cfg['agent_global'] = True
        service.store.put('config', cfg, id='account', account='account')
        async def no_run(job):
            return None
        monkeypatch.setattr(service, 'run', no_run)
        try:
            first = await service.build('account')
            await service.jobs[first['id']]
            first['coverage'] = {'0': {'username': 'chat', 'start': 0, 'end': 100, 'complete': False}}
            service.publish_partial(first)
            active = service.config('account')['active']
            assert active['identity'] == cfg['active']['identity']
            assert active['remote_spec']['endpoint'] == 'http://gpu-a/v1'
            second = await service.build('account')
            await service.jobs[second['id']]
            assert second['generation'] == first['generation']
        finally:
            await service.stop()
            service.store.close()
    asyncio.run(run())


@pytest.mark.parametrize('changed', [False, True])
def test_legacy_index_uses_current_config_only_when_identity_matches(tmp_path, monkeypatch, changed):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response([[1., 0.]]))
    mock_clients(monkeypatch, handler)
    async def run():
        service = service_fixture(tmp_path, monkeypatch)
        cfg = initial_config()
        cfg['active'].pop('remote_spec')
        if changed:
            cfg['remote_model'] = 'model-b'
        service.store.put('config', cfg, id='account', account='account')
        try:
            result = await service.hybrid('account', {'hits': []}, '查询', ['chat'])
            assert result['retrievalMode'] == ('keyword' if changed else 'hybrid')
            assert len(calls) == (0 if changed else 1)
        finally:
            await service.stop()
            service.store.close()
    asyncio.run(run())


def test_key_rotation_uses_latest_key_for_same_service(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response([[1., 0.]]))
    mock_clients(monkeypatch, handler)
    async def run():
        service = service_fixture(tmp_path, monkeypatch)
        cfg = initial_config()
        cfg['remote_api_key'] = 'rotated-key'
        service.store.put('config', cfg, id='account', account='account')
        try:
            result = await service.hybrid('account', {'hits': []}, '查询', ['chat'])
            assert result['retrievalMode'] == 'hybrid'
            assert calls[-1].headers['Authorization'] == 'Bearer rotated-key'
        finally:
            await service.stop()
            service.store.close()
    asyncio.run(run())


@pytest.mark.parametrize('content', [b'{}', b'{broken', b'{"error":"unavailable"}', b'\xff'])
def test_invalid_tokenizer_falls_back_without_poisoning_cache(tmp_path, monkeypatch, content):
    mock_clients(monkeypatch, lambda request: httpx.Response(200, content=content))
    async def run():
        service = service_fixture(tmp_path, monkeypatch)
        try:
            assert await service.ensure_tokenizer(configured_spec(initial_config()), tmp_path / 'tokenizers') is None
            assert not list((tmp_path / 'tokenizers').rglob('tokenizer.json'))
            assert not list((tmp_path / 'tokenizers').rglob('*.part'))
        finally:
            service.store.close()
    asyncio.run(run())


def test_corrupt_cached_tokenizer_is_replaced_and_models_are_isolated(tmp_path, monkeypatch):
    calls = []
    content = Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).to_str().encode()
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=content)
    mock_clients(monkeypatch, handler)
    async def run():
        service = service_fixture(tmp_path, monkeypatch)
        root = tmp_path / 'tokenizers'
        spec = configured_spec(initial_config())
        path = root / remote_identity(spec) / 'tokenizer.json'
        path.parent.mkdir(parents=True)
        path.write_text('{}', encoding='utf-8')
        try:
            assert await service.ensure_tokenizer(spec, root) == path
            Tokenizer.from_file(str(path))
            assert await service.ensure_tokenizer(spec, root) == path
            assert len(calls) == 1
            other = {**spec, 'model': 'another-model'}
            other_path = await service.ensure_tokenizer(other, root)
            assert other_path != path and len(calls) == 2
        finally:
            service.store.close()
    asyncio.run(run())
