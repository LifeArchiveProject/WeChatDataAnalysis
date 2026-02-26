import sys
import unittest
from pathlib import Path

# Ensure "src/" is importable when running tests from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestWrappedManifestBentoSummary(unittest.TestCase):
    def test_manifest_appends_bento_summary(self):
        try:
            from wechat_decrypt_tool.wrapped.service import _WRAPPED_CARD_MANIFEST
        except ModuleNotFoundError as e:
            # Some dev/test environments may not have optional deps installed (e.g. pypinyin).
            # The manifest itself doesn't depend on them, but importing the service module does.
            if getattr(e, "name", "") == "pypinyin":
                self.skipTest("pypinyin is not installed")
            raise

        self.assertTrue(len(_WRAPPED_CARD_MANIFEST) > 0)
        last = _WRAPPED_CARD_MANIFEST[-1]
        self.assertEqual(int(last.get("id")), 7)
        self.assertEqual(str(last.get("kind")), "global/bento_summary")


if __name__ == "__main__":
    unittest.main()
