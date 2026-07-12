import asyncio
import hashlib
import sys
import threading
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import sns_export_service, sns_media  # noqa: E402  pylint: disable=wrong-import-position


class TestSnsMedia(unittest.TestCase):
    def test_html_export_refreshes_wcdb_before_first_timeline_read(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-wcdb-refresh",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "html",
                    "useCache": True,
                    "outputDir": str(root),
                    "fileName": "sns_wcdb_refresh.zip",
                },
            )
            events: list[str] = []

            def timeline(**_kwargs):
                events.append("timeline")
                return {"timeline": [], "hasMore": False}

            def disconnect(account: str):
                self.assertEqual(account, account_dir.name)
                events.append("disconnect")

            with mock.patch.object(
                sns_export_service,
                "_load_sns_users",
                return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 0}],
            ):
                with mock.patch.object(sns_export_service, "list_sns_timeline", side_effect=timeline):
                    with mock.patch.object(sns_export_service.WCDB_REALTIME, "disconnect", side_effect=disconnect):
                        output = manager._run_job(job, account_dir)

            self.assertTrue(output.exists())
            self.assertEqual(events, ["disconnect", "timeline"])

    def test_prefetch_refreshes_thumbnail_cached_for_original_task(self):
        def png_header(width: int, height: int) -> bytes:
            return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big")

        task = sns_export_service.SnsRemoteMediaTask(
            kind="image",
            url="https://mmsns.qpic.cn/sns/original/0",
            key="image-key",
            token="image-token",
            expected_width=1920,
            expected_height=1080,
            require_original=True,
        )
        cached_thumbnail = sns_media.SnsRemoteImageResult(
            payload=png_header(480, 270),
            media_type="image/png",
            source="remote-cache",
        )
        downloaded_original = sns_media.SnsRemoteImageResult(
            payload=png_header(1920, 1080),
            media_type="image/png",
            source="remote",
        )

        with TemporaryDirectory() as td:
            with mock.patch.object(
                sns_export_service,
                "_get_cached_sns_remote_image",
                return_value=cached_thumbnail,
            ):
                with mock.patch.object(
                    sns_export_service,
                    "_try_fetch_and_decrypt_sns_image_remote",
                    return_value=downloaded_original,
                ) as fetch:
                    result = asyncio.run(
                        sns_export_service._prefetch_sns_remote_media(
                            account_dir=Path(td),
                            tasks=[task],
                            use_cache=True,
                            concurrency=1,
                        )
                    )

        self.assertEqual(result.cached, 0)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 0)
        fetch.assert_awaited_once()
        self.assertFalse(fetch.await_args.kwargs["use_cache"])

    def test_prefetch_sns_remote_media_deduplicates_and_limits_concurrency(self):
        active = 0
        max_active = 0
        calls: list[tuple[str, str]] = []
        clients: set[int] = set()
        guard = threading.Lock()

        async def fake_fetch_image(**kwargs):
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(max_active, active)
                calls.append(("image", str(kwargs.get("url") or "")))
                clients.add(id(kwargs.get("client")))
            await asyncio.sleep(0.02)
            with guard:
                active -= 1
            return object()

        async def fake_fetch_video(**kwargs):
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(max_active, active)
                calls.append(("video", str(kwargs.get("url") or "")))
                clients.add(id(kwargs.get("client")))
            await asyncio.sleep(0.02)
            with guard:
                active -= 1
            return Path("cached.mp4")

        tasks = [
            sns_export_service.SnsRemoteMediaTask(kind="image", url=f"https://mmsns.qpic.cn/sns/{i}/0", key=str(i), token="")
            for i in range(6)
        ]
        tasks.extend(
            sns_export_service.SnsRemoteMediaTask(
                kind="video",
                url=f"https://snsvideodownload.video.qq.com/{i}.mp4",
                key=str(i),
                token="",
            )
            for i in range(3)
        )
        tasks.append(tasks[0])

        with TemporaryDirectory() as td:
            with mock.patch.object(sns_export_service, "_get_cached_sns_remote_image", return_value=None):
                with mock.patch.object(sns_export_service, "_get_cached_sns_remote_video", return_value=None):
                    with mock.patch.object(
                        sns_export_service,
                        "_try_fetch_and_decrypt_sns_image_remote",
                        side_effect=fake_fetch_image,
                    ):
                        with mock.patch.object(
                            sns_export_service,
                            "_materialize_sns_remote_video",
                            side_effect=fake_fetch_video,
                        ):
                            result = asyncio.run(
                                sns_export_service._prefetch_sns_remote_media(
                                    account_dir=Path(td),
                                    tasks=tasks,
                                    use_cache=True,
                                    concurrency=5,
                                )
                            )

        self.assertEqual(result.total, 9)
        self.assertEqual(result.succeeded, 9)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(calls), 9)
        self.assertEqual(max_active, 5)
        self.assertEqual(len(clients), 1)
        self.assertNotIn(id(None), clients)

    def test_remote_image_download_does_not_retry_bad_request(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400, request=request)

        async def run() -> None:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(httpx.HTTPStatusError):
                    await sns_media._download_sns_remote_bytes(
                        "https://wxapp.tc.qq.com/stale",
                        client=client,
                    )

        asyncio.run(run())
        self.assertEqual(calls, 1)

    def test_remote_image_download_does_not_retry_forbidden(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(403, request=request)

        async def run() -> None:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(httpx.HTTPStatusError):
                    await sns_media._download_sns_remote_bytes(
                        "https://mmsns.qpic.cn/sns/retry/0",
                        client=client,
                    )

        asyncio.run(run())
        self.assertEqual(calls, 1)

    def test_prefetch_sns_remote_media_skips_exact_remote_cache_hits(self):
        image_task = sns_export_service.SnsRemoteMediaTask(
            kind="image",
            url="https://mmsns.qpic.cn/sns/cached/0",
            key="image-key",
            token="",
        )
        video_task = sns_export_service.SnsRemoteMediaTask(
            kind="video",
            url="https://snsvideodownload.video.qq.com/cached.mp4",
            key="video-key",
            token="",
        )

        with TemporaryDirectory() as td:
            with mock.patch.object(sns_export_service, "_get_cached_sns_remote_image", return_value=object()):
                with mock.patch.object(sns_export_service, "_get_cached_sns_remote_video", return_value=Path("cached.mp4")):
                    with mock.patch.object(sns_export_service, "_try_fetch_and_decrypt_sns_image_remote") as image_fetch:
                        with mock.patch.object(sns_export_service, "_materialize_sns_remote_video") as video_fetch:
                            result = asyncio.run(
                                sns_export_service._prefetch_sns_remote_media(
                                    account_dir=Path(td),
                                    tasks=[image_task, video_task],
                                    use_cache=True,
                                    concurrency=5,
                                )
                            )

        self.assertEqual(result.total, 2)
        self.assertEqual(result.cached, 2)
        self.assertEqual(result.succeeded, 0)
        image_fetch.assert_not_called()
        video_fetch.assert_not_called()

    def test_collect_sns_remote_media_tasks_prefers_original_and_keeps_video_tasks(self):
        posts = [
            {
                "id": "post-1",
                "media": [
                    {
                        "id": "local-image",
                        "type": 2,
                        "url": "https://mmsns.qpic.cn/sns/local/original",
                        "thumb": "https://mmsns.qpic.cn/sns/local/thumb",
                        "urlAttrs": {"key": "local-original-key", "token": "local-original-token"},
                        "thumbAttrs": {"key": "local-thumb-key", "token": "local-thumb-token"},
                    },
                    {
                        "id": "remote-image",
                        "type": 2,
                        "url": "https://mmsns.qpic.cn/sns/remote/original",
                        "thumb": "https://mmsns.qpic.cn/sns/remote/thumb",
                        "urlAttrs": {"key": "remote-original-key", "token": "remote-original-token"},
                        "thumbAttrs": {"key": "remote-thumb-key", "token": "remote-thumb-token"},
                        "livePhoto": {
                            "url": "https://snsvideodownload.video.qq.com/live.mp4?token=live-video-token&idx=1",
                            "key": "live-key",
                        },
                    },
                    {
                        "id": "local-video",
                        "type": 6,
                        "thumb": "https://mmsns.qpic.cn/sns/poster/0",
                        "url": "https://snsvideodownload.video.qq.com/local.mp4",
                        "videoKey": "local-video-key",
                    },
                    {
                        "id": "remote-video",
                        "type": 6,
                        "url": "https://snsvideodownload.video.qq.com/remote.mp4",
                        "videoKey": "remote-video-key",
                        "urlAttrs": {"token": "remote-video-token"},
                    },
                ],
            }
        ]

        def fake_local_image(**kwargs):
            media = kwargs.get("media") or {}
            return Path("local.jpg") if media.get("id") in {"local-image", "local-video"} else None

        def fake_local_video(_wxid_dir, _post_id, media_id):
            return Path("local.mp4") if media_id == "local-video" else None

        with mock.patch.object(
            sns_export_service,
            "_resolve_sns_exact_cached_image_path",
            side_effect=fake_local_image,
        ):
            with mock.patch.object(
                sns_export_service,
                "_resolve_sns_cached_video_path",
                side_effect=fake_local_video,
            ):
                tasks = sns_export_service._collect_sns_remote_media_tasks(
                    wxid_dir=Path("wxid"),
                    posts=posts,
                    use_cache=True,
                )

        self.assertEqual(
            [(task.kind, task.url, task.key, task.token) for task in tasks],
            [
                (
                    "image",
                    "https://mmsns.qpic.cn/sns/local/original",
                    "local-original-key",
                    "local-original-token",
                ),
                (
                    "image",
                    "https://mmsns.qpic.cn/sns/remote/original",
                    "remote-original-key",
                    "remote-original-token",
                ),
                (
                    "video",
                    "https://snsvideodownload.video.qq.com/live.mp4?token=live-video-token&idx=1",
                    "live-key",
                    "",
                ),
                (
                    "video",
                    "https://snsvideodownload.video.qq.com/remote.mp4",
                    "remote-video-key",
                    "remote-video-token",
                ),
            ],
        )
        live_task = next(task for task in tasks if task.url.endswith("token=live-video-token&idx=1"))
        self.assertIn(
            "token=live-video-token",
            sns_export_service._fix_sns_cdn_url(live_task.url, token=live_task.token, is_video=True),
        )
        self.assertNotIn("remote-original-token", live_task.url)

    def test_html_export_does_not_retry_failed_prefetch_serially(self):
        async def failed_fetch(**_kwargs):
            return None

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-prefetch-once",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "html",
                    "useCache": False,
                    "outputDir": str(root),
                    "fileName": "sns_prefetch_once.zip",
                },
            )
            post = {
                "id": "post-1",
                "username": "wxid_alice",
                "media": [
                    {
                        "id": "media-1",
                        "type": 2,
                        "url": "https://mmsns.qpic.cn/sns/missing/0",
                        "key": "image-key",
                    }
                ],
                "likes": [],
                "comments": [],
            }

            with mock.patch.object(
                sns_export_service,
                "_load_sns_users",
                return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 1}],
            ):
                with mock.patch.object(
                    sns_export_service,
                    "list_sns_timeline",
                    return_value={"timeline": [post], "hasMore": False},
                ):
                    with mock.patch.object(
                        sns_export_service,
                        "_try_fetch_and_decrypt_sns_image_remote",
                        side_effect=failed_fetch,
                    ) as fetch:
                        output = manager._run_job(job, account_dir)
                        self.assertTrue(output.exists())

        fetch.assert_awaited_once()
        self.assertEqual(job.progress.media_prepare_total, 1)
        self.assertEqual(job.progress.media_prepared, 1)

    def test_html_export_stores_already_compressed_media_without_deflate(self):
        async def fetched_image(**_kwargs):
            return sns_media.SnsRemoteImageResult(
                payload=b"\xff\xd8\xff\x00jpeg-payload",
                media_type="image/jpeg",
                source="remote",
            )

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-media-stored",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "html",
                    "useCache": False,
                    "outputDir": str(root),
                    "fileName": "sns_media_stored.zip",
                },
            )
            post = {
                "id": "post-1",
                "username": "wxid_alice",
                "media": [
                    {
                        "id": "media-1",
                        "type": 2,
                        "url": "https://mmsns.qpic.cn/sns/image/0",
                        "key": "image-key",
                    }
                ],
                "likes": [],
                "comments": [],
            }

            with mock.patch.object(
                sns_export_service,
                "_load_sns_users",
                return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 1}],
            ):
                with mock.patch.object(
                    sns_export_service,
                    "list_sns_timeline",
                    return_value={"timeline": [post], "hasMore": False},
                ):
                    with mock.patch.object(
                        sns_export_service,
                        "_try_fetch_and_decrypt_sns_image_remote",
                        side_effect=fetched_image,
                    ):
                        output = manager._run_job(job, account_dir)

            with zipfile.ZipFile(output) as archive:
                media_entries = [item for item in archive.infolist() if item.filename.startswith("media/images/")]

            self.assertEqual(len(media_entries), 1)
            self.assertEqual(media_entries[0].compress_type, zipfile.ZIP_STORED)

    def test_html_export_video_has_controls_instead_of_autoplay(self):
        async def no_remote_image(**_kwargs):
            return None

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            video_path = root / "local.mp4"
            video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42video-payload")
            poster_path = root / "poster.jpg"
            poster_path.write_bytes(b"\xff\xd8\xff\x00poster-payload")

            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-video-controls",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "html",
                    "useCache": True,
                    "outputDir": str(root),
                    "fileName": "sns_video_controls.zip",
                },
            )
            post = {
                "id": "post-video",
                "username": "wxid_alice",
                "media": [
                    {
                        "id": "media-video",
                        "type": 6,
                        "url": "https://snsvideodownload.video.qq.com/video.mp4",
                        "videoKey": "video-key",
                    }
                ],
                "likes": [],
                "comments": [],
            }

            with mock.patch.object(
                sns_export_service,
                "_load_sns_users",
                return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 1}],
            ):
                with mock.patch.object(sns_export_service, "_resolve_account_wxid_dir", return_value=account_dir):
                    with mock.patch.object(
                        sns_export_service,
                        "list_sns_timeline",
                        return_value={"timeline": [post], "hasMore": False},
                    ):
                        with mock.patch.object(
                            sns_export_service,
                            "_resolve_sns_cached_video_path",
                            return_value=video_path,
                        ):
                            with mock.patch.object(
                                sns_export_service,
                                "_resolve_sns_exact_cached_image_path",
                                return_value=poster_path,
                            ):
                                with mock.patch.object(
                                    sns_export_service,
                                    "_try_fetch_and_decrypt_sns_image_remote",
                                    side_effect=no_remote_image,
                                ):
                                    output = manager._run_job(job, account_dir)

            with zipfile.ZipFile(output) as archive:
                page_name = next(name for name in archive.namelist() if name.startswith("sns_") and name.endswith(".html"))
                page = archive.read(page_name).decode("utf-8")

            self.assertIn("<video", page)
            self.assertIn(" controls", page)
            self.assertIn('preload="metadata"', page)
            self.assertNotIn(" autoplay", page)
            self.assertNotIn(" loop", page)
            self.assertNotIn(" muted", page)

    def test_html_export_prefers_downloaded_original_over_local_thumbnail(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            original_path = root / "original.jpg"
            original_payload = b"\xff\xd8\xff\x00original-image-payload"
            original_path.write_bytes(original_payload)
            thumbnail_path = root / "thumbnail.jpg"
            thumbnail_path.write_bytes(b"\xff\xd8\xff\x00thumbnail-payload")

            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-original-image",
                account=account_dir.name,
                options={
                    "scope": "selected",
                    "usernames": ["wxid_alice"],
                    "format": "html",
                    "useCache": True,
                    "outputDir": str(root),
                    "fileName": "sns_original_image.zip",
                },
            )
            media = {
                "id": "media-image",
                "type": 2,
                "url": "https://mmsns.qpic.cn/sns/image/original",
                "thumb": "https://mmsns.qpic.cn/sns/image/thumb",
                "urlAttrs": {"key": "original-key", "token": "original-token"},
                "thumbAttrs": {"key": "thumb-key", "token": "thumb-token"},
            }
            post = {
                "id": "post-image",
                "username": "wxid_alice",
                "media": [media],
                "likes": [],
                "comments": [],
            }

            async def prefetched_original(**kwargs):
                tasks = kwargs.get("tasks") or []
                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0].url, media["url"])
                task_id = sns_export_service._sns_remote_media_task_id(tasks[0])
                return sns_export_service.SnsRemoteMediaPrefetchResult(
                    total=1,
                    succeeded=1,
                    results={
                        task_id: sns_export_service.SnsPrefetchedImage(
                            cache_path=original_path,
                            media_type="image/jpeg",
                        )
                    },
                )

            with mock.patch.object(
                sns_export_service,
                "_load_sns_users",
                return_value=[{"username": "wxid_alice", "displayName": "Alice", "postCount": 1}],
            ):
                with mock.patch.object(sns_export_service, "_resolve_account_wxid_dir", return_value=account_dir):
                    with mock.patch.object(
                        sns_export_service,
                        "list_sns_timeline",
                        return_value={"timeline": [post], "hasMore": False},
                    ):
                        with mock.patch.object(
                            sns_export_service,
                            "_resolve_sns_exact_cached_image_path",
                            return_value=thumbnail_path,
                        ):
                            with mock.patch.object(
                                sns_export_service,
                                "_prefetch_sns_remote_media",
                                side_effect=prefetched_original,
                            ):
                                output = manager._run_job(job, account_dir)

            with zipfile.ZipFile(output) as archive:
                media_entries = [name for name in archive.namelist() if name.startswith("media/images/")]
                self.assertEqual(len(media_entries), 1)
                self.assertEqual(archive.read(media_entries[0]), original_payload)

    def test_html_export_prefetches_multiple_users_in_one_global_queue(self):
        active = 0
        max_active = 0
        both_started = asyncio.Event()

        async def fetched_image(**kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if active == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1.0)
            active -= 1
            return sns_media.SnsRemoteImageResult(
                payload=b"\xff\xd8\xff\x00jpeg-payload",
                media_type="image/jpeg",
                source="remote",
            )

        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "wxid_test"
            account_dir.mkdir()
            manager = sns_export_service.SnsExportManager()
            job = sns_export_service.ExportJob(
                export_id="sns-global-prefetch",
                account=account_dir.name,
                options={
                    "scope": "all",
                    "usernames": [],
                    "format": "html",
                    "useCache": False,
                    "outputDir": str(root),
                    "fileName": "sns_global_prefetch.zip",
                },
            )
            users = [
                {"username": "wxid_alice", "displayName": "Alice", "postCount": 1},
                {"username": "wxid_bob", "displayName": "Bob", "postCount": 1},
            ]

            def timeline(**kwargs):
                username = str(kwargs.get("usernames") or "")
                return {
                    "timeline": [
                        {
                            "id": f"post-{username}",
                            "username": username,
                            "media": [
                                {
                                    "id": f"media-{username}",
                                    "type": 2,
                                    "url": f"https://mmsns.qpic.cn/sns/{username}/0",
                                    "key": username,
                                }
                            ],
                            "likes": [],
                            "comments": [],
                        }
                    ],
                    "hasMore": False,
                }

            with mock.patch.object(sns_export_service, "_load_sns_users", return_value=users):
                with mock.patch.object(sns_export_service, "list_sns_timeline", side_effect=timeline):
                    with mock.patch.object(
                        sns_export_service,
                        "_try_fetch_and_decrypt_sns_image_remote",
                        side_effect=fetched_image,
                    ):
                        output = manager._run_job(job, account_dir)

            self.assertTrue(output.exists())
            self.assertEqual(max_active, 2)

    def test_weflow_wxisaac64_script_path_uses_bundled_helper(self):
        sns_media._weflow_wxisaac64_script_path.cache_clear()
        script = sns_media._weflow_wxisaac64_script_path()
        self.assertTrue(script)

        script_path = Path(script)
        normalized = script.replace("\\", "/")
        self.assertTrue(script_path.exists())
        self.assertEqual(script_path.name, "weflow_wasm_keystream.js")
        self.assertIn("/src/wechat_decrypt_tool/native/weflow_wasm/", normalized)
        self.assertNotIn("/WeFlow/", normalized)
        self.assertTrue((script_path.parent / "wasm_video_decode.js").exists())
        self.assertTrue((script_path.parent / "wasm_video_decode.wasm").exists())

    def test_weflow_wxisaac64_reuses_persistent_process(self):
        sns_media.weflow_wxisaac64_keystream.cache_clear()
        sns_media._WEFLOW_WASM_PROCESS.close()
        try:
            first = sns_media.weflow_wxisaac64_keystream("1", 32)
            process = sns_media._WEFLOW_WASM_PROCESS._process
            self.assertIsNotNone(process)
            assert process is not None
            first_pid = process.pid

            second = sns_media.weflow_wxisaac64_keystream("2", 16)
            process2 = sns_media._WEFLOW_WASM_PROCESS._process
            self.assertIsNotNone(process2)
            assert process2 is not None
            self.assertEqual(process2.pid, first_pid)
            self.assertEqual(len(first), 32)
            self.assertEqual(len(second), 16)
        finally:
            sns_media._WEFLOW_WASM_PROCESS.close()

    def test_fix_sns_cdn_url_image_rewrites_150_and_appends_token(self):
        u = "http://mmsns.qpic.cn/sns/abc/150"
        out = sns_media.fix_sns_cdn_url(u, token="tkn", is_video=False)
        self.assertEqual(out, "https://mmsns.qpic.cn/sns/abc/0?token=tkn&idx=1")

        u2 = "https://mmsns.qpic.cn/sns/abc/150?foo=bar"
        out2 = sns_media.fix_sns_cdn_url(u2, token="tkn", is_video=False)
        self.assertEqual(out2, "https://mmsns.qpic.cn/sns/abc/0?foo=bar&token=tkn&idx=1")

    def test_fix_sns_cdn_url_replaces_stale_token_and_idx(self):
        out = sns_media.fix_sns_cdn_url(
            "https://mmsns.qpic.cn/sns/abc/0?token=stale&idx=9&foo=bar",
            token="fresh",
            is_video=False,
        )
        self.assertEqual(out, "https://mmsns.qpic.cn/sns/abc/0?foo=bar&token=fresh&idx=1")

    def test_normalize_sns_cache_url_ignores_token_and_idx(self):
        first = sns_media.normalize_sns_cache_url(
            "https://mmsns.qpic.cn/sns/abc/0?foo=bar&token=old&idx=1"
        )
        second = sns_media.normalize_sns_cache_url(
            "https://mmsns.qpic.cn/sns/abc/0?token=new&idx=7&foo=bar"
        )
        self.assertEqual(first, second)
        self.assertEqual(first, "mmsns.qpic.cn/sns/abc/0?foo=bar")

    def test_fix_sns_cdn_url_video_places_token_first(self):
        u = "https://snsvideodownload.video.qq.com/abc.mp4?foo=1&bar=2"
        out = sns_media.fix_sns_cdn_url(u, token="tkn", is_video=True)
        self.assertEqual(out, "https://snsvideodownload.video.qq.com/abc.mp4?token=tkn&idx=1&foo=1&bar=2")

    def test_fix_sns_cdn_url_non_tencent_host_passthrough(self):
        u = "http://example.com/a/150?x=1"
        out = sns_media.fix_sns_cdn_url(u, token="tkn", is_video=False)
        self.assertEqual(out, u)

    def test_maybe_decrypt_sns_video_file_xors_inplace(self):
        # Build a fake MP4 header (ftyp at offset 4) and encrypt it by XORing with a keystream.
        plain = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 48
        ks = bytes(range(len(plain)))
        enc = bytes([plain[i] ^ ks[i] for i in range(len(plain))])

        with TemporaryDirectory() as td:
            p = Path(td) / "v.mp4"
            p.write_bytes(enc)

            with mock.patch("wechat_decrypt_tool.sns_media.weflow_wxisaac64_keystream", return_value=ks):
                did = sns_media.maybe_decrypt_sns_video_file(p, key="1")
                self.assertTrue(did)
                self.assertEqual(p.read_bytes(), plain)

                # Second run should be a no-op because it already looks like a MP4.
                did2 = sns_media.maybe_decrypt_sns_video_file(p, key="1")
                self.assertFalse(did2)

    def test_try_fetch_and_decrypt_sns_image_remote_cache_hit(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            url = "https://mmsns.qpic.cn/sns/test/0?token=tkn&idx=1"
            key = "123"
            fixed = sns_media.fix_sns_cdn_url(url, token="tkn", is_video=False)
            digest = hashlib.md5(f"{fixed}|{key}".encode("utf-8", errors="ignore")).hexdigest()

            cache_dir = account_dir / "sns_remote_cache" / digest[:2]
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / f"{digest}.jpg"

            payload = b"\xff\xd8\xff\x00fakejpeg"
            cache_path.write_bytes(payload)

            res = asyncio.run(
                sns_media.try_fetch_and_decrypt_sns_image_remote(
                    account_dir=account_dir,
                    url=url,
                    key=key,
                    token="tkn",
                    use_cache=True,
                )
            )
            self.assertIsNotNone(res)
            assert res is not None
            self.assertEqual(res.source, "remote-cache")
            self.assertEqual(res.media_type, "image/jpeg")
            self.assertEqual(res.payload, payload)
            self.assertTrue(res.cache_path and res.cache_path.exists())

    def test_cached_remote_image_lookup_never_downloads(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            url = "https://mmsns.qpic.cn/sns/test/0?token=tkn&idx=1"
            key = "123"
            fixed = sns_media.fix_sns_cdn_url(url, token="tkn", is_video=False)
            digest = hashlib.md5(f"{fixed}|{key}".encode("utf-8", errors="ignore")).hexdigest()
            cache_dir = account_dir / "sns_remote_cache" / digest[:2]
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{digest}.jpg").write_bytes(b"\xff\xd8\xff\x00cached")

            with mock.patch("wechat_decrypt_tool.sns_media._download_sns_remote_bytes") as download:
                res = sns_media.get_cached_sns_remote_image(
                    account_dir=account_dir,
                    url=url,
                    key=key,
                    token="tkn",
                )

            download.assert_not_called()
            self.assertIsNotNone(res)
            assert res is not None
            self.assertEqual(res.source, "remote-cache")

    def test_cached_remote_image_survives_token_rotation(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)
            old_url = "https://mmsns.qpic.cn/sns/test/0?foo=bar&token=old&idx=1"
            cache_dir, cache_stem = sns_media._sns_remote_cache_dir_and_stem(
                account_dir,
                url=old_url,
                key="old-key",
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{cache_stem}.jpg").write_bytes(b"\xff\xd8\xff\x00cached")

            with mock.patch("wechat_decrypt_tool.sns_media._download_sns_remote_bytes") as download:
                result = sns_media.get_cached_sns_remote_image(
                    account_dir=account_dir,
                    url="https://mmsns.qpic.cn/sns/test/0?foo=bar&token=new&idx=9",
                    key="new-key",
                    token="new",
                )

            download.assert_not_called()
            self.assertIsNotNone(result)

    def test_try_fetch_and_decrypt_sns_image_remote_cache_upgrades_bin_extension(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            url = "https://mmsns.qpic.cn/sns/test/0?token=tkn&idx=1"
            key = "123"
            fixed = sns_media.fix_sns_cdn_url(url, token="tkn", is_video=False)
            digest = hashlib.md5(f"{fixed}|{key}".encode("utf-8", errors="ignore")).hexdigest()

            cache_dir = account_dir / "sns_remote_cache" / digest[:2]
            cache_dir.mkdir(parents=True, exist_ok=True)
            bin_path = cache_dir / f"{digest}.bin"
            png_payload = b"\x89PNG\r\n\x1a\n" + b"fakepng"
            bin_path.write_bytes(png_payload)

            res = asyncio.run(
                sns_media.try_fetch_and_decrypt_sns_image_remote(
                    account_dir=account_dir,
                    url=url,
                    key=key,
                    token="tkn",
                    use_cache=True,
                )
            )
            self.assertIsNotNone(res)
            assert res is not None
            self.assertEqual(res.source, "remote-cache")
            self.assertEqual(res.media_type, "image/png")
            self.assertTrue(res.cache_path and res.cache_path.suffix.lower() == ".png")
            self.assertTrue(res.cache_path and res.cache_path.exists())
            self.assertFalse(bin_path.exists())

    def test_try_fetch_and_decrypt_sns_image_remote_decrypts_when_needed(self):
        raw = b"\x01\x02\x03\x04not_an_image"
        decoded = b"\x89PNG\r\n\x1a\n" + b"decoded"

        async def fake_download(_url: str, **_kwargs):
            return raw, "image/jpeg", "1"

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("wechat_decrypt_tool.sns_media._download_sns_remote_bytes", side_effect=fake_download):
                with mock.patch("wechat_decrypt_tool.sns_media.weflow_decrypt_sns_image_bytes", return_value=decoded):
                    res = asyncio.run(
                        sns_media.try_fetch_and_decrypt_sns_image_remote(
                            account_dir=account_dir,
                            url="https://mmsns.qpic.cn/sns/test/0",
                            key="123",
                            token="tkn",
                            use_cache=False,
                        )
                    )
                    self.assertIsNotNone(res)
                    assert res is not None
                    self.assertTrue(res.cache_path and res.cache_path.exists())

        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.media_type, "image/png")
        self.assertEqual(res.source, "remote-decrypt")
        self.assertEqual(res.x_enc, "1")
        self.assertEqual(res.payload, decoded)

    def test_try_fetch_and_decrypt_sns_image_remote_decrypt_failure_returns_none(self):
        raw = b"\x01\x02\x03\x04not_an_image"
        decoded_bad = b"\x00\x00\x00\x00still_bad"

        async def fake_download(_url: str, **_kwargs):
            return raw, "image/jpeg", "1"

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("wechat_decrypt_tool.sns_media._download_sns_remote_bytes", side_effect=fake_download):
                with mock.patch("wechat_decrypt_tool.sns_media.weflow_decrypt_sns_image_bytes", return_value=decoded_bad):
                    res = asyncio.run(
                        sns_media.try_fetch_and_decrypt_sns_image_remote(
                            account_dir=account_dir,
                            url="https://mmsns.qpic.cn/sns/test/0",
                            key="123",
                            token="tkn",
                            use_cache=False,
                        )
                    )

        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
