"""Device command bus for serialized Collector <-> API coordination.

PromptID: ADMS-Frontend-FullControlUX-002

Coordinates browser/API-triggered device operations (such as terminal account
creation) with the running Collector engine over MQTT. Ensures:
  1. Zero competing/concurrent ZK device connections.
  2. The active Collector executes the command using its verified device handle.
  3. Strict timeout, error propagation, and failure recovery.
"""

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt
from app.config import Config

log = logging.getLogger(__name__)

CMD_REQUEST_TOPIC = "adms/device/command/request"
CMD_RESPONSE_PREFIX = "adms/device/command/response/"


class DeviceCommandError(Exception):
    """Raised when a device command fails or times out."""


class DeviceCommandBus:
    """MQTT-backed synchronous command-response client for the API process."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._client: Optional[mqtt.Client] = None
        self._lock = threading.Lock()
        self._pending: Dict[str, Dict[str, Any]] = {}
        self.connected = False

    def _ensure_connected(self) -> None:
        with self._lock:
            if self._client is not None and self.connected:
                return
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"adms-api-cmd-{uuid.uuid4().hex[:8]}",
            )
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            try:
                client.connect(self.host, self.port, keepalive=60)
                client.loop_start()
                self._client = client
                # Wait briefly for connection
                for _ in range(20):
                    if self.connected:
                        break
                    time.sleep(0.05)
            except Exception as e:
                log.warning("DeviceCommandBus connect failed: %s", e)
                self.connected = False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            client.subscribe(f"{CMD_RESPONSE_PREFIX}+", qos=1)
            log.info("DeviceCommandBus connected and subscribed to responses")
        else:
            self.connected = False

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.connected = False

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            command_id = payload.get("command_id")
            if command_id and command_id in self._pending:
                entry = self._pending[command_id]
                entry["response"] = payload
                entry["event"].set()
        except Exception as e:
            log.warning("DeviceCommandBus error processing response: %s", e)

    def execute(self, action: str, params: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """Dispatches a command to the Collector and waits synchronously for the response."""
        self._ensure_connected()
        if not self._client or not self.connected:
            raise DeviceCommandError("MQTT broker unavailable; cannot reach terminal collector")

        command_id = uuid.uuid4().hex
        event = threading.Event()
        entry = {"event": event, "response": None}
        self._pending[command_id] = entry

        req_payload = {
            "command_id": command_id,
            "action": action,
            "params": params,
            "timestamp": time.time(),
        }

        try:
            self._client.publish(CMD_REQUEST_TOPIC, json.dumps(req_payload), qos=1)
            if not event.wait(timeout=timeout):
                raise DeviceCommandError(
                    f"Terminal operation timed out after {timeout:.1f}s. "
                    "Ensure the collector is online and connected to the device."
                )
            res = entry["response"]
            if not res or not res.get("success"):
                err_msg = res.get("error") if res else "Unknown collector error"
                raise DeviceCommandError(err_msg)
            return res.get("result", {})
        finally:
            self._pending.pop(command_id, None)

    def stop(self) -> None:
        with self._lock:
            if self._client:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:
                    pass
                self._client = None
                self.connected = False


_cmd_bus: Optional[DeviceCommandBus] = None
_cmd_bus_lock = threading.Lock()


def get_command_bus(cfg: Optional[Config] = None) -> DeviceCommandBus:
    global _cmd_bus
    with _cmd_bus_lock:
        if _cmd_bus is None:
            host = os.getenv("MQTT_HOST", "mqtt" if cfg is None else cfg.mqtt_host)
            port = int(os.getenv("MQTT_PORT", "1883" if cfg is None else str(cfg.mqtt_port)))
            _cmd_bus = DeviceCommandBus(host, port)
    return _cmd_bus
