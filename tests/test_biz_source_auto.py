import hashlib
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import biz as biz_router


class _DummyConn:
    def __init__(self) -> None:
        self.handle = 1
        self.lock = threading.Lock()


class TestBizSourceAuto(unittest.TestCase):
    def test_biz_list_auto_uses_real_name2id_column_not_literal_username(self):
        username = "gh_real_official"

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            live_dir = Path(td) / "db_storage"
            live_message_dir = live_dir / "message"
            live_message_dir.mkdir(parents=True, exist_ok=True)
            live_biz_db = live_message_dir / "biz_message_0.db"
            live_biz_db.touch()
            conn = _DummyConn()

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertEqual(Path(path), live_biz_db)
                sql_l = " ".join(str(sql).lower().split())
                if "pragma table_info(name2id)" in sql_l:
                    return [{"cid": 0, "name": "user_name", "type": "TEXT"}]
                if 'select "username" as username from name2id' in sql_l:
                    # SQLite can treat double-quoted unknown identifiers as string literals.
                    return [{"username": "username"}]
                if "select user_name as username from name2id" in sql_l or 'select "user_name" as username from name2id' in sql_l:
                    return [{"username": username}]
                if "max(create_time)" in sql_l:
                    return [{"max_time": 1700000000}]
                return []

            with (
                patch.object(biz_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(biz_router, "_resolve_account_db_storage_dir", return_value=live_dir),
                patch.object(
                    biz_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(live_dir)},
                ),
                patch.object(biz_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(biz_router, "_wcdb_exec_query", side_effect=fake_exec_query),
            ):
                resp = biz_router.get_biz_account_list(account="acc", source="auto")

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "realtime")
        data = resp.get("data") or []
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].get("username"), username)

    def test_biz_messages_auto_reads_realtime_rows_when_available(self):
        username = "gh_realtime_official"
        table_name = f"Msg_{hashlib.md5(username.encode('utf-8')).hexdigest().lower()}"
        xml = """
        <msg>
          <appmsg>
            <title>实时服务号文章</title>
            <des>来自 WCDB realtime</des>
            <url>https://example.test/article</url>
            <thumburl>https://example.test/cover.jpg</thumburl>
          </appmsg>
        </msg>
        """

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            live_dir = Path(td) / "db_storage"
            live_message_dir = live_dir / "message"
            live_message_dir.mkdir(parents=True, exist_ok=True)
            live_biz_db = live_message_dir / "biz_message_0.db"
            live_biz_db.touch()
            conn = _DummyConn()

            def fake_exec_query(_handle, *, kind, path, sql):
                self.assertEqual(kind, "message")
                self.assertEqual(Path(path), live_biz_db)
                sql_l = str(sql).lower()
                if "sqlite_master" in sql_l:
                    return [{"name": table_name}]
                if "select local_id" in sql_l:
                    return [
                        {
                            "local_id": 7,
                            "create_time": 1700000000,
                            "message_content": xml,
                        }
                    ]
                return []

            with (
                patch.object(biz_router, "_resolve_account_dir", return_value=account_dir),
                patch.object(biz_router, "_resolve_account_db_storage_dir", return_value=live_dir),
                patch.object(
                    biz_router.WCDB_REALTIME,
                    "get_status",
                    return_value={"dll_present": True, "key_present": True, "db_storage_dir": str(live_dir)},
                ),
                patch.object(biz_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
                patch.object(biz_router, "_wcdb_exec_query", side_effect=fake_exec_query),
            ):
                resp = biz_router.get_biz_messages(
                    username=username,
                    account="acc",
                    limit=20,
                    offset=0,
                    source="auto",
                )

        self.assertEqual(resp.get("status"), "success")
        self.assertEqual(resp.get("source"), "realtime")
        self.assertEqual((resp.get("data") or [])[0].get("title"), "实时服务号文章")


if __name__ == "__main__":
    unittest.main()
