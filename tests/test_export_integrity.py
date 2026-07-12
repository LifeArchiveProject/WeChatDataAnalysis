import hashlib
import base64
import json
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.export_integrity import (
    IntegrityZipWriter,
    export_css,
    seal_bytes_artifact,
    seal_protected_html_bytes,
    write_file_integrity_sidecars,
    write_zip_integrity_sidecars,
)
from wechat_decrypt_tool.routers import account_archive_export, chat_contacts
from wechat_decrypt_tool import sns_export_service


class TestExportIntegrity(unittest.TestCase):
    def test_native_module_owns_every_export_stylesheet(self):
        expected = {
            "chat": ".wechat-transfer-card",
            "sns": ".wse-sns-post-list",
            "records-project": ".records-grid",
            "records-generic": ".message",
            "contacts": ".contact-grid",
        }
        for kind, selector in expected.items():
            with self.subTest(kind=kind):
                self.assertIn(selector, export_css(kind))

        exposed_sources = [
            ROOT / "frontend" / "pages" / "contacts.vue",
            ROOT / "src" / "wechat_decrypt_tool" / "routers" / "chat_contacts.py",
            ROOT / "src" / "wechat_decrypt_tool" / "routers" / "record_export.py",
            ROOT / "src" / "wechat_decrypt_tool" / "sns_export_service.py",
        ]
        for path in exposed_sources:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(":root{--page:#ededed", text, msg=str(path))
            self.assertNotIn("_PROJECT_RECORD_EXPORT_CSS", text, msg=str(path))
            self.assertNotIn("_SNS_EXPORT_CSS_PATCH", text, msg=str(path))

    def test_single_file_sidecars_cover_export_bytes(self):
        with TemporaryDirectory() as td:
            target = Path(td) / "contacts.json"
            target.write_bytes(b'{"ok":true}\n')
            manifest_path, signature_path = write_file_integrity_sidecars(target, "single-file-test")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = {item["path"]: item for item in manifest["f"]}
            self.assertEqual(files[target.name]["sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertTrue(signature_path.read_text(encoding="utf-8").strip())

    def test_zip_sidecars_cover_written_entries(self):
        with TemporaryDirectory() as td:
            target = Path(td) / "export.zip"
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as raw_archive:
                archive = IntegrityZipWriter(raw_archive)
                archive.writestr("index.json", '{"ok":true}')
                write_zip_integrity_sidecars(archive, "zip-test")

            with zipfile.ZipFile(target) as archive:
                names = set(archive.namelist())
                self.assertIn("_integrity/manifest.wce", names)
                self.assertIn("_integrity/signature.wce", names)
                manifest = json.loads(archive.read("_integrity/manifest.wce"))
                self.assertIn("index.json", {item["path"] for item in manifest["f"]})

    def test_account_archive_contains_native_integrity_sidecars(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            (account_dir / "message.db").write_bytes(b"sqlite-test")
            output_dir = root / "exports"
            job = account_archive_export.AccountArchiveExportJob(export_id="archive-test")
            with account_archive_export._JOBS_LOCK:
                account_archive_export._JOBS[job.export_id] = job
            original_resolver = account_archive_export._resolve_account_dir
            account_archive_export._resolve_account_dir = lambda _account: account_dir
            try:
                account_archive_export._run_account_archive_export(
                    job.export_id,
                    {
                        "account": account_dir.name,
                        "output_dir": str(output_dir),
                        "include_databases": True,
                        "include_resources": False,
                        "file_name": "account.zip",
                    },
                )
            finally:
                account_archive_export._resolve_account_dir = original_resolver
                with account_archive_export._JOBS_LOCK:
                    account_archive_export._JOBS.pop(job.export_id, None)

            self.assertEqual(job.status, "done", msg=job.error)
            with zipfile.ZipFile(job.zip_path) as archive:
                self.assertIn("_integrity/manifest.wce", archive.namelist())
                self.assertIn("_integrity/signature.wce", archive.namelist())

    def test_sns_html_contains_active_integrity_runtime(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-html-test",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "html",
                    "useCache": True,
                    "outputDir": str(root),
                    "fileName": "sns_html.zip",
                },
            )
            post = {
                "id": "sns-1",
                "createTime": 1735689600,
                "contentDesc": "朋友圈内容",
                "media": [],
                "likes": [],
                "comments": [],
            }
            with (
                patch.object(
                    sns_export_service,
                    "_load_sns_users",
                    return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 1}],
                ),
                patch.object(
                    sns_export_service,
                    "list_sns_timeline",
                    return_value={"timeline": [post], "hasMore": False},
                ),
            ):
                output = manager._run_job(job, account_dir)

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                page_name = next(name for name in names if name.startswith("sns_") and name.endswith(".html"))
                page = archive.read(page_name).decode("utf-8")
                self.assertIn('data-wce-protected-root="1"', page)
                self.assertIn('data-wce-integrity-bundle="1"', page)
                self.assertIn('id="wceBrandAttribution"', page)
                self.assertTrue(any(name.startswith("assets/_wce/i-") for name in names))
                self.assertTrue(any(name.startswith("assets/_wce/r-") for name in names))

    def test_browser_export_seal_uses_native_manifest(self):
        sealed = chat_contacts.seal_chat_contacts_browser_export(
            chat_contacts.ContactBrowserExportSealRequest(
                file_name="contacts.json",
                content_base64="e30=",
            )
        )
        self.assertEqual(sealed["manifestFileName"], "contacts.json.wce")
        self.assertTrue(sealed["signature"].strip())
        self.assertIn("contacts.json", sealed["manifest"])

        direct = seal_bytes_artifact("records.txt", b"hello", "browser-test")
        self.assertIn("records.txt", direct["manifest"])

        html_document = b"<!doctype html><html><head><style>.page{color:red}</style></head><body><div class=\"page\">ok</div></body></html>"
        html_sealed = seal_protected_html_bytes("contacts.html", html_document, "browser-html-test")
        protected = base64.b64decode(html_sealed["protectedContentBase64"]).decode("utf-8")
        self.assertIn('data-wce-protected-root="1"', protected)
        self.assertIn('data-wce-integrity-bundle="1"', protected)
        self.assertIn('data-wce-runtime="1"', protected)
        self.assertIn('id="wceBrandAttribution"', protected)
        self.assertTrue(html_sealed["integrityFileName"].endswith(".wce.js"))


if __name__ == "__main__":
    unittest.main()
