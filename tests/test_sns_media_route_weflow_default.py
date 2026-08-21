import asyncio
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import sns  # noqa: E402  pylint: disable=wrong-import-position


class TestSnsMediaRouteWeFlowDefault(unittest.TestCase):
    @staticmethod
    def _render_log_calls(log_info: mock.Mock) -> str:
        rendered: list[str] = []
        for item in log_info.call_args_list:
            args = item.args
            if not args:
                continue
            template = str(args[0])
            try:
                rendered.append(template % tuple(args[1:]))
            except Exception:
                rendered.append(" ".join(str(value) for value in args))
        return "\n".join(rendered)

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
        self.assertTrue(str(resp.headers.get("X-SNS-Diagnostic-Id") or "").startswith("sns-media-"))

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

    def test_heuristic_rejects_cache_files_far_from_post_time(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            wxid_dir = Path(td) / "wxid"
            account_dir.mkdir(parents=True, exist_ok=True)
            wxid_dir.mkdir(parents=True, exist_ok=True)

            # 旧动态附近没有缓存文件时，不得从多年后的缓存中按相同尺寸猜图。
            create_time = 1_531_913_605
            recent_cache_time = 1_787_146_219.0
            with mock.patch(
                "wechat_decrypt_tool.routers.sns._resolve_account_wxid_dir",
                return_value=wxid_dir,
            ):
                with mock.patch(
                    "wechat_decrypt_tool.routers.sns._sns_img_time_index",
                    return_value=([recent_cache_time], [str(wxid_dir / "unrelated-image")]),
                ):
                    with mock.patch(
                        "wechat_decrypt_tool.routers.sns._read_and_maybe_decrypt_media"
                    ) as decode:
                        resolved = sns._resolve_sns_cached_image_path(
                            account_dir_str=str(account_dir),
                            create_time=create_time,
                            width=1440,
                            height=1080,
                            idx=0,
                            total_size=108713,
                        )

        self.assertIsNone(resolved)
        decode.assert_not_called()

    def test_route_logs_redacted_identity_and_local_match_details(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            wxid_dir = Path(td) / "wxid_trace"
            account_dir.mkdir(parents=True, exist_ok=True)
            wxid_dir.mkdir(parents=True, exist_ok=True)
            local_path = account_dir / "matched-local.jpg"
            payload = b"\xff\xd8\xff\x00local-trace-payload"
            local_path.write_bytes(payload)

            with ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_account_dir",
                        return_value=account_dir,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_account_wxid_dir",
                        return_value=wxid_dir,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path_by_cache_key",
                        return_value=None,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path",
                        return_value=str(local_path),
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._read_and_maybe_decrypt_media",
                        return_value=(payload, "image/jpeg"),
                    )
                )
                remote = stack.enter_context(
                    mock.patch("wechat_decrypt_tool.routers.sns._try_fetch_and_decrypt_sns_remote")
                )
                log_info = stack.enter_context(mock.patch.object(sns.logger, "info"))

                resp = asyncio.run(
                    sns.get_sns_media(
                        account="acc",
                        create_time=1234567890,
                        width=640,
                        height=480,
                        total_size=len(payload),
                        idx=3,
                        post_id="post-42",
                        media_id="media-7",
                        post_type=1,
                        media_type=2,
                        url=(
                            "https://mmsns.qpic.cn/sns/identity/0"
                            "?token=url-secret-token&idx=4&foo=bar"
                        ),
                        key="super-secret-key",
                        token="super-secret-token",
                        use_cache=1,
                    )
                )

            logs = self._render_log_calls(log_info)

        remote.assert_not_called()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("sns.media request:start", logs)
        self.assertIn("sns.media local-key-post:probe", logs)
        self.assertIn("sns.media local-heuristic:probe", logs)
        self.assertIn('"matchedBy": "local-heuristic"', logs)
        self.assertIn('"candidatePath":', logs)
        self.assertIn("matched-local.jpg", logs)
        self.assertIn('"postId": "post-42"', logs)
        self.assertIn('"mediaId": "media-7"', logs)
        self.assertIn('"urlHost": "mmsns.qpic.cn"', logs)
        self.assertIn('"urlIdentity":', logs)
        self.assertIn('"tokenHash":', logs)
        self.assertIn('"keyHash":', logs)
        self.assertIn('"responseSha256":', logs)
        self.assertNotIn("super-secret-token", logs)
        self.assertNotIn("super-secret-key", logs)
        self.assertNotIn("url-secret-token", logs)

    def test_remote_wrapper_preserves_source_and_traces_result(self):
        payload = b"\x89PNG\r\n\x1a\n" + b"remote-payload"
        remote_result = sns._sns_media.SnsRemoteImageResult(
            payload=payload,
            media_type="image/png",
            source="remote-cache",
            x_enc="1",
            cache_path=Path("cache") / "remote.png",
        )
        trace = mock.Mock()

        with mock.patch.object(
            sns._sns_media,
            "try_fetch_and_decrypt_sns_image_remote",
            return_value=remote_result,
        ) as fetch:
            resp = asyncio.run(
                sns._try_fetch_and_decrypt_sns_remote(
                    account_dir=Path("account"),
                    url="https://mmsns.qpic.cn/sns/test/0",
                    key="secret-key",
                    token="secret-token",
                    use_cache=True,
                    trace=trace,
                    diagnostic_id="diag-123",
                    stage="remote-fallback",
                )
            )

        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertEqual(resp.headers.get("X-SNS-Source"), "remote-cache")
        self.assertEqual(resp.headers.get("X-SNS-Diagnostic-Id"), "diag-123")
        fetch.assert_awaited_once()
        self.assertEqual(fetch.await_args.kwargs["diagnostic_id"], "diag-123")
        trace.assert_any_call("remote-fallback:start", useCache=True)
        result_call = next(
            item for item in trace.call_args_list if item.args == ("remote-fallback:result",)
        )
        self.assertEqual(result_call.kwargs["result"], "remote-cache")
        self.assertEqual(result_call.kwargs["bytes"], len(payload))
        self.assertEqual(result_call.kwargs["cachePath"], str(Path("cache") / "remote.png"))

    def test_route_logs_exact_key_and_md5_match_strategies(self):
        cases = (
            ("local-key-post", ["MATCH"], None, None),
            ("local-key-media", [None, "MATCH"], None, None),
            ("local-md5", [None, None], "a" * 32, "MATCH"),
        )

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            wxid_dir = Path(td) / "wxid"
            local_path = account_dir / "exact.jpg"
            payload = b"\xff\xd8\xff\x00exact"
            account_dir.mkdir(parents=True, exist_ok=True)
            wxid_dir.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(payload)

            for expected_match, key_results, md5, md5_result in cases:
                with self.subTest(expected_match=expected_match):
                    resolved_key_results = [
                        str(local_path) if value == "MATCH" else value for value in key_results
                    ]
                    resolved_md5_result = str(local_path) if md5_result == "MATCH" else md5_result
                    with ExitStack() as stack:
                        stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._resolve_account_dir",
                                return_value=account_dir,
                            )
                        )
                        stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._resolve_account_wxid_dir",
                                return_value=wxid_dir,
                            )
                        )
                        stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path_by_cache_key",
                                side_effect=resolved_key_results,
                            )
                        )
                        stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path_by_md5",
                                return_value=resolved_md5_result,
                            )
                        )
                        heuristic = stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path",
                                return_value=None,
                            )
                        )
                        stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._read_and_maybe_decrypt_media",
                                return_value=(payload, "image/jpeg"),
                            )
                        )
                        remote = stack.enter_context(
                            mock.patch(
                                "wechat_decrypt_tool.routers.sns._try_fetch_and_decrypt_sns_remote"
                            )
                        )
                        log_info = stack.enter_context(mock.patch.object(sns.logger, "info"))

                        resp = asyncio.run(
                            sns.get_sns_media(
                                account="acc",
                                post_id="post-exact",
                                media_id="media-exact",
                                post_type=1,
                                media_type=2,
                                md5=md5,
                                use_cache=1,
                            )
                        )

                    logs = self._render_log_calls(log_info)
                    self.assertEqual(resp.status_code, 200)
                    self.assertIn(f'"matchedBy": "{expected_match}"', logs)
                    heuristic.assert_not_called()
                    remote.assert_not_called()

    def test_route_logs_final_not_found_with_diagnostic_id(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            with ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_account_dir",
                        return_value=account_dir,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_account_wxid_dir",
                        return_value=None,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._resolve_sns_cached_image_path",
                        return_value=None,
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "wechat_decrypt_tool.routers.sns._try_fetch_and_decrypt_sns_remote",
                        return_value=None,
                    )
                )
                log_info = stack.enter_context(mock.patch.object(sns.logger, "info"))

                with self.assertRaises(sns.HTTPException) as caught:
                    asyncio.run(
                        sns.get_sns_media(
                            account="acc",
                            create_time=1,
                            width=1,
                            height=1,
                            url="https://mmsns.qpic.cn/sns/missing/0",
                            use_cache=1,
                        )
                    )

            logs = self._render_log_calls(log_info)

        self.assertEqual(caught.exception.status_code, 404)
        diagnostic_id = str((caught.exception.headers or {}).get("X-SNS-Diagnostic-Id") or "")
        self.assertTrue(diagnostic_id.startswith("sns-media-"))
        self.assertIn("sns.media response:error", logs)
        self.assertIn('"result": "not-found"', logs)
        self.assertIn(f'"requestId": "{diagnostic_id}"', logs)


if __name__ == "__main__":
    unittest.main()
