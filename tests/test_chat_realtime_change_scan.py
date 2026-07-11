import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.routers.chat import _scan_db_storage_mtime_ns


class TestChatRealtimeChangeScan(unittest.TestCase):
    def test_general_database_changes_are_visible_to_realtime_pages(self):
        with TemporaryDirectory() as td:
            db_path = Path(td) / "general" / "general.db"
            db_path.parent.mkdir(parents=True)
            db_path.write_bytes(b"fixture")

            self.assertGreater(_scan_db_storage_mtime_ns(Path(td)), 0)


if __name__ == "__main__":
    unittest.main()
