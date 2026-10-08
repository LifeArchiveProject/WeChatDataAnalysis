"""写盘预算回归：展示更新零写入，业务边界持久化，重连与恢复保持可用。"""
import asyncio
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from test_ai_agent import service, FakeModels
from test_ai_agent_sse import request
from test_ai_global_assistant import idle_run
from wechat_decrypt_tool.ai.storage import AIStore
from wechat_decrypt_tool.ai.service import AIService
from wechat_decrypt_tool.ai.agent_service import AgentService
from wechat_decrypt_tool.local_search.service import LocalSearch
from wechat_decrypt_tool.routers import ai_agent


def disk_record(store, kind, id):
    # 绕过进程内快照，确认另一个连接真正看到的持久状态。
    with sqlite3.connect(store.path) as db:
        row = db.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, id)).fetchone()
    return json.loads(row[0]) if row else None


def changes(store):
    with store.connection() as db:
        return db.total_changes


def test_stream_updates_are_live_without_sql_writes_and_periodically_checkpoint(service):
    async def run():
        _, task = await idle_run(service)
        id = task['id']
        before = changes(service.store)
        with patch('wechat_decrypt_tool.ai.agent_service.time.monotonic', return_value=100):
            for i in range(100):
                service.stream_answer(id, f'正文{i}', '正在回答')
        assert changes(service.store) == before
        assert service.run(id)['answer'] == '正文99'
        assert disk_record(service.store, 'agent_run', id)['answer'] == ''
        assert service.public_run(id, 'account')['answer'] == '正文99'
        with patch('wechat_decrypt_tool.ai.agent_service.time.monotonic', return_value=102):
            service.stream_answer(id, '草稿检查点', '正在回答')
        assert disk_record(service.store, 'agent_run', id)['answer'] == '草稿检查点'
        with service.store.connection() as db:
            assert db.execute("SELECT count(*) FROM agent_piece WHERE run_id=? AND kind='timeline'", (id,)).fetchone()[0] == 1
        with patch('wechat_decrypt_tool.ai.agent_service.time.monotonic', return_value=103):
            service.stream_answer(id, '检查点之后的文字', '正在回答')
        reopened = AIStore(service.store.root)
        try:
            assert reopened.get('agent_run', id)['answer'] == '草稿检查点'
        finally:
            reopened.close()
    asyncio.run(run())


def test_service_restart_marks_checkpoint_interrupted_without_losing_saved_draft(service):
    async def run():
        _, task = await idle_run(service)
        with patch('wechat_decrypt_tool.ai.agent_service.time.monotonic', return_value=100):
            service.stream_answer(task['id'], '第一段', '正在回答')
        with patch('wechat_decrypt_tool.ai.agent_service.time.monotonic', return_value=102):
            service.stream_answer(task['id'], '已提交的草稿', '正在回答')
        store = AIStore(service.store.root)
        restarted = AgentService(AIService(store, FakeModels(store)), service.tools)
        try:
            await restarted.start()
            run = restarted.run(task['id'])
            assert run['status'] == 'interrupted' and run['answer'] == '已提交的草稿'
            assert restarted.public_run(task['id'], 'account')['can_resume']
        finally:
            await restarted.stop()
            store.close()
    asyncio.run(run())


@pytest.mark.parametrize('status', ['completed', 'cancelled', 'interrupted', 'failed'])
def test_final_state_flushes_latest_draft_and_history(service, status):
    async def run():
        thread, task = await idle_run(service)
        service.stream_answer(task['id'], '最后一段正文', '正在回答')
        service.finish(task['id'], status)
        saved = disk_record(service.store, 'agent_run', task['id'])
        assert saved['answer'] == '最后一段正文' and saved['status'] == status
        assert saved['timeline'][-1]['text'] == '最后一段正文'
        assert not service.store.has_live_record('agent_run', task['id'])
        if status == 'completed':
            assert service.thread(thread['id'], 'account')['messages'][-1]['text'] == '最后一段正文'
    asyncio.run(run())


def test_memory_sse_wakes_replays_latest_and_keeps_account_boundary(service):
    async def run():
        _, task = await idle_run(service)
        with patch.object(ai_agent, 'get_agent_service', return_value=service), \
                patch.object(ai_agent, 'account_name', side_effect=lambda value: value):
            response = await ai_agent.events(request(), 'account')
            initial = await anext(response.body_iterator)
            cursor = int(initial.split(': ')[1])
            waiting = asyncio.create_task(anext(response.body_iterator))
            await asyncio.sleep(0)
            before = changes(service.store)
            service.store.event('other', 'agent', {'text': '其他账号'}, transient=True)
            service.stream_answer(task['id'], '实时文字', '正在回答')
            event = await asyncio.wait_for(waiting, 0.5)
            assert json.loads(event.split('data: ', 1)[1])['timeline_item']['text'] == '实时文字'
            assert json.loads(event.split('data: ', 1)[1])['patch']['stage'] == '正在回答'
            assert changes(service.store) == before
            await response.body_iterator.aclose()
            service.stream_answer(task['id'], '断线后的最新文字', '正在回答')
            again = await ai_agent.events(request(cursor), 'account')
            await anext(again.body_iterator)
            replay = await anext(again.body_iterator)
            assert '断线后的最新文字' in replay and '其他账号' not in replay
            await again.body_iterator.aclose()
    asyncio.run(run())


def test_index_display_counters_do_not_write_or_advance_recovery_cursor(tmp_path):
    search = LocalSearch(tmp_path, engine=SimpleNamespace(status={}, gpu_failed=False))
    job = dict(id='index', account='account', status='running', stage='reading', processed=10,
               offset=10, embedded=3, read_count=10)
    search.update(job)
    before = changes(search.store)
    for count in range(11, 111):
        search.update(job, read_count=count, embedded_count=count)
    assert changes(search.store) == before
    assert search.store.get('index_job', 'index')['read_count'] == 110
    assert search.store.list('index_job', 'account')[0]['read_count'] == 110
    saved = disk_record(search.store, 'index_job', 'index')
    assert saved['read_count'] == 10 and saved['offset'] == 10
    job.update(processed=110, offset=110, embedded=110)
    search.update(job)
    saved = disk_record(search.store, 'index_job', 'index')
    assert saved['read_count'] == 110 and saved['offset'] == 110
    assert len(search.store.events(account='account')) == 1
    before = changes(search.store)
    search.update(job)
    assert changes(search.store) == before
    search.store.close()


def test_storage_transaction_rolls_back_records_events_and_live_overlay(tmp_path):
    store = AIStore(tmp_path)
    store.put('agent_run', {'answer': '已提交'}, id='run', account='account')
    store.put('agent_run', {'answer': '内存草稿'}, id='run', account='account', transient=True)
    with pytest.raises(RuntimeError):
        with store.connection():
            store.put('agent_run', {'answer': '失败的提交'}, id='run', account='account')
            store.event('account', 'agent', {'text': '不应出现'})
            raise RuntimeError('模拟事务失败')
    assert store.get('agent_run', 'run')['answer'] == '内存草稿'
    assert disk_record(store, 'agent_run', 'run')['answer'] == '已提交'
    assert store.events() == []
    store.close()


def test_connection_reuse_cross_thread_rollback_and_repair(tmp_path):
    store = AIStore(tmp_path)
    with store.connection() as first:
        pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda i: store.put('value', {'i': i}, id=str(i)), range(20)))
    with store.connection() as second:
        assert first is second
        assert db_integrity(second) == 'ok'
    assert store.repair_oversized(max_database_bytes=1) > 0
    assert len(store.list('value')) == 20
    with store.connection() as repaired:
        assert repaired is not first and db_integrity(repaired) == 'ok'
    store.close()


def db_integrity(db):
    return db.execute('PRAGMA integrity_check').fetchone()[0]


def test_restart_event_ids_follow_transient_cursor_and_notifications_remain_durable(tmp_path):
    store = AIStore(tmp_path)
    store.event('account', 'agent', {'text': '展示'}, transient=True)
    cursor = store.latest_event_id()
    store.close()
    restarted = AIStore(tmp_path)
    restarted.event('account', 'notification', {'text': '通知'}, unique_key='notification')
    assert restarted.latest_event_id() > cursor
    assert restarted.events(cursor, 'account', pending=True)[0]['body']['text'] == '通知'
    restarted.close()


def test_coalesced_live_event_keeps_verified_reference_mapping(tmp_path):
    store = AIStore(tmp_path)
    store.event('account', 'agent', {'version': 1, 'text': '带引用的文字',
                'citations': [{'source': 'a', 'text': '原文'}], 'references': [{'id': 'b'}]},
                unique_key='answer', transient=True)
    store.event('account', 'agent', {'version': 1, 'text': '带引用的文字继续输出'},
                unique_key='answer', transient=True)
    latest = store.events()[0]['body']
    assert latest['citations'][0]['source'] == 'a' and latest['references'][0]['id'] == 'b'
    store.event('account', 'agent', {'version': 2, 'text': '新版本'}, unique_key='answer', transient=True)
    assert 'citations' not in store.events()[0]['body']
    for i in range(300):
        store.event('account', 'agent', {'text': str(i)}, unique_key=f'item:{i}', transient=True)
    assert len(store._live_events) == 256
    assert store._live_event_bytes <= 8 * 1024 * 1024
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM events').fetchone()[0] == 0
    store.close()


def test_abrupt_process_exit_retains_committed_checkpoint_and_notifications(tmp_path):
    source = Path(__file__).resolve().parents[1] / 'src'
    script = f"""
import sys, os
from pathlib import Path
sys.path.insert(0, {str(source)!r})
from wechat_decrypt_tool.ai.storage import AIStore
store = AIStore(Path({str(tmp_path)!r}))
store.put('agent_run', {{'answer': '已提交的草稿'}}, id='run', account='account')
store.event('account', 'notification', {{'text': '未投递提醒'}}, unique_key='notice')
store.put('agent_run', {{'answer': '最后的展示片段'}}, id='run', account='account', transient=True)
os._exit(0)
"""
    subprocess.run([sys.executable, '-c', script], check=True, timeout=30)
    restarted = AIStore(tmp_path)
    assert restarted.get('agent_run', 'run')['answer'] == '已提交的草稿'
    assert restarted.events(account='account', pending=True)[0]['body']['text'] == '未投递提醒'
    with restarted.connection() as db:
        assert db_integrity(db) == 'ok'
    restarted.close()


def test_identical_records_and_updates_do_not_write(service):
    async def run():
        _, task = await idle_run(service)
        before = changes(service.store)
        service.update(task['id'], status='running')
        service.store.put('agent_run', service.store.get('agent_run', task['id']))
        assert changes(service.store) == before
    asyncio.run(run())


def test_deleted_run_and_revoked_account_remove_live_state(service):
    async def run():
        _, task = await idle_run(service)
        service.stream_answer(task['id'], '即将删除', '正在回答')
        service.store.delete('agent_run', task['id'])
        assert service.store.get('agent_run', task['id']) is None
        assert not any(e['body'].get('run_id') == task['id'] for e in service.store.events()
                       if e['unique_key'] and e['unique_key'].startswith('timeline:'))
        service.store.put('index_job', {'read_count': 1}, id='job', account='account', transient=True)
        service.store.event('account', 'agent', {'text': '即将清理'}, transient=True)
        service.store.purge_account('account')
        assert service.store.get('index_job', 'job') is None
        assert service.store.events(account='account') == []
    asyncio.run(run())
