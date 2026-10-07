"""账号归档下载接口只能按服务端任务的 export_id 取文件，不能由调用方指定路径。"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wechat_decrypt_tool.routers import account_archive_export


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(account_archive_export.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def register_job():
    registered: list[str] = []

    def _register(**fields):
        job = account_archive_export.AccountArchiveExportJob(**fields)
        with account_archive_export._JOBS_LOCK:
            account_archive_export._JOBS[job.export_id] = job
        registered.append(job.export_id)
        return job

    yield _register
    with account_archive_export._JOBS_LOCK:
        for export_id in registered:
            account_archive_export._JOBS.pop(export_id, None)


def test_unknown_export_id_returns_404(client):
    response = client.get("/api/account/archive_export/missing-export/download")

    assert response.status_code == 404
    assert response.json() == {"detail": "Export not found."}


@pytest.mark.parametrize("status", ["queued", "running", "error", "cancelled"])
def test_unfinished_job_is_not_downloadable(client, register_job, tmp_path, status):
    # 任务一开始就会写入 zip_path；同名旧文件可能还在磁盘上，不能在任务完成前被取走。
    stale = tmp_path / "wechat_archive_account.zip"
    stale.write_bytes(b"stale-archive")
    register_job(export_id=f"archive-{status}", status=status, zip_path=str(stale), file_name=stale.name)

    response = client.get(f"/api/account/archive_export/archive-{status}/download")

    assert response.status_code == 409
    assert response.json() == {"detail": "Export not ready."}


@pytest.mark.parametrize(
    ("file_name", "media_type"),
    [
        ("wechat_archive_account.zip", "application/zip"),
        ("wechat_archive_account.zip.wec", "application/octet-stream"),
    ],
)
def test_finished_job_serves_its_own_file(client, register_job, tmp_path, file_name, media_type):
    archive = tmp_path / file_name
    archive.write_bytes(b"archive-bytes")
    register_job(export_id="archive-done", status="done", zip_path=str(archive), file_name=file_name)

    response = client.get("/api/account/archive_export/archive-done/download")

    assert response.status_code == 200
    assert response.content == b"archive-bytes"
    assert response.headers["content-type"] == media_type
    assert f'filename="{file_name}"' in response.headers["content-disposition"]


def test_finished_job_with_removed_file_returns_404(client, register_job, tmp_path):
    removed = tmp_path / "wechat_archive_account.zip"
    register_job(export_id="archive-removed", status="done", zip_path=str(removed), file_name=removed.name)

    response = client.get("/api/account/archive_export/archive-removed/download")

    assert response.status_code == 404
    assert response.json() == {"detail": "Export file not found."}


def test_path_query_cannot_read_other_files(client, register_job, tmp_path):
    other = tmp_path / "other" / "private.zip"
    other.parent.mkdir()
    other.write_bytes(b"not-an-export")
    archive = tmp_path / "wechat_archive_account.zip"
    archive.write_bytes(b"archive-bytes")
    register_job(export_id="archive-done", status="done", zip_path=str(archive), file_name=archive.name)

    legacy = client.get("/api/account/archive_export/download", params={"path": str(other)})
    assert legacy.status_code == 404
    assert b"not-an-export" not in legacy.content

    overridden = client.get("/api/account/archive_export/archive-done/download", params={"path": str(other)})
    assert overridden.status_code == 200
    assert overridden.content == b"archive-bytes"


def test_frontend_downloads_archive_by_export_id():
    source = (ROOT / "frontend" / "components" / "GlobalExportDialog.vue").read_text(encoding="utf-8")

    assert "/account/archive_export/${encodeURIComponent(currentExportId.value)}/download" in source
    assert "archive_export/download?" not in source
