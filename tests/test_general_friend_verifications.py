import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import general


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/api/general/friend-verifications",
            "headers": [],
        }
    )


class _StrictTextSource:
    def __init__(self, path: Path, source: str) -> None:
        self.source = source
        self.requested_source = source
        self.fallback_reason = ""
        self.retry_after_seconds = 0
        self.db_path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self._conn.close()

    def execute(self, sql: str, params=None):
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)


class TestGeneralFriendVerifications(unittest.TestCase):
    def _seed_general_db(self, path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            conn.executescript(
                """
                CREATE TABLE FMessageTable(
                    user_name_ TEXT,
                    type_ INTEGER,
                    timestamp_ INTEGER,
                    encrypt_user_name_ TEXT,
                    content_ TEXT,
                    is_sender_ INTEGER,
                    ticket_ TEXT,
                    scene_ INTEGER,
                    fmessage_detail_buf_ TEXT,
                    remark_ TEXT,
                    label_ids_ TEXT
                );
                INSERT INTO FMessageTable VALUES (
                    'wxid_friend', 1, 1735689600, 'encrypted-user', '你好', 0,
                    'ticket', 3, CAST(X'FFFE0A4208E6FCD2' AS TEXT), '备注', '1,2'
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _seed_friend_verification_state_dbs(
        self,
        general_path: Path,
        contact_path: Path,
    ) -> None:
        conn = sqlite3.connect(str(general_path))
        try:
            conn.executescript(
                """
                CREATE TABLE FMessageTable(
                    user_name_ TEXT,
                    type_ INTEGER,
                    timestamp_ INTEGER,
                    encrypt_user_name_ TEXT,
                    content_ TEXT,
                    is_sender_ INTEGER,
                    ticket_ TEXT,
                    scene_ INTEGER,
                    fmessage_detail_buf_ BLOB,
                    remark_ TEXT,
                    label_ids_ TEXT
                );
                INSERT INTO FMessageTable VALUES (
                    'wxid_accepted', 37, CAST(strftime('%s', 'now') AS INTEGER),
                    '', '已通过的申请', 0,
                    '', 14, X'2000', '', ''
                );
                INSERT INTO FMessageTable VALUES (
                    'wxid_pending', 37, CAST(strftime('%s', 'now') AS INTEGER) - 1,
                    '', '仍待处理的申请', 0,
                    '', 14, X'2000', '', ''
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        conn = sqlite3.connect(str(contact_path))
        try:
            conn.executescript(
                """
                CREATE TABLE contact(username TEXT, local_type INTEGER, flag INTEGER);
                INSERT INTO contact VALUES ('wxid_accepted', 1, 0);
                INSERT INTO contact VALUES ('wxid_pending', 3, 1);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def test_binary_detail_buffer_does_not_break_realtime_or_decrypted_results(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            account_dir.mkdir(parents=True)
            db_path = account_dir / "general.db"
            self._seed_general_db(db_path)
            ctx = SimpleNamespace(name="wxid_test", account_dir=account_dir)

            for source in ("realtime", "decrypted"):
                with self.subTest(source=source), patch.object(
                    general, "_general_context", return_value=(ctx, db_path)
                ), patch.object(
                    general,
                    "_open_general_source",
                    side_effect=lambda _ctx, selected: _StrictTextSource(db_path, selected),
                ), patch.object(general, "_resolve_general_contacts", return_value={}):
                    result = general.list_friend_verifications(
                        request=_request(),
                        account="wxid_test",
                        source=source,
                        limit=20,
                        offset=0,
                    )

                    self.assertEqual(result["dataSource"], source)
                    self.assertEqual(result["total"], 1)
                    self.assertEqual(result["items"][0]["userName"], "wxid_friend")
                    self.assertEqual(result["items"][0]["content"], "你好")
                    self.assertEqual(result["items"][0]["detailSize"], 8)

    def test_friend_membership_uses_local_type_before_pending_filter(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "wxid_test"
            account_dir.mkdir(parents=True)
            general_path = account_dir / "general.db"
            contact_path = account_dir / "contact.db"
            self._seed_friend_verification_state_dbs(general_path, contact_path)
            ctx = SimpleNamespace(name="wxid_test", account_dir=account_dir)

            with patch.object(
                general, "_general_context", return_value=(ctx, general_path)
            ), patch.object(
                general,
                "_open_general_source",
                side_effect=lambda _ctx, selected: _StrictTextSource(general_path, selected),
            ), patch.object(
                general,
                "_open_db_source",
                side_effect=lambda *_args, **_kwargs: _StrictTextSource(contact_path, "decrypted"),
            ), patch.object(general, "_resolve_general_contacts", return_value={}):
                result = general.list_friend_verifications(
                    request=_request(),
                    account="wxid_test",
                    source="decrypted",
                    limit=20,
                    offset=0,
                )
                by_username = {item["userName"]: item for item in result["items"]}

                self.assertEqual(by_username["wxid_accepted"]["verificationState"], "accepted")
                self.assertFalse(by_username["wxid_accepted"]["isPending"])
                self.assertEqual(by_username["wxid_pending"]["verificationState"], "pending")
                self.assertTrue(by_username["wxid_pending"]["isPending"])

                pending = general.list_friend_verifications(
                    request=_request(),
                    account="wxid_test",
                    source="decrypted",
                    limit=20,
                    offset=0,
                    pendingOnly=True,
                )

                self.assertEqual(pending["total"], 1)
                self.assertEqual(
                    [item["userName"] for item in pending["items"]],
                    ["wxid_pending"],
                )


if __name__ == "__main__":
    unittest.main()
