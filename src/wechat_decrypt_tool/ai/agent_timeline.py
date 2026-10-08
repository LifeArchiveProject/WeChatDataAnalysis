"""面向用户的执行记录；只保存实际动作、公开进展与可恢复状态。"""
import time
import uuid
import re
from contextlib import nullcontext
from .deep_synchronization import serialized


class AgentTimeline:
    @serialized
    def timeline_item(self, id, kind, text, *, item_id=None, status='completed', persist=True,
                      transient_event=False, run_fields=None, **fields):
        # 业务时间线、任务快照和持久事件在同一事务提交，避免一个动作多次刷盘。
        with self.store.connection() if persist else nullcontext():
            return self._timeline_item(id, kind, text, item_id=item_id, status=status, persist=persist,
                                       transient_event=transient_event, run_fields=run_fields, **fields)

    def _timeline_item(self, id, kind, text, *, item_id, status, persist, transient_event, run_fields, **fields):
        run = self.run(id)
        items = run.get('timeline') or [dict(x, seq=i+1, revision=1, kind='status') for i,x in enumerate(run.get('activity', []))]
        now = time.time()
        item = next((x for x in items if x['id'] == item_id), None)
        previous_text = item.get('text', '') if item else ''
        if (item and item.get('text') == text and item.get('status') == status
                and all(item.get(k) == v for k, v in fields.items())
                and all(run.get(k) == v for k, v in (run_fields or {}).items())):
            if persist and self.store.has_live_record('agent_run', id):
                self.update(id, emit=False, **(run_fields or {}))
                if hasattr(self, 'workspace'):
                    self.workspace.put(id, run['version'], f'timeline:{item["seq"]:012d}', 'timeline', item)
            return item['id']
        if item is None:
            item = dict(id=item_id or uuid.uuid4().hex, seq=max(run.get('timeline_seq',0),max((x.get('seq',0) for x in items),default=0)) + 1, revision=0,
                        kind=kind, started_at=now, input_version=run['version'])
            items.append(item)
        item.update(text=text, status=status, revision=item['revision'] + 1, **fields)
        if status not in ('running', 'received'):
            item['finished_at'] = now
        # 普通过程保留最近 200 步；压缩节点是持久的对话分隔，不能随步骤淘汰。
        if persist and hasattr(self,'workspace'):
            self.workspace.put(id,run['version'],f'timeline:{item["seq"]:012d}','timeline',item)
        retained = [x for i, x in enumerate(items) if i >= len(items) - 200 or
                    (x.get('kind') == 'notice' and x.get('context_job', {}).get('before') is not None)]
        self.update(id, transient=not persist, emit=False, timeline=retained,
                    timeline_seq=max(x.get('seq',0) for x in items), **(run_fields or {}))
        event = {'type':'timeline_item', 'run_id':id, 'thread_id':run['thread_id'], 'version':run['version'], 'timeline_item':item}
        if run_fields:
            current = self.run(id)
            event['updated_at'] = current['updated_at']
            # 正文仍从时间线合并，阶段信息同一个事件送达，避免额外写入 run_patch。
            event['patch'] = {key: current[key] for key in run_fields if key != 'answer'}
        if kind in ('answer', 'progress'):
            # 新标记与已校验身份同时送达，避免正文先出现、来源等待慢速快照。
            # 只发送本次新增标记，完整映射仍由运行快照和历史保存负责。
            pattern = r'\[\[(?:(?:person|image):)?[a-f0-9]{24}\]\]|[（(\[]\s*source\s*[:：]\s*[a-f0-9]{24}\s*[）)\]]'
            previous = set(re.findall(pattern, previous_text, re.I))
            added = '\n'.join(dict.fromkeys(m for m in re.findall(pattern, text, re.I) if m not in previous))
            if added:
                from .agent_references import cited_references
                event['citations'] = self.citations({**run, 'answer': added, 'timeline': [], 'answer_context': {}})
                event['references'] = cited_references(added, run.get('references', {}))
        self.store.event(run['account'], 'agent', event, transient=transient_event,
                         unique_key=f'timeline:{id}:{item["id"]}' if transient_event else None)
        return item['id']

    def close_activity(self, id, status='completed'):
        run = self.run(id)
        for item in run.get('timeline', []):
            if item['kind'] in ('tool', 'status') and item['status'] == 'running':
                self.timeline_item(id, item['kind'], item['text'], item_id=item['id'], status=status)

    def activity(self, id, text, status='running'):
        run = self.run(id)
        active = next((x for x in reversed(run.get('timeline', [])) if x['kind'] == 'tool' and x['status'] == 'running'), None)
        if active:
            self.timeline_item(id, 'tool', active['text'], item_id=active['id'], status='running', detail=text)
        else:
            self.close_activity(id)
            self.timeline_item(id, 'status', text, status=status)
        items = self.run(id).get('activity', [])
        if items and items[-1]['status'] == 'running':
            items[-1].update(status='completed', finished_at=time.time())
        items.append(dict(id=uuid.uuid4().hex, text=text, status=status, started_at=time.time()))
        self.update(id, activity=items[-100:], stage=text, stage_started_at=time.time())

    def model_feedback(self, id, data):
        self.guard(id)
        self.timeline_item(id, 'notice', data['text'], attempt=data['attempt'])
        self.update(id, stage=data['text'], stage_started_at=time.time())
        if data['phase'] == 'answer':
            run = self.run(id)
            prefix = run.get('answer_resume', '') if run.get('answer_resume_version') == run['version'] else ''
            self.update(id, answer=prefix)
            self.timeline_item(id, 'answer', prefix, item_id='answer:' + id, status='running')

    @staticmethod
    def public_timeline(run):
        if run.get('timeline'):
            return run['timeline']
        # 旧数据只有动作名称，按原记录展示，不生成不存在的旁白。
        return [dict(x, seq=i + 1, revision=1, kind='status') for i, x in enumerate(run.get('activity', []))]

    def public_thread(self, id, account):
        thread = self.thread(id, account)
        # 内部检查点和计量指纹不属于聊天展示，也不随每次轮询传给前端。
        thread.pop('history_checkpoints', None)
        thread.pop('context_meter_samples', None)
        # 账号是读取边界；旧会话筛选的版本不能改写或隐藏同账号历史回答。
        for message in thread['messages']:
            if message['role'] == 'user':
                continue
            requested = set(re.findall(r'\[\[([a-f0-9]{24})\]\]', message.get('text', ''), re.I))
            present = {c['source'] for c in message.get('citations', [])}
            typed = set(re.findall(r'\[\[(?:person|image):([a-f0-9]{24})\]\]', message.get('text', ''), re.I))
            present_refs = {r['id'] for r in message.get('references', [])}
            if not message.get('run_id') or (requested <= present and typed <= present_refs):
                continue
            original = self.store.get('agent_run', message['run_id'])
            if not original or original['account'] != account or original['thread_id'] != id:
                continue
            # 旧长报告曾截断展示来源；只从同一任务的已存原文补齐，不重写回答。
            run = self.run(original['id'], account)
            from .agent_references import cited_references
            restored_refs = cited_references(message.get('text', ''), run.get('references', {}))
            message['references'] = list({r['id']: r for r in [*restored_refs, *message.get('references', [])]}.values())
            if not requested <= present or restored_refs:
                restored = self.citations({**run, 'answer': message.get('text', ''), 'timeline': [], 'answer_context': {}})
                message['citations'] = list({c['source']: c for c in [*message.get('citations', []), *restored]}.values())
        with self.store.connection() as db:
            rows = db.execute("SELECT id, json_extract(body,'$.status'), json_extract(body,'$.created'), json_extract(body,'$.elapsed_seconds') FROM records WHERE kind='agent_run' AND account=? AND json_extract(body,'$.thread_id')=? ORDER BY json_extract(body,'$.created')", (account, id)).fetchall()
        return thread | {'runs': [dict(id=r[0], status=r[1], created=r[2], elapsed_seconds=r[3]) for r in rows]}
