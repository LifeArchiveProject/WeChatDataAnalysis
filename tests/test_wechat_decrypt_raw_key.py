import hashlib
import hmac
import os
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.wechat_decrypt import (
    PAGE_SIZE,
    RESERVE_SIZE,
    SALT_SIZE,
    SQLITE_HEADER,
    WeChatDatabaseDecryptor,
    _derive_mac_key,
    decrypt_wechat_databases,
)


def _encrypt_page(raw_key: bytes, plain_page: bytes, page_num: int, salt: bytes, iv: bytes) -> bytes:
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


def _build_plain_page(body_byte: int, *, first_page: bool) -> bytes:
    if first_page:
        payload = SQLITE_HEADER + bytes([body_byte]) * (PAGE_SIZE - RESERVE_SIZE - len(SQLITE_HEADER))
    else:
        payload = bytes([body_byte]) * (PAGE_SIZE - RESERVE_SIZE)
    return payload + (b"\x00" * RESERVE_SIZE)


class WeChatDecryptRawKeyTests(unittest.TestCase):
    def test_decrypt_database_uses_raw_enc_key(self):
        raw_key = bytes.fromhex("00112233445566778899aabbccddeefffedcba98765432100123456789abcdef")
        salt = bytes.fromhex("11223344556677889900aabbccddeeff")
        iv1 = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
        iv2 = bytes.fromhex("1112131415161718191a1b1c1d1e1f20")

        page1 = _build_plain_page(0x41, first_page=True)
        page2 = _build_plain_page(0x42, first_page=False)
        encrypted_db = _encrypt_page(raw_key, page1, 1, salt, iv1) + _encrypt_page(raw_key, page2, 2, salt, iv2)

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.db"
            dst = Path(tmpdir) / "out.db"
            src.write_bytes(encrypted_db)

            decryptor = WeChatDatabaseDecryptor(raw_key.hex())
            self.assertTrue(decryptor.decrypt_database(str(src), str(dst)))
            self.assertEqual(dst.read_bytes(), page1 + page2)

    def test_decrypt_database_keeps_existing_output_on_hmac_failure(self):
        good_key = bytes.fromhex("00112233445566778899aabbccddeefffedcba98765432100123456789abcdef")
        bad_key_hex = "ffeeddccbbaa998877665544332211000123456789abcdeffedcba9876543210"
        salt = bytes.fromhex("11223344556677889900aabbccddeeff")
        iv1 = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")

        page1 = _build_plain_page(0x41, first_page=True)
        encrypted_db = _encrypt_page(good_key, page1, 1, salt, iv1)

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.db"
            dst = Path(tmpdir) / "out.db"
            src.write_bytes(encrypted_db)
            dst.write_bytes(b"keep-existing-output")

            decryptor = WeChatDatabaseDecryptor(bad_key_hex)
            self.assertFalse(decryptor.decrypt_database(str(src), str(dst)))
            self.assertEqual(dst.read_bytes(), b"keep-existing-output")

    def test_decrypt_wechat_databases_reports_key_scope_message(self):
        good_key = bytes.fromhex("00112233445566778899aabbccddeefffedcba98765432100123456789abcdef")
        bad_key_hex = "ffeeddccbbaa998877665544332211000123456789abcdeffedcba9876543210"
        salt = bytes.fromhex("11223344556677889900aabbccddeeff")
        iv1 = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")

        page1 = _build_plain_page(0x41, first_page=True)
        encrypted_db = _encrypt_page(good_key, page1, 1, salt, iv1)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_storage = root / "xwechat_files" / "wxid_scope_user" / "db_storage"
            db_storage.mkdir(parents=True, exist_ok=True)
            (db_storage / "MSG0.db").write_bytes(encrypted_db)

            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)
                result = decrypt_wechat_databases(str(db_storage), bad_key_hex)
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir

            self.assertEqual(result["status"], "error")
            self.assertIn("当前数据库密钥不正确", result["message"])
            self.assertIn("账号/当前设备", result["message"])
            self.assertIn("另一台设备复制", result["message"])


if __name__ == "__main__":
    unittest.main()
