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


class _FakeDisconnectingRequest:
    def __init__(self, disconnect_after: int):
        self._disconnect_after = disconnect_after
        self._calls = 0

    async def is_disconnected(self):
        self._calls += 1
        return self._calls >= self._disconnect_after


class TestMediaDecryptStreamCancel(unittest.TestCase):
    def test_stream_stops_processing_when_client_disconnects(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            account_dir = root / "account"
            wxid_dir = root / "wxid"
            dat_path = wxid_dir / "image.dat"
            resource_dir = account_dir / "resource"
            wxid_dir.mkdir(parents=True, exist_ok=True)
            dat_path.write_bytes(b"encrypted")

            request = _FakeDisconnectingRequest(disconnect_after=3)
            decrypt_mock = mock.Mock(return_value=(True, "ok"))

            with mock.patch.object(media_router, "_resolve_account_dir", return_value=account_dir):
                with mock.patch.object(media_router, "_resolve_account_wxid_dir", return_value=wxid_dir):
                    with mock.patch.object(media_router, "_load_media_keys", return_value={"xor": 0xA5, "aes": ""}):
                        with mock.patch.object(media_router, "_collect_all_dat_files", return_value=[(dat_path, "abc123")]):
                            with mock.patch.object(media_router, "_get_resource_dir", return_value=resource_dir):
                                with mock.patch.object(media_router, "_try_find_decrypted_resource", return_value=None):
                                    with mock.patch.object(media_router, "_decrypt_and_save_resource", decrypt_mock):
                                        response = asyncio.run(
                                            media_router.decrypt_all_media_stream(
                                                request=request,
                                                account="wxid_demo",
                                            )
                                        )

                                        async def _read_chunks():
                                            chunks = []
                                            async for chunk in response.body_iterator:
                                                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
                                            return chunks

                                        chunks = asyncio.run(_read_chunks())

            events = []
            for chunk in chunks:
                for line in chunk.splitlines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[len("data: ") :]))

            self.assertEqual([event.get("type") for event in events], ["scanning", "start"])
            decrypt_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
