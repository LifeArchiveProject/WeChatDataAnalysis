import asyncio
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import sns  # noqa: E402  pylint: disable=wrong-import-position


class TestSnsMediaRouteWeFlowDefault(unittest.TestCase):
    def test_route_prefers_local_cache_before_remote(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            local_path = account_dir / "local.jpg"
            payload = b"\xff\xd8\xff\x00localjpeg"
            local_path.write_bytes(payload)

            with mock.patch("wechat_decrypt_tool.routers.sns._resolve_account_dir", return_value=account_dir):
                with mock.patch("wechat_decrypt_tool.routers.sns._resolve_account_wxid_dir", return_value=Path(td) / "wxid"):
                    with mock.patch("wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path", return_value=str(local_path)):
                        with mock.patch("wechat_decrypt_tool.routers.sns._read_and_maybe_decrypt_media", return_value=(payload, "image/jpeg")):
                            with mock.patch("wechat_decrypt_tool.routers.sns._try_fetch_and_decrypt_sns_remote") as remote:
                                resp = asyncio.run(
                                    sns.get_sns_media(
                                        account="acc",
                                        create_time=1,
                                        width=1,
                                        height=1,
                                        url="https://mmsns.qpic.cn/sns/test/0",
                                        key="123",
                                        token="tkn",
                                        use_cache=1,
                                    )
                                )

        remote.assert_not_called()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.body, payload)
        self.assertEqual(resp.headers.get("X-SNS-Source"), "local-cache")

    def test_route_falls_back_to_remote_when_local_cache_misses(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            remote_resp = sns.Response(content=b"remote", media_type="image/jpeg")
            remote_resp.headers["X-SNS-Source"] = "remote-decrypt"

            with mock.patch("wechat_decrypt_tool.routers.sns._resolve_account_dir", return_value=account_dir):
                with mock.patch("wechat_decrypt_tool.routers.sns._resolve_account_wxid_dir", return_value=Path(td) / "wxid"):
                    with mock.patch("wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path", return_value=None):
                        with mock.patch(
                            "wechat_decrypt_tool.routers.sns._try_fetch_and_decrypt_sns_remote",
                            return_value=remote_resp,
                        ) as remote:
                            resp = asyncio.run(
                                sns.get_sns_media(
                                    account="acc",
                                    create_time=1,
                                    width=1,
                                    height=1,
                                    url="https://mmsns.qpic.cn/sns/test/0",
                                    key="123",
                                    token="tkn",
                                    use_cache=1,
                                )
                            )

        remote.assert_called_once()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.body, b"remote")
        self.assertEqual(resp.headers.get("X-SNS-Source"), "remote-decrypt")


if __name__ == "__main__":
    unittest.main()
