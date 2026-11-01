import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestContactsExportFrontend(unittest.TestCase):
    def test_browser_export_requests_write_permission_before_backend_work(self):
        source = (ROOT / "frontend" / "pages" / "contacts.vue").read_text(encoding="utf-8")

        self.assertIn("window.showDirectoryPicker({ mode: 'readwrite' })", source)
        self.assertIn("handle.requestPermission({ mode: 'readwrite' })", source)

        start_export = source.split("const startExport = async () => {", 1)[1].split("\nonMounted(", 1)[0]
        permission_offset = start_export.index("await ensureWebExportWritePermission()")
        contacts_offset = start_export.index("await exportContactsInWeb()")
        self.assertLess(permission_offset, contacts_offset)


if __name__ == "__main__":
    unittest.main()
