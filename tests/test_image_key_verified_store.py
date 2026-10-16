import asyncio
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _reload_key_modules(root: Path):
    previous = os.environ.get("WECHAT_TOOL_DATA_DIR")
    os.environ["WECHAT_TOOL_DATA_DIR"] = str(root)

    import wechat_decrypt_tool.app_paths as app_paths
    import wechat_decrypt_tool.key_store as key_store
    import wechat_decrypt_tool.routers.keys as keys_router

    importlib.reload(app_paths)
    importlib.reload(key_store)
    importlib.reload(keys_router)
    return previous, key_store, keys_router


def _restore_data_dir(previous: str | None) -> None:
    for logger_name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers[:]:
            try:
                handler.close()
            finally:
                logger.removeHandler(handler)
    if previous is None:
        os.environ.pop("WECHAT_TOOL_DATA_DIR", None)
    else:
        os.environ["WECHAT_TOOL_DATA_DIR"] = previous


def test_image_key_updates_default_to_unverified_and_clear_stale_provenance():
    with TemporaryDirectory() as td:
        previous, key_store, _ = _reload_key_modules(Path(td))
        try:
            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="weflow_local_verified",
                image_key_source_wxid_dir="D:/xwechat_files/wxid_demo_abcd",
                image_key_derived_wxid="wxid_demo",
                image_key_code=1234,
            )

            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="0x2C",
                image_aes_key="fedcba0987654321",
            )

            saved = key_store.get_account_keys_from_store("wxid_demo")
            assert saved["image_key_verified"] is False
            assert saved["image_key_source"] == "legacy_or_manual"
            assert saved["image_key_source_wxid_dir"] == ""
            assert saved["image_key_derived_wxid"] == ""
            assert saved["image_key_code"] is None
        finally:
            _restore_data_dir(previous)


def test_repeated_save_of_same_verified_pair_preserves_provenance():
    with TemporaryDirectory() as td:
        previous, key_store, _ = _reload_key_modules(Path(td))
        try:
            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="memory_v2_verified",
                image_key_source_wxid_dir="D:/xwechat_files/wxid_demo_abcd",
                image_key_derived_wxid="wxid_demo",
            )

            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="8a",
                image_aes_key="1234567890abcdef",
            )

            saved = key_store.get_account_keys_from_store("wxid_demo")
            assert saved["image_key_verified"] is True
            assert saved["image_key_source"] == "memory_v2_verified"
            assert saved["image_key_source_wxid_dir"].endswith("wxid_demo_abcd")
            assert saved["image_key_derived_wxid"] == "wxid_demo"
        finally:
            _restore_data_dir(previous)


def test_alias_image_update_does_not_copy_unrelated_database_key():
    with TemporaryDirectory() as td:
        previous, key_store, _ = _reload_key_modules(Path(td))
        try:
            key_store.upsert_account_keys_in_store(
                "account_a",
                db_key="a" * 64,
                db_key_source_wxid_dir="D:/xwechat_files/account_a",
            )
            key_store.upsert_account_keys_in_store(
                "account_b",
                db_key="b" * 64,
                db_key_source_wxid_dir="D:/xwechat_files/account_b",
            )

            key_store.upsert_account_keys_in_store(
                "account_a",
                aliases=["account_b"],
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="weflow_local_verified",
                image_key_source_wxid_dir="D:/xwechat_files/account_a",
            )

            account_a = key_store.get_account_keys_from_store("account_a")
            account_b = key_store.get_account_keys_from_store("account_b")
            assert account_a["db_key"] == "a" * 64
            assert account_b["db_key"] == "b" * 64
            assert account_a["image_aes_key"] == account_b["image_aes_key"]
        finally:
            _restore_data_dir(previous)


def test_get_saved_keys_uses_one_complete_image_key_record_without_alias_mixing():
    with TemporaryDirectory() as td:
        root = Path(td)
        db_storage = root / "xwechat_files" / "wxid_demo_abcd" / "db_storage"
        db_storage.mkdir(parents=True)
        previous, key_store, keys_router = _reload_key_modules(root)
        try:
            key_store.upsert_account_keys_in_store(
                "wxid_demo_abcd",
                image_xor_key="0x8A",
                image_aes_key="",
            )
            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="",
                image_aes_key="1234567890abcdef",
            )

            result = asyncio.run(
                keys_router.get_saved_keys(account="wxid_demo", db_storage_path=str(db_storage))
            )

            assert result["keys"]["image_xor_key"] == "0x8A"
            assert result["keys"]["image_aes_key"] == ""
            assert result["keys"]["image_key_verified"] is False
        finally:
            _restore_data_dir(previous)


def test_get_saved_keys_prefers_verified_complete_pair_and_exposes_provenance():
    with TemporaryDirectory() as td:
        root = Path(td)
        wxid_dir = root / "xwechat_files" / "wxid_demo_abcd"
        db_storage = wxid_dir / "db_storage"
        db_storage.mkdir(parents=True)
        previous, key_store, keys_router = _reload_key_modules(root)
        try:
            key_store.upsert_account_keys_in_store(
                "wxid_demo_abcd",
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="weflow_local_verified",
                image_key_source_wxid_dir=str(wxid_dir),
                image_key_derived_wxid="wxid_demo",
                image_key_code=138,
            )

            result = asyncio.run(
                keys_router.get_saved_keys(account="wxid_demo", db_storage_path=str(db_storage))
            )
            keys = result["keys"]

            assert keys["image_xor_key"] == "0x8A"
            assert keys["image_aes_key"] == "1234567890abcdef"
            assert keys["image_key_verified"] is True
            assert keys["image_key_source"] == "weflow_local_verified"
            assert keys["image_key_source_wxid_dir"] == str(wxid_dir.resolve())
            assert keys["image_key_derived_wxid"] == "wxid_demo"
            assert keys["image_key_code"] == 138
        finally:
            _restore_data_dir(previous)


def test_get_saved_keys_excludes_pair_verified_for_another_source_root():
    with TemporaryDirectory() as td:
        root = Path(td)
        current_wxid_dir = root / "current" / "xwechat_files" / "wxid_demo_abcd"
        stale_wxid_dir = root / "stale" / "xwechat_files" / "wxid_demo_abcd"
        db_storage = current_wxid_dir / "db_storage"
        db_storage.mkdir(parents=True)
        stale_wxid_dir.mkdir(parents=True)
        previous, key_store, keys_router = _reload_key_modules(root)
        try:
            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="weflow_local_verified",
                image_key_source_wxid_dir=str(stale_wxid_dir),
            )

            result = asyncio.run(
                keys_router.get_saved_keys(account="wxid_demo", db_storage_path=str(db_storage))
            )

            assert result["keys"]["image_xor_key"] == ""
            assert result["keys"]["image_aes_key"] == ""
            assert result["keys"]["image_key_verified"] is False
        finally:
            _restore_data_dir(previous)


def test_get_saved_keys_rejects_truthy_non_boolean_verified_metadata():
    with TemporaryDirectory() as td:
        root = Path(td)
        wxid_dir = root / "xwechat_files" / "wxid_demo_abcd"
        db_storage = wxid_dir / "db_storage"
        db_storage.mkdir(parents=True)
        previous, key_store, keys_router = _reload_key_modules(root)
        try:
            key_store._KEY_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            key_store._KEY_STORE_PATH.write_text(
                json.dumps({
                    "wxid_demo_abcd": {
                        "image_xor_key": "0x8A",
                        "image_aes_key": "1234567890abcdef",
                        "image_key_verified": "false",
                        "image_key_source": "edited_store",
                        "image_key_source_wxid_dir": str(wxid_dir),
                    }
                }),
                encoding="utf-8",
            )

            result = asyncio.run(
                keys_router.get_saved_keys(account="wxid_demo", db_storage_path=str(db_storage))
            )

            assert result["keys"]["image_key_verified"] is False
        finally:
            _restore_data_dir(previous)


def test_verified_store_overrides_stale_media_key_file():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "output" / "databases" / "wxid_demo"
        wxid_dir = root / "xwechat_files" / "wxid_demo_abcd"
        account_dir.mkdir(parents=True)
        wxid_dir.mkdir(parents=True)
        (account_dir / "_media_keys.json").write_text(
            json.dumps({"xor": 0x2C, "aes": "fedcba0987654321"}),
            encoding="utf-8",
        )
        (account_dir / "_source.json").write_text(
            json.dumps({"wxid_dir": str(wxid_dir)}),
            encoding="utf-8",
        )
        previous, key_store, _ = _reload_key_modules(root)
        try:
            import wechat_decrypt_tool.media_helpers as media_helpers

            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="weflow_local_verified",
                image_key_source_wxid_dir=str(wxid_dir),
            )

            loaded = media_helpers._load_media_keys(account_dir)

            assert loaded["xor"] == 0x8A
            assert loaded["aes"] == "1234567890abcdef"
            assert loaded["verified"] is True
            assert loaded["source"] == "weflow_local_verified"
        finally:
            _restore_data_dir(previous)


def test_verified_store_from_another_source_does_not_override_media_cache():
    with TemporaryDirectory() as td:
        root = Path(td)
        account_dir = root / "output" / "databases" / "wxid_demo"
        current_wxid_dir = root / "current" / "xwechat_files" / "wxid_demo_abcd"
        stale_wxid_dir = root / "stale" / "xwechat_files" / "wxid_demo_abcd"
        account_dir.mkdir(parents=True)
        current_wxid_dir.mkdir(parents=True)
        stale_wxid_dir.mkdir(parents=True)
        (account_dir / "_media_keys.json").write_text(
            json.dumps({"xor": 0x2C, "aes": "fedcba0987654321"}),
            encoding="utf-8",
        )
        (account_dir / "_source.json").write_text(
            json.dumps({"wxid_dir": str(current_wxid_dir)}),
            encoding="utf-8",
        )
        previous, key_store, _ = _reload_key_modules(root)
        try:
            import wechat_decrypt_tool.media_helpers as media_helpers

            key_store.upsert_account_keys_in_store(
                "wxid_demo",
                image_xor_key="0x8A",
                image_aes_key="1234567890abcdef",
                image_key_verified=True,
                image_key_source="weflow_local_verified",
                image_key_source_wxid_dir=str(stale_wxid_dir),
            )

            loaded = media_helpers._load_media_keys(account_dir)

            assert loaded["xor"] == 0x2C
            assert loaded["aes"] == "fedcba0987654321"
            assert loaded["verified"] is False
            assert loaded["source"] == "legacy_media_cache"
        finally:
            _restore_data_dir(previous)
