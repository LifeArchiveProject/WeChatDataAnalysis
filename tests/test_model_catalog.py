import asyncio
import json
import time

import httpx
import pytest

from wechat_decrypt_tool.ai.model_catalog import ModelCatalog
from wechat_decrypt_tool.ai.agent_budget import input_limit, output_limit
from wechat_decrypt_tool.ai.providers import ModelService
from wechat_decrypt_tool.ai.storage import AIStore


CATALOG = {'openai': {'id': 'openai', 'name': 'OpenAI', 'api': 'https://api.openai.com/v1', 'models': {
    'fixture-model': {'id': 'fixture-model', 'name': '目录模型', 'tool_call': False, 'reasoning': True,
        'structured_output': False, 'temperature': False, 'modalities': {'input': ['text', 'image'], 'output': ['text']},
        'limit': {'context': 128000, 'output': 16384}, 'cost': {'input': 0, 'output': 2.5}}}}}


def test_refresh_cache_offline_and_credential_isolation(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == 'https://models.dev/api.json'
        assert 'authorization' not in request.headers and 'x-api-key' not in request.headers
        return httpx.Response(200, json=CATALOG)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    catalog = ModelCatalog(tmp_path)
    async def run():
        await asyncio.gather(catalog.refresh(), catalog.refresh())
    asyncio.run(run())
    assert len(calls) == 1
    cached = ModelCatalog(tmp_path)
    assert cached.data == CATALOG
    assert cached.lookup({'provider':'openai', 'model':'fixture-model'})['cost']['input'] == 0
    def offline(request):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(offline), **kwargs))
    cached.checked_at = 0
    asyncio.run(cached.refresh())
    assert cached.data == CATALOG
    assert json.loads(cached.path.read_text(encoding='utf-8'))['data'] == CATALOG


def test_exact_matching_and_runtime_capabilities(tmp_path):
    models = ModelService(AIStore(tmp_path))
    models.metadata.data = CATALOG
    models.store.put('profile', {'provider':'custom', 'model':'fixture-model', 'base_url':'https://proxy.example/v1',
                               'vision':False, 'context_window':8192}, id='selected')
    resolved = models.resolve('selected', vision=True)
    assert resolved['vision'] is True and resolved['context_window'] == 128000
    assert resolved['model_metadata']['tool_call'] is False
    assert resolved['model_metadata']['logo_url'] == 'https://models.dev/logos/openai.svg'
    assert input_limit(resolved) == 111104
    assert output_limit(resolved) == 16384
    assert models.metadata.lookup({'provider':'custom','model':'fixture-model-preview'}) is None
    assert models.metadata.enrich({'provider':'custom','model':'unknown','context_window':64000})['context_window'] == 64000
    models.metadata.data = {**CATALOG, 'anthropic': CATALOG['openai']}
    assert models.metadata.lookup({'provider':'custom','model':'fixture-model'}) is None


def test_known_tool_capability_skips_unsupported_protocol(tmp_path):
    from langchain_core.messages import AIMessage, HumanMessage
    from wechat_decrypt_tool.ai.agent_model import AgentModel
    calls = []
    class Client:
        def bind_tools(self, *args, **kwargs):
            pytest.fail('不支持工具的模型不应尝试绑定工具')
        async def ainvoke(self, messages, **kwargs):
            calls.append(kwargs)
            assert 'JSON' in messages[-1].content
            assert 'response_format' not in kwargs
            return AIMessage(content='{"action":"clarify","question":"哪位联系人？"}')
    models = ModelService(AIStore(tmp_path))
    models.client = lambda profile: Client()
    profile = {'id':'test','model':'fixture-model','protocol':'openai',
               'model_metadata': {'tool_call':False, 'structured_output':False}}
    answer = asyncio.run(AgentModel(models).call(profile,[HumanMessage(content='查一下')],'account',decision=True))
    assert answer.action == 'clarify' and len(calls) == 1


def test_upstream_fields_override_catalog_and_survive_restart(tmp_path):
    from wechat_decrypt_tool.ai.providers import parse_model_catalog
    store = AIStore(tmp_path)
    models = ModelService(store)
    models.metadata.data = CATALOG
    profile = {'provider':'custom','model':'fixture-model','base_url':'https://proxy.example/v1','protocol':'openai'}
    items = parse_model_catalog({'data':[{'id':'fixture-model','context_length':64000,
        'architecture':{'input_modalities':['text']}, 'top_provider':{'max_completion_tokens':8192},
        'capabilities':{'tool_call':True}}]})
    models.metadata.remember(profile, items)
    metadata = models.metadata.automatic(profile)
    assert metadata['limit'] == {'context':64000,'output':8192}
    assert metadata['vision'] is False and metadata['tool_call'] is True
    assert metadata['reasoning'] is True
    assert metadata['field_sources']['limit.context'] == 'upstream'
    assert metadata['field_sources']['reasoning'] == 'models.dev'
    store.put('profile', profile, id='selected')
    restarted = ModelService(AIStore(tmp_path))
    assert restarted.resolve('selected')['context_window'] == 64000
    assert restarted.resolve('selected')['vision'] is False
    other = {**profile,'base_url':'https://another.example/v1'}
    assert restarted.metadata.automatic(other) is None
    models.metadata.remember(profile, [{'id':'fixture-model','vision':None}])
    assert models.metadata.automatic(profile)['limit']['context'] == 128000


def test_manual_overrides_take_priority_even_for_false_values(tmp_path):
    models = ModelService(AIStore(tmp_path))
    models.metadata.data = json.loads(json.dumps(CATALOG))
    profile = {'provider':'openai','model':'fixture-model','context_window':128000,'vision':True,
        'model_overrides':{'context_window':96000,'vision':False,'tool_call':True,'max_output_tokens':8000}}
    models.store.put('profile', profile, id='selected')
    effective = models.resolve('selected')
    assert effective['context_window'] == 96000 and effective['vision'] is False
    assert effective['model_metadata']['tool_call'] is True
    assert output_limit(effective) == 8000
    assert input_limit(effective) == 87488
    assert effective['automatic_metadata']['vision'] is True
    models.metadata.data['openai']['models']['fixture-model']['limit']['context'] = 200000
    assert models.resolve('selected')['context_window'] == 96000
    models.store.put('profile', {**profile,'model_overrides':{}}, id='selected')
    assert models.resolve('selected')['context_window'] == 200000
