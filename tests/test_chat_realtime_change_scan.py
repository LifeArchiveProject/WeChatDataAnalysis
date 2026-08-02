import asyncio
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers.chat import _scan_db_storage_mtime_ns


class TestChatRealtimeChangeScan(unittest.TestCase):
    def test_general_database_changes_remain_visible_to_all_scope(self):
        with TemporaryDirectory() as td:
            db_path = Path(td) / "general" / "general.db"
            db_path.parent.mkdir(parents=True)
            db_path.write_bytes(b"fixture")

            self.assertGreater(_scan_db_storage_mtime_ns(Path(td)), 0)

    def test_chat_scope_ignores_non_chat_databases(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            for relative in ("general/general.db-wal", "sns/sns.db-wal", "favorite/favorite.db-wal"):
                db_path = root / relative
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path.write_bytes(b"fixture")

            self.assertEqual(_scan_db_storage_mtime_ns(root, scope="chat"), 0)

    def test_chat_scope_tracks_message_and_session_writes_but_not_shm_reads(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            shm_path = root / "message" / "message_0.db-shm"
            shm_path.parent.mkdir(parents=True)
            shm_path.write_bytes(b"reader-state")
            self.assertEqual(_scan_db_storage_mtime_ns(root, scope="chat"), 0)

            wal_path = root / "message" / "message_0.db-wal"
            wal_path.write_bytes(b"new-message")
            self.assertGreater(_scan_db_storage_mtime_ns(root, scope="chat"), 0)

            wal_path.unlink()
            session_path = root / "session" / "session.db"
            session_path.parent.mkdir(parents=True)
            session_path.write_bytes(b"new-session")
            self.assertGreater(_scan_db_storage_mtime_ns(root, scope="chat"), 0)

    def test_sse_ready_event_uses_current_mtime_as_its_baseline(self):
        from wechat_decrypt_tool.routers import chat

        class RequestStub:
            async def is_disconnected(self):
                return True

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "account"
            db_storage_dir = root / "db_storage"
            account_dir.mkdir()
            db_storage_dir.mkdir()
            scans: list[str] = []

            def fake_scan(_path, *, scope="all"):
                scans.append(scope)
                return 123456789

            async def run_case():
                with (
                    mock.patch.object(chat, "_resolve_account_dir", return_value=account_dir),
                    mock.patch.object(chat.WCDB_REALTIME, "get_status", return_value={"db_storage_dir": str(db_storage_dir)}),
                    mock.patch.object(chat, "_scan_db_storage_mtime_ns", side_effect=fake_scan),
                ):
                    response = await chat.stream_chat_realtime_events(
                        RequestStub(),
                        account=account_dir.name,
                        scope="chat",
                    )
                    first_chunk = await response.body_iterator.__anext__()
                    await response.body_iterator.aclose()
                    return first_chunk

            first = asyncio.run(run_case())
            payload = json.loads(str(first).removeprefix("data: ").strip())
            self.assertEqual(payload["type"], "ready")
            self.assertEqual(payload["scope"], "chat")
            self.assertEqual(payload["mtimeNs"], 123456789)
            self.assertEqual(scans, ["chat"])


if __name__ == "__main__":
    unittest.main()
