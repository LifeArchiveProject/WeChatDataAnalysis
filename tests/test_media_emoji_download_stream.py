import asyncio
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import media as media_router  # noqa: E402  pylint: disable=wrong-import-position


PNG_1X1 = bytes.fromhex(
    "89504E470D0A1A0A"
    "0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C6360606060000000050001A5F64540"
    "0000000049454E44AE426082"
)


class _FakeRequest:
    async def is_disconnected(self):
        return False


class _FakeDisconnectingRequest:
    def __init__(self, disconnect_after: int):
        self._disconnect_after = disconnect_after
        self._calls = 0

    async def is_disconnected(self):
        self._calls += 1
        return self._calls >= self._disconnect_after


def _emoji_catalog(md5: str):
    return (
        {
            md5: {
                "md5": md5,
                "urls": [f"https://example.com/{md5}.png"],
                "aes_keys": [],
                "sources": ["message_xml"],
            }
        },
        {
            "total_candidates": 1,
            "total_candidates_with_url": 1,
            "source_counts": {"message_xml": 1},
        },
    )


async def _read_sse_events(response) -> list[dict]:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))

    events = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


class TestMediaEmojiDownloadStream(unittest.TestCase):
    def test_stream_downloads_missing_emoji_and_saves_resource(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "account"
            account_dir.mkdir(parents=True, exist_ok=True)
            md5 = "a" * 32

            with mock.patch.object(media_router, "_resolve_account_dir", return_value=account_dir):
                with mock.patch.object(
                    media_router,
                    "_collect_emoticon_download_catalog",
                    return_value=_emoji_catalog(md5),
                ):
                    with mock.patch.object(
                        media_router,
                        "_try_fetch_emoticon_from_remote",
                        return_value=(PNG_1X1, "image/png"),
                    ) as fetch_mock:
                        response = asyncio.run(
                            media_router.download_all_emojis_stream(
                                request=_FakeRequest(),
                                account="wxid_demo",
                            )
                        )
                        events = asyncio.run(_read_sse_events(response))

            self.assertEqual([event.get("type") for event in events], ["scanning", "start", "progress", "complete"])
            self.assertEqual(events[2].get("status"), "success")
            self.assertEqual(events[3].get("success_count"), 1)
            self.assertEqual(events[1].get("concurrency"), 20)
            self.assertTrue((account_dir / "resource" / md5[:2] / f"{md5}.png").exists())
            fetch_mock.assert_called_once()

    def test_stream_uses_requested_concurrency(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "account"
            account_dir.mkdir(parents=True, exist_ok=True)
            md5 = "d" * 32

            with mock.patch.object(media_router, "_resolve_account_dir", return_value=account_dir):
                with mock.patch.object(
                    media_router,
                    "_collect_emoticon_download_catalog",
                    return_value=_emoji_catalog(md5),
                ):
                    with mock.patch.object(
                        media_router,
                        "_try_fetch_emoticon_from_remote",
                        return_value=(PNG_1X1, "image/png"),
                    ):
                        response = asyncio.run(
                            media_router.download_all_emojis_stream(
                                request=_FakeRequest(),
                                account="wxid_demo",
                                concurrency=7,
                            )
                        )
                        events = asyncio.run(_read_sse_events(response))

            self.assertEqual(events[1].get("concurrency"), 7)
            self.assertEqual(events[2].get("concurrency"), 7)
            self.assertEqual(events[3].get("concurrency"), 7)

    def test_stream_skips_existing_downloaded_emoji(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "account"
            md5 = "b" * 32
            resource_dir = account_dir / "resource" / md5[:2]
            account_dir.mkdir(parents=True, exist_ok=True)
            resource_dir.mkdir(parents=True, exist_ok=True)
            cached = resource_dir / f"{md5}.png"
            cached.write_bytes(PNG_1X1)

            with mock.patch.object(media_router, "_resolve_account_dir", return_value=account_dir):
                with mock.patch.object(
                    media_router,
                    "_collect_emoticon_download_catalog",
                    return_value=_emoji_catalog(md5),
                ):
                    with mock.patch.object(media_router, "_try_fetch_emoticon_from_remote") as fetch_mock:
                        response = asyncio.run(
                            media_router.download_all_emojis_stream(
                                request=_FakeRequest(),
                                account="wxid_demo",
                            )
                        )
                        events = asyncio.run(_read_sse_events(response))

            self.assertEqual([event.get("type") for event in events], ["scanning", "start", "progress", "complete"])
            self.assertEqual(events[2].get("status"), "skip")
            self.assertEqual(events[3].get("skip_count"), 1)
            fetch_mock.assert_not_called()

    def test_stream_stops_before_processing_when_client_disconnects(self):
        with TemporaryDirectory() as td:
            account_dir = Path(td) / "account"
            account_dir.mkdir(parents=True, exist_ok=True)
            md5 = "c" * 32

            with mock.patch.object(media_router, "_resolve_account_dir", return_value=account_dir):
                with mock.patch.object(
                    media_router,
                    "_collect_emoticon_download_catalog",
                    return_value=_emoji_catalog(md5),
                ):
                    with mock.patch.object(media_router, "_try_fetch_emoticon_from_remote") as fetch_mock:
                        response = asyncio.run(
                            media_router.download_all_emojis_stream(
                                request=_FakeDisconnectingRequest(disconnect_after=3),
                                account="wxid_demo",
                            )
                        )
                        events = asyncio.run(_read_sse_events(response))

            self.assertEqual([event.get("type") for event in events], ["scanning", "start"])
            fetch_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
