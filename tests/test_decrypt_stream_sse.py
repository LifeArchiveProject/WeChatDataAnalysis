import json
import os
import sys
import unittest
import importlib
import hashlib
import hmac
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _encrypt_page(raw_key: bytes, plain_page: bytes, page_num: int, salt: bytes, iv: bytes) -> bytes:
    from wechat_decrypt_tool.wechat_decrypt import PAGE_SIZE, RESERVE_SIZE, SALT_SIZE, _derive_mac_key

    if page_num == 1:
        encrypted_input = plain_page[SALT_SIZE : PAGE_SIZE - RESERVE_SIZE]
        prefix = salt
    else:
        encrypted_input = plain_page[: PAGE_SIZE - RESERVE_SIZE]
        prefix = b""

    cipher = Cipher(
        algorithms.AES(raw_key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(encrypted_input) + encryptor.finalize()

    page_without_hmac = prefix + encrypted + iv
    mac = hmac.new(_derive_mac_key(raw_key, salt), digestmod=hashlib.sha512)
    mac.update(page_without_hmac[SALT_SIZE if page_num == 1 else 0 :])
    mac.update(page_num.to_bytes(4, "little"))
    return page_without_hmac + mac.digest()


class TestDecryptStreamSSE(unittest.TestCase):
    def test_decrypt_stream_reports_progress(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from wechat_decrypt_tool.wechat_decrypt import SQLITE_HEADER

        with TemporaryDirectory() as td:
            root = Path(td)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            prev_build_cache = os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = "0"

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.routers.decrypt as decrypt_router

                importlib.reload(app_paths)
                importlib.reload(decrypt_router)

                db_storage = root / "xwechat_files" / "wxid_foo_bar" / "db_storage"
                db_storage.mkdir(parents=True, exist_ok=True)

                # Fake a decrypted sqlite db (>= 4096 bytes) so decryptor falls back to copy.
                (db_storage / "MSG0.db").write_bytes(SQLITE_HEADER + b"\x00" * (4096 - len(SQLITE_HEADER)))

                app = FastAPI()
                app.include_router(decrypt_router.router)
                client = TestClient(app)

                events: list[dict] = []
                with client.stream(
                    "GET",
                    "/api/decrypt_stream",
                    params={"key": "00" * 32, "db_storage_path": str(db_storage)},
                ) as resp:
                    self.assertEqual(resp.status_code, 200)
                    self.assertIn("text/event-stream", resp.headers.get("content-type", ""))

                    for line in resp.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="ignore")
                        line = str(line)

                        if line.startswith(":"):
                            continue
                        if not line.startswith("data: "):
                            continue
                        payload = json.loads(line[len("data: ") :])
                        events.append(payload)
                        if payload.get("type") in {"complete", "error"}:
                            break

                types = {e.get("type") for e in events}
                self.assertIn("start", types)
                self.assertIn("progress", types)
                self.assertEqual(events[-1].get("type"), "complete")

                out = root / "output" / "databases" / "wxid_foo" / "MSG0.db"
                self.assertTrue(out.exists())
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir
                if prev_build_cache is None:
                    os.environ.pop("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", None)
                else:
                    os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = prev_build_cache

    def test_decrypt_stream_reports_key_scope_error_for_wrong_key(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from wechat_decrypt_tool.wechat_decrypt import PAGE_SIZE, RESERVE_SIZE, SQLITE_HEADER

        good_key = bytes.fromhex("00112233445566778899aabbccddeefffedcba98765432100123456789abcdef")
        bad_key = "ffeeddccbbaa998877665544332211000123456789abcdeffedcba9876543210"
        salt = bytes.fromhex("11223344556677889900aabbccddeeff")
        iv1 = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
        plain_page = SQLITE_HEADER + (b"A" * (PAGE_SIZE - RESERVE_SIZE - len(SQLITE_HEADER))) + (b"\x00" * RESERVE_SIZE)
        encrypted_db = _encrypt_page(good_key, plain_page, 1, salt, iv1)

        with TemporaryDirectory() as td:
            root = Path(td)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            prev_build_cache = os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = "0"

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.routers.decrypt as decrypt_router

                importlib.reload(app_paths)
                importlib.reload(decrypt_router)

                db_storage = root / "xwechat_files" / "wxid_wrong_key_user" / "db_storage"
                db_storage.mkdir(parents=True, exist_ok=True)
                (db_storage / "MSG0.db").write_bytes(encrypted_db)

                app = FastAPI()
                app.include_router(decrypt_router.router)
                client = TestClient(app)

                events: list[dict] = []
                with client.stream(
                    "GET",
                    "/api/decrypt_stream",
                    params={"key": bad_key, "db_storage_path": str(db_storage)},
                ) as resp:
                    self.assertEqual(resp.status_code, 200)
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", errors="ignore")
                        line = str(line)
                        if line.startswith(":") or not line.startswith("data: "):
                            continue
                        payload = json.loads(line[len("data: ") :])
                        events.append(payload)
                        if payload.get("type") in {"complete", "error"}:
                            break

                self.assertEqual(events[-1].get("type"), "complete")
                self.assertEqual(events[-1].get("status"), "failed")
                self.assertIn("当前数据库密钥不正确", events[-1].get("message", ""))
                self.assertIn("另一台设备复制", events[-1].get("message", ""))
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir
                if prev_build_cache is None:
                    os.environ.pop("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", None)
                else:
                    os.environ["WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE"] = prev_build_cache


if __name__ == "__main__":
    unittest.main()

