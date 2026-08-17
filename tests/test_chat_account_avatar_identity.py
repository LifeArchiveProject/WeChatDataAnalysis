import hashlib
import sqlite3
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wechat_decrypt_tool import chat_export_service
from wechat_decrypt_tool.routers import chat as chat_router
from wechat_decrypt_tool.wcdb_realtime import resolve_account_native_wxid


class _Request:
    base_url = "http://testserver/"


class _RealtimeConnection:
    def __init__(self, native_wxid: str) -> None:
        self.handle = 1
        self.lock = threading.Lock()
        self.native_wxid = native_wxid


def _context(tmp_path: Path, account: str = "SimpleChinese_a73c") -> SimpleNamespace:
    account_dir = tmp_path / account
    account_dir.mkdir()
    return SimpleNamespace(
        account_dir=account_dir,
        name=account,
        mode="direct",
        db_storage_path=str(tmp_path / account / "db_storage"),
        wxid_dir=str(tmp_path / account),
        has_decrypted_dbs=True,
        db_key_present=True,
        image_key_present=True,
        image_xor_key_present=True,
        image_aes_key_present=True,
        keys_ready=True,
        keys_updated_at="",
    )


def test_account_info_exposes_native_username_for_own_avatar(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    with (
        patch.object(chat_router, "list_countable_database_names", return_value=["head_image.db"]),
        patch.object(
            chat_router.WCDB_REALTIME,
            "get_status",
            return_value={
                "native_wxid": "SimpleChinese",
                "dll_present": True,
                "key_present": True,
                "db_storage_dir": ctx.db_storage_path,
                "session_db_path": str(Path(ctx.db_storage_path) / "session" / "session.db"),
            },
        ),
    ):
        info = chat_router._chat_account_context_public(ctx)

    assert info["account"] == "SimpleChinese_a73c"
    assert info["selfUsername"] == "SimpleChinese"
    assert info["nativeWxid"] == "SimpleChinese"
    assert info["realtime"]["nativeWxid"] == "SimpleChinese"


def test_account_info_prefers_explicit_realtime_native_username(tmp_path: Path) -> None:
    ctx = _context(tmp_path, "output_alias_a73c")
    with (
        patch.object(chat_router, "list_countable_database_names", return_value=[]),
        patch.object(
            chat_router.WCDB_REALTIME,
            "get_status",
            return_value={"native_wxid": "wxid_real_user"},
        ),
    ):
        info = chat_router._chat_account_context_public(ctx)

    assert info["account"] == "output_alias_a73c"
    assert info["selfUsername"] == "wxid_real_user"


def test_account_info_derives_native_username_when_realtime_status_omits_it(tmp_path: Path) -> None:
    ctx = _context(tmp_path, "wxid_example_a73c")
    with (
        patch.object(chat_router, "list_countable_database_names", return_value=[]),
        patch.object(chat_router.WCDB_REALTIME, "get_status", return_value={}),
    ):
        info = chat_router._chat_account_context_public(ctx)

    assert info["selfUsername"] == "wxid_example"


def test_native_username_derivation_preserves_internal_underscores(tmp_path: Path) -> None:
    account_dir = tmp_path / "wxid_real_user_a73c"
    account_dir.mkdir()

    assert resolve_account_native_wxid(account_dir) == "wxid_real_user"


def test_native_username_derivation_keeps_plain_ids_and_does_not_leak_between_accounts(tmp_path: Path) -> None:
    for name in ("wxid_demo", "wxid_dead", "alice_a73c", "bob_b4e5"):
        (tmp_path / name).mkdir()

    assert resolve_account_native_wxid(tmp_path / "wxid_demo") == "wxid_demo"
    assert resolve_account_native_wxid(tmp_path / "wxid_dead") == "wxid_dead"
    assert resolve_account_native_wxid(tmp_path / "alice_a73c") == "alice"
    assert resolve_account_native_wxid(tmp_path / "bob_b4e5") == "bob"


def test_realtime_sent_message_uses_native_username_for_own_avatar(tmp_path: Path) -> None:
    account = "satiagolovexia_8392"
    native_wxid = "satiagolovexia"
    account_dir = tmp_path / account
    account_dir.mkdir()
    conn = _RealtimeConnection(native_wxid)
    rows = [
        {
            "local_id": 1,
            "server_id": 10,
            "local_type": 1,
            "sort_seq": 1700000000000,
            "real_sender_id": 1,
            "create_time": 1700000000,
            "message_content": "sent by me",
            "compress_content": None,
            "packed_info_data": None,
            "msg_source": None,
            "sender_username": native_wxid,
            "computed_is_sent": 1,
        }
    ]

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
        patch.object(
            chat_router,
            "_fetch_realtime_message_rows_via_exec",
            return_value=([], False, None, "", None),
        ),
        patch.object(chat_router, "_fetch_realtime_message_rows_via_cursor", return_value=(rows, False)),
        patch.object(chat_router, "_load_contact_rows", return_value={}),
        patch.object(
            chat_router,
            "_query_head_image_usernames",
            side_effect=lambda _path, usernames: set(usernames),
        ),
        patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
        patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
        patch.object(chat_router, "_load_group_nickname_map", return_value={}),
    ):
        response = chat_router.list_chat_messages(
            _Request(),
            username="friend_user",
            account=account,
            source="realtime",
        )

    message = (response.get("messages") or [])[0]
    assert message["isSent"] is True
    assert message["senderUsername"] == native_wxid
    assert f"account={account}" in message["senderAvatar"]
    assert f"username={native_wxid}" in message["senderAvatar"]
    assert f"username={account}" not in message["senderAvatar"]


def test_realtime_native_sender_without_direction_flag_is_still_own_message(tmp_path: Path) -> None:
    account = "satiagolovexia_8392"
    native_wxid = "satiagolovexia"
    account_dir = tmp_path / account
    account_dir.mkdir()
    conn = _RealtimeConnection(native_wxid)
    rows = [
        {
            "local_id": 1,
            "server_id": 10,
            "local_type": 1,
            "sort_seq": 1700000000000,
            "real_sender_id": 1,
            "create_time": 1700000000,
            "message_content": "sent by me",
            "compress_content": None,
            "packed_info_data": None,
            "msg_source": None,
            "sender_username": native_wxid,
        }
    ]

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router.WCDB_REALTIME, "ensure_connected", return_value=conn),
        patch.object(
            chat_router,
            "_fetch_realtime_message_rows_via_exec",
            return_value=([], False, None, "", None),
        ),
        patch.object(chat_router, "_fetch_realtime_message_rows_via_cursor", return_value=(rows, False)),
        patch.object(chat_router, "_load_contact_rows", return_value={}),
        patch.object(
            chat_router,
            "_query_head_image_usernames",
            side_effect=lambda _path, usernames: set(usernames),
        ),
        patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
        patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
        patch.object(chat_router, "_load_group_nickname_map", return_value={}),
    ):
        response = chat_router.list_chat_messages(
            _Request(),
            username="friend_user",
            account=account,
            source="realtime",
        )

    message = (response.get("messages") or [])[0]
    assert message["isSent"] is True
    assert message["senderUsername"] == native_wxid
    assert f"account={account}" in message["senderAvatar"]
    assert f"username={native_wxid}" in message["senderAvatar"]


def test_decrypted_sent_message_uses_native_username_for_own_avatar(tmp_path: Path) -> None:
    account = "satiagolovexia_8392"
    native_wxid = "satiagolovexia"
    friend = "friend_user"
    account_dir = tmp_path / account
    account_dir.mkdir()
    message_db = account_dir / "message_0.db"
    table_name = f"msg_{hashlib.md5(friend.encode('utf-8')).hexdigest()}"

    conn = sqlite3.connect(message_db)
    try:
        conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
        conn.executemany(
            "INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)",
            [(1, native_wxid), (2, friend)],
        )
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                local_id INTEGER,
                server_id INTEGER,
                local_type INTEGER,
                sort_seq INTEGER,
                real_sender_id INTEGER,
                create_time INTEGER,
                message_content TEXT,
                compress_content BLOB
            )
            """
        )
        conn.execute(
            f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 10, 1, 1700000000000, 1, 1700000000, "sent by me", None),
        )
        conn.commit()
    finally:
        conn.close()

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router, "_iter_message_db_paths", return_value=[message_db]),
        patch.object(chat_router, "_load_contact_rows", return_value={}),
        patch.object(
            chat_router,
            "_query_head_image_usernames",
            side_effect=lambda _path, usernames: set(usernames),
        ),
        patch.object(chat_router, "_wcdb_get_display_names", return_value={}),
        patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
        patch.object(chat_router, "_load_group_nickname_map", return_value={}),
    ):
        response = chat_router.list_chat_messages(
            _Request(),
            username=friend,
            account=account,
            source="decrypted",
        )

    message = (response.get("messages") or [])[0]
    assert message["isSent"] is True
    assert message["senderUsername"] == native_wxid
    assert f"account={account}" in message["senderAvatar"]
    assert f"username={native_wxid}" in message["senderAvatar"]


def test_search_hit_uses_native_username_for_sent_message(tmp_path: Path) -> None:
    account_dir = tmp_path / "SimpleChinese_a73c"
    account_dir.mkdir()
    hit = chat_router._row_to_search_hit(
        {
            "local_id": 1,
            "server_id": 10,
            "local_type": 1,
            "sort_seq": 1700000000000,
            "real_sender_id": 1,
            "create_time": 1700000000,
            "message_content": "sent by me",
            "compress_content": None,
            "sender_username": "SimpleChinese",
        },
        db_path=account_dir / "message_0.db",
        table_name="msg_test",
        username="friend_user",
        account_dir=account_dir,
        is_group=False,
        my_rowid=1,
        self_username="SimpleChinese",
    )

    assert hit["isSent"] is True
    assert hit["senderUsername"] == "SimpleChinese"


def test_export_realtime_sent_message_keeps_native_sender_username(tmp_path: Path) -> None:
    account_dir = tmp_path / "SimpleChinese_a73c"
    account_dir.mkdir()

    row = chat_export_service._normalize_realtime_message_item_for_export(
        {
            "local_id": 1,
            "server_id": 10,
            "local_type": 1,
            "create_time": 1700000000,
            "message_content": "sent by me",
            "sender_username": "SimpleChinese",
            "computed_is_sent": 1,
        },
        account_dir=account_dir,
        conv_username="friend_user",
    )

    assert row.is_sent is True
    assert row.sender_username == "SimpleChinese"


def test_export_decrypted_sent_message_uses_native_sender_username(tmp_path: Path) -> None:
    account_dir = tmp_path / "SimpleChinese_a73c"
    account_dir.mkdir()
    friend = "friend_user"
    message_db = account_dir / "message_0.db"
    table_name = f"msg_{hashlib.md5(friend.encode('utf-8')).hexdigest()}"
    conn = sqlite3.connect(message_db)
    try:
        conn.execute("CREATE TABLE Name2Id (rowid INTEGER PRIMARY KEY, user_name TEXT)")
        conn.executemany(
            "INSERT INTO Name2Id(rowid, user_name) VALUES (?, ?)",
            [(1, "SimpleChinese"), (2, friend)],
        )
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                local_id INTEGER,
                server_id INTEGER,
                local_type INTEGER,
                sort_seq INTEGER,
                real_sender_id INTEGER,
                create_time INTEGER,
                message_content TEXT,
                compress_content BLOB
            )
            """
        )
        conn.execute(
            f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 10, 1, 1700000000000, 1, 1700000000, "sent by me", None),
        )
        conn.commit()
    finally:
        conn.close()

    with patch.object(chat_export_service, "_iter_message_db_paths", return_value=[message_db]):
        rows = list(
            chat_export_service._iter_rows_for_conversation(
                account_dir=account_dir,
                conv_username=friend,
                start_time=None,
                end_time=None,
                source="decrypted",
            )
        )

    assert len(rows) == 1
    assert rows[0].is_sent is True
    assert rows[0].sender_username == "SimpleChinese"


def test_prepared_html_export_uses_native_self_avatar_in_left_rail(tmp_path: Path) -> None:
    account_dir = tmp_path / "SimpleChinese_a73c"
    account_dir.mkdir()
    head_image_db = account_dir / "head_image.db"
    conn = sqlite3.connect(head_image_db)
    try:
        conn.execute(
            "CREATE TABLE head_image(username TEXT PRIMARY KEY, md5 TEXT, image_buffer BLOB, update_time INTEGER)"
        )
        conn.execute(
            "INSERT INTO head_image(username, md5, image_buffer, update_time) VALUES (?, ?, ?, ?)",
            ("SimpleChinese", "avatar-md5", b"\x89PNG\r\n\x1a\n" + b"avatar", 1),
        )
        conn.commit()
    finally:
        conn.close()

    with patch.object(chat_export_service, "write_active_html_zip_integrity", return_value=None):
        job = chat_export_service.export_prepared_chat_archive(
            account_dir=account_dir,
            output_dir=tmp_path / "exports",
            file_name="self-avatar.zip",
            title="聊天记录",
            export_format="html",
            conversations=[
                {
                    "username": "friend_user",
                    "displayName": "Friend",
                    "messages": [
                        {
                            "id": "message-1",
                            "renderType": "text",
                            "content": "sent by me",
                            "senderUsername": "SimpleChinese",
                            "isSent": True,
                            "createTime": 1700000000,
                        }
                    ],
                }
            ],
            include_media=False,
            media_kinds=[],
            message_types=["text"],
        )

    assert job.status == "done", job.error
    assert job.zip_path is not None
    with zipfile.ZipFile(job.zip_path, "r") as zf:
        html_path = next(name for name in zf.namelist() if name.endswith("/messages.html"))
        html_text = zf.read(html_path).decode("utf-8")
        rail_fragment = html_text.split('data-wce-rail-avatar="1"', 1)[1].split("</div>", 1)[0]
        assert "<img " in rail_fragment
        assert "media/avatars/SimpleChinese_" in rail_fragment
