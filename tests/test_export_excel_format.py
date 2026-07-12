import io
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_export_service import export_prepared_chat_archive
from wechat_decrypt_tool.routers import chat_contacts, record_export
from wechat_decrypt_tool.routers.chat_export import ChatExportCreateRequest
from wechat_decrypt_tool.routers.sns_export import SnsExportCreateRequest
from wechat_decrypt_tool import sns_export_service
from wechat_decrypt_tool.xlsx_export import build_xlsx_workbook


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/api/export",
            "headers": [],
        }
    )


def _assert_workbook(test_case: unittest.TestCase, data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        test_case.assertIn("[Content_Types].xml", names)
        test_case.assertIn("xl/workbook.xml", names)
        test_case.assertIn("xl/worksheets/sheet1.xml", names)
        ET.fromstring(archive.read("xl/workbook.xml"))
        ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))


class TestExcelExportFormat(unittest.TestCase):
    def test_xlsx_builder_creates_open_xml_workbook(self):
        workbook = build_xlsx_workbook(
            [("导出", ["名称", "内容"], [["Alice", "你好"], ["Formula", "=SUM(A1:A2)"]])]
        )
        _assert_workbook(self, workbook)

    def test_content_export_request_models_accept_excel(self):
        self.assertEqual(ChatExportCreateRequest(format="excel").format, "excel")
        self.assertEqual(SnsExportCreateRequest(format="excel").format, "excel")
        self.assertEqual(
            record_export.RecordExportRequest(dataset="payments", output_dir="C:\\exports", format="excel").format,
            "excel",
        )
        self.assertEqual(
            chat_contacts.ContactExportRequest(output_dir="C:\\exports", format="excel").format,
            "excel",
        )

    def test_contacts_and_records_write_xlsx(self):
        contact = {
            "username": "wxid_alice",
            "displayName": "Alice",
            "remark": "",
            "nickname": "Alice",
            "alias": "alice",
            "type": "friend",
            "officialAccountKind": "",
            "officialAccountType": "",
            "region": "中国大陆·四川·成都",
            "country": "CN",
            "province": "Sichuan",
            "city": "Chengdu",
            "source": "通过搜索手机号添加",
            "sourceScene": 15,
            "avatarLink": "http://testserver/avatar",
        }
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            with (
                patch.object(chat_contacts, "_resolve_account_dir", return_value=account_dir),
                patch.object(chat_contacts, "_resolve_contacts_source_for_account", return_value="decrypted"),
                patch.object(chat_contacts, "_collect_contacts_for_account", return_value=[contact]),
            ):
                result = chat_contacts.export_chat_contacts(
                    _request(),
                    chat_contacts.ContactExportRequest(
                        account="wxid_test",
                        output_dir=str(root),
                        format="excel",
                    ),
                )
            contact_path = Path(result["outputPath"])
            self.assertEqual(contact_path.suffix, ".xlsx")
            _assert_workbook(self, contact_path.read_bytes())
            self.assertTrue(Path(result["integrityManifestPath"]).is_file())
            self.assertTrue(Path(result["integritySignaturePath"]).is_file())

            record = {
                "kind": "transfer",
                "name": "Alice",
                "timeText": "2026-01-01 12:00",
                "transferState": "received",
                "amount": "¥10.00",
            }
            with patch.object(record_export, "_load_records", return_value=([record], {"account": "wxid_test"})):
                result = record_export.export_records(
                    _request(),
                    record_export.RecordExportRequest(
                        account="wxid_test",
                        dataset="payments",
                        output_dir=str(root),
                        format="excel",
                    ),
                )
            record_path = Path(result["outputPath"])
            self.assertEqual(record_path.suffix, ".xlsx")
            _assert_workbook(self, record_path.read_bytes())
            self.assertTrue(Path(result["integrityManifestPath"]).is_file())
            self.assertTrue(Path(result["integritySignaturePath"]).is_file())

    def test_chat_excel_archive_contains_workbooks(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            job = export_prepared_chat_archive(
                account_dir=account_dir,
                output_dir=root,
                file_name="chat_export.zip",
                title="聊天记录",
                export_format="excel",
                conversations=[
                    {
                        "username": "wxid_alice",
                        "displayName": "Alice",
                        "isGroup": False,
                        "messages": [
                            {
                                "createTime": 1735689600,
                                "senderUsername": "wxid_alice",
                                "renderType": "text",
                                "content": "你好",
                            }
                        ],
                    }
                ],
                include_media=False,
                media_kinds=[],
                message_types=[],
            )
            self.assertEqual(job.status, "done", msg=job.error)
            self.assertIsNotNone(job.zip_path)
            with zipfile.ZipFile(job.zip_path) as archive:
                self.assertIn("_integrity/manifest.wce", archive.namelist())
                self.assertIn("_integrity/signature.wce", archive.namelist())
                self.assertIn("index.xlsx", archive.namelist())
                message_workbook = next(name for name in archive.namelist() if name.endswith("/messages.xlsx"))
                self.assertFalse(any(name.endswith("/messages.json") for name in archive.namelist()))
                _assert_workbook(self, archive.read("index.xlsx"))
                _assert_workbook(self, archive.read(message_workbook))

    def test_sns_excel_archive_contains_workbooks(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="testexcel",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "excel",
                    "useCache": True,
                    "outputDir": str(root),
                    "fileName": "sns_export.zip",
                },
            )
            post = {
                "id": "sns-1",
                "createTime": 1735689600,
                "contentDesc": "朋友圈内容",
                "location": "成都",
                "media": [],
                "likes": ["Bob"],
                "comments": [{"nickname": "Carol", "content": "你好"}],
            }
            with (
                patch.object(sns_export_service, "_load_sns_users", return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 1}]),
                patch.object(sns_export_service, "list_sns_timeline", return_value={"timeline": [post], "hasMore": False}),
            ):
                output = manager._run_job(job, account_dir)
            with zipfile.ZipFile(output) as archive:
                self.assertIn("_integrity/manifest.wce", archive.namelist())
                self.assertIn("_integrity/signature.wce", archive.namelist())
                self.assertIn("index.xlsx", archive.namelist())
                self.assertIn("sns_wxid_alice.xlsx", archive.namelist())
                _assert_workbook(self, archive.read("index.xlsx"))
                _assert_workbook(self, archive.read("sns_wxid_alice.xlsx"))
