import asyncio
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import keys as keys_router


def test_image_key_router_exposes_verified_source_metadata() -> None:
    workflow_result = {
        "wxid": "wxid_demo_abcd",
        "matched_wxid": "wxid_demo",
        "xor_key": "0x8A",
        "aes_key": "1234567890abcdef",
        "source": "weflow_local_verified",
        "verified": True,
        "code": 138,
    }
    with mock.patch.object(
        keys_router,
        "get_image_key_integrated_workflow",
        new=mock.AsyncMock(return_value=workflow_result),
    ):
        response = asyncio.run(keys_router.get_image_key(account="wxid_demo"))

    assert response["status"] == 0
    assert response["errmsg"] == "ok"
    assert response["data"]["verified"] is True
    assert response["data"]["source"] == "weflow_local_verified"
    assert response["data"]["matched_wxid"] == "wxid_demo"
    assert response["data"]["code"] == 138


def test_image_key_router_does_not_mark_unverified_remote_candidate_successful() -> None:
    workflow_result = {
        "wxid": "wxid_demo_abcd",
        "xor_key": "0x8A",
        "aes_key": "1234567890abcdef",
        "source": "remote_api",
        "verified": False,
    }
    with mock.patch.object(
        keys_router,
        "get_image_key_integrated_workflow",
        new=mock.AsyncMock(return_value=workflow_result),
    ):
        response = asyncio.run(keys_router.get_image_key(account="wxid_demo"))

    assert response["status"] == -2
    assert response["data"]["verified"] is False
    assert response["data"]["source"] == "remote_api"
    assert "缺少可用于本地验真的 V2 图片" in response["errmsg"]


def test_image_key_memory_router_returns_only_verified_metadata() -> None:
    workflow_result = {
        "wxid": "wxid_demo_abcd",
        "matched_wxid": "wxid_demo_abcd",
        "xor_key": "0x8A",
        "aes_key": "1234567890abcdef",
        "source": "memory_v2_verified",
        "verified": True,
        "pid": 4321,
        "encoding": "ascii",
    }
    request = keys_router.ImageKeyMemoryRequest(
        account="wxid_demo",
        db_storage_path=r"D:\xwechat_files\wxid_demo_abcd\db_storage",
    )
    with mock.patch.object(
        keys_router,
        "get_image_key_memory_workflow",
        new=mock.AsyncMock(return_value=workflow_result),
    ) as workflow_mock:
        response = asyncio.run(keys_router.get_image_key_memory(request))

    workflow_mock.assert_awaited_once_with(
        "wxid_demo",
        db_storage_path=r"D:\xwechat_files\wxid_demo_abcd\db_storage",
        wxid_dir=None,
    )
    assert response["status"] == 0
    assert response["errmsg"] == "ok"
    assert response["data"] == {
        "xor_key": "0x8A",
        "aes_key": "1234567890abcdef",
        "account": "wxid_demo_abcd",
        "matched_wxid": "wxid_demo_abcd",
        "source": "memory_v2_verified",
        "verified": True,
        "pid": 4321,
        "encoding": "ascii",
    }


def test_image_key_memory_router_reports_scan_miss_without_key_data() -> None:
    request = keys_router.ImageKeyMemoryRequest(account="wxid_demo")
    with mock.patch.object(
        keys_router,
        "get_image_key_memory_workflow",
        new=mock.AsyncMock(side_effect=RuntimeError("60 秒内未命中")),
    ):
        response = asyncio.run(keys_router.get_image_key_memory(request))

    assert response["status"] == -1
    assert response["data"] == {}
    assert "内存扫描失败" in response["errmsg"]
    assert "60 秒内未命中" in response["errmsg"]
