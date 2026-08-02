import inspect
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool import native_core_realtime, wcdb_realtime


class TestWcdbRealtimeNativeFacade(unittest.TestCase):
    def test_legacy_dll_and_sidecar_runtime_are_absent(self) -> None:
        source = inspect.getsource(wcdb_realtime).lower()
        for marker in (
            "ctypes",
            "urllib",
            "sidecar",
            "wcdb_api.dll",
            "_ensure_initialized",
            "_load_wcdb_lib",
            "_validate_session_db_key",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, source)

        for symbol in (
            "WCDBSidecarUnavailableError",
            "_DEFAULT_WCDB_API_DLL",
            "_resolve_wcdb_api_dll_path",
            "_sidecar_call",
        ):
            with self.subTest(symbol=symbol):
                self.assertFalse(hasattr(wcdb_realtime, symbol))

    def test_open_account_delegates_with_inferred_native_context(self) -> None:
        with TemporaryDirectory() as td:
            storage = Path(td) / "wxid_demo_1234" / "db_storage"
            session_db = storage / "session" / "session.db"
            session_db.parent.mkdir(parents=True)
            session_db.write_bytes(b"synthetic-session")

            with patch.object(
                native_core_realtime, "open_account", return_value=123
            ) as native_open:
                handle = wcdb_realtime.open_account(
                    session_db, "12" * 32, timeout=0.01
                )

        self.assertEqual(handle, 123)
        native_open.assert_called_once_with(
            account="wxid_demo_1234",
            native_wxid="wxid_demo",
            db_storage_dir=storage.resolve(),
            session_db_path=session_db.resolve(),
            key_hex="12" * 32,
        )

    def test_facade_delegates_reads_without_transforming_results(self) -> None:
        cases = (
            ("get_sessions", (7,), {}, [{"username": "wxid_friend"}]),
            (
                "get_messages",
                (7, "wxid_friend"),
                {"limit": 8, "offset": 3},
                [{"local_id": 1}],
            ),
            ("get_message_count", (7, "wxid_friend"), {}, 42),
            (
                "get_display_names",
                (7, ["wxid_friend"]),
                {},
                {"wxid_friend": "Friend"},
            ),
            (
                "get_contacts_compact",
                (7, []),
                {},
                [{"username": "wxid_friend"}],
            ),
        )
        for name, args, kwargs, expected in cases:
            with self.subTest(name=name), patch.object(
                native_core_realtime, name, return_value=expected
            ) as delegated:
                actual = getattr(wcdb_realtime, name)(*args, **kwargs)
                self.assertEqual(actual, expected)
                delegated.assert_called_once_with(*args, **kwargs)

    def test_message_cursor_accepts_lite_but_does_not_forward_it(self) -> None:
        with patch.object(
            native_core_realtime, "open_message_cursor", return_value=321
        ) as native_open:
            cursor = wcdb_realtime.open_message_cursor(
                7,
                "wxid_friend",
                batch_size=100,
                ascending=True,
                begin_timestamp=1,
                end_timestamp=2,
                lite=True,
            )

        self.assertEqual(cursor, 321)
        native_open.assert_called_once_with(
            7,
            "wxid_friend",
            batch_size=100,
            ascending=True,
            begin_timestamp=1,
            end_timestamp=2,
        )

    def test_native_errors_are_exposed_as_facade_errors(self) -> None:
        with patch.object(
            native_core_realtime,
            "get_sessions",
            side_effect=native_core_realtime.NativeCoreRealtimeError("query failed"),
        ):
            with self.assertRaisesRegex(
                wcdb_realtime.WCDBRealtimeError,
                "Native core get sessions failed: query failed",
            ):
                wcdb_realtime.get_sessions(7)


if __name__ == "__main__":
    unittest.main()
