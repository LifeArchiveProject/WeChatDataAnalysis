import hashlib
import hmac
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_db_key_discovery import (
    MacOSDBKeyDiscoveryFailure,
    discover_macos_db_key,
)
from wechat_decrypt_tool.wechat_decrypt import PAGE_SIZE, RESERVE_SIZE


def encrypted_page_for_passphrase(passphrase: bytes, salt: bytes = bytes(range(16))) -> bytes:
    enc_key = hashlib.pbkdf2_hmac("sha512", passphrase, salt, 256000, dklen=32)
    mac_salt = bytes(value ^ 0x3A for value in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=32)
    page = bytearray(PAGE_SIZE)
    page[:16] = salt
    page[16 : PAGE_SIZE - RESERVE_SIZE + 16] = bytes([0x5A]) * (PAGE_SIZE - RESERVE_SIZE)
    digest = hmac.new(mac_key, digestmod=hashlib.sha512)
    digest.update(page[16 : PAGE_SIZE - RESERVE_SIZE + 16])
    digest.update((1).to_bytes(4, "little"))
    page[PAGE_SIZE - 64 :] = digest.digest()
    return bytes(page)


class TestMacOSDBKeyDiscovery(unittest.TestCase):
    def test_discovers_wcdb_key_tool_passphrase_and_validates_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "account" / "db_storage" / "message" / "message_0.db"
            db.parent.mkdir(parents=True)
            passphrase = bytes(range(32))
            db.write_bytes(encrypted_page_for_passphrase(passphrase))
            cache = root / ".wcdb-key-tool" / "wechat-passphrase.json"
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({"passphrase": passphrase.hex()}), encoding="utf-8")

            with patch("sys.platform", "darwin"):
                result = discover_macos_db_key(db, home=root)

            self.assertEqual(result["db_key"], passphrase.hex())
            self.assertEqual(result["key_mode"], "sqlcipher_passphrase")
            self.assertFalse(result["wechat_modified"])
            self.assertFalse(result["process_attached"])

    def test_rejects_unverified_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "db_storage" / "message_0.db"
            db.parent.mkdir(parents=True)
            db.write_bytes(encrypted_page_for_passphrase(bytes(range(32))))
            cache = root / ".wcdb-key-tool" / "wechat-passphrase.json"
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({"passphrase": "ff" * 32}), encoding="utf-8")

            with patch("sys.platform", "darwin"):
                with self.assertRaises(MacOSDBKeyDiscoveryFailure) as context:
                    discover_macos_db_key(db, home=root)

            self.assertEqual(context.exception.code, "safe_key_not_found")

    def test_cache_miss_guidance_describes_recoverable_in_place_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "db_storage" / "message_0.db"
            db.parent.mkdir(parents=True)
            db.write_bytes(encrypted_page_for_passphrase(bytes(range(32))))

            with patch("sys.platform", "darwin"):
                with self.assertRaises(MacOSDBKeyDiscoveryFailure) as context:
                    discover_macos_db_key(db, home=root)

        message = str(context.exception)
        self.assertEqual(context.exception.code, "safe_key_not_found")
        self.assertIn("所选备份目录验证腾讯原版备份", message)
        self.assertIn("默认路径微信", message)
        self.assertIn("同卷 APFS 写时复制恢复副本", message)
        self.assertIn("临时启用调试签名", message)
        self.assertIn("完成断点预检并分离后先退出账号", message)
        self.assertIn("随后只重新登录同一个账号", message)
        self.assertIn("当前数据库校验", message)
        self.assertIn("恢复腾讯原签名", message)
        self.assertIn("清理临时恢复副本", message)
        self.assertNotIn("WeChat Debug - WCDA", message)

    def test_reports_full_disk_access_requirement_on_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "session.db"
            db.write_bytes(encrypted_page_for_passphrase(bytes(range(32))))
            with (
                patch("sys.platform", "darwin"),
                patch.object(Path, "open", side_effect=PermissionError(1, "Operation not permitted")),
            ):
                with self.assertRaises(MacOSDBKeyDiscoveryFailure) as context:
                    discover_macos_db_key(db, home=Path(tmp))

        self.assertEqual(context.exception.code, "database_permission_denied")
        self.assertIn("完全磁盘访问权限", str(context.exception))


if __name__ == "__main__":
    unittest.main()
