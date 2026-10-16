import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import chat as chat_router


class _DummyRequest:
    base_url = "http://testserver/"


def _seed_session_db(path: Path, rows: list[tuple[str, int, int, str]]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE SessionTable(
                username TEXT PRIMARY KEY,
                unread_count INTEGER,
                is_hidden INTEGER,
                summary TEXT,
                draft TEXT,
                last_timestamp INTEGER,
                sort_timestamp INTEGER,
                last_msg_type INTEGER,
                last_msg_sub_type INTEGER
            )
            """
        )
        for username, sort_timestamp, last_timestamp, summary in rows:
            conn.execute(
                """
                INSERT INTO SessionTable(
                    username, unread_count, is_hidden, summary, draft,
                    last_timestamp, sort_timestamp, last_msg_type, last_msg_sub_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    0,
                    0,
                    summary,
                    "",
                    int(last_timestamp),
                    int(sort_timestamp),
                    1,
                    0,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_contact_db_with_flag(path: Path, flags: dict[str, int]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE contact(
                username TEXT,
                remark TEXT,
                nick_name TEXT,
                alias TEXT,
                big_head_url TEXT,
                small_head_url TEXT,
                flag INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE stranger(
                username TEXT,
                remark TEXT,
                nick_name TEXT,
                alias TEXT,
                big_head_url TEXT,
                small_head_url TEXT,
                flag INTEGER
            )
            """
        )
        for username, flag in flags.items():
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, "", "", "", "", "", int(flag)),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_contact_db_without_flag(path: Path, usernames: list[str]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE contact(
                username TEXT,
                remark TEXT,
                nick_name TEXT,
                alias TEXT,
                big_head_url TEXT,
                small_head_url TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE stranger(
                username TEXT,
                remark TEXT,
                nick_name TEXT,
                alias TEXT,
                big_head_url TEXT,
                small_head_url TEXT
            )
            """
        )
        for username in usernames:
            conn.execute(
                "INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?)",
                (username, "", "", "", "", ""),
            )
        conn.commit()
    finally:
        conn.close()


class TestChatSessionsPinning(unittest.TestCase):
    def test_pinned_session_is_sorted_first_and_has_is_top(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            _seed_session_db(
                account_dir / "session.db",
                [
                    ("wxid_new", 200, 200, "new message"),
                    ("wxid_top", 100, 100, "top older message"),
                ],
            )
            _seed_contact_db_with_flag(
                account_dir / "contact.db",
                {
                    "wxid_new": 0,
                    "wxid_top": 1 << 11,
                },
            )

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=50,
                    include_hidden=True,
                    include_official=True,
                    preview="session",
                    source="",
                )

            self.assertEqual(resp.get("status"), "success")
            sessions = resp.get("sessions") or []
            self.assertEqual(len(sessions), 2)
            self.assertEqual(sessions[0].get("username"), "wxid_top")
            self.assertTrue(bool(sessions[0].get("isTop")))
            self.assertEqual(sessions[1].get("username"), "wxid_new")
            self.assertFalse(bool(sessions[1].get("isTop")))

    def test_missing_flag_column_does_not_error_and_defaults_false(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            _seed_session_db(
                account_dir / "session.db",
                [
                    ("wxid_top", 100, 100, "hello"),
                ],
            )
            _seed_contact_db_without_flag(account_dir / "contact.db", ["wxid_top"])

            with patch.object(chat_router, "_resolve_account_dir", return_value=account_dir):
                resp = chat_router.list_chat_sessions(
                    _DummyRequest(),
                    account="acc",
                    limit=50,
                    include_hidden=True,
                    include_official=True,
                    preview="session",
                    source="",
                )

            self.assertEqual(resp.get("status"), "success")
            sessions = resp.get("sessions") or []
            self.assertEqual(len(sessions), 1)
            self.assertFalse(bool(sessions[0].get("isTop")))


if __name__ == "__main__":
    unittest.main()

