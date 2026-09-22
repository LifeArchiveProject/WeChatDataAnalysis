"""本地检索任务、账号范围与设备状态的统一服务。"""
from ..ai.diagnostics import observed, event as diagnostic_event, context as diagnostic_context, new_id, executor_call, failures
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
import hashlib
from pathlib import Path
import threading
import time
import uuid

from ..ai.storage import AIStore
from ..app_paths import get_data_dir, get_output_dir
from .catalog import model_dir, model_spec
from .downloads import ModelDownloads
from .index import SemanticIndex, make_chunks, fuse
from .inference import LocalInference, InferenceFailure
from .progressive import ProgressiveIndex, reading_segments, committed_coverage, coverage_complete
from .totals import MessageTotals


DEFAULTS = {'enabled': False, 'model': None, 'usernames': [], 'days': 90,
            'start': None, 'end': None, 'device': 'auto', 'device_id': 0, 'auto_update': True,
            'read_batch_size': 0, 'agent_global': False}


class LocalSearch(ProgressiveIndex, MessageTotals):
    def __init__(self, root=None, model_root=None, reader=None, engine=None):
        self.root = Path(root or get_output_dir() / 'local_search')
        self.store = AIStore(self.root)
        self.engine = engine or LocalInference(callback=lambda status: self.store.event('', 'local_search_device', status))
        self.downloads = ModelDownloads(model_root or get_data_dir() / 'local_search_models', self.store, self.engine)
        from .gpu import GPUComponent
        self.gpu = GPUComponent(self.downloads.root.parent / 'local_search_gpu', self.store, self.engine)
        self.reader = reader
        self.jobs, self.cancelled, self.revoked, self.queries = {}, set(), set(), {}
        self.restarting=set()
        self.foreground_queries = 0
        self.queue_lock = asyncio.Lock()
        self.model_lock = asyncio.Lock()
        self.loop_task = None

    def config(self, account):
        return {**DEFAULTS, **(self.store.get('config', account) or {}), 'account': account}

    def index(self, account):
        safe = hashlib.sha256(account.encode()).hexdigest()
        return SemanticIndex(self.root / 'indexes' / (safe + '.sqlite3'))

    def status(self, account=None):
        event_cursor = self.store.latest_event_id()
        cfg = self.config(account) if account else None
        jobs = self.store.list('index_job', account, limit=5) if account else []
        result = {'config': cfg, 'models': self.downloads.models(), 'device': self.engine.status, 'jobs': jobs, 'event_cursor': event_cursor,
                  'message_total': self.store.get('index_message_total', jobs[0]['id']) if jobs else None,
                  'gpu': {**self.gpu.status(), 'failed': self.engine.gpu_failed}, 'audit': self.store.list('local_usage', account, limit=20) if account else []}
        if account:
            index = self.index(account)
            result['index_bytes'] = index.path.stat().st_size
            active = cfg.get('active') or {}
            result['index_stats'] = index.stats(active['generation']) if active.get('generation') else {'messages': 0, 'chunks': 0}
        return result

    @observed('search.configure', id_field='task_id')
    async def configure(self, account, values):
        async with self.model_lock:
            return await self._configure(account,values)

    async def _configure(self, account, values):
        self.revoked.discard(account)
        self.store.revoked_accounts.discard(account)
        old = self.config(account)
        cfg = {**old, **values, 'account': account}
        if cfg['model'] is not None: model_spec(cfg['model'])
        if cfg['enabled'] and not self.downloads.available(cfg['model']):
            raise ValueError('请先下载并选择可用的本地模型')
        # 重复保存相同设置不使断点失效，也不打断后台任务。
        if all(cfg.get(key) == old.get(key) for key in DEFAULTS):
            return old
        cfg['revision'] = old.get('revision', 0) + 1
        self.store.put('config', cfg, id=account, account=account)
        # 范围或设备变更后，旧任务不得继续提交过期配置。
        await self.pause_account(account)
        await asyncio.to_thread(self.clear_message_plans, account)
        if cfg.get('active'):
            start=cfg['start'] if cfg['start'] is not None else max(0,int(time.time())-cfg['days']*86400) if cfg['days'] else 0
            await asyncio.to_thread(self.index(account).prune,cfg['active']['generation'],cfg['usernames'],start,cfg['end'] or 2**53)
            # 清理后同步实际覆盖范围，防止先缩小再扩大时把已删除内容误判为可复用。
            active = cfg['active']
            cfg['active'] = {**active, 'usernames': [u for u in active.get('usernames', []) if u in cfg['usernames']],
                             'start': max(active.get('start', start), start),
                             'end': min(active.get('end', cfg['end'] or 2**53), cfg['end'] or 2**53)}
            if 'coverage' in active:
                cfg['active']['coverage'] = committed_coverage({'config': cfg, 'generation': active['generation'],
                    'start': cfg['active']['start'], 'end': cfg['active']['end']})
            self.store.put('config', cfg, id=account, account=account)
        self.queries.clear()
        return cfg

    def update(self, job, **changes):
        job.update(changes, updated=time.time())
        if job['id'] in self.restarting: job['resume_on_start']=True
        if job['account'] in self.revoked: return
        self.store.put('index_job', job, id=job['id'], account=job['account'])
        self.store.event(job['account'], 'local_search_index', job)

    def enrichment_version(self, account):
        """只检查本地提取缓存，不触发媒体分析或网络访问。"""
        import sqlite3
        values = []
        path = get_output_dir() / 'ai' / 'ai.sqlite3'
        if path.exists():
            with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
                values.append(db.execute("SELECT coalesce(max(updated),0) FROM records WHERE kind='local_media_text' AND account=?", (account,)).fetchone()[0])
        try:
            from ..chat_helpers import _resolve_account_dir
            path = _resolve_account_dir(account) / '_cache/voice_transcripts.sqlite3'
            if path.exists():
                with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
                    values.append(db.execute('SELECT coalesce(max(updated_at),0) FROM transcript').fetchone()[0])
        except (ValueError, OSError, sqlite3.Error):
            pass
        return values

    def local_text(self, account, messages):
        import sqlite3, json
        path = get_output_dir() / 'ai' / 'ai.sqlite3'
        if not path.exists(): return
        with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
            for m in messages:
                if m['kind'] != 'file': continue
                id = hashlib.sha256(f"{account}:{m['username']}:{m['anchor']}".encode()).hexdigest()
                row = db.execute("SELECT body FROM records WHERE kind='local_media_text' AND id=? AND account=?", (id,account)).fetchone()
                if row:
                    m['local_attachment_text'] = json.loads(row[0])['text']

    @observed('search.build', id_field='task_id')
    async def build(self, account, rebuild=False, incremental=True):
        # 后台调度和前台提问可能同时触发；创建任务与配置更新共用锁。
        async with self.model_lock:
            return await self._build(account, rebuild, incremental)

    async def _build(self, account, rebuild=False, incremental=True):
        cfg = self.config(account)
        if not cfg['enabled']: raise ValueError('请先启用本地语义检索')
        if not cfg['usernames']: raise ValueError('请选择需要建立索引的聊天')
        if not self.downloads.available(cfg['model']): raise ValueError('检索模型尚未下载完成')
        for id, task in self.jobs.items():
            job = self.store.get('index_job', id)
            if not task.done() and job and job['account'] == account: return job
        end = min(cfg['end'] or int(time.time()), int(time.time()))
        start = cfg['start'] if cfg['start'] is not None else max(0, end - cfg['days'] * 86400) if cfg['days'] else 0
        active = cfg.get('active') or {}
        new_generation = rebuild or active.get('model') != cfg['model'] or not active.get('generation')
        generation = uuid.uuid4().hex if new_generation else active['generation']
        enrichment = await asyncio.to_thread(self.enrichment_version, account)
        # 增量保留同秒和短期补写窗口；旧转写/附件变化或每天一次校对重读范围。
        recent_only = incremental and not new_generation and enrichment == active.get('enrichment') and time.time()-active.get('reconciled',0)<86400
        # 按聊天判断覆盖范围；新增聊天或向前扩展历史必须补齐，设备设置不影响复用。
        read_starts = {username: max(start, active.get('end', start)-600)
                       if recent_only and username in active.get('usernames', []) and start >= active.get('start', start)
                       else start for username in cfg['usernames']}
        reason = ('rebuild' if rebuild else 'initial' if new_generation else
                  'manual_check' if not incremental else 'enrichment' if enrichment != active.get('enrichment') else
                  'reconcile' if not recent_only else 'incremental')
        read_start = min(read_starts.values())
        job = {'id': uuid.uuid4().hex, 'account': account, 'config': cfg, 'generation': generation,
               'trace_id': diagnostic_context.get().get('trace_id') or new_id(),
               'read_start': read_start, 'read_starts': read_starts, 'mode': reason,
               'incremental': recent_only, 'enrichment': enrichment,
               'start': start, 'end': end, 'chat_index': 0, 'offset': 0, 'processed': 0,
               'embedded': 0, 'unchanged': 0, 'status': 'queued', 'stage': 'queued', 'started': time.time(), 'warning': '', 'error': ''}
        if cfg.get('agent_global'):
            job['segments'] = reading_segments(cfg['usernames'], read_starts, end)
            job['coverage'] = {}
        self.update(job)
        self.jobs[job['id']] = asyncio.create_task(self.run(job))
        return job

    @observed('search.resume', id_field='task_id')
    async def resume(self, account, id):
        job = self.store.get('index_job', id)
        if not job or job['account'] != account: raise ValueError('任务不存在')
        if job['config']['revision'] != self.config(account).get('revision'):
            raise ValueError('配置已改变，请按当前范围重新建立索引')
        if id in self.jobs and not self.jobs[id].done(): return job
        saved = self.index(account).progress(id)
        if saved: job.update(saved)
        self.cancelled.discard(id)
        job.pop('finished', None)
        self.update(job, status='queued', error='')
        self.jobs[id] = asyncio.create_task(self.run(job))
        return job

    @observed('search.pause_account', id_field='task_id')
    async def pause_account(self, account):
        for id, task in list(self.jobs.items()):
            job = self.store.get('index_job', id)
            if job and job['account'] == account and not task.done():
                self.cancelled.add(id)
                if job['status']=='queued':
                    task.cancel()
                    self.update(job,status='paused',stage='paused',finished=time.time())
                else:
                    self.update(job,stage='pausing')
                await asyncio.gather(task, return_exceptions=True)

    @asynccontextmanager
    async def open_pages(self, account, username, start, end, offset, checkpoint, page_size=0, on_progress=None, on_batch_size=None, cursor=None, frozen=None):
        """在专用线程中顺序推进和关闭游标，避免线程池切换破坏 SQLite 连接。"""
        from ..ai.messages import iter_message_pages
        from .reading import choose_read_batch_size
        closing = threading.Event()

        def check():
            if closing.is_set():
                raise InferenceFailure('读取已停止', 'cancelled')
            checkpoint()

        def batch_size():
            size = choose_read_batch_size(page_size)
            if on_batch_size:
                loop.call_soon_threadsafe(on_batch_size, size)
            return size

        def pages():
            if frozen:
                plan, segment = frozen
                position = offset
                while True:
                    result = plan.page(segment, position, batch_size(), check)
                    position += len(result['messages'])
                    if on_progress:
                        loop.call_soon_threadsafe(on_progress, position)
                    yield result
                    if not result['has_more']:
                        return
            elif self.reader:
                # 保留可注入的分页数据源，进度仍按事务提交的消息数量计算。
                position = offset
                while True:
                    check()
                    result = self.reader(account, username, start, end, position)
                    yield result
                    if not result.get('has_more', False):
                        return
                    position += len(result['messages'])
            else:
                yield from iter_message_pages(account, username, start, end,
                    page_offset=offset, page_size=batch_size, checkpoint=check,
                    cursor=cursor, emit_cursor=True,
                    on_progress=(lambda count: loop.call_soon_threadsafe(on_progress, count)) if on_progress else None)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='local-search-reader')
        loop = asyncio.get_running_loop()
        stream = pages()
        try:
            yield lambda: executor_call(executor, next, stream, None)
        finally:
            closing.set()
            try:
                # 关闭排在正在进行的读取之后，取消时也不得从别的线程销毁游标。
                await asyncio.shield(executor_call(executor, stream.close))
            finally:
                executor.shutdown(wait=False)

    @observed('search.run', id_field='task_id', execution=True)
    async def run(self, job):
        cfg, account = job['config'], job['account']
        plan = None
        def cancelled(): return job['id'] in self.cancelled or account in self.revoked
        def check():
            if cancelled(): raise InferenceFailure('任务已暂停', 'cancelled')
        async with self.queue_lock:
            try:
                check()
                from tokenizers import Tokenizer
                spec = model_spec(cfg['model'])
                root = model_dir(self.downloads.root, cfg['model'])
                tokenizer = Tokenizer.from_file(str(root / 'tokenizer.json'))
                index = self.index(account)
                self.update(job, status='running', read_count=job['processed'], embedded_count=job['embedded'])
                plan = await self.count_message_total(job, check)
                segments = job.get('segments')
                targets = segments or [{'username': username,
                    'start': job.get('read_starts', {}).get(username, job.get('read_start', job['start'])),
                    'end': job['end']} for username in cfg['usernames']]

                async def encode_chunks(chunks, embedded_base):
                    vectors = []
                    last_embedding_update = time.monotonic()
                    if chunks:
                        self.update(job, stage='embedding')
                    for batch_start in range(0, len(chunks), 8):
                        check()
                        await self.yield_to_queries(check)
                        batch = chunks[batch_start:batch_start + 8]
                        strategy = cfg['device']
                        # 语音任务占用显卡时，本地索引主动让出。
                        try:
                            from ..voice_transcription import _VOICE_MODEL_ACTIVITY
                            if any(_VOICE_MODEL_ACTIVITY.values()):
                                strategy = 'cpu'
                        except ImportError:
                            pass
                        diagnostic_event('index.batch.started', index=batch_start, batch_size=len(batch), strategy=strategy,
                                         reason_code='voice_priority' if strategy != cfg['device'] else 'configured')
                        values = await asyncio.to_thread(self.engine.encode, root, spec, [c['text'] for c in batch],
                                                         strategy, cfg['device_id'], False, cancelled)
                        diagnostic_event('index.batch.finished', index=batch_start, count=len(values),
                                         actual_device=self.engine.status.get('actual_device'))
                        vectors.extend(values)
                        if len(vectors) == len(chunks) or time.monotonic() - last_embedding_update >= 0.25:
                            self.update(job, embedded_count=embedded_base + len(vectors))
                            last_embedding_update = time.monotonic()
                    return vectors

                for position in range(job['chat_index'], len(segments) if segments is not None else len(cfg['usernames'])):
                    segment = segments[position] if segments is not None else None
                    username = segment['username'] if segment else cfg['usernames'][position]
                    offset = job['offset'] if position == job['chat_index'] else 0
                    read_start = segment['start'] if segment else job.get('read_starts', {}).get(username, job.get('read_start', job['start']))
                    read_end = segment['end'] if segment else job['end']
                    read_base = job['processed'] - offset

                    def reading_progress(count):
                        # 展示读取中的真实数量，只有事务提交才能推进断点 processed/offset。
                        total = read_base + count
                        if not cancelled() and job['stage'] == 'reading' and total > job.get('read_count', 0):
                            self.update(job, read_count=total)

                    def batch_size_changed(size):
                        if not cancelled() and job.get('read_batch_size_effective') != size:
                            self.update(job, read_batch_size_effective=size)

                    async with self.open_pages(account, username, read_start, read_end, offset, check,
                            page_size=cfg.get('read_batch_size', 0), on_progress=reading_progress,
                            on_batch_size=batch_size_changed, cursor=job.get('cursor') if offset else None,
                            frozen=(plan, position)) as next_page:
                        while True:
                            check()
                            await self.yield_to_queries(check)
                            self.update(job, stage='reading', current_chat=username)
                            page_started = time.monotonic()
                            diagnostic_event('index.page.started', username=username, offset=offset, start=read_start, end=job['end'])
                            result = await next_page()
                            check()
                            messages = result['messages']
                            diagnostic_event('index.page.finished', username=username, offset=offset, count=len(messages), has_more=result.get('has_more',False), duration_ms=(time.monotonic()-page_started)*1000)
                            await self.yield_to_queries(check)
                            for m in messages:
                                raw = m.get('media') or {}
                                m['sender_id'] = raw.get('senderUsername') or m.get('sender', '')
                                m['name'] = result.get('name', username)
                            await asyncio.to_thread(self.local_text, account, messages)
                            await self.yield_to_queries(check)
                            self.update(job, stage='organizing', read_count=job['processed'] + len(messages))
                            unchanged = await asyncio.to_thread(index.existing, job['generation'], messages)
                            changed = await asyncio.to_thread(index.affected_messages, job['generation'], [m for m in messages if m['source'] not in unchanged])
                            chunks = await asyncio.to_thread(make_chunks, changed, tokenizer)
                            diagnostic_event('index.page.organized', count=len(changed), unchanged=len(unchanged), chunks=len(chunks))
                            vectors = await encode_chunks(chunks, job['embedded'])
                            check()
                            more = result.get('has_more', False)
                            next_job = {**job, 'chat_index': position if more else position + 1,
                                        'offset': offset + len(messages) if more else 0,
                                        'cursor': result.get('cursor') if more else None,
                                        'processed': job['processed'] + len(messages), 'embedded': job['embedded'] + len(chunks),
                                        'unchanged': job.get('unchanged', 0) + len(unchanged),
                                        'warning': result.get('warning', ''), 'source': result.get('source', 'snapshot')}
                            next_job['coverage'] = {**job.get('coverage', {}), str(position): {
                                'username': username, 'start': read_start, 'end': read_end,
                                'last_time': result.get('cursor', {}).get('time') if result.get('cursor') else None,
                                'processed': offset + len(messages), 'complete': not more,
                                'warning': result.get('warning', '')}}
                            self.update(job, stage='saving')
                            await asyncio.to_thread(index.commit, job['generation'], changed, chunks, vectors, next_job, check)
                            job.update(next_job)
                            self.publish_partial(job)
                            self.update(job)
                            if not more: break
                            offset += len(messages)
                check()
                frozen_total = (await asyncio.to_thread(plan.metadata))['total']
                if job['processed'] != frozen_total:
                    raise InferenceFailure('本轮消息清单与已保存数量不一致，已保留进度，请重试。', 'count_mismatch')
                current = self.config(account)
                if current.get('revision') != cfg.get('revision'): raise InferenceFailure('配置已更新', 'cancelled')
                if not job.get('incremental'):
                    scopes = await asyncio.to_thread(plan.reconciliation_scopes, targets)
                    reconciliation = await asyncio.to_thread(index.reconciliation, job['generation'], plan.path, scopes)
                    if reconciliation['missing']:
                        changed = reconciliation['messages']
                        chunks = await asyncio.to_thread(make_chunks, changed, tokenizer)
                        vectors = await encode_chunks(chunks, job['embedded'])
                        next_job = {**job, 'embedded': job['embedded'] + len(chunks),
                                    'removed': job.get('removed', 0) + reconciliation['missing']}
                        self.update(job, stage='saving')
                        await asyncio.to_thread(index.commit, job['generation'], changed, chunks, vectors,
                                                next_job, check, plan.path)
                        job.update(next_job)
                        diagnostic_event('index.reconcile.finished', generation=job['generation'],
                                         dropped_count=reconciliation['missing'], count=len(changed), chunks=len(chunks))
                # 完成清理、范围约束和统计后才发布成功状态。
                await asyncio.to_thread(index.prune, job['generation'], cfg['usernames'], job['start'], job['end'])
                stats = await asyncio.to_thread(index.stats, job['generation'])
                coverage = committed_coverage(job) if cfg.get('agent_global') else job.get('coverage', {})
                current['active'] = {'generation': job['generation'], 'model': cfg['model'], 'start': job['start'],
                                     'end': job['end'], 'usernames': cfg['usernames'], 'updated': time.time(), 'source': job.get('source'),
                                     'revision': cfg['revision'], 'enrichment': job.get('enrichment'),
                                     'coverage': coverage,
                                     'partial': cfg.get('agent_global', False) and not coverage_complete(coverage, cfg['usernames'], job['start'], job['end']),
                                     'reconciled': cfg.get('active',{}).get('reconciled',time.time()) if job.get('incremental') else time.time()}
                self.store.put('config', current, id=account, account=account)
                await asyncio.to_thread(index.clear, job['generation'])
                self.update(job, status='done', stage='done', index_stats=stats, finished=time.time())
                try:
                    await asyncio.to_thread(plan.discard)
                except OSError as error:
                    failures.report('search.plan.cleanup', error)
            except InferenceFailure as error:
                diagnostic_event('index.execution.interrupted' if error.category=='cancelled' else 'index.execution.failed',
                                 level=logging.INFO if error.category=='cancelled' else logging.ERROR, error=error)
                self.update(job, status='paused' if error.category == 'cancelled' else 'error', error=str(error), finished=time.time())
            except Exception as error:
                diagnostic_event('index.execution.failed', level=logging.ERROR, error=error)
                self.update(job, status='error', error='索引处理失败，已保留进度，请检查数据源和模型后重试', error_type=type(error).__name__, finished=time.time())
            finally:
                if account in self.revoked:
                    await asyncio.to_thread(self.clear_message_plans, account)
                self.store.put('local_usage', {'kind': 'index', 'account': account, 'model': cfg['model'], 'status':job['status'],
                    'messages': job['processed'], 'chunks': job['embedded'], 'seconds': time.time()-job['started'], **self.engine.status},id=job['id'],account=account)

    @observed('search.hybrid', id_field='task_id')
    async def hybrid(self, account, keyword, q, usernames, start=None, end=None, sender=None, kinds=None, offset=0, limit=50, ticket=None):
        cfg = self.config(account)
        active = cfg.get('active') or {}
        allowed = set(cfg['usernames']) & set(active.get('usernames', [])) & set(usernames)
        warning = ''
        if not cfg['enabled'] or not active or not allowed:
            diagnostic_event('search.keyword.fallback', reason_code='disabled' if not cfg['enabled'] else 'scope_not_indexed')
            return {**keyword, 'retrievalMode': 'keyword', 'coverage': {'message': '本地语义索引尚未覆盖所选范围，当前展示关键词结果'}}
        key = (account, cfg.get('revision'), q, tuple(sorted(usernames)), start, end, sender, tuple(kinds or []))
        reset_search=False
        if offset and not ticket:
            ticket = next((k for k,v in reversed(list(self.queries.items())) if v['key']==key and v['expires']>time.time()),None)
        if ticket:
            cached = self.queries.get(ticket)
            key = (account, cfg.get('revision'), q, tuple(sorted(usernames)), start, end, sender, tuple(kinds or []))
            if cached and cached['key'] == key and cached['expires'] > time.time():
                diagnostic_event('search.ticket.hit', ticket_id=ticket, offset=offset, cached=True)
                return {**cached['response'], 'hits': cached['hits'][offset:offset+limit], 'hasMore': offset+limit < len(cached['hits']), 'resetSearch':False}
            reset_search=bool(offset)
            diagnostic_event('search.ticket.expired', offset=offset, cached=False)
            offset=0
        began = time.monotonic()
        snapshot_keyword, committed_keyword_hits = keyword, []
        self.foreground_queries += 1
        try:
            scope_start = cfg['start'] if cfg['start'] is not None else max(0, int(time.time())-cfg['days']*86400) if cfg['days'] else 0
            query_start, query_end = max(start or 0, scope_start), min(end if end is not None else 2**53, cfg['end'] if cfg['end'] is not None else 2**53)
            index = self.index(account)
            def as_hit(m):
                return {**m.get('media', {}), 'id': m['anchor'], 'anchorId': m['anchor'], 'username': m['username'],
                        'conversationName': m.get('name', m['username']), 'senderDisplayName': m['sender'],
                        'senderUsername': m.get('sender_id', m['sender']), 'createTime': m['time'],
                        # 索引正文已经包含标题、引用和转写；AI 适配器不能再次拼接这些字段。
                        'content': m['text'], 'aiText': m['text'], 'snippet': m['text'], 'renderType': m['kind']}
            literal = await asyncio.to_thread(index.keyword, active['generation'], q, sorted(allowed), query_start, query_end, sender, kinds, 200)
            # 渐进索引里的新消息可能尚未进入旧全文索引，原文命中必须独立于向量召回。
            committed_keyword_hits = [as_hit(m) for m in literal]
            keyword = {**keyword, 'hits': fuse([*committed_keyword_hits, *keyword.get('hits', [])], [])}
            spec = model_spec(active['model'])
            root = model_dir(self.downloads.root, active['model'])
            vectors = await asyncio.to_thread(self.engine.encode, root, spec, [q], cfg['device'], cfg['device_id'], True)
            rows = await asyncio.to_thread(index.search, active['generation'], vectors[0], sorted(allowed), query_start, query_end, sender, kinds, 200)
            semantic = [as_hit(row['message']) for row in rows]
            # 同一片段内的消息共享向量分数；直接匹配原文的消息应先于相邻闲聊。
            needle = q.strip().casefold()
            if needle:
                semantic.sort(key=lambda hit: needle not in hit['content'].casefold())
            hits = fuse(keyword.get('hits', []), semantic)
            diagnostic_event('search.recall.finished', keyword_count=len(keyword.get('hits',[])), semantic_count=len(semantic), returned=len(hits), actual_device=self.engine.status.get('actual_device'))
            coverage = {'message': '语义结果来自已建立的本地索引；新消息、未解析图片和范围外历史可能尚未覆盖。',
                        'start': active['start'], 'end': active['end'], 'updated': active['updated'],
                        'partial': bool(active.get('partial')) or bool(set(usernames)-allowed) or len(rows) >= 200 or len(literal) >= 200,
                        'ranges': active.get('coverage', {}), 'source': active.get('source')}
            ticket = uuid.uuid4().hex
            response = {**keyword, 'retrievalMode': 'hybrid', 'coverage': coverage, 'total': len(hits), 'searchTicket': ticket,
                        'device': self.engine.status, 'status': 'success', 'resetSearch':reset_search}
            key = (account, cfg.get('revision'), q, tuple(sorted(usernames)), start, end, sender, tuple(kinds or []))
            self.queries = {k:v for k,v in self.queries.items() if v['expires'] > time.time()}
            if len(self.queries) >= 32: self.queries.pop(next(iter(self.queries)))
            self.queries[ticket] = {'key': key, 'response': response, 'hits': hits, 'expires': time.time()+600}
            self.store.put('local_usage', {'kind':'search','account':account,'model':active['model'],'candidates':len(hits),
                'seconds':time.monotonic()-began,**self.engine.status}, account=account)
            return {**response, 'hits': hits[offset:offset+limit], 'hasMore': offset+limit<len(hits)}
        except Exception as error:
            diagnostic_event('search.keyword.fallback', level=logging.WARNING, error=error, reason_code='semantic_failed')
            self.store.put('local_usage',{'kind':'search','account':account,'model':active.get('model'),'status':'error',
                'seconds':time.monotonic()-began,'error_type':type(error).__name__,**self.engine.status},account=account)
            # 旧全文结果已经按 offset 分页，不能再对它重复切片。
            fallback_hits = fuse([*committed_keyword_hits[offset:offset+limit], *snapshot_keyword.get('hits', [])], [])
            return {**keyword, 'hits': fallback_hits[:limit],
                    'total': max(snapshot_keyword.get('total', 0), len(committed_keyword_hits), offset + len(fallback_hits)),
                    'hasMore': offset + limit < len(committed_keyword_hits) or len(fallback_hits) > limit or bool(snapshot_keyword.get('hasMore')),
                    'retrievalMode':'keyword','coverage':{'message':'语义检索暂不可用，当前展示关键词结果，请检查本地模型'}}
        finally:
            self.foreground_queries -= 1

    @observed('search.clear', id_field='task_id')
    async def clear(self, account):
        await self.pause_account(account)
        cfg = self.config(account)
        cfg.pop('active', None)
        if not cfg['enabled']: cfg['model']=None
        self.store.put('config', cfg, id=account, account=account)
        await asyncio.to_thread(self.index(account).clear)
        await asyncio.to_thread(self.clear_message_plans, account)
        self.queries.clear()

    @observed('search.purge', id_field='task_id')
    def purge(self, account):
        self.revoked.add(account)
        active = False
        for job in self.store.list('index_job',account):
            self.cancelled.add(job['id'])
            active |= job['id'] in self.jobs and not self.jobs[job['id']].done()
        self.store.purge_account(account)
        self.index(account).clear()
        self.queries.clear()
        if not active:
            self.clear_message_plans(account)

    @observed('search.start', id_field='task_id')
    async def start(self):
        for job in self.store.list('index_job'):
            if job['status'] in {'queued','running'} or job.get('resume_on_start'):
                try:
                    job.pop('resume_on_start',None)
                    self.update(job,status='paused')
                    await self.resume(job['account'],job['id'])
                except ValueError:
                    self.update(job, status='paused', error='配置已改变，请按当前范围重新建立索引')
        for job in self.store.list('download'):
            if job['status'] in {'queued','running'} or job.get('resume_on_start'): await self.downloads.start(job['id'])
        gpu_job = self.store.get('gpu_component','global') or {}
        if gpu_job.get('status') in {'queued','running'} or gpu_job.get('resume_on_start'): await self.gpu.start()
        self.loop_task = asyncio.create_task(self.schedule())

    async def schedule(self):
        while True:
            await asyncio.sleep(60)
            try:
                if time.monotonic()-self.engine.last_used>300 and self.engine.lock.acquire(blocking=False):
                    try: self.engine.close()
                    finally: self.engine.lock.release()
                for cfg in self.store.list('config'):
                    if not cfg['enabled'] or not cfg['auto_update']: continue
                    # 已开启自动更新的旧配置也迁移为全账号，不必等用户首次提问。
                    # ensure_global 保留显式暂停、检查模型可用性并只发布已提交覆盖。
                    try:
                        await self.ensure_global(cfg['account'])
                    except ValueError as error: failures.report('search.schedule.'+cfg['account'], error)
                failures.recovered('search.scheduler')
            except Exception as error:
                failures.report('search.scheduler', error)

    @observed('search.stop', id_field='task_id')
    async def stop(self):
        if self.loop_task:
            self.loop_task.cancel()
            await asyncio.gather(self.loop_task, return_exceptions=True)
        for id,task in self.jobs.items():
            if not task.done():
                self.cancelled.add(id)
                job=self.store.get('index_job',id)
                if job and job['status'] in {'running','queued'}:
                    self.restarting.add(id)
                    self.update(job,resume_on_start=True)
                    if job['status']=='queued':
                        task.cancel()
                        self.update(job,status='paused',stage='paused')
        await asyncio.gather(*self.jobs.values(), return_exceptions=True)
        downloading=[id for id,task in self.downloads.tasks.items() if not task.done()]
        await self.downloads.stop()
        for id in downloading:
            job=self.store.get('download',id)
            if job: self.downloads.update(job,resume_on_start=True)
        gpu_running=self.gpu.task and not self.gpu.task.done()
        await self.gpu.pause()
        if gpu_running: self.gpu.update(resume_on_start=True)
        self.engine.close()


_service = None


@contextmanager
def prioritize_foreground():
    """仅协调当前已运行的索引；嵌套查询、异常及取消都准确归还计数。"""
    service = _service
    if service is not None:
        service.foreground_queries += 1
    try:
        yield
    finally:
        if service is not None:
            service.foreground_queries -= 1


def get_local_search():
    global _service
    if _service is None: _service = LocalSearch()
    return _service
