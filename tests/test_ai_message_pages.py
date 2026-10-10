"""连续读取的扫描量、分页一致性及游标生命周期回归。"""
import asyncio
import sqlite3
import threading
import tracemalloc
import psutil

import pytest

from wechat_decrypt_tool.ai.messages import iter_message_pages, read_messages
from wechat_decrypt_tool.local_search.service import LocalSearch


def test_time_reader_keeps_explicit_at_identity(message_source):
    from wechat_decrypt_tool.ai.agent_references import material_references, reference_id
    state = message_source(1)
    state['rows'][0].msg_source = '<msgsource><atuserlist>target</atuserlist></msgsource>'
    original = read_messages('a', 'group@chatroom', 0, 200)['messages'][0]
    assert original['media']['atUsernames'] == ['target']
    refs = material_references('a', [original], [{'username': 'target', 'name': '同名'}, {'username': 'other', 'name': '同名'}])
    assert refs[reference_id('person', 'a', 'target')]['mentioned_sources'] == [original['source']]
    assert reference_id('person', 'a', 'other') not in refs


@pytest.mark.parametrize('budget', [None, 4096])
def test_group_sender_name_matches_chat_view_without_changing_identity(message_source, monkeypatch, budget):
    from wechat_decrypt_tool import chat_helpers
    from wechat_decrypt_tool.ai.agent_budget import message_payload
    from wechat_decrypt_tool.ai.agent_references import material_references, reference_id
    message_source(1)
    monkeypatch.setattr(chat_helpers, '_load_contact_rows', lambda path, names: {u: {'remark': '联系人名称'} for u in names})
    monkeypatch.setattr(chat_helpers, '_load_group_nickname_map_from_contact_db',
                        lambda path, group, senders: {'sender': '群内名片'} if group == 'group@chatroom' else {})
    group = read_messages('a', 'group@chatroom', 0, 200, max_batch_bytes=budget)['messages'][0]
    assert group['sender'] == '群内名片'
    assert group['sender_id'] == 'sender'
    assert group['sender_aliases'] == ['群内名片', '联系人名称']
    assert message_payload(group)['sender_aliases'] == group['sender_aliases']
    refs = material_references('a', [group])
    person = refs[reference_id('person', 'a', 'sender')]
    assert person['name'] == '群内名片' and '联系人名称' in person['aliases']
    private = read_messages('a', 'private', 0, 200, max_batch_bytes=budget)['messages'][0]
    assert private['sender'] == '联系人名称' and private['sender_id'] == 'sender'
    assert 'sender_aliases' not in private


def test_search_context_and_time_reader_share_source_identity(message_source):
    from wechat_decrypt_tool.ai.agent_tools import normalize
    state = message_source(12)
    messages = read_messages('a', 'chat', 0, 200)['messages']
    for row, message in zip(state['rows'], messages):
        raw = {'id': f'{row.db_stem}:{row.table_name}:{row.local_id}', 'serverIdStr': str(row.server_id),
               'createTime': row.create_time, 'conversationUsername': 'chat', 'content': row.raw_text}
        # 时间读取按稳定身份排序，因此按身份匹配，覆盖无服务端编号的消息。
        normalized = normalize('a', '', raw)
        original = next(m for m in messages if m['text'] == row.raw_text)
        assert normalized['source'] == original['source']
        assert normalized['identity'] == original['identity']
        assert normalize('another-account', '', raw)['source'] != original['source']


def test_agent_stream_100000_messages_has_bounded_memory_and_deduplicates(message_source, ai_file_diagnostics):
    from wechat_decrypt_tool.chat_export_service import _Row
    from wechat_decrypt_tool.ai.agent_tools import ChatTools
    state = message_source(0)
    def synthetic():
        for i in range(100000):
            row = _Row('db','table',i+1,i+1,1,i,100,'合成消息内容。'*40,'sender',False)
            yield row
            if i % 1000 == 0: yield row
    state['rows'] = synthetic()
    async def run():
        count, maximum = 0, 0
        process = psutil.Process()
        baseline = peak_rss = None
        tracemalloc.start()
        try:
            async with ChatTools().open_pages('a','chat',0,200,0,lambda:None,max_batch_bytes=3276) as read:
                while True:
                    page = await read()
                    if page is None: break
                    count += len(page['messages'])
                    maximum = max(maximum,sum(len(m['text'].encode()) for m in page['messages']))
                    current_rss = process.memory_info().rss
                    if baseline is None:baseline = current_rss
                    peak_rss = max(peak_rss or current_rss,current_rss)
            _,peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert count == 100000 and maximum <= 40000
        assert peak < 8*1024*1024
        assert peak_rss-baseline < 32*1024*1024
        assert state['opens'] == state['closed'] == 1
        assert state['scanned'] == 100100
    asyncio.run(run())


@pytest.fixture
def message_source(tmp_path, monkeypatch):
    from wechat_decrypt_tool import account_source_policy, chat_export_service, chat_helpers

    state = {'rows': [], 'opens': 0, 'scanned': 0, 'closed': 0, 'threads': set()}
    monkeypatch.setattr(chat_helpers, '_resolve_account_dir', lambda _: tmp_path)
    monkeypatch.setattr(chat_helpers, '_load_contact_rows', lambda *args: {})
    monkeypatch.setattr(chat_helpers, '_resource_lookup_chat_id', lambda *args: None)
    monkeypatch.setattr(account_source_policy, 'account_prefers_decrypted_snapshot', lambda _: True)
    # 实际 SQLite 连接检查跨线程推进和关闭的问题。
    sqlite3.connect(tmp_path / 'message_resource.db').close()

    def rows(**kwargs):
        connection = sqlite3.connect(':memory:')
        state['opens'] += 1
        state['threads'].add(threading.get_ident())
        try:
            for row in state['rows']:
                if kwargs.get('start_time') is not None and row.create_time < kwargs['start_time']:
                    continue
                if kwargs.get('end_time') is not None and row.create_time > kwargs['end_time']:
                    continue
                connection.execute('SELECT 1')
                state['scanned'] += 1
                yield row
        finally:
            connection.close()
            state['closed'] += 1

    monkeypatch.setattr(chat_export_service, '_iter_rows_for_conversation', rows)
    monkeypatch.setattr(chat_export_service, '_parse_message_for_export', lambda row, **kwargs: {
        'id': str(row.local_id), 'content': row.raw_text, 'renderType': 'text', 'senderUsername': 'sender'})

    def populate(total):
        # 所有消息同秒，部分没有 server ID，且有跨页重复项。
        state['rows'] = []
        for i in range(1, total + 1):
            row = chat_export_service._Row('db', 'table', i, i if i % 3 else 0, 1, i, 100, f'消息{i}', 'sender', False)
            state['rows'].append(row)
            if i % 100 == 0:
                state['rows'].append(row)
        return state

    return populate


@pytest.mark.parametrize('total', [0, 1, 100, 101, 200, 3400])
def test_stream_reads_source_once_and_matches_messages(message_source, total):
    state = message_source(total)
    expected = read_messages('a', 'chat', 0, 200)['messages']
    state.update(opens=0, scanned=0, closed=0)
    pages = list(iter_message_pages('a', 'chat', 0, 200))
    actual = [m for page in pages for m in page['messages']]
    assert sorted(actual, key=lambda m: m['identity']) == sorted(expected, key=lambda m: m['identity'])
    # 每页内部排序与旧接口保持一致，同秒消息不能因边界去重而遗漏。
    assert len(actual) == len({m['identity'] for m in actual})
    assert all(page['has_more'] for page in pages[:-1])
    assert pages[-1]['has_more'] is False
    assert all(len(page['messages']) <= 100 for page in pages)
    assert state['opens'] == state['closed'] == 1
    assert state['scanned'] == len(state['rows'])


@pytest.mark.parametrize('start', [None, 0, 90])
@pytest.mark.parametrize('total', [0, 27, 100, 231])
def test_recent_count_pages_only_latest_unique_messages(message_source, start, total):
    message_source(total)
    pages = list(iter_message_pages('a', 'chat', start, 200, count=100, page_size=50))
    messages = [m for page in pages for m in page['messages']]
    assert len(messages) == min(total, 100)
    assert {int(m['anchor']) for m in messages} == set(range(max(1, total-99), total+1))
    assert pages[-1]['has_more'] is False
    if total > 50:
        resumed = list(iter_message_pages('a', 'chat', start, 200, count=100, page_size=50, page_offset=50))
        assert [m for page in resumed for m in page['messages']] == messages[50:]


def test_global_recent_count_uses_same_second_order_before_per_chat_limit(message_source):
    """单群先按另一种顺序取 N，会在跨群合并前丢掉应入选的同秒消息。"""
    from wechat_decrypt_tool.ai.agent_tools import ChatTools
    message_source(231)
    expected = []
    for username in ('first', 'second'):
        expected.extend(read_messages('a', username, 0, 200)['messages'])
    expected = sorted(expected, key=lambda m: (m['time'], m['source']))[-7:]
    actual = asyncio.run(ChatTools().recent_set('a', ['first', 'second'], 0, 201, 7, lambda: None))
    assert [m['source'] for m in actual['messages']] == [m['source'] for m in expected]
    reversed_order = asyncio.run(ChatTools().recent_set('a', ['second', 'first'], 0, 201, 7, lambda: None))
    assert [m['source'] for m in reversed_order['messages']] == [m['source'] for m in expected]


def test_legacy_page_matches_stream_and_closes_early(message_source):
    state = message_source(250)
    expected = list(iter_message_pages('a', 'chat', 0, 200))
    state.update(opens=0, scanned=0, closed=0)
    actual = read_messages('a', 'chat', 0, 200, page_offset=100, page_size=100)
    assert actual == expected[1]
    assert state['opens'] == state['closed'] == 1


def test_cursor_resume_skips_history_but_keeps_same_second_arrivals(message_source):
    state = message_source(350)
    for row in state['rows']:
        row.create_time = row.local_id // 10
    stream = iter_message_pages('a', 'chat', 0, 200, page_size=100, emit_cursor=True)
    first = next(stream)
    stream.close()
    cursor = first['cursor']
    assert cursor['time'] == 10
    from wechat_decrypt_tool.chat_export_service import _Row
    arrival = _Row('db', 'table', 999, 999, 1, 999, 10, '同秒补写', 'sender', False)
    state['rows'].insert(101, arrival)
    state['scanned'] = 0
    pages = list(iter_message_pages('a', 'chat', 0, 200, page_offset=100, page_size=100, cursor=cursor))
    remaining = [m for page in pages for m in page['messages']]
    assert len(remaining) == 251
    assert 's:999' in {m['identity'] for m in remaining}
    assert not ({m['identity'] for m in remaining} & {m['identity'] for m in first['messages']})
    assert state['scanned'] == sum(row.create_time >= 10 for row in state['rows'])
    assert state['scanned'] < len(state['rows'])


def test_pause_and_resume_keep_sqlite_on_reader_thread(message_source, tmp_path):
    state = message_source(350)
    expected = read_messages('a', 'chat', 0, 200)['messages']
    state.update(opens=0, scanned=0, closed=0, threads=set())

    async def run():
        service = LocalSearch(tmp_path / 'state', tmp_path / 'models')
        collected = []
        async with service.open_pages('a', 'chat', 0, 200, 0, lambda: None, page_size=100) as read:
            for _ in range(2):
                collected.extend((await read())['messages'])
        assert state['closed'] == 1
        async with service.open_pages('a', 'chat', 0, 200, len(collected), lambda: None, page_size=100) as read:
            while True:
                page = await read()
                collected.extend(page['messages'])
                if not page['has_more']:
                    break
        assert state['opens'] == state['closed'] == 2
        assert threading.get_ident() not in state['threads']
        assert sorted(collected, key=lambda m: m['identity']) == sorted(expected, key=lambda m: m['identity'])
        await service.stop()

    asyncio.run(run())


def test_consumer_failure_releases_stream(message_source, tmp_path):
    state = message_source(300)

    async def run():
        service = LocalSearch(tmp_path / 'state', tmp_path / 'models')
        with pytest.raises(RuntimeError, match='推理失败'):
            async with service.open_pages('a', 'chat', 0, 200, 0, lambda: None, page_size=100) as read:
                await read()
                raise RuntimeError('推理失败')
        assert state['opens'] == state['closed'] == 1
        await service.stop()

    asyncio.run(run())


def test_checkpoint_cancellation_releases_stream(message_source, tmp_path):
    state = message_source(300)
    cancelled = False

    def checkpoint():
        if cancelled:
            raise RuntimeError('用户暂停')

    async def run():
        nonlocal cancelled
        service = LocalSearch(tmp_path / 'state', tmp_path / 'models')
        with pytest.raises(RuntimeError, match='用户暂停'):
            async with service.open_pages('a', 'chat', 0, 200, 0, checkpoint, page_size=100) as read:
                await read()
                cancelled = True
                await read()
        assert state['opens'] == state['closed'] == 1
        await service.stop()

    asyncio.run(run())


def test_large_batch_reports_before_first_page_is_ready(message_source, monkeypatch):
    state = message_source(2000)
    from wechat_decrypt_tool.ai import messages
    clock = iter(i * 0.02 for i in range(20000))
    monkeypatch.setattr(messages.time, 'monotonic', lambda: next(clock))
    progress = []
    pages = iter_message_pages('a', 'chat', 0, 200, page_size=1000,
        on_progress=lambda count: progress.append((count, state['scanned'])))
    try:
        first = next(pages)
        assert len(first['messages']) == 1000
        assert len(progress) > 2
        assert 0 < progress[0][0] < 1000
        assert progress[0][1] < 1000
        assert [count for count, _ in progress] == sorted(count for count, _ in progress)
        assert progress[-1][0] == 1000
    finally:
        pages.close()


def test_batch_shrinks_between_pages_and_long_text_is_bounded(message_source):
    state = message_source(1250)
    sizes = iter([1000, 100, 100, 100])
    pages = list(iter_message_pages('a', 'chat', 0, 200, page_size=lambda: next(sizes)))
    assert [len(p['messages']) for p in pages] == [1000, 100, 100, 50]
    state = message_source(10)
    for row in state['rows']:
        row.raw_text = '长文本' * 20000
    pages = list(iter_message_pages('a', 'chat', 0, 200, page_size=2000))
    assert [len(p['messages']) for p in pages] == [3, 3, 3, 1]
    assert sum(len(p['messages']) for p in pages) == 10


def test_index_stream_resumes_only_committed_batches(message_source, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tokenizers import Tokenizer, models
    from wechat_decrypt_tool.local_search.catalog import model_dir
    from wechat_decrypt_tool.local_search import service as module

    state = message_source(1250)
    calls = 0

    def encode(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('第二批推理失败')
        return [[1., 0.] for _ in args[2]]

    engine = SimpleNamespace(status={'actual_device': 'cpu'}, gpu_root=None, gpu_failed=False,
        close=lambda: None, last_used=0, lock=threading.RLock(), key=None, encode=encode)
    monkeypatch.setattr(module, 'make_chunks', lambda messages, tokenizer, **kwargs: [
        {'text': '\n'.join(m['text'] for m in messages), 'sources': [m['source'] for m in messages], 'username': 'chat'}
    ] if messages else [])

    async def run():
        service = LocalSearch(tmp_path / 'state', tmp_path / 'models', engine=engine)
        emitted = []
        original_event = service.store.event
        def record(account, kind, body, unique_key=None, replace=False, transient=False):
            if kind == 'local_search_index':
                emitted.append(body)
            return original_event(account, kind, body, unique_key, replace, transient=transient)
        monkeypatch.setattr(service.store, 'event', record)
        root = model_dir(service.downloads.root, 'bge-small-zh')
        root.mkdir(parents=True)
        Tokenizer(models.WordLevel({'[UNK]': 0}, unk_token='[UNK]')).save(str(root / 'tokenizer.json'))
        monkeypatch.setattr(service.downloads, 'available', lambda _: True)
        monkeypatch.setattr(service, 'enrichment_version', lambda _: [])
        await service.configure('a', {'enabled': True, 'model': 'bge-small-zh', 'days': 0,
            'end': 200, 'usernames': ['chat'], 'read_batch_size': 500})
        job = await service.build('a')
        await service.jobs[job['id']]
        assert job['status'] == 'error' and job['processed'] == 500
        assert job['read_count'] == 1000
        assert service.index('a').progress(job['id'])['offset'] == 500
        assert state['opens'] == state['closed'] == 1
        assert service.status('a')['message_total']['value'] == 1250
        scanned = state['scanned']
        # 本轮清单已固定，恢复仅处理尚未提交的批次；源消息变化也不能触发重新扫描。
        state['rows'].clear()
        resumed = await service.resume('a', job['id'])
        await service.jobs[job['id']]
        assert resumed['status'] == 'done'
        assert resumed['processed'] == resumed['read_count'] == 1250
        assert state['opens'] == state['closed'] == 1
        assert state['scanned'] == scanned
        assert service.status('a')['message_total']['value'] == 1250
        with service.index('a').connection() as db:
            assert db.execute('SELECT count(*) FROM messages').fetchone()[0] == 1250
        events = service.store.events()
        assert any(e.get('stage') == 'reading'
            and e.get('read_count', 0) > e.get('processed', 0) for e in emitted)
        # 同一任务在事件表只保留最新一行，且不携带可重建的大字段。
        stored = [e for e in events if e['kind'] == 'local_search_index' and e['body'].get('id') == job['id']]
        assert len(stored) == 1
        assert 'config' not in stored[0]['body'] and 'segments' not in stored[0]['body'] and 'coverage' not in stored[0]['body']
        await service.stop()

    asyncio.run(run())
