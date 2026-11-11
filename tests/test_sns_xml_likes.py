import sqlite3
import json
import zipfile
from unittest import mock

import pytest
from wechat_decrypt_tool.routers import sns
from wechat_decrypt_tool import sns_export_service


def test_xml_likes_reach_timeline_and_export_snapshot(tmp_path):
    account = tmp_path / "account"
    account.mkdir()
    with sqlite3.connect(account / "sns.db") as conn:
        conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
        conn.execute("CREATE TABLE SnsMessage_tmp3 (local_id INTEGER, feed_id INTEGER, type INTEGER, from_username TEXT, from_nickname TEXT, del_status INTEGER)")
        xml = ('<SnsDataItem><TimelineObject><contentDesc>Post</contentDesc></TimelineObject>'
               '<LocalExtraInfo><like_user_list>'
               '<user_comment><username>alice</username><nickname>Alice</nickname></user_comment>'
               '<user_comment><username>bob</username><nickname>Bob</nickname></user_comment>'
               '<user_comment><username>deleted</username><b_deleted>1</b_deleted></user_comment>'
               '</like_user_list></LocalExtraInfo></SnsDataItem>')
        conn.execute("INSERT INTO SnsTimeLine VALUES (?, ?, ?)", (42, "author", xml))
        conn.executemany("INSERT INTO SnsMessage_tmp3 VALUES (?, ?, ?, ?, ?, ?)", [
            (1, 42, 1, "notification_only", "Not in XML", 0),
        ])

    with sqlite3.connect(account / "contact.db") as conn:
        conn.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, alias TEXT, big_head_url TEXT, small_head_url TEXT)")
        conn.execute("INSERT INTO contact VALUES (?, ?, ?, ?, ?, ?)", ("alice", "Alice 备注", "Alice 昵称", "", "", ""))

    with mock.patch.object(sns, "_resolve_account_dir", return_value=account):
        result = sns.list_sns_timeline(account="account", source="decrypted", limit=20, offset=0)
    snapshot = sns_export_service._load_sns_export_snapshot(account)
    assert result["timeline"][0]["likes"] == ["Alice 备注", "Bob"]
    assert snapshot[0]["posts"][0]["likes"] == ["Alice 备注", "Bob"]

    old_fingerprint = snapshot[0]["posts"][0]["_contentFingerprint"]
    with sqlite3.connect(account / "contact.db") as conn:
        conn.execute("UPDATE contact SET remark = '新备注' WHERE username = 'alice'")
    updated = sns_export_service._load_sns_export_snapshot(account)
    assert updated[0]["posts"][0]["likes"] == ["新备注", "Bob"]
    assert updated[0]["posts"][0]["_contentFingerprint"] != old_fingerprint


@pytest.mark.parametrize("export_format", ["html", "json", "txt", "excel"])
def test_all_export_formats_include_xml_likes(tmp_path, export_format):
    account = tmp_path / "account"
    account.mkdir()
    with sqlite3.connect(account / "sns.db") as conn:
        conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
        conn.execute("INSERT INTO SnsTimeLine VALUES (?, ?, ?)", (42, "author", '<SnsDataItem><TimelineObject><contentDesc>Post</contentDesc></TimelineObject><LocalExtraInfo><like_user_list><user_comment><username>alice</username><nickname>Alice</nickname></user_comment></like_user_list></LocalExtraInfo></SnsDataItem>'))
    job = sns_export_service.ExportJob(export_id=f"likes-{export_format}", account="account", options={"scope": "all", "format": export_format, "useCache": True, "outputDir": str(tmp_path), "fileName": f"{export_format}.zip"})
    assets = {"cssPath": "assets/a.css", "cssPayload": "", "jsPath": "assets/a.js", "jsPayload": ""}
    with (mock.patch.object(sns_export_service, "sync_sns_realtime_timeline_latest", return_value={"status": "noop"}),
          mock.patch.object(sns_export_service, "export_css", return_value=""),
          mock.patch.object(sns_export_service, "prepare_html_zip_assets", return_value=assets),
          mock.patch.object(sns_export_service, "protect_html_document_with_external_assets", side_effect=lambda doc, _: doc),
          mock.patch.object(sns_export_service, "write_active_html_zip_integrity"),
          mock.patch.object(sns_export_service, "write_zip_integrity_sidecars")):
        output = sns_export_service.SnsExportManager()._run_job(job, account)
    with zipfile.ZipFile(output) as archive:
        extension = {"html": "html", "json": "json", "txt": "txt", "excel": "xlsx"}[export_format]
        payload = archive.read(f"sns_author.{extension}")
        if export_format == "json":
            assert json.loads(payload)["posts"][0]["likes"] == ["Alice"]
        elif export_format == "excel":
            import io
            with zipfile.ZipFile(io.BytesIO(payload)) as workbook:
                assert any(b"Alice" in workbook.read(name) for name in workbook.namelist() if name.endswith(".xml"))
        else:
            assert "Alice" in payload.decode("utf-8")
