import asyncio
import json
import os
import platform
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import key_service, platform_support
from wechat_decrypt_tool.image_key_resolver import ImageKeyResolution, TemplateScanResult
from wechat_decrypt_tool.path_fix import PathFixRequest
from wechat_decrypt_tool.routers import keys as keys_router


class TestMacosPlatformSupport(unittest.TestCase):
    def test_packaged_native_resources_prefer_stable_sibling_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backend = root / "WeChatDataAnalysis.app" / "Contents" / "Resources" / "backend"
            external_helper = backend / "native" / "macos" / "db-key" / "wda_xkey_helper"
            embedded_native = root / "_MEI" / "wechat_decrypt_tool" / "native"
            embedded_helper = embedded_native / "macos" / "db-key" / "wda_xkey_helper"
            external_helper.parent.mkdir(parents=True)
            embedded_helper.parent.mkdir(parents=True)
            external_helper.write_bytes(b"producer-signed-helper")
            embedded_helper.write_bytes(b"pyinstaller-normalized-helper")

            with (
                patch.object(platform_support.sys, "frozen", True, create=True),
                patch.object(platform_support.sys, "executable", str(backend / "wechat-backend")),
                patch.object(platform_support, "_native_root", return_value=embedded_native),
                patch.object(platform_support.sys, "_MEIPASS", str(root / "_MEI"), create=True),
            ):
                selected = platform_support.mac_db_key_bundle_dir()

        self.assertEqual(selected, external_helper.parent.resolve())

    def test_packaged_database_key_bundle_ignores_environment_override(self) -> None:
        bundled_helper = Path(
            "/Applications/WeChatDataAnalysis.app/Contents/Resources/backend/"
            "native/macos/db-key/wda_xkey_helper"
        )
        with (
            patch.dict(
                os.environ,
                {"WECHAT_TOOL_MACOS_DB_KEY_BUNDLE": "/tmp/untrusted-xkey"},
                clear=False,
            ),
            patch.object(platform_support.sys, "frozen", True, create=True),
            patch.object(
                platform_support,
                "_bundled_native_candidates",
                return_value=(bundled_helper,),
            ) as candidates,
        ):
            root = platform_support.mac_db_key_bundle_dir()

        self.assertEqual(root, bundled_helper.parent)
        self.assertEqual(candidates.call_args.kwargs["explicit"], "")

    def test_bundled_macos_resources_are_self_contained(self) -> None:
        helper = platform_support.mac_image_scan_helper_path()
        image_library = platform_support.mac_image_scan_library_path()

        self.assertTrue(helper.is_file())
        self.assertTrue(image_library.is_file())
        self.assertEqual(helper.parent, image_library.parent)
        self.assertIn("wechat_decrypt_tool/native/macos", helper.as_posix())
        self.assertNotIn("WeFlow", helper.as_posix())

    def test_apple_silicon_capabilities_enable_validated_db_key_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            native_root = Path(temp_dir)
            client = native_root / "libwechatdb_client.dylib"
            broker = native_root / "wechatdb_broker"
            manifest = native_root / "wechatdb_native_build.json"
            client.write_bytes(b"client")
            broker.write_bytes(b"broker")
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "buildId": "dev-local",
                        "developmentBuild": True,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(platform_support, "current_platform", return_value="macos"),
                patch.object(platform, "machine", return_value="arm64"),
                patch.object(
                    platform_support,
                    "mac_native_core_paths",
                    return_value=(client, broker, manifest),
                ),
                patch(
                    "wechat_decrypt_tool.macos_db_key_helper.inspect_macos_db_key_bundle",
                    return_value=SimpleNamespace(
                        as_capability=lambda: {
                            "available": True,
                            "note": "ready",
                            "build_id": "wda-xkey-20260803",
                            "build_expires_at_unix": 2_000_000_000,
                        }
                    ),
                ),
            ):
                capabilities = platform_support.runtime_capabilities()

        self.assertTrue(capabilities["database_key_extraction"])
        self.assertTrue(capabilities["database_key_manual_input"])
        self.assertTrue(capabilities["database_decryption"])
        self.assertTrue(capabilities["image_key_memory_scan"])
        self.assertTrue(capabilities["realtime_wcdb"])
        self.assertTrue(capabilities["account_archive_cross_platform"])

    def test_macos_realtime_capability_rejects_an_incomplete_native_core(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            native_root = Path(temp_dir)
            client = native_root / "libwechatdb_client.dylib"
            broker = native_root / "wechatdb_broker"
            manifest = native_root / "wechatdb_native_build.json"
            client.write_bytes(b"client")
            manifest.write_text("{}", encoding="utf-8")
            with (
                patch.object(platform_support, "current_platform", return_value="macos"),
                patch.object(platform, "machine", return_value="arm64"),
                patch.object(
                    platform_support,
                    "mac_native_core_paths",
                    return_value=(client, broker, manifest),
                ),
            ):
                capabilities = platform_support.runtime_capabilities()

        self.assertFalse(capabilities["realtime_wcdb"])
        self.assertIn("原生资源缺失", capabilities["realtime_wcdb_note"])

    def test_database_key_endpoint_invokes_private_helper_on_macos(self) -> None:
        class ConnectedRequest:
            async def is_disconnected(self) -> bool:
                return False

        with (
            patch.object(keys_router, "is_macos", return_value=True),
            patch.object(
                keys_router,
                "get_db_key_workflow",
                return_value={"db_key": "ab" * 32, "method": "macos_private_helper"},
            ) as workflow,
        ):
            result = asyncio.run(keys_router.get_wechat_db_key(ConnectedRequest()))

        self.assertEqual(result["status"], 0)
        self.assertEqual(result["data"]["method"], "macos_private_helper")
        self.assertEqual(workflow.call_args.kwargs["key_mode"], "macos_private_helper")
        self.assertIsNotNone(workflow.call_args.kwargs["cancel_event"])

    def test_macos_database_key_endpoint_redacts_unknown_internal_errors(self) -> None:
        class ConnectedRequest:
            async def is_disconnected(self) -> bool:
                return False

        secret_detail = "/Users/private/internal-state=do-not-leak"
        with (
            patch.object(keys_router, "is_macos", return_value=True),
            patch.object(
                keys_router,
                "get_db_key_workflow",
                side_effect=RuntimeError(secret_detail),
            ),
        ):
            result = asyncio.run(keys_router.get_wechat_db_key(ConnectedRequest()))

        self.assertEqual(result["status"], -1)
        self.assertEqual(result["data"]["error_code"], "INTERNAL_ERROR")
        self.assertNotIn(secret_detail, result["errmsg"])

    def test_macos_database_key_endpoint_redacts_unknown_timeout_details(self) -> None:
        class ConnectedRequest:
            async def is_disconnected(self) -> bool:
                return False

        secret_detail = "private://internal-state=do-not-leak"
        with (
            patch.object(keys_router, "is_macos", return_value=True),
            patch.object(
                keys_router,
                "get_db_key_workflow",
                side_effect=TimeoutError(secret_detail),
            ),
        ):
            result = asyncio.run(keys_router.get_wechat_db_key(ConnectedRequest()))

        self.assertEqual(result["status"], -1)
        self.assertEqual(result["data"]["error_code"], "TIMEOUT")
        self.assertNotIn(secret_detail, result["errmsg"])

    def test_database_key_service_uses_only_private_helper_on_macos(self) -> None:
        with (
            patch.object(key_service, "is_macos", return_value=True),
            patch(
                "wechat_decrypt_tool.macos_db_key_helper.capture_macos_database_key",
                return_value={"db_key": "cd" * 32, "method": "macos_private_helper"},
            ) as capture,
            patch.object(key_service, "_get_db_key_with_v4") as memory_scan,
            patch.object(key_service, "WeChatKeyFetcher") as hook_fetcher,
        ):
            result = key_service.get_db_key_workflow(
                db_storage_path="/tmp/wxid_demo/db_storage",
                key_mode="auto",
            )

        self.assertEqual(result["method"], "macos_private_helper")
        capture.assert_called_once()
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
