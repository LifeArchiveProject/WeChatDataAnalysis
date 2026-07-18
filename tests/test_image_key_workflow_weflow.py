import asyncio
import sys
from pathlib import Path
from unittest import mock

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


import wechat_decrypt_tool.key_service as key_service
from wechat_decrypt_tool.image_key_resolver import (
    ImageKeyResolution,
    TemplateScanResult,
    V2Template,
    derive_image_keys,
)


def _encrypted_jpeg_block(aes_key: str) -> bytes:
    plaintext = b"\xff\xd8\xff" + (b"\x00" * 13)
    encryptor = Cipher(algorithms.AES(aes_key.encode("ascii")), modes.ECB()).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def _template_scan(tmp_path: Path, xor_key: int = 0x8A) -> TemplateScanResult:
    return TemplateScanResult(
        templates=(
            V2Template(
                path=tmp_path / "sample_t.dat",
                ciphertext=b"\x00" * 16,
                mtime_ns=1,
                tail_xor_key=xor_key,
            ),
        ),
        inferred_xor_key=xor_key,
        used_fallback=False,
        files_scanned=1,
    )


def test_verified_weflow_resolver_wins_and_persists_canonical_account(tmp_path: Path) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    wxid_dir.mkdir(parents=True)
    scan = _template_scan(tmp_path)
    resolution = ImageKeyResolution(
        code=138,
        wxid="wxid_demo",
        xor_key=0x8A,
        aes_key="1234567890abcdef",
        verified=True,
        template_path=scan.templates[0].path,
        inferred_xor_key=0x8A,
    )

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service, "get_account_keys_from_store", return_value={}
    ), mock.patch.object(
        key_service,
        "try_get_local_image_keys",
        side_effect=AssertionError("deterministic resolver should win before native extraction"),
    ), mock.patch.object(
        key_service, "parse_global_config", return_value={"wxid": "wxid_demo"}
    ), mock.patch.object(
        key_service, "scan_v2_templates", return_value=scan
    ), mock.patch.object(
        key_service, "resolve_local_image_key", return_value=resolution
    ) as resolver_mock, mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock, mock.patch.object(
        key_service,
        "fetch_and_save_remote_keys",
        new=mock.AsyncMock(side_effect=AssertionError("remote must not run")),
    ):
        result = asyncio.run(
            key_service.get_image_key_integrated_workflow(
                "wxid_demo", db_storage_path=str(wxid_dir / "db_storage")
            )
        )

    assert result["verified"] is True
    assert result["source"] == "weflow_local_verified"
    assert result["wxid"] == "wxid_demo_abcd"
    assert result["matched_wxid"] == "wxid_demo"
    assert result["xor_key"] == "0x8A"
    assert result["aes_key"] == "1234567890abcdef"
    assert resolver_mock.call_args.kwargs["template_scan"] is scan
    persisted = upsert_mock.call_args.kwargs
    assert persisted["account"] == "wxid_demo_abcd"
    assert set(persisted["aliases"]) == {"wxid_demo"}
    assert persisted["image_key_verified"] is True
    assert persisted["image_key_source"] == "weflow_local_verified"
    assert persisted["image_key_source_wxid_dir"] == str(wxid_dir)
    assert persisted["image_key_code"] == 138


def test_native_pair_is_accepted_only_after_v2_verification_for_custom_folder(tmp_path: Path) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "custom_account_abcd"
    wxid_dir.mkdir(parents=True)
    scan = _template_scan(tmp_path, xor_key=0xD0)
    native = {
        "wxid": "wxid_internal",
        "xor_key": "0xD0",
        "aes_key": "fedcba0987654321",
    }

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service, "get_account_keys_from_store", return_value={}
    ), mock.patch.object(
        key_service, "try_get_local_image_keys", return_value=[native]
    ), mock.patch.object(
        key_service, "parse_global_config", return_value={"wxid": "wxid_internal"}
    ), mock.patch.object(
        key_service, "scan_v2_templates", return_value=scan
    ), mock.patch.object(
        key_service, "verify_key_pair", return_value=True
    ) as verify_mock, mock.patch.object(
        key_service, "resolve_local_image_key", return_value=None
    ) as resolver_mock, mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock, mock.patch.object(
        key_service,
        "fetch_and_save_remote_keys",
        new=mock.AsyncMock(side_effect=AssertionError("remote must not run")),
    ):
        result = asyncio.run(
            key_service.get_image_key_integrated_workflow(
                "custom_account", db_storage_path=str(wxid_dir / "db_storage")
            )
        )

    resolver_mock.assert_called_once()
    verify_mock.assert_called_once_with(0xD0, "fedcba0987654321", scan, require_xor_match=True)
    assert result["source"] == "native_v2_verified"
    assert result["verified"] is True
    assert result["wxid"] == "custom_account_abcd"
    assert result["matched_wxid"] == "wxid_internal"
    persisted = upsert_mock.call_args.kwargs
    assert persisted["account"] == "custom_account_abcd"
    assert set(persisted["aliases"]) == {"wxid_internal"}


def test_unverified_native_name_match_does_not_persist_and_remote_is_last(tmp_path: Path) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    wxid_dir.mkdir(parents=True)
    empty_scan = TemplateScanResult(templates=(), inferred_xor_key=None, used_fallback=False, files_scanned=0)
    remote_result = {
        "wxid": "wxid_demo_abcd",
        "xor_key": "0x8A",
        "aes_key": "1234567890abcdef",
        "source": "remote_api",
        "verified": False,
    }

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service, "get_account_keys_from_store", return_value={}
    ), mock.patch.object(
        key_service,
        "try_get_local_image_keys",
        return_value=[{"wxid": "wxid_demo", "xor_key": "0x8A", "aes_key": "1234567890abcdef"}],
    ), mock.patch.object(
        key_service, "parse_global_config", return_value={"wxid": "wxid_demo"}
    ), mock.patch.object(
        key_service, "scan_v2_templates", return_value=empty_scan
    ), mock.patch.object(
        key_service, "resolve_local_image_key", return_value=None
    ), mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock, mock.patch.object(
        key_service, "fetch_and_save_remote_keys", new=mock.AsyncMock(return_value=remote_result)
    ) as remote_mock:
        result = asyncio.run(
            key_service.get_image_key_integrated_workflow(
                "wxid_demo", db_storage_path=str(wxid_dir / "db_storage")
            )
        )

    remote_mock.assert_awaited_once()
    upsert_mock.assert_not_called()
    assert result["source"] == "remote_api"
    assert result["verified"] is False


def test_verified_cache_bound_to_current_wxid_dir_skips_all_probes(tmp_path: Path) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    wxid_dir.mkdir(parents=True)
    cached = {
        "image_xor_key": "0x8A",
        "image_aes_key": "1234567890abcdef",
        "image_key_verified": True,
        "image_key_source": "weflow_local_verified",
        "image_key_source_wxid_dir": str(wxid_dir.resolve()),
        "image_key_derived_wxid": "wxid_demo",
        "image_key_code": 138,
    }
    empty_scan = TemplateScanResult(
        templates=(),
        inferred_xor_key=None,
        used_fallback=False,
        files_scanned=0,
    )

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service, "get_account_keys_from_store", return_value=cached
    ), mock.patch.object(
        key_service, "try_get_local_image_keys", side_effect=AssertionError("cache should win")
    ), mock.patch.object(
        key_service, "scan_v2_templates", return_value=empty_scan
    ), mock.patch.object(
        key_service,
        "fetch_and_save_remote_keys",
        new=mock.AsyncMock(side_effect=AssertionError("cache should win")),
    ):
        result = asyncio.run(
            key_service.get_image_key_integrated_workflow(
                "wxid_demo", db_storage_path=str(wxid_dir / "db_storage")
            )
        )

    assert result["source"] == "verified_cache"
    assert result["verified"] is True
    assert result["wxid"] == "wxid_demo_abcd"


def test_verified_derived_cache_is_rechecked_against_newest_template(tmp_path: Path) -> None:
    wxid = "wxid_demo"
    old_code = 100
    current_code = 200
    old_keys = derive_image_keys(old_code, wxid)
    current_keys = derive_image_keys(current_code, wxid)
    scan = TemplateScanResult(
        templates=(
            V2Template(
                path=tmp_path / "current_t.dat",
                ciphertext=_encrypted_jpeg_block(current_keys.aes_key),
                mtime_ns=2,
                tail_xor_key=current_keys.xor_key,
            ),
        ),
        inferred_xor_key=current_keys.xor_key,
        used_fallback=False,
        files_scanned=1,
    )
    stale_cache = {
        "matched_wxid": wxid,
        "xor_key": f"0x{old_keys.xor_key:02X}",
        "aes_key": old_keys.aes_key,
        "cached_source": "weflow_local_verified",
        "code": old_code,
    }
    current_cache = {
        **stale_cache,
        "xor_key": f"0x{current_keys.xor_key:02X}",
        "aes_key": current_keys.aes_key,
        "code": current_code,
    }

    assert not key_service._verified_image_key_cache_matches_templates(stale_cache, scan)
    assert key_service._verified_image_key_cache_matches_templates(current_cache, scan)


@pytest.mark.parametrize(
    "remote_payload",
    [
        {"xorKey": "not-a-key", "aesKey": "1234567890abcdef"},
        {"xorKey": "138", "aesKey": "too-short"},
        {"xorKey": "999", "aesKey": "1234567890abcdef"},
    ],
)
def test_remote_invalid_key_payload_is_never_persisted(
    tmp_path: Path,
    remote_payload: dict[str, str],
) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    (wxid_dir / "db_storage").mkdir(parents=True)

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return remote_payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service,
        "get_wechat_internal_global_config",
        side_effect=[b"global-config", b"crc"],
    ), mock.patch.object(
        key_service.httpx, "AsyncClient", FakeAsyncClient
    ), mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock:
        with pytest.raises(RuntimeError, match="不完整或格式无效"):
            asyncio.run(
                key_service.fetch_and_save_remote_keys(
                    "wxid_demo",
                    db_storage_path=str(wxid_dir / "db_storage"),
                )
            )

    upsert_mock.assert_not_called()
