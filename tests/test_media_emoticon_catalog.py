import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.media_helpers import (  # noqa: E402  pylint: disable=wrong-import-position
    _collect_emoticon_download_catalog,
    _lookup_emoticon_info,
)


class TestMediaEmoticonCatalog(unittest.TestCase):
    def test_catalog_merges_emoticon_db_extern_md5_and_message_xml(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "account"
            account_dir.mkdir(parents=True, exist_ok=True)
            primary_md5 = "a" * 32
            extern_md5 = "b" * 32
            message_md5 = "c" * 32
            no_url_md5 = "d" * 32
            message_extern_md5 = "e" * 32
            aes_key = "1" * 32

            conn = sqlite3.connect(str(account_dir / "emoticon.db"))
            conn.execute(
                "CREATE TABLE kNonStoreEmoticonTable ("
                "md5 TEXT, extern_md5 TEXT, aes_key TEXT, cdn_url TEXT, encrypt_url TEXT, "
                "extern_url TEXT, thumb_url TEXT, tp_url TEXT)"
            )
            conn.execute(
                "INSERT INTO kNonStoreEmoticonTable VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    primary_md5,
                    extern_md5,
                    aes_key,
                    f"https://example.com/{primary_md5}.gif",
                    "",
                    "",
                    "",
                    "",
                ),
            )
            conn.commit()
            conn.close()

            conn = sqlite3.connect(str(account_dir / "message_0.db"))
            conn.execute(
                "CREATE TABLE Msg_demo ("
                "local_type INTEGER, compress_content BLOB, message_content BLOB, packed_info_data BLOB)"
            )
            conn.executemany(
                "INSERT INTO Msg_demo VALUES (?, ?, ?, ?)",
                [
                    (
                        47,
                        None,
                        (
                            f'<msg><emoji md5="{message_md5}" externmd5="{message_extern_md5}" '
                            f'aeskey="{aes_key}" cdnurl="https://example.com/{message_md5}.png" /></msg>'
                        ),
                        bytes([0x10, 0x45]),
                    ),
                    (
                        47,
                        None,
                        f'<msg><emoji md5="{primary_md5}" cdnurl="https://example.com/{primary_md5}-2.png" /></msg>',
                        bytes([0x10, 0x45]),
                    ),
                    (
                        47,
                        None,
                        f'<msg><emoji md5="{no_url_md5}" /></msg>',
                        bytes([0x10, 0x45]),
                    ),
                ],
            )
            conn.commit()
            conn.close()

            catalog, stats = _collect_emoticon_download_catalog(account_dir)

            self.assertEqual(set(catalog), {primary_md5, extern_md5, message_md5})
            self.assertIn("emoticon_db_md5", catalog[primary_md5]["sources"])
            self.assertIn("message_xml", catalog[primary_md5]["sources"])
            self.assertIn("emoticon_db_extern_md5", catalog[extern_md5]["sources"])
            self.assertIn("message_xml", catalog[message_md5]["sources"])
            self.assertNotIn(no_url_md5, catalog)
            self.assertEqual(stats["emoticon_db_md5"], 1)
            self.assertEqual(stats["emoticon_db_extern_md5"], 1)
            self.assertEqual(stats["message_xml_rows"], 3)
            self.assertEqual(stats["message_xml_md5"], 3)
            self.assertEqual(stats["message_xml_md5_with_url"], 2)
            self.assertEqual(stats["message_xml_extern_md5"], 1)
            self.assertEqual(stats["message_builtin_expr_ids"], 1)
            self.assertEqual(stats["source_counts"]["message_xml"], 2)

            info = _lookup_emoticon_info(str(account_dir), extern_md5)
            self.assertEqual(info["md5"], primary_md5)
            self.assertEqual(info["extern_md5"], extern_md5)


if __name__ == "__main__":
    unittest.main()
