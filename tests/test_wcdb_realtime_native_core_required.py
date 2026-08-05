import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_broker, native_core_client, native_core_realtime, wcdb_realtime
from wechat_decrypt_tool.native_core_client import (
    ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD,
    ENV_NATIVE_CORE_ENDPOINT,
    ENV_NATIVE_CORE_LIBRARY,
    ENV_NATIVE_CORE_MODE,
    ENV_SOURCE_NATIVE_CORE_DIR,
    NativeCoreComponentMissingError,
    NativeCoreProtocolError,
    NativeCoreUnavailableError,
)
from wechat_decrypt_tool.native_core_lease import ENV_LICENSE_TOKEN, ENV_LICENSE_URL


def _manifest(*, development: bool) -> dict[str, object]:
    if development:
        return {
            "schemaVersion": 2,
            "buildId": "dev-local",
            "developmentBuild": True,
            "offlineBootstrapFeatureBits": 0,
            "offlineExportSealFormat": "none",
            "codeSignatureEnforced": False,
            "rootPublicKeyCompiled": False,
            "testHooksEnabled": True,
            "stagingPinnedSignerTrust": False,
        }
    build_issued_at = int(time.time()) - 60
    return {
        "schemaVersion": 2,
        "buildId": "release-2026.07.27",
        "buildIssuedAtUnix": build_issued_at,
        "buildExpiresAtUnix": build_issued_at + 45 * 24 * 60 * 60,
        "developmentBuild": False,
        "offlineBootstrapFeatureBits": 3,
        "offlineExportSealFormat": "WES2",
        "codeSignatureEnforced": True,
        "rootPublicKeyCompiled": True,
        "testHooksEnabled": False,
        "stagingPinnedSignerTrust": False,
        "windowsClientSignerSha256": (b"h" * 32).hex(),
    }


def _write_runtime(root: Path, *, development: bool, include_broker: bool = True) -> None:
    (root / native_core_client._native_library_name()).write_bytes(b"client")
    if include_broker:
        (root / native_core_client._native_core_broker_name()).write_bytes(b"broker")
    (root / "wechatdb_native_build.json").write_text(
        json.dumps(_manifest(development=development)), encoding="utf-8"
    )


class TestWCDBRealtimeNativeCoreRequired(unittest.TestCase):
    def setUp(self) -> None:
        native_core_realtime.close_all()

    def tearDown(self) -> None:
        native_core_realtime.close_all()

    def test_native_core_mode_defaults_to_required_and_rejects_every_legacy_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(wcdb_realtime._native_core_mode_value(), "required")
        for value in ("off", "prefer", "off-by-mistake"):
            with self.subTest(value=value), patch.dict(
                os.environ, {ENV_NATIVE_CORE_MODE: value}, clear=True
            ):
                with self.assertRaisesRegex(NativeCoreProtocolError, "must be required"):
                    wcdb_realtime._native_core_mode_value()

    def test_source_entrypoint_locks_exact_dev_runtime_and_handshakes(self) -> None:
        with TemporaryDirectory() as td:
            runtime = Path(td)
            _write_runtime(runtime, development=True)
            legacy_names = native_core_client._LEGACY_WCDB_ENVIRONMENT
            legacy = {name: "legacy" for name in legacy_names}
            legacy[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD] = "1"
            with (
                patch.dict(os.environ, legacy, clear=True),
                patch.object(native_core_client.sys, "frozen", False, create=True),
                patch.object(
                    native_core_client,
                    "_native_core_entrypoint_directory",
                    return_value=runtime,
                ),
                patch.object(native_core_broker, "ensure_native_core_broker") as ensure,
                patch.object(native_core_broker, "stop_native_core_broker") as stop,
            ):
                selected = native_core_client.configure_native_core_entrypoint()

                self.assertEqual(selected.build_id, "dev-local")
                self.assertEqual(os.environ[ENV_NATIVE_CORE_MODE], "required")
                self.assertEqual(
                    os.environ[ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD], "1"
                )
                self.assertEqual(
                    Path(os.environ[ENV_NATIVE_CORE_LIBRARY]),
                    (runtime / native_core_client._native_library_name()).resolve(),
                )
                self.assertEqual(
                    Path(os.environ["WECHAT_TOOL_NATIVE_CORE_BROKER"]),
                    (runtime / native_core_client._native_core_broker_name()).resolve(),
                )
                for name in legacy_names:
                    self.assertNotIn(name, os.environ)
                ensure.assert_called_once_with(export_only=True)
                stop.assert_called_once_with(_force=True)

    def test_source_entrypoint_uses_bootstrap_runtime_directory(self) -> None:
        with TemporaryDirectory() as td:
            runtime = Path(td)
            (runtime / "libwechatdb_client.dylib").write_bytes(b"client")
            (runtime / "wechatdb_broker").write_bytes(b"broker")
            (runtime / "wechatdb_native_build.json").write_text(
                "{}", encoding="utf-8"
            )
            manifest = SimpleNamespace(development_build=False)

            with (
                patch.dict(
                    os.environ,
                    {ENV_SOURCE_NATIVE_CORE_DIR: str(runtime)},
                    clear=True,
                ),
                patch.object(native_core_client.sys, "frozen", False, create=True),
                patch.object(native_core_client.sys, "platform", "darwin"),
                patch.object(
                    native_core_client,
                    "_required_native_core_build_manifest",
                    return_value=manifest,
                ),
                patch.object(native_core_broker, "ensure_native_core_broker") as ensure,
                patch.object(native_core_broker, "stop_native_core_broker") as stop,
            ):
                selected = native_core_client.configure_native_core_entrypoint()

                self.assertIs(selected, manifest)
                self.assertEqual(
                    Path(os.environ[ENV_NATIVE_CORE_LIBRARY]),
                    (runtime / "libwechatdb_client.dylib").resolve(),
                )
                self.assertEqual(
                    Path(os.environ["WECHAT_TOOL_NATIVE_CORE_BROKER"]),
                    (runtime / "wechatdb_broker").resolve(),
                )
                ensure.assert_called_once_with(export_only=True)
                stop.assert_called_once_with(_force=True)

    def test_source_runtime_directory_environment_matches_desktop_bootstrap(self) -> None:
        desktop_contract = (ROOT / "desktop/src/native-core-path.cjs").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            f'const ENV_SOURCE_NATIVE_CORE_DIR = "{ENV_SOURCE_NATIVE_CORE_DIR}";',
            desktop_contract,
        )

    def test_entrypoint_rejects_legacy_mode_external_overrides_and_missing_triple(self) -> None:
        with patch.dict(os.environ, {ENV_NATIVE_CORE_MODE: "off"}, clear=True):
            with self.assertRaisesRegex(NativeCoreProtocolError, "must be required"):
                native_core_client.configure_native_core_entrypoint()

        with TemporaryDirectory() as td:
            runtime = Path(td)
            _write_runtime(runtime, development=True)
            for name in (
                ENV_NATIVE_CORE_LIBRARY,
                "WECHAT_TOOL_NATIVE_CORE_BROKER",
                ENV_NATIVE_CORE_ENDPOINT,
                "WECHAT_TOOL_NATIVE_CORE_TRUST_KEY_PATH",
            ):
                with self.subTest(name=name), patch.dict(
                    os.environ,
                    {
                        name: str(runtime / "external"),
                        ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1",
                    },
                    clear=True,
                ), patch.object(
                    native_core_client,
                    "_native_core_entrypoint_directory",
                    return_value=runtime,
                ):
                    with self.assertRaisesRegex(
                        NativeCoreProtocolError, "External .* overrides are disabled"
                    ):
                        native_core_client.configure_native_core_entrypoint()

        with TemporaryDirectory() as td:
            runtime = Path(td)
            _write_runtime(runtime, development=True, include_broker=False)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(
                    native_core_client,
                    "_native_core_entrypoint_directory",
                    return_value=runtime,
                ),
                self.assertRaises(NativeCoreComponentMissingError),
            ):
                native_core_client.configure_native_core_entrypoint()

    def test_source_and_frozen_manifest_profiles_cannot_be_swapped(self) -> None:
        cases = ((True, True, "requires a production"),)
        for frozen, development, error in cases:
            with self.subTest(frozen=frozen), TemporaryDirectory() as td:
                runtime = Path(td)
                _write_runtime(runtime, development=development)
                with (
                    patch.dict(
                        os.environ,
                        {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
                        clear=True,
                    ),
                    patch.object(native_core_client.sys, "frozen", frozen, create=True),
                    patch.object(
                        native_core_client,
                        "_native_core_entrypoint_directory",
                        return_value=runtime,
                    ),
                ):
                    with self.assertRaisesRegex(NativeCoreProtocolError, error):
                        native_core_client.configure_native_core_entrypoint()

        with TemporaryDirectory() as td:
            runtime = Path(td)
            _write_runtime(runtime, development=False)
            with (
                patch.dict(
                    os.environ,
                    {
                        ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                        ENV_LICENSE_TOKEN: "production-test-token",
                    },
                    clear=True,
                ),
                patch.object(native_core_client.sys, "frozen", True, create=True),
                patch.object(
                    native_core_client,
                    "_native_core_entrypoint_directory",
                    return_value=runtime,
                ),
                patch.object(native_core_broker, "ensure_native_core_broker") as ensure,
                patch.object(native_core_broker, "stop_native_core_broker") as stop,
            ):
                selected = native_core_client.configure_native_core_entrypoint()
                self.assertEqual(selected.build_id, "release-2026.07.27")
                self.assertNotIn(ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD, os.environ)
                ensure.assert_called_once_with(export_only=True)
                stop.assert_called_once_with(_force=True)

        with TemporaryDirectory() as td:
            runtime = Path(td)
            _write_runtime(runtime, development=False)
            with (
                patch.dict(
                    os.environ,
                    {
                        ENV_LICENSE_URL: "https://license.example.test/v1/leases",
                        ENV_LICENSE_TOKEN: "production-test-token",
                    },
                    clear=True,
                ),
                patch.object(native_core_client.sys, "frozen", False, create=True),
                patch.object(
                    native_core_client,
                    "_native_core_entrypoint_directory",
                    return_value=runtime,
                ),
                patch.object(native_core_broker, "ensure_native_core_broker") as ensure,
                patch.object(native_core_broker, "stop_native_core_broker") as stop,
            ):
                selected = native_core_client.configure_native_core_entrypoint()

            self.assertEqual(selected.build_id, "release-2026.07.27")
            ensure.assert_called_once_with(export_only=True)
            stop.assert_called_once_with(_force=True)

    def test_entrypoint_authorization_policy_fails_before_broker_start(self) -> None:
        cases = ((False, {}, "explicit .*ALLOW_DEVELOPMENT_BUILD=1"),)
        for frozen, environment, error in cases:
            with self.subTest(frozen=frozen, error=error), TemporaryDirectory() as td:
                runtime = Path(td)
                development = not frozen and not environment
                _write_runtime(runtime, development=development)
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch.object(native_core_client.sys, "frozen", frozen, create=True),
                    patch.object(
                        native_core_client,
                        "_native_core_entrypoint_directory",
                        return_value=runtime,
                    ),
                    patch.object(native_core_broker, "ensure_native_core_broker") as ensure,
                    patch.object(native_core_broker, "stop_native_core_broker") as stop,
                    self.assertRaisesRegex(NativeCoreProtocolError, error),
                ):
                    native_core_client.configure_native_core_entrypoint()
                ensure.assert_not_called()
                stop.assert_not_called()

    def test_failed_handshake_is_not_swallowed_and_is_cleaned_up(self) -> None:
        with TemporaryDirectory() as td:
            runtime = Path(td)
            _write_runtime(runtime, development=True)
            with (
                patch.dict(
                    os.environ,
                    {ENV_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD: "1"},
                    clear=True,
                ),
                patch.object(
                    native_core_client,
                    "_native_core_entrypoint_directory",
                    return_value=runtime,
                ),
                patch.object(
                    native_core_broker,
                    "ensure_native_core_broker",
                    side_effect=NativeCoreUnavailableError("handshake failed"),
                ),
                patch.object(native_core_broker, "stop_native_core_broker") as stop,
            ):
                with self.assertRaisesRegex(NativeCoreUnavailableError, "handshake failed"):
                    native_core_client.configure_native_core_entrypoint()
                stop.assert_called_once_with(_force=True)

    def test_real_server_entrypoints_enforce_native_core_before_serving(self) -> None:
        for relative_path in (
            "main.py",
            "src/wechat_decrypt_tool/backend_entry.py",
            "src/wechat_decrypt_tool/api.py",
        ):
            with self.subTest(relative_path=relative_path):
                source = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("configure_native_core_entrypoint()", source)

        backend = (ROOT / "src/wechat_decrypt_tool/backend_entry.py").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            backend.index("configure_native_core_entrypoint()"),
            backend.index("from wechat_decrypt_tool.api import app"),
        )
        api = (ROOT / "src/wechat_decrypt_tool/api.py").read_text(encoding="utf-8")
        self.assertIn("async def _startup_native_core()", api)
        self.assertLess(
            api.index("async def _startup_native_core()"),
            api.index("async def _startup_background_jobs()"),
        )
        self.assertIn("WCDB_REALTIME.start_background_prime()", api)
        self.assertIn("WCDB_REALTIME.stop_background_prime()", api)

    @staticmethod
    def _account_fixture(root: Path) -> tuple[Path, Path, Path]:
        account_dir = root / "wxid_demo_1234"
        db_storage = root / "source" / "db_storage"
        session_db = db_storage / "session" / "session.db"
        account_dir.mkdir(parents=True)
        session_db.parent.mkdir(parents=True)
        session_db.write_bytes(b"synthetic-session")
        return account_dir, db_storage, session_db

    def test_required_success_and_read_dispatch_never_touch_legacy_runtime(self) -> None:
        with TemporaryDirectory() as td:
            account_dir, db_storage, session_db = self._account_fixture(Path(td))
            manager = wcdb_realtime.WCDBRealtimeManager()

            def fake_query(_context, _database_path: Path, sql: str):
                if "native_core_probe" in sql:
                    return [{"native_core_probe": 1}]
                return []

            with (
                patch.dict(os.environ, {ENV_NATIVE_CORE_MODE: "required"}, clear=False),
                patch.object(
                    wcdb_realtime,
                    "_resolve_account_db_storage_dir",
                    return_value=db_storage,
                ),
                patch.object(
                    wcdb_realtime, "_resolve_session_db_path", return_value=session_db
                ),
                patch.object(
                    wcdb_realtime, "_derive_native_wxid", return_value="wxid_demo"
                ),
                patch.object(native_core_realtime, "_query", side_effect=fake_query),
            ):
                connection = manager.ensure_connected(
                    account_dir, key_hex="34" * 32, timeout=1.0
                )
                self.assertTrue(native_core_realtime.is_native_core_handle(connection.handle))

                with patch.object(
                    native_core_realtime,
                    "get_sessions",
                    return_value=[{"username": "wxid_friend"}],
                ) as native_sessions:
                    rows = wcdb_realtime.get_sessions(connection.handle)
                self.assertEqual(rows, [{"username": "wxid_friend"}])
                native_sessions.assert_called_once_with(connection.handle)

                manager.disconnect(account_dir.name)
                self.assertFalse(native_core_realtime.is_native_core_handle(connection.handle))

    def test_required_native_failure_never_falls_back_to_legacy_runtime(self) -> None:
        with TemporaryDirectory() as td:
            account_dir, db_storage, session_db = self._account_fixture(Path(td))
            manager = wcdb_realtime.WCDBRealtimeManager()

            with (
                patch.dict(os.environ, {ENV_NATIVE_CORE_MODE: "required"}, clear=False),
                patch.object(
                    wcdb_realtime,
                    "_resolve_account_db_storage_dir",
                    return_value=db_storage,
                ),
                patch.object(
                    wcdb_realtime, "_resolve_session_db_path", return_value=session_db
                ),
                patch.object(
                    wcdb_realtime, "_derive_native_wxid", return_value="wxid_demo"
                ),
                patch.object(
                    native_core_realtime,
                    "open_account",
                    side_effect=NativeCoreUnavailableError("native core unavailable"),
                ) as native_open,
            ):
                with self.assertRaisesRegex(
                    wcdb_realtime.WCDBRealtimeError, "native core unavailable"
                ):
                    manager.ensure_connected(account_dir, key_hex="45" * 32, timeout=1.0)

                native_open.assert_called_once()
                self.assertFalse(manager.is_connected(account_dir.name))
                self.assertNotIn(account_dir.name, manager._connecting)
                failure = manager.get_recent_failure(account_dir.name)
                self.assertTrue(failure.get("active"))
                self.assertIn("native core unavailable", str(failure.get("reason") or ""))

                with self.assertRaisesRegex(
                    wcdb_realtime.WCDBRealtimeError, "recently failed"
                ):
                    manager.ensure_connected(
                        account_dir, key_hex="45" * 32, timeout=1.0
                    )
                native_open.assert_called_once()

    def test_account_aliases_reuse_one_connection_for_the_same_database_root(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            first_dir = root / "wxid_demo"
            alias_dir = root / "wxid_demo_1234"
            db_storage = root / "source" / "db_storage"
            session_db = db_storage / "session" / "session.db"
            first_dir.mkdir()
            alias_dir.mkdir()
            session_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"synthetic-session")
            manager = wcdb_realtime.WCDBRealtimeManager()

            with (
                patch.object(
                    wcdb_realtime,
                    "_resolve_account_db_storage_dir",
                    return_value=db_storage,
                ),
                patch.object(
                    wcdb_realtime, "_resolve_session_db_path", return_value=session_db
                ),
                patch.object(
                    wcdb_realtime, "_derive_native_wxid", return_value="wxid_demo"
                ),
                patch.object(
                    wcdb_realtime.native_core_realtime,
                    "open_account",
                    return_value=1 << 60,
                ) as native_open,
                patch.object(wcdb_realtime, "_is_native_core_handle", return_value=True),
                patch.object(wcdb_realtime, "close_account") as native_close,
            ):
                first = manager.ensure_connected(first_dir, key_hex="56" * 32)
                alias = manager.ensure_connected(alias_dir, key_hex="56" * 32)

                self.assertIs(alias, first)
                self.assertIs(manager.get_connection(first_dir.name), first)
                self.assertIs(manager.get_connection(alias_dir.name), first)
                native_open.assert_called_once()

                manager.disconnect(alias_dir.name)
                native_close.assert_called_once_with(first.handle)
                self.assertIsNone(manager.get_connection(first_dir.name))
                self.assertIsNone(manager.get_connection(alias_dir.name))

    def test_background_prime_selects_direct_accounts_with_database_keys(self) -> None:
        manager = wcdb_realtime.WCDBRealtimeManager()
        accounts = [
            SimpleNamespace(
                name="wxid_ready",
                account_dir=Path("ready"),
                mode="direct",
                db_key_present=True,
            ),
            SimpleNamespace(
                name="wxid_no_key",
                account_dir=Path("no-key"),
                mode="direct",
                db_key_present=False,
            ),
            SimpleNamespace(
                name="wxid_decrypted",
                account_dir=Path("decrypted"),
                mode="decrypted",
                db_key_present=True,
            ),
        ]

        with (
            patch(
                "wechat_decrypt_tool.chat_accounts.list_chat_account_contexts",
                return_value=accounts,
            ),
            patch.object(manager, "ensure_connected") as ensure_connected,
        ):
            manager._prime_available_accounts_once()

        ensure_connected.assert_called_once_with(Path("ready"), timeout=30.0)

    def test_concurrent_alias_connections_share_one_native_open(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            first_dir = root / "wxid_demo"
            alias_dir = root / "wxid_demo_1234"
            db_storage = root / "source" / "db_storage"
            session_db = db_storage / "session" / "session.db"
            first_dir.mkdir()
            alias_dir.mkdir()
            session_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"synthetic-session")
            manager = wcdb_realtime.WCDBRealtimeManager()
            entered = threading.Event()
            alias_resolved = threading.Event()
            release = threading.Event()
            connections: list[wcdb_realtime.WCDBRealtimeConnection] = []
            errors: list[BaseException] = []

            def slow_open(**_kwargs):
                entered.set()
                if not release.wait(2.0):
                    raise AssertionError("concurrent alias did not reach the waiter")
                return 1 << 60

            def resolve_storage(account_dir: Path):
                if Path(account_dir).name == alias_dir.name:
                    alias_resolved.set()
                return db_storage

            def connect(account_dir: Path) -> None:
                try:
                    connections.append(
                        manager.ensure_connected(account_dir, key_hex="67" * 32)
                    )
                except BaseException as exc:
                    errors.append(exc)

            with (
                patch.object(
                    wcdb_realtime,
                    "_resolve_account_db_storage_dir",
                    side_effect=resolve_storage,
                ),
                patch.object(
                    wcdb_realtime, "_resolve_session_db_path", return_value=session_db
                ),
                patch.object(
                    wcdb_realtime, "_derive_native_wxid", return_value="wxid_demo"
                ),
                patch.object(
                    wcdb_realtime.native_core_realtime,
                    "open_account",
                    side_effect=slow_open,
                ) as native_open,
                patch.object(wcdb_realtime, "_is_native_core_handle", return_value=True),
                patch.object(wcdb_realtime, "close_account"),
            ):
                first = threading.Thread(target=connect, args=(first_dir,))
                alias = threading.Thread(target=connect, args=(alias_dir,))
                first.start()
                self.assertTrue(entered.wait(1.0))
                alias.start()
                self.assertTrue(alias_resolved.wait(1.0))
                release.set()
                first.join(2.0)
                alias.join(2.0)

                self.assertFalse(first.is_alive())
                self.assertFalse(alias.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(connections), 2)
                self.assertIs(connections[0], connections[1])
                native_open.assert_called_once()
                manager.close_all()


if __name__ == "__main__":
    unittest.main()
