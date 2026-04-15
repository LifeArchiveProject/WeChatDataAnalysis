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
    def test_route_stops_after_remote_miss_by_default(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("wechat_decrypt_tool.routers.sns._resolve_account_dir", return_value=account_dir):
                with mock.patch("wechat_decrypt_tool.routers.sns._try_fetch_and_decrypt_sns_remote", return_value=None):
                    with self.assertRaises(sns.HTTPException) as ctx:
                        asyncio.run(
                            sns.get_sns_media(
                                account="acc",
                                url="https://mmsns.qpic.cn/sns/test/0",
                                key="123",
                                token="tkn",
                                use_cache=1,
                            )
                        )

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
