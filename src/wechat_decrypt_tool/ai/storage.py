from __future__ import annotations
from .diagnostics import observed, event as diagnostic_event
import logging
import copy
from collections import OrderedDict

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..app_paths import get_output_dir


# 事件默认保留窗口；超过该窗口且无需重放的事件会被回收。
EVENT_RETENTION_SECONDS = 24 * 3600
# 事件表空闲页超过该阈值才执行 VACUUM，避免频繁全库重写。
COMPACT_MINIMUM_BYTES = 64 * 1024 * 1024
# 超过该体积的库不做原地删除/VACUUM（对遗留巨型库会放大 WAL），改为重建：
# 仅保留 records 与未投递提醒，丢弃可再生的 events。
MAINTENANCE_MAX_DATABASE_BYTES = 512 * 1024 * 1024

SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS records (
        kind TEXT NOT NULL, id TEXT NOT NULL, account TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(kind,id));
    CREATE INDEX IF NOT EXISTS records_account ON records(kind,account,updated);
    CREATE INDEX IF NOT EXISTS records_status ON records(kind,json_extract(body,'$.status'),updated);
    CREATE INDEX IF NOT EXISTS records_task_usage ON records(kind,account,json_extract(body,'$.task_id'));
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL,
        kind TEXT NOT NULL, body TEXT NOT NULL, unique_key TEXT UNIQUE,
        delivered INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
"""


class AIStore:
    """短事务业务存储；与工作流检查点分开，避免模型请求持有数据库锁。"""

    def __init__(self, root: Path | None = None):
        self.root = root or get_output_dir() / "ai"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "ai.sqlite3"
        self.lock = threading.RLock()
        self._db = None
        self._depth = 0
        self._live_records = {}
        self._live_events = OrderedDict()
        self._live_event_bytes = 0
        self._last_event_id = 0
        self.revoked_accounts = set()
        # SSE 订阅者通过条件变量等待新事件；持久事件及内存快照共同支持断线重放。
        # 使用按账号修订号，避免其他账号的高频事件无谓唤醒当前连接。
        self._event_condition = threading.Condition()
        self._event_revisions = {}
        with self.connection() as db:
            db.executescript(SCHEMA_SQL)
        self._reserve_event_ids()

    def _reserve_event_ids(self):
        """低频预留事件编号，内存事件无需写盘也能跨重启保持游标递增。"""
        with self.connection() as db:
            sequence = db.execute("SELECT coalesce(max(seq),0) FROM sqlite_sequence WHERE name='events'").fetchone()[0]
            maximum = db.execute('SELECT coalesce(max(id),0) FROM events').fetchone()[0]
            self._next_event_id = max(sequence, maximum, self._last_event_id) + 1
            self._event_id_limit = self._next_event_id + 1_000_000
            if not db.execute("UPDATE sqlite_sequence SET seq=? WHERE name='events'", (self._event_id_limit,)).rowcount:
                db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('events',?)", (self._event_id_limit,))

    def _allocate_event_id(self):
        id = max(self._next_event_id, self.latest_event_id() + 1)
        if id >= self._event_id_limit:
            self._reserve_event_ids()
            id = self._next_event_id
        self._next_event_id = id + 1
        self._last_event_id = id
        return id

    @contextmanager
    def connection(self):
        with self.lock:
            if self._db is None:
                self._db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
                self._db.row_factory = sqlite3.Row
                self._db.execute("PRAGMA journal_mode=WAL")
            db = self._db
            depth = self._depth
            live_records = self._live_records.copy()
            live_events = self._live_events.copy()
            live_bytes = self._live_event_bytes
            event_range = (getattr(self, '_next_event_id', None), getattr(self, '_event_id_limit', None))
            if depth:
                db.execute(f'SAVEPOINT nested_{depth}')
            else:
                db.execute('BEGIN')
            self._depth += 1
            try:
                if depth:
                    yield db
                    db.execute(f'RELEASE nested_{depth}')
                else:
                    with db:
                        yield db
            except BaseException as error:
                if depth:
                    db.execute(f'ROLLBACK TO nested_{depth}')
                    db.execute(f'RELEASE nested_{depth}')
                self._live_records = live_records
                self._live_events = live_events
                self._live_event_bytes = live_bytes
                if event_range[0] is not None:
                    self._next_event_id, self._event_id_limit = event_range
                diagnostic_event('storage.transaction.failed', level=logging.ERROR, error=error, committed=False)
                raise
            finally:
                self._depth -= 1

    def close(self):
        """工作线程退出后关闭连接；提交仍保持 SQLite 默认的持久性级别。"""
        with self.lock:
            if self._depth:
                raise RuntimeError('不能在事务中关闭 AI 存储')
            if self._db is not None:
                self._db.close()
                self._db = None

    def has_live_record(self, kind, id):
        with self.lock:
            return (kind, id) in self._live_records

    def put(self, kind, body, id=None, account="", transient=False):
        id = id or body.get("id") or uuid.uuid4().hex
        body = {**body, "id": id}
        owner = account or body.get("account", "")
        with self.lock:
            if owner in self.revoked_accounts:
                return body
            if transient:
                self._live_records[kind, id] = (copy.deepcopy(body), owner, time.time())
                return body
        with self.connection() as db:
            if (account or body.get("account", "")) in self.revoked_accounts:
                return body
            db.execute("INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body, account=excluded.account, updated=excluded.updated WHERE records.body<>excluded.body OR records.account<>excluded.account",
                       (kind, id, account or body.get("account", ""), json.dumps(body, ensure_ascii=False), time.time()))
            self._live_records.pop((kind, id), None)
        return body

    def get(self, kind, id):
        with self.lock:
            if (kind, id) in self._live_records:
                return copy.deepcopy(self._live_records[kind, id][0])
        with self.connection() as db:
            row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind, account=None, limit=None, offset=0, compact=False):
        with self.lock:
            live = {id: entry for (entry_kind, id), entry in self._live_records.items()
                    if entry_kind == kind and (account is None or entry[1] == account)}
            if live:
                with self.connection() as db:
                    rows = db.execute('SELECT id,body,updated FROM records WHERE kind=?' +
                                      (' AND account=?' if account is not None else ''),
                                      [kind] if account is None else [kind, account]).fetchall()
                merged = {row['id']: (json.loads(row['body']), row['updated']) for row in rows}
                merged.update({id: (copy.deepcopy(entry[0]), entry[2]) for id, entry in live.items()})
                bodies = [body for body, _ in sorted(merged.values(), key=lambda entry: entry[1], reverse=True)]
                bodies = bodies[offset:offset + limit if limit is not None else None]
                return [{k: v for k, v in body.items() if not compact or k not in
                         ('results', 'overview', 'models', 'cursors')} for body in bodies]
        column = "json_remove(body,'$.results','$.overview','$.models','$.cursors')" if compact else "body"
        args = [kind] if account is None else [kind, account]
        sql = f"SELECT {column} FROM records WHERE kind=?" + (" AND account=?" if account is not None else "") + " ORDER BY updated DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend([limit, offset])
        with self.connection() as db:
            rows = db.execute(sql, args).fetchall()
        return [json.loads(row[0]) for row in rows]

    def tasks_in_status(self, statuses):
        placeholders = ",".join("?" for _ in statuses)
        with self.connection() as db:
            rows = db.execute(f"SELECT body FROM records WHERE kind='task' AND json_extract(body,'$.status') IN ({placeholders}) ORDER BY updated DESC", statuses).fetchall()
        return [json.loads(row[0]) for row in rows]

    @observed('storage.recover_interrupted_usage')
    def recover_interrupted_usage(self):
        """仅在服务启动、尚未接受请求时收尾上次进程遗留的调用。"""
        now = time.time()
        with self.connection() as db:
            # 无法获知进程退出的准确时间，不补造结束时间、耗时或 Token。
            db.execute("""UPDATE records SET
                body=json_set(body,'$.status','interrupted','$.error_type','ProcessInterrupted',
                              '$.recovered_at',?), updated=?
                WHERE kind='usage' AND json_extract(body,'$.status')='running'""", (now, now))
            recovered = db.execute('SELECT changes()').fetchone()[0]
        diagnostic_event('storage.usage.recovered', count=recovered, status='interrupted')

    def latest_event_id(self):
        with self.connection() as db:
            return max(self._last_event_id, db.execute("SELECT coalesce(max(id),0) FROM events").fetchone()[0])

    def delete(self, kind, id):
        with self.connection() as db:
            db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, id))
            self._live_records.pop((kind, id), None)
            if kind in ('agent_run', 'agent_thread'):
                field = 'run_id' if kind == 'agent_run' else 'thread_id'
                self.discard_live_events(field, id)

    def discard_live_events(self, field, value):
        """删除任务或账号时同步移除内存重放，避免已删内容再次送达。"""
        with self.lock:
            for key, (row, size) in list(self._live_events.items()):
                if row['body'].get(field) == value:
                    del self._live_events[key]
                    self._live_event_bytes -= size

    def event(self, account, kind, body, unique_key=None, replace=False, transient=False):
        """写入事件供 SSE 重放。

        默认行为保持不变：提供 `unique_key` 时按去重语义写入（同 key 已存在则忽略），
        用于提醒等只应投递一次的事件。`replace=True` 时改为用最新快照替换旧行，
        让高频进度事件每个逻辑任务只保留一行，同时因 INSERT OR REPLACE 会删除旧行、
        新行仍获得递增 id，断线重连的 EventSource 依然能收到最新状态。
        `transient=True` 仅在有界内存缓存中合并展示快照，不写 SQLite；通知仍使用默认持久化。
        """
        with self.lock:
            if account in self.revoked_accounts:
                return
            if transient:
                id = self._allocate_event_id()
                key = (account, kind, unique_key) if unique_key is not None else id
                old = self._live_events.pop(key, None)
                if old:
                    self._live_event_bytes -= old[1]
                    # 累计正文快照被合并后，早先送达的引用映射也必须随最新快照保留。
                    if old[0]['body'].get('version') == body.get('version'):
                        body = dict(body)
                        for field, identity in (('citations', 'source'), ('references', 'id')):
                            if old[0]['body'].get(field):
                                merged = {item[identity]: item for item in old[0]['body'][field]}
                                merged.update({item[identity]: item for item in body.get(field, [])})
                                body[field] = list(merged.values())
                payload = json.dumps(body, ensure_ascii=False)
                row = dict(id=id, account=account, kind=kind, body=json.loads(payload),
                           unique_key=unique_key, delivered=0, created=time.time())
                size = len(payload.encode('utf-8'))
                self._live_events[key] = (row, size)
                self._live_event_bytes += size
                # 短暂断线重放最新快照；长断线由前端已有的重连 GET 补齐权威状态。
                while len(self._live_events) > 1 and (
                        len(self._live_events) > 256 or self._live_event_bytes > 8 * 1024 * 1024):
                    _, (_, removed_size) = self._live_events.popitem(last=False)
                    self._live_event_bytes -= removed_size
                self._notify_event(account)
                return
        with self.connection() as db:
            if account in self.revoked_accounts:
                return
            payload = json.dumps(body, ensure_ascii=False)
            id = self._allocate_event_id()
            if unique_key is None:
                cursor = db.execute(
                    "INSERT INTO events(id,account,kind,body,created) VALUES(?,?,?,?,?)",
                    (id, account, kind, payload, time.time()))
            elif replace:
                cursor = db.execute(
                    "INSERT OR REPLACE INTO events(id,account,kind,body,unique_key,created) VALUES(?,?,?,?,?,?)",
                    (id, account, kind, payload, unique_key, time.time()))
            else:
                cursor = db.execute(
                    "INSERT OR IGNORE INTO events(id,account,kind,body,unique_key,created) VALUES(?,?,?,?,?,?)",
                    (id, account, kind, payload, unique_key, time.time()))
            inserted = cursor.rowcount > 0
            if inserted:
                self._last_event_id = id
                if replace:
                    old = self._live_events.pop((account, kind, unique_key), None)
                    if old:
                        self._live_event_bytes -= old[1]
        if inserted:
            self._notify_event(account)

    def _notify_event(self, account):
        with self._event_condition:
            self._event_revisions[account] = self._event_revisions.get(account, 0) + 1
            self._event_condition.notify_all()

    def event_revision(self, account):
        """返回进程内事件修订号，用于无竞态地建立 SSE 等待点。"""
        with self._event_condition:
            return self._event_revisions.get(account, 0)

    def wait_for_event(self, account, revision, timeout):
        """阻塞等待账号出现新事件；超时后由 SSE 发送低频心跳。"""
        with self._event_condition:
            changed = self._event_condition.wait_for(
                lambda: self._event_revisions.get(account, 0) != revision,
                timeout=max(0, timeout),
            )
            return changed, self._event_revisions.get(account, 0)

    def events(self, after=0, account=None, pending=False):
        sql, args = "SELECT * FROM events WHERE id>?", [after]
        if account is not None:
            sql += " AND account=?"
            args.append(account)
        if pending:
            sql += " AND delivered=0 AND kind='notification'"
        with self.connection() as db:
            rows = db.execute(sql + " ORDER BY id LIMIT 100", args).fetchall()
            result = [{**dict(row), "body": json.loads(row["body"])} for row in rows]
            if not pending:
                result.extend(copy.deepcopy(row) for row, _ in self._live_events.values()
                              if row['id'] > after and (account is None or row['account'] == account))
        return sorted(result, key=lambda row: row['id'])[:100]

    @observed('storage.acknowledge')
    def acknowledge(self, id):
        with self.connection() as db:
            db.execute("UPDATE events SET delivered=1 WHERE id=?", (id,))

    @observed('storage.prune_duplicates')
    def prune_duplicate_events(self, batch=2000):
        """一次性折叠旧版追加式进度事件：每个逻辑任务只保留最新快照。

        新写入的进度事件已带 unique_key、本身只保留一行；这里主要清理升级前
        历史遗留的、同一任务多次追加的整份快照，避免巨型库只能等 TTL 慢慢过期。
        """
        total = 0
        for kind, field in (('local_search_index', '$.id'), ('local_search_download', '$.id'),
                            ('local_search_total', '$.job_id')):
            with self.connection() as db:
                db.execute("CREATE TEMP TABLE IF NOT EXISTS keep_event_ids(id INTEGER PRIMARY KEY)")
                db.execute("DELETE FROM keep_event_ids")
                db.execute(
                    f"INSERT INTO keep_event_ids SELECT max(id) FROM events "
                    f"WHERE kind=? AND unique_key IS NULL GROUP BY json_extract(body,'{field}')", (kind,))
                while True:
                    removed = db.execute(
                        "DELETE FROM events WHERE id IN (SELECT id FROM events "
                        "WHERE kind=? AND unique_key IS NULL AND id NOT IN (SELECT id FROM keep_event_ids) LIMIT ?)",
                        (kind, batch)).rowcount
                    total += removed
                    db.commit()
                    if removed < batch:
                        break
                db.execute("DELETE FROM keep_event_ids")
        for kind in ('local_search_device', 'local_search_gpu'):
            with self.connection() as db:
                total += db.execute(
                    "DELETE FROM events WHERE kind=? AND unique_key IS NULL AND id < (SELECT max(id) FROM events WHERE kind=?)",
                    (kind, kind)).rowcount
        if total:
            diagnostic_event('storage.events.deduplicated', count=total)
        return total

    @observed('storage.prune_events')
    def prune_events(self, max_age=EVENT_RETENTION_SECONDS, batch=2000):
        """按 TTL 批量回收事件：非通知事件直接过期；已投递通知同样回收，未投递通知保留。"""
        cutoff = time.time() - max_age
        total = 0
        while True:
            with self.connection() as db:
                removed = db.execute(
                    "DELETE FROM events WHERE id IN (SELECT id FROM events "
                    "WHERE created<? AND (kind!='notification' OR delivered=1) LIMIT ?)",
                    (cutoff, batch)).rowcount
            total += removed
            if removed < batch:
                break
        if total:
            diagnostic_event('storage.events.pruned', count=total, retention_seconds=max_age)
        return total

    @observed('storage.compact')
    def compact(self, minimum_bytes=COMPACT_MINIMUM_BYTES):
        """回收已删除行遗留的空闲页；空闲空间不多时不做全库重写。"""
        with self.lock:
            self.close()
            probe = sqlite3.connect(self.path, timeout=30)
            try:
                page_size = probe.execute('PRAGMA page_size').fetchone()[0]
                free = probe.execute('PRAGMA freelist_count').fetchone()[0] * page_size
            finally:
                probe.close()
            if free < minimum_bytes:
                return 0
            # VACUUM 不能在事务内执行，使用独立连接并先截断 WAL。
            db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            try:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                db.execute('VACUUM')
            finally:
                db.close()
        diagnostic_event('storage.compacted', freed_bytes=free)
        return free

    @observed('storage.repair')
    def repair_oversized(self, max_database_bytes=MAINTENANCE_MAX_DATABASE_BYTES):
        """重建过大的库：保留 records 与未投递提醒，丢弃可再生的 events。

        对遗留巨型库，原地 DELETE + VACUUM 会把 WAL 放大到库体积且长时间占锁；
        这里改为把少量存活数据复制到新库再原子替换，耗时与库体积无关。
        返回重建前的库大小（字节），未触发或失败返回 0。
        """
        with self.lock:
            try:
                self.close()
                probe = sqlite3.connect(self.path, timeout=30)
                try:
                    database_bytes = self._database_bytes(probe)
                finally:
                    probe.close()
                if database_bytes <= max_database_bytes:
                    return 0

                temporary = self.path.with_name(self.path.name + '.repair')
                for suffix in ('', '-wal', '-shm'):
                    try:
                        os.remove(str(temporary) + suffix)
                    except FileNotFoundError:
                        pass

                source = sqlite3.connect(self.path, timeout=30)
                target = sqlite3.connect(temporary, timeout=30)
                try:
                    source.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    target.executescript(SCHEMA_SQL)
                    target.executemany(
                        'INSERT INTO records(kind,id,account,body,updated) VALUES(?,?,?,?,?)',
                        source.execute('SELECT kind,id,account,body,updated FROM records'))
                    # 未投递提醒不可再生，随 records 一起保留；其余 events 只是进度快照。
                    target.executemany(
                        'INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES(?,?,?,?,?,?)',
                        source.execute("SELECT account,kind,body,unique_key,delivered,created FROM events "
                                       "WHERE kind='notification' AND delivered=0"))
                    sequence = source.execute("SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone()
                    if sequence:
                        target.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('events',?)", (sequence[0],))
                    target.commit()
                finally:
                    source.close()
                    target.close()

                # 先原子替换主库，再清理旧的 WAL/SHM：即使替换失败，原库仍完整。
                for attempt in range(4):
                    try:
                        os.replace(temporary, self.path)
                        break
                    except OSError as error:
                        if attempt == 3:
                            raise
                        diagnostic_event('storage.repair.retry', level=logging.WARNING, error=error)
                        time.sleep(0.3 * (attempt + 1))
                for suffix in ('-wal', '-shm'):
                    try:
                        os.remove(str(self.path) + suffix)
                    except FileNotFoundError:
                        pass
                diagnostic_event('storage.repaired', bytes_before=database_bytes)
                return database_bytes
            except Exception as error:
                for suffix in ('', '-wal', '-shm'):
                    try:
                        os.remove(str(self.path.with_name(self.path.name + '.repair')) + suffix)
                    except FileNotFoundError:
                        pass
                diagnostic_event('storage.repair.failed', level=logging.WARNING, error=error)
                return 0

    def maintain(self, max_age=EVENT_RETENTION_SECONDS, minimum_bytes=COMPACT_MINIMUM_BYTES,
                 max_database_bytes=MAINTENANCE_MAX_DATABASE_BYTES):
        """启动维护：折叠遗留重复事件、回收过期事件，再按需压缩数据库文件。

        超过 `max_database_bytes` 的遗留巨型库改为重建（保留 records 与未投递提醒），
        避免原地删除/VACUUM 长时间占锁并放大 WAL。
        """
        with self.connection() as db:
            database_bytes = self._database_bytes(db)
        if database_bytes > max_database_bytes:
            repaired = self.repair_oversized(max_database_bytes)
            return 0, 0, repaired
        deduplicated = self.prune_duplicate_events()
        removed = self.prune_events(max_age)
        freed = self.compact(minimum_bytes)
        return deduplicated, removed, freed

    @staticmethod
    def _database_bytes(db):
        page_size = db.execute('PRAGMA page_size').fetchone()[0]
        page_count = db.execute('PRAGMA page_count').fetchone()[0]
        return page_size * page_count

    @observed('storage.purge_account')
    def purge_account(self, account):
        with self.connection() as db:
            self.revoked_accounts.add(account)
            db.execute("DELETE FROM records WHERE account=?", (account,))
            db.execute("DELETE FROM events WHERE account=?", (account,))
            self._live_records = {key: value for key, value in self._live_records.items() if value[1] != account}
            for key, (row, size) in list(self._live_events.items()):
                if row['account'] == account:
                    del self._live_events[key]
                    self._live_event_bytes -= size
