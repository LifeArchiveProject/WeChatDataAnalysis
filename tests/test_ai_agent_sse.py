"""校验初次空闲连接断开后仍从原游标续读；使用真实事件存储，无模型调用。"""
import asyncio
import json
from unittest.mock import patch

from starlette.requests import Request
from test_ai_agent import service
from wechat_decrypt_tool.routers import ai_agent


def request(last_id=None):
    headers = [] if last_id is None else [(b'last-event-id', str(last_id).encode())]
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    return Request({'type': 'http', 'headers': headers}, receive=receive)


def test_idle_initial_stream_reconnect_replays_gap_without_other_account_events(service):
    async def run():
        service.store.event('account', 'agent', {'type': 'old'})
        initial_id = service.store.latest_event_id()
        with patch.object(ai_agent, 'get_agent_service', return_value=service), patch.object(ai_agent, 'account_name', side_effect=lambda value:value):
            first = await ai_agent.events(request(), 'account')
            initial = await anext(first.body_iterator)
            assert initial == f'id: {initial_id}\n\n' and 'data:' not in initial
            await first.body_iterator.aclose()
            # 初次空闲连接结束后才到达的更新，不能从重连时的“最新编号”开始而漏掉。
            service.store.event('other', 'agent', {'type': 'private'})
            service.store.event('account', 'agent', {'type': 'context_budget', 'version': 2})
            gap_id = service.store.latest_event_id()
            again = await ai_agent.events(request(initial_id), 'account')
            assert await anext(again.body_iterator) == initial
            event = await anext(again.body_iterator)
            assert f'id: {gap_id}\n' in event
            assert json.loads(event.split('data: ', 1)[1]) == {'type': 'context_budget', 'version': 2}
            assert 'private' not in event and 'old' not in event
            await again.body_iterator.aclose()
    asyncio.run(run())


def test_empty_store_keeps_zero_cursor_and_explicit_after_is_not_replaced(service):
    async def run():
        with patch.object(ai_agent, 'get_agent_service', return_value=service), patch.object(ai_agent, 'account_name', side_effect=lambda value:value):
            first = await ai_agent.events(request(), 'account')
            assert await anext(first.body_iterator) == 'id: 0\n\n'
            await first.body_iterator.aclose()
            service.store.event('account', 'agent', {'type': 'one'})
            again = await ai_agent.events(request(0), 'account', after=0)
            assert await anext(again.body_iterator) == 'id: 0\n\n'
            assert '"one"' in await anext(again.body_iterator)
            await again.body_iterator.aclose()
    asyncio.run(run())


def test_stream_waits_for_notification_instead_of_polling_and_uses_low_frequency_heartbeat(service):
    async def run():
        with patch.object(ai_agent, 'get_agent_service', return_value=service), \
                patch.object(ai_agent, 'account_name', side_effect=lambda value:value), \
                patch.object(ai_agent, 'SSE_HEARTBEAT_SECONDS', 0.03):
            response = await ai_agent.events(request(), 'account')
            assert await anext(response.body_iterator) == 'id: 0\n\n'
            calls = 0
            original = service.store.events

            def counted(*args, **kwargs):
                nonlocal calls
                calls += 1
                return original(*args, **kwargs)

            with patch.object(service.store, 'events', side_effect=counted):
                # 空闲期间只查询一次后等待通知，不再每 100ms 查询 SQLite。
                assert await asyncio.wait_for(anext(response.body_iterator), 0.5) == ': heartbeat\n\n'
                assert calls == 1
                # 通知验证的心跳要晚于断言截止时间；通知失效时应超时，而非靠心跳重查通过。
                with patch.object(ai_agent, 'SSE_HEARTBEAT_SECONDS', 2.0):
                    pending = asyncio.create_task(anext(response.body_iterator))
                    await asyncio.sleep(0)
                    service.store.event('account', 'agent', {'type': 'live'})
                    event = await asyncio.wait_for(pending, 0.5)
                    assert json.loads(event.split('data: ', 1)[1]) == {'type': 'live'}
            await response.body_iterator.aclose()
    asyncio.run(run())
