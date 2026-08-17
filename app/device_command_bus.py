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
    """Raised when a device command fails or times out.

    IMPORTANT: a timeout raising this exception means UNKNOWN OUTCOME, not
    guaranteed failure — the Collector may have already executed the command
    on the physical device; the response was merely lost or delayed past the
    caller's wait window. Callers dispatching commands whose device-side
    effect can be independently re-verified (e.g. terminal-account creation,
    via a roster read-back) MUST treat a timeout as "needs reconciliation",
    not as proof nothing happened. See app.enrollment.create_or_reconcile_
    terminal_account, which is designed around exactly this uncertainty.
    """

    def __init__(self, message: str, timed_out: bool = False, error_code: Optional[str] = None):
        super().__init__(message)
        self.timed_out = timed_out
        self.error_code = error_code


class DeviceCommandBusy(DeviceCommandError):
    """Raised when a command is already in flight for the same dedupe_key
    (e.g. the same enrollment_id). Prevents two concurrent set_user() calls
    from racing on the Collector's single, non-thread-safe device connection
    — a double-click or an eager retry issued before the first command's
    response arrives must not reach the device twice."""


class DeviceCommandBus:
    """MQTT-backed synchronous command-response client for the API process."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._client: Optional[mqtt.Client] = None
        self._lock = threading.Lock()
        self._pending: Dict[str, Dict[str, Any]] = {}
        # Per-dedupe-key in-flight tracking (e.g. "enrollment:2") — a second
        # execute() call with the same key while one is outstanding is
        # rejected immediately rather than dispatched, so at most one
        # set_user()-class command reaches the device per key at a time.
        #
        # Each entry is {"command_id": ..., "expires_at": <monotonic time>}.
        # IMPORTANT: this is NOT released when the caller's own wait times
        # out — the Collector may still genuinely be executing the command
        # (it has no idea the caller gave up). Releasing it immediately on a
        # client-side timeout would let an eager retry/double-click dispatch
        # a second command while the first is still physically in flight on
        # the device. It is released when: (a) the response actually arrives
        # (on time or late — see _on_message), or (b) `expires_at` has
        # passed, as a bounded safety net against a permanently stuck key if
        # the response is truly lost forever (e.g. Collector crash).
        self._inflight_keys: Dict[str, Dict[str, Any]] = {}
        # command_id -> dedupe_key, kept alive past a client-side timeout
        # (unlike _pending) so a late response can still find and release
        # the right _inflight_keys entry.
        self._command_dedupe_keys: Dict[str, str] = {}
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

    def _release_dedupe_key_for_command(self, command_id: str) -> None:
        """Releases the in-flight dedupe key associated with command_id, if
        any — called whenever we learn the command has truly finished
        (on-time OR late response). Thread-safe."""
        with self._lock:
            dedupe_key = self._command_dedupe_keys.pop(command_id, None)
            if dedupe_key is not None:
                entry = self._inflight_keys.get(dedupe_key)
                if entry is not None and entry.get("command_id") == command_id:
                    self._inflight_keys.pop(dedupe_key, None)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            command_id = payload.get("command_id")
            if command_id and command_id in self._pending:
                entry = self._pending[command_id]
                entry["response"] = payload
                entry["event"].set()
                self._release_dedupe_key_for_command(command_id)
            elif command_id:
                # Late response for a command the caller already timed out on
                # (its pending entry was popped). The caller can no longer act
                # on this directly, but it's valuable diagnostic evidence that
                # the timeout was scenario C (late completion) rather than a
                # genuine failure — log it instead of silently discarding it.
                # Also release the dedupe key now that we know the command is
                # truly finished, so a subsequent retry isn't stuck waiting
                # out the full safety-net expiry unnecessarily.
                log.warning(
                    "DeviceCommandBus received a response for command_id=%s "
                    "with no matching pending entry (likely a late response "
                    "after the caller's timeout) — success=%s",
                    command_id, payload.get("success"),
                )
                self._release_dedupe_key_for_command(command_id)
        except Exception as e:
            log.warning("DeviceCommandBus error processing response: %s", e)

    def execute(
        self,
        action: str,
        params: Dict[str, Any],
        timeout: float = 10.0,
        dedupe_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches a command to the Collector and waits synchronously for
        the response.

        dedupe_key: when provided (e.g. f"enrollment:{enrollment_id}"), a
        second call with the same key while one is still in flight raises
        DeviceCommandBusy immediately instead of dispatching a second
        command — this is defense-in-depth against concurrent device I/O,
        independent of (and in addition to) the DB-level row lock the caller
        should also be holding for anything that mutates device state. The
        key is held until the response actually arrives (on time or late),
        not merely until this call's own wait expires — see the
        _inflight_keys docstring in __init__ for why.
        """
        self._ensure_connected()
        if not self._client or not self.connected:
            raise DeviceCommandError(
                "MQTT broker unavailable; cannot reach terminal collector",
                error_code="DEVICE_UNAVAILABLE",
            )

        command_id = uuid.uuid4().hex
        event = threading.Event()
        entry = {"event": event, "response": None}
        self._pending[command_id] = entry

        # Check-and-reserve the dedupe key atomically under one lock
        # acquisition — checking busy-ness and registering this command_id
        # as the new holder must not be two separate critical sections, or
        # two concurrent callers could both observe "available" and both
        # proceed to dispatch (the exact double-submit this key exists to
        # prevent).
        if dedupe_key is not None:
            with self._lock:
                now = time.time()
                existing = self._inflight_keys.get(dedupe_key)
                if existing is not None:
                    if existing["expires_at"] > now:
                        del self._pending[command_id]
                        raise DeviceCommandBusy(
                            "a terminal command is already in progress for %s "
                            "(command_id=%s) — please wait for it to finish "
                            "rather than retrying" % (dedupe_key, existing["command_id"]),
                            error_code="DEVICE_COMMAND_IN_PROGRESS",
                        )
                    # Safety-net expiry passed with no response ever having
                    # arrived (Collector crash or similarly total loss) —
                    # auto-recover: treat the key as available again.
                    log.warning(
                        "DeviceCommandBus: in-flight key %s (command_id=%s) "
                        "exceeded its safety-net expiry with no response ever "
                        "received — releasing it to allow a new attempt.",
                        dedupe_key, existing["command_id"],
                    )
                    self._command_dedupe_keys.pop(existing["command_id"], None)
                # expires_at bounds how long this key can remain held even if
                # the response is lost forever — derived from this call's own
                # timeout budget, which already represents "the maximum time
                # this operation could legitimately take" (see
                # app.enrollment's derived timing constants for
                # CREATE_TERMINAL_ACCOUNT).
                self._inflight_keys[dedupe_key] = {"command_id": command_id, "expires_at": now + timeout}
                self._command_dedupe_keys[command_id] = dedupe_key

        req_payload = {
            "command_id": command_id,
            "action": action,
            "params": params,
            "timestamp": time.time(),
        }

        try:
            self._client.publish(CMD_REQUEST_TOPIC, json.dumps(req_payload), qos=1)
            if not event.wait(timeout=timeout):
                # UNKNOWN OUTCOME, not guaranteed failure — see DeviceCommandError
                # docstring. We stop waiting here, but the Collector may still be
                # executing (or may have already completed) the command; if its
                # response arrives after this point it is logged (and releases
                # the dedupe key then), not silently dropped — the dedupe key
                # is deliberately NOT released here (see __init__ docstring).
                raise DeviceCommandError(
                    f"Terminal operation timed out after {timeout:.1f}s. The "
                    "command may still complete on the device — outcome is "
                    "unknown, not guaranteed failure. Reconciliation (re-running "
                    "the same operation) will detect and confirm the true state "
                    "rather than blindly retrying.",
                    timed_out=True,
                )
            res = entry["response"]
            if not res or not res.get("success"):
                err_msg = res.get("error") if res else "Unknown collector error"
                err_code = res.get("error_code") if res else None
                raise DeviceCommandError(err_msg, error_code=err_code)
            return res.get("result", {})
        finally:
            # _pending cleanup always happens — the waiter itself (the Event)
            # is done being useful either way. _inflight_keys/
            # _command_dedupe_keys are intentionally NOT touched here on a
            # timeout; _on_message releases them when the real response
            # arrives (on time, this already happened inside the `if` above
            # via _release_dedupe_key_for_command — see _on_message).
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
