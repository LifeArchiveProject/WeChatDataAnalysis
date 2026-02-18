import asyncio
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import sns_media  # noqa: E402  pylint: disable=wrong-import-position


class TestSnsMedia(unittest.TestCase):
    def test_fix_sns_cdn_url_image_rewrites_150_and_appends_token(self):
        u = "http://mmsns.qpic.cn/sns/abc/150"
        out = sns_media.fix_sns_cdn_url(u, token="tkn", is_video=False)
        self.assertEqual(out, "https://mmsns.qpic.cn/sns/abc/0?token=tkn&idx=1")

        u2 = "https://mmsns.qpic.cn/sns/abc/150?foo=bar"
        out2 = sns_media.fix_sns_cdn_url(u2, token="tkn", is_video=False)
        self.assertEqual(out2, "https://mmsns.qpic.cn/sns/abc/0?foo=bar&token=tkn&idx=1")

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

        async def fake_download(_url: str):
            return raw, "image/jpeg", "1"

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("wechat_decrypt_tool.sns_media._download_sns_remote_bytes", side_effect=fake_download):
                with mock.patch("wechat_decrypt_tool.sns_media._wcdb_decrypt_sns_image", return_value=decoded):
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
        self.assertEqual(res.media_type, "image/png")
        self.assertEqual(res.source, "remote-decrypt")
        self.assertEqual(res.x_enc, "1")
        self.assertEqual(res.payload, decoded)

    def test_try_fetch_and_decrypt_sns_image_remote_decrypt_failure_returns_none(self):
        raw = b"\x01\x02\x03\x04not_an_image"
        decoded_bad = b"\x00\x00\x00\x00still_bad"

        async def fake_download(_url: str):
            return raw, "image/jpeg", "1"

        with TemporaryDirectory() as td:
            account_dir = Path(td) / "acc"
            account_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("wechat_decrypt_tool.sns_media._download_sns_remote_bytes", side_effect=fake_download):
                with mock.patch("wechat_decrypt_tool.sns_media._wcdb_decrypt_sns_image", return_value=decoded_bad):
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

