"""回归：进度事件必须原地替换、按 TTL 回收并可压缩，避免 ai.sqlite3 无界膨胀。"""
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wechat_decrypt_tool.ai.storage import AIStore
from wechat_decrypt_tool.local_search.service import LocalSearch


def test_periodic_maintenance_runs_until_shutdown():
    from wechat_decrypt_tool.ai.lifecycle import _maintenance_loop

    calls = []
    stopped = threading.Event()

    class Store:
        def maintain(self):
            calls.append(time.monotonic())
            if len(calls) >= 2:
                stopped.set()
            return 0, 0, 0

    _maintenance_loop(Store(), 'test', stopped, interval=0.01)
    assert len(calls) == 2
    assert calls[1] >= calls[0]


def test_local_search_update_emits_compact_deduplicated_event(tmp_path):
    service = LocalSearch(tmp_path, engine=SimpleNamespace(status={}, gpu_failed=False))
    job = {'id': 'job1', 'account': 'a', 'config': {'usernames': ['chat']}, 'coverage': {'0': {}},
           'segments': [{}], 'read_starts': {'chat': 0}, 'processed': 0}
    for processed in range(10):
        service.update(job, processed=processed)
    events = [event for event in service.store.events() if event['kind'] == 'local_search_index']
    assert len(events) == 1
    body = events[0]['body']
    assert body['processed'] == 9 and body['id'] == 'job1'
    for heavy in ('config', 'coverage', 'segments', 'read_starts'):
        assert heavy not in body


def test_prune_duplicate_events_collapses_legacy_snapshots(tmp_path):
    store = AIStore(tmp_path)
    now = time.time()
    with store.connection() as db:
        for processed in range(5):
            db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','local_search_index',?,NULL,0,?)",
                       (json.dumps({'id': 'job-a', 'processed': processed}), now))
        for processed in (1, 2):
            db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','local_search_index',?,NULL,0,?)",
                       (json.dumps({'id': 'job-b', 'processed': processed}), now))
    assert store.prune_duplicate_events(batch=2) == 5
    kept = sorted(row['body']['processed'] for row in store.events())
    assert kept == [2, 4]


def test_unique_key_event_keeps_only_latest_snapshot(tmp_path):
    store = AIStore(tmp_path)
    for processed in range(50):
        store.event('', 'local_search_index', {'id': 'job', 'processed': processed},
                    unique_key='index_job:job', replace=True)
    rows = store.events()
    assert len(rows) == 1
    assert rows[0]['body']['processed'] == 49
    # 替换后仍产生新的自增 id，保证 SSE 客户端能收到更新。
    assert rows[0]['id'] > 0


def test_unique_key_without_replace_stays_idempotent(tmp_path):
    store = AIStore(tmp_path)
    store.event('', 'notification', {'n': 1}, unique_key='summary:1')
    store.event('', 'notification', {'n': 2}, unique_key='summary:1')
    rows = store.events()
    assert len(rows) == 1 and rows[0]['body']['n'] == 1


def test_prune_events_keeps_undelivered_notifications(tmp_path):
    store = AIStore(tmp_path)
    old = time.time() - 10 * 24 * 3600
    with store.connection() as db:
        db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','local_search_index','{}','old-progress',0,?)", (old,))
        db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','notification','{}',NULL,0,?)", (old,))
        db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','notification','{}',NULL,1,?)", (old,))
    assert store.prune_events(max_age=24 * 3600) == 2
    remaining = store.events()
    assert len(remaining) == 1
    assert remaining[0]['kind'] == 'notification' and remaining[0]['delivered'] == 0


def test_maintain_repairs_oversized_database_preserving_records(tmp_path):
    store = AIStore(tmp_path)
    store.put('config', {'enabled': True}, id='acct', account='acct')
    now = time.time()
    with store.connection() as db:
        for index in range(300):
            db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','local_search_index',?,NULL,0,?)",
                       (json.dumps({'id': 'job', 'index': index, 'pad': 'x' * 2000}), now))
        db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','notification','{\"n\":1}','k1',0,?)", (now,))
        db.execute("INSERT INTO events(account,kind,body,unique_key,delivered,created) VALUES('','notification','{\"n\":2}','k2',1,?)", (now,))
        before = store._database_bytes(db)
    # 用极小阈值模拟遗留巨型库：应重建而不是长时间原地删除。
    deduplicated, pruned, repaired = store.maintain(max_database_bytes=1)
    assert repaired > 0
    with store.connection() as db:
        assert store._database_bytes(db) < before
    # records 保留；未投递提醒保留，可再生的进度事件与已投递提醒丢弃。
    assert store.get('config', 'acct')['enabled'] is True
    events = store.events()
    assert [event['kind'] for event in events] == ['notification']
    assert events[0]['body']['n'] == 1


def test_compact_reclaims_free_pages_after_prune(tmp_path):
    store = AIStore(tmp_path)
    for index in range(2000):
        store.event('', 'task', {'payload': 'x' * 2000, 'index': index})
    with store.connection() as db:
        db.execute("DELETE FROM events")
    before = store.path.stat().st_size
    assert before > 0
    freed = store.compact(minimum_bytes=1)
    assert freed > 0
    assert store.path.stat().st_size < before
