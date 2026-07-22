import asyncio
import json
import sqlite3
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers import account_archive_export, import_decrypted


def _create_sqlite(path: Path, statements: list[str]) -> None:
    connection = sqlite3.connect(path)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def _create_account(account_dir: Path) -> None:
    account_dir.mkdir(parents=True)
    _create_sqlite(
        account_dir / "contact.db",
        [
            "CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, alias TEXT, big_head_url TEXT, small_head_url TEXT)",
            "INSERT INTO contact VALUES ('wxid_cross_platform', '', 'Cross Platform', '', '', '')",
        ],
    )
    _create_sqlite(
        account_dir / "session.db",
        [
            "CREATE TABLE SessionTable (username TEXT, is_hidden INTEGER, summary TEXT, draft TEXT, last_msg_type INTEGER, last_msg_sub_type INTEGER, sort_timestamp INTEGER, last_timestamp INTEGER)",
        ],
    )
    (account_dir / "account.json").write_text(
        json.dumps(
            {
                "username": "wxid_cross_platform",
                "nick": "Cross Platform",
                "avatar_url": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (account_dir / "_media_keys.json").write_text('{"image_key":"1234"}', encoding="utf-8")
    (account_dir / "resource" / "images").mkdir(parents=True)
    (account_dir / "resource" / "images" / "photo.bin").write_bytes(b"image-resource")
    (account_dir / "sns_resource").mkdir()
    (account_dir / "sns_resource" / "timeline.bin").write_bytes(b"sns-resource")
    (account_dir / "cache").mkdir()
    (account_dir / "cache" / "index.json").write_text('{"cached":true}', encoding="utf-8")


def _export_account(account_dir: Path, output_dir: Path) -> Path:
    job = account_archive_export.AccountArchiveExportJob(export_id="cross-platform-export")
    with account_archive_export._JOBS_LOCK:
        account_archive_export._JOBS[job.export_id] = job
    try:
        with patch.object(account_archive_export, "_resolve_account_dir", return_value=account_dir):
            account_archive_export._run_account_archive_export(
                job.export_id,
                {
                    "account": account_dir.name,
                    "output_dir": str(output_dir),
                    "include_databases": True,
                    "include_resources": True,
                    "file_name": "windows-account-export.zip",
                },
            )
    finally:
        with account_archive_export._JOBS_LOCK:
            account_archive_export._JOBS.pop(job.export_id, None)
    if job.status != "done":
        raise AssertionError(job.error)
    return Path(job.zip_path)


async def _consume_import(path: Path) -> list[dict]:
    response = await import_decrypted.import_decrypted_directory(
        import_path=str(path),
        job_id="cross-platform-import",
    )
    payload = ""
    async for chunk in response.body_iterator:
        payload += chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
    events: list[dict] = []
    for block in payload.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


class TestAccountArchiveCrossPlatform(unittest.TestCase):
    def test_exported_account_zip_round_trips_into_new_data_directory(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "windows-output" / "wxid_cross_platform"
            _create_account(account_dir)
            archive_path = _export_account(account_dir, root / "exports")

            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                self.assertTrue(all("\\" not in name for name in names))
                self.assertIn("_integrity/manifest.wce", names)
                self.assertIn("wxid_cross_platform/contact.db", names)
                self.assertIn("wxid_cross_platform/resource/images/photo.bin", names)

            output_dir = root / "mac-data" / "databases"
            existing_dir = output_dir / "wxid_cross_platform"
            existing_dir.mkdir(parents=True)
            (existing_dir / "old-data.txt").write_text("old", encoding="utf-8")

            with (
                patch.object(import_decrypted, "get_output_databases_dir", return_value=output_dir),
                patch.object(import_decrypted, "get_data_dir", return_value=root / "mac-data"),
            ):
                preview = import_decrypted._validate_import_archive(archive_path)
                self.assertEqual(preview["username"], "wxid_cross_platform")
                self.assertTrue(preview["integrity_present"])
                events = asyncio.run(_consume_import(archive_path))

            self.assertEqual(events[-1]["type"], "complete", msg=events)
            imported_dir = output_dir / "wxid_cross_platform"
            self.assertTrue(import_decrypted._is_valid_sqlite(imported_dir / "contact.db"))
            self.assertEqual((imported_dir / "resource" / "images" / "photo.bin").read_bytes(), b"image-resource")
            self.assertEqual((imported_dir / "sns_resource" / "timeline.bin").read_bytes(), b"sns-resource")
            self.assertEqual((imported_dir / "cache" / "index.json").read_text(encoding="utf-8"), '{"cached":true}')
            self.assertEqual((imported_dir / "_media_keys.json").read_text(encoding="utf-8"), '{"image_key":"1234"}')
            self.assertFalse((imported_dir / "old-data.txt").exists())

            backup_dir = Path(events[-1]["backup_dir"])
            self.assertEqual((backup_dir / "old-data.txt").read_text(encoding="utf-8"), "old")
            self.assertFalse(list(output_dir.glob(".wxid_cross_platform.import-*")))
            self.assertFalse(list((root / "mac-data" / "import-tmp").glob("account-archive-*")))

    def test_tampered_archive_is_rejected_without_replacing_existing_account(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "windows-output" / "wxid_cross_platform"
            _create_account(account_dir)
            archive_path = _export_account(account_dir, root / "exports")
            tampered_path = root / "tampered.zip"

            with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(tampered_path, "w") as target:
                for item in source.infolist():
                    data = source.read(item)
                    if item.filename.endswith("/account.json"):
                        data += b" "
                    target.writestr(item, data)

            output_dir = root / "mac-data" / "databases"
            existing_dir = output_dir / "wxid_cross_platform"
            existing_dir.mkdir(parents=True)
            (existing_dir / "old-data.txt").write_text("old", encoding="utf-8")

            with (
                patch.object(import_decrypted, "get_output_databases_dir", return_value=output_dir),
                patch.object(import_decrypted, "get_data_dir", return_value=root / "mac-data"),
            ):
                events = asyncio.run(_consume_import(tampered_path))

            self.assertEqual(events[-1]["type"], "error", msg=events)
            self.assertIn("归档文件校验失败", events[-1]["message"])
            self.assertEqual((existing_dir / "old-data.txt").read_text(encoding="utf-8"), "old")
            self.assertFalse(list(output_dir.glob(".wxid_cross_platform.import-*")))

    def test_zip_path_traversal_is_rejected(self):
        with TemporaryDirectory() as td:
            archive_path = Path(td) / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")
            with self.assertRaisesRegex(Exception, "unsafe path"):
                import_decrypted._validate_import_archive(archive_path)


if __name__ == "__main__":
    unittest.main()
