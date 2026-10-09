"""全账号渐进索引：已提交批次即可查询，覆盖记录与任务断点一起保存。"""
import asyncio
import time
from .catalog import configured_spec, index_model_metadata


def reading_segments(usernames, starts, end, recent_seconds=30 * 86400):
    boundary = max(0, end - recent_seconds)
    recent, older = [], []
    for username in usernames:
        start = starts[username]
        if max(start, boundary) <= end:
            recent.append({'username': username, 'start': max(start, boundary), 'end': end, 'phase': 'recent'})
        if start < boundary:
            older.append({'username': username, 'start': start, 'end': boundary - 1, 'phase': 'history'})
    return recent + older


def committed_coverage(job):
    """合并同一代索引的已提交范围；不把增量窗口或有缺口区间标成全历史。"""
    active = job['config'].get('active') or {}
    previous = active.get('coverage', {}) if active.get('generation') == job['generation'] else {}
    # 设置收窄会实际裁剪索引；旧覆盖记录只在仍保留的范围内有效。
    previous = {k: {**r, 'start': max(r['start'], active.get('start', r['start'])),
                          'end': min(r['end'], active.get('end', r['end']))}
                for k, r in previous.items() if r['username'] in active.get('usernames', [])}
    allowed = set(job['config'].get('usernames', []))
    complete, partial = [], []
    for item in [*previous.values(), *job.get('coverage', {}).values()]:
        if item['username'] not in allowed:
            continue
        start, end = max(job['start'], item['start']), min(job['end'], item['end'])
        if start > end:
            continue
        # 覆盖计量是时间范围，重叠批次的 processed 不能相加作为消息总数。
        record = {'username': item['username'], 'start': start, 'end': end,
                  'complete': bool(item.get('complete')), 'warning': item.get('warning', '')}
        (complete if record['complete'] else partial).append(record)
    merged = []
    for item in sorted(complete, key=lambda r: (r['username'], r['start'], r['end'])):
        if merged and merged[-1]['username'] == item['username'] and item['start'] <= merged[-1]['end'] + 1:
            previous = merged[-1]
            previous['end'] = max(previous['end'], item['end'])
            previous['warning'] = '；'.join(dict.fromkeys(filter(None, [previous['warning'], item['warning']])))
        else:
            merged.append(item)
    for item in partial:
        if not any(r['username'] == item['username'] and r['start'] <= item['start'] and r['end'] >= item['end'] for r in merged if r['complete']):
            if item not in merged:
                merged.append(item)
    return {str(i): item for i, item in enumerate(merged)}


def coverage_complete(coverage, usernames, start, end):
    for username in usernames:
        next_time = start
        for item in sorted((r for r in coverage.values() if r['username'] == username and r['complete']), key=lambda r: r['start']):
            if item['start'] > next_time:
                break
            next_time = max(next_time, item['end'] + 1)
        if next_time <= end:
            return False
    return bool(usernames)


class ProgressiveIndex:
    async def ensure_global(self, account):
        cfg = self.config(account)
        if not cfg['enabled'] or not self.downloads.available(cfg['model']):
            return None
        jobs = self.store.list('index_job', account, limit=1)
        current_job = jobs[0] if jobs and jobs[0]['config'].get('revision') == cfg.get('revision') else None
        # 本轮聊天范围固定；新会话不能在后台刷新时改配置、打断任务或扩大总量。
        if current_job and (current_job['status'] == 'paused' or (cfg.get('agent_global') and current_job['status'] in {'queued', 'running', 'error'})):
            return current_job
        from ..ai.agent_tools import ChatTools
        contacts = await ChatTools().conversations(account)
        usernames = [c['username'] for c in contacts]
        if not usernames:
            return None
        if not cfg.get('agent_global') or set(cfg['usernames']) != set(usernames):
            cfg = await self.configure(account, {'agent_global': True, 'usernames': usernames,
                                                 'days': 0, 'start': 0, 'end': None, 'auto_update': True})
        jobs = self.store.list('index_job', account, limit=1)
        current_job = jobs[0] if jobs and jobs[0]['config'].get('revision') == cfg.get('revision') else None
        if current_job and current_job['status'] in ('paused', 'error', 'running', 'queued'):
            return current_job
        if cfg.get('active') and cfg['active'].get('revision') == cfg.get('revision') and time.time() - cfg['active'].get('updated', 0) < 60:
            return None
        return await self.build(account)

    async def yield_to_queries(self, check):
        while self.foreground_queries:
            check()
            await asyncio.sleep(.05)

    def publish_partial(self, job):
        if not job['config'].get('agent_global'):
            return
        current = self.config(job['account'])
        if current.get('revision') != job['config'].get('revision'):
            return
        coverage = committed_coverage(job)
        base = job['config'].get('active') or {}
        # 旧格式索引的范围未知，但已存在会话仍可查询；不能据此补造完整覆盖。
        existing = base.get('usernames', []) if base.get('generation') == job['generation'] else []
        usernames = set(existing) | {v['username'] for v in coverage.values()}
        current['active'] = {'generation': job['generation'], 'model': job['config']['model'],
                             **index_model_metadata(configured_spec(job['config'])),
                             'start': job['start'], 'end': job['end'], 'updated': time.time(),
                             'usernames': [u for u in job['config'].get('usernames', []) if u in usernames],
                             'coverage': coverage, 'partial': True, 'source': job.get('source'),
                             'revision': current['revision']}
        self.store.put('config', current, id=job['account'], account=job['account'])
