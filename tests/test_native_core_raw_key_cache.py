import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import key_store, native_core_raw_key_cache, native_core_realtime
from wechat_decrypt_tool.routers import decrypt as decrypt_router


class TestNativeCoreRawKeyCache(unittest.TestCase):
    def test_cache_location_follows_internal_data_dir_not_export_output(self) -> None:
        with TemporaryDirectory() as td:
            data_dir = Path(td) / "internal"
            output_dir = Path(td) / "export-output"
            with patch.dict(
                os.environ,
                {
                    "WECHAT_TOOL_DATA_DIR": str(data_dir),
                    "WECHAT_TOOL_OUTPUT_DIR": str(output_dir),
                },
            ):
                self.assertEqual(
                    native_core_raw_key_cache._cache_directory(),
                    data_dir / ".native-core-cache-v1",
                )

    def test_round_trip_is_encrypted_and_bound_to_database_key(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            database = root / "message" / "message_0.db"
            database.parent.mkdir(parents=True)
            database.write_bytes(b"database")
            cache_dir = Path(td) / "cache"
            salt = bytes(range(16))
            raw_key = bytes(range(32))
            database_key = bytes(reversed(range(32)))

            with patch.object(
                native_core_raw_key_cache,
                "_cache_directory",
                return_value=cache_dir,
            ):
                native_core_raw_key_cache.merge_cached_raw_keys(
                    root,
                    database_key,
                    {database: (salt, raw_key)},
                )
                cache_files = list(cache_dir.glob("*.bin"))
                self.assertEqual(len(cache_files), 1)
                encrypted = cache_files[0].read_bytes()
                if sys.platform.startswith("win"):
                    self.assertTrue(encrypted.startswith(b"WCEDP001"))
                self.assertNotIn(salt, encrypted)
                self.assertNotIn(raw_key, encrypted)

                loaded = native_core_raw_key_cache.load_cached_raw_keys(
                    root,
                    database_key,
                    [database],
                )
                cache_key = native_core_raw_key_cache.database_cache_key(database)
                self.assertEqual(loaded[cache_key].salt, salt)
                self.assertEqual(bytes(loaded[cache_key].key), raw_key)

                self.assertEqual(
                    native_core_raw_key_cache.load_cached_raw_keys(
                        root,
                        b"x" * 32,
                        [database],
                    ),
                    {},
                )

    def test_tampered_cache_is_rejected_without_system_interaction(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            database = root / "session" / "session.db"
            database.parent.mkdir(parents=True)
            database.write_bytes(b"database")
            cache_dir = Path(td) / "cache"
            database_key = b"k" * 32

            with patch.object(
                native_core_raw_key_cache,
                "_cache_directory",
                return_value=cache_dir,
            ):
                native_core_raw_key_cache.merge_cached_raw_keys(
                    root,
                    database_key,
                    {database: (b"s" * 16, b"r" * 32)},
                )
                cache_file = next(cache_dir.glob("*.bin"))
                payload = bytearray(cache_file.read_bytes())
                payload[-1] ^= 0x01
                cache_file.write_bytes(payload)

                self.assertEqual(
                    native_core_raw_key_cache.load_cached_raw_keys(
                        root,
                        database_key,
                        [database],
                    ),
                    {},
                )

    def test_kdf_profile_change_invalidates_existing_cache(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            database = root / "session" / "session.db"
            database.parent.mkdir(parents=True)
            database.write_bytes(b"database")
            cache_dir = Path(td) / "cache"
            database_key = b"k" * 32

            with patch.object(
                native_core_raw_key_cache,
                "_cache_directory",
                return_value=cache_dir,
            ):
                native_core_raw_key_cache.merge_cached_raw_keys(
                    root,
                    database_key,
                    {database: (b"s" * 16, b"r" * 32)},
                )
                with patch.object(
                    native_core_raw_key_cache,
                    "_DATABASE_KDF_PROFILE",
                    b"future-profile",
                ):
                    self.assertEqual(
                        native_core_raw_key_cache.load_cached_raw_keys(
                            root,
                            database_key,
                            [database],
                        ),
                        {},
                    )

    def test_platform_protection_failure_never_writes_plaintext_fallback(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            database = root / "session" / "session.db"
            database.parent.mkdir(parents=True)
            database.write_bytes(b"database")
            cache_dir = Path(td) / "cache"

            with (
                patch.object(
                    native_core_raw_key_cache,
                    "_cache_directory",
                    return_value=cache_dir,
                ),
                patch.object(
                    native_core_raw_key_cache,
                    "_protect_platform_payload",
                    side_effect=OSError("platform protection failed"),
                ),
                self.assertRaisesRegex(OSError, "platform protection failed"),
            ):
                native_core_raw_key_cache.merge_cached_raw_keys(
                    root,
                    b"k" * 32,
                    {database: (b"s" * 16, b"r" * 32)},
                )

            self.assertEqual(list(cache_dir.glob("*.bin")), [])

    def test_removing_one_entry_preserves_other_database_entries(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            first = root / "message" / "message_0.db"
            second = root / "message" / "message_1.db"
            first.parent.mkdir(parents=True)
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            cache_dir = Path(td) / "cache"
            database_key = b"d" * 32

            with patch.object(
                native_core_raw_key_cache,
                "_cache_directory",
                return_value=cache_dir,
            ):
                native_core_raw_key_cache.merge_cached_raw_keys(
                    root,
                    database_key,
                    {
                        first: (b"1" * 16, b"a" * 32),
                        second: (b"2" * 16, b"b" * 32),
                    },
                )
                self.assertTrue(
                    native_core_raw_key_cache.remove_cached_raw_key(
                        root,
                        database_key,
                        first,
                    )
                )
                loaded = native_core_raw_key_cache.load_cached_raw_keys(
                    root,
                    database_key,
                    [first, second],
                )
                self.assertNotIn(
                    native_core_raw_key_cache.database_cache_key(first), loaded
                )
                second_entry = loaded[
                    native_core_raw_key_cache.database_cache_key(second)
                ]
                self.assertEqual(second_entry.salt, b"2" * 16)
                self.assertEqual(bytes(second_entry.key), b"b" * 32)

    def test_key_save_prepares_cache_before_chat_is_opened(self) -> None:
        result = {
            "success": 2,
            "source_wxid_dir": "D:/fixture/wxid_demo",
            "source_db_storage_path": "D:/fixture/wxid_demo/db_storage",
            "db_diagnostics": {
                "session.db": {
                    "db_name": "session.db",
                    "success": True,
                    "key_mode": "sqlcipher_passphrase",
                    "failed_pages": 0,
                    "diagnostic_status": "ok",
                },
                "message_0.db": {
                    "db_name": "message_0.db",
                    "success": True,
                    "key_mode": "sqlcipher_passphrase",
                    "failed_pages": 0,
                    "diagnostic_status": "ok",
                },
            },
        }
        with (
            patch.object(decrypt_router, "upsert_account_keys_in_store") as upsert,
            patch.object(
                native_core_realtime,
                "prepare_account_raw_key_cache",
                return_value=8,
            ) as prepare,
        ):
            decrypt_router._save_db_key_for_account(
                "wxid_demo",
                "ab" * 32,
                result,
            )

        upsert.assert_called_once()
        prepare.assert_called_once_with(
            Path("D:/fixture/wxid_demo/db_storage"),
            "ab" * 32,
            account="wxid_demo",
        )

    def test_last_account_alias_removal_deletes_root_cache(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td) / "db_storage"
            database = root / "session" / "session.db"
            database.parent.mkdir(parents=True)
            database.write_bytes(b"database")
            cache_dir = Path(td) / "cache"
            key_store_path = Path(td) / "account_keys.json"
            database_key = b"k" * 32

            with (
                patch.object(key_store, "_KEY_STORE_PATH", key_store_path),
                patch.object(
                    native_core_raw_key_cache,
                    "_cache_directory",
                    return_value=cache_dir,
                ),
            ):
                key_store.upsert_account_keys_in_store(
                    "wxid_demo",
                    db_key=database_key.hex(),
                    aliases=["wxid_demo_alias"],
                    db_key_source_wxid_dir=str(root.parent),
                )
                native_core_raw_key_cache.merge_cached_raw_keys(
                    root,
                    database_key,
                    {database: (b"s" * 16, b"r" * 32)},
                )
                cache_file = next(cache_dir.glob("*.bin"))

                self.assertTrue(
                    key_store.remove_account_keys_from_store("wxid_demo")
                )
                self.assertTrue(cache_file.exists())
                self.assertTrue(
                    key_store.remove_account_keys_from_store("wxid_demo_alias")
                )
                self.assertFalse(cache_file.exists())

    def test_db_source_root_change_deletes_the_old_cache(self) -> None:
        with TemporaryDirectory() as td:
            old_root = Path(td) / "old" / "db_storage"
            new_root = Path(td) / "new" / "db_storage"
            old_database = old_root / "session" / "session.db"
            old_database.parent.mkdir(parents=True)
            old_database.write_bytes(b"database")
            new_root.mkdir(parents=True)
            cache_dir = Path(td) / "cache"
            key_store_path = Path(td) / "account_keys.json"
            database_key = b"k" * 32

            with (
                patch.object(key_store, "_KEY_STORE_PATH", key_store_path),
                patch.object(
                    native_core_raw_key_cache,
                    "_cache_directory",
                    return_value=cache_dir,
                ),
            ):
                key_store.upsert_account_keys_in_store(
                    "wxid_demo",
                    db_key=database_key.hex(),
                    db_key_source_db_storage_path=str(old_root),
                )
                native_core_raw_key_cache.merge_cached_raw_keys(
                    old_root,
                    database_key,
                    {old_database: (b"s" * 16, b"r" * 32)},
                )
                old_cache_file = next(cache_dir.glob("*.bin"))

                key_store.upsert_account_keys_in_store(
                    "wxid_demo",
                    db_key=database_key.hex(),
                    db_key_source_db_storage_path=str(new_root),
                )
                self.assertFalse(old_cache_file.exists())


if __name__ == "__main__":
    unittest.main()
