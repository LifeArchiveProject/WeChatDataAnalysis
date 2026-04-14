import importlib
import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


class TestChatExportEmojiFastMiss(unittest.TestCase):
    def _reload_export_module(self):
        import wechat_decrypt_tool.chat_export_service as chat_export_service

        importlib.reload(chat_export_service)
        return chat_export_service

    def test_emoji_miss_skips_fallback_scan_and_caches_negative_result(self):
        svc = self._reload_export_module()
        md5 = "8f436b616da7832e5c206ba3d781a714"
        calls: list[dict[str, object]] = []

        original_try_find = svc._try_find_decrypted_resource
        original_resolve_kind = svc._resolve_media_path_for_kind
        try:
            svc._try_find_decrypted_resource = lambda *args, **kwargs: None

            def fake_resolve_kind(account_dir, kind, md5, username, allow_fallback_scan=True):
                calls.append(
                    {
                        "account_dir": account_dir,
                        "kind": kind,
                        "md5": md5,
                        "username": username,
                        "allow_fallback_scan": allow_fallback_scan,
                    }
                )
                return None

            svc._resolve_media_path_for_kind = fake_resolve_kind

            with TemporaryDirectory() as td:
                media_written: dict[str, str] = {}
                with io.BytesIO() as buf, zipfile.ZipFile(buf, "w") as zf:
                    arc1, is_new1 = svc._materialize_media(
                        zf=zf,
                        account_dir=Path(td),
                        conv_username="room@chatroom",
                        kind="emoji",
                        md5=md5,
                        file_id="",
                        media_written=media_written,
                        suggested_name="",
                        media_index=None,
                    )
                    arc2, is_new2 = svc._materialize_media(
                        zf=zf,
                        account_dir=Path(td),
                        conv_username="room@chatroom",
                        kind="emoji",
                        md5=md5,
                        file_id="",
                        media_written=media_written,
                        suggested_name="",
                        media_index=None,
                    )

            self.assertEqual(arc1, "")
            self.assertEqual(arc2, "")
            self.assertFalse(is_new1)
            self.assertFalse(is_new2)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["kind"], "emoji")
            self.assertEqual(calls[0]["md5"], md5)
            self.assertEqual(calls[0]["username"], "room@chatroom")
            self.assertFalse(bool(calls[0]["allow_fallback_scan"]))
            self.assertIn("emoji:" + md5, media_written)
            self.assertEqual(media_written["emoji:" + md5], "")
        finally:
            svc._try_find_decrypted_resource = original_try_find
            svc._resolve_media_path_for_kind = original_resolve_kind

    def test_image_lookup_keeps_fallback_scan_enabled(self):
        svc = self._reload_export_module()
        md5 = "80793a35a19810699a03579c654f4c50"
        calls: list[dict[str, object]] = []

        original_try_find = svc._try_find_decrypted_resource
        original_resolve_kind = svc._resolve_media_path_for_kind
        try:
            svc._try_find_decrypted_resource = lambda *args, **kwargs: None

            def fake_resolve_kind(account_dir, kind, md5, username, allow_fallback_scan=True):
                calls.append(
                    {
                        "kind": kind,
                        "md5": md5,
                        "allow_fallback_scan": allow_fallback_scan,
                    }
                )
                return None

            svc._resolve_media_path_for_kind = fake_resolve_kind

            with TemporaryDirectory() as td:
                with io.BytesIO() as buf, zipfile.ZipFile(buf, "w") as zf:
                    arc, is_new = svc._materialize_media(
                        zf=zf,
                        account_dir=Path(td),
                        conv_username="friend",
                        kind="image",
                        md5=md5,
                        file_id="",
                        media_written={},
                        suggested_name="",
                        media_index=None,
                    )

            self.assertEqual(arc, "")
            self.assertFalse(is_new)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["kind"], "image")
            self.assertFalse(bool(calls[0]["allow_fallback_scan"]))
            self.assertEqual(calls[1]["kind"], "image")
            self.assertTrue(bool(calls[1]["allow_fallback_scan"]))
        finally:
            svc._try_find_decrypted_resource = original_try_find
            svc._resolve_media_path_for_kind = original_resolve_kind


if __name__ == "__main__":
    unittest.main()
