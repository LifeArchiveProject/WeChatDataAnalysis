"""通用执行可靠性：统计/分析隔离、可恢复错误、断流以及子任务接力。"""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from test_ai_deepagents import make_service, action, last_result, execute
from test_ai_deep_contracts import prepared
from wechat_decrypt_tool.ai.deep_model import DeepChatModel
from wechat_decrypt_tool.ai.deep_runtime import RuntimeEvents, CHILD_SCOPE
from wechat_decrypt_tool.ai.providers import ProviderFailure


def test_statistics_then_full_analysis_has_independent_cursor(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        service.update(gateway.id, input_digest='完整分析聊天并统计总量')
        scope = await gateway.select(mode='statistics')
        tools = {t.name: t for t in gateway.tools()}
        stats = await tools['count_messages'].ainvoke({'scope_handle': scope['scope_handle']})
        assert stats['complete'] and not stats['analysis_complete']
        assert not gateway.validate_complete()
        assert service.run(gateway.id)['analysis']['coverage'][0]['analyzed'] == 0
        page = await tools['read_messages'].ainvoke({'scope_handle': scope['scope_handle']})
        assert page['scope_handle'] != scope['scope_handle']
        assert page['requires_commit'] and len(page['messages']) == 1
        assert not gateway.validate_complete()
        await tools['commit_findings'].ainvoke({'scope_handle': page['scope_handle'], 'page_id': page['page_id'],
            'findings': [{'text': '报价100元', 'sources': [page['messages'][0]['source']]}]})
        assert gateway.validate_complete()
        # 再次计数复用统计游标，不增加原文读取。
        reads = service.tools.calls.count('read')
        await tools['count_messages'].ainvoke({'scope_handle': scope['scope_handle']})
        assert service.tools.calls.count('read') == reads
    asyncio.run(check())


def test_optional_commit_does_not_fail_or_claim_analysis(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        scope = await gateway.select()
        page = await gateway.read_next(scope['scope_handle'])
        result = gateway.commit(scope['scope_handle'], page['page_id'], [])
        assert result['saved'] is False and not result['requires_commit']
        assert service.run(gateway.id)['analysis']['segments'] == 0
    asyncio.run(check())


def test_optional_invalid_quote_is_dropped_without_repeating_batch(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        scope = await gateway.select(complete=True)
        page = await gateway.read_next(scope['scope_handle'])
        findings = [{'text': '报价100元', 'sources': ['a' * 24], 'quote': '报价100元'} for _ in range(9)]
        findings.append({'text': '报价100元', 'sources': ['a' * 24], 'quote': '概括的引文'})
        result = gateway.commit(scope['scope_handle'], page['page_id'], findings)
        assert result['saved'] and result['findings'] == 10 and result['dropped_quote_count'] == 1
        assert '附加引文' in result['note']
        assert gateway.progress_state()[0]['pending_page'] is None
        assert gateway.get(f'finding:{page["page_id"]}:00000')['quote'] == '报价100元'
        saved = gateway.get(f'finding:{page["page_id"]}:00009')
        assert saved == {'text': '报价100元', 'sources': ['a' * 24]}
        assert gateway.get('note:' + page['page_id'])['items'][-1] == saved
        assert findings[-1]['quote'] == '概括的引文'
        assert gateway.commit(scope['scope_handle'], page['page_id'], findings)['reused']
        assert gateway.scope(scope['scope_handle'])['committed_pages'] == 1
        assert gateway.validate_complete()
    asyncio.run(check())


def test_graph_continues_after_discarding_optional_quote(tmp_path, monkeypatch):
    def commit(messages):
        page = last_result(messages)
        return action('commit_findings', {'scope_handle': page['scope_handle'], 'page_id': page['page_id'],
            'findings': [{'text': '报价100元', 'sources': ['a' * 24], 'quote': '报价200元'}]})

    def answer(messages):
        result = last_result(messages)
        assert result['saved'] and result['dropped_quote_count'] == 1
        return AIMessage(content='报价100元。[[aaaaaaaaaaaaaaaaaaaaaaaa]]')

    service, _ = make_service(tmp_path, monkeypatch, responses=[
        action('select_chat_scope', {'complete': True}),
        lambda messages: action('read_messages', {'scope_handle': last_result(messages)['scope_handle']}),
        commit, answer,
    ])

    async def check():
        _, run = await execute(service, '完整总结聊天里的报价')
        assert run['status'] == 'completed', run.get('error')
        commits = [item for item in run['timeline'] if item.get('action') == 'commit_findings']
        assert len(commits) == 1 and commits[0]['status'] == 'completed'
        assert commits[0]['result']['dropped_quote_count'] == 1
        assert '附加引文' in commits[0]['result']['note']
        assert '200' not in run['answer']

    asyncio.run(check())


def test_commit_retry_timeline_preserves_page_identity_and_error(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)

    async def check():
        gateway = await prepared(service)
        scope = await gateway.select(complete=True)
        page = await gateway.read_next(scope['scope_handle'])
        events = RuntimeEvents(service, gateway)

        async def handler(request):
            # 调用真实提交校验，确认失败未落库、成功后页面只推进一次。
            running = service.run(gateway.id)['timeline'][-1]
            assert running['status'] == 'running'
            assert running['page_id'] == page['page_id']
            assert running['scope_handle'] == page['scope_handle']
            args = request.tool_call['args']
            result = gateway.commit(args['scope_handle'], args['page_id'], args['findings'])
            return ToolMessage(content=json.dumps(result), tool_call_id=request.tool_call['id'])

        for call_id, source in [('first', 'not-in-page'), ('retry', page['messages'][0]['source'])]:
            args = {'scope_handle': page['scope_handle'], 'page_id': page['page_id'],
                    'findings': [{'text': '报价100元', 'sources': [source]}]}
            request = SimpleNamespace(tool_call={'id': call_id, 'name': 'commit_findings', 'args': args})
            result = await events.awrap_tool_call(request, handler)
            if call_id == 'first':
                assert result.status == 'error'
                assert not gateway.get(page['page_id']).get('committed')
                assert gateway.scope(page['scope_handle'])['committed_pages'] == 0
            else:
                assert json.loads(result.content)['saved'] is True

        # 读取持久化记录，覆盖刷新和历史详情，原始失败不改写成成功。
        run = service.store.get('agent_run', gateway.id)
        commits = [item for item in run['timeline'] if item.get('action') == 'commit_findings']
        assert [item['status'] for item in commits] == ['failed', 'completed']
        for item in commits:
            assert item['scope_handle'] == page['scope_handle']
            assert item['page_id'] == page['page_id']
            assert item['input_version'] == gateway.version
            assert gateway.get(f'timeline:{item["seq"]:012d}') == item
        assert '来源不属于本页' in commits[0]['result']['error']
        assert commits[1]['result']['saved'] is True
        assert commits[1]['result']['findings'] == 1
        assert gateway.scope(page['scope_handle'])['committed_pages'] == 1

    asyncio.run(check())


def test_repeat_detection_allows_distinct_errors_and_new_pages(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        scope = await gateway.select()
        events = RuntimeEvents(service, gateway)
        async def handler(request):
            raise ValueError('参数不正确')
        for i in range(4):
            request = SimpleNamespace(tool_call={'id': str(i), 'name': 'search_messages', 'args': {'query': str(i), 'scope_handle': scope['scope_handle']}})
            result = await events.awrap_tool_call(request, handler)
            assert result.status == 'error'
            assert 'recovery' in json.loads(result.content)
        for _ in range(2):
            await events.awrap_tool_call(request, handler)
        with pytest.raises(ProviderFailure, match='未推进'):
            await events.awrap_tool_call(request, handler)
        await gateway.read_next(scope['scope_handle'])
        assert (await events.awrap_tool_call(request, handler)).status == 'error'
    asyncio.run(check())


@pytest.mark.parametrize('fault', ['connection', 'sdk_connection', 'malformed_tool', 'timeout'])
def test_unexposed_tool_calls_retry_without_duplicate_fragments(tmp_path, monkeypatch, fault):
    service, client = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        attempts = []
        if fault == 'timeout':
            # 首次请求挂起以触发真实超时；不能要求 CI 上的 SQLite 和正常重试在半秒内完成。
            monkeypatch.setattr('wechat_decrypt_tool.ai.deep_model.MODEL_ATTEMPT_SECONDS', 5)
        async def stream(messages, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                yield AIMessageChunk(content='', tool_call_chunks=[{'name': 'select_chat_scope', 'args': '{', 'id': 'bad', 'index': 0}])
                if fault == 'connection':
                    raise httpx.RemoteProtocolError('测试断流')
                if fault == 'sdk_connection':
                    import httpx2
                    raise httpx2.RemoteProtocolError('SDK 传输层断流')
                if fault == 'timeout':
                    try:
                        await asyncio.Event().wait()
                    finally:
                        # 当前尝试的截止时间已经固定，下一次尝试应获得独立且充足的期限。
                        monkeypatch.setattr('wechat_decrypt_tool.ai.deep_model.MODEL_ATTEMPT_SECONDS', 30)
                yield AIMessageChunk(content='', tool_call_chunks=[{'name': None, 'args': 'invalid', 'id': None, 'index': 0}])
                return
            if fault == 'timeout':
                # 正常重试也允许超过旧的 0.5 秒阈值，模拟慢速 CI 的调度及持久化开销。
                await asyncio.sleep(.6)
            yield AIMessageChunk(content='', tool_calls=[{'name': 'select_chat_scope', 'args': {}, 'id': 'good', 'type': 'tool_call'}])
        client.astream = stream
        model = DeepChatModel(service=service, run_id=gateway.id, input_version=gateway.version).bind_tools(gateway.tools())
        response = await model.ainvoke([HumanMessage(content='查询')])
        assert len(attempts) == 2
        assert len(response.tool_calls) == 1 and response.tool_calls[0]['id'] == 'good'
        assert not response.invalid_tool_calls
        audits = service.store.list('usage', 'account')
        assert any(a.get('status') == 'failed' and a.get('output_exposed') is False for a in audits)
        if fault == 'timeout':
            assert any(a.get('error_type') == 'TimeoutError' for a in audits)
    asyncio.run(check())


def test_visible_text_disconnect_is_not_blindly_replayed(tmp_path, monkeypatch):
    service, client = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        attempts = []
        async def stream(messages, **kwargs):
            attempts.append(1)
            yield AIMessageChunk(content='已显示的正文')
            raise httpx.RemoteProtocolError('测试断流')
        client.astream = stream
        model = DeepChatModel(service=service, run_id=gateway.id, input_version=gateway.version)
        chunks = []
        with pytest.raises(ProviderFailure):
            async for chunk in model.astream([HumanMessage(content='回答')]):
                chunks.append(chunk.content)
        assert attempts == [1] and ''.join(chunks) == '已显示的正文'
    asyncio.run(check())


def test_invalid_findings_report_all_positions_without_committing_page(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        scope = await gateway.select(complete=True)
        page = await gateway.read_next(scope['scope_handle'])
        findings = [{'text': '本页事实', 'sources': ['a' * 24], 'quote': '不是逐字原文'},
            {'text': '错误引用', 'sources': ['b' * 24]}, {'text': '另一处错误', 'sources': ['c' * 24]}]
        with pytest.raises(ValueError) as error:
            gateway.commit(scope['scope_handle'], page['page_id'], findings)
        assert '第 2 项' in str(error.value) and '第 3 项' in str(error.value)
        assert 'b' * 24 in str(error.value) and 'c' * 24 in str(error.value)
        assert '一次性提交本页全部发现' in str(error.value)
        assert gateway.scope(scope['scope_handle'])['pending_page'] == page['page_id']
        assert not gateway.get(page['page_id']).get('committed')
        assert gateway.get(f'finding:{page["page_id"]}:00000') is None
        assert gateway.get('note:' + page['page_id']) is None
        findings[1]['sources'] = findings[2]['sources'] = ['a' * 24]
        result = gateway.commit(scope['scope_handle'], page['page_id'], findings)
        assert result['saved'] and result['findings'] == 3
    asyncio.run(check())


def test_child_reuses_parent_pending_page_and_reports_live_progress(tmp_path, monkeypatch):
    service, client = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        scope = await gateway.select(complete=True)
        page = await gateway.read_next(scope['scope_handle'])
        reads = service.tools.calls.count('read')
        handle = scope['scope_handle']
        def inspect_and_commit(messages):
            result = last_result(messages)
            assert result['page_id'] == page['page_id']
            item = service.subtasks.page(gateway.id, 'account')['items'][0]
            assert item['coverage']['read'] == 1 and item['coverage']['analyzed'] == 0
            assert item['latest_progress']['text'] == '我正在接手已读取的页面。'
            assert item['objective'] == '分析分配范围'
            assert any(t['kind'] == 'tool' for t in item['activity'])
            assert item['model_running'] and item['action_started_at']
            return action('commit_findings', {'scope_handle': handle, 'page_id': page['page_id'], 'findings': []})
        opening = action('select_chat_scope', {})
        opening.content = '我正在接手已读取的页面。'
        client.responses = [opening, action('read_messages', {'scope_handle': handle}),
            inspect_and_commit, AIMessage(content='已分析分配范围。')]
        token = CHILD_SCOPE.set({'parent_id': gateway.id, 'scope': gateway.scope(handle), 'role': 'range-analyst', 'call_id': 'handoff'})
        try:
            await service.deep_child({'messages': [HumanMessage(content='分析分配范围')]})
        finally:
            CHILD_SCOPE.reset(token)
        assert service.tools.calls.count('read') == reads
        assert gateway.validate_complete()
        item = service.subtasks.page(gateway.id, 'account')['items'][0]
        assert item['status'] == 'completed' and item['coverage']['analyzed'] == 1
        assert item['latest_progress']['text'] == '我正在接手已读取的页面。' and not item['model_running']
        child_request = client.requests[-4]
        assert any('select_chat_scope_args' in str(m.content) for m in child_request)
    asyncio.run(check())


def test_missing_context_anchor_preserves_original_and_does_not_abort(tmp_path, monkeypatch):
    from fastapi import HTTPException
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        scope = await gateway.select()
        page = await gateway.read_next(scope['scope_handle'])
        async def missing(*args):
            raise HTTPException(status_code=404, detail='Anchor message not found.')
        service.tools.context = missing
        tool = next(t for t in gateway.tools() if t.name == 'read_context')
        result = await tool.ainvoke({'scope_handle': scope['scope_handle'], 'source': page['messages'][0]['source']})
        assert not result['context_available'] and result['warning']
        assert result['messages'][0]['text'] == '报价100元'
        assert result['data_source'] == 'saved_original'
    asyncio.run(check())


def test_stats_for_other_chat_cannot_satisfy_full_analysis(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch)
    async def check():
        gateway = await prepared(service)
        service.update(gateway.id, input_digest='完整分析所有聊天')
        async def directory(account):
            return [{'username': 'friend', 'name': '好友'}, {'username': 'other', 'name': '同事'}]
        service.tools.conversations = directory
        stats = await gateway.select(all_chats=True, mode='statistics')
        tool = next(t for t in gateway.tools() if t.name == 'count_messages')
        await tool.ainvoke({'scope_handle': stats['scope_handle']})
        scope = await gateway.select(conversations=['friend'], complete=True)
        page = await gateway.read_next(scope['scope_handle'])
        gateway.commit(scope['scope_handle'], page['page_id'], [])
        assert not gateway.validate_complete()
    asyncio.run(check())


def test_source_gap_pauses_full_report_without_repeating_completed_pages(tmp_path, monkeypatch):
    service, client = make_service(tmp_path, monkeypatch)
    original = service.tools.read
    async def snapshot(*args, **kwargs):
        return {**await original(*args, **kwargs), 'warning': '实时源不可用，仅读取快照'}
    service.tools.read = snapshot
    client.responses = [action('select_chat_scope', {}),
        lambda m: action('read_messages', {'scope_handle': last_result(m)['scope_handle']}),
        lambda m: action('commit_findings', {'scope_handle': last_result(m)['scope_handle'],
            'page_id': last_result(m)['page_id'], 'findings': []}),
        AIMessage(content='可用快照提到报价100元；实时数据暂不可用。')]
    async def check():
        _, run = await execute(service, '完整分析所有聊天')
        assert run['status'] == 'interrupted' and run['needs_source_refresh']
        assert run['used']['models'] == 4 and service.tools.calls.count('read') == 1
        assert not run['analysis']['complete'] and '阶段草稿' in run['answer']
        service.update(run['id'], status='queued')
        service.refresh_source_gaps(run['id'])
        from wechat_decrypt_tool.ai.deep_tools import ChatGateway
        gateway = ChatGateway(service, run['id'], run['version'])
        state = gateway.scopes()[0]
        assert not state['read_complete'] and not state['warnings']
        service.tools.read = original
        page = await gateway.read_next(state['handle'])
        gateway.commit(state['handle'], page['page_id'], [])
        assert gateway.validate_complete()
        assert len(service.run(run['id'])['evidence']) == 1
    asyncio.run(check())


def test_snapshot_warning_prevents_claiming_full_live_coverage():
    from wechat_decrypt_tool.ai.deep_validation import coverage_claim_issues
    run = {'analysis': {'coverage': [{'warning': '实时源不可用'}]}}
    assert coverage_claim_issues('已读完该时间范围内的全部消息。9月7日之后就无消息记录。', run)
    assert not coverage_claim_issues('在已读取的快照中未发现后续消息，不能证明实时没有新消息。', run)
    assert not coverage_claim_issues('已读完全部消息。', {'analysis': {'coverage': [{'warning': ''}]}})


def test_retry_classifier_handles_sdk_wrappers_but_not_authentication():
    from openai import APIConnectionError, AuthenticationError
    from wechat_decrypt_tool.ai.deep_model import transient_model_error
    request = httpx.Request('POST', 'https://example.invalid')
    assert transient_model_error(APIConnectionError(request=request))
    assert not transient_model_error(AuthenticationError('无效配置', response=httpx.Response(401, request=request), body=None))
    assert not transient_model_error(ValueError('请求参数无效'))
