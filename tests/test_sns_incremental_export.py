import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import sns_export_service as service  # noqa: E402


def _timeline_xml(text: str, comment: str = "") -> str:
    return (
        "<TimelineObject><username>wxid_friend</username>"
        "<createTime>1700000000</createTime>"
        f"<contentDesc>{text}</contentDesc>"
        "<ContentObject><type>1</type></ContentObject>"
        f"<commentList><comment><nickname>Bob</nickname><content>{comment}</content></comment></commentList>"
        "</TimelineObject>"
    )


def test_snapshot_scan_groups_rows_and_hashes_raw_content():
    with TemporaryDirectory() as td:
        account_dir = Path(td) / "wxid_me"
        account_dir.mkdir()
        conn = sqlite3.connect(account_dir / "sns.db")
        conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
        conn.execute("INSERT INTO SnsTimeLine VALUES (?, ?, ?)", (42, "wxid_friend", _timeline_xml("正文", "旧评论")))
        conn.commit()
        conn.close()

        users = service._load_sns_export_snapshot(account_dir, usernames=["wxid_friend"])

        assert len(users) == 1
        assert users[0]["postCount"] == 1
        assert users[0]["posts"][0]["id"] == "42"
        assert len(users[0]["posts"][0]["_contentFingerprint"]) == 64


def test_incremental_baseline_detects_comment_and_profile_changes_and_keeps_name():
    with TemporaryDirectory() as td:
        account_dir = Path(td) / "wxid_me"
        account_dir.mkdir()
        first_users = [{
            "username": "wxid_friend",
            "displayName": "原备注",
            "posts": [{"id": "42", "_contentFingerprint": "old"}],
            "cover": {"_contentFingerprint": "cover"},
        }]
        with mock.patch.object(service, "_account_display_name", return_value="我"):
            first, _old, changed, folder, warning = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="html",
                users=first_users,
                requested_folder_name="",
                supplied_baseline={},
                reset_baseline=False,
            )
        assert changed == {"wxid_friend"}
        assert folder == "原备注_朋友圈"
        assert warning == ""

        first["files"] = {"原备注.html": {"sha256": "abc", "size": 3}}
        next_users = [{
            "username": "wxid_friend",
            "displayName": "新备注",
            "posts": [{"id": "42", "_contentFingerprint": "comment-changed"}],
            "cover": {"_contentFingerprint": "cover"},
        }]
        with mock.patch.object(service, "_account_display_name", return_value="我"):
            second, _old, changed, _folder, _warning = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="html",
                users=next_users,
                requested_folder_name=folder,
                supplied_baseline=first,
                reset_baseline=False,
            )
        assert changed == {"wxid_friend"}
        assert second["users"]["wxid_friend"]["output"] == "原备注.html"


def test_browser_patch_stages_state_last_and_reuses_unchanged_files():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_me"
        account_dir.mkdir()
        users = [{
            "username": "wxid_friend",
            "displayName": "Alice",
            "posts": [{"id": "42", "_contentFingerprint": "same"}],
            "cover": None,
        }]
        with mock.patch.object(service, "_account_display_name", return_value="Me"):
            state, old, changed, folder, _warning = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="json",
                users=users,
                requested_folder_name="",
                supplied_baseline={},
                reset_baseline=False,
            )
        archive_path = root / "patch.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("Alice.json", "{}")
            archive.writestr("assets/image.jpg", b"image")

        manager = service.SnsExportManager()
        first_job = service.ExportJob(export_id="first", account="wxid_me")
        manager._materialize_folder_export(
            job=first_job,
            zip_path=archive_path,
            exports_root=root,
            account_dir=account_dir,
            export_format="json",
            users=users,
            state=state,
            old_state=old,
            changed_users=changed,
            folder_name=folder,
            desktop_output=False,
            reset_baseline=False,
        )
        assert first_job.change_manifest["files"]
        state_path = manager.get_staged_file("missing", "missing")
        assert state_path is None
        baseline_file = first_job.staged_files[first_job.change_manifest["state"]["fileId"]]
        persisted = json.loads(baseline_file.read_text(encoding="utf-8"))

        with mock.patch.object(service, "_account_display_name", return_value="Me"):
            next_state, next_old, next_changed, _, _ = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="json",
                users=users,
                requested_folder_name=folder,
                supplied_baseline=persisted,
                reset_baseline=False,
            )
        second_job = service.ExportJob(export_id="second", account="wxid_me")
        manager._materialize_folder_export(
            job=second_job,
            zip_path=archive_path,
            exports_root=root,
            account_dir=account_dir,
            export_format="json",
            users=users,
            state=next_state,
            old_state=next_old,
            changed_users=next_changed,
            folder_name=folder,
            desktop_output=False,
            reset_baseline=False,
        )
        assert next_changed == set()
        assert second_job.incremental["usersReused"] == 1
        assert second_job.change_manifest["files"] == []


def test_browser_patch_restores_only_missing_managed_media():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_me"
        account_dir.mkdir()
        users = [{
            "username": "wxid_friend",
            "displayName": "Alice",
            "posts": [{"id": "42", "_contentFingerprint": "same"}],
            "cover": None,
        }]
        with mock.patch.object(service, "_account_display_name", return_value="Me"):
            state, old, changed, folder, _warning = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="html",
                users=users,
                requested_folder_name="",
                supplied_baseline={},
                reset_baseline=False,
            )

        archive_path = root / "first.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("Alice.html", '<img src="media/photo.jpg">')
            archive.writestr("media/photo.jpg", b"photo")

        manager = service.SnsExportManager()
        first_job = service.ExportJob(export_id="browser-first", account="wxid_me")
        manager._materialize_folder_export(
            job=first_job,
            zip_path=archive_path,
            exports_root=root,
            account_dir=account_dir,
            export_format="html",
            users=users,
            state=state,
            old_state=old,
            changed_users=changed,
            folder_name=folder,
            desktop_output=False,
            reset_baseline=False,
        )
        baseline_path = first_job.staged_files[first_job.change_manifest["state"]["fileId"]]
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

        with mock.patch.object(service, "_account_display_name", return_value="Me"):
            next_state, next_old, next_changed, _, _ = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="html",
                users=users,
                requested_folder_name=folder,
                supplied_baseline=baseline,
                reset_baseline=False,
                missing_files=["media/photo.jpg"],
            )
        assert next_changed == {"wxid_friend"}

        second_job = service.ExportJob(export_id="browser-repair", account="wxid_me")
        manager._materialize_folder_export(
            job=second_job,
            zip_path=archive_path,
            exports_root=root,
            account_dir=account_dir,
            export_format="html",
            users=users,
            state=next_state,
            old_state=next_old,
            changed_users=next_changed,
            folder_name=folder,
            desktop_output=False,
            reset_baseline=False,
            missing_files=["media/photo.jpg"],
        )
        assert [entry["path"] for entry in second_job.change_manifest["files"]] == ["media/photo.jpg"]
        assert second_job.incremental["filesChanged"] == 1
        assert second_job.incremental["filesReused"] == 1


def test_changed_html_removes_only_files_managed_by_old_baseline():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_me"
        account_dir.mkdir()
        users = [{
            "username": "wxid_friend",
            "displayName": "Alice",
            "posts": [{"id": "42", "_contentFingerprint": "v1"}],
            "cover": None,
        }]
        with mock.patch.object(service, "_account_display_name", return_value="Me"):
            state, old, changed, folder, _ = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="html",
                users=users,
                requested_folder_name="",
                supplied_baseline={},
                reset_baseline=False,
            )
        first_zip = root / "first.zip"
        with zipfile.ZipFile(first_zip, "w") as archive:
            archive.writestr("Alice.html", '<img src="media/old.jpg">')
            archive.writestr("media/old.jpg", b"old")
        manager = service.SnsExportManager()
        first_job = service.ExportJob(export_id="html-first", account="wxid_me")
        manager._materialize_folder_export(
            job=first_job,
            zip_path=first_zip,
            exports_root=root,
            account_dir=account_dir,
            export_format="html",
            users=users,
            state=state,
            old_state=old,
            changed_users=changed,
            folder_name=folder,
            desktop_output=False,
            reset_baseline=False,
        )
        baseline_path = first_job.staged_files[first_job.change_manifest["state"]["fileId"]]
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline["files"]["user-note.txt"] = {"sha256": "custom", "size": 6}

        changed_users = [{
            "username": "wxid_friend",
            "displayName": "Alice",
            "posts": [{"id": "42", "_contentFingerprint": "v2"}],
            "cover": None,
        }]
        with mock.patch.object(service, "_account_display_name", return_value="Me"):
            next_state, next_old, next_changed, _, _ = service._prepare_incremental_baseline(
                account_dir=account_dir,
                export_format="html",
                users=changed_users,
                requested_folder_name=folder,
                supplied_baseline=baseline,
                reset_baseline=False,
            )
        next_zip = root / "next.zip"
        with zipfile.ZipFile(next_zip, "w") as archive:
            archive.writestr("Alice.html", "<p>updated</p>")
        next_job = service.ExportJob(export_id="html-next", account="wxid_me")
        manager._materialize_folder_export(
            job=next_job,
            zip_path=next_zip,
            exports_root=root,
            account_dir=account_dir,
            export_format="html",
            users=changed_users,
            state=next_state,
            old_state=next_old,
            changed_users=next_changed,
            folder_name=folder,
            desktop_output=False,
            reset_baseline=False,
        )
        assert "media/old.jpg" in next_job.change_manifest["stale"]
        # 清理列表严格来自旧基线；目录中未记录的用户文件不会被扫描或删除。
        assert "user-note.txt" in next_job.change_manifest["stale"]


def test_desktop_folder_export_is_atomic_and_second_run_reuses_contact_file():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_me"
        account_dir.mkdir()
        conn = sqlite3.connect(account_dir / "sns.db")
        conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
        conn.execute("INSERT INTO SnsTimeLine VALUES (?, ?, ?)", (42, "wxid_friend", _timeline_xml("正文")))
        conn.commit()
        conn.close()

        manager = service.SnsExportManager()
        options = {
            "scope": "selected",
            "usernames": ["wxid_friend"],
            "format": "txt",
            "useCache": True,
            "outputDir": str(root),
            "outputMode": "folder",
            "folderName": "Alice_朋友圈",
        }
        first_job = service.ExportJob(export_id="desktop-first", account="wxid_me", options=dict(options))
        with (
            mock.patch.object(service, "sync_sns_realtime_timeline_latest", return_value={"status": "ok"}),
            mock.patch.object(service, "write_zip_integrity_sidecars"),
            mock.patch.object(service, "_account_display_name", return_value="Me"),
        ):
            output = manager._run_job(first_job, account_dir)
        contact_file = output / "wxid_friend.txt"
        assert contact_file.is_file()
        assert (output / ".wechat-sns-export.json").is_file()
        before = contact_file.stat().st_mtime_ns

        second_job = service.ExportJob(export_id="desktop-second", account="wxid_me", options=dict(options))
        with (
            mock.patch.object(service, "sync_sns_realtime_timeline_latest", return_value={"status": "noop"}),
            mock.patch.object(service, "write_zip_integrity_sidecars"),
            mock.patch.object(service, "_account_display_name", return_value="Me"),
        ):
            second_output = manager._run_job(second_job, account_dir)
        assert second_output == output
        assert contact_file.stat().st_mtime_ns == before
        assert second_job.incremental["usersReused"] == 1
        assert second_job.incremental["filesChanged"] == 0

        # 直接选中已有导出根目录时，应在原目录增量补回，不能再创建同名子目录。
        contact_file.unlink()
        direct_options = {**options, "outputDir": str(output)}
        repair_job = service.ExportJob(export_id="desktop-repair", account="wxid_me", options=direct_options)
        with (
            mock.patch.object(service, "sync_sns_realtime_timeline_latest", return_value={"status": "noop"}),
            mock.patch.object(service, "write_zip_integrity_sidecars"),
            mock.patch.object(service, "_account_display_name", return_value="Me"),
        ):
            repair_output = manager._run_job(repair_job, account_dir)
        assert repair_output == output
        assert contact_file.is_file()
        assert not (output / "Alice_朋友圈").exists()
        assert repair_job.incremental["filesChanged"] == 1


def test_html_folder_export_uses_stable_css_without_zip_integrity_runtime():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "wxid_me"
        account_dir.mkdir()
        conn = sqlite3.connect(account_dir / "sns.db")
        conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
        conn.execute("INSERT INTO SnsTimeLine VALUES (?, ?, ?)", (42, "wxid_friend", _timeline_xml("正文")))
        conn.commit()
        conn.close()
        avatar = sqlite3.connect(account_dir / "head_image.db")
        avatar.execute("CREATE TABLE head_image (username TEXT, md5 TEXT, update_time INTEGER, image_buffer BLOB)")
        avatar.execute("INSERT INTO head_image VALUES (?, ?, ?, ?)", ("wxid_friend", "avatar", 1, b"\x89PNG\r\n\x1a\n"))
        avatar.commit()
        avatar.close()

        manager = service.SnsExportManager()
        job = service.ExportJob(
            export_id="desktop-html",
            account="wxid_me",
            options={
                "scope": "selected",
                "usernames": ["wxid_friend"],
                "format": "html",
                "useCache": True,
                "outputDir": str(root),
                "outputMode": "folder",
                "folderName": "Alice_朋友圈",
            },
        )
        with (
            mock.patch.object(service, "sync_sns_realtime_timeline_latest", return_value={"status": "ok"}),
            mock.patch.object(service, "export_css", return_value=".wse-sns-page{color:#123}"),
            mock.patch.object(service, "_account_display_name", return_value="Me"),
        ):
            output = manager._run_job(job, account_dir)
        document = (output / "wxid_friend.html").read_text(encoding="utf-8")
        assert '<link rel="stylesheet" href="assets/sns.css"' in document
        assert 'data-wce-protected-root="1"' not in document
        assert (output / "assets" / "sns.css").read_text(encoding="utf-8") == ".wse-sns-page{color:#123}"
