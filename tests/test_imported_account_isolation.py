from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wechat_decrypt_tool.account_identity import (
    account_identity_candidates,
    resolve_account_self_rowid,
    resolve_account_self_username,
)
from wechat_decrypt_tool import media_helpers, wcdb_realtime
from wechat_decrypt_tool.routers import biz as biz_router
from wechat_decrypt_tool.routers import chat as chat_router
from wechat_decrypt_tool.routers import chat_contacts as contacts_router
from wechat_decrypt_tool.routers import general as general_router
from wechat_decrypt_tool.routers import import_decrypted


def _create_sqlite(path: Path, statements: tuple[str, ...] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def _mark_imported_snapshot(account_dir: Path, username: str) -> None:
    (account_dir / "account.json").write_text(
        json.dumps({"username": username, "nick": "Windows Account"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (account_dir / "_source.json").write_text(
        json.dumps(
            {
                "import_mode": "manual_import",
                # Old releases wrote the archive path into this live-source
                # field. The import marker must still take precedence.
                "db_storage_path": "/HOST/archive/windows-export",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _create_snapshot_pair(account_dir: Path, username: str) -> None:
    account_dir.mkdir(parents=True, exist_ok=True)
    _create_sqlite(
        account_dir / "session.db",
        (
            "CREATE TABLE SessionTable ("
            "username TEXT, unread_count INTEGER, is_hidden INTEGER, summary TEXT, "
            "draft TEXT, last_timestamp INTEGER, sort_timestamp INTEGER, "
            "last_msg_locald_id INTEGER, last_msg_type INTEGER, "
            "last_msg_sub_type INTEGER, last_msg_sender TEXT, "
            "last_sender_display_name TEXT)",
            "INSERT INTO SessionTable VALUES "
            "('wxid_windows_friend', 0, 0, 'from windows archive', '', "
            "100, 100, 1, 1, 0, '', '')",
        ),
    )
    _create_sqlite(
        account_dir / "contact.db",
        (
            "CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, alias TEXT)",
        ),
    )
    _mark_imported_snapshot(account_dir, username)


async def _consume_import(import_path: Path) -> list[dict]:
    response = await import_decrypted.import_decrypted_directory(
        import_path=str(import_path),
        job_id="import-isolation-fixture",
    )
    payload = ""
    async for chunk in response.body_iterator:
        payload += chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
    events = []
    for block in payload.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


def test_identity_candidates_use_account_metadata_not_db_storage_leaf(tmp_path: Path) -> None:
    account_dir = tmp_path / "renamed-account"
    account_dir.mkdir()
    (account_dir / "_source.json").write_text(
        json.dumps(
            {
                "db_storage_path": (
                    r"C:\Users\fixture\Documents\xwechat_files"
                    r"\wxid_demo_abcd\db_storage"
                )
            }
        ),
        encoding="utf-8",
    )

    candidates = account_identity_candidates(account_dir)

    assert candidates[:2] == ["wxid_demo", "wxid_demo_abcd"]
    assert "db_storage" not in candidates

    direct_alias_dir = tmp_path / "wxid_demo_abcd"
    direct_alias_dir.mkdir()
    assert resolve_account_self_username(direct_alias_dir) == "wxid_demo_abcd"


def test_directory_import_keeps_rollback_outside_account_discovery(tmp_path: Path) -> None:
    source_account = tmp_path / "windows-export" / "wxid_windows"
    _create_snapshot_pair(source_account, "wxid_windows")
    output_dir = tmp_path / "mac-data" / "output" / "databases"
    existing_dir = output_dir / "wxid_windows"
    existing_dir.mkdir(parents=True)
    (existing_dir / "old-mac-data.txt").write_text("old mac data", encoding="utf-8")

    with (
        patch.object(import_decrypted, "get_output_databases_dir", return_value=output_dir),
        patch.object(import_decrypted, "get_data_dir", return_value=tmp_path / "mac-data"),
        patch.object(wcdb_realtime.WCDB_REALTIME, "disconnect") as disconnect,
    ):
        events = asyncio.run(_consume_import(source_account))

    assert events[-1]["type"] == "complete", events
    imported_dir = output_dir / "wxid_windows"
    source_info = json.loads((imported_dir / "_source.json").read_text(encoding="utf-8"))
    backup_dir = Path(events[-1]["backup_dir"])
    assert backup_dir.parent == (
        tmp_path / "mac-data" / "output" / "account_backups" / "wxid_windows"
    )
    assert (backup_dir / "old-mac-data.txt").read_text(encoding="utf-8") == "old mac data"
    assert not list(output_dir.glob("wxid_windows.backup-*"))
    assert source_info["import_mode"] == "manual_import"
    assert source_info["import_source_path"] == str(source_account)
    assert "db_storage_path" not in source_info
    disconnect.assert_called_once_with("wxid_windows")


def test_imported_snapshot_auto_sessions_never_open_host_realtime_store(tmp_path: Path) -> None:
    account_dir = tmp_path / "wxid_windows"
    _create_snapshot_pair(account_dir, "wxid_windows")

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router.WCDB_REALTIME, "ensure_connected") as ensure_connected,
        patch.object(chat_router.WCDB_REALTIME, "get_status") as get_status,
        patch.object(
            chat_router,
            "_load_contact_rows",
            return_value={
                "wxid_windows_friend": {
                    "username": "wxid_windows_friend",
                    "remark": "",
                    "nick_name": "Windows Friend",
                    "alias": "",
                }
            },
        ),
        patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
        patch.object(chat_router, "_avatar_url_unified", return_value=""),
    ):
        response = chat_router.list_chat_sessions(
            SimpleNamespace(base_url="http://testserver/"),
            account=account_dir.name,
            limit=50,
            include_hidden=True,
            include_official=True,
            preview="session",
            source="auto",
        )

    assert response["source"] == "decrypted"
    assert response["sessions"][0]["username"] == "wxid_windows_friend"
    assert response["sessions"][0]["lastMessage"] == "from windows archive"
    ensure_connected.assert_not_called()
    get_status.assert_not_called()


def test_imported_snapshot_account_info_reports_decrypted_as_active_source(
    tmp_path: Path,
) -> None:
    account_dir = tmp_path / "wxid_windows"
    _create_snapshot_pair(account_dir, "wxid_windows")
    context = SimpleNamespace(
        name="wxid_windows",
        account_dir=account_dir,
        prefers_decrypted_snapshot=True,
        db_storage_path="/HOST/mac-live/db_storage",
        wxid_dir="/HOST/mac-live",
        has_decrypted_dbs=True,
        db_key_present=True,
        image_key_present=False,
        image_xor_key_present=False,
        image_aes_key_present=False,
        keys_ready=False,
        mode="decrypted",
        keys_updated_at="",
    )

    with patch.object(chat_router.WCDB_REALTIME, "get_status") as get_status:
        result = chat_router._chat_account_context_public(context)

    assert result["defaultSource"] == "decrypted"
    assert result["dataSourceStatus"]["activeSource"] == "decrypted"
    assert result["dbStoragePath"] == ""
    assert result["dataSourcePath"] == str(account_dir)
    assert result["realtimeAvailable"] is False
    get_status.assert_not_called()


def test_imported_snapshot_realtime_probe_is_skipped(tmp_path: Path) -> None:
    account_dir = tmp_path / "wxid_windows"
    _create_snapshot_pair(account_dir, "wxid_windows")

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router.WCDB_REALTIME, "get_status") as get_status,
        patch.object(chat_router.WCDB_REALTIME, "ensure_connected") as ensure_connected,
    ):
        response = asyncio.run(
            chat_router.get_chat_realtime_status(account=account_dir.name)
        )

    assert response["available"] is False
    assert response["realtime"]["snapshot_preferred"] is True
    assert response["realtime"]["probe_attempted"] is False
    get_status.assert_not_called()
    ensure_connected.assert_not_called()


def test_imported_snapshot_policy_covers_contacts_biz_and_media_paths(
    tmp_path: Path,
) -> None:
    account_dir = tmp_path / "wxid_windows"
    _create_snapshot_pair(account_dir, "wxid_windows")

    with patch.object(biz_router, "_is_biz_realtime_available") as realtime_available:
        biz_source = biz_router._resolve_biz_source_for_account("auto", account_dir)

    assert contacts_router._resolve_contacts_source_for_account("auto", account_dir) == "decrypted"
    assert biz_source == "decrypted"
    assert media_helpers._resolve_account_db_storage_dir(account_dir) is None
    assert media_helpers._resolve_account_wxid_dir(account_dir) is None
    realtime_available.assert_not_called()


def test_imported_snapshot_general_auto_uses_local_database(tmp_path: Path) -> None:
    account_dir = tmp_path / "wxid_windows"
    _create_snapshot_pair(account_dir, "wxid_windows")
    _create_sqlite(
        account_dir / "general.db",
        (
            "CREATE TABLE fixture (value TEXT)",
            "INSERT INTO fixture VALUES ('from Windows archive')",
        ),
    )
    context = SimpleNamespace(
        account_dir=account_dir,
        name=account_dir.name,
        db_key_present=True,
        db_storage_path="/HOST/mac-live/db_storage",
        wxid_dir="/HOST/mac-live",
        prefers_decrypted_snapshot=True,
    )

    with patch.object(general_router, "_open_realtime_db_source") as open_realtime:
        with general_router._open_db_source(
            context,
            source="auto",
            db_group="general",
            db_name="general.db",
            decrypted_name="general.db",
        ) as source:
            value = source.execute("SELECT value FROM fixture").fetchone()[0]

    assert value == "from Windows archive"
    assert source.source == "decrypted"
    open_realtime.assert_not_called()


def test_imported_snapshot_recovers_self_rowid_and_message_direction(tmp_path: Path) -> None:
    canonical_account = "wxid_windows"
    account_dir = tmp_path / f"{canonical_account}.backup-20260812-200746"
    _create_snapshot_pair(account_dir, canonical_account)
    username = "wxid_windows_friend"
    table_name = "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()

    connection = sqlite3.connect(str(account_dir / "message_0.db"))
    try:
        connection.execute("CREATE TABLE Name2Id (user_name TEXT)")
        connection.execute(
            "INSERT INTO Name2Id(rowid, user_name) VALUES (1, ?)",
            (canonical_account,),
        )
        connection.execute(
            "INSERT INTO Name2Id(rowid, user_name) VALUES (2, ?)",
            (username,),
        )
        connection.execute(
            f"CREATE TABLE {table_name} ("
            "local_id INTEGER, server_id INTEGER, local_type INTEGER, sort_seq INTEGER, "
            "real_sender_id INTEGER, create_time INTEGER, message_content TEXT, "
            "compress_content BLOB)"
        )
        connection.execute(
            f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, 101, 1, 1000, 1, 100, "sent from Windows", None),
        )
        connection.execute(
            f"INSERT INTO {table_name} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (2, 102, 1, 2000, 2, 200, "received on Windows", None),
        )
        connection.commit()

        self_rowid, matched_username = resolve_account_self_rowid(
            connection,
            account_dir,
        )
    finally:
        connection.close()

    assert self_rowid == 1
    assert matched_username == canonical_account

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router.WCDB_REALTIME, "ensure_connected") as ensure_connected,
        patch.object(chat_router, "_load_contact_rows", return_value={}),
        patch.object(chat_router, "_query_head_image_usernames", return_value=set()),
        patch.object(chat_router, "_load_usernames_by_display_names", return_value={}),
    ):
        response = chat_router.list_chat_messages(
            SimpleNamespace(base_url="http://testserver/"),
            username=username,
            account=account_dir.name,
            limit=50,
            offset=0,
            order="asc",
            source="auto",
        )

    messages = response["messages"]
    assert response["source"] == "decrypted"
    assert [message["isSent"] for message in messages] == [True, False]
    assert messages[0]["senderUsername"] == canonical_account
    assert messages[1]["senderUsername"] == username
    ensure_connected.assert_not_called()


def test_delete_resolved_account_removes_rollbacks_exports_and_key_aliases(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    databases_dir = output_dir / "databases"
    canonical_account = "wxid_windows"
    stale_alias = f"{canonical_account}_1e7a"
    account_dir = databases_dir / canonical_account
    account_dir.mkdir(parents=True)
    (account_dir / "session.db").write_bytes(b"fixture")
    stale_alias_dir = databases_dir / stale_alias
    stale_alias_dir.mkdir()
    (stale_alias_dir / "session.db").write_bytes(b"stale")

    structured_backup = output_dir / "account_backups" / canonical_account / "20260812-200746"
    structured_backup.mkdir(parents=True)
    alias_structured_backup = output_dir / "account_backups" / stale_alias / "20260812-200747"
    alias_structured_backup.mkdir(parents=True)
    legacy_backup = databases_dir / f"{canonical_account}.backup-20260812-200746"
    legacy_backup.mkdir()
    exports_dir = output_dir / "exports" / canonical_account
    exports_dir.mkdir(parents=True)
    alias_exports_dir = output_dir / "exports" / stale_alias
    alias_exports_dir.mkdir(parents=True)

    with (
        patch.object(chat_router, "_resolve_account_dir", return_value=account_dir),
        patch.object(chat_router, "get_output_dir", return_value=output_dir),
        patch.object(
            chat_router,
            "remove_account_family_keys_from_store",
            return_value=[canonical_account, stale_alias],
        ) as remove_keys,
        patch.object(chat_router, "_list_decrypted_accounts", return_value=[]),
        patch.object(chat_router.WCDB_REALTIME, "disconnect"),
    ):
        response = chat_router.delete_chat_account(stale_alias)

    assert response["deleted_account"] == canonical_account
    assert response["removed_key_accounts"] == [canonical_account, stale_alias]
    assert not account_dir.exists()
    assert not stale_alias_dir.exists()
    assert not structured_backup.exists()
    assert not alias_structured_backup.exists()
    assert not legacy_backup.exists()
    assert not exports_dir.exists()
    assert not alias_exports_dir.exists()
    remove_keys.assert_called_once_with(canonical_account)


def test_import_page_forces_account_refresh_and_selects_completed_import() -> None:
    source = Path("frontend/pages/import.vue").read_text(encoding="utf-8")

    assert '@click="enterImportedChat"' in source
    assert "import { useChatAccountsStore } from '~/stores/chatAccounts'" in source
    assert "await chatAccounts.ensureLoaded({ force: true })" in source
    assert "chatAccounts.setSelectedAccount(importedAccount)" in source
    assert "await selectImportedAccount(data.account)" in source

    realtime_store = Path("frontend/stores/chatRealtime.js").read_text(encoding="utf-8")
    assert "const snapshotPreferred = !!info?.snapshot_preferred" in realtime_store
    assert "fallbackActive: !isAvailable" in realtime_store
    assert "fallbackActive: false" in realtime_store


def test_desktop_fallback_ignores_legacy_backup_accounts_and_removes_alias_family() -> None:
    source = Path("desktop/src/main.cjs").read_text(encoding="utf-8")

    assert "isInternalAccountDataDirectory(entry.name)" in source
    assert "removeAccountFamilyFromKeyStore(outputDir, accountName)" in source
    assert 'path.join(outputDir, "account_backups", cleanupName)' in source
    assert "const accountDirsToRemove = new Set([accountDir])" in source
    assert "canonicalAccountKeyName(requestedAccountName)" in source
