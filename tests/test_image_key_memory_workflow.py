import asyncio
import sys
from pathlib import Path
from unittest import mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


import wechat_decrypt_tool.key_service as key_service
from wechat_decrypt_tool.image_key_memory_scan import MemoryImageKeyResolution


def _resolution(tmp_path: Path, *, verified: bool = True) -> MemoryImageKeyResolution:
    return MemoryImageKeyResolution(
        pid=4321,
        xor_key=0x8A,
        aes_key="1234567890abcdef",
        verified=verified,
        template_path=tmp_path / "sample_t.dat",
        encoding="utf-16le",
    )


def test_memory_workflow_persists_only_verified_pair_for_canonical_account(
    tmp_path: Path,
) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    wxid_dir.mkdir(parents=True)

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service, "scan_image_key_from_memory", return_value=_resolution(tmp_path)
    ) as scan_mock, mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock:
        result = asyncio.run(
            key_service.get_image_key_memory_workflow(
                "wxid_demo",
                db_storage_path=str(wxid_dir / "db_storage"),
            )
        )

    scan_mock.assert_called_once_with(wxid_dir, 60)
    assert result == {
        "wxid": "wxid_demo_abcd",
        "matched_wxid": "wxid_demo_abcd",
        "xor_key": "0x8A",
        "aes_key": "1234567890abcdef",
        "source": "memory_v2_verified",
        "verified": True,
        "code": None,
        "template_path": str(tmp_path / "sample_t.dat"),
        "pid": 4321,
        "encoding": "utf-16le",
    }
    persisted = upsert_mock.call_args.kwargs
    assert persisted["account"] == "wxid_demo_abcd"
    assert set(persisted["aliases"]) == {"wxid_demo"}
    assert persisted["image_xor_key"] == "0x8A"
    assert persisted["image_aes_key"] == "1234567890abcdef"
    assert persisted["image_key_verified"] is True
    assert persisted["image_key_source"] == "memory_v2_verified"
    assert persisted["image_key_source_wxid_dir"] == str(wxid_dir)


@pytest.mark.parametrize("resolution", [None, pytest.param("unverified", id="unverified")])
def test_memory_workflow_never_persists_missing_or_unverified_candidate(
    tmp_path: Path,
    resolution: object,
) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    wxid_dir.mkdir(parents=True)
    scan_result = _resolution(tmp_path, verified=False) if resolution == "unverified" else None

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service, "scan_image_key_from_memory", return_value=scan_result
    ), mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock:
        with pytest.raises(RuntimeError, match="V2 图片验真"):
            asyncio.run(key_service.get_image_key_memory_workflow("wxid_demo"))

    upsert_mock.assert_not_called()


def test_memory_workflow_bounds_the_background_scan_wait(tmp_path: Path) -> None:
    wxid_dir = tmp_path / "xwechat_files" / "wxid_demo_abcd"
    wxid_dir.mkdir(parents=True)

    async def never_finishes(*args, **kwargs):
        await asyncio.Future()

    async def run_with_safety_timeout():
        return await asyncio.wait_for(
            key_service.get_image_key_memory_workflow("wxid_demo", timeout=0.01),
            timeout=0.1,
        )

    with mock.patch.object(
        key_service, "_resolve_wxid_dir_for_image_key", return_value=wxid_dir
    ), mock.patch.object(
        key_service.asyncio, "to_thread", side_effect=never_finishes
    ), mock.patch.object(
        key_service, "upsert_account_keys_in_store"
    ) as upsert_mock:
        with pytest.raises(RuntimeError, match="V2 图片验真"):
            asyncio.run(run_with_safety_timeout())

    upsert_mock.assert_not_called()
