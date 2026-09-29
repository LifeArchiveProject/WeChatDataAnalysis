"""先准备完整消息快照，再发布固定总量；暂停继续不重新统计或更改分母。"""
import asyncio
import hashlib
import time

from .frozen import FrozenMessages
from .inference import InferenceFailure


class MessageTotals:
    def save_message_total(self, job, **values):
        total = {'job_id': job['id'], 'updated': time.time(), **values}
        self.store.put('index_message_total', total, id=job['id'], account=job['account'])
        self.store.event(job['account'], 'local_search_total', total, unique_key=f'index_total:{job["id"]}', replace=True)

    def message_plan(self, job):
        account_key = hashlib.sha256(job['account'].encode()).hexdigest()
        job_key = hashlib.sha256(job['id'].encode()).hexdigest()
        path = self.root / 'plans' / account_key / f'{job_key}.sqlite3'
        previous = self.store.get('index_message_total', job['id']) or {}
        if previous.get('fixed') and not path.exists():
            raise InferenceFailure('本轮消息清单已丢失，请从头整理；原有索引仍保留。', 'plan_missing')
        plan = FrozenMessages(path, job)
        if previous.get('fixed') and not plan.metadata()['ready']:
            raise InferenceFailure('本轮消息清单不完整，请从头整理；原有索引仍保留。', 'plan_missing')
        return plan

    async def count_message_total(self, job, check):
        plan = await asyncio.to_thread(self.message_plan, job)
        metadata = await asyncio.to_thread(plan.metadata)
        if metadata['ready']:
            self.save_message_total(job, status='ready', value=metadata['total'], fixed=True, estimated=False)
            return plan
        self.save_message_total(job, status='counting')
        self.update(job, stage='counting')
        targets = job.get('segments')
        if targets is None:
            targets = [{'username': username,
                        'start': job.get('read_starts', {}).get(username, job.get('read_start', job['start'])),
                        'end': job['end']} for username in job['config']['usernames']]
        try:
            for position in range(metadata['start_index'], len(targets)):
                await self.yield_to_queries(check)
                check()
                state = await asyncio.to_thread(plan.segment, position)
                if state['complete']:
                    continue
                target = targets[position]
                async with self.open_pages(job['account'], target['username'], target['start'], target['end'],
                        state['offset'], check, page_size=job['config'].get('read_batch_size', 0),
                        cursor=state['cursor']) as next_page:
                    while True:
                        await self.yield_to_queries(check)
                        check()
                        result = await next_page()
                        check()
                        await asyncio.to_thread(plan.append, position, result, check)
                        if not result.get('has_more', False):
                            break
            check()
            metadata = await asyncio.to_thread(plan.freeze, len(targets))
            self.save_message_total(job, status='ready', value=metadata['total'], fixed=True, estimated=False)
            return plan
        except InferenceFailure:
            self.save_message_total(job, status='paused')
            raise
        except Exception as error:
            self.save_message_total(job, status='unavailable')
            raise InferenceFailure('消息总量统计未完成，已保留统计进度，请继续整理以重试。', 'count_failed') from error

    def clear_message_plans(self, account):
        account_key = hashlib.sha256(account.encode()).hexdigest()
        directory = self.root / 'plans' / account_key
        for path in directory.glob('*.sqlite3'):
            path.unlink(missing_ok=True)
