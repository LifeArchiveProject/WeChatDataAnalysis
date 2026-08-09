import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import favorites as favorites_router


def _msg_row(server_id: int, real_sender_id: int, **extra) -> dict:
    row = {
        "local_id": server_id,
        "server_id": server_id,
        "local_type": 1,
        "sort_seq": server_id,
        "real_sender_id": real_sender_id,
        "create_time": 1700000000,
        "status": 2,
        "upload_status": 0,
        "download_status": 0,
        "server_seq": 0,
        "origin_source": 0,
        "source": "",
        "message_content": "hello",
        "compress_content": None,
        "packed_info_data": None,
    }
    row.update(extra)
    return row


class TestFavoritesOriginalMessageDirection(unittest.TestCase):
    """Regression for issue #86: exported favorite records had isSent always false."""

    def _attach(self, *, items, select_handler):
        executed: list[str] = []
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_me_ab12"
            storage_dir = account_dir / "db_storage"
            message_dir = storage_dir / "message"
            message_dir.mkdir(parents=True)
            (message_dir / "message_0.db").write_bytes(b"")

            realtime = SimpleNamespace(
                lock=threading.Lock(),
                handle=object(),
                db_storage_dir=str(storage_dir),
                native_wxid="wxid_me_ab12",
            )

            def fake_exec_query(handle, *, kind, path, sql):
                executed.append(sql)
                if "sqlite_master" in sql:
                    return [{"name": "MsgTable"}]
                return select_handler(sql)

            ctx = SimpleNamespace(account_dir=account_dir)
            with (
                patch.object(
                    favorites_router,
                    "WCDB_REALTIME",
                    SimpleNamespace(ensure_connected=lambda account_dir: realtime),
                ),
                patch.object(favorites_router, "_wcdb_exec_query", fake_exec_query),
                patch.object(
                    favorites_router,
                    "_resolve_msg_table_name_by_map",
                    lambda table_map, conversation: "MsgTable",
                ),
                patch.object(favorites_router, "_postprocess_full_messages", lambda **kwargs: None),
            ):
                favorites_router._attach_original_messages(
                    ctx=ctx,
                    items=items,
                    base_url="http://127.0.0.1:10392",
                )
        return executed

    def test_sent_and_received_directions_survive_export(self):
        items = [
            {"conversationUsername": "friend_user", "sourceId": 101},
            {"conversationUsername": "friend_user", "sourceId": 102},
        ]

        def select_handler(sql):
            self.assertIn("LEFT JOIN Name2Id", sql)
            self.assertIn("__my_rowid", sql)
            self.assertIn("'wxid_me_ab12'", sql)
            return [
                _msg_row(101, 5, sender_username="wxid_me_ab12", __my_rowid=5),
                _msg_row(102, 7, sender_username="friend_user", __my_rowid=5),
            ]

        self._attach(items=items, select_handler=select_handler)

        mine = items[0].get("originalMessage")
        theirs = items[1].get("originalMessage")
        self.assertIsNotNone(mine)
        self.assertIsNotNone(theirs)
        self.assertTrue(mine["isSent"])
        self.assertFalse(theirs["isSent"])
        self.assertEqual(mine["senderUsername"], "wxid_me_ab12")
        self.assertEqual(theirs["senderUsername"], "friend_user")

    def test_join_failure_falls_back_to_plain_select(self):
        items = [{"conversationUsername": "friend_user", "sourceId": 101}]

        def select_handler(sql):
            if "LEFT JOIN Name2Id" in sql:
                raise RuntimeError("no such table: Name2Id")
            return [_msg_row(101, 5)]

        executed = self._attach(items=items, select_handler=select_handler)

        message = items[0].get("originalMessage")
        self.assertIsNotNone(message)
        # Degraded but attached: without Name2Id the direction stays unknown/false.
        self.assertFalse(message["isSent"])
        selects = [sql for sql in executed if "sqlite_master" not in sql]
        self.assertEqual(len(selects), 2)
        self.assertIn("SELECT * FROM", selects[1])


if __name__ == "__main__":
    unittest.main()
