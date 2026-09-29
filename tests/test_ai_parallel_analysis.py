"""真实持久化和分页合同；模拟模型耗时以稳定验证并行与恢复。"""
import asyncio
import hashlib
import json
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from test_ai_deepagents import make_service, execute, action
from wechat_decrypt_tool.ai.deep_tools import ChatGateway, ScopeError
from wechat_decrypt_tool.ai.deep_runtime import CHILD_SCOPE
from wechat_decrypt_tool.ai.deep_partition import fingerprint
from wechat_decrypt_tool.ai.providers import ProviderFailure


class Data:
    def __init__(self, count=24, text='资料' * 120, same_second=False):
        self.rows = [{'source': hashlib.sha256(str(i).encode()).hexdigest()[:24], 'username': 'friend',
            'anchor': f'db:{i}', 'time': 100 if same_second else 100 + i * 4000,
            'sender': '甲', 'sender_id': 'person-a', 'kind': 'text', 'text': f'{i}:' + text, 'media': {}}
            for i in range(count)]
        self.calls = []

    async def conversations(self, account):
        return [{'username': 'friend', 'name': '好友'}, {'username': 'other', 'name': '另一群'}]

    async def read(self, account, username, start, end, offset, **kwargs):
        self.calls.append((username, start, end, offset))
        rows = [m for m in self.rows if m['username'] == username and start <= m['time'] < end]
        return {'messages': rows[offset:offset + 1], 'has_more': offset + 1 < len(rows), 'next_offset': offset + 1}

    async def recent_set(self, account, usernames, start, end, count, checkpoint, sender=None):
        rows = [m for m in self.rows if m['username'] in usernames and start <= m['time'] < end and (not sender or m['sender_id'] == sender)]
        return {'messages': sorted(rows, key=lambda m: (m['time'], m['source']))[-count:], 'warning': ''}


async def prepared(service, text='完整分析当前聊天'):
    _, public = await execute(service)
    # 本文件验证历史 v1 分片与恢复，新增任务使用 v2 规划回归。
    service.update(public['id'], status='running', finished_at=None, input_digest=text, cutoff=2_000_000_000, subtask_plan_version=1)
    return ChatGateway(service, public['id'], public['version'])


def setup(tmp_path, monkeypatch, data=None):
    service, client = make_service(tmp_path, monkeypatch, tools=data or Data())
    monkeypatch.setattr('wechat_decrypt_tool.ai.deep_partition.capacity', lambda service, run: 1024)
    monkeypatch.setattr('wechat_decrypt_tool.ai.deep_dispatch.capacity', lambda service, run: 1024)
    return service, client


def fake_workers(service, monkeypatch, *, delay=.2, failures=None, started=None, release=None):
    stats = {'active': 0, 'peak': 0, 'runs': [], 'commits': []}
    failures = failures if failures is not None else set()

    async def run(id):
        child = service.run(id)
        stats['active'] += 1
        stats['peak'] = max(stats['peak'], stats['active'])
        stats['runs'].append(id)
        try:
            if started is not None and stats['active'] == 4:
                started.set()
            if release is not None:
                await release.wait()
            await asyncio.sleep(delay)
            if child.get('manifest_id') in failures:
                service.finish(id, 'failed', '模拟临时失败')
                return
            gateway = ChatGateway(service, id, child['version'])
            while True:
                page = await gateway.read_next(child['scope_handle'])
                if not page.get('requires_commit'):
                    break
                assert not {m['source'] for m in page['messages']} & {m['source'] for m in page.get('background', [])}
                stats['commits'].extend((m['source'], m.get('text_offset', 0), len(m['text'])) for m in page['messages'])
                gateway.commit(child['scope_handle'], page['page_id'], [])
                if not page['has_more']:
                    break
            service.update(id, answer='已完成分配资料。')
            service.finish(id, 'completed')
        finally:
            stats['active'] -= 1
    monkeypatch.setattr(service, 'execute', run)
    return stats


def test_small_scope_prefetch_is_reused_without_subagent(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(1))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        assert selected['execution_mode'] == 'direct'
        calls = list(service.tools.calls)
        page = await gateway.read_next(selected['scope_handle'])
        gateway.commit(selected['scope_handle'], page['page_id'], [])
        assert gateway.validate_complete()
        assert service.tools.calls == calls
        assert service.subtasks.summary(service.run(gateway.id))['total'] == 0
    asyncio.run(check())


def test_all_history_single_chat_runs_parallel_without_repeated_read(tmp_path, monkeypatch):
    # 八条同秒消息仍覆盖四个工作槽和第二轮调度；更大队列由专门的 50 条用例验证。
    service, _ = setup(tmp_path, monkeypatch, Data(8, same_second=True))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        assert selected['execution_mode'] == 'parallel'
        with pytest.raises(ScopeError, match='task'):
            await gateway.read_next(selected['scope_handle'])
        stats = fake_workers(service, monkeypatch)
        parent = service.run(gateway.id)
        plan = service.analysis_plans.get(parent, selected['plan_handle'])
        # 本用例验证完整覆盖和去重，真实 SQLite 在 Windows CI 上较慢；这里只设防死锁期限。
        # 四路并行的速度收益由 test_four_workers_accelerate_eight_equal_jobs 单独断言。
        result = await asyncio.wait_for(service.execute_plan(parent, plan), 180)
        # 持久化开销会影响短任务占槽数；四路加速由固定耗时测试单独验证。
        assert 1 < stats['peak'] <= 4
        assert result['phase'] == 'completed' and gateway.validate_complete()
        assert result['metrics']['repeated_characters'] == 0
        assert result['metrics']['read_characters'] == result['metrics']['analyzed_characters']
        assert len(service.tools.calls) == len(set(service.tools.calls)) == len(service.tools.rows)
        assert len(stats['commits']) == len(set(stats['commits'])) == len(service.tools.rows)
        assert {s for s, _, _ in stats['commits']} == {m['source'] for m in service.tools.rows}
        before = list(stats['runs'])
        await service.execute_plan(parent, result)
        assert stats['runs'] == before
        summary = service.subtasks.summary(parent)
        assert summary['completed'] == summary['total'] and summary['total_known']
    asyncio.run(check())


def test_failed_piece_resumes_without_rerunning_completed(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        plan = service.analysis_plans.get(parent, selected['plan_handle'])
        first = service.analysis_plans.enqueue(parent, plan)
        failures = {first['manifest_id']}
        stats = fake_workers(service, monkeypatch, failures=failures)
        with pytest.raises(ProviderFailure, match='部分分片'):
            await service.execute_plan(parent, plan)
        assert not gateway.validate_complete()
        completed = {j['child_run_id'] for j in service.analysis_plans.jobs(parent, plan['id'], ['completed'])}
        assert completed
        failures.clear()
        count = len(stats['runs'])
        await service.execute_plan(parent, plan)
        assert set(stats['runs'][count:]).isdisjoint(completed)
        assert stats['runs'][count:] == [first['child_run_id']]
        assert gateway.validate_complete()
    asyncio.run(check())


def test_multiple_plans_share_parent_slots_and_queue_is_bounded(tmp_path, monkeypatch):
    data = Data(50)
    for index, row in enumerate(data.rows):
        row['username'] = 'friend' if index % 2 else 'other'
    service, _ = setup(tmp_path, monkeypatch, data)
    async def check():
        gateway = await prepared(service)
        selected = [await gateway.select(conversations=[user], complete=True) for user in ['friend', 'other']]
        parent = service.run(gateway.id)
        workers_full, queue_full, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        stats = fake_workers(service, monkeypatch, started=workers_full, release=release)
        plans = [service.analysis_plans.get(parent, s['plan_handle']) for s in selected]
        original = service.analysis_plans.enqueue
        queue_peak = 0
        def enqueue(parent, plan):
            nonlocal queue_peak
            result = original(parent, plan)
            queued = service.analysis_plans.queued_count(parent)
            queue_peak = max(queue_peak, queued)
            assert queued <= 8
            if queued == 8:
                queue_full.set()
            return result
        monkeypatch.setattr(service.analysis_plans, 'enqueue', enqueue)

        async def release_full_queue():
            # 先阻塞四个工作槽，让两个计划真正填满共享队列，再验证排空和完整覆盖。
            await asyncio.gather(workers_full.wait(), queue_full.wait())
            assert stats['active'] == 4
            release.set()

        tasks = [asyncio.create_task(release_full_queue()),
                 *(asyncio.create_task(service.execute_plan(parent, p)) for p in plans)]
        try:
            # 数千次真实 SQLite 连接在 Windows CI 上较慢；此期限只防死锁，不衡量性能。
            await asyncio.wait_for(asyncio.gather(*tasks), 180)
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        assert stats['peak'] == 4 and queue_peak == 8
        assert gateway.validate_complete()
        assert len(stats['commits']) == len(set(stats['commits']))
        assert {source for source, _, _ in stats['commits']} == {row['source'] for row in data.rows}
    asyncio.run(check())


def test_recent_count_selects_one_global_set_before_partition(tmp_path, monkeypatch):
    data = Data(24)
    for i, row in enumerate(data.rows):
        row['username'] = 'friend' if i % 2 else 'other'
    service, _ = setup(tmp_path, monkeypatch, data)
    async def check():
        gateway = await prepared(service, '完整分析最近 12 条消息')
        selected = await gateway.select(conversations=['friend', 'other'], complete=True, message_count=12)
        parent = service.run(gateway.id)
        stats = fake_workers(service, monkeypatch)
        await service.execute_plan(parent, service.analysis_plans.get(parent, selected['plan_handle']))
        assert {s for s, _, _ in stats['commits']} == {m['source'] for m in data.rows[-12:]}
        assert not data.calls and gateway.validate_complete()
    asyncio.run(check())


def test_cancel_cleans_running_queue_and_resume_reuses_commits(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(50))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        stats = fake_workers(service, monkeypatch, delay=.05)
        plan = service.analysis_plans.get(parent, selected['plan_handle'])
        task = asyncio.create_task(service.execute_plan(parent, plan))
        await asyncio.sleep(.13)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stats['active'] == 0 and not service.analysis_plans.jobs(parent, plan['id'], ['running'])
        done = {j['child_run_id'] for j in service.analysis_plans.jobs(parent, plan['id'], ['completed'])}
        checkpoint = len(stats['runs'])
        await service.execute_plan(parent, plan)
        assert done.isdisjoint(stats['runs'][checkpoint:])
        assert gateway.validate_complete()
    asyncio.run(check())


def test_fragment_manifest_preserves_whole_long_message(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(1, '长文' * 8000))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        stats = fake_workers(service, monkeypatch, delay=0)
        await service.execute_plan(parent, service.analysis_plans.get(parent, selected['plan_handle']))
        position = 0
        for _, offset, length in stats['commits']:
            assert offset == position
            position += length
        assert position == len(service.tools.rows[0]['text'])
        assert gateway.validate_complete()
    asyncio.run(check())


def test_real_graph_worker_consumes_manifest_and_commits_sources(tmp_path, monkeypatch):
    service, client = setup(tmp_path, monkeypatch, Data(5))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        def respond(messages):
            states = next(json.JSONDecoder().raw_decode(str(m.content).rsplit('当前执行状态（程序元数据）：', 1)[1].lstrip())[0]
                for m in messages if m.type == 'system' and '当前执行状态（程序元数据）：' in str(m.content))
            scope = states['scopes'][0]
            results = [m for m in messages if isinstance(m, ToolMessage)]
            if scope.get('pending_page'):
                page = json.loads(results[-1].content)
                return action('commit_findings', {'scope_handle': scope['scope_handle'], 'page_id': scope['pending_page'],
                    'findings': [{'text': '本片原文事实', 'sources': [m['source']]} for m in page['messages']]})
            if not scope['analysis_complete']:
                return action('read_messages', {'scope_handle': scope['scope_handle']})
            return AIMessage(content='已提交本片发现。')
        client.next = respond
        parent = service.run(gateway.id)
        plan = await service.execute_plan(parent, service.analysis_plans.get(parent, selected['plan_handle']))
        assert plan['result']['finding_count'] == 5
        assert gateway.validate_complete()
        assert all(j['status'] == 'completed' for j in service.analysis_plans.jobs(parent, plan['id']))
    asyncio.run(check())


def test_empty_and_search_scopes_do_not_spawn_or_prescan(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(0))
    async def check():
        gateway = await prepared(service, '查找约饭消息')
        selected = await gateway.select()
        assert 'plan_handle' not in selected and not service.tools.calls
        selected = await gateway.select(complete=True)
        assert selected['execution_mode'] == 'direct'
        page = await gateway.read_next(selected['scope_handle'])
        gateway.commit(selected['scope_handle'], page['page_id'], [])
        assert gateway.validate_complete()
        assert service.subtasks.summary(service.run(gateway.id))['total'] == 0
    asyncio.run(check())


def test_focus_deduplicates_same_evidence_and_limits_new_rounds(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service, '核查具体日期')
        selected = await gateway.select()
        parent = service.run(gateway.id)
        scope = gateway.scope(selected['scope_handle'])
        calls = []
        async def work(parent, job, scope):
            calls.append(job['id'])
            child = service.create_partition_child(parent, job, scope)
            service.update(child['id'], status='completed', answer='仍待确认', finished_at=time.time())
            job.update(status='completed')
            service.deep_job(parent, job)
        monkeypatch.setattr(service, 'work_partition', work)
        first = await service.focused_task(parent, scope, 'fact-checker', '核查活动日期')
        again = await service.focused_task(parent, scope, 'fact-checker', '核查活动日期')
        assert first == again and len(calls) == 1
        gateway.save_messages([service.tools.rows[0]])
        await service.focused_task(parent, scope, 'fact-checker', '核查活动日期')
        assert len(calls) == 2
        gateway.save_messages([service.tools.rows[1]])
        stopped = await service.focused_task(parent, scope, 'fact-checker', '核查活动日期')
        assert '两轮' in stopped['instruction'] and len(calls) == 2
        result = await service.focused_task(parent, scope, 'retrieval-analyst', '独立搜索另一个专题')
        assert result['coverage'] == 'search_only' and len(calls) == 3
    asyncio.run(check())


def test_four_workers_accelerate_eight_equal_jobs(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(16))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        manager = service.analysis_plans
        plan = manager.get(parent, selected['plan_handle'])
        while not plan['scan_complete']:
            await manager.fetch(parent, plan)
        while plan['buffer']:
            manager.enqueue(parent, plan)
        assert len(manager.jobs(parent, plan['id'])) >= 8
        # 这里只比较执行调度的耗时，真实正文覆盖由其他合同测试负责。
        monkeypatch.setattr(manager, 'validate', lambda *a, **kw: True)
        async def work(parent, job, scope):
            # 模拟有实质工作量的固定模型延迟，避免磁盘抖动主导 200 毫秒微任务。
            await asyncio.sleep(1)
            job.update(status='completed')
            service.deep_job(parent, job)
        monkeypatch.setattr(service, 'work_partition', work)
        durations = []
        for workers in [1, 4]:
            manager.slots[(parent['id'], parent['version'])] = asyncio.Semaphore(workers)
            plan = manager.get(parent, plan['id'])
            plan['phase'] = 'analyzing'
            manager.save(parent, plan)
            for job in manager.jobs(parent, plan['id']):
                job['status'] = 'queued'
                service.deep_job(parent, job)
            start = time.perf_counter()
            await service.execute_plan(parent, plan)
            durations.append(time.perf_counter() - start)
        assert durations[1] <= durations[0] * .5, durations
    asyncio.run(check())


def test_manifest_only_context_cannot_read_other_messages(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(8))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        plan = service.analysis_plans.get(parent, selected['plan_handle'])
        job = service.analysis_plans.enqueue(parent, plan)
        child = service.create_partition_child(parent, job, gateway.scope(selected['scope_handle']))
        service.update(child['id'], status='running')
        cg = ChatGateway(service, child['id'], 1)
        scope = await cg.select()
        page = await cg.read_next(scope['scope_handle'])
        context_tool = next(t for t in cg.tools() if t.name == 'read_context')
        result = await context_tool.ainvoke({'scope_handle':scope['scope_handle'], 'source':page['messages'][0]['source']})
        manifest = service.analysis_plans.get(parent, job['manifest_id'])
        allowed = {r['source'] for r in manifest['core'] + manifest['context']}
        assert {m['source'] for m in result['messages']} <= allowed
        with pytest.raises(ValueError, match='来源'):
            await context_tool.ainvoke({'scope_handle':scope['scope_handle'], 'source':service.tools.rows[-1]['source']})
    asyncio.run(check())


def test_revision_reuses_frozen_sources_but_not_old_findings(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(1))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        page = await gateway.read_next(selected['scope_handle'])
        gateway.commit(selected['scope_handle'], page['page_id'], [{'text':'旧目标发现','sources':[page['messages'][0]['source']]}])
        reads = list(service.tools.calls)
        service.update(gateway.id, version=2, input_digest='完整分析活动安排的变更', scope_handle='', required_conversations=[])
        revised = ChatGateway(service, gateway.id, 2)
        selected = await revised.select(complete=True)
        plan = service.analysis_plans.get(service.run(gateway.id), selected['plan_handle'])
        assert plan['reuse_version'] == 1
        assert service.tools.calls == reads
        assert service.workspace.page(gateway.id, 2, 'finding')['total'] == 0
        page = await revised.read_next(selected['scope_handle'])
        revised.commit(selected['scope_handle'], page['page_id'], [])
        assert revised.validate_complete()
    asyncio.run(check())


def test_context_failure_splits_only_uncommitted_text(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(6))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        stats = fake_workers(service, monkeypatch, delay=0)
        healthy = service.execute
        first = []
        async def fail_once(id):
            if first:
                return await healthy(id)
            first.append(id)
            child = service.run(id)
            cg = ChatGateway(service, id, 1)
            page = await cg.read_next(child['scope_handle'])
            stats['commits'].extend((m['source'], m.get('text_offset',0),len(m['text'])) for m in page['messages'])
            cg.commit(child['scope_handle'], page['page_id'], [])
            service.finish(id, 'failed', '上下文窗口不足')
        monkeypatch.setattr(service, 'execute', fail_once)
        plan = await service.execute_plan(parent, service.analysis_plans.get(parent, selected['plan_handle']))
        jobs = service.analysis_plans.jobs(parent, plan['id'])
        assert any(j['status'] == 'superseded' for j in jobs)
        assert any(j.get('replaces') for j in jobs)
        page = service.subtasks.page(parent['id'], parent['account'], limit=100)
        assert any(j['status'] == 'superseded' for j in page['items'])
        assert page['summary']['total'] == len(jobs) - 1
        assert gateway.validate_complete()
        spans = {}
        for source, offset, length in stats['commits']:
            spans.setdefault(source, []).append((offset, offset + length))
        for row in service.tools.rows:
            position = 0
            for start, end in sorted(spans[row['source']]):
                assert start == position
                position = end
            assert position == len(row['text'])
    asyncio.run(check())


def test_reduction_visits_all_findings_and_resumes_cached_nodes(tmp_path, monkeypatch):
    from wechat_decrypt_tool.ai.deep_model import DeepChatModel
    service, _ = setup(tmp_path, monkeypatch, Data(1))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        source = service.tools.rows[0]['source']
        ids = {f'finding:{i:04d}' for i in range(80)}
        service.workspace.put_pieces(gateway.id, gateway.version,
            [(key, 'finding', {'text':key + '事件状态发生变化，需核查具体关系。' * 40, 'sources':[source]}) for key in sorted(ids)])
        other = {**service.tools.rows[0], 'source':'other-source', 'username':'other'}
        gateway.save_messages([other])
        service.workspace.put(gateway.id, gateway.version, 'finding:other', 'finding',
            {'text':'另一个计划尚未汇总的结果', 'sources':['other-source']})
        visited = set()
        async def summarize(self, messages, **kwargs):
            group = json.loads(messages[-1].content)['findings']
            visited.update(e['id'] for e in group)
            return AIMessage(content=json.dumps({'text':'存在状态变化，具体关系仍待核查。','sources':[source], 'unresolved':['状态是否实际生效']}))
        monkeypatch.setattr(DeepChatModel, 'ainvoke', summarize)
        parent = service.run(gateway.id)
        plan = service.analysis_plans.get(parent, selected['plan_handle'])
        result = await service.reduce_plan(parent, plan)
        assert ids <= visited and result['finding_count'] == 80
        visited.clear()
        assert await service.reduce_plan(parent, plan) == result
        assert not visited
    asyncio.run(check())


def test_manifest_material_tools_and_files_cannot_read_outside_character_span(tmp_path, monkeypatch):
    from wechat_decrypt_tool.ai.deep_backend import TaskBackend
    service, _ = setup(tmp_path, monkeypatch, Data(4))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        manager = service.analysis_plans
        plan = manager.get(parent, selected['plan_handle'])
        plan['buffer'] = [{**plan['buffer'][0], 'start':20, 'end':40}]
        job = manager.enqueue(parent, plan)
        child = service.create_partition_child(parent, job, gateway.scope(selected['scope_handle']))
        service.update(child['id'], status='running')
        cg = ChatGateway(service, child['id'], 1)
        selected = await cg.select()
        page = await cg.read_next(selected['scope_handle'])
        source = page['messages'][0]['source']
        tools = {t.name:t for t in cg.tools()}
        expected = service.tools.rows[0]['text'][20:40]
        for name, params in [('read_material', {'source':source}), ('search_material', {'source':source})]:
            result = await tools[name].ainvoke({'scope_handle':selected['scope_handle'], **params})
            assert [m['text'] for m in result['messages']] == [expected]
        content = TaskBackend(service, child['id'], 1).data('/materials/' + source + '.json')
        assert [m['text'] for m in json.loads(content['content'])['fragments']] == [expected]
        async def enrich(account, original, *args, **kwargs):
            assert original['text'] == expected
            return {'text':original['text'], 'coverage':'附件不可用'}
        monkeypatch.setattr(service.ai.media, 'enrich', enrich)
        await tools['analyze_media'].ainvoke({'scope_handle':selected['scope_handle'], 'source':source})
        with pytest.raises(ValueError, match='续读'):
            await tools['read_material'].ainvoke({'scope_handle':selected['scope_handle'], 'source':source, 'text_offset':40})
    asyncio.run(check())


def test_focus_cancellation_settles_only_original_job(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service, '查找活动安排')
        selected = await gateway.select()
        parent = service.run(gateway.id)
        entered = asyncio.Event()
        async def work(*args):
            entered.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(service, 'work_partition', work)
        task = asyncio.create_task(service.focused_task(parent, gateway.scope(selected['scope_handle']), 'retrieval-analyst', '查找活动'))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        summary = service.subtasks.summary(parent)
        assert summary['interrupted'] == 1 and summary['running'] == 0 and summary['queued'] == 0
    asyncio.run(check())


def test_probe_delivers_only_one_message_beyond_remaining_budget():
    from wechat_decrypt_tool.ai.agent_reading import read_window
    from wechat_decrypt_tool.ai.agent_budget import message_payload, size
    rows = Data(20, text='小消息').rows
    rows = [{**m, 'identity':m['source']} for m in rows]
    async def read(*args):
        return {'messages':rows, 'has_more':False, 'budgeted_page':True}
    async def check():
        budget = 600
        result = await read_window(read, 0, 200000, 10000, probe_budget=budget)
        assert 1 < len(result['messages']) < len(rows) and result['has_more']
        assert size([message_payload(m) for m in result['messages'][:-1]]) <= budget
        assert size([message_payload(m) for m in result['messages']]) > budget
    asyncio.run(check())


def test_refresh_subtracts_partial_commits_and_holes():
    from wechat_decrypt_tool.ai.deep_partition import uncommitted
    ref = {'source':'a', 'start':0, 'end':100, 'weight':1000}
    values = uncommitted(ref, {'a':[(0,20),(30,50),(40,60),(80,100)]})
    assert [(r['start'],r['end']) for r in values] == [(20,30),(60,80)]


def test_confirmed_values_use_decimal_and_reject_duplicate_or_unavailable_events(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(1))
    async def check():
        gateway = await prepared(service, '计算已确认费用')
        selected = await gateway.select()
        page = await gateway.read_next(selected['scope_handle'])
        source = page['messages'][0]['source']
        tool = next(t for t in gateway.tools() if t.name == 'calculate_values')
        terms = [{'event_key':key, 'value':value, 'sources':[source], 'confirmed':True}
            for key, value in [('first','0.1'),('second','0.2')]]
        args = {'scope_handle':selected['scope_handle'], 'terms':terms}
        assert (await tool.ainvoke(args))['value'] == '0.3'
        assert (await tool.ainvoke({**args,'operation':'difference'}))['value'] == '-0.1'
        with pytest.raises(ValueError, match='重复'):
            await tool.ainvoke({**args,'terms':[terms[0],terms[0]]})
        with pytest.raises(ValueError, match='来源'):
            await tool.ainvoke({**args,'terms':[{**terms[0],'sources':['missing']}]})
        with pytest.raises(ValueError):
            await tool.ainvoke({**args,'terms':[{**terms[0],'confirmed':False}]})
    asyncio.run(check())


def test_source_gap_refresh_preserves_already_analyzed_fragments(tmp_path, monkeypatch):
    from wechat_decrypt_tool.ai.deep_runtime import DeepSourceGap
    data = Data(6)
    original_read = data.read
    gap = [True]
    async def read(*args, **kwargs):
        result = await original_read(*args, **kwargs)
        return {**result, 'warning':'实时源缺口' if gap[0] else ''}
    data.read = read
    service, _ = setup(tmp_path, monkeypatch, data)
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        stats = fake_workers(service, monkeypatch, delay=0)
        plan = service.analysis_plans.get(parent, selected['plan_handle'])
        with pytest.raises(DeepSourceGap):
            await service.execute_plan(parent, plan)
        assert not gateway.validate_complete() and service.run(gateway.id)['needs_source_refresh']
        runs = list(stats['runs'])
        gap[0] = False
        service.refresh_source_gaps(gateway.id)
        await service.execute_plan(parent, plan)
        assert stats['runs'] == runs and gateway.validate_complete()
    asyncio.run(check())


def test_search_and_statistics_coverage_remain_distinct(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch, Data(1))
    async def search(*args):
        return {'messages':[], 'has_more':False, 'warning':'索引可能有缺口'}
    monkeypatch.setattr(service.tools, 'search', search, raising=False)
    async def check():
        gateway = await prepared(service, '查找活动并统计消息')
        selected = await gateway.select()
        tools = {t.name:t for t in gateway.tools()}
        await tools['search_messages'].ainvoke({'scope_handle':selected['scope_handle'], 'query':'活动'})
        ledger = service.workspace.page(gateway.id, gateway.version, 'deep_search_coverage')['items']
        assert len(ledger) == 1 and ledger[0]['coverage'] == 'search_only' and ledger[0]['warning']
        assert not gateway.scope(selected['scope_handle'])['read_complete']
        statistical = await gateway.select(mode='statistics')
        await tools['count_messages'].ainvoke({'scope_handle':statistical['scope_handle']})
        ledger = service.workspace.page(gateway.id, gateway.version, 'deep_statistics_coverage')['items']
        assert ledger[0]['coverage'] == 'statistics_only'
    asyncio.run(check())


def test_child_media_gaps_merge_and_late_jobs_cannot_update_revised_parent(tmp_path, monkeypatch):
    from wechat_decrypt_tool.ai.agent_service import Revised
    service, _ = setup(tmp_path, monkeypatch, Data(4))
    async def check():
        gateway = await prepared(service)
        selected = await gateway.select(complete=True)
        parent = service.run(gateway.id)
        manager = service.analysis_plans
        plan = manager.get(parent, selected['plan_handle'])
        job = manager.enqueue(parent, plan)
        child = service.create_partition_child(parent, job, gateway.scope(selected['scope_handle']))
        body = {'source':service.tools.rows[0]['source'], 'coverage':'附件不可用', 'analysis':'未解析'}
        service.workspace.put(child['id'], 1, 'media:test', 'deep_media_result', body)
        service.merge_partition(parent, child, job)
        assert service.workspace.get(parent['id'], parent['version'], 'media:test') == body
        service.update(parent['id'], version=2)
        with pytest.raises(Revised):
            service.deep_job(parent, {**job,'status':'completed'})
        with service.store.connection() as db:
            assert db.execute('SELECT status FROM agent_subtask WHERE id=?',(job['id'],)).fetchone()[0] == 'queued'
    asyncio.run(check())


def test_legacy_official_parent_task_routes_large_single_chat_to_content_queue(tmp_path, monkeypatch):
    service, client = setup(tmp_path, monkeypatch, Data(5))
    delegated = []
    def respond(messages):
        state = next(json.JSONDecoder().raw_decode(str(m.content).rsplit('当前执行状态（程序元数据）：', 1)[1].lstrip())[0]
            for m in messages if m.type == 'system' and '当前执行状态（程序元数据）：' in str(m.content))
        if not state['scopes']:
            return action('select_chat_scope', {'complete':True})
        scope = state['scopes'][0]
        if scope.get('pending_page'):
            page = json.loads(next(m.content for m in reversed(messages) if isinstance(m, ToolMessage) and 'page_id' in str(m.content)))
            return action('commit_findings', {'scope_handle':scope['scope_handle'], 'page_id':scope['pending_page'],
                'findings':[{'text':'原文中的局部事实', 'sources':[m['source']]} for m in page['messages']]})
        if scope.get('execution_mode') == 'parallel' and not scope['analysis_complete']:
            delegated.append(scope['scope_handle'])
            return action('task', {'scope_handle':scope['scope_handle'], 'subagent_type':'range-analyst', 'description':'完整分析全部已选聊天资料'})
        if not scope['analysis_complete']:
            return action('read_messages', {'scope_handle':scope['scope_handle']})
        return AIMessage(content='已完成分配范围，并保留原文来源。')
    client.next = respond
    async def check():
        thread = await service.create_thread('account', 'friend', '历史分片回归')
        pending = await service.submit(thread['id'], 'account', {'text': '完整分析当前聊天', 'request_id': 'legacy-partitions'})
        service.update(pending['id'], subtask_plan_version=1)
        await service.workers[pending['id']]
        public = service.public_run(pending['id'], 'account')
        assert public['status'] == 'completed', public.get('error')
        assert len(delegated) == 1
        parent = service.run(public['id'])
        summary = service.subtasks.summary(parent)
        assert summary['completed'] == summary['total'] > 1
        assert service.workspace.page(parent['id'], parent['version'], 'finding')['total'] == 5
    asyncio.run(check())
