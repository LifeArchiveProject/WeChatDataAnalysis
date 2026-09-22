"""回归：``tools/seed_demo_database.py`` 生成的演示库必须能被项目解密器读取。

这个测试守护的是「演示数据与真实解密链路一致」这一契约：如果
``wechat_decrypt`` 的页面格式、HMAC 覆盖范围或预留字节数发生变化，而种子脚本
没有同步，测试会立刻失败——避免演示环境悄悄偏离真实格式后又被人当成基准。
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from seed_demo_database import (  # noqa: E402
    DEMO_ACCOUNT,
    DEMO_GROUP,
    DEMO_KEY,
    encrypt_wcdb,
    seed,
)

from wechat_decrypt_tool.wechat_decrypt import (  # noqa: E402
    PAGE_SIZE,
    RESERVE_SIZE,
    SQLITE_HEADER,
    _compute_page_hmac,
    _derive_mac_key,
    _derive_sqlcipher_enc_key,
)


def _decrypt_to_plain(encrypted: bytes, key_hex: str) -> bytes:
    """按 ``wechat_decrypt._decrypt_page`` 的规则还原整库明文。"""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if len(encrypted) % PAGE_SIZE != 0:
        raise AssertionError("加密库长度不是 4096 的整数倍")

    salt = encrypted[:16]
    enc_key = _derive_sqlcipher_enc_key(bytes.fromhex(key_hex), salt)
    plain = bytearray()
    for page_num in range(1, len(encrypted) // PAGE_SIZE + 1):
        start = (page_num - 1) * PAGE_SIZE
        page = encrypted[start : start + PAGE_SIZE]
        iv = page[PAGE_SIZE - RESERVE_SIZE : PAGE_SIZE - RESERVE_SIZE + 16]
        offset = 16 if page_num == 1 else 0
        body = page[offset : PAGE_SIZE - RESERVE_SIZE]
        cipher = Cipher(
            algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(body) + decryptor.finalize()
        if page_num == 1:
            plain += SQLITE_HEADER + decrypted + b"\x00" * RESERVE_SIZE
        else:
            plain += decrypted + b"\x00" * RESERVE_SIZE
    return bytes(plain)


class TestSeedDemoDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.output = Path(self._tmp.name)
        self.paths = seed(self.output)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_generated_page_hmac_matches_decryptor(self):
        """逐页 HMAC 必须与解密器的校验算法一致，否则真实解密会拒绝该库。"""
        raw = self.paths["message_db"].read_bytes()
        self.assertEqual(len(raw) % PAGE_SIZE, 0)

        salt = raw[:16]
        enc_key = _derive_sqlcipher_enc_key(bytes.fromhex(DEMO_KEY), salt)
        mac_key = _derive_mac_key(enc_key, salt)

        for page_num in range(1, len(raw) // PAGE_SIZE + 1):
            start = (page_num - 1) * PAGE_SIZE
            page = raw[start : start + PAGE_SIZE]
            expected = _compute_page_hmac(mac_key, page, page_num)
            stored = page[PAGE_SIZE - 64 :]
            self.assertEqual(
                stored, expected, f"第 {page_num} 页 HMAC 与解密器算法不一致"
            )

    def test_generated_databases_decrypt_to_valid_sqlite(self):
        for key_name in ("message_db", "contact_db"):
            path = self.paths[key_name]
            plain = _decrypt_to_plain(path.read_bytes(), DEMO_KEY)
            self.assertTrue(plain.startswith(SQLITE_HEADER))

            decrypted_path = self.output / f"{key_name}.decrypted.db"
            decrypted_path.write_bytes(plain)
            conn = sqlite3.connect(decrypted_path)
            try:
                status = conn.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(status, "ok", f"{key_name} 解密后完整性检查失败")

    def test_demo_account_excludes_self_from_name2id(self):
        """真实微信的 Name2Id 不含账号本人，演示库必须保持同样结构。"""
        plain = _decrypt_to_plain(self.paths["message_db"].read_bytes(), DEMO_KEY)
        decrypted_path = self.output / "name2id.decrypted.db"
        decrypted_path.write_bytes(plain)
        conn = sqlite3.connect(decrypted_path)
        try:
            names = [row[0] for row in conn.execute("SELECT user_name FROM Name2Id")]
        finally:
            conn.close()
        self.assertNotIn(DEMO_ACCOUNT, names)
        self.assertIn(DEMO_GROUP, names)

    def test_demo_content_is_marked_fictional(self):
        """所有昵称都带「示例」标记，避免演示数据被误认为真实数据。"""
        plain = _decrypt_to_plain(self.paths["contact_db"].read_bytes(), DEMO_KEY)
        decrypted_path = self.output / "contact_content.decrypted.db"
        decrypted_path.write_bytes(plain)
        conn = sqlite3.connect(decrypted_path)
        try:
            rows = conn.execute("SELECT nick_name FROM Contact").fetchall()
        finally:
            conn.close()
        self.assertTrue(rows)
        for (nick_name,) in rows:
            self.assertIn("示例", str(nick_name))

    def test_encrypt_wcdb_rejects_unaligned_input(self):
        with self.assertRaises(ValueError):
            encrypt_wcdb(b"not-a-full-page", DEMO_KEY)


if __name__ == "__main__":
    unittest.main()
