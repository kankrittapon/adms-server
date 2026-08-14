"""Realtime attendance event fan-out for the API process.

PromptID: ADMS-Frontend-RealtimeSSE-001

Bridges the Collector's MQTT ``attendance/events`` topic to connected SSE
clients (``GET /api/v1/stream/attendance``). The API process runs a single
uvicorn worker, so a process-local singleton + in-process queues is accurate.

Design notes:
  - The MQTT client is started lazily on the first SSE request (never on app
    import), so API tests that never open the stream never touch the broker.
  - Fan-out is thread-safe: paho callbacks run on paho's network thread; we
    schedule ``put_nowait`` onto the client's event loop via
    ``call_soon_threadsafe`` (falling back to a direct put for same-loop
    callers, e.g. tests).
  - This is a live-only channel: no replay/backfill. Events published before
    a client subscribes are intentionally not delivered.
"""

import asyncio
import json
import logging
import os
import threading
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)

# Bounded queue per SSE client: slow consumers drop events rather than
# blocking the fan-out loop (events remain retrievable via GET attendance).
CLIENT_QUEUE_MAX = 100


class MqttStream:
    """MQTT -> SSE fan-out bridge (singleton per API process)."""

    def __init__(self, host: str, port: int, topic: str):
        self.host = host
        self.port = port
        self.topic = topic
        self._clients: Dict[int, asyncio.Queue] = {}
        self._lock = threading.Lock()
        self._client: Optional[mqtt.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._next_id = 1
        self.connected = False

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def ensure_started(self) -> None:
        """Start the MQTT subscriber exactly once (idempotent).

        Must be called from an async context (the first SSE request); the
        running loop is captured so fan-out can schedule thread-safely.
        """
        with self._lock:
            if self._client is not None:
                return
            self._loop = asyncio.get_running_loop()
            try:
                client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id="adms-api-stream",
                )
                client.on_connect = self._on_connect
                client.on_message = self._on_message
                client.connect(self.host, self.port, keepalive=60)
                client.loop_start()
                self._client = client
                log.info(
                    "MQTT stream subscriber starting %s:%s topic=%s",
                    self.host,
                    self.port,
                    self.topic,
                )
            except Exception as e:  # pragma: no cover - broker down at boot
                log.warning("MQTT stream connect warning: %s", e)
                self._client = None
                self.connected = False

    def stop(self) -> None:
        """Stop the subscriber and drop all clients (idempotent)."""
        with self._lock:
            self._clients.clear()
            client, self._client = self._client, None
            self.connected = False
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as e:  # pragma: no cover
                log.warning("MQTT stream stop error: %s", e)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            client.subscribe(self.topic, qos=1)
            log.info("MQTT stream subscribed to %s", self.topic)
        else:
            log.warning("MQTT stream connect rc=%s", rc)
            self.connected = False

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except Exception:
            log.warning("MQTT stream: non-JSON payload ignored")
            return
        if isinstance(payload, dict):
            self.ingest(payload)

    # ------------------------------------------------------------------ #
    # fan-out
    # ------------------------------------------------------------------ #
    def ingest(self, payload: Dict[str, Any]) -> int:
        """Fan a payload out to every connected SSE client (thread-safe).

        Returns the number of clients that received it. The queue put is
        always scheduled onto the client loop via call_soon_threadsafe, so
        this is safe from paho's network thread, the API loop, or tests.
        """
        delivered = 0
        with self._lock:
            clients = list(self._clients.values())
            loop = self._loop
        for q in clients:
            try:
                if loop is not None:
                    loop.call_soon_threadsafe(q.put_nowait, payload)
                else:
                    q.put_nowait(payload)
                delivered += 1
            except Exception:
                pass
        return delivered

    # ------------------------------------------------------------------ #
    # client registry (async side)
    # ------------------------------------------------------------------ #
    def register(self):
        """Register a new SSE client queue; returns (client_id, queue)."""
        q: asyncio.Queue = asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)
        with self._lock:
            cid = self._next_id
            self._next_id += 1
            self._clients[cid] = q
        return cid, q

    def unregister(self, cid: int) -> None:
        with self._lock:
            self._clients.pop(cid, None)


_stream: Optional[MqttStream] = None
_stream_lock = threading.Lock()


def get_stream() -> MqttStream:
    """Process-local singleton accessor (single uvicorn worker)."""
    global _stream
    with _stream_lock:
        if _stream is None:
            _stream = MqttStream(
                host=os.getenv("MQTT_HOST", "mqtt"),
                port=int(os.getenv("MQTT_PORT", "1883")),
                topic=os.getenv("MQTT_TOPIC", "attendance/events"),
            )
    return _stream


def reset_stream() -> None:
    """Test hook: stop and drop the singleton so tests start clean."""
    global _stream
    with _stream_lock:
        if _stream is not None:
            _stream.stop()
        _stream = None
