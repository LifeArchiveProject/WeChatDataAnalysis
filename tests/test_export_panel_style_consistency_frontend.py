import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestExportPanelStyleConsistencyFrontend(unittest.TestCase):
    def test_shared_export_styles_are_loaded(self):
        config = (ROOT / "frontend" / "nuxt.config.ts").read_text(encoding="utf-8")
        styles = (ROOT / "frontend" / "assets" / "css" / "export-panels.css").read_text(encoding="utf-8")

        self.assertIn("~/assets/css/export-panels.css", config)
        self.assertIn(".app-export-modal", styles)
        self.assertIn(".app-export-format-option", styles)
        self.assertIn(".app-export-destination", styles)
        self.assertIn("html[data-theme='dark'] .app-export-modal", styles)

    def test_all_non_chat_export_surfaces_use_the_shared_visual_language(self):
        sources = {
            "records": ROOT / "frontend" / "components" / "RecordExportDialog.vue",
            "account archive": ROOT / "frontend" / "components" / "GlobalExportDialog.vue",
            "moments": ROOT / "frontend" / "pages" / "sns.vue",
            "contacts": ROOT / "frontend" / "pages" / "contacts.vue",
        }

        for label, path in sources.items():
            with self.subTest(surface=label):
                source = path.read_text(encoding="utf-8")
                self.assertIn("app-export-", source)
                self.assertIn("app-export-panel", source)

        records = sources["records"].read_text(encoding="utf-8")
        moments = sources["moments"].read_text(encoding="utf-8")
        contacts = sources["contacts"].read_text(encoding="utf-8")
        archive = sources["account archive"].read_text(encoding="utf-8")

        for source in (records, moments, contacts):
            self.assertIn("app-export-format-option", source)
            self.assertIn("app-export-destination", source)
        self.assertIn("app-export-destination", archive)
        self.assertIn("app-export-layout", moments)


if __name__ == "__main__":
    unittest.main()
