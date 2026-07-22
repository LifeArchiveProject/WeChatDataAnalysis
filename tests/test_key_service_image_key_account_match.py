import asyncio
import sys
import unittest
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


import wechat_decrypt_tool.key_service as key_service


class TestKeyServiceImageKeyAccountMatch(unittest.TestCase):
    def setUp(self) -> None:
        self._windows_patch = mock.patch.object(key_service, "is_windows", return_value=True)
        self._macos_patch = mock.patch.object(key_service, "is_macos", return_value=False)
        self._windows_patch.start()
        self._macos_patch.start()

    def tearDown(self) -> None:
        self._macos_patch.stop()
        self._windows_patch.stop()

    def test_normalize_internal_db_key_accepts_spaced_hex(self) -> None:
        key = key_service._normalize_internal_db_key("11 22 33 44 " * 8)
        self.assertEqual(len(key), 32)
        self.assertEqual(key[:4], bytes.fromhex("11223344"))

    def test_get_db_key_with_v4_auto_scans_dll_key_before_key_v4(self) -> None:
        fake_key_v4 = types.SimpleNamespace(
            recover_key=mock.Mock(return_value="A" * 64)
        )
        fake_pymem = types.SimpleNamespace(
            Pymem=mock.Mock(return_value=types.SimpleNamespace(process_id=4321))
        )
        dll_key = bytes.fromhex("11" * 32)

        with mock.patch.object(
            key_service,
            "_resolve_v4_probe_db_file",
            return_value=Path("D:/xwechat_files/wxid_demo/db_storage/MSG0.db"),
        ), mock.patch.object(
            key_service,
            "_load_internal_db_key_candidates",
            return_value=[dll_key],
        ), mock.patch.object(
            key_service.importlib,
            "import_module",
            return_value=fake_key_v4,
        ), mock.patch.dict(
            sys.modules,
            {"pymem": fake_pymem},
            clear=False,
        ):
            result = key_service._get_db_key_with_v4("D:/xwechat_files/wxid_demo/db_storage")

        self.assertEqual(result["db_key"], "bb" * 32)
        self.assertEqual(result["method"], "key_v4")
        self.assertEqual(result["internal_db_key_source"], "scan.py")
        self.assertEqual(result["internal_db_key_candidate_count"], 1)
        fake_key_v4.recover_key.assert_called_once_with(
            4321,
            str(Path("D:/xwechat_files/wxid_demo/db_storage/MSG0.db")),
            dll_key,
        )

    def test_get_db_key_with_v4_uses_internal_db_key_when_provided(self) -> None:
        fake_key_v4 = types.SimpleNamespace(
            recover_key=mock.Mock(return_value="A" * 64)
        )
        fake_pymem = types.SimpleNamespace(
            Pymem=mock.Mock(return_value=types.SimpleNamespace(process_id=4321))
        )
        internal_db_key = "11" * 32

        with mock.patch.object(
            key_service,
            "_resolve_v4_probe_db_file",
            return_value=Path("D:/xwechat_files/wxid_demo/db_storage/MSG0.db"),
        ), mock.patch.object(
            key_service,
            "_load_internal_db_key_candidates",
            side_effect=AssertionError("manual internal_db_key should skip DLL scan"),
        ), mock.patch.object(
            key_service.importlib,
            "import_module",
            return_value=fake_key_v4,
        ), mock.patch.dict(
            sys.modules,
            {"pymem": fake_pymem},
            clear=False,
        ):
            result = key_service._get_db_key_with_v4(
                "D:/xwechat_files/wxid_demo/db_storage",
                internal_db_key=internal_db_key,
                wechat_install_path="D:/Program Files/Tencent/WeChat",
            )

        self.assertEqual(result["method"], "key_v4")
        self.assertEqual(result["db_key"], "bb" * 32)
        fake_key_v4.recover_key.assert_called_once()
        call_args = fake_key_v4.recover_key.call_args.args
        self.assertEqual(call_args[0], 4321)
        self.assertEqual(call_args[1], str(Path("D:/xwechat_files/wxid_demo/db_storage/MSG0.db")))
        self.assertEqual(call_args[2], bytes.fromhex(internal_db_key))

    def test_get_db_key_with_v4_fails_before_key_v4_when_dll_key_missing(self) -> None:
        fake_key_v4 = types.SimpleNamespace(
            recover_key=mock.Mock(return_value="A" * 64)
        )

        with mock.patch.object(
            key_service,
            "_resolve_v4_probe_db_file",
            return_value=Path("D:/xwechat_files/wxid_demo/db_storage/MSG0.db"),
        ), mock.patch.object(
            key_service,
            "_load_internal_db_key_candidates",
            return_value=[],
        ), mock.patch.object(
            key_service.importlib,
            "import_module",
            return_value=fake_key_v4,
        ):
            with self.assertRaisesRegex(RuntimeError, "未从微信 DLL 中扫描到可用的辅助 key"):
                key_service._get_db_key_with_v4("D:/xwechat_files/wxid_demo/db_storage")

        fake_key_v4.recover_key.assert_not_called()

    def test_resolve_v4_probe_db_file_prefers_msg0_database(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_storage = Path(temp_dir) / "xwechat_files" / "wxid_demo" / "db_storage"
            db_storage.mkdir(parents=True)
            favorite = db_storage / "Favorite.db"
            msg0 = db_storage / "MSG0.db"
            favorite.write_bytes(b"\x01" * 4096)
            msg0.write_bytes(b"\x02" * 4096)

            result = key_service._resolve_v4_probe_db_file(str(db_storage))

        self.assertEqual(result.name, "MSG0.db")

    def test_get_db_key_workflow_uses_v4_before_hook(self) -> None:
        with mock.patch.object(
            key_service,
            "_get_db_key_with_v4",
            return_value={"db_key": "a" * 64, "method": "key_v4"},
        ) as v4_mock, mock.patch.object(
            key_service,
            "WeChatKeyFetcher",
            side_effect=AssertionError("hook should not be used when key_v4 succeeds"),
        ):
            result = key_service.get_db_key_workflow(db_storage_path="D:/xwechat_files/wxid/db_storage")

        self.assertEqual(result["db_key"], "a" * 64)
        self.assertEqual(result["method"], "key_v4")
        v4_mock.assert_called_once_with(
            "D:/xwechat_files/wxid/db_storage",
            internal_db_key=None,
            wechat_install_path=None,
        )

    def test_get_db_key_workflow_key_v4_mode_does_not_fallback_to_hook(self) -> None:
        with mock.patch.object(
            key_service,
            "_get_db_key_with_v4",
            side_effect=RuntimeError("v4 failed"),
        ), mock.patch.object(
            key_service,
            "WeChatKeyFetcher",
            side_effect=AssertionError("hook should not be used in key_v4-only mode"),
        ):
            with self.assertRaisesRegex(RuntimeError, "v4 failed"):
                key_service.get_db_key_workflow(
                    db_storage_path="D:/xwechat_files/wxid/db_storage",
                    key_mode="key_v4",
                )

    def test_get_db_key_workflow_hook_mode_skips_v4(self) -> None:
        fetcher = mock.Mock()
        fetcher.fetch_db_key.return_value = {"db_key": "c" * 64}

        with mock.patch.object(
            key_service,
            "_get_db_key_with_v4",
            side_effect=AssertionError("v4 should not be used in hook mode"),
        ), mock.patch.object(
            key_service,
            "WeChatKeyFetcher",
            return_value=fetcher,
        ):
            result = key_service.get_db_key_workflow(
                wechat_install_path="D:/WeChat",
                db_storage_path="D:/xwechat_files/wxid/db_storage",
                key_mode="hook",
            )

        fetcher.fetch_db_key.assert_called_once_with(wechat_install_path="D:/WeChat")
        self.assertEqual(result["db_key"], "c" * 64)
        self.assertEqual(result["method"], "hook")

    def test_get_db_key_workflow_falls_back_to_hook_when_v4_fails(self) -> None:
        fetcher = mock.Mock()
        fetcher.fetch_db_key.return_value = {"db_key": "b" * 64}

        with mock.patch.object(
            key_service,
            "_get_db_key_with_v4",
            side_effect=RuntimeError("v4 unavailable"),
        ), mock.patch.object(
            key_service,
            "WeChatKeyFetcher",
            return_value=fetcher,
        ):
            result = key_service.get_db_key_workflow(
                wechat_install_path="D:/WeChat",
                db_storage_path="D:/xwechat_files/wxid/db_storage",
            )

        fetcher.fetch_db_key.assert_called_once_with(wechat_install_path="D:/WeChat")
        self.assertEqual(result["db_key"], "b" * 64)
        self.assertEqual(result["method"], "hook")
        self.assertEqual(result["fallback_from"], "key_v4")
        self.assertIn("v4 unavailable", result["key_v4_error"])

    def test_local_image_keys_do_not_match_by_substring(self) -> None:
        remote_result = {
            "wxid": "wxid_demo_extra",
            "xor_key": "0x8A",
            "aes_key": "BBBBBBBBBBBBBBBB",
        }

        with mock.patch.object(
            key_service,
            "try_get_local_image_keys",
            return_value=[
                {"wxid": "wxid_demo", "xor_key": "0x01", "aes_key": "AAAAAAAAAAAAAAAA"},
            ],
        ), mock.patch.object(
            key_service,
            "_resolve_account_dir",
            return_value=Path("D:/tmp/output/databases/wxid_demo_extra"),
        ), mock.patch.object(
            key_service,
            "_resolve_account_wxid_dir",
            return_value=Path("D:/tmp/xwechat_files/wxid_demo_extra"),
        ), mock.patch.object(
            key_service,
            "upsert_account_keys_in_store",
        ) as upsert_mock, mock.patch.object(
            key_service,
            "fetch_and_save_remote_keys",
            new=mock.AsyncMock(return_value=remote_result),
        ) as remote_mock:
            result = asyncio.run(key_service.get_image_key_integrated_workflow("wxid_demo_extra"))

        self.assertEqual(result["wxid"], remote_result["wxid"])
        self.assertEqual(result["xor_key"], remote_result["xor_key"])
        self.assertEqual(result["aes_key"], remote_result["aes_key"])
        self.assertEqual(result["source"], "remote_api")
        self.assertFalse(result["verified"])
        remote_mock.assert_awaited_once_with(
            "wxid_demo_extra", wxid_dir=None, db_storage_path=None, persist=False
        )
        upsert_mock.assert_not_called()

    def test_exact_native_account_match_still_requires_v2_verification(self) -> None:
        remote_result = {
            "wxid": "wxid_demo_extra",
            "xor_key": "0x8A",
            "aes_key": "BBBBBBBBBBBBBBBB",
        }
        with mock.patch.object(
            key_service,
            "try_get_local_image_keys",
            return_value=[
                {"wxid": "wxid_demo", "xor_key": "0x01", "aes_key": "AAAAAAAAAAAAAAAA"},
                {"wxid": "wxid_demo_extra", "xor_key": "0x8A", "aes_key": "BBBBBBBBBBBBBBBB"},
            ],
        ), mock.patch.object(
            key_service,
            "_resolve_account_dir",
            return_value=Path("D:/tmp/output/databases/wxid_demo_extra"),
        ), mock.patch.object(
            key_service,
            "_resolve_account_wxid_dir",
            return_value=Path("D:/tmp/xwechat_files/wxid_demo_extra"),
        ), mock.patch.object(
            key_service,
            "upsert_account_keys_in_store",
        ) as upsert_mock, mock.patch.object(
            key_service,
            "fetch_and_save_remote_keys",
            new=mock.AsyncMock(return_value=remote_result),
        ) as remote_mock:
            result = asyncio.run(key_service.get_image_key_integrated_workflow("wxid_demo_extra"))

        self.assertEqual(result["wxid"], "wxid_demo_extra")
        self.assertEqual(result["xor_key"], "0x8A")
        self.assertEqual(result["aes_key"], "BBBBBBBBBBBBBBBB")
        self.assertFalse(result["verified"])
        remote_mock.assert_awaited_once_with(
            "wxid_demo_extra", wxid_dir=None, db_storage_path=None, persist=False
        )
        upsert_mock.assert_not_called()

    def test_suffixed_native_account_match_still_requires_v2_verification(self) -> None:
        remote_result = {
            "wxid": "wxid_demo_8d63",
            "xor_key": "0x2C",
            "aes_key": "AAAAAAAAAAAAAAAA",
        }
        with mock.patch.object(
            key_service,
            "try_get_local_image_keys",
            return_value=[
                {"wxid": "wxid_demo", "xor_key": "0x2C", "aes_key": "AAAAAAAAAAAAAAAA"},
            ],
        ), mock.patch.object(
            key_service,
            "_resolve_account_dir",
            return_value=Path("D:/tmp/output/databases/wxid_demo"),
        ), mock.patch.object(
            key_service,
            "_resolve_account_wxid_dir",
            return_value=Path("D:/tmp/xwechat_files/wxid_demo_8d63"),
        ), mock.patch.object(
            key_service,
            "upsert_account_keys_in_store",
        ) as upsert_mock, mock.patch.object(
            key_service,
            "fetch_and_save_remote_keys",
            new=mock.AsyncMock(return_value=remote_result),
        ) as remote_mock:
            result = asyncio.run(key_service.get_image_key_integrated_workflow("wxid_demo"))

        self.assertEqual(result["wxid"], "wxid_demo_8d63")
        self.assertEqual(result["xor_key"], "0x2C")
        self.assertEqual(result["aes_key"], "AAAAAAAAAAAAAAAA")
        self.assertFalse(result["verified"])
        remote_mock.assert_awaited_once_with(
            "wxid_demo", wxid_dir=None, db_storage_path=None, persist=False
        )
        upsert_mock.assert_not_called()

    def test_fetch_remote_keys_can_use_db_storage_path_without_decrypted_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            wxid_dir = Path(temp_dir) / "xwechat_files" / "wxid_v4mbduwqtzpt22"
            db_storage_dir = wxid_dir / "db_storage"
            db_storage_dir.mkdir(parents=True, exist_ok=True)

            class _FakeResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {
                        "xorKey": "138",
                        "aesKey": "c3f3366e23628242",
                        "nickName": "demo",
                    }

            class _FakeAsyncClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                async def post(self, url, data=None, files=None):
                    self.last_url = url
                    self.last_data = data
                    self.last_files = files
                    return _FakeResponse()

            with mock.patch.object(
                key_service,
                "_resolve_account_dir",
                side_effect=AssertionError("should not require decrypted account dir"),
            ), mock.patch.object(
                key_service,
                "get_wechat_internal_global_config",
                side_effect=[b"global-config", b"crc-bytes"],
            ), mock.patch.object(
                key_service.httpx,
                "AsyncClient",
                _FakeAsyncClient,
            ), mock.patch.object(
                key_service,
                "upsert_account_keys_in_store",
            ) as upsert_mock:
                result = asyncio.run(
                    key_service.fetch_and_save_remote_keys(
                        "wxid_v4mbduwqtzpt22",
                        db_storage_path=str(db_storage_dir),
                    )
                )

        self.assertEqual(result["wxid"], "wxid_v4mbduwqtzpt22")
        self.assertEqual(result["xor_key"], "0x8A")
        self.assertEqual(result["aes_key"], "c3f3366e23628242")
        upsert_mock.assert_called_once_with(
            account="wxid_v4mbduwqtzpt22",
            image_xor_key="0x8A",
            image_aes_key="c3f3366e23628242",
            image_key_verified=False,
            image_key_source="remote_api",
        )
        self.assertEqual(result["source"], "remote_api")
        self.assertFalse(result["verified"])


if __name__ == "__main__":
    unittest.main()
