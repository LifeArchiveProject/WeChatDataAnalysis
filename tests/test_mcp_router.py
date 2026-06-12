import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TestMcpRouter(unittest.TestCase):
    TEST_TOKEN = "test-mcp-token-1234567890"
    REMOVED_MCP_TOOLS = {
        "wechat.setup.get_saved_keys",
        "wechat.setup.get_database_key",
        "wechat.setup.get_image_key",
        "wechat.setup.decrypt_databases",
        "wechat.setup.get_decrypt_stream_url",
        "wechat.setup.preview_import_decrypted",
        "wechat.setup.get_import_decrypted_stream_url",
        "wechat.setup.cancel_import_decrypted",
        "wechat.setup.save_media_keys",
        "wechat.setup.decrypt_all_media",
        "wechat.setup.get_decrypt_all_media_stream_url",
        "wechat.setup.get_download_all_emojis_stream_url",
        "wechat.contacts.export_contacts",
        "wechat.chat.get_realtime_status",
        "wechat.chat.sync_realtime_session",
        "wechat.chat.sync_realtime_all_sessions",
        "wechat.chat.get_realtime_events_url",
        "wechat.moments.sync_latest",
        "wechat.editing.list_edited_sessions",
        "wechat.editing.list_edited_messages",
        "wechat.editing.get_message_edit_status",
        "wechat.editing.edit_message",
        "wechat.editing.repair_message_sender",
        "wechat.editing.flip_message_direction",
        "wechat.editing.reset_message_edit",
        "wechat.editing.reset_session_edits",
        "wechat.export.preview_chat_targets",
        "wechat.export.create_chat_export",
        "wechat.export.list_chat_exports",
        "wechat.export.get_chat_export",
        "wechat.export.cancel_chat_export",
        "wechat.export.get_chat_export_download",
        "wechat.export.get_chat_export_events_url",
        "wechat.export.create_moments_export",
        "wechat.export.list_moments_exports",
        "wechat.export.get_moments_export",
        "wechat.export.cancel_moments_export",
        "wechat.export.get_moments_export_download",
        "wechat.export.get_moments_export_events_url",
        "wechat.export.create_account_archive",
        "wechat.export.get_account_archive",
        "wechat.export.cancel_account_archive",
        "wechat.export.get_account_archive_download",
        "wechat.mobile.export_job",
        "wechat.admin.detect_wechat_installation",
        "wechat.admin.get_current_wechat_account",
        "wechat.admin.get_wechat_runtime_status",
        "wechat.admin.delete_account_data",
        "wechat.system.api_root",
        "wechat.system.health_check",
        "wechat.system.get_backend_log_file",
        "wechat.system.open_backend_log_file",
        "wechat.system.log_frontend_server_error",
        "wechat.system.get_backend_port",
        "wechat.system.set_backend_port_setting",
        "wechat.system.set_backend_port_and_restart",
        "wechat.system.get_mcp_lan_access",
        "wechat.system.set_mcp_lan_access",
        "wechat.system.get_img_helper_status",
        "wechat.system.toggle_img_helper",
        "wechat.system.pick_directory",
        "wechat.chat.get_search_index_status",
        "wechat.chat.build_search_index",
        "wechat.chat.get_session_last_message_cache_status",
        "wechat.chat.build_session_last_message_cache",
        "wechat.media.download_chat_emoji",
        "wechat.media.open_chat_media_folder",
    }

    def setUp(self):
        self._old_mcp_token = os.environ.get("WECHAT_TOOL_MCP_TOKEN")
        os.environ["WECHAT_TOOL_MCP_TOKEN"] = self.TEST_TOKEN

    def tearDown(self):
        if self._old_mcp_token is None:
            os.environ.pop("WECHAT_TOOL_MCP_TOKEN", None)
        else:
            os.environ["WECHAT_TOOL_MCP_TOKEN"] = self._old_mcp_token

    def _client(self, auth: bool = True) -> TestClient:
        from wechat_decrypt_tool.routers.mcp import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        if auth:
            client.headers.update({"Authorization": f"Bearer {self.TEST_TOKEN}"})
        return client

    def _rpc(self, method, params=None, request_id=1):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        return payload

    def test_initialize_and_tools_list(self):
        client = self._client()

        init_resp = client.post("/mcp", json=self._rpc("initialize"))
        self.assertEqual(init_resp.status_code, 200)
        init_payload = init_resp.json()["result"]
        self.assertEqual(init_payload["protocolVersion"], "2025-06-18")
        self.assertEqual(init_payload["serverInfo"]["name"], "wechat-data-analysis-mcp")

        tools_resp = client.post("/mcp", json=self._rpc("tools/list"))
        self.assertEqual(tools_resp.status_code, 200)
        tools = tools_resp.json()["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertIn("wechat.core.get_status", names)
        self.assertIn("wechat.chat.search_messages", names)
        self.assertIn("wechat.chat.list_search_senders", names)
        self.assertIn("wechat.chat.resolve_chat_history", names)
        self.assertIn("wechat.chat.resolve_app_message", names)
        self.assertIn("wechat.moments.get_remote_video_url", names)
        self.assertNotIn("search_memory", names)
        self.assertNotIn("transcribe_voice_message", names)
        self.assertNotIn("transcribe_audio_file", names)
        self.assertFalse(self.REMOVED_MCP_TOOLS & names)

    def test_mcp_requires_token(self):
        client = self._client(auth=False)

        resp = client.post("/mcp", json=self._rpc("ping"))

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers.get("www-authenticate"), "Bearer")

    def test_skill_endpoints_require_token(self):
        client = self._client(auth=False)

        for path in ("/mcp/skill/bundle", "/mcp/skill"):
            with self.subTest(path=path):
                resp = client.get(path)
                self.assertEqual(resp.status_code, 401)
                self.assertEqual(resp.headers.get("www-authenticate"), "Bearer")

    def test_mcp_rejects_invalid_token(self):
        client = self._client(auth=False)

        resp = client.post("/mcp", json=self._rpc("ping"), headers={"Authorization": "Bearer wrong-token"})

        self.assertEqual(resp.status_code, 401)

    def test_mcp_accepts_x_mcp_token_and_query_token(self):
        client = self._client(auth=False)

        header_resp = client.post("/mcp", json=self._rpc("ping"), headers={"X-MCP-Token": self.TEST_TOKEN})
        query_resp = client.post(f"/mcp?token={self.TEST_TOKEN}", json=self._rpc("ping"))

        self.assertEqual(header_resp.status_code, 200)
        self.assertEqual(header_resp.json()["result"], {})
        self.assertEqual(query_resp.status_code, 200)
        self.assertEqual(query_resp.json()["result"], {})

    def test_get_mcp_returns_method_not_allowed(self):
        client = self._client()

        resp = client.get("/mcp")

        self.assertEqual(resp.status_code, 405)
        self.assertEqual(resp.headers.get("allow"), "POST")

    def test_skill_bundle_can_be_loaded_over_http(self):
        client = self._client()

        resp = client.get("/mcp/skill/bundle")

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["name"], "wechat-mcp-copilot")
        self.assertIn("bundleText", payload)
        self.assertIn("WeChat MCP Copilot", payload["bundleText"])
        self.assertTrue(any(ref["path"] == "references/mobile.md" for ref in payload["references"]))
        self.assertFalse(any(ref["path"] == "references/system.md" for ref in payload["references"]))
        self.assertFalse(any(ref["path"] == "references/setup-system.md" for ref in payload["references"]))
        self.assertFalse(any(ref["path"] == "references/export.md" for ref in payload["references"]))
        for tool_name in self.REMOVED_MCP_TOOLS:
            self.assertNotIn(tool_name, payload["bundleText"])

    def test_skill_text_can_be_loaded_over_http(self):
        client = self._client()

        resp = client.get("/mcp/skill")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("WeChat MCP Copilot", resp.text)

    def test_ping_returns_empty_result(self):
        client = self._client()

        resp = client.post("/mcp", json=self._rpc("ping"))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["result"], {})

    def test_tools_list_supports_cursor_pagination(self):
        client = self._client()

        first_resp = client.post("/mcp", json=self._rpc("tools/list", {"limit": 3}))
        self.assertEqual(first_resp.status_code, 200)
        first = first_resp.json()["result"]
        self.assertEqual(first["count"], 3)
        self.assertEqual(len(first["tools"]), 3)
        self.assertIn("nextCursor", first)
        self.assertGreater(first["total"], 3)

        second_resp = client.post(
            "/mcp",
            json=self._rpc("tools/list", {"limit": 3, "cursor": first["nextCursor"]}),
        )
        second = second_resp.json()["result"]
        self.assertEqual(second["count"], 3)
        self.assertNotEqual(first["tools"][0]["name"], second["tools"][0]["name"])

    def test_core_list_tools_supports_package_filter_and_pagination(self):
        client = self._client()

        resp = client.post(
            "/mcp",
            json=self._rpc(
                "tools/call",
                {"name": "wechat.core.list_tools", "arguments": {"package": "wechat.media", "limit": 2}},
            ),
        )

        self.assertEqual(resp.status_code, 200)
        structured = resp.json()["result"]["structuredContent"]
        self.assertEqual(structured["status"], "success")
        self.assertEqual(structured["count"], 2)
        self.assertIn("nextCursor", structured)
        self.assertTrue(all(t["annotations"]["package"] == "wechat.media" for t in structured["tools"]))

    def test_tools_call_status_uses_structured_content(self):
        client = self._client()

        with patch("wechat_decrypt_tool.mcp.tools._list_decrypted_accounts", return_value=["wxid_test"]):
            resp = client.post(
                "/mcp",
                json=self._rpc(
                    "tools/call",
                    {"name": "wechat.core.get_status", "arguments": {}},
                ),
            )

        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"], "success")
        self.assertTrue(result["structuredContent"]["dbReady"])
        self.assertEqual(result["structuredContent"]["defaultAccount"], "wxid_test")
        self.assertEqual(result["content"][0]["type"], "text")

    def test_direct_tool_method_is_supported(self):
        client = self._client()

        with patch("wechat_decrypt_tool.mcp.tools._list_decrypted_accounts", return_value=[]):
            resp = client.post("/mcp", json=self._rpc("wechat.core.list_accounts"))

        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertTrue(result["isError"])
        structured = result["structuredContent"]
        self.assertEqual(structured["status"], "error")
        self.assertEqual(structured["accounts"], [])

    def test_notification_returns_accepted_empty_body(self):
        client = self._client()

        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.text, "")

    def test_json_rpc_response_input_returns_accepted_empty_body(self):
        client = self._client()

        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 99, "result": {"ok": True}})

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.text, "")

    def test_notification_batch_returns_accepted_empty_body(self):
        client = self._client()

        resp = client.post(
            "/mcp",
            json=[
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
            ],
        )

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.text, "")

    def test_empty_batch_returns_invalid_request(self):
        client = self._client()

        resp = client.post("/mcp", json=[])

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"]["code"], -32600)

    def test_non_string_method_returns_invalid_request(self):
        client = self._client()

        resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": 1})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"]["code"], -32600)

    def test_batch_mixed_requests_and_notifications(self):
        client = self._client()

        with patch("wechat_decrypt_tool.mcp.tools._list_decrypted_accounts", return_value=["wxid_test"]):
            resp = client.post(
                "/mcp",
                json=[
                    self._rpc("ping", request_id=1),
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    self._rpc("wechat.core.get_status", request_id=2),
                ],
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["result"], {})
        self.assertEqual(payload[1]["result"]["structuredContent"]["defaultAccount"], "wxid_test")

    def test_unknown_tool_returns_json_rpc_error(self):
        client = self._client()

        resp = client.post(
            "/mcp",
            json=self._rpc(
                "tools/call",
                {"name": "wechat.nope", "arguments": {}},
            ),
        )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["error"]["code"], -32601)

    def test_removed_mcp_tools_are_not_listed_or_callable(self):
        client = self._client()

        tools_resp = client.post("/mcp", json=self._rpc("tools/list"))
        self.assertEqual(tools_resp.status_code, 200)
        names = {tool["name"] for tool in tools_resp.json()["result"]["tools"]}
        self.assertFalse(self.REMOVED_MCP_TOOLS & names)

        for tool_name in sorted(self.REMOVED_MCP_TOOLS):
            with self.subTest(tool_name=tool_name):
                direct_resp = client.post("/mcp", json=self._rpc(tool_name, {}))
                call_resp = client.post(
                    "/mcp",
                    json=self._rpc("tools/call", {"name": tool_name, "arguments": {}}),
                )
                self.assertEqual(direct_resp.status_code, 200)
                self.assertEqual(call_resp.status_code, 200)
                self.assertEqual(direct_resp.json()["error"]["code"], -32601)
                self.assertEqual(call_resp.json()["error"]["code"], -32601)

    def test_missing_tool_name_returns_invalid_params(self):
        client = self._client()

        resp = client.post("/mcp", json=self._rpc("tools/call", {"arguments": {}}))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"]["code"], -32602)

    def test_non_object_arguments_returns_invalid_params(self):
        client = self._client()

        resp = client.post(
            "/mcp",
            json=self._rpc("tools/call", {"name": "wechat.core.get_status", "arguments": []}),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"]["code"], -32602)

    def test_media_url_helpers_pass_supported_parameters(self):
        client = self._client()

        image_resp = client.post(
            "/mcp",
            json=self._rpc(
                "wechat.media.get_chat_image_url",
                {
                    "md5": "abc",
                    "file_id": "fid",
                    "msg_svr_id": 123,
                    "username": "wxid_a",
                    "account": "wxid_acc",
                    "deep_scan": True,
                    "prefer_live": True,
                },
            ),
        )
        image = image_resp.json()["result"]["structuredContent"]
        self.assertIn("/api/chat/media/image?", image["url"])
        self.assertEqual(image["params"]["server_id"], 123)
        self.assertEqual(image["params"]["file_id"], "fid")
        self.assertTrue(image["params"]["deep_scan"])
        self.assertTrue(image["params"]["prefer_live"])

        moments_resp = client.post(
            "/mcp",
            json=self._rpc(
                "wechat.moments.get_media_url",
                {"tid": "post-a", "media_id": "media-a", "md5": "deadbeef", "use_cache": 1},
            ),
        )
        moments = moments_resp.json()["result"]["structuredContent"]
        self.assertIn("/api/sns/media?", moments["url"])
        self.assertEqual(moments["params"]["post_id"], "post-a")
        self.assertEqual(moments["params"]["media_id"], "media-a")
        self.assertNotIn("use_cache", moments["params"])
        self.assertNotIn("use_cache", moments["url"])

    def test_completed_mcp_packages_and_mobile_facade_are_listed(self):
        client = self._client()

        resp = client.post("/mcp", json=self._rpc("tools/list"))

        self.assertEqual(resp.status_code, 200)
        tools = resp.json()["result"]["tools"]
        names = {tool["name"] for tool in tools}
        expected = {
            "wechat.media.get_decrypted_resource_url",
            "wechat.media.get_proxy_image_url",
            "wechat.media.get_favicon_url",
            "wechat.mobile.get_overview",
            "wechat.mobile.resolve_target",
            "wechat.mobile.search_chat",
            "wechat.mobile.get_chat_context",
            "wechat.mobile.search_moments",
            "wechat.mobile.get_media_links",
        }
        self.assertTrue(expected.issubset(names))
        self.assertFalse(self.REMOVED_MCP_TOOLS & names)
        self.assertNotIn("search_memory", names)
        self.assertNotIn("transcribe_voice_message", names)
        self.assertNotIn("transcribe_audio_file", names)

        packages = {tool["annotations"]["package"] for tool in tools}
        self.assertTrue({"wechat.core", "wechat.mobile", "wechat.media"}.issubset(packages))
        self.assertFalse({"wechat.setup", "wechat.export", "wechat.editing", "wechat.system", "wechat.admin"} & packages)

    def test_new_url_helpers_return_urls_and_params(self):
        client = self._client()

        checks = [
            (
                "wechat.media.get_decrypted_resource_url",
                {"account": "wxid_a", "md5": "a" * 32},
                "url",
                "/api/media/resource/",
            ),
        ]

        for tool_name, args, url_key, path_part in checks:
            with self.subTest(tool_name=tool_name):
                resp = client.post("/mcp", json=self._rpc(tool_name, args))
                self.assertEqual(resp.status_code, 200)
                structured = resp.json()["result"]["structuredContent"]
                self.assertEqual(structured["status"], "success")
                self.assertIn(path_part, structured[url_key])

    def test_exposed_mcp_tools_are_read_only(self):
        client = self._client()

        resp = client.post("/mcp", json=self._rpc("tools/list"))

        self.assertEqual(resp.status_code, 200)
        tools = resp.json()["result"]["tools"]
        self.assertTrue(tools)
        for tool in tools:
            with self.subTest(tool_name=tool["name"]):
                annotations = tool.get("annotations") or {}
                self.assertTrue(annotations.get("readOnlyHint"))
                self.assertFalse(annotations.get("destructiveHint"))

    def test_analytics_schema_does_not_expose_refresh(self):
        client = self._client()

        resp = client.post("/mcp", json=self._rpc("tools/list"))

        self.assertEqual(resp.status_code, 200)
        tools = {tool["name"]: tool for tool in resp.json()["result"]["tools"]}
        for tool_name in [
            "wechat.analytics.get_wrapped_meta",
            "wechat.analytics.get_wrapped_card",
            "wechat.analytics.get_wrapped_annual",
        ]:
            with self.subTest(tool_name=tool_name):
                properties = tools[tool_name]["inputSchema"].get("properties") or {}
                self.assertNotIn("refresh", properties)

    def test_analytics_tools_are_cache_only(self):
        client = self._client()

        class FakeWrappedService:
            _CACHE_VERSION = 26
            _IMPLEMENTED_UPTO_ID = 7
            _WRAPPED_CARD_MANIFEST = ({"id": 0, "title": "Overview"},)

            @staticmethod
            def _default_year():
                return 2025

            def build_wrapped_annual_meta(self, **_kwargs):
                raise AssertionError("MCP analytics must not build wrapped meta.")

            def build_wrapped_annual_card(self, **_kwargs):
                raise AssertionError("MCP analytics must not build wrapped card.")

            def build_wrapped_annual_response(self, **_kwargs):
                raise AssertionError("MCP analytics must not build wrapped annual data.")

        with tempfile.TemporaryDirectory() as tmp:
            account_dir = Path(tmp) / "wxid_a"
            account_dir.mkdir()
            with patch("wechat_decrypt_tool.mcp.tools._resolve_account_dir", return_value=account_dir), patch(
                "wechat_decrypt_tool.mcp.tools._wrapped_service", return_value=FakeWrappedService()
            ):
                card_resp = client.post(
                    "/mcp",
                    json=self._rpc("wechat.analytics.get_wrapped_card", {"account": "wxid_a", "year": 2025, "card_id": 0}),
                )
                annual_resp = client.post(
                    "/mcp",
                    json=self._rpc("wechat.analytics.get_wrapped_annual", {"account": "wxid_a", "year": 2025}),
                )

            self.assertFalse((account_dir / "_wrapped" / "cache").exists())

        for resp in [card_resp, annual_resp]:
            self.assertEqual(resp.status_code, 200)
            result = resp.json()["result"]
            self.assertTrue(result["isError"])
            structured = result["structuredContent"]
            self.assertEqual(structured["status"], "error")
            self.assertTrue(structured["cacheOnly"])
            self.assertEqual(structured["message"], "Wrapped cache not found. Open the app to generate it first.")

    def test_mobile_overview_uses_compact_facade(self):
        client = self._client()

        with patch("wechat_decrypt_tool.mcp.tools._list_decrypted_accounts", return_value=["wxid_a"]), patch(
            "wechat_decrypt_tool.mcp.tools._get_account_info",
            return_value={"status": "success", "account": "wxid_a", "databaseCount": 3},
        ), patch(
            "wechat_decrypt_tool.mcp.tools._list_sessions",
            return_value={"status": "success", "sessions": [{"username": "friend", "displayName": "Friend"}]},
        ):
            resp = client.post(
                "/mcp",
                json=self._rpc("wechat.mobile.get_overview", {"account": "wxid_a", "session_limit": 5}),
            )

        self.assertEqual(resp.status_code, 200)
        structured = resp.json()["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertTrue(structured["ready"])
        self.assertEqual(structured["defaultAccount"], "wxid_a")
        self.assertIn("wechat.mobile.search_chat", structured["suggestedTools"])
        self.assertNotIn("wechat.mobile.export_job", structured["suggestedTools"])
        self.assertNotIn("realtime", structured["health"])
        self.assertNotIn("indexes", structured["health"])

    def test_mobile_overview_does_not_expose_realtime_status(self):
        client = self._client()

        with patch("wechat_decrypt_tool.mcp.tools._list_decrypted_accounts", return_value=["wxid_a"]), patch(
            "wechat_decrypt_tool.mcp.tools._get_account_info",
            return_value={"status": "success", "account": "wxid_a", "databaseCount": 3},
        ), patch(
            "wechat_decrypt_tool.mcp.tools._list_sessions",
            return_value={"status": "success", "sessions": [{"username": "friend", "displayName": "Friend"}]},
        ):
            resp = client.post(
                "/mcp",
                json=self._rpc("wechat.mobile.get_overview", {"account": "wxid_a", "session_limit": 5}),
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertNotIn("error", payload)
        structured = payload["result"]["structuredContent"]
        self.assertNotIn("realtime", structured["health"])
        self.assertNotIn("indexes", structured["health"])

    def test_mobile_resolve_target_normalizes_candidates(self):
        client = self._client()

        with patch(
            "wechat_decrypt_tool.mcp.tools._resolve_contact",
            return_value={"status": "success", "candidates": [{"username": "wxid_friend", "remark": "Alice", "confidence": 92}]},
        ), patch(
            "wechat_decrypt_tool.mcp.tools._resolve_session",
            return_value={"status": "success", "candidates": [{"username": "chatroom", "displayName": "Alice Group", "confidence": 75}]},
        ), patch(
            "wechat_decrypt_tool.mcp.tools._sns_users", return_value={"status": "success", "users": []}
        ), patch(
            "wechat_decrypt_tool.mcp.tools._biz_accounts", return_value={"status": "success", "accounts": []}
        ):
            resp = client.post("/mcp", json=self._rpc("wechat.mobile.resolve_target", {"query": "Alice", "limit": 5}))

        self.assertEqual(resp.status_code, 200)
        structured = resp.json()["result"]["structuredContent"]
        self.assertEqual(structured["status"], "success")
        self.assertEqual(structured["best"]["username"], "wxid_friend")
        self.assertEqual(structured["best"]["kind"], "contact")

    def test_mobile_media_links_does_not_fetch_binary_content(self):
        client = self._client()

        resp = client.post(
            "/mcp",
            json=self._rpc(
                "wechat.mobile.get_media_links",
                {"kind": "favicon", "url": "https://example.com/article", "max_items": 5},
            ),
        )

        self.assertEqual(resp.status_code, 200)
        structured = resp.json()["result"]["structuredContent"]
        self.assertEqual(structured["status"], "success")
        self.assertEqual(structured["resources"][0]["kind"], "favicon")
        self.assertIn("/api/chat/media/favicon?", structured["resources"][0]["url"])

    def test_invalid_json_returns_parse_error(self):
        client = self._client()

        resp = client.post("/mcp", content="{not-json", headers={"Content-Type": "application/json"})

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
