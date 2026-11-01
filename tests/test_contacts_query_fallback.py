import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from wechat_decrypt_tool import native_core_realtime as native
from wechat_decrypt_tool.routers import chat_contacts as contacts


@pytest.fixture
def contact_query_env(tmp_path, monkeypatch):
    # 保留路由、WCDB 包装和备用查询的真实调用链，只替换原生查询边界。
    connection = SimpleNamespace(handle=1, lock=threading.RLock())
    monkeypatch.setattr(contacts, "_resolve_account_dir", lambda _: tmp_path)
    monkeypatch.setattr(contacts.WCDB_REALTIME, "ensure_connected", lambda _: connection)
    monkeypatch.setattr(contacts.WCDB_REALTIME, "get_recent_failure", lambda _: {})
    sessions = [{"username": f"{i}@chatroom"} for i in range(28)]
    sessions.append({"username": "wxid_friend_0"})
    monkeypatch.setattr(contacts, "_wcdb_get_sessions", lambda _: sessions)
    monkeypatch.setattr(contacts, "_wcdb_get_display_names", lambda *_: {})
    monkeypatch.setattr(contacts, "_wcdb_get_avatar_urls", lambda *_: {})
    monkeypatch.setattr(native, "_context", lambda _: SimpleNamespace())
    monkeypatch.setattr(native, "_default_database_path", lambda *_: tmp_path / "contact.db")
    with sqlite3.connect(tmp_path / "contact.db") as db:
        db.execute("CREATE TABLE contact (username TEXT, nick_name TEXT, local_type INTEGER)")
        db.executemany(
            "INSERT INTO contact VALUES (?, ?, 1)",
            [(f"wxid_friend_{i}", f"好友{i}") for i in range(306)],
        )
    db.close()
    return tmp_path


def read_contacts():
    return contacts.list_chat_contacts(
        SimpleNamespace(base_url="http://test/"), source="auto", include_groups=False,
    )


def test_failed_contact_queries_restore_snapshot_friends(contact_query_env, monkeypatch, caplog):
    query = Mock(side_effect=RuntimeError("contact query unavailable"))
    monkeypatch.setattr(native, "_query", query)

    response = read_contacts()

    assert response["source"] == "decrypted"
    assert response["sourceFallback"] is True
    assert "contact query unavailable" in response["sourceFallbackReason"]
    assert response["counts"]["friends"] == 306
    assert response["total"] == 306
    assert "contact query unavailable" in caplog.text
    # 主查询失败时不能用 stranger 的部分结果冒充完整通讯录。
    assert all("stranger" not in call.args[2] for call in query.call_args_list)


def test_failed_contact_queries_without_snapshot_report_error(contact_query_env, monkeypatch):
    (contact_query_env / "contact.db").unlink()
    monkeypatch.setattr(native, "_query", Mock(side_effect=RuntimeError("contact query unavailable")))

    with pytest.raises(HTTPException, match="contact query unavailable"):
        read_contacts()


def test_successful_empty_contact_query_keeps_realtime_source(contact_query_env, monkeypatch):
    monkeypatch.setattr(native, "_query", Mock(return_value=[]))
    compact = Mock(side_effect=AssertionError("空通讯录不应触发备用查询"))
    monkeypatch.setattr(contacts, "_wcdb_get_contacts_compact", compact)

    response = read_contacts()

    assert response["source"] == "realtime"
    assert not response["sourceFallback"]
    assert response["total"] == 0
    assert response["counts"]["friends"] == 0
    assert response["counts"]["groups"] == 28
    compact.assert_not_called()


@pytest.mark.parametrize("rows", [[], [{"username": "wxid_live_friend", "local_type": 1}]])
def test_compact_query_can_recover_primary_failure(contact_query_env, monkeypatch, rows):
    # 老接口不支持通用 SQL 时，备用接口成功（包括零行）仍应视为有效读取。
    monkeypatch.setattr(contacts, "_wcdb_exec_query", Mock(side_effect=RuntimeError("SQL unsupported")))
    monkeypatch.setattr(native, "_query", Mock(return_value=rows))

    response = read_contacts()

    assert response["source"] == "realtime"
    assert not response["sourceFallback"]
    assert response["total"] == len(rows)


def test_compact_full_query_does_not_substitute_strangers(contact_query_env, monkeypatch):
    query = Mock(side_effect=[RuntimeError("contact failed"), [{"username": "stranger"}]])
    monkeypatch.setattr(native, "_query", query)

    with pytest.raises(RuntimeError, match="contact failed"):
        native.get_contacts_compact(1, [])
    assert query.call_count == 1


def test_targeted_contact_query_tolerates_missing_stranger_table(contact_query_env, monkeypatch):
    row = {"username": "wxid_friend", "local_type": 1}
    monkeypatch.setattr(native, "_query", Mock(side_effect=[[row], RuntimeError("no such table: stranger")]))

    assert native.get_contact(1, "wxid_friend") == row
