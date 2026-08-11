import os
import sqlite3
import sys
import time
import types
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Wrapped imports the optional pypinyin dependency through the word-cloud card.
# This regression only exercises annual metadata, so keep it self-contained.
try:
    import pypinyin  # noqa: F401
except ModuleNotFoundError:
    pypinyin_stub = types.ModuleType("pypinyin")
    pypinyin_stub.lazy_pinyin = lambda value, style=None: [str(value)]
    pypinyin_stub.Style = types.SimpleNamespace(NORMAL=0)
    sys.modules["pypinyin"] = pypinyin_stub


def _seed_message_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE Msg_fixture (create_time INTEGER)")
        conn.executemany(
            "INSERT INTO Msg_fixture(create_time) VALUES (?)",
            [
                (int(datetime(2025, 3, 1, 12, 0).timestamp()),),
                (int(datetime(2026, 1, 30, 21, 39).timestamp()),),
                (int(datetime(2026, 7, 1, 12, 0).timestamp()),),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _seed_stale_index(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            [("schema_version", "4"), ("source", "decrypted")],
        )
        conn.execute(
            "CREATE VIRTUAL TABLE message_fts USING fts5("
            "text, create_time UNINDEXED, db_stem UNINDEXED)"
        )
        conn.execute(
            "INSERT INTO message_fts(text, create_time, db_stem) VALUES (?, ?, ?)",
            ("recent", int(datetime(2026, 7, 1, 12, 0).timestamp()), "message_0"),
        )
        conn.commit()
    finally:
        conn.close()


def test_wrapped_discards_index_older_than_decrypted_message_shards() -> None:
    import wechat_decrypt_tool.chat_search_index as search_index
    import wechat_decrypt_tool.wrapped.service as wrapped_service

    with TemporaryDirectory() as td:
        account_dir = Path(td) / "wxid_fixture"
        account_dir.mkdir(parents=True)
        message_db = account_dir / "message_0.db"
        index_db = account_dir / "chat_search_index.db"
        _seed_message_db(message_db)
        _seed_stale_index(index_db)

        now_ns = time.time_ns()
        os.utime(index_db, ns=(now_ns - 2_000_000_000, now_ns - 2_000_000_000))
        os.utime(message_db, ns=(now_ns, now_ns))

        stale_cache = account_dir / "_wrapped" / "cache" / "global_2026_card_0_v36.json"
        stale_cache.parent.mkdir(parents=True)
        stale_cache.write_text('{"stale": true}', encoding="utf-8")

        status = search_index.get_chat_search_index_status(account_dir, source="auto")
        assert status["index"]["ready"] is False
        assert status["index"]["staleForSourceData"] is True

        with patch.object(wrapped_service, "_resolve_account_dir", return_value=account_dir):
            result = wrapped_service.build_wrapped_annual_meta(
                account=account_dir.name,
                year=2026,
            )

        assert result["availableYears"] == [2026, 2025]
        assert not index_db.exists()
        assert not stale_cache.exists()

        from wechat_decrypt_tool.wrapped.cards.card_00_global_overview import (
            compute_annual_daily_counts,
        )

        daily_counts = compute_annual_daily_counts(
            account_dir=account_dir,
            year=2026,
            sender_username=account_dir.name,
        )
        jan_30_index = datetime(2026, 1, 30).timetuple().tm_yday - 1
        assert daily_counts[jan_30_index] == 1
