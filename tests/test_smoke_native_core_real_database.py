from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "smoke_native_core_real_database.py"
_SPEC = importlib.util.spec_from_file_location("wda_smoke_native_core_real_database", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
smoke = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(smoke)


class _FakeFunction:
    def __init__(self, implementation):
        self._implementation = implementation
        self.argtypes = None
        self.calls: list[tuple[object, ...]] = []

    def __call__(self, *args):
        self.calls.append(args)
        return self._implementation(*args)


class _FakeNCrypt:
    def __init__(self) -> None:
        self._next_provider = 100
        self._next_key = 200
        self.NCryptOpenStorageProvider = _FakeFunction(self._open_provider)
        self.NCryptOpenKey = _FakeFunction(self._open_key)
        self.NCryptDeleteKey = _FakeFunction(lambda _key, _flags: 0)
        self.NCryptFreeObject = _FakeFunction(lambda _handle: 0)

    def _open_provider(self, provider_pointer, _name, _flags) -> int:
        self._next_provider += 1
        provider_pointer._obj.value = self._next_provider
        return 0

    def _open_key(self, _provider, key_pointer, _name, _legacy_spec, _flags) -> int:
        self._next_key += 1
        key_pointer._obj.value = self._next_key
        return 0


def test_device_key_cleanup_does_not_use_silent_flag_for_deletion() -> None:
    ncrypt = _FakeNCrypt()
    with patch.object(smoke.sys, "platform", "win32"), patch.object(
        smoke.ctypes, "WinDLL", return_value=ncrypt, create=True
    ):
        smoke._delete_windows_device_key("LifeArchiveProject.WeChatDB.Native.Test")

    assert [call[-1] for call in ncrypt.NCryptOpenKey.calls] == [0x00000040, 0x00000040]
    assert [call[-1] for call in ncrypt.NCryptDeleteKey.calls] == [0, 0]


def test_authorization_profile_distinguishes_staging_from_production() -> None:
    with TemporaryDirectory() as td:
        manifest_path = Path(td) / "wechatdb_native_build.json"
        for development, staging_trust, expected in (
            (True, False, "development"),
            (False, True, "staging"),
            (False, False, "production"),
        ):
            manifest_path.write_text(
                json.dumps(
                    {
                        "developmentBuild": development,
                        "stagingPinnedSignerTrust": staging_trust,
                    }
                ),
                encoding="utf-8",
            )
            assert smoke._authorization_profile(manifest_path) == expected


def test_parent_allocated_temporary_root_is_removed_after_normal_exit(
    tmp_path: Path,
) -> None:
    temporary_root = tmp_path / "parent-owned" / "wda-smoke"

    with smoke._temporary_root(temporary_root) as active_root:
        assert active_root == temporary_root.resolve()
        (active_root / "artifact.bin").write_bytes(b"fixture")

    assert not temporary_root.exists()


def test_device_key_name_is_limited_to_ephemeral_smoke_namespace() -> None:
    valid = "LifeArchiveProject.WeChatDB.Native.RealSmoke." + "a" * 32
    assert smoke._device_key_name(valid) == valid

    try:
        smoke._device_key_name("LifeArchiveProject.WeChatDB.Native.Production")
    except RuntimeError as exc:
        assert str(exc) == (
            "Smoke device key name is outside the ephemeral test namespace."
        )
    else:
        raise AssertionError("non-ephemeral CNG key name was accepted")


def test_database_failure_marker_contains_only_hash_and_status(tmp_path: Path) -> None:
    storage = tmp_path / "SENSITIVE_ACCOUNT" / "db_storage"
    database = storage / "message" / "SENSITIVE_DATABASE.db"

    error = smoke.core.NativeCoreError("SENSITIVE_PATH", status=-15)
    marker = smoke._database_failure_marker(storage, database, error)

    assert marker.startswith("pathSha256=")
    assert marker.endswith(" status=-15")
    assert "SENSITIVE" not in marker
