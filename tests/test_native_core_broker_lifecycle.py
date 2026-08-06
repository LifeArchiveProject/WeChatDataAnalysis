from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wechat_decrypt_tool import native_core_broker


def test_macos_broker_first_start_has_a_longer_default_budget() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(native_core_broker.sys, "platform", "darwin"),
    ):
        assert native_core_broker._startup_timeout_seconds() == 60.0

    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(native_core_broker.sys, "platform", "win32"),
    ):
        assert native_core_broker._startup_timeout_seconds() == 5.0


def test_broker_startup_timeout_environment_still_overrides_platform_default() -> None:
    with (
        patch.dict(
            os.environ,
            {native_core_broker.ENV_NATIVE_CORE_STARTUP_TIMEOUT_MS: "7000"},
            clear=True,
        ),
        patch.object(native_core_broker.sys, "platform", "darwin"),
    ):
        assert native_core_broker._startup_timeout_seconds() == 7.0


def test_broker_validates_controlled_distribution_against_client_artifact(
    tmp_path: Path,
) -> None:
    broker_path = tmp_path / "wechatdb_broker.exe"
    client_path = tmp_path / "wechatdb_client.dll"
    broker_path.write_bytes(b"broker")
    client_path.write_bytes(b"client")
    manifest = object()
    process = SimpleNamespace(poll=lambda: None)
    original = (
        native_core_broker._process,
        native_core_broker._owned_endpoint,
        native_core_broker._owned_database_roots,
        native_core_broker._owned_database_disabled,
        native_core_broker._active_operations,
    )
    try:
        native_core_broker._process = None
        native_core_broker._owned_endpoint = ""
        native_core_broker._owned_database_roots = ()
        native_core_broker._owned_database_disabled = False
        native_core_broker._active_operations = 0
        with (
            patch.object(
                native_core_broker,
                "resolve_native_core_broker",
                return_value=broker_path,
            ),
            patch.object(
                native_core_broker,
                "_required_native_core_build_manifest",
                return_value=manifest,
            ) as require_manifest,
            patch.object(native_core_broker, "_new_endpoint", return_value="test-endpoint"),
            patch.object(native_core_broker, "_resolve_broker_trust_key", return_value=""),
            patch.object(native_core_broker, "_broker_child_environment", return_value={}),
            patch.object(
                native_core_broker,
                "_broker_log_file",
                return_value=native_core_broker.subprocess.DEVNULL,
            ),
            patch.object(native_core_broker.subprocess, "Popen", return_value=process),
            patch.object(native_core_broker, "_wait_until_ready"),
            patch.object(native_core_broker, "close_native_core_client"),
            patch.object(native_core_broker, "_install_owned_environment"),
        ):
            assert native_core_broker.ensure_native_core_broker(export_only=True) == (
                "test-endpoint"
            )

        require_manifest.assert_called_once_with(client_path)
    finally:
        (
            native_core_broker._process,
            native_core_broker._owned_endpoint,
            native_core_broker._owned_database_roots,
            native_core_broker._owned_database_disabled,
            native_core_broker._active_operations,
        ) = original


def test_last_export_only_operation_stops_owned_broker() -> None:
    original = (
        native_core_broker._process,
        native_core_broker._owned_database_disabled,
        native_core_broker._active_operations,
    )
    try:
        native_core_broker._process = object()
        native_core_broker._owned_database_disabled = True
        native_core_broker._active_operations = 1
        operation = native_core_broker.NativeCoreManagedOperation("test-endpoint")

        with patch.object(native_core_broker, "stop_native_core_broker") as stop:
            operation.close()

        stop.assert_called_once_with()
        assert native_core_broker._active_operations == 0
    finally:
        (
            native_core_broker._process,
            native_core_broker._owned_database_disabled,
            native_core_broker._active_operations,
        ) = original
