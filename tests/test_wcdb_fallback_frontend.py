import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestWcdbFallbackFrontend(unittest.TestCase):
    def test_app_shell_renders_global_data_source_fallback_banner(self):
        app = (ROOT / "frontend" / "app.vue").read_text(encoding="utf-8")
        banner = (
            ROOT / "frontend" / "components" / "DataSourceFallbackBanner.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("DataSourceFallbackBanner", app)
        self.assertIn("selectedDataSourceStatus", app)
        self.assertIn("当前显示已解密数据库快照", banner)
        self.assertIn('role="status"', banner)

    def test_api_responses_update_selected_account_source_status(self):
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(encoding="utf-8")
        store = (ROOT / "frontend" / "stores" / "chatAccounts.js").read_text(encoding="utf-8")

        self.assertIn("applySourceResponse(response)", api)
        self.assertIn("const applySourceResponse", store)
        self.assertIn("sourceFallbackReason", store)
        self.assertIn("selectedDataSourceStatus", store)

    def test_homepage_can_scroll_below_wrapped_mobile_banner(self):
        home = (ROOT / "frontend" / "pages" / "index.vue").read_text(encoding="utf-8")

        self.assertIn("overflow-auto", home)
        self.assertIn("justify-start lg:justify-center", home)


if __name__ == "__main__":
    unittest.main()
