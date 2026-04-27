import hashlib
import hmac
import tempfile
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import wechat_decrypt_tool.wechat_decrypt as wechat_decrypt
from wechat_decrypt_tool.wechat_decrypt import (
    HMAC_SIZE,
    PAGE_SIZE,
    RESERVE_SIZE,
    SALT_SIZE,
    SQLITE_HEADER,
    WeChatDatabaseDecryptor,
    _derive_mac_key,
    _derive_sqlcipher_enc_key,
)


def _build_plain_page(fill: int, *, first_page: bool) -> bytes:
    body = bytes([fill]) * (PAGE_SIZE - RESERVE_SIZE)
    if first_page:
        body = SQLITE_HEADER + body[len(SQLITE_HEADER):]
    return body + (b"\x00" * RESERVE_SIZE)


def _encrypt_page(key_material: bytes, plain_page: bytes, page_num: int, salt: bytes, iv: bytes, *, passphrase: bool = False) -> bytes:
    enc_key = _derive_sqlcipher_enc_key(key_material, salt) if passphrase else key_material
    if page_num == 1:
        encrypted_input = plain_page[SALT_SIZE: PAGE_SIZE - RESERVE_SIZE]
        prefix = salt
    else:
        encrypted_input = plain_page[: PAGE_SIZE - RESERVE_SIZE]
        prefix = b""

    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(encrypted_input) + encryptor.finalize()

    page_without_hmac = prefix + encrypted + iv
    mac = hmac.new(_derive_mac_key(enc_key, salt), digestmod=hashlib.sha512)
    mac.update(page_without_hmac[SALT_SIZE if page_num == 1 else 0:])
    mac.update(page_num.to_bytes(4, "little"))
    return page_without_hmac + mac.digest()


def _decrypt_sample(key_hex: str, encrypted_db: bytes, monkeypatch) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source.db"
        dst = Path(tmpdir) / "out.db"
        src.write_bytes(encrypted_db)
        monkeypatch.setattr(wechat_decrypt, "collect_sqlite_diagnostics", lambda *args, **kwargs: {"quick_check_ok": True})
        monkeypatch.setattr(wechat_decrypt, "sqlite_diagnostics_status", lambda diagnostics: "ok")
        decryptor = WeChatDatabaseDecryptor(key_hex)
        assert decryptor.decrypt_database(str(src), str(dst))
        return dst.read_bytes()


def test_decrypt_database_accepts_raw_enc_key_like_weflow(monkeypatch):
    raw_key = bytes.fromhex("00112233445566778899aabbccddeefffedcba98765432100123456789abcdef")
    salt = bytes.fromhex("50f4090ef6897e146f94109f13743e34")
    page1 = _build_plain_page(0x41, first_page=True)
    page2 = _build_plain_page(0x42, first_page=False)

    encrypted_db = _encrypt_page(raw_key, page1, 1, salt, bytes.fromhex("0102030405060708090a0b0c0d0e0f10"))
    encrypted_db += _encrypt_page(raw_key, page2, 2, salt, bytes.fromhex("1112131415161718191a1b1c1d1e1f20"))

    assert _decrypt_sample(raw_key.hex(), encrypted_db, monkeypatch) == page1 + page2


def test_decrypt_database_keeps_sqlcipher_passphrase_compatibility(monkeypatch):
    passphrase_key = bytes.fromhex("9f5dd0d3b6d0477ea5045c9e380ee272e53927993eb548dd98a022e842d5f7bd")
    salt = bytes.fromhex("40f4090ef6897e146f94109f13743e34")
    page1 = _build_plain_page(0x51, first_page=True)
    page2 = _build_plain_page(0x52, first_page=False)

    encrypted_db = _encrypt_page(passphrase_key, page1, 1, salt, bytes.fromhex("2122232425262728292a2b2c2d2e2f30"), passphrase=True)
    encrypted_db += _encrypt_page(passphrase_key, page2, 2, salt, bytes.fromhex("3132333435363738393a3b3c3d3e3f40"), passphrase=True)

    assert _decrypt_sample(passphrase_key.hex(), encrypted_db, monkeypatch) == page1 + page2
