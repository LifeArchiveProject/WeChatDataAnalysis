import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.chat_helpers import _load_group_nickname_map_from_contact_db


def _enc_varint(n: int) -> bytes:
    v = int(n)
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _enc_tag(field_no: int, wire_type: int) -> bytes:
    return _enc_varint((int(field_no) << 3) | int(wire_type))


def _enc_len(field_no: int, data: bytes) -> bytes:
    b = bytes(data or b"")
    return _enc_tag(field_no, 2) + _enc_varint(len(b)) + b


def _member_entry(*, inner: bytes) -> bytes:
    # contact.db ext_buffer uses repeated length-delimited submessages; the top-level field number is not important
    # for our best-effort parser, so we use field 1.
    return _enc_len(1, inner)


class TestGroupNicknameExtBufferParsing(unittest.TestCase):
    def test_parse_pattern_a_field1_username_field2_display(self):
        chatroom = "demo@chatroom"
        username = "wxid_demo_123456"
        display = "群名片A"

        inner = _enc_len(1, username.encode("utf-8")) + _enc_len(2, display.encode("utf-8"))
        ext_buffer = _member_entry(inner=inner)

        with TemporaryDirectory() as td:
            contact_db_path = Path(td) / "contact.db"
            conn = sqlite3.connect(str(contact_db_path))
            try:
                conn.execute(
                    "CREATE TABLE chat_room(id INTEGER PRIMARY KEY, username TEXT, owner TEXT, ext_buffer BLOB)"
                )
                conn.execute(
                    "INSERT INTO chat_room(id, username, owner, ext_buffer) VALUES (?, ?, ?, ?)",
                    (1, chatroom, "", ext_buffer),
                )
                conn.commit()
            finally:
                conn.close()

            out = _load_group_nickname_map_from_contact_db(contact_db_path, chatroom, [username])
            self.assertEqual(out.get(username), display)

    def test_parse_pattern_b_field4_username_field1_display(self):
        chatroom = "demo2@chatroom"
        username = "wxid_demo_abcdef"
        display = "hjlbingo"

        inner = _enc_len(4, username.encode("utf-8")) + _enc_len(1, display.encode("utf-8"))
        ext_buffer = _member_entry(inner=inner)

        with TemporaryDirectory() as td:
            contact_db_path = Path(td) / "contact.db"
            conn = sqlite3.connect(str(contact_db_path))
            try:
                conn.execute(
                    "CREATE TABLE chat_room(id INTEGER PRIMARY KEY, username TEXT, owner TEXT, ext_buffer BLOB)"
                )
                conn.execute(
                    "INSERT INTO chat_room(id, username, owner, ext_buffer) VALUES (?, ?, ?, ?)",
                    (1, chatroom, "", ext_buffer),
                )
                conn.commit()
            finally:
                conn.close()

            out = _load_group_nickname_map_from_contact_db(contact_db_path, chatroom, [username])
            self.assertEqual(out.get(username), display)

    def test_non_chatroom_returns_empty(self):
        with TemporaryDirectory() as td:
            contact_db_path = Path(td) / "contact.db"
            conn = sqlite3.connect(str(contact_db_path))
            try:
                conn.execute(
                    "CREATE TABLE chat_room(id INTEGER PRIMARY KEY, username TEXT, owner TEXT, ext_buffer BLOB)"
                )
                conn.commit()
            finally:
                conn.close()

            out = _load_group_nickname_map_from_contact_db(contact_db_path, "wxid_not_chatroom", ["wxid_xxx"])
            self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()

