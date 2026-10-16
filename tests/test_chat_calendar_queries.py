"""用真实 SQLite 分库验证月历 SQL、完整性以及超过旧扫描上限的历史记录。"""
import hashlib
import json
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wechat_decrypt_tool import chat_realtime_reader as reader
from wechat_decrypt_tool.routers import chat

USERNAME = "calendar_test@chatroom"
TABLE = "Msg_" + hashlib.md5(USERNAME.encode()).hexdigest()


def ts(value):
    return int(datetime.fromisoformat(value).timestamp())


def seed(path, times, column_type="INTEGER"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(f'CREATE TABLE "{TABLE}" (local_id INTEGER PRIMARY KEY, create_time {column_type}, sort_seq INTEGER, message_content TEXT)')
        conn.executemany(f'INSERT INTO "{TABLE}" (create_time, sort_seq, message_content) VALUES (?, 0, ?)',
                         ((value, "测试正文" * 20) for value in times))
        conn.execute(f'CREATE INDEX calendar_time ON "{TABLE}" (create_time)')


@pytest.fixture
def calendar(tmp_path, monkeypatch):
    reader._clear_realtime_reader_caches()
    account = tmp_path / "acc"
    account.mkdir()
    storage = tmp_path / "db_storage"
    rt = SimpleNamespace(handle=42, lock=threading.Lock())
    calls = []

    def execute(_handle, *, kind, path, sql):
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(sql)]
        calls.append((path, sql, len(rows)))
        return rows

    monkeypatch.setattr(chat, "_resolve_account_dir", lambda _: account)
    monkeypatch.setattr(chat, "_resolve_account_db_storage_dir", lambda _: storage)
    monkeypatch.setattr(chat, "_connect_realtime_for_chat_source", lambda **_: ("realtime", rt, ""))
    monkeypatch.setattr(chat, "_wcdb_exec_query", execute)

    def no_scan(*args, **kwargs):
        raise AssertionError("月历不能读取或解析消息正文")

    monkeypatch.setattr(chat, "_wcdb_get_messages", no_scan)
    monkeypatch.setattr(chat, "_normalize_realtime_message_item", no_scan)
    yield SimpleNamespace(account=account, storage=storage, rt=rt, calls=calls, execute=execute)
    reader._clear_realtime_reader_caches()


def query(year=2020, month=2, source="auto"):
    return chat.get_chat_message_daily_counts(USERNAME, year, month, account="acc", source=source)


def test_cross_shard_local_boundaries_leap_day_and_empty_month(calendar):
    seed(calendar.storage / "message/message_0.db", map(ts, [
        "2020-01-31T23:59:59", "2020-02-01T00:00:00", "2020-02-29T23:59:59", "2020-03-01T00:00:00",
    ]))
    seed(calendar.storage / "message/message_1.db", [ts("2020-02-01T00:00:01")])
    result = query()
    assert result["counts"] == {"2020-02-01": 2, "2020-02-29": 1}
    assert (result["total"], result["max"]) == (3, 2)
    assert result["scanLimited"] is False and result["scannedMessages"] == 0
    assert query(month=4)["counts"] == {}
    assert all(size <= 31 for _, sql, size in calendar.calls if "GROUP BY" in sql)


def test_missing_conversation_is_empty_only_after_all_shards_probed(calendar):
    path = calendar.storage / "message/message_0.db"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
    assert query()["total"] == 0


@pytest.mark.parametrize("stage", ["discovery", "aggregate"])
def test_failed_shard_never_returns_partial_counts(calendar, monkeypatch, stage):
    events = []
    monkeypatch.setattr(chat, "create_perf_trace", lambda *args, **kwargs: (
        "test-trace", lambda phase, **fields: events.append((phase, fields)),
    ))
    for name in ["message_0.db", "message_1.db"]:
        seed(calendar.storage / "message" / name, [ts("2020-02-01")])

    def fail(_handle, **kwargs):
        if kwargs["path"].endswith("message_1.db") and (
            (stage == "discovery" and "sqlite_master" in kwargs["sql"])
            or (stage == "aggregate" and "GROUP BY" in kwargs["sql"])
        ):
            raise RuntimeError("synthetic failure")
        return calendar.execute(_handle, **kwargs)

    monkeypatch.setattr(chat, "_wcdb_exec_query", fail)
    with pytest.raises(HTTPException) as error:
        query()
    assert error.value.status_code == 503
    assert "完整加载" in error.value.detail
    assert events[0][0] == "request:start"
    assert events[-1][0] == "request:failed" and events[-1][1]["stage"] == stage
    assert all("synthetic failure" not in str(fields) for _, fields in events)
    assert calendar.rt.lock.acquire(blocking=False)
    calendar.rt.lock.release()


def test_missing_realtime_database_directory_is_error(calendar):
    with pytest.raises(HTTPException) as error:
        query()
    assert error.value.status_code == 503


@pytest.mark.parametrize("column_type", ["INTEGER", "TEXT"])
def test_decrypted_integer_and_text_timestamps(calendar, monkeypatch, column_type):
    seed(calendar.account / "message.db", map(ts, ["2020-01-31T23:59:59", "2020-02-01", "2020-02-29T23:59:59", "2020-03-01"]), column_type)
    seed(calendar.account / "message_1.db", [ts("2020-02-01")], column_type)
    statements = []
    real_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(chat.sqlite3, "connect", traced_connect)
    monkeypatch.setattr(chat, "_connect_realtime_for_chat_source", lambda **_: ("decrypted", None, ""))
    assert query(source="decrypted")["counts"] == {"2020-02-01": 2, "2020-02-29": 1}
    sql = next(statement for statement in statements if "GROUP BY" in statement)
    assert ("CAST(create_time" in sql) == (column_type == "TEXT")
    if column_type == "INTEGER":
        with real_connect(calendar.account / "message.db") as conn:
            assert any("SEARCH" in row[3] and "calendar_time" in row[3]
                       for row in conn.execute("EXPLAIN QUERY PLAN " + sql))


@pytest.mark.parametrize("failure", ["corrupt", "missing_column", "removed"])
def test_decrypted_shard_errors_are_not_swallowed(calendar, monkeypatch, failure):
    seed(calendar.account / "message.db", [ts("2020-02-01")])
    bad = calendar.account / "message_1.db"
    if failure == "corrupt":
        bad.write_bytes(b"invalid sqlite")
    elif failure == "missing_column":
        with sqlite3.connect(bad) as conn:
            conn.execute(f'CREATE TABLE "{TABLE}" (id INTEGER)')
    else:
        monkeypatch.setattr(chat, "_iter_message_db_paths", lambda _: [calendar.account / "message.db", bad])
    monkeypatch.setattr(chat, "_connect_realtime_for_chat_source", lambda **_: ("decrypted", None, ""))
    with pytest.raises(HTTPException) as error:
        query(source="decrypted")
    assert error.value.status_code == 503
    if failure == "removed":
        assert not bad.exists()


def test_large_old_month_uses_index_and_bounded_results(calendar, monkeypatch):
    path = calendar.storage / "message/message_0.db"
    old = ts("2020-02-01")
    recent = ts("2026-09-01")
    seed(path, [old, old + 1, ts("2020-02-29")] + [recent] * 200_001)
    metrics = {}
    result = reader.fetch_daily_counts_via_exec(
        rt_conn=calendar.rt, username=USERNAME, db_storage_dir=calendar.storage,
        exec_query=calendar.execute, start_time=old, end_time=ts("2020-03-01"), timings=metrics,
    )
    assert result == {"2020-02-01": 2, "2020-02-29": 1}
    aggregate_sql = next(sql for _, sql, _ in calendar.calls if "GROUP BY" in sql)
    with sqlite3.connect(path) as conn:
        plan = conn.execute("EXPLAIN QUERY PLAN " + aggregate_sql).fetchall()
    assert any("SEARCH" in row[3] and "calendar_time" in row[3] for row in plan)
    assert metrics["returnedRows"] == 2
    assert all(name in metrics for name in ["discoveryMs", "aggregateMs", "sqlMs", "lockWaitMs"])

    # 归一化使用恒等函数，基线刻意偏向旧方案；首次指应用缓存清空，非冷磁盘。
    def get_messages(_handle, _username, *, limit, offset):
        return calendar.execute(_handle, kind="message", path=str(path), sql=(
            f'SELECT * FROM "{TABLE}" ORDER BY create_time DESC LIMIT {limit} OFFSET {offset}'
        ))

    monkeypatch.setattr(chat, "_wcdb_get_messages", get_messages)
    monkeypatch.setattr(chat, "_normalize_realtime_message_item", lambda row: row)
    timings = {}
    for run in ["first", "repeat"]:
        start = time.perf_counter()
        rows, limited, scanned = chat._fetch_realtime_message_rows(
            rt_conn=calendar.rt, username=USERNAME, max_scan=200_000, stop_before_ts=old,
        )
        timings[f"old_{run}_ms"] = round((time.perf_counter() - start) * 1000, 2)
        assert limited and scanned == 200_000
        assert not any(old <= row["create_time"] < ts("2020-03-01") for row in rows)
    for run in ["first", "repeat"]:
        if run == "first":
            reader._clear_realtime_reader_caches()
        start = time.perf_counter()
        assert query()["total"] == 3
        timings[f"new_{run}_ms"] = round((time.perf_counter() - start) * 1000, 2)
    print("CALENDAR_BENCHMARK " + json.dumps({
        "fixture_messages": 200_004, "old_returned_rows": 200_000, "new_aggregate_rows": 2,
        "note": "本地 SQLite 合成数据；首次指应用缓存清空，非操作系统冷磁盘", **timings,
    }, ensure_ascii=False))
