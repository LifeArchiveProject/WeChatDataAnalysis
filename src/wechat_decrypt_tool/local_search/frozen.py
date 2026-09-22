"""本轮消息快照：分页落盘、精确计数，统计完成后不再访问变化中的消息源。"""
from contextlib import contextmanager
import json
import sqlite3


class FrozenMessages:
    def __init__(self, path, job):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, body TEXT);
                CREATE TABLE IF NOT EXISTS segments(position INTEGER PRIMARY KEY, body TEXT);
                CREATE TABLE IF NOT EXISTS messages(segment INTEGER, ordinal INTEGER, source TEXT, body TEXT,
                    PRIMARY KEY(segment,ordinal), UNIQUE(segment,source));
                CREATE INDEX IF NOT EXISTS messages_source ON messages(source);
                CREATE TABLE IF NOT EXISTS reconcile(source TEXT PRIMARY KEY);
            ''')
            if not self._get(db, 'plan'):
                self._put(db, 'plan', {'job_id': job['id'], 'base': job['processed'],
                    'start_index': job['chat_index'], 'start_offset': job['offset'],
                    'start_cursor': job.get('cursor'), 'ready': False})

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute('PRAGMA cache_size=-1024')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _get(db, key):
        row = db.execute('SELECT body FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _put(db, key, value):
        db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def metadata(self):
        with self.connection() as db:
            return self._get(db, 'plan')

    def segment(self, position):
        with self.connection() as db:
            row = db.execute('SELECT body FROM segments WHERE position=?', (position,)).fetchone()
            if row:
                return json.loads(row[0])
            plan = self._get(db, 'plan')
            offset = plan['start_offset'] if position == plan['start_index'] else 0
            return {'offset': offset, 'ordinal': offset, 'complete': False,
                    'cursor': plan['start_cursor'] if position == plan['start_index'] else None}

    def append(self, position, result, checkpoint):
        state = self.segment(position)
        with self.connection() as db:
            if self._get(db, 'plan')['ready']:
                raise ValueError('本轮消息范围已固定，不能追加消息')
            for index, message in enumerate(result['messages']):
                if index % 100 == 0:
                    checkpoint()
                inserted = db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?)',
                    (position, state['ordinal'] + 1, message['source'], json.dumps(message, ensure_ascii=False)))
                if inserted.rowcount:
                    state['ordinal'] += 1
            warning = '；'.join(dict.fromkeys(filter(None, [state.get('warning', ''), result.get('warning', '')])))
            state.update(offset=state['offset'] + len(result['messages']), cursor=result.get('cursor'),
                complete=not result.get('has_more', False), name=result.get('name', ''),
                source=result.get('source', 'snapshot'), warning=warning)
            checkpoint()
            db.execute('INSERT OR REPLACE INTO segments VALUES(?,?)',
                       (position, json.dumps(state, ensure_ascii=False)))

    def freeze(self, segment_count):
        with self.connection() as db:
            plan = self._get(db, 'plan')
            if not plan['ready']:
                states = [json.loads(row[0]) for row in db.execute('SELECT body FROM segments')]
                if len(states) != segment_count - plan['start_index'] or not all(s['complete'] for s in states):
                    raise ValueError('消息清单尚未统计完整')
                plan.update(ready=True, total=plan['base'] + db.execute('SELECT COUNT(*) FROM messages').fetchone()[0])
                self._put(db, 'plan', plan)
            return plan

    def page(self, position, offset, size, checkpoint):
        checkpoint()
        with self.connection() as db:
            if not self._get(db, 'plan')['ready']:
                raise ValueError('消息总量尚未统计完成')
            rows = db.execute('SELECT body FROM messages WHERE segment=? AND ordinal>? ORDER BY ordinal LIMIT ?',
                              (position, offset, size + 1))
            messages, chars, more = [], 0, False
            for row in rows:
                checkpoint()
                if len(messages) >= size or (messages and chars >= 128000):
                    more = True
                    break
                message = json.loads(row[0])
                messages.append(message)
                chars += len(message.get('text', ''))
            state = json.loads(db.execute('SELECT body FROM segments WHERE position=?', (position,)).fetchone()[0])
        checkpoint()
        return {'messages': messages, 'has_more': more,
                'name': state['name'], 'source': state['source'], 'warning': state['warning']}

    def reconciliation_scopes(self, targets):
        """只返回读取完整且无来源警告、可安全核对删除的快照范围。"""
        with self.connection() as db:
            states = {row[0]: json.loads(row[1])
                      for row in db.execute('SELECT position,body FROM segments')}
        return [{'segment': position, 'username': target['username'],
                 'start': target['start'], 'end': target['end']}
                for position, target in enumerate(targets)
                if (state := states.get(position)) and state.get('complete') and not state.get('warning')]

    def discard(self):
        # 只删除由任务 ID 推导的临时快照文件；索引与聊天数据库不受影响。
        self.path.unlink(missing_ok=True)
