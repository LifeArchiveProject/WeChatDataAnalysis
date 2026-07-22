import os
import sys
import threading
import unittest
import urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import wcdb_realtime


class TestWcdbRealtimeDllPathSelection(unittest.TestCase):
    def setUp(self) -> None:
        wcdb_realtime._WCDB_API_DLL_SELECTED = None

    def tearDown(self) -> None:
        wcdb_realtime._WCDB_API_DLL_SELECTED = None

    def test_resolve_rejects_external_native_library_override(self) -> None:
        self.assertTrue(wcdb_realtime._DEFAULT_WCDB_API_DLL.exists())
        with TemporaryDirectory() as td:
            external_library = Path(td) / wcdb_realtime._wcdb_native_relative_path().name
            external_library.write_bytes(b"external fixture")
            with patch.dict(
                os.environ,
                {"WECHAT_TOOL_WCDB_API_DLL_PATH": str(external_library)},
                clear=False,
            ):
                resolved = wcdb_realtime._resolve_wcdb_api_dll_path()

        self.assertEqual(
            resolved.resolve(),
            wcdb_realtime._DEFAULT_WCDB_API_DLL.resolve(),
        )

    def test_resolve_accepts_project_packaged_override(self) -> None:
        with TemporaryDirectory() as td:
            packaged_dll = (
                Path(td)
                / "backend"
                / "native"
                / wcdb_realtime._wcdb_native_relative_path()
            )
            packaged_dll.parent.mkdir(parents=True)
            packaged_dll.write_bytes(b"packaged fixture")
            with patch.dict(
                os.environ,
                {"WECHAT_TOOL_WCDB_API_DLL_PATH": str(packaged_dll)},
                clear=False,
            ):
                resolved = wcdb_realtime._resolve_wcdb_api_dll_path()

            self.assertEqual(resolved.resolve(), packaged_dll.resolve())

    def test_sidecar_transport_failure_does_not_claim_vc_runtime_is_missing(self) -> None:
        manager = wcdb_realtime.WCDBRealtimeManager()
        manager._conns["wxid_demo"] = wcdb_realtime.WCDBRealtimeConnection(
            account="wxid_demo",
            native_wxid="wxid_demo",
            handle=7,
            db_storage_dir=ROOT,
            session_db_path=ROOT / "session.db",
            connected_at=0.0,
            lock=threading.Lock(),
        )
        with (
            patch.dict(
                os.environ,
                {
                    "WECHAT_TOOL_WCDB_SIDECAR_URL": "http://127.0.0.1:65534",
                    "WECHAT_TOOL_WCDB_SIDECAR_TOKEN": "test-token",
                },
                clear=False,
            ),
            patch.object(
                wcdb_realtime.urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError(OSError(10061, "connection refused")),
            ),
            patch.object(wcdb_realtime.time, "sleep", return_value=None),
            patch.object(wcdb_realtime, "WCDB_REALTIME", manager),
        ):
            with self.assertRaises(wcdb_realtime.WCDBRealtimeError) as raised:
                wcdb_realtime._sidecar_call("get_sessions", {"handle": 1}, timeout=1.0)

        message = str(raised.exception)
        self.assertIn("WCDB sidecar unavailable", message)
        self.assertIn("辅助进程已退出或正在重启", message)
        self.assertNotIn("Visual C++ Redistributable", message)
        self.assertNotIn("latest-supported-vc-redist", message)
        self.assertIsInstance(raised.exception, wcdb_realtime.WCDBSidecarUnavailableError)
        self.assertFalse(manager.is_connected("wxid_demo"))

    def test_source_sidecar_requires_electron_runtime(self) -> None:
        with TemporaryDirectory() as td:
            repo_root = Path(td)
            sidecar_script = repo_root / "desktop" / "src" / "wcdb-sidecar.cjs"
            koffi_dir = repo_root / "desktop" / "vendor" / "koffi"
            sidecar_script.parent.mkdir(parents=True)
            koffi_dir.mkdir(parents=True)
            sidecar_script.write_text("", encoding="utf-8")

            with patch.object(wcdb_realtime, "_repo_root", return_value=repo_root):
                assets = wcdb_realtime._source_sidecar_assets()

        self.assertIsNone(assets)

    def test_session_db_key_mismatch_is_rejected_before_native_open(self) -> None:
        with TemporaryDirectory() as td:
            session_db = Path(td) / "session.db"
            session_db.write_bytes(b"encrypted-page".ljust(4096, b"\x00"))

            with patch.object(wcdb_realtime, "_ensure_initialized") as ensure_initialized:
                with self.assertRaises(wcdb_realtime.WCDBRealtimeError) as raised:
                    wcdb_realtime.open_account(session_db, "11" * 32)

        message = str(raised.exception)
        ensure_initialized.assert_not_called()
        self.assertIn("数据库密钥与当前 session.db 不匹配", message)
        self.assertIn("重新获取当前账号", message)
        self.assertNotIn("Visual C++ Redistributable", message)

    def test_key_mismatch_does_not_get_hidden_by_failure_cache(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_demo"
            db_storage = root / "source" / "db_storage"
            session_db = db_storage / "session" / "session.db"
            account_dir.mkdir(parents=True)
            session_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"encrypted-page".ljust(4096, b"\x00"))

            manager = wcdb_realtime.WCDBRealtimeManager()
            with patch.object(wcdb_realtime, "_resolve_account_db_storage_dir", return_value=db_storage):
                for _ in range(2):
                    with self.assertRaises(wcdb_realtime.WCDBRealtimeError) as raised:
                        manager.ensure_connected(account_dir, key_hex="45" * 32, timeout=3.0)
                    self.assertIn("数据库密钥与当前 session.db 不匹配", str(raised.exception))

        self.assertNotIn("wxid_demo", manager._failed)

    def test_session_db_key_preflight_accepts_matching_raw_key(self) -> None:
        from wechat_decrypt_tool.wechat_decrypt import _compute_page_hmac, _derive_mac_key

        key = bytes.fromhex("23" * 32)
        page = bytearray(b"salt-for-page-01" + b"\x5a" * (4096 - 16))
        page[-64:] = _compute_page_hmac(_derive_mac_key(key, bytes(page[:16])), bytes(page), 1)

        with TemporaryDirectory() as td:
            session_db = Path(td) / "session.db"
            session_db.write_bytes(bytes(page))
            mode = wcdb_realtime._validate_session_db_key(session_db, key.hex())

        self.assertEqual(mode, "raw_enc_key")

    def test_realtime_connection_reads_the_manually_saved_account_key(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_demo"
            db_storage = root / "source" / "db_storage"
            session_db = db_storage / "session" / "session.db"
            account_dir.mkdir(parents=True)
            session_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"fixture")
            manual_key = "67" * 32

            manager = wcdb_realtime.WCDBRealtimeManager()
            with (
                patch.object(
                    wcdb_realtime,
                    "get_account_keys_from_store",
                    return_value={"db_key": manual_key},
                ) as key_store,
                patch.object(
                    wcdb_realtime,
                    "_resolve_account_db_storage_dir",
                    return_value=db_storage,
                ),
                patch.object(wcdb_realtime, "_resolve_session_db_path", return_value=session_db),
                patch.object(wcdb_realtime, "open_account", return_value=77) as open_account,
                patch.object(wcdb_realtime, "set_my_wxid", return_value=True),
            ):
                connection = manager.ensure_connected(account_dir, timeout=3.0)

        key_store.assert_called_once_with("wxid_demo")
        self.assertEqual(open_account.call_args.args, (session_db, manual_key))
        self.assertEqual(connection.handle, 77)
        self.assertEqual(connection.db_storage_dir, db_storage)

    def test_inprocess_open_timeout_poison_runtime_without_vc_hint(self) -> None:
        release_open = threading.Event()
        original_poison = wcdb_realtime._inprocess_runtime_poisoned_reason

        def hanging_open(*_args, **_kwargs) -> int:
            release_open.wait(timeout=2.0)
            return 1

        try:
            with TemporaryDirectory() as td:
                root = Path(td)
                account_dir = root / "wxid_demo"
                db_storage = root / "source" / "db_storage"
                session_db = db_storage / "session" / "session.db"
                account_dir.mkdir(parents=True)
                session_db.parent.mkdir(parents=True)
                session_db.write_bytes(b"placeholder")

                manager = wcdb_realtime.WCDBRealtimeManager()
                with (
                    patch.object(wcdb_realtime, "_resolve_account_db_storage_dir", return_value=db_storage),
                    patch.object(wcdb_realtime, "open_account", side_effect=hanging_open),
                    patch.object(wcdb_realtime, "_sidecar_enabled", return_value=False),
                ):
                    with self.assertRaises(wcdb_realtime.WCDBRealtimeError) as raised:
                        manager.ensure_connected(account_dir, key_hex="34" * 32, timeout=0.05)

            message = str(raised.exception)
            self.assertIn("当前为进程内 WCDB", message)
            self.assertIn("原生调用无法安全终止", message)
            self.assertIn("npm ci", message)
            self.assertNotIn("Visual C++ Redistributable", message)
            self.assertTrue(wcdb_realtime._inprocess_runtime_poisoned_reason)
        finally:
            release_open.set()
            wcdb_realtime._inprocess_runtime_poisoned_reason = original_poison


if __name__ == "__main__":
    unittest.main()
