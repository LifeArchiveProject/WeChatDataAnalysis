import asyncio
import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import key_service, platform_support
from wechat_decrypt_tool.image_key_resolver import ImageKeyResolution, TemplateScanResult
from wechat_decrypt_tool.path_fix import PathFixRequest
from wechat_decrypt_tool.routers import keys as keys_router


class TestMacosPlatformSupport(unittest.TestCase):
    def test_bundled_macos_resources_are_self_contained(self) -> None:
        helper = platform_support.mac_image_scan_helper_path()
        image_library = platform_support.mac_image_scan_library_path()
        wcdb_api = platform_support.mac_wcdb_api_path("arm64")

        self.assertTrue(helper.is_file())
        self.assertTrue(image_library.is_file())
        self.assertTrue(wcdb_api.is_file())
        self.assertEqual(helper.parent, image_library.parent)
        self.assertIn("wechat_decrypt_tool/native/macos", helper.as_posix())
        self.assertNotIn("WeFlow", helper.as_posix())

    def test_apple_silicon_capabilities_only_disable_db_key_extraction(self) -> None:
        with (
            patch.object(platform_support, "current_platform", return_value="macos"),
            patch.object(platform, "machine", return_value="arm64"),
        ):
            capabilities = platform_support.runtime_capabilities()

        self.assertFalse(capabilities["database_key_extraction"])
        self.assertTrue(capabilities["database_key_manual_input"])
        self.assertTrue(capabilities["database_decryption"])
        self.assertTrue(capabilities["image_key_memory_scan"])
        self.assertTrue(capabilities["realtime_wcdb"])
        self.assertTrue(capabilities["account_archive_cross_platform"])

    def test_database_key_endpoint_returns_manual_input_guidance_on_macos(self) -> None:
        with patch.object(keys_router, "is_macos", return_value=True):
            result = asyncio.run(keys_router.get_wechat_db_key())

        self.assertEqual(result["status"], -3)
        self.assertFalse(result["data"]["database_key_extraction"])
        self.assertTrue(result["data"]["manual_input_supported"])
        self.assertIn("手动填写", result["errmsg"])

    def test_database_key_service_never_starts_extraction_on_macos(self) -> None:
        with (
            patch.object(key_service, "is_macos", return_value=True),
            patch.object(key_service, "_get_db_key_with_v4") as memory_scan,
            patch.object(key_service, "WeChatKeyFetcher") as hook_fetcher,
        ):
            with self.assertRaisesRegex(RuntimeError, "手动填写"):
                key_service.get_db_key_workflow(
                    db_storage_path="/tmp/wxid_demo/db_storage",
                    key_mode="auto",
                )

        memory_scan.assert_not_called()
        hook_fetcher.assert_not_called()

    def test_macos_kvcomm_candidates_follow_weflow_data_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            default_kvcomm = (
                home
                / "Library"
                / "Containers"
                / "com.tencent.xinWeChat"
                / "Data"
                / "Documents"
                / "app_data"
                / "net"
                / "kvcomm"
            )
            account_dir = home / "wechat" / "xwechat_files" / "wxid_demo"
            derived_kvcomm = home / "wechat" / "app_data" / "net" / "kvcomm"
            default_kvcomm.mkdir(parents=True)
            derived_kvcomm.mkdir(parents=True)

            with (
                patch.object(key_service, "is_macos", return_value=True),
                patch.object(key_service.Path, "home", return_value=home),
                patch.dict(os.environ, {"WECHAT_IMAGE_KVCOMM_DIR": ""}),
            ):
                candidates = key_service._get_image_key_kvcomm_dirs(account_dir)

            self.assertEqual(candidates, (default_kvcomm, derived_kvcomm))

    def test_macos_kvcomm_candidates_use_default_before_directories_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            account_dir = home / "wechat" / "xwechat_files" / "wxid_demo"
            with (
                patch.object(key_service, "is_macos", return_value=True),
                patch.object(key_service.Path, "home", return_value=home),
                patch.dict(os.environ, {"WECHAT_IMAGE_KVCOMM_DIR": ""}),
            ):
                candidates = key_service._get_image_key_kvcomm_dirs(account_dir)

        self.assertEqual(
            candidates,
            (
                home
                / "Library"
                / "Containers"
                / "com.tencent.xinWeChat"
                / "Data"
                / "Documents"
                / "app_data"
                / "net"
                / "kvcomm",
            ),
        )

    def test_path_validation_uses_a_unix_example_on_macos(self) -> None:
        request = object.__new__(PathFixRequest)
        with patch("wechat_decrypt_tool.path_fix.os.name", "posix"):
            message = request._validate_paths_in_json({"db_storage_path": "relative/path"})

        self.assertIn("/Users/name/Library/Containers", message)
        self.assertNotIn("Windows绝对路径示例", message)

    def test_macos_image_key_derivation_checks_each_existing_kvcomm_dir(self) -> None:
        account_dir = ROOT / ".pytest-kvcomm-account"
        first = account_dir / "first"
        second = account_dir / "second"
        scan = TemplateScanResult(
            templates=(),
            inferred_xor_key=None,
            used_fallback=False,
            files_scanned=0,
        )
        expected = ImageKeyResolution(
            code=138,
            wxid="wxid_demo",
            xor_key=0x8A,
            aes_key="1234567890abcdef",
            verified=True,
            template_path=account_dir / "sample.dat",
            inferred_xor_key=0x8A,
        )

        with (
            patch.object(key_service, "_get_image_key_kvcomm_dirs", return_value=(first, second)),
            patch.object(key_service, "resolve_local_image_key", side_effect=(None, expected)) as resolver,
        ):
            result = key_service._resolve_local_image_key_from_kvcomm_candidates(
                account_dir=account_dir,
                target_wxid="wxid_demo",
                account="wxid_demo",
                local_native_wxids=["wxid_demo"],
                template_scan=scan,
            )

        self.assertIs(result, expected)
        self.assertEqual(
            [call.kwargs["kvcomm_dir"] for call in resolver.call_args_list],
            [first, second],
        )


if __name__ == "__main__":
    unittest.main()
