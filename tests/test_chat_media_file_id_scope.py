import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestChatMediaFileIdScope(unittest.TestCase):
    def setUp(self) -> None:
        from wechat_decrypt_tool.media_helpers import _fallback_search_media_by_file_id

        _fallback_search_media_by_file_id.cache_clear()

    def tearDown(self) -> None:
        from wechat_decrypt_tool.media_helpers import _fallback_search_media_by_file_id

        _fallback_search_media_by_file_id.cache_clear()

    def test_scoped_lookup_finds_current_conversation_cache_thumb(self):
        from wechat_decrypt_tool.media_helpers import _fallback_search_media_by_file_id

        with TemporaryDirectory() as td:
            root = Path(td) / "wxid_source"
            username = "wbh6463"
            file_id = "85_1785198543"
            chat_hash = hashlib.md5(username.encode("utf-8")).hexdigest()
            target = root / "cache" / "2026-07" / "Message" / chat_hash / "Thumb" / f"{file_id}_thumb.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\xff\xd8\xff\xd9")

            found = _fallback_search_media_by_file_id(
                str(root),
                file_id,
                kind="image",
                username=username,
                allow_global_scan=False,
            )

            self.assertEqual(found, str(target))

    def test_scoped_lookup_does_not_recurse_through_global_media_roots(self):
        from wechat_decrypt_tool.media_helpers import _fallback_search_media_by_file_id

        with TemporaryDirectory() as td:
            root = Path(td) / "wxid_source"
            username = "selected-contact"
            other_hash = hashlib.md5(b"other-contact").hexdigest()
            target = root / "cache" / "2026-07" / "Message" / other_hash / "Thumb" / "71_1784432483_thumb.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"\xff\xd8\xff\xd9")

            original_rglob = Path.rglob
            scanned_roots: list[Path] = []

            def recording_rglob(path: Path, pattern: str):
                scanned_roots.append(path)
                return original_rglob(path, pattern)

            with mock.patch.object(Path, "rglob", recording_rglob):
                found = _fallback_search_media_by_file_id(
                    str(root),
                    "71_1784432483",
                    kind="image",
                    username=username,
                    allow_global_scan=False,
                )

            self.assertIsNone(found)
            self.assertNotIn(root / "cache", scanned_roots)
            self.assertNotIn(root / "msg" / "attach", scanned_roots)

    def test_lookup_rejects_file_id_path_traversal(self):
        from wechat_decrypt_tool.media_helpers import _fallback_search_media_by_file_id

        with TemporaryDirectory() as td:
            root = Path(td) / "wxid_source"
            username = "selected-contact"
            chat_hash = hashlib.md5(username.encode("utf-8")).hexdigest()
            search_dir = root / "cache" / "Message" / chat_hash
            search_dir.mkdir(parents=True, exist_ok=True)
            escaped_target = root / "outside.jpg"
            escaped_target.write_bytes(b"\xff\xd8\xff\xd9")

            found = _fallback_search_media_by_file_id(
                str(root),
                "../../../outside.jpg",
                kind="image",
                username=username,
                allow_global_scan=False,
            )

            self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
