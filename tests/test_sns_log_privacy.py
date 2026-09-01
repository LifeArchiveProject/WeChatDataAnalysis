import asyncio
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from fastapi import HTTPException

from wechat_decrypt_tool import sns_export_service, sns_media
from wechat_decrypt_tool import request_logging
from wechat_decrypt_tool.routers import sns as sns_router


def _render_calls(calls) -> str:
    rendered = []
    for item in calls:
        args = item.args
        if not args:
            continue
        try:
            rendered.append(str(args[0]) % tuple(args[1:]))
        except Exception:
            rendered.append(" ".join(str(value) for value in args))
    return "\n".join(rendered)


class TestSnsLogPrivacy(unittest.TestCase):
    def test_sns_server_exception_log_omits_exception_text_and_traceback(self):
        sentinel = "C:/private/account-sentinel/source.db"

        class _Url:
            path = "/api/sns/media"

        class _Request:
            method = "GET"
            url = _Url()

        async def fail(_request):
            raise RuntimeError(sentinel)

        fake_logger = mock.Mock()
        with self.assertRaises(RuntimeError):
            asyncio.run(request_logging.log_server_errors_middleware(fake_logger, _Request(), fail))

        logs = _render_calls(fake_logger.error.call_args_list)
        self.assertIn("code=sns_request_failed", logs)
        self.assertIn("error_type=RuntimeError", logs)
        self.assertNotIn(sentinel, logs)
        fake_logger.exception.assert_not_called()

    def test_remote_media_log_omits_all_user_and_derived_sentinels(self):
        sentinels = {
            "account": "privacy-account-sentinel",
            "nickname": "隐私昵称哨兵",
            "content": "朋友圈正文哨兵",
            "url": "https://private.example.test/secret/path?token=url-token-sentinel",
            "path": "C:/Users/private-user/朋友圈/private-file.jpg",
            "post": "post-id-sentinel",
            "media": "media-id-sentinel",
            "key": "key-sentinel-value",
            "token": "token-sentinel-value",
        }
        derived = {
            hashlib.sha256(value.encode("utf-8")).hexdigest()
            for value in sentinels.values()
        }

        with mock.patch.object(sns_media.logger, "info") as log_info:
            sns_media._sns_remote_diagnostic_log(
                "remote:download-error",
                url=sentinels["url"],
                diagnostic_id="diag-safe-1",
                key=sentinels["key"],
                token=sentinels["token"],
                error=RuntimeError(f"failed at {sentinels['path']} {sentinels['content']}"),
                account=sentinels["account"],
                nickname=sentinels["nickname"],
                postId=sentinels["post"],
                mediaId=sentinels["media"],
                candidatePath=sentinels["path"],
                responseSha256=next(iter(derived)),
                width=123,
                height=456,
                createTime=1234567890,
                statusCode=503,
            )

        logs = _render_calls(log_info.call_args_list)
        self.assertIn("diag-safe-1", logs)
        self.assertIn('"statusCode": 503', logs)
        self.assertIn('"errorType": "RuntimeError"', logs)
        for value in (*sentinels.values(), *derived):
            self.assertNotIn(value, logs)
        for forbidden_field in (
            "urlHost",
            "urlIdentity",
            "errorText",
            "candidatePath",
            "responseSha256",
            "postId",
            "mediaId",
            "width",
            "height",
            "createTime",
        ):
            self.assertNotIn(forbidden_field, logs)

    def test_incremental_unavailable_log_does_not_include_account_or_path(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "private-account-sentinel"
            account_dir.mkdir()
            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=account_dir),
                mock.patch.object(sns_router.WCDB_REALTIME, "get_status", return_value={}),
                mock.patch.object(sns_router.logger, "info") as log_info,
                mock.patch.object(sns_router.logger, "error") as log_error,
            ):
                with self.assertRaises(HTTPException):
                    sns_router.sync_sns_realtime_timeline_latest(account=account_dir.name)

        logs = _render_calls(log_info.call_args_list + log_error.call_args_list)
        self.assertIn("[sns.incremental-sync]", logs)
        self.assertIn("realtime_not_available", logs)
        self.assertNotIn(account_dir.name, logs)
        self.assertNotIn(str(account_dir), logs)

    def test_export_prefetch_failure_log_omits_url_and_exception_text(self):
        task = sns_export_service.SnsRemoteMediaTask(
            kind="image",
            url="https://private.example.test/media/url-sentinel",
            key="private-key-sentinel",
            token="private-token-sentinel",
        )

        async def fail_fetch(**_kwargs):
            raise RuntimeError("C:/private/path-sentinel")

        async def run(account_dir: Path):
            return await sns_export_service._prefetch_sns_remote_media(
                account_dir=account_dir,
                tasks=[task],
                use_cache=False,
                concurrency=1,
            )

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "account-sentinel"
            account_dir.mkdir()
            with (
                mock.patch.object(
                    sns_export_service,
                    "_try_fetch_and_decrypt_sns_image_remote",
                    side_effect=fail_fetch,
                ),
                mock.patch.object(sns_export_service.logger, "info") as log_info,
            ):
                result = asyncio.run(run(account_dir))

        self.assertEqual(result.failed, 1)
        logs = _render_calls(log_info.call_args_list)
        self.assertIn("error_type=RuntimeError", logs)
        for sentinel in (task.url, task.key, task.token, "C:/private/path-sentinel", account_dir.name):
            self.assertNotIn(sentinel, logs)


if __name__ == "__main__":
    unittest.main()
