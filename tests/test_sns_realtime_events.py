import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool import sns_realtime_autosync
from wechat_decrypt_tool.routers import sns as sns_router


class _FakeRequest:
    async def is_disconnected(self):
        return False


class TestSnsRealtimeEvents(unittest.TestCase):
    def test_sse_route_is_registered_and_frame_has_named_event(self):
        route = next(
            route
            for route in sns_router.router.routes
            if getattr(route, "path", "") == "/api/sns/realtime/events"
        )
        self.assertIn("GET", route.methods)

        frame = sns_router._format_sns_sse_event({
            "type": "change",
            "sequence": 7,
            "account": "wxid_test",
            "snapshotVersion": "v2",
        })
        self.assertIn("id: 7\n", frame)
        self.assertIn("event: change\n", frame)
        payload = json.loads(frame.split("data: ", 1)[1].strip())
        self.assertEqual(payload.get("snapshotVersion"), "v2")

    def test_subscribe_ready_registers_capacity_one_queue(self):
        async def scenario():
            service = sns_realtime_autosync.SnsRealtimeAutoSyncService()

            def ensure_account(account, *, schedule_startup):
                del schedule_startup
                service._states.setdefault(
                    account,
                    sns_realtime_autosync._AccountState(),
                ).watcher_available = True
                return {"available": True}

            with (
                mock.patch.object(
                    service,
                    "ensure_account",
                    side_effect=ensure_account,
                ),
                mock.patch.object(service, "_current_snapshot_version", return_value="version-1"),
            ):
                token, queue, ready = service.subscribe(
                    "wxid_test",
                    loop=asyncio.get_running_loop(),
                )

            self.assertEqual(queue.maxsize, 1)
            self.assertEqual(ready.get("type"), "ready")
            self.assertTrue(ready.get("watcherAvailable"))
            self.assertEqual(ready.get("snapshotVersion"), "version-1")
            self.assertIn(token, service._states["wxid_test"].subscribers)
            service.unsubscribe("wxid_test", token)
            self.assertNotIn(token, service._states["wxid_test"].subscribers)

        asyncio.run(scenario())

    def test_stream_unsubscribes_when_generator_closes(self):
        async def scenario():
            queue = asyncio.Queue(maxsize=1)
            ready = {
                "type": "ready",
                "sequence": 0,
                "account": "wxid_test",
                "snapshotVersion": "",
                "watcherAvailable": True,
            }
            with (
                mock.patch.object(sns_router, "_resolve_account_dir", return_value=Path("C:/output/wxid_test")),
                mock.patch.object(
                    sns_router.SNS_REALTIME_AUTOSYNC,
                    "subscribe",
                    return_value=("token-1", queue, ready),
                ),
                mock.patch.object(sns_router.SNS_REALTIME_AUTOSYNC, "unsubscribe") as unsubscribe,
            ):
                response = await sns_router.stream_sns_realtime_events(
                    _FakeRequest(),
                    account="wxid_test",
                )
                iterator = response.body_iterator
                first = await anext(iterator)
                self.assertIn("event: ready", first)

                await queue.put({
                    "type": "change",
                    "sequence": 1,
                    "account": "wxid_test",
                    "changed": 1,
                })
                second = await anext(iterator)
                self.assertIn("event: change", second)
                await iterator.aclose()

            unsubscribe.assert_called_once_with("wxid_test", "token-1")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
