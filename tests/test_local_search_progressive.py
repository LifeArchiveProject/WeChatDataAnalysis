"""渐进索引的读取顺序、可查询覆盖和前台优先级。"""
import asyncio
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from wechat_decrypt_tool.local_search.progressive import reading_segments
from wechat_decrypt_tool.local_search.progressive import committed_coverage, coverage_complete
from wechat_decrypt_tool.local_search.service import LocalSearch


@pytest.mark.parametrize('status', ['error', 'paused', 'done'])
def test_old_revision_cannot_block_new_global_index(tmp_path, monkeypatch, status):
    from unittest.mock import AsyncMock
    from wechat_decrypt_tool.ai.agent_tools import ChatTools
    async def run():
        service = LocalSearch(root=tmp_path)
        cfg = {**service.config('account'), 'enabled': True, 'agent_global': True, 'revision': 10,
               'model': 'bge-small-zh', 'usernames': ['room@chatroom'], 'start': 0, 'days': 0,
               'active': {'revision': 9, 'updated': time.time()}}
        service.store.put('config', cfg, id='account', account='account')
        service.store.put('index_job', {'id': 'old', 'account': 'account', 'status': status,
                                      'config': {**cfg, 'revision': 9, 'days': 30}}, id='old', account='account')
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(ChatTools, 'conversations', AsyncMock(return_value=[{'username': 'room@chatroom'}]))
        build = AsyncMock(return_value={'id': 'new'})
        monkeypatch.setattr(service, 'build', build)
        assert await service.ensure_global('account') == {'id': 'new'}
        build.assert_awaited_once_with('account')
        assert service.store.get('index_job', 'old')['status'] == status
        await service.stop()
    asyncio.run(run())


@pytest.mark.parametrize('status,global_config', [('paused', True), ('error', True), ('paused', False)])
def test_current_global_pause_or_error_is_not_automatically_resumed(tmp_path, monkeypatch, status, global_config):
    from unittest.mock import AsyncMock
    from wechat_decrypt_tool.ai.agent_tools import ChatTools
    async def run():
        service = LocalSearch(root=tmp_path)
        cfg = {**service.config('account'), 'enabled': True, 'agent_global': global_config, 'revision': 10,
               'model': 'bge-small-zh', 'usernames': ['room@chatroom']}
        service.store.put('config', cfg, id='account', account='account')
        service.store.put('index_job', {'id': 'current', 'account': 'account', 'status': status,
                                      'config': cfg}, id='current', account='account')
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        directory = AsyncMock(return_value=[{'username': 'new-room@chatroom'}])
        monkeypatch.setattr(ChatTools, 'conversations', directory)
        build = AsyncMock()
        monkeypatch.setattr(service, 'build', build)
        assert (await service.ensure_global('account'))['status'] == status
        directory.assert_not_awaited()
        build.assert_not_awaited()
        await service.stop()
    asyncio.run(run())


@pytest.mark.parametrize('global_config', [True, False])
def test_scheduler_starts_global_without_active_index_despite_old_error(tmp_path, monkeypatch, global_config):
    from unittest.mock import AsyncMock
    async def run():
        service = LocalSearch(root=tmp_path)
        cfg = {**service.config('account'), 'enabled': True, 'agent_global': global_config, 'revision': 10,
               'model': 'bge-small-zh'}
        service.store.put('config', cfg, id='account', account='account')
        service.store.put('index_job', {'id': 'old', 'status': 'error', 'config': {'revision': 9}}, id='old', account='account')
        ensure = AsyncMock()
        monkeypatch.setattr(service, 'ensure_global', ensure)
        ticks = 0
        async def tick(_):
            nonlocal ticks
            ticks += 1
            if ticks > 1:
                raise asyncio.CancelledError()
        monkeypatch.setattr(asyncio, 'sleep', tick)
        with pytest.raises(asyncio.CancelledError):
            await service.schedule()
        ensure.assert_awaited_once_with('account')
        await service.stop()
    asyncio.run(run())


def test_foreground_and_scheduler_create_one_index_task(tmp_path, monkeypatch):
    async def run():
        service = LocalSearch(root=tmp_path)
        cfg = {**service.config('account'), 'enabled': True, 'agent_global': True, 'revision': 1,
               'model': 'bge-small-zh', 'usernames': ['room@chatroom']}
        service.store.put('config', cfg, id='account', account='account')
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        release = asyncio.Event()
        async def pending(_):
            await release.wait()
        monkeypatch.setattr(service, 'run', pending)
        try:
            first, second = await asyncio.gather(service.build('account'), service.build('account'))
            assert first['id'] == second['id']
            assert len(service.jobs) == 1
        finally:
            release.set()
            await asyncio.gather(*service.jobs.values())
            await service.stop()
    asyncio.run(run())


def test_global_settings_resolve_account_catalog_and_ignore_query_filters(monkeypatch):
    from wechat_decrypt_tool.routers import local_search as router
    from wechat_decrypt_tool.ai.agent_tools import ChatTools
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    contacts = AsyncMock(return_value=[{'username': 'group@chatroom'}, {'username': 'friend'}])
    configure = AsyncMock(return_value={'ok': True})
    monkeypatch.setattr(router, 'account_name', lambda account: 'test-account')
    monkeypatch.setattr(ChatTools, 'conversations', contacts)
    monkeypatch.setattr(router, 'get_local_search', lambda: SimpleNamespace(configure=configure))
    body = router.Settings(agent_global=True, enabled=True, model='bge-small-zh',
                           usernames=['old-filter'], days=30, start=20, end=40, auto_update=False)
    asyncio.run(router.settings(body, 'test-account'))
    contacts.assert_awaited_once_with('test-account')
    account, values = configure.await_args.args
    assert account == 'test-account'
    assert values['usernames'] == ['group@chatroom', 'friend']
    assert (values['start'], values['end'], values['days'], values['auto_update']) == (0, None, 0, True)


def test_recent_chats_precede_older_history_without_boundary_overlap():
    segments = reading_segments(['a', 'b'], {'a': 0, 'b': 2}, 20, recent_seconds=5)
    assert [(s['username'], s['start'], s['end']) for s in segments] == [
        ('a', 15, 20), ('b', 15, 20), ('a', 0, 14), ('b', 2, 14)]
    for username, start in [('a', 0), ('b', 2)]:
        values = [n for s in segments if s['username'] == username for n in range(s['start'], s['end']+1)]
        assert sorted(values) == list(range(start, 21))


def test_partial_publication_exposes_only_committed_coverage(tmp_path):
    service = LocalSearch(root=tmp_path)
    cfg = {**service.config('a'), 'enabled': True, 'agent_global': True, 'revision': 1, 'model': 'bge-small-zh', 'usernames': ['a', 'b']}
    service.store.put('config', cfg, id='a')
    service.publish_partial({'account': 'a', 'config': cfg, 'generation': 'g', 'start': 0, 'end': 100,
                             'coverage': {'0': {'username': 'a', 'start': 90, 'end': 100, 'complete': False}}})
    active = service.config('a')['active']
    assert active['partial'] is True
    assert active['usernames'] == ['a']
    assert active['coverage']['0']['complete'] is False


def test_old_config_batch_cannot_publish_over_new_selection(tmp_path):
    service = LocalSearch(root=tmp_path)
    service.store.put('config', {'revision': 2, 'usernames': ['new']}, id='a')
    service.publish_partial({'account': 'a', 'config': {'revision': 1, 'agent_global': True}})
    assert 'active' not in service.config('a')


def test_index_yields_until_foreground_query_finishes(tmp_path):
    async def run():
        service = LocalSearch(root=tmp_path)
        service.foreground_queries = 1
        checks = []
        task = asyncio.create_task(service.yield_to_queries(lambda: checks.append(True)))
        await asyncio.sleep(.06)
        assert not task.done()
        service.foreground_queries = 0
        await asyncio.wait_for(task, 1)
        assert checks
    asyncio.run(run())


def test_foreground_context_is_nested_and_does_not_start_service(tmp_path, monkeypatch):
    from wechat_decrypt_tool.local_search import service as module
    monkeypatch.setattr(module, '_service', None)
    with module.prioritize_foreground():
        assert module._service is None
    index = LocalSearch(root=tmp_path)
    monkeypatch.setattr(module, '_service', index)
    with module.prioritize_foreground():
        assert index.foreground_queries == 1
        with pytest.raises(ValueError), module.prioritize_foreground():
            assert index.foreground_queries == 2
            raise ValueError('读取失败')
        assert index.foreground_queries == 1
    assert index.foreground_queries == 0


def test_foreground_blocks_index_before_first_raw_page(tmp_path, monkeypatch):
    """前台正在读原文时，后台不能先抢读一整页再等向量阶段让步。"""
    from tokenizers import Tokenizer, models
    from test_local_search import FakeEngine, message
    from wechat_decrypt_tool.local_search import service as module
    from wechat_decrypt_tool.local_search.catalog import model_dir
    async def run():
        read_calls = []
        def reader(*args):
            read_calls.append(True)
            return {'messages': [message('source')], 'has_more': False}
        index = LocalSearch(tmp_path / 'state', tmp_path / 'models', reader=reader, engine=FakeEngine())
        monkeypatch.setattr(module, '_service', index)
        root = model_dir(index.downloads.root, 'bge-small-zh')
        root.mkdir(parents=True)
        Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root / 'tokenizer.json'))
        monkeypatch.setattr(index.downloads, 'available', lambda _: True)
        monkeypatch.setattr(index, 'enrichment_version', lambda _: [])
        await index.configure('a', {'enabled': True, 'model': 'bge-small-zh', 'start': 0, 'end': 200,
                                    'usernames': ['allowed']})
        reached = asyncio.Event()
        original_yield = index.yield_to_queries
        async def observed_yield(check):
            reached.set()
            await original_yield(check)
        monkeypatch.setattr(index, 'yield_to_queries', observed_yield)
        try:
            with module.prioritize_foreground():
                job = await index.build('a')
                await asyncio.wait_for(reached.wait(), 3)
                assert not read_calls and not index.jobs[job['id']].done()
            await asyncio.wait_for(index.jobs[job['id']], 5)
            assert read_calls == [True] and job['status'] == 'done'
        finally:
            await index.stop()
    asyncio.run(run())


def test_incremental_batch_keeps_other_chat_searchable(tmp_path):
    """增量第一批只更新甲会话时，乙会话旧向量仍应可检索。"""
    from test_local_search import FakeEngine, message

    async def run():
        service = LocalSearch(tmp_path, engine=FakeEngine())
        cfg = {**service.config('account'), 'enabled': True, 'agent_global': True,
               'model': 'bge-small-zh', 'days': 0, 'revision': 1, 'usernames': ['a', 'b'],
               'active': {'generation': 'g', 'model': 'bge-small-zh', 'start': 0, 'end': 100,
                          'updated': 1, 'usernames': ['a', 'b'], 'partial': False,
                          'coverage': {u: {'username': u, 'start': 0, 'end': 100, 'complete': True}
                                       for u in ['a', 'b']}}}
        service.store.put('config', cfg, id='account', account='account')
        item = message('old-b', username='b', timestamp=50)
        service.index('account').commit('g', [item],
            [{'text': item['text'], 'sources': [item['source']], 'username': 'b'}], [[1., 0.]], {'id': 'old'})
        service.publish_partial({'account': 'account', 'config': cfg, 'generation': 'g', 'start': 0, 'end': 150,
            'coverage': {'0': {'username': 'a', 'start': 90, 'end': 150, 'complete': False}}})
        result = await service.hybrid('account', {'hits': []}, '交付', ['b'])
        assert result['retrievalMode'] == 'hybrid'
        assert [hit['id'] for hit in result['hits']] == ['old-b']
        ranges = list(service.config('account')['active']['coverage'].values())
        assert any(r['username'] == 'b' and r['start'] == 0 and r['end'] == 100 and r['complete'] for r in ranges)
        assert not any(r['username'] == 'a' and r['end'] == 150 and r['complete'] for r in ranges)
        await service.stop()
    asyncio.run(run())


def test_coverage_merges_updates_without_filling_holes_or_crossing_generations():
    job = {'generation': 'g', 'start': 0, 'end': 150,
           'config': {'usernames': ['a'], 'active': {'generation': 'g', 'usernames': ['a'], 'coverage': {
               'old': {'username': 'a', 'start': 0, 'end': 100, 'complete': True}}}},
           'coverage': {'new': {'username': 'a', 'start': 90, 'end': 150, 'complete': True}}}
    for _ in range(20):
        ranges = committed_coverage(job)
        assert len(ranges) == 1
        assert coverage_complete(ranges, ['a'], 0, 150)
        job['config']['active']['coverage'] = ranges
    job['generation'] = 'rebuild'
    ranges = committed_coverage(job)
    assert not coverage_complete(ranges, ['a'], 0, 150)
    job['coverage']['new']['start'] = 101
    job['config']['active']['generation'] = 'rebuild'
    job['config']['active']['coverage']['0']['end'] = 99
    ranges = committed_coverage(job)
    assert not coverage_complete(ranges, ['a'], 0, 150), '未读的第 100 秒不能被相邻时间段填平'
    job['start'] = 101
    assert coverage_complete(committed_coverage(job), ['a'], 101, 150)


def test_pruned_ranges_cannot_reappear_as_complete_when_settings_expand():
    job = {'generation': 'g', 'start': 0, 'end': 150, 'coverage': {},
           'config': {'usernames': ['a', 'b'], 'active': {'generation': 'g', 'usernames': ['a'],
               'start': 50, 'end': 100, 'coverage': {
                   u: {'username': u, 'start': 0, 'end': 150, 'complete': True} for u in ['a', 'b']}}}}
    ranges = committed_coverage(job)
    assert {(r['username'], r['start'], r['end']) for r in ranges.values()} == {('a', 50, 100)}
    assert not coverage_complete(ranges, ['a', 'b'], 0, 150)


def test_global_incremental_completion_retains_full_coverage_after_reopen(tmp_path, monkeypatch):
    from tokenizers import Tokenizer, models
    from test_local_search import FakeEngine, message
    from wechat_decrypt_tool.local_search.catalog import model_dir

    async def run():
        rows = [message('old', timestamp=100), message('recent', timestamp=9500)]
        def reader(account, username, start, end, offset):
            return {'messages': [dict(m) for m in rows if start <= m['time'] <= end],
                    'name': username, 'has_more': False}
        service = LocalSearch(tmp_path / 'state', tmp_path / 'models', reader=reader, engine=FakeEngine())
        root = model_dir(service.downloads.root, 'bge-small-zh')
        root.mkdir(parents=True)
        Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root / 'tokenizer.json'))
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        await service.configure('a', {'enabled': True, 'agent_global': True, 'model': 'bge-small-zh',
                                     'start': 0, 'end': 10000, 'usernames': ['allowed']})
        first = await service.build('a')
        await service.jobs[first['id']]
        assert first['status'] == 'done'
        rows.append(message('new', timestamp=10500))
        await service.configure('a', {'end': 11000})
        updated = await service.build('a')
        await service.jobs[updated['id']]
        assert updated['status'] == 'done' and updated['read_starts'] == {'allowed': 9400}
        assert updated['index_stats']['messages'] == 3
        await service.stop()
        restored = LocalSearch(tmp_path / 'state', tmp_path / 'models', engine=FakeEngine())
        active = restored.config('a')['active']
        assert active['partial'] is False
        assert coverage_complete(active['coverage'], ['allowed'], 0, 11000)
        assert restored.index('a').search(active['generation'], [1., 0.], ['allowed'], 0, 100)[0]['message']['source'] == 'old'
        monkeypatch.setattr(restored.downloads, 'available', lambda _: True)
        await restored.configure('a', {'start': 500})
        assert not restored.index('a').search(active['generation'], [1., 0.], ['allowed'], 0, 100)
        await restored.configure('a', {'start': 0})
        assert not coverage_complete(restored.config('a')['active']['coverage'], ['allowed'], 0, 11000)
        await restored.stop()
    asyncio.run(run())
