import base64
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TestRequestLogRedaction(unittest.TestCase):
    def test_contacts_export_seal_request_logs_only_redacted_metadata(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from wechat_decrypt_tool.routers import chat_contacts

        raw_content = b'CONTACT_EXPORT_PRIVATE_DATA' * 100
        encoded_content = base64.b64encode(raw_content).decode('ascii')
        app = FastAPI()
        app.include_router(chat_contacts.router)

        with self.assertLogs('wechat_decrypt_tool.path_fix', level='INFO') as captured:
            response = TestClient(app).post(
                '/api/chat/contacts/export/seal',
                json={'file_name': 'contacts.json', 'content_base64': encoded_content},
            )

        self.assertEqual(response.status_code, 200)
        rendered = '\n'.join(captured.output)
        self.assertIn('contacts.json', rendered)
        self.assertIn(str(len(encoded_content)), rendered)
        self.assertNotIn(encoded_content, rendered)
        self.assertNotIn('CONTACT_EXPORT_PRIVATE_DATA', rendered)
        self.assertLess(max(map(len, captured.output)), 1000)

    def test_sensitive_fields_are_redacted_recursively(self):
        from wechat_decrypt_tool.request_logging import redact_sensitive_log_data

        content = "CONTACT_EXPORT_BASE64_SENTINEL" * 100
        payload = {
            "file_name": "contacts.json",
            "content_base64": content,
            "key": "DATABASE_KEY_SENTINEL_64_HEX_CHARS",
            "aes_key": "IMAGE_AES_KEY_SENTINEL",
            "image_xor_key": "IMAGE_XOR_KEY_SENTINEL",
            "auth": "AUTH_SENTINEL",
            "cookies": "COOKIE_SENTINEL",
            "nested": [{"token": "secret-token", "display": "kept"}],
        }

        redacted = redact_sensitive_log_data(payload)
        rendered = repr(redacted)

        self.assertNotIn(content, rendered)
        self.assertNotIn("DATABASE_KEY_SENTINEL_64_HEX_CHARS", rendered)
        self.assertNotIn("IMAGE_AES_KEY_SENTINEL", rendered)
        self.assertNotIn("IMAGE_XOR_KEY_SENTINEL", rendered)
        self.assertNotIn("AUTH_SENTINEL", rendered)
        self.assertNotIn("COOKIE_SENTINEL", rendered)
        self.assertNotIn("secret-token", rendered)
        self.assertIn(str(len(content)), rendered)
        self.assertIn("contacts.json", rendered)
        self.assertIn("kept", rendered)

    def test_path_validation_log_does_not_emit_contact_export_content(self):
        from wechat_decrypt_tool import path_fix

        content = "CONTACT_EXPORT_LOG_SENTINEL" * 100
        payload = {"file_name": "contacts.json", "content_base64": content}

        with patch.object(path_fix.logger, "info") as info:
            path_fix.PathFixRequest._validate_paths_in_json(None, payload)

        rendered = repr(info.call_args_list)
        self.assertNotIn(content, rendered)
        self.assertIn(str(len(content)), rendered)
        self.assertIn("contacts.json", rendered)

    def test_error_detail_stringification_redacts_sensitive_fields(self):
        from wechat_decrypt_tool.request_logging import _stringify_detail

        rendered = _stringify_detail({
            "message": "export failed",
            "context": {"content_base64": "PRIVATE_EXPORT_CONTENT", "password": "PRIVATE_PASSWORD"},
            "non_json_value": {1, 2},
        })

        self.assertIn("export failed", rendered)
        self.assertNotIn("PRIVATE_EXPORT_CONTENT", rendered)
        self.assertNotIn("PRIVATE_PASSWORD", rendered)

    def test_uvicorn_access_filter_redacts_query_secrets(self):
        from wechat_decrypt_tool.request_logging import SensitiveQueryLogFilter

        record = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            (
                "127.0.0.1:1234",
                "GET",
                "/api/decrypt_stream?key=DATABASE_SECRET&db_storage_path=C%3A%5Cdb&image_aes_key=AES_SECRET",
                "1.1",
                200,
            ),
            None,
        )

        self.assertTrue(SensitiveQueryLogFilter().filter(record))
        rendered = record.getMessage()
        self.assertNotIn("DATABASE_SECRET", rendered)
        self.assertNotIn("AES_SECRET", rendered)
        self.assertIn("db_storage_path=C%3A%5Cdb", rendered)


if __name__ == "__main__":
    unittest.main()
