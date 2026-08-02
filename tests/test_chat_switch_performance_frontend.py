import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestChatSwitchPerformanceFrontend(unittest.TestCase):
    def test_superseded_message_requests_are_aborted(self):
        messages = (
            ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js"
        ).read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "composables" / "useApi.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("let messageLoadController = null", messages)
        self.assertIn("abortMessageLoad()", messages)
        self.assertIn("new AbortController()", messages)
        self.assertIn("params.signal = requestController.signal", messages)
        self.assertIn("isAbortError(error, requestController)", messages)
        self.assertIn(
            "request(url, params?.signal ? { signal: params.signal } : {})", api
        )

    def test_realtime_stream_is_singleton_and_burst_coalesced(self):
        source = (
            ROOT / "frontend" / "stores" / "chatRealtime.js"
        ).read_text(encoding="utf-8")

        self.assertIn("Symbol.for('wechat-data-analysis.chat-realtime-streams')", source)
        self.assertIn("previous.source.close()", source)
        self.assertIn("registry?.get(streamKey)?.source !== source", source)
        self.assertIn("initialSnapshotPending", source)
        self.assertIn("CHANGE_MAX_WAIT_MS", source)
        self.assertIn("if (!silent) {", source)

    def test_session_refreshes_are_cancelled_deduplicated_and_throttled(self):
        sessions = (
            ROOT / "frontend" / "composables" / "chat" / "useChatSessions.js"
        ).read_text(encoding="utf-8")
        page = (
            ROOT / "frontend" / "pages" / "chat" / "[[username]].vue"
        ).read_text(encoding="utf-8")

        self.assertIn("let sessionsRequestPromise = null", sessions)
        self.assertIn("sessionsRequestKey === requestKey", sessions)
        self.assertIn("abortSessionsRequest()", sessions)
        self.assertIn("params.signal = controller.signal", sessions)
        self.assertIn("REALTIME_SESSIONS_REFRESH_MIN_INTERVAL_MS = 3000", page)
        self.assertIn("realtimeSessionsRefreshTimer", page)
        self.assertIn("document.visibilityState === 'hidden'", page)
        self.assertIn("resumedFromHidden && realtimeEnabled.value", page)

    def test_chat_media_diagnostics_are_opt_in_and_link_images_are_lazy(self):
        perf_logger = (
            ROOT / "frontend" / "lib" / "chat" / "perf-logger.js"
        ).read_text(encoding="utf-8")
        media_plugin = (
            ROOT / "frontend" / "plugins" / "chat-media-perf.client.js"
        ).read_text(encoding="utf-8")
        link_card = (
            ROOT / "frontend" / "components" / "chat" / "LinkCard.vue"
        ).read_text(encoding="utf-8")
        messages = (
            ROOT / "frontend" / "composables" / "chat" / "useChatMessages.js"
        ).read_text(encoding="utf-8")

        self.assertIn("CHAT_PERF_STORAGE_KEY = 'debug.chat.performance'", perf_logger)
        self.assertIn("if (!isChatPerfLoggingEnabled()) return", media_plugin)
        self.assertIn("isChatPerfLoggingEnabled()", messages)
        self.assertIn("logPerfChannel('chat-messages', phase, payload)", messages)
        self.assertNotIn(
            "window.wechatDesktop?.logDebug?.('chat-messages'", messages
        )
        self.assertNotIn("console.info(`[chat-messages]", messages)
        self.assertIn("loading: 'lazy'", link_card)
        self.assertIn("decoding: 'async'", link_card)
        self.assertIn("fetchpriority: 'low'", link_card)

    def test_sns_timeline_does_not_autoplay_remote_videos(self):
        source = (ROOT / "frontend" / "pages" / "sns.vue").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(':src="getSnsRemoteVideoSrc(post,', source)
        self.assertGreaterEqual(
            source.count('v-chat-lazy-src="getMediaThumbSrc(post,'), 4
        )
        self.assertIn('alt="视频缩略图"', source)

    def test_lazy_media_releases_inflight_sources_on_unmount(self):
        source = (
            ROOT / "frontend" / "plugins" / "chat-media-perf.client.js"
        ).read_text(encoding="utf-8")

        release = source.split("const releaseLazySrc", 1)[1].split(
            "const applyLazySrc", 1
        )[0]
        self.assertIn("element.removeAttribute('src')", release)
        self.assertIn("element.pause?.()", release)
        self.assertIn("element.load?.()", release)
        self.assertIn("releaseLazySrc(element)", source)


if __name__ == "__main__":
    unittest.main()
