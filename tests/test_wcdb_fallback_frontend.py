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

    def test_realtime_status_surfaces_native_probe_errors(self):
        store = (ROOT / "frontend" / "stores" / "chatRealtime.js").read_text(encoding="utf-8")

        self.assertIn("info?.probe_error", store)
        self.assertIn("info?.failure_reason", store)
        self.assertIn("info?.error", store)
        self.assertIn("publishRealtimeDataSourceStatus(result)", store)
        self.assertIn("fallbackActive: !isAvailable", store)
        self.assertIn("reason: isAvailable ? '' : reason", store)

    def test_realtime_status_ignores_out_of_order_account_responses(self):
        store = (ROOT / "frontend" / "stores" / "chatRealtime.js").read_text(encoding="utf-8")

        self.assertIn("let statusRequestGeneration = 0", store)
        self.assertIn("const requestGeneration = ++statusRequestGeneration", store)
        self.assertIn("generation === statusRequestGeneration && account === getAccount()", store)
        self.assertGreaterEqual(store.count("stale: !statusRequestIsCurrent(requestGeneration, account)"), 2)
        self.assertGreaterEqual(store.count("if (result.stale) return result"), 2)

        enable_start = store.index("const enable = async")
        enable_end = store.index("const disable = async", enable_start)
        enable_source = store[enable_start:enable_end]
        self.assertIn("const statusResult = await fetchStatus()", enable_source)
        self.assertIn("if (!statusResult || statusResult.stale) return false", enable_source)
        self.assertIn("if (!statusResult.available)", enable_source)
        self.assertNotIn("if (!available.value)", enable_source)

    def test_realtime_stream_reconnects_with_bounded_backoff(self):
        store = (ROOT / "frontend" / "stores" / "chatRealtime.js").read_text(encoding="utf-8")

        self.assertIn("REALTIME_STREAM_RECONNECT_BASE_MS", store)
        self.assertIn("REALTIME_STREAM_RECONNECT_MAX_MS", store)
        self.assertIn("scheduleStreamReconnect(generation, account)", store)
        self.assertIn("streamReconnectAttempt = 0", store)
        self.assertIn("clearStreamReconnectTimer()", store)

    def test_realtime_stream_resets_backoff_only_after_stable_window(self):
        store = (ROOT / "frontend" / "stores" / "chatRealtime.js").read_text(encoding="utf-8")

        self.assertIn("const REALTIME_STREAM_STABLE_MS = 10_000", store)
        self.assertIn("let streamStabilityTimer = null", store)
        self.assertIn("clearStreamStabilityTimer()", store)
        onopen_start = store.index("source.onopen = () => {")
        onmessage_start = store.index("source.onmessage =", onopen_start)
        onopen_source = store[onopen_start:onmessage_start]
        self.assertIn("streamStabilityTimer = setTimeout(() => {", onopen_source)
        self.assertIn("streamReconnectAttempt = 0", onopen_source)
        self.assertIn("}, REALTIME_STREAM_STABLE_MS)", onopen_source)

    def test_realtime_stream_rejects_stale_errors_and_closes_previous_source(self):
        store = (ROOT / "frontend" / "stores" / "chatRealtime.js").read_text(encoding="utf-8")

        self.assertIn("closeEventSource()\n    const apiBase", store)
        onerror_start = store.index("source.onerror = () => {")
        start_stream = store.index("const startStream =", onerror_start)
        onerror_source = store[onerror_start:start_stream]
        self.assertIn("if (!streamIsCurrent(generation, account) || eventSource !== source)", onerror_source)
        self.assertIn("closeEventSource()", onerror_source)


if __name__ == "__main__":
    unittest.main()
