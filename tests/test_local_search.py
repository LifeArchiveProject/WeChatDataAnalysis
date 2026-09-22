"""本地检索的权限、事务恢复和融合排序回归。"""
import asyncio
import json
from pathlib import Path
import pytest

from wechat_decrypt_tool.local_search.index import SemanticIndex, make_chunks, fuse
from wechat_decrypt_tool.local_search.catalog import model_spec, verify_model
from wechat_decrypt_tool.local_search.service import LocalSearch
from wechat_decrypt_tool.local_search.inference import InferenceFailure, LocalInference
from wechat_decrypt_tool.routers.local_search import Settings

def message(id, text='下周二才能交付', username='allowed', timestamp=100, sender='alice'):
    return dict(source=id,anchor=id,identity=id,username=username,time=timestamp,sender=sender,sender_id=sender,
                kind='text',text=text,media={'id':id,'senderUsername':sender})

def test_filter_before_return_and_same_second(tmp_path):
    index=SemanticIndex(tmp_path/'index.sqlite3')
    messages=[message('a'),message('b',username='other'),message('c',sender='bob'),message('d',timestamp=200)]
    chunks=[{'text':m['text'],'sources':[m['source']],'username':m['username']} for m in messages]
    index.commit('g',messages,chunks,[[1.,0.]]*4,{'id':'job','offset':4})
    result=index.search('g',[1.,0.],['allowed'],100,100,'alice',['text'])
    assert [r['message']['source'] for r in result]==['a']
    assert index.progress('job')['offset']==4
    assert not index.search('different',[1.,0.],['allowed'])

@pytest.mark.parametrize('sender,kinds,start,end', [
    (None, None, 0, 1000), ('alice', ['text'], 108, 124),
    ('missing', None, 0, 1000), (None, None, 500, 600),
])
def test_chunk_recall_matches_exhaustive_message_ranking(tmp_path, sender, kinds, start, end):
    import sqlite_vec
    index = SemanticIndex(tmp_path / 'index.sqlite3')
    messages = [message(f'm{i:03}', timestamp=100 + i % 31,
                        sender='alice' if i % 3 else 'bob',
                        username='allowed' if i % 7 else 'other') for i in range(180)]
    chunks, vectors = [], []
    for i, m in enumerate(messages):
        neighbors = [v['source'] for v in messages[max(0, i-2):i+1] if v['username'] == m['username']]
        chunks.append({'text': str(i), 'sources': neighbors, 'username': m['username']})
        # 大量等距离及重叠片段，最近原消息可能出现在后续批次。
        vectors.append([1., 0.] if i % 5 else [0., 1.])
    index.commit('g', messages, chunks, vectors, {'id': 'j'})
    index.commit('other-generation', [message('m001', timestamp=999)],
                 [{'text': 'other', 'sources': ['m001'], 'username': 'allowed'}], [[1., 0.]], {'id': 'old'})
    clauses = ['m.generation=?', 'm.username=?', 'm.created>=?', 'm.created<=?']
    params = ['g', 'allowed', start, end]
    if sender:
        clauses.append('m.sender=?'); params.append(sender)
    if kinds:
        clauses.append('m.kind=?'); params.append(kinds[0])
    with index.connection() as db:
        expected = db.execute('SELECT m.source,MIN(vec_distance_cosine(c.vector,?)) AS distance FROM messages m'
            ' JOIN members x ON x.source=m.source JOIN chunks c ON c.id=x.chunk AND c.generation=m.generation'
            ' WHERE ' + ' AND '.join(clauses) + ' GROUP BY m.source ORDER BY distance,m.created DESC,m.source LIMIT 17',
            [sqlite_vec.serialize_float32([1., 0.]), *params]).fetchall()
    actual = index.search('g', [1., 0.], ['allowed'], start, end, sender, kinds, 17)
    assert [(v['message']['source'], v['distance']) for v in actual] == [(r['source'], r['distance']) for r in expected]


def test_commit_is_atomic(tmp_path):
    index=SemanticIndex(tmp_path/'index.sqlite3')
    with pytest.raises(Exception):
        index.commit('g',[message('a')],[{'text':'x','sources':['a'],'username':'allowed'}],[['invalid']],{'id':'job','offset':1})
    assert index.progress('job') is None
    with index.connection() as db: assert db.execute('select count(*) from messages').fetchone()[0]==0


def test_cancel_large_commit_rolls_back_messages_and_progress(tmp_path):
    index = SemanticIndex(tmp_path / 'index.sqlite3')
    checks = 0
    def checkpoint():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise InferenceFailure('任务已暂停', 'cancelled')
    with pytest.raises(InferenceFailure):
        index.commit('g', [message(str(i)) for i in range(2000)], [], [], {'id': 'job', 'offset': 2000}, checkpoint)
    assert index.progress('job') is None
    with index.connection() as db:
        assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 0

def test_index_generations_and_clearing(tmp_path):
    index=SemanticIndex(tmp_path/'index.sqlite3')
    for generation in ('old','new'):
        index.commit(generation,[message(generation)],[{'text':'x','sources':[generation],'username':'allowed'}],[[1.,0.]],{'id':generation})
    index.clear('new')
    assert not index.search('old',[1.,0.],['allowed'])
    assert index.search('new',[1.,0.],['allowed'])
    index.clear()
    assert not index.search('new',[1.,0.],['allowed'])

def test_fusion_dedup_and_matching_metadata():
    keyword=[{'id':'a','username':'u'},{'id':'b','username':'u'}]
    semantic=[{'id':'b','username':'u'},{'id':'c','username':'u'}]
    result=fuse(keyword,semantic)
    assert result[0]['id']=='b'
    assert result[0]['matchMethods']==['keyword','semantic']
    assert len(result)==3

def test_catalog_pinned_and_hashed():
    from wechat_decrypt_tool.local_search.catalog import CATALOG
    assert len(CATALOG)==3
    for model in CATALOG:
        assert len(model['revision'])==40
        assert all(len(f['sha256'])==64 and f['size']>0 for f in model['files'])
        assert [f['path'] for f in model['files'] if f['path'].endswith('.onnx')]==['onnx/model.onnx']

def test_model_corruption_detected(tmp_path):
    (tmp_path/'test').write_bytes(b'wrong')
    with pytest.raises(ValueError): verify_model(tmp_path,{'files':[{'path':'test','size':5,'sha256':'0'*64}]})
    with pytest.raises(ValueError): model_spec('../escape')

def test_settings_validation():
    with pytest.raises(ValueError): Settings(start=200,end=100)
    with pytest.raises(ValueError): Settings(device='amd')
    assert Settings(usernames=['a','a',' b ']).usernames==['a','b']
    assert Settings().read_batch_size == 0
    assert Settings(read_batch_size=2000).read_batch_size == 2000
    with pytest.raises(ValueError): Settings(read_batch_size=100000)

class FakeEngine:
    def __init__(self):
        import threading
        self.lock=threading.RLock();self.status={'actual_device':'cpu'};self.key=None
        self.gpu_root=None;self.gpu_failed=False;self.last_used=0;self.calls=0
    def encode(self,*args,**kwargs):
        self.calls+=1
        return [[1.,0.] for _ in args[2]]
    def close(self): pass

def test_disabled_never_calls_model(tmp_path):
    async def run():
        engine=FakeEngine(); service=LocalSearch(tmp_path/'state',tmp_path/'models',engine=engine)
        result=await service.hybrid('account',{'hits':[]},'q',['allowed'])
        assert result['retrievalMode']=='keyword'
        assert engine.calls==0
        await service.stop()
    asyncio.run(run())

def test_scope_revocation_immediate_and_pagination(tmp_path):
    async def run():
        engine=FakeEngine(); service=LocalSearch(tmp_path/'state',tmp_path/'models',engine=engine)
        cfg={'account':'a','enabled':True,'model':'bge-small-zh','days':0,'usernames':['allowed'], 'revision':1,
             'active':{'model':'bge-small-zh','generation':'g','usernames':['allowed','other'],'start':0,'end':999,'updated':1}}
        service.store.put('config',cfg,id='a',account='a')
        index=service.index('a')
        msgs=[message('a'),message('b'),message('secret',username='other')]
        index.commit('g',msgs,[{'text':m['text'],'sources':[m['source']],'username':m['username']} for m in msgs],[[1.,0.]]*3,{'id':'job'})
        result=await service.hybrid('a',{'hits':[]},'q',['allowed','other'],limit=1)
        assert result['retrievalMode']=='hybrid'
        assert result['total']==2
        second=await service.hybrid('a',{'hits':[]},'q',['allowed','other'],limit=1,offset=1,ticket=result['searchTicket'])
        assert result['hits'][0]['id']!=second['hits'][0]['id']
        assert engine.calls==1
        denied=await service.hybrid('different',{'hits':[]},'q',['allowed'],ticket=result['searchTicket'])
        assert denied['retrievalMode']=='keyword'
        await service.stop()
    asyncio.run(run())


def test_exact_message_precedes_neighbors_with_shared_vector(tmp_path):
    async def run():
        service = LocalSearch(tmp_path/'state', tmp_path/'models', engine=FakeEngine())
        service.store.put('config', {'enabled': True, 'model': 'bge-small-zh', 'days': 0, 'usernames': ['allowed'],
            'active': {'model': 'bge-small-zh', 'generation': 'g', 'usernames': ['allowed'], 'start': 0, 'end': 999, 'updated': 1}}, id='a', account='a')
        target = message('target', '周五晚上七点去吃饭', timestamp=100)
        neighbors = [message(str(i), '相邻消息', timestamp=101+i) for i in range(25)]
        messages = [target, *neighbors]
        service.index('a').commit('g', messages, [{'text': '片段', 'sources': [m['source'] for m in messages], 'username': 'allowed'}], [[1., 0.]], {'id': 'j'})
        result = await service.hybrid('a', {'hits': []}, target['text'], ['allowed'], limit=10)
        assert result['retrievalMode'] == 'hybrid'
        assert result['hits'][0]['id'] == 'target'
        assert result['hits'][0]['matchMethods'] == ['keyword', 'semantic']
        await service.stop()
    asyncio.run(run())

def test_partial_index_literal_hit_survives_vector_candidate_limit(tmp_path):
    async def run():
        service = LocalSearch(tmp_path/'state', tmp_path/'models', engine=FakeEngine())
        service.store.put('config', {'enabled': True, 'model': 'bge-small-zh', 'days': 0, 'usernames': ['allowed'],
            'active': {'model': 'bge-small-zh', 'generation': 'g', 'usernames': ['allowed'], 'start': 0,
                       'end': 999, 'updated': 1, 'partial': True}}, id='a', account='a')
        target = message('target', '7-21惨案', timestamp=100)
        neighbors = [message(str(i), '打球聊天', timestamp=101+i) for i in range(250)]
        index = service.index('a')
        index.commit('g', [target, *neighbors],
                     [{'text': m['text'], 'sources': [m['source']], 'username': 'allowed'} for m in [target, *neighbors]],
                     [[0.,1.], *([[1.,0.]] * 250)], {'id': 'j'})
        assert not any(r['message']['source'] == 'target' for r in index.search('g', [1.,0.], ['allowed']))
        result = await service.hybrid('a', {'hits': []}, '7-21惨案', ['allowed'], limit=10)
        assert result['hits'][0]['id'] == 'target'
        assert result['hits'][0]['matchMethods'] == ['keyword']
        assert result['coverage']['partial'] is True
        await service.stop()
    asyncio.run(run())


@pytest.mark.parametrize('extra', [
    {'quoteTitle': '甲', 'quoteContent': '明晚讨论'},
    {'title': '附件标题', 'voiceTranscript': '转写文字'},
])
def test_index_hit_returns_canonical_ai_text_without_appending_metadata_twice(tmp_path, extra):
    from wechat_decrypt_tool.ai.agent_tools import normalize
    async def run():
        service = LocalSearch(tmp_path/'state', tmp_path/'models', engine=FakeEngine())
        service.store.put('config', {'enabled': True, 'model': 'bge-small-zh', 'days': 0, 'usernames': ['allowed'],
            'active': {'model': 'bge-small-zh', 'generation': 'g', 'usernames': ['allowed'], 'start': 0,
                       'end': 999, 'updated': 1}}, id='a', account='a')
        raw = {'id': 'db:table:3', 'username': 'allowed', 'content': '原始正文', 'createTime': 100, **extra}
        target = normalize('a', 'allowed', raw)
        service.index('a').commit('g', [target], [{'text': target['text'], 'sources': [target['source']],
            'username': 'allowed'}], [[1., 0.]], {'id': 'j'})
        result = await service.hybrid('a', {'hits': []}, '原始正文', ['allowed'], limit=10)
        hit = result['hits'][0]
        restored = normalize('a', 'allowed', hit)
        assert restored['text'] == target['text']
        assert restored['source'] == target['source']
        assert all(hit[key] == value for key, value in extra.items())
        # 搜索票据续页仍走同一格式，不依赖是否再次调用向量模型。
        cached = await service.hybrid('a', {'hits': []}, '原始正文', ['allowed'], ticket=result['searchTicket'])
        assert normalize('a', 'allowed', cached['hits'][0])['text'] == target['text']
        await service.stop()
    asyncio.run(run())


def test_literal_search_filters_committed_raw_messages_without_vectors(tmp_path):
    index = SemanticIndex(tmp_path/'index.sqlite3')
    index.commit('g', [message('a', 'ÄBC 100%_报价'), message('other', 'ÄBC 100%_报价', username='other'),
                       message('sender', 'ÄBC 100%_报价', sender='bob'),
                       message('later', 'ÄBC 100%_报价', timestamp=101), message('wildcard', 'ÄBC 1000报价')],
                 [], [], {'id': 'j'})
    assert [m['source'] for m in index.keyword('g', 'äbc 100%_', ['allowed'], 100, 100, 'alice', ['text'])] == ['a']
    assert index.keyword('old', '报价', ['allowed']) == []
    assert index.keyword('g', "' OR 1=1 --", ['allowed']) == []


def test_literal_results_survive_model_failure_and_remain_paged(tmp_path, monkeypatch):
    async def run():
        service = LocalSearch(tmp_path/'state', tmp_path/'models', engine=FakeEngine())
        service.store.put('config', {'enabled': True, 'model': 'bge-small-zh', 'days': 0, 'usernames': ['allowed'],
            'active': {'model': 'bge-small-zh', 'generation': 'g', 'usernames': ['allowed'], 'start': 0,
                       'end': 999, 'updated': 1, 'partial': True}}, id='a', account='a')
        service.index('a').commit('g', [message(str(i), '报价') for i in range(3)], [], [], {'id': 'j'})
        def unavailable(*args):
            raise InferenceFailure('模型暂不可用', 'runtime')
        monkeypatch.setattr(service.engine, 'encode', unavailable)
        first = await service.hybrid('a', {'hits': []}, '报价', ['allowed'], limit=1)
        second = await service.hybrid('a', {'hits': []}, '报价', ['allowed'], limit=1, offset=1)
        assert first['retrievalMode'] == 'keyword' and first['total'] == 3
        assert len(first['hits']) == len(second['hits']) == 1
        assert first['hits'][0]['id'] != second['hits'][0]['id']
        assert first['hasMore'] is True
        old_page = await service.hybrid('a', {'hits': [{'id': 'old-page', 'username': 'allowed'}], 'total': 11},
                                        '没有新索引命中', ['allowed'], limit=1, offset=10)
        assert old_page['hits'][0]['id'] == 'old-page'
        await service.stop()
    asyncio.run(run())


def test_gpu_failure_falls_back_without_changing_preference(monkeypatch):
    monkeypatch.setattr('wechat_decrypt_tool.local_search.inference.sys.platform','win32')
    monkeypatch.setattr(Path,'is_file',lambda _:True)
    engine=LocalInference(gpu_root='gpu')
    class Process:
        def start(self): pass
        def is_alive(self): return False
        def join(self,timeout=None): pass
    class Pipe:
        def close(self): pass
        def send(self,request): pass
    class Context:
        def Pipe(self): return Pipe(),Pipe()
        def Process(self,**kwargs): return Process()
    monkeypatch.setattr('wechat_decrypt_tool.local_search.inference.mp.get_context',lambda _:Context())
    responses=[InferenceFailure('GPU error','gpu'),{'ready':True},{'vectors':[[1.,0.]]}]
    def receive(*args):
        value=responses.pop(0)
        if isinstance(value,Exception): raise value
        return value
    monkeypatch.setattr(engine,'_receive',receive)
    assert engine.encode('model',model_spec('bge-small-zh'),['text'],'cuda')==[[1.,0.]]
    assert engine.status['actual_device']=='cpu' and engine.gpu_failed
    engine.close()

def test_cancel_does_not_retry_cpu(monkeypatch):
    monkeypatch.setattr('wechat_decrypt_tool.local_search.inference.sys.platform','win32')
    monkeypatch.setattr(Path,'is_file',lambda _:True)
    engine=LocalInference(gpu_root='gpu')
    engine.key=('root',model_spec('bge-small-zh')['revision'],'cuda',0)
    class Pipe:
        def send(self,request): pass
        def close(self): pass
    engine.pipe=Pipe()
    def receive(*args): raise InferenceFailure('cancel','cancelled')
    monkeypatch.setattr(engine,'_receive',receive)
    with pytest.raises(InferenceFailure,match='cancel'): engine.encode('root',model_spec('bge-small-zh'),['text'],'cuda')
    assert not engine.gpu_failed

def test_edited_message_keeps_unchanged_chunk_neighbors(tmp_path):
    index=SemanticIndex(tmp_path/'index.sqlite3')
    a,b=message('a'),message('b','补充报价明天确认')
    index.commit('g',[a,b],[{'text':'原片段','sources':['a','b'],'username':'allowed'}],[[1.,0.]],{'id':'one'})
    changed=index.affected_messages('g',[{**a,'text':'报价已确认'}])
    assert len(changed)==2
    index.commit('g',changed,[{'text':'新片段','sources':['a','b'],'username':'allowed'}],[[0.,1.]],{'id':'two'})
    assert {r['message']['source'] for r in index.search('g',[0.,1.],['allowed'])}=={'a','b'}

def test_short_vector_batch_never_advances_progress(tmp_path):
    index=SemanticIndex(tmp_path/'index.sqlite3')
    with pytest.raises(ValueError):
        index.commit('g',[message('a')],[{'text':'a','sources':['a'],'username':'allowed'}],[],{'id':'one'})
    assert index.progress('one') is None

def test_index_failure_resume_and_unchanged_update(tmp_path,monkeypatch):
    from tokenizers import Tokenizer,models,pre_tokenizers
    from wechat_decrypt_tool.local_search.catalog import model_dir
    async def run():
        calls=[];fail=[True]
        def reader(account,username,start,end,offset):
            calls.append(offset)
            if offset==2 and fail[0]:
                fail[0]=False
                raise OSError('数据源暂不可用')
            return {'messages':[message(str(i),'hello '+str(i)) for i in range(offset,min(6,offset+2))],
                    'name':'示例聊天','has_more':offset+2<6,'source':'snapshot'}
        service=LocalSearch(tmp_path/'state',tmp_path/'models',reader=reader,engine=FakeEngine())
        root=model_dir(service.downloads.root,'bge-small-zh');root.mkdir(parents=True)
        tokenizer=Tokenizer(models.WordLevel({'[UNK]':0,'hello':1},unk_token='[UNK]'))
        tokenizer.pre_tokenizer=pre_tokenizers.Whitespace();tokenizer.save(str(root/'tokenizer.json'))
        monkeypatch.setattr(service.downloads,'available',lambda _:True)
        monkeypatch.setattr(service,'enrichment_version',lambda _:[])
        await service.configure('a',{'enabled':True,'model':'bge-small-zh','days':0,'end':1000,'usernames':['allowed']})
        job=await service.build('a');await service.jobs[job['id']]
        # 统计未完成不能提前建索引；统计本身的分页断点可继续。
        assert job['status']=='error' and job['processed']==0
        assert service.index('a').progress(job['id']) is None
        assert service.message_plan(job).segment(0)['offset']==2
        resumed=await service.resume('a',job['id']);await service.jobs[job['id']]
        assert resumed['status']=='done' and resumed['processed']==6
        assert calls==[0,2,2,4]
        encoded=service.engine.calls
        second=await service.build('a');await service.jobs[second['id']]
        assert second['status']=='done' and second['embedded']==0
        assert second['unchanged'] == 6
        assert second['index_stats']['messages'] == 6
        assert second['index_stats']['chunks'] > 0
        assert service.status('a')['index_stats'] == second['index_stats']
        assert service.engine.calls==encoded
        await service.stop()
    asyncio.run(run())

def test_model_switch_keeps_previous_generation_until_success(tmp_path):
    async def run():
        service=LocalSearch(tmp_path/'state',tmp_path/'models',engine=FakeEngine())
        cfg={'enabled':True,'model':'bge-small-zh','usernames':['allowed'],'active':{'model':'bge-small-zh','generation':'old'}}
        service.store.put('config',cfg,id='a',account='a')
        service.downloads.available=lambda _:True
        new=await service.configure('a',{'model':'bge-base-zh'})
        assert new['active']['generation']=='old'
        assert new['active']['model']=='bge-small-zh'
        await service.stop()
    asyncio.run(run())


@pytest.mark.parametrize('target_model,force', [('bge-base-zh', False), ('bge-small-zh', True)])
def test_model_switch_and_forced_rebuild_recompute_all_vectors(tmp_path, monkeypatch, target_model, force):
    from tokenizers import Tokenizer, models
    from wechat_decrypt_tool.local_search.catalog import model_dir

    async def run():
        reads, encoded = [], []
        fail = False
        def reader(account, username, start, end, offset):
            reads.append((start, offset))
            return {'messages': [message('history', timestamp=100), message('latest', timestamp=1900)],
                    'has_more': False, 'name': username}
        engine = FakeEngine()
        def encode(root, spec, texts, *args):
            nonlocal fail
            if fail:
                fail = False
                raise RuntimeError('模拟新索引推理失败')
            encoded.append((root, len(texts)))
            return [[1., 0.] for _ in texts]
        monkeypatch.setattr(engine, 'encode', encode)
        service = LocalSearch(tmp_path/'state', tmp_path/'models', reader=reader, engine=engine)
        for name in {'bge-small-zh', target_model}:
            root = model_dir(service.downloads.root, name)
            root.mkdir(parents=True)
            Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root/'tokenizer.json'))
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        await service.configure('a', {'enabled': True, 'model': 'bge-small-zh', 'start': 0,
                                      'end': 2000, 'days': 0, 'usernames': ['allowed']})
        first = await service.build('a')
        await service.jobs[first['id']]
        assert first['status'] == 'done' and first['embedded'] > 0
        await service.configure('a', {'model': target_model})
        fail = True
        replacement = await service.build('a', rebuild=force)
        await service.jobs[replacement['id']]
        assert replacement['status'] == 'error'
        assert replacement['generation'] != first['generation']
        assert service.config('a')['active']['generation'] == first['generation']
        assert service.index('a').stats(first['generation'])['messages'] == 2
        reads.clear()
        encoded.clear()
        resumed = await service.resume('a', replacement['id'])
        await service.jobs[resumed['id']]
        assert resumed['status'] == 'done' and resumed['unchanged'] == 0
        # 推理失败后直接使用原清单，不重读源消息或更改总量。
        assert reads == []
        assert sum(count for _, count in encoded) == first['embedded'] == resumed['embedded']
        assert all(root == model_dir(service.downloads.root, target_model) for root, _ in encoded)
        assert service.config('a')['active']['generation'] == resumed['generation']
        assert service.index('a').stats(first['generation']) == {'messages': 0, 'chunks': 0}
        await service.stop()
    asyncio.run(run())


def test_manual_build_is_incremental_across_settings_and_scope_changes(tmp_path, monkeypatch):
    from tokenizers import Tokenizer, models
    from wechat_decrypt_tool.local_search.catalog import model_dir

    async def run():
        rows = [message('old', timestamp=100), message('recent', timestamp=9500)]
        reads = []
        def reader(account, username, start, end, offset):
            reads.append((username, start, end))
            return {'messages': [dict(m) for m in rows if m['username'] == username and start <= m['time'] <= end],
                    'name': username, 'has_more': False}
        service = LocalSearch(tmp_path/'state', tmp_path/'models', reader=reader, engine=FakeEngine())
        root = model_dir(service.downloads.root, 'bge-small-zh')
        root.mkdir(parents=True)
        Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root/'tokenizer.json'))
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        cfg = await service.configure('a', {'enabled': True, 'model': 'bge-small-zh', 'days': 0,
                                          'start': 0, 'end': 10000, 'usernames': ['allowed']})
        same = await service.configure('a', {'enabled': True})
        assert same['revision'] == cfg['revision']
        first = await service.build('a')
        await service.jobs[first['id']]
        assert first['status'] == 'done'
        rows.extend([message('late', timestamp=9500), message('new', timestamp=10500),
                     message('other-old', username='other', timestamp=100)])
        await service.configure('a', {'device': 'cpu', 'end': 11000, 'usernames': ['allowed', 'other']})
        reads.clear()
        second = await service.build('a')
        await service.jobs[second['id']]
        assert second['status'] == 'done' and second['mode'] == 'incremental'
        assert reads == [('allowed', 9400, 11000), ('other', 0, 11000)]
        assert second['unchanged'] == 1
        assert second['index_stats']['messages'] == 5
        assert second['generation'] == first['generation']
        await service.configure('a', {'start': 500, 'usernames': ['allowed']})
        await service.configure('a', {'start': 0, 'usernames': ['allowed', 'other']})
        reads.clear()
        restored = await service.build('a')
        await service.jobs[restored['id']]
        assert restored['status'] == 'done'
        assert reads == [('allowed', 0, 11000), ('other', 0, 11000)]
        assert restored['index_stats']['messages'] == 5
        await service.stop()
    asyncio.run(run())


def test_full_reconciliation_removes_missing_messages_and_rebuilds_neighbors(tmp_path, monkeypatch):
    from tokenizers import Tokenizer, models
    from wechat_decrypt_tool.local_search.catalog import model_dir

    async def run():
        rows = [message('kept', '继续保留'), message('deleted', '已经删除的秘密', timestamp=101)]
        warning = ['']

        def reader(account, username, start, end, offset):
            return {'messages': [dict(m) for m in rows if start <= m['time'] <= end],
                    'name': username, 'has_more': False, 'warning': warning[0]}
        service = LocalSearch(tmp_path/'state', tmp_path/'models', reader=reader, engine=FakeEngine())
        root = model_dir(service.downloads.root, 'bge-small-zh')
        root.mkdir(parents=True)
        Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root/'tokenizer.json'))
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        await service.configure('a', {'enabled': True, 'model': 'bge-small-zh', 'days': 0,
                                      'start': 0, 'end': 1000, 'usernames': ['allowed']})
        first = await service.build('a')
        await service.jobs[first['id']]
        assert first['status'] == 'done'
        assert service.index('a').keyword(first['generation'], '秘密', ['allowed'])

        rows.pop()
        warning[0] = '数据源暂时不完整'
        incomplete = await service.build('a', incremental=False)
        await service.jobs[incomplete['id']]
        assert incomplete['status'] == 'done'
        assert service.index('a').keyword(first['generation'], '秘密', ['allowed'])

        warning[0] = ''
        reconciled = await service.build('a', incremental=False)
        await service.jobs[reconciled['id']]
        index = service.index('a')
        assert reconciled['status'] == 'done' and reconciled['removed'] == 1
        assert index.keyword(first['generation'], '秘密', ['allowed']) == []
        assert index.stats(first['generation'])['messages'] == 1
        assert {r['message']['source'] for r in index.search(first['generation'], [1., 0.], ['allowed'])} == {'kept'}
        with index.connection() as db:
            assert db.execute("SELECT count(*) FROM members WHERE source='deleted'").fetchone()[0] == 0
        await service.stop()
    asyncio.run(run())


@pytest.mark.parametrize('change,expected_mode,expected_start', [
    ({}, 'incremental', 9400),
    ({'start': 200}, 'incremental', 0),
    ({'enrichment': [1]}, 'enrichment', 0),
    ({'reconciled': 0}, 'reconcile', 0),
    ({'model': 'e5-small'}, 'initial', 0),
])
def test_incremental_never_skips_uncovered_or_changed_history(tmp_path, monkeypatch, change, expected_mode, expected_start):
    import time
    async def run():
        service = LocalSearch(tmp_path/'state', tmp_path/'models', engine=FakeEngine())
        active = {'generation': 'g', 'model': 'bge-small-zh', 'start': 0, 'end': 10000,
                  'usernames': ['allowed'], 'enrichment': [], 'reconciled': time.time(), **change}
        service.store.put('config', {'enabled': True, 'model': 'bge-small-zh', 'start': 0,
                          'end': 11000, 'usernames': ['allowed'], 'active': active}, id='a', account='a')
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        async def no_run(job): pass
        monkeypatch.setattr(service, 'run', no_run)
        job = await service.build('a')
        await service.jobs[job['id']]
        assert job['mode'] == expected_mode
        assert job['read_starts']['allowed'] == expected_start
        rebuilt = await service.build('a', rebuild=True)
        await service.jobs[rebuilt['id']]
        assert rebuilt['mode'] == 'rebuild' and rebuilt['read_start'] == 0
        assert rebuilt['generation'] != active['generation']
        await service.stop()
    asyncio.run(run())

def test_api_account_isolation_and_local_only(tmp_path,monkeypatch):
    from fastapi import FastAPI
    import httpx
    from wechat_decrypt_tool.routers import local_search
    service=LocalSearch(tmp_path/'state',tmp_path/'models',engine=FakeEngine())
    monkeypatch.setattr(local_search,'get_local_search',lambda:service)
    monkeypatch.setattr(local_search,'account_name',lambda a:a)
    app=FastAPI();app.include_router(local_search.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://localhost') as client:
            assert (await client.put('/api/ai/local-search/settings?account=a',json={'enabled':True})).status_code==400
            saved=await client.put('/api/ai/local-search/settings?account=a',json={'usernames':['allowed'],'device':'cpu'})
            assert saved.status_code==200
            assert (await client.get('/api/ai/local-search/status?account=b')).json()['config']['usernames']==[]
            assert (await client.get('/api/ai/local-search/status',headers={'Origin':'https://evil.example'})).status_code==403
            assert (await client.post('/api/ai/local-search/gpu/import')).status_code==400
            assert (await client.post('/api/ai/local-search/models/unknown/download')).status_code==400
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('192.168.1.50',1)),base_url='http://localhost') as client:
            assert (await client.get('/api/ai/local-search/status')).status_code==403
        await service.stop()
    asyncio.run(run())

@pytest.mark.parametrize('category,attempts',[('rate_limit',5),('checksum',1),('missing',1),('access',1)])
def test_download_retry_budget_and_terminal_errors(tmp_path,monkeypatch,category,attempts):
    from wechat_decrypt_tool.local_search import downloads
    from wechat_decrypt_tool.ai.storage import AIStore
    class Pipe:
        def poll(self):return True
        def recv(self):return {'error':category,'wait':7}
        def close(self):pass
    class Process:
        def start(self):pass
        def join(self,timeout=None):pass
        def is_alive(self):return False
    class Context:
        def Pipe(self):return Pipe(),Pipe()
        def Process(self,**kwargs):return Process()
    waits=[]
    async def sleep(n):waits.append(n)
    monkeypatch.setattr(downloads.mp,'get_context',lambda _:Context())
    monkeypatch.setattr(downloads.asyncio,'sleep',sleep)
    async def run():
        manager=downloads.ModelDownloads(tmp_path/'models',AIStore(tmp_path/'state'),FakeEngine())
        job=await manager.start('bge-small-zh');await manager.tasks[job['id']]
        assert job['status']=='error' and job['attempt']==attempts
        assert waits==[7]*(attempts-1)
        await manager.stop()
    asyncio.run(run())

def test_offline_import_uses_same_hash_validation(tmp_path,monkeypatch):
    import hashlib
    from wechat_decrypt_tool.local_search import catalog,downloads
    from wechat_decrypt_tool.ai.storage import AIStore
    data=b'{}';spec={'id':'bge-small-zh','revision':'a'*40,'files':[{'path':'tokenizer.json','size':2,'sha256':hashlib.sha256(data).hexdigest()}]}
    monkeypatch.setattr(catalog,'CATALOG',[spec]);monkeypatch.setattr(downloads,'CATALOG',[spec])
    source=tmp_path/'offline';source.mkdir();(source/'tokenizer.json').write_bytes(data)
    async def run():
        manager=downloads.ModelDownloads(tmp_path/'models',AIStore(tmp_path/'state'),FakeEngine())
        await manager.import_model(spec['id'],source);await manager.tasks[spec['id']]
        assert manager.available(spec['id'])
        assert manager.store.get('download',spec['id'])['status']=='done'
        await manager.stop()
    asyncio.run(run())

def test_clear_disabled_index_releases_model_reference(tmp_path):
    async def run():
        service=LocalSearch(tmp_path/'state',tmp_path/'models',engine=FakeEngine())
        service.store.put('config',{'enabled':False,'model':'bge-small-zh'},id='a',account='a')
        await service.clear('a')
        assert service.config('a')['model'] is None
        assert service.status()['audit']==[]
        await service.stop()
    asyncio.run(run())

def test_pausing_queued_job_does_not_wait_for_other_account(tmp_path):
    async def run():
        service=LocalSearch(tmp_path/'state',tmp_path/'models',engine=FakeEngine())
        await service.queue_lock.acquire()
        job={'id':'queued','account':'a','status':'queued','config':service.config('a')}
        service.update(job)
        service.jobs['queued']=asyncio.create_task(service.run(job))
        await asyncio.wait_for(service.pause_account('a'),timeout=1)
        assert service.store.get('index_job','queued')['status']=='paused'
        service.queue_lock.release();await service.stop()
    asyncio.run(run())
