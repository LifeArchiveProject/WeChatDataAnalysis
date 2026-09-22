"""固定本轮总量、源数据变化、暂停恢复与临时快照回收回归。"""
import asyncio
import copy
from pathlib import Path

import pytest
from tokenizers import Tokenizer, models

from test_local_search import FakeEngine, message
from wechat_decrypt_tool.local_search.service import LocalSearch
from wechat_decrypt_tool.local_search.frozen import FrozenMessages
from wechat_decrypt_tool.local_search.index import SemanticIndex
from wechat_decrypt_tool.local_search.inference import InferenceFailure
from wechat_decrypt_tool.local_search.catalog import model_dir


def snapshot(tmp_path, **values):
    job = {'id': 'job', 'account': 'account', 'processed': 0, 'chat_index': 0, 'offset': 0, **values}
    return FrozenMessages(tmp_path / 'plan.sqlite3', job)


def test_snapshot_is_deduplicated_complete_and_immutable(tmp_path):
    plan = snapshot(tmp_path)
    plan.append(0, {'messages': [message('a'), message('a'), message('b')], 'has_more': True,
                    'warning': '第一页读取不完整'}, lambda: None)
    with pytest.raises(ValueError):
        plan.freeze(1)
    plan.append(0, {'messages': [message('b'), message('c')], 'has_more': False}, lambda: None)
    assert plan.freeze(1)['total'] == 3
    assert plan.segment(0)['warning'] == '第一页读取不完整'
    reopened = snapshot(tmp_path, processed=2, offset=2)
    assert reopened.metadata()['total'] == 3
    assert [m['source'] for m in reopened.page(0, 1, 100, lambda: None)['messages']] == ['b', 'c']
    with pytest.raises(ValueError, match='固定'):
        reopened.append(0, {'messages': [message('new')]}, lambda: None)
    assert reopened.freeze(1)['total'] == 3


def test_snapshot_commit_cancel_rolls_back_count_and_cursor(tmp_path):
    plan = snapshot(tmp_path)
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise InferenceFailure('暂停', 'cancelled')
    with pytest.raises(InferenceFailure):
        plan.append(0, {'messages': [message(str(i)) for i in range(200)], 'has_more': True}, cancel)
    assert plan.segment(0)['offset'] == 0
    plan.append(0, {'messages': [message('a')], 'has_more': False}, lambda: None)
    assert plan.freeze(1)['total'] == 1


def test_snapshot_pages_keep_character_budget_and_old_committed_base(tmp_path):
    plan = snapshot(tmp_path, processed=500, offset=100, chat_index=1)
    plan.append(1, {'messages': [message(str(i), '文' * 70000) for i in range(3)], 'has_more': False}, lambda: None)
    assert plan.freeze(2)['total'] == 503
    page = plan.page(1, 100, 1000, lambda: None)
    assert len(page['messages']) == 2 and page['has_more']
    assert len(plan.page(1, 102, 1000, lambda: None)['messages']) == 1


async def service_for(tmp_path, monkeypatch, reader, engine=None):
    service = LocalSearch(tmp_path / 'state', tmp_path / 'models', reader=reader, engine=engine or FakeEngine())
    root = model_dir(service.downloads.root, 'bge-small-zh')
    root.mkdir(parents=True)
    Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root / 'tokenizer.json'))
    monkeypatch.setattr(service.downloads, 'available', lambda _: True)
    monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
    await service.configure('a', {'enabled': True, 'model': 'bge-small-zh', 'days': 0,
                                'start': 0, 'end': 2000, 'usernames': ['allowed'], 'read_batch_size': 100})
    return service


def test_count_finishes_before_encoding_and_new_or_deleted_messages_do_not_change_total(tmp_path, monkeypatch):
    async def run():
        rows = [message('a'), message('a'), message('b')]
        reads = []
        def reader(account, username, start, end, offset):
            reads.append(offset)
            return {'messages': copy.deepcopy(rows[offset:offset + 2]), 'has_more': offset + 2 < len(rows)}
        service = await service_for(tmp_path, monkeypatch, reader)
        original = service.engine.encode
        def encode(*args, **kwargs):
            status = service.status('a')
            assert status['message_total']['value'] == 2
            assert status['message_total']['fixed'] is True
            assert reads == [0, 2]
            # 包括补入旧时间的消息、删除原记录，都不能改变已经固定的清单。
            rows[:] = [message('new', timestamp=50)]
            return original(*args, **kwargs)
        monkeypatch.setattr(service.engine, 'encode', encode)
        current = await service.build('a')
        await service.jobs[current['id']]
        assert current['status'] == 'done' and current['processed'] == 2
        assert service.status('a')['message_total']['value'] == 2
        assert not list((service.root / 'plans').rglob('*.sqlite3'))
        monkeypatch.setattr(service.engine, 'encode', original)
        next_round = await service.build('a', incremental=False)
        await service.jobs[next_round['id']]
        assert next_round['status'] == 'done' and next_round['processed'] == 1
        assert service.status('a')['message_total']['value'] == 1
        await service.stop()
    asyncio.run(run())


def test_pause_after_commit_resumes_same_plan_without_rereading_source(tmp_path, monkeypatch):
    async def run():
        rows = [message(str(i), timestamp=100 + i) for i in range(250)]
        reads = []
        def reader(account, username, start, end, offset):
            reads.append(offset)
            return {'messages': copy.deepcopy(rows[offset:offset + 100]), 'has_more': offset + 100 < len(rows)}
        service = await service_for(tmp_path, monkeypatch, reader)
        original_commit = SemanticIndex.commit
        paused = False
        def commit(index, generation, messages, chunks, vectors, current, checkpoint=None):
            nonlocal paused
            original_commit(index, generation, messages, chunks, vectors, current, checkpoint)
            if not paused:
                paused = True
                service.cancelled.add(current['id'])
        monkeypatch.setattr(SemanticIndex, 'commit', commit)
        current = await service.build('a')
        await service.jobs[current['id']]
        assert current['status'] == 'paused' and current['processed'] == 100
        assert service.status('a')['message_total']['value'] == 250
        rows.clear()
        reads_before = list(reads)
        resumed = await service.resume('a', current['id'])
        await service.jobs[resumed['id']]
        assert resumed['status'] == 'done' and resumed['processed'] == 250
        assert reads == reads_before
        assert service.status('a')['message_total']['value'] == 250
        assert service.index('a').stats(resumed['generation'])['messages'] == 250
        await service.stop()
    asyncio.run(run())


def test_failed_preparation_never_starts_inference_and_can_resume_its_cursor(tmp_path, monkeypatch):
    async def run():
        reads, fail = [], True
        def reader(account, username, start, end, offset):
            nonlocal fail
            reads.append(offset)
            if offset == 1 and fail:
                fail = False
                raise OSError('源暂不可用')
            return {'messages': [message(str(offset))], 'has_more': offset < 2}
        service = await service_for(tmp_path, monkeypatch, reader)
        current = await service.build('a')
        await service.jobs[current['id']]
        assert current['status'] == 'error' and current['processed'] == 0
        assert service.engine.calls == 0
        assert 'value' not in service.status('a')['message_total']
        resumed = await service.resume('a', current['id'])
        await service.jobs[resumed['id']]
        assert resumed['status'] == 'done' and resumed['processed'] == 3
        assert reads == [0, 1, 1, 2]
        await service.stop()
    asyncio.run(run())


def test_missing_fixed_plan_fails_instead_of_recounting_a_different_total(tmp_path, monkeypatch):
    async def run():
        service = await service_for(tmp_path, monkeypatch, lambda *args: {'messages': []})
        current = {'id': 'lost', 'account': 'a', 'processed': 0, 'chat_index': 0, 'offset': 0}
        service.save_message_total(current, status='ready', value=10, fixed=True)
        with pytest.raises(InferenceFailure, match='清单已丢失'):
            await service.count_message_total(current, lambda: None)
        assert service.store.get('index_message_total', 'lost')['value'] == 10
        await service.stop()
    asyncio.run(run())


def test_zero_message_round_has_fixed_zero_total(tmp_path, monkeypatch):
    async def run():
        service = await service_for(tmp_path, monkeypatch, lambda *args: {'messages': [], 'has_more': False})
        current = await service.build('a')
        await service.jobs[current['id']]
        assert current['status'] == 'done' and current['processed'] == 0
        assert service.status('a')['message_total']['value'] == 0
        assert service.status('a')['message_total']['fixed']
        await service.stop()
    asyncio.run(run())


@pytest.mark.parametrize('status', ['queued', 'running', 'paused', 'error'])
def test_global_refresh_does_not_expand_scope_while_round_is_unfinished(tmp_path, monkeypatch, status):
    from unittest.mock import AsyncMock
    from wechat_decrypt_tool.ai.agent_tools import ChatTools
    async def run():
        service = LocalSearch(tmp_path)
        cfg = {'enabled': True, 'model': 'bge-small-zh', 'agent_global': True, 'usernames': ['old'], 'revision': 1}
        current = {'id': 'run', 'account': 'a', 'status': status, 'config': cfg, 'end': 100}
        service.store.put('config', cfg, id='a', account='a')
        service.store.put('index_job', current, id='run', account='a')
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        contacts = AsyncMock(return_value=[{'username': 'old'}, {'username': 'new'}])
        monkeypatch.setattr(ChatTools, 'conversations', contacts)
        assert (await service.ensure_global('a'))['id'] == 'run'
        contacts.assert_not_called()
        assert service.config('a')['revision'] == 1
        assert service.config('a')['usernames'] == ['old']
    asyncio.run(run())
