import importlib
import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatAccountsKeyReady(unittest.TestCase):
    def _with_temp_data_dir(self):
        return TemporaryDirectory()

    def test_key_ready_accounts_require_db_key_and_image_key(self) -> None:
        with self._with_temp_data_dir() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.chat_accounts as chat_accounts

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(chat_accounts)

                key_store.upsert_account_keys_in_store(
                    "wxid_ready",
                    db_key="A" * 64,
                    image_xor_key="0x8A",
                    image_aes_key="1234567890abcdef",
                )
                key_store.upsert_account_keys_in_store("wxid_db_only", db_key="B" * 64)
                key_store.upsert_account_keys_in_store(
                    "wxid_img_only",
                    image_xor_key="0x2C",
                    image_aes_key="fedcba0987654321",
                )

                by_name = {ctx.name: ctx for ctx in chat_accounts.list_chat_account_contexts()}

                self.assertIn("wxid_ready", by_name)
                self.assertIn("wxid_db_only", by_name)
                self.assertNotIn("wxid_img_only", by_name)
                self.assertTrue(by_name["wxid_ready"].keys_ready)
                self.assertTrue(by_name["wxid_ready"].db_key_present)
                self.assertTrue(by_name["wxid_ready"].image_key_present)
                self.assertFalse(by_name["wxid_db_only"].keys_ready)
                self.assertTrue(by_name["wxid_db_only"].db_key_present)
                self.assertFalse(by_name["wxid_db_only"].image_key_present)
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir

    def test_media_keys_file_counts_as_image_key_for_switching(self) -> None:
        with self._with_temp_data_dir() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.chat_accounts as chat_accounts

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(chat_accounts)

                key_store.upsert_account_keys_in_store("wxid_media_fallback", db_key="C" * 64)
                account_dir = root / "output" / "databases" / "wxid_media_fallback"
                account_dir.mkdir(parents=True, exist_ok=True)
                (account_dir / "_media_keys.json").write_text('{"xor": 138, "aes": ""}', encoding="utf-8")

                ctx = chat_accounts.resolve_chat_account_context("wxid_media_fallback")

                self.assertTrue(ctx.db_key_present)
                self.assertTrue(ctx.image_key_present)
                self.assertTrue(ctx.image_xor_key_present)
                self.assertFalse(ctx.image_aes_key_present)
                self.assertTrue(ctx.keys_ready)
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir

    def test_source_aliases_are_listed_once_under_the_base_wxid(self) -> None:
        with self._with_temp_data_dir() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.chat_accounts as chat_accounts

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(chat_accounts)

                base_account = "wxid_v4mbduwqtzpt22"
                source_account = f"{base_account}_1e7a"
                wxid_dir = root / "xwechat_files" / source_account
                db_storage = wxid_dir / "db_storage"
                db_storage.mkdir(parents=True)

                key_store.upsert_account_keys_in_store(
                    base_account,
                    aliases=[source_account],
                    db_key="D" * 64,
                    image_xor_key="0x8A",
                    image_aes_key="1234567890abcdef",
                    db_key_source_wxid_dir=str(wxid_dir),
                    db_key_source_db_storage_path=str(db_storage),
                )

                contexts = chat_accounts.list_chat_account_contexts()

                self.assertEqual([ctx.name for ctx in contexts], [base_account])
                self.assertEqual(contexts[0].db_storage_path, str(db_storage.resolve()))
                self.assertTrue(contexts[0].keys_ready)
                resolved_alias = chat_accounts.resolve_chat_account_context(source_account)
                self.assertEqual(resolved_alias.name, base_account)
                self.assertEqual(resolved_alias.db_storage_path, str(db_storage.resolve()))
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir

    def test_direct_key_store_source_replaces_stale_source_marker(self) -> None:
        """A newly captured direct source must win over the prior account marker."""
        with self._with_temp_data_dir() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.chat_accounts as chat_accounts
                import wechat_decrypt_tool.media_helpers as media_helpers

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(chat_accounts)
                importlib.reload(media_helpers)

                account = "wxid_real_user"
                account_dir = root / "output" / "databases" / account
                account_dir.mkdir(parents=True, exist_ok=True)
                old_source = root / "wechat" / "old" / "db_storage"
                new_source = root / "wechat" / "new" / "db_storage"
                old_source.mkdir(parents=True)
                new_source.mkdir(parents=True)
                marker = account_dir / "_source.json"
                marker.write_text(
                    json.dumps({"db_storage_path": str(old_source)}),
                    encoding="utf-8",
                )

                key_store.upsert_account_keys_in_store(
                    account,
                    db_key="E" * 64,
                    db_key_source_db_storage_path=str(new_source),
                )

                context = chat_accounts.resolve_chat_account_context(account)

                self.assertEqual(context.db_storage_path, str(new_source.resolve()))
                persisted = json.loads(marker.read_text(encoding="utf-8"))
                self.assertEqual(persisted["db_storage_path"], str(new_source.resolve()))
                self.assertEqual(
                    media_helpers._resolve_account_db_storage_dir(account_dir),
                    new_source.resolve(),
                )
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir

    def test_source_alias_with_internal_wxid_underscores_canonicalizes(self) -> None:
        from wechat_decrypt_tool.account_identity import canonical_account_name
        from wechat_decrypt_tool.media_helpers import _clean_weflow_account_dir_name

        self.assertEqual(
            canonical_account_name("wxid_real_user_a73c"),
            "wxid_real_user",
        )
        self.assertEqual(
            _clean_weflow_account_dir_name("wxid_real_user_a73c"),
            "wxid_real_user",
        )

    def test_imported_snapshot_hides_host_aliases_and_legacy_backup_directories(self) -> None:
        with self._with_temp_data_dir() as td:
            root = Path(td)
            prev_data_dir = os.environ.get("WECHAT_TOOL_DATA_DIR")
            try:
                os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

                import wechat_decrypt_tool.app_paths as app_paths
                import wechat_decrypt_tool.key_store as key_store
                import wechat_decrypt_tool.chat_accounts as chat_accounts

                importlib.reload(app_paths)
                importlib.reload(key_store)
                importlib.reload(chat_accounts)

                base_account = "wxid_imported"
                source_account = f"{base_account}_1e7a"
                databases_dir = root / "output" / "databases"
                account_dir = databases_dir / base_account
                legacy_backup = databases_dir / f"{base_account}.backup-20260812-200746"
                staging_dir = databases_dir / f".{base_account}.import-fixture"

                for target in (account_dir, legacy_backup, staging_dir):
                    target.mkdir(parents=True, exist_ok=True)
                    for db_name in ("session.db", "contact.db"):
                        connection = sqlite3.connect(str(target / db_name))
                        connection.execute("CREATE TABLE fixture (value TEXT)")
                        connection.commit()
                        connection.close()

                (account_dir / "_source.json").write_text(
                    json.dumps(
                        {
                            "import_mode": "manual_import",
                            "import_source_path": "/HOST/windows-export.zip",
                        }
                    ),
                    encoding="utf-8",
                )
                (account_dir / "account.json").write_text(
                    json.dumps({"username": base_account}),
                    encoding="utf-8",
                )

                wxid_dir = root / "xwechat_files" / source_account
                db_storage = wxid_dir / "db_storage"
                db_storage.mkdir(parents=True)
                key_store.upsert_account_keys_in_store(
                    base_account,
                    aliases=[source_account],
                    db_key="D" * 64,
                    image_xor_key="0x8A",
                    image_aes_key="1234567890abcdef",
                    db_key_source_wxid_dir=str(wxid_dir),
                    db_key_source_db_storage_path=str(db_storage),
                )

                contexts = chat_accounts.list_chat_account_contexts()

                self.assertEqual([ctx.name for ctx in contexts], [base_account])
                self.assertEqual(contexts[0].mode, "decrypted")
                self.assertTrue(contexts[0].prefers_decrypted_snapshot)
                self.assertEqual(contexts[0].db_storage_path, "")
                resolved_alias = chat_accounts.resolve_chat_account_context(source_account)
                self.assertEqual(resolved_alias.name, base_account)
                self.assertEqual(resolved_alias.mode, "decrypted")
                resolved_backup = chat_accounts.resolve_chat_account_context(legacy_backup.name)
                self.assertEqual(resolved_backup.name, base_account)
                self.assertEqual(resolved_backup.mode, "decrypted")
            finally:
                if prev_data_dir is None:
                    os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
                else:
                    os.environ["WECHAT_TOOL_DATA_DIR"] = prev_data_dir


if __name__ == "__main__":
    unittest.main()
