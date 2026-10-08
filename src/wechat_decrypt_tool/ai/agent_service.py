"""微信 Agent 任务服务：唯一生产执行引擎为官方 DeepAgents。"""
import asyncio
import json
import logging
import re
import time
import uuid
from .diagnostics import observed, event as diagnostic_event
from .agent_timeline import AgentTimeline
from .agent_schemas import AgentControl
from .agent_tools import ChatTools
from .agent_workspace import Workspace, Evidence
from .deep_runtime import DeepAgentRuntime
from .deep_projection import DeepProjection
from .providers import ProviderFailure

class Revised(AgentControl):
    pass

ACTIVE = {'queued', 'running'}
STREAM_PATCH_FIELDS = {
    'stage', 'stage_started_at', 'segment_started', 'finished_at', 'elapsed_seconds',
    'error', 'error_info', 'used', 'read_count', 'index_status', 'query_scope',
    'query_filters', 'time_range', 'intent', 'coverage_state', 'subtasks', 'choices',
    'answer_context', 'needs_continuation', 'can_resume', 'restart_required',
    'context_compaction',
}

from .deep_synchronization import serialized


class AgentService(DeepAgentRuntime, DeepProjection, AgentTimeline):
    def __init__(self, ai, tools=None, model=None):
        self.ai, self.store = ai, ai.store
        self.tools = tools or ChatTools()
        # 兼容外部测试夹具的构造参数；生产模型请求只经过 DeepChatModel。
        self.model = model
        self.workers = {}
        self.locks = {}
        self.stopping = False
        self.workspace = Workspace(self.store)
        self.readers = {}
        self.index_workers = {}
        self.reference_contacts = {}
        self._draft_saved_at = {}
        from .deep_subtasks import DeepSubtasks
        self.subtasks = DeepSubtasks(self)

    def settings(self):
        # 兼容旧客户端读取；历史额度不再参与执行。
        return {'unlimited': True, 'context_source': 'models.dev'}

    def thread(self, id, account):
        record = self.store.get('agent_thread', id)
        if not record or record['account'] != account:
            raise ValueError('对话不存在')
        return record

    def run(self, id, account=None):
        record = self.store.get('agent_run', id)
        if not record or (account is not None and record['account'] != account):
            raise ValueError('任务不存在')
        evidence = self.workspace.evidence(id)
        if record.get('evidence'):
            for key,value in record['evidence'].items(): evidence[key]=value
            record.pop('evidence')
            self.store.put('agent_run',record)
        record['evidence'] = evidence
        return record

    @serialized
    def update(self, id, *, transient=False, emit=True, **fields):
        with self.store.lock if transient else self.store.connection():
            return self._update(id, transient=transient, emit=emit, **fields)

    def _update(self, id, *, transient, emit, **fields):
        record = self.run(id)
        values = fields.pop('evidence',None)
        if values is not None and not isinstance(values,Evidence):
            record['evidence'].replace(values)
        record.pop('evidence',None)
        if all(record.get(key) == value for key, value in fields.items()) and not self.store.has_live_record('agent_run', id):
            return self.run(id)
        record.update(fields, updated_at=time.time())
        self.store.put('agent_run', record, transient=transient)
        if 'version' in fields or 'status' in fields:
            diagnostic_event('agent.run.state', run_id=id, thread_id=record['thread_id'], version=record['version'], status=record['status'])
        event = {'type': 'run_patch', 'run_id': id, 'thread_id': record['thread_id'], 'status': record['status'],
                 'version': record['version'], 'updated_at': record['updated_at']}
        patch = {key: record.get(key) for key in STREAM_PATCH_FIELDS if key in fields}
        # 新版本开始时必须立即清空旧回答；非空回答由带修订号的 timeline_item 传输，
        # 避免每个字符同时产生两份累计正文。
        if 'answer' in fields and not record.get('answer'):
            patch['answer'] = ''
        if 'context_budget' in fields:
            event['context_budget'] = record['context_budget']
        if 'analysis' in fields:
            state = record.get('analysis') or {}
            event['coverage'] = {'run_id': id, 'version': record['version'],
                                 'complete': state.get('complete', False),
                                 'conversations': state.get('coverage', [])}
            patch['analysis'] = {
                'coverage': state.get('coverage', []),
                'segments': state.get('segments', 0),
                'complete': state.get('complete', False),
                'known': bool(state),
                'mode': record.get('intent', {}).get('mode', 'search'),
                'findings': state.get('findings', 0),
                'analyzed': sum(item.get('analyzed', 0) for item in state.get('coverage', [])),
                'tracked': state.get('tracked', True),
            }
        if patch:
            event['patch'] = patch
        if emit and (patch or any(key in fields for key in ('context_budget', 'analysis', 'status', 'version'))):
            self.store.event(record['account'], 'agent', event, transient=transient,
                             unique_key=f'run_patch:{id}' if transient else None)
        return self.run(id)

    @serialized
    def stream_answer(self, id, text, stage):
        """实时正文只推送内存事件；每两秒及终态保存可恢复草稿。"""
        run = self.guard(id)
        now = time.monotonic()
        key = (id, run['version'])
        saved_at = self._draft_saved_at.setdefault(key, now)
        persist = now - saved_at >= 2.0
        self.timeline_item(id, 'answer', text, item_id='answer:' + id, status='running',
                           persist=persist, transient_event=True, run_fields={'answer': text, 'stage': stage})
        if persist:
            self._draft_saved_at[key] = now

    def guard(self, id):
        run = self.run(id)
        if self.stopping or run['status'] not in ACTIVE:
            raise asyncio.CancelledError()
        if run.get('parent_run_id'):
            parent = self.guard(run['parent_run_id'])
            if parent['version'] != run['parent_version']:
                raise Revised()
        return run

    @serialized
    def spend(self, id, kind, amount=1):
        run = self.guard(id)
        used = run['used']
        used[kind] = used.get(kind, 0) + amount
        self.update(id, used=used)
        diagnostic_event('agent.usage.consumed', run_id=id, kind=kind, count=used[kind])

    @observed('agent.edit_thread', id_field='thread_id')
    async def edit_thread(self, id, account, title=None, scope=None):
        async with self.locks.setdefault(id, asyncio.Lock()):
            thread = self.thread(id, account)
            if title is not None:
                thread['title'] = title
            if scope is not None:
                allowed = {x['username'] for x in await self.tools.conversations(account)}
                if not scope or not set(scope) <= allowed:
                    raise ValueError('会话范围无效')
                thread.update(scope=list(dict.fromkeys(scope)), scope_revision=thread['scope_revision'] + 1)
                if thread['latest_run']:
                    run = self.run(thread['latest_run'])
                    if run['status'] in ACTIVE:
                        self.update(run['id'], version=run['version'] + 1)
            return self.store.put('agent_thread', thread)

    async def prepare_global_index(self, account, run_id):
        from ..local_search.service import get_local_search
        try:
            service = get_local_search()
            job = await service.ensure_global(account)
            config = service.config(account)
            available = config['enabled'] and service.downloads.available(config['model'])
            status = (job or {}).get('status', 'ready' if available else 'unavailable')
            message = '当前使用基础搜索，可在 AI 设置启用已下载的本地语义模型。'
            if available:
                message = {'paused': '语义索引已暂停，已保存部分和基础搜索仍可使用。',
                           'error': '语义索引遇到错误并已保留进度，基础搜索仍可使用；可在 AI 设置检查后继续。',
                           'ready': '已保存的语义索引可查询，后台会继续检查新增消息。',
                           'done': '本次索引任务已结束，覆盖范围以已保存记录为准。'}.get(status,
                               '语义索引在后台渐进补齐，基础搜索可立即使用。')
            self.update(run_id, index_status={'run_id': run_id, 'enabled': bool(available),
                'status': status,
                'coverage': (config.get('active') or {}).get('coverage', {}),
                'partial': (config.get('active') or {}).get('partial', True),
                'message': message})
        except Exception as exc:
            diagnostic_event('agent.index.preparation.failed', level=logging.WARNING, error=exc, account=account)

    def launch(self, id):
        if id not in self.workers or self.workers[id].done():
            self.workers[id] = asyncio.create_task(self.execute(id))

    @observed('agent.stop_run', id_field='run_id')
    async def stop_run(self, id, account):
        run = self.run(id, account)
        if run['status'] not in ACTIVE:
            return run
        self.finish(id, 'cancelled', '已停止，已查资料已保留。')
        worker = self.workers.get(id)
        if worker and not worker.done():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        return self.run(id)

    def profile(self, run, vision=False):
        snapshot = run['vision' if vision else 'profile']
        if not snapshot:
            return {}
        # 只读取当前凭据；图片能力来自实际选中模型的快照，而非服务的默认模型。
        live = self.ai.models.resolve(snapshot['id'])
        return snapshot | {'api_key': live.get('api_key', '')}

    @observed('agent.finish', id_field='run_id')
    @serialized
    def finish(self, id, status, error='', error_info=None):
        with self.store.connection():
            return self._finish(id, status, error, error_info)

    def _finish(self, id, status, error, error_info):
        run = self.store.get('agent_run', id)
        if not run:
            return
        self._draft_saved_at = {key: value for key, value in self._draft_saved_at.items() if key[0] != id}
        if status == 'completed' and run.get('delegation_partial'):
            status = 'interrupted'
            error = '部分子任务未完成，当前为阶段结果，可继续分析。'
        # 停止后到达的读取错误不能再次结算，或把已停止状态改成失败。
        # 正常继续会重置 finished_at，因此仍可结算下一段运行。
        if run.get('status') not in ACTIVE and run.get('finished_at') is not None:
            return run
        if hasattr(self.tools, 'release_read_session'):
            self.tools.release_read_session(id)
        self.close_activity(id, 'completed' if status in ('completed', 'needs_input') else 'failed' if status == 'failed' else 'paused')
        for item in self.run(id).get('timeline', []):
            if item['kind'] == 'answer' and item['status'] == 'running':
                self.timeline_item(id, 'answer', item['text'], item_id=item['id'], status='completed' if status == 'completed' else 'incomplete')
        items = run.get('activity', [])
        if items and items[-1]['status'] == 'running':
            items[-1].update(status='completed' if status == 'completed' else 'paused' if status in ('budget', 'interrupted', 'cancelled', 'needs_input') else 'failed', finished_at=time.time())
        now = time.time()
        run = self.update(id, status=status, error=error, error_info=error_info, finished_at=now, activity=items,
                          elapsed_seconds=run.get('elapsed_seconds', 0) + max(0, now - run['segment_started']))
        diagnostic_event('agent.run.terminal', level=logging.ERROR if status=='failed' else logging.INFO, run_id=id,
                         status=status, version=run['version'], read_count=run['read_count'], seconds=run['elapsed_seconds'],
                         diagnostic_id=(error_info or {}).get('diagnostic_id'))
        thread = self.thread(run['thread_id'], run['account'])
        if status in ('completed', 'needs_input'):
            message = dict(id=f'answer:{id}', role='assistant', text=run['answer'], run_id=id, created=now,
                           scope_revision=thread['scope_revision'], citations=self.citations(run))
            from .agent_references import cited_references
            message['references'] = cited_references(run['answer'], run.get('references', {}))
            thread['messages'] = [m for m in thread['messages'] if m['id'] != message['id']] + [message]
            self.store.put('agent_thread', thread)
        # 终态通过 SSE 一次补齐用量、覆盖、错误和全部引用。运行中继续使用小增量，
        # 前端无需再用高频 GET 快照追赶最终状态。
        snapshot = self.public_run(id, run['account'])
        final_fields = {
            'answer', 'error', 'error_info', 'finished_at', 'elapsed_seconds', 'used',
            'read_count', 'index_status', 'query_scope', 'query_filters', 'time_range',
            'intent', 'analysis', 'usage', 'source_count', 'coverage_warnings',
            'coverage_state', 'subtasks', 'choices', 'can_resume', 'restart_required',
            'answer_context', 'needs_continuation',
        }
        self.store.event(run['account'], 'agent', {
            'type': 'run_snapshot',
            'run_id': id,
            'thread_id': run['thread_id'],
            'status': snapshot['status'],
            'version': snapshot['version'],
            'updated_at': snapshot['updated_at'],
            'patch': {key: snapshot.get(key) for key in final_fields if key in snapshot},
            'citations': snapshot.get('citations', []),
            'references': snapshot.get('references', []),
        })
        return self.run(id)

    def citations(self, run):
        # 过程消息也会引用较早读到的资料，不能只返回最终答案和前 20 条来源。
        texts = [run.get('answer', '')] + [item.get('text', '') for item in run.get('timeline', []) if item.get('kind') == 'progress']
        pattern = r'\[\[([a-fA-F0-9]{24})\]\]|[（(\[]\s*source\s*[:：]\s*([a-fA-F0-9]{24})\s*[）)\]]'
        requested = list(dict.fromkeys((a or b).lower() for text in texts for a, b in re.findall(pattern, text, re.I)))
        requested += [s['source'] for s in (run.get('answer_context') or {}).get('sources',[])]
        from .agent_references import cited_references
        for ref in cited_references('\n'.join(texts), run.get('references', {})):
            if ref['kind'] == 'person':
                # 正文引用全部保留；仅用于人物点击兜底的资料取代表消息，
                # 不把该人物的全部历史消息塞进每次流式刷新。
                requested.extend(ref.get('mentioned_sources', [])[:1])
                requested.extend(ref.get('sources', [])[:1])
            else:
                requested.append(ref['source'])
        values = {x['source']:self.public_source(x, run['account']) for x in run['evidence'].rows(limit=20)}
        # 长报告可能引用超过 200 条消息；逐批取全，不能把合法出处截断成“待核实”。
        originals = run['evidence'].get_many(requested)
        for source in dict.fromkeys(requested):
            if source in originals:
                values[source] = self.public_source(originals[source], run['account'])
        return list(values.values())

    def public_run(self, id, account):
        run = self.run(id, account)
        modern = run.get('engine_version') == 3
        run.update(engine='deepagents' if modern else 'legacy', can_resume=modern and run['status'] not in ('completed', 'needs_input'),
                   restart_required=not modern and run['status'] != 'completed',
                   coverage_state=run.get('coverage_state', 'unknown'))
        self.thread(run['thread_id'],account)
        # 旧范围字段只作历史兼容；同账号已保存回答和来源始终可读。
        with self.store.connection() as db:
            totals = db.execute("SELECT count(*), coalesce(sum(json_extract(body,'$.usage.input_tokens')),0), coalesce(sum(json_extract(body,'$.usage.output_tokens')),0), coalesce(sum(CASE WHEN json_extract(body,'$.usage_known')=1 THEN 0 ELSE 1 END),0) FROM records WHERE kind='usage' AND account=? AND json_extract(body,'$.task_id')=?", (account,id)).fetchone()
        usage = dict(zip(('calls','input_tokens','output_tokens','unknown'),totals))
        groups, warnings = {}, []
        for observation in run['observations']:
            if observation.get('warning'):
                warnings.append(observation['warning'])
            if 'username' in observation and 'has_more' in observation:
                groups[(observation['username'], observation.get('start'), observation.get('end'), observation.get('query', ''))] = observation
        # 完整任务的完成状态来自持久化逐条覆盖，早期分页有下一页不代表最终仍未读。
        # 工具实际失败和附件缺失等 warning 继续单独保留。
        analysis = run.get('analysis') or {}
        if not analysis.get('complete') and (any(o.get('has_more') for o in groups.values()) or analysis):
            warnings.append('部分范围仍有未读取的消息，当前回答仅依据已读取资料。')
        warnings.extend(c['warning'] for c in run.get('analysis',{}).get('coverage',[]) if c.get('warning'))
        from .agent_references import cited_references
        refs = cited_references('\n'.join([run.get('answer', '')] + [x.get('text', '') for x in run.get('timeline', [])]), run.get('references', {}))
        return {k: v for k, v in run.items() if k not in ('evidence', 'profile', 'vision', 'tool_cache', 'pending_actions', 'analysis', 'references', 'active_material', 'pending_material', 'answer_resume')} | {'references': refs} | {'citations': self.citations(run), 'usage': usage, 'timeline': self.public_timeline(run), 'coverage_warnings':list(dict.fromkeys(warnings)), 'analysis': self.public_analysis(run), 'source_count':len(run['evidence'])}

    @observed('agent.stop', id_field='run_id')
    async def stop(self):
        self.stopping = True
        for worker in self.index_workers.values():
            worker.cancel()
        await asyncio.gather(*self.index_workers.values(), return_exceptions=True)
        for worker in self.workers.values():
            worker.cancel()
        await asyncio.gather(*self.workers.values(), return_exceptions=True)

    @observed('agent.cancel_account', id_field='run_id')
    def cancel_account(self, account):
        workers = []
        for run in self.store.list('agent_run', account):
            worker = self.workers.get(run['id'])
            if worker and not worker.done():
                workers.append(worker)
        if not workers:
            return
        loop = workers[0].get_loop()
        if not loop.is_running():
            raise RuntimeError('Agent 事件循环已停止，无法确认任务退出')
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            raise RuntimeError('账号清理不能在 Agent 事件循环中同步等待')

        async def stop_workers():
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        asyncio.run_coroutine_threadsafe(stop_workers(), loop).result(timeout=30)


_agent = None


def get_agent_service():
    global _agent
    if _agent is None:
        from .service import get_ai_service
        _agent = AgentService(get_ai_service())
    return _agent
