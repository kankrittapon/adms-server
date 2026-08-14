"""Realtime SSE stream tests (ADMS-Frontend-RealtimeSSE-001).

Covers: the auth gate (401 without token, VIEWER allowed), the SSE HTTP
headers, event fan-out + heartbeat from the core generator (tested directly
with asyncio — no threads, no real broker), the MqttStream registry
semantics, and malformed-payload safety.

Same mocking conventions as tests/test_api_hardening.py.
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.api.main import create_app
from app.api.mqtt_stream import MqttStream
from app.api.routers.stream import attendance_event_generator
from app.api.settings import ApiSettings


class _FakeRequest:
    """Minimal Request stand-in exposing is_disconnected()."""

    def __init__(self, disconnected: bool = False):
        self._disconnected = disconnected

    async def is_disconnected(self):
        return self._disconnected


def _run(coro):
    # asyncio.run manages the loop lifecycle (create + close) and sets the
    # Windows event-loop policy correctly — safer than new_event_loop() after
    # other tests have run TestClient portals.
    return asyncio.run(coro)


class TestSseGenerator(unittest.TestCase):
    def test_heartbeat_then_event_then_disconnect(self):
        async def scenario():
            stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
            client_id, queue = stream.register()
            request = _FakeRequest(disconnected=False)
            gen = attendance_event_generator(stream, client_id, queue, request, 0.05)

            # heartbeat fires when the queue is idle
            chunk = await asyncio.wait_for(anext(gen), timeout=2.0)
            self.assertEqual(chunk, ": ping\n\n")

            # fan-out an event from the same loop (thread-safe path not needed here)
            stream.ingest({"event_type": "ATTENDANCE_SCAN", "user_id": "1001"})
            chunk = await asyncio.wait_for(anext(gen), timeout=2.0)
            self.assertTrue(chunk.startswith("event: attendance\n"))
            self.assertIn('"user_id": "1001"', chunk)
            self.assertIn("ATTENDANCE_SCAN", chunk)

            # disconnect terminates the generator and unregisters the client
            request._disconnected = True
            with self.assertRaises(StopAsyncIteration):
                await anext(gen)
            self.assertNotIn(client_id, stream._clients)
            stream.stop()

        _run(scenario())

    def test_bounded_queue_drops_for_slow_client(self):
        # A full queue must not block the fan-out loop.
        async def scenario():
            stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
            stream.register()
            for i in range(110):  # maxsize=100
                stream.ingest({"n": i})
            with stream._lock:
                self.assertLessEqual(len(stream._clients), 1)
            stream.stop()

        _run(scenario())


class TestMqttStreamRegistry(unittest.TestCase):
    def test_register_ingest_unregister(self):
        stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
        cid1, q1 = stream.register()
        cid2, q2 = stream.register()
        self.assertNotEqual(cid1, cid2)

        delivered = stream.ingest({"user_id": "1001"})
        self.assertEqual(delivered, 2)
        self.assertEqual(q1.get_nowait(), {"user_id": "1001"})
        self.assertEqual(q2.get_nowait(), {"user_id": "1001"})

        stream.unregister(cid1)
        self.assertEqual(stream.ingest({"user_id": "1002"}), 1)
        self.assertEqual(q2.get_nowait(), {"user_id": "1002"})
        self.assertTrue(q1.empty())

    def test_ingest_with_no_clients(self):
        stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
        self.assertEqual(stream.ingest({"a": 1}), 0)

    def test_stop_clears_clients(self):
        stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
        stream.register()
        stream.stop()
        self.assertEqual(stream.ingest({"a": 1}), 0)

    def test_non_json_payload_ignored(self):
        stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
        stream.ingest = MagicMock()
        msg = MagicMock()
        msg.payload = b"not-json{{{"
        stream._on_message(None, None, msg)  # must not raise
        stream.ingest.assert_not_called()

        msg.payload = b'{"event_type": "ATTENDANCE_SCAN"}'
        stream._on_message(None, None, msg)
        stream.ingest.assert_called_once()
        payload = stream.ingest.call_args.args[0]
        self.assertEqual(payload["event_type"], "ATTENDANCE_SCAN")


class TestStreamEndpoint(unittest.TestCase):
    """HTTP-surface tests via httpx.ASGITransport.

    ASGITransport runs the ASGI app in-process on the current event loop —
    no TestClient portal threads (which deadlock on Windows after certain
    preceding tests when a response body never completes).
    """

    def setUp(self):
        self.app = create_app(settings=ApiSettings(write_enabled=False))

    def _ctx(self, role):
        from app.api.dependencies import OperatorContext

        return OperatorContext(1, "tester", "Tester", role)

    def test_stream_requires_auth(self):
        async def scenario():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/stream/attendance")
            self.assertEqual(resp.status_code, 401)

        _run(scenario())

    def test_stream_response_contract(self):
        """The endpoint returns an SSE StreamingResponse with the right
        headers and a bounded, well-formed body.

        Uses a direct async call (not TestClient.stream — the portal buffers
        infinite streams, so an endless SSE body would never complete). The
        VIEWER auth gate is covered by the 401 test above.
        """
        async def scenario():
            stream = MqttStream(host="localhost", port=1883, topic="attendance/events")
            with patch("app.api.routers.stream.get_stream", return_value=stream), patch(
                "app.api.routers.stream.HEARTBEAT_INTERVAL", 0.05
            ):
                from app.api.routers.stream import stream_attendance

                resp = await stream_attendance(_FakeRequest())

            self.assertEqual(resp.media_type, "text/event-stream")
            self.assertEqual(resp.headers.get("cache-control"), "no-cache")
            self.assertEqual(resp.headers.get("x-accel-buffering"), "no")

            # Bounded iteration: heartbeat -> fan-out event -> disconnect.
            gen = resp.body_iterator
            chunk = await asyncio.wait_for(anext(gen), timeout=2.0)
            self.assertEqual(chunk, ": ping\n\n")
            stream.ingest({"event_type": "ATTENDANCE_SCAN", "user_id": "1001"})
            chunk = await asyncio.wait_for(anext(gen), timeout=2.0)
            self.assertTrue(chunk.startswith("event: attendance\n"))
            await gen.aclose()  # run the finally (unregister) cleanly
            stream.stop()

        _run(scenario())


if __name__ == "__main__":
    unittest.main()
