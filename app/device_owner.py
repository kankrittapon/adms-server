"""Single-owner serialization for physical ZK device I/O.

PromptID: ADMS-ZEM560-SingleOwnerIO-014

Audit 013 confirmed a production correctness defect: the Collector's main
thread (state-machine loop, owning `self.connection` through CONNECTING /
BACKFILLING / LIVE / BACKOFF / STOPPING) and paho-mqtt's network thread
(dispatching `handle_device_command()` synchronously from `on_message`) could
both call methods on the same non-thread-safe pyzk `ZK` connection object at
the same time — pyzk has no internal locking at all (verified directly from
its installed source: no `threading` import, no `Lock`/`RLock` anywhere).

This module enforces the hard invariant required by 014: exactly ONE
execution context — the Collector's existing main thread, which already
owns the connection object — may ever call a method on it. Every other
thread (specifically, the MQTT callback thread) submits a request into a
bounded queue and blocks on a private per-request result slot; it never
touches the ZK connection directly. The owner drains the queue only at
points where it is not itself inside a blocking pyzk call (see
app/collector.py's `handle_live()` — the top of each `live_capture()` loop
iteration, right after a yield, is such a point: `live_capture()` is a lazy
generator, so no pyzk code runs between one `next()` call returning and the
next one starting).
"""

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


class DeviceOwnerError(Exception):
    """Base class for all device-ownership-layer failures — distinct from
    app.enrollment's EnrollmentError hierarchy, which represents failures
    *during* an owned execution, not failures to obtain ownership at all."""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class DeviceCommandQueueFull(DeviceOwnerError):
    """Category 1 — the bounded command queue was already full at submission
    time. A prior command has not yet been serviced by the owner."""

    def __init__(self, message: str):
        super().__init__(message, "DEVICE_COMMAND_QUEUE_FULL")


class DeviceOwnerAcquireTimeout(DeviceOwnerError):
    """Category 2 — the command was accepted into the queue but the owner
    did not reach and finish it within the allotted wait window. Distinct
    from a device PROTOCOL timeout (category 3, raised from inside the
    owned execution itself, e.g. TerminalRosterUnavailable) — this fires
    before the owner has even started executing the command, while it is
    still waiting for a safe point (e.g. the current live_capture() idle
    cycle, or an earlier queued command) to finish."""

    def __init__(self, message: str):
        super().__init__(message, "DEVICE_OWNER_TIMEOUT")


class DeviceCommandCancelled(DeviceOwnerError):
    """A queued command was cancelled before the owner executed it, because
    the underlying connection was reconnected/torn down (generation
    changed) or the Collector is shutting down. Mutation safety default:
    cancel rather than execute against a connection the command was never
    validated against — see DeviceOwner.bump_generation()."""

    def __init__(self, message: str):
        super().__init__(message, "DEVICE_COMMAND_CANCELLED")


@dataclass
class _Request:
    command_id: str
    action: str
    params: Dict[str, Any]
    generation: int
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Optional[BaseException] = None
    abandoned: bool = False


class DeviceOwner:
    """Bounded, thread-safe request/response queue serializing all
    command-triggered physical-device I/O through a single owner thread.

    Usage:
      - Non-owner thread (MQTT callback): `submit_and_wait(...)`.
      - Owner thread only, at a safe point: `drain_pending(executor)`.
      - Owner thread only, on reconnect/disconnect: `bump_generation()` and
        `cancel_all_pending(...)`.
    """

    def __init__(self, maxsize: int, acquire_timeout_seconds: float):
        self._queue: "queue.Queue[_Request]" = queue.Queue(maxsize=maxsize)
        self._gen_lock = threading.Lock()
        self.generation = 0
        self.acquire_timeout_seconds = acquire_timeout_seconds

    def bump_generation(self) -> None:
        """Called by the owner whenever the underlying connection is
        replaced or torn down (reconnect, disconnect). Any request already
        queued under a prior generation is cancelled — never executed
        against a connection it wasn't validated for."""
        with self._gen_lock:
            self.generation += 1

    def current_generation(self) -> int:
        with self._gen_lock:
            return self.generation

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def submit_and_wait(self, command_id: str, action: str, params: Dict[str, Any]) -> Any:
        """Non-owner-thread entry point. Enqueues the request (raising
        DeviceCommandQueueFull immediately if the bounded queue is already
        full) and blocks until the owner has executed it, the acquire
        timeout elapses, or it is cancelled. Returns the executor's result
        or re-raises whatever exception the owner's execution raised."""
        req = _Request(
            command_id=command_id, action=action, params=params,
            generation=self.current_generation(),
        )
        try:
            self._queue.put_nowait(req)
        except queue.Full:
            raise DeviceCommandQueueFull(
                "device command queue is full (max %d) — a prior command has "
                "not yet been serviced by the device owner" % self._queue.maxsize
            )
        signaled = req.event.wait(timeout=self.acquire_timeout_seconds)
        if not signaled:
            # Mark abandoned so a late drain (the request may still be
            # sitting in the queue, or about to be picked up) does not
            # execute a real device mutation for a caller no longer
            # listening for the result.
            req.abandoned = True
            raise DeviceOwnerAcquireTimeout(
                "device owner did not service command %s within %.1fs — the "
                "physical terminal connection is busy with attendance "
                "capture or an earlier command" % (command_id, self.acquire_timeout_seconds)
            )
        if req.error is not None:
            raise req.error
        return req.result

    def drain_pending(self, executor: Callable[[str, Dict[str, Any]], Any]) -> int:
        """Owner-thread-only entry point, called at a safe point (no pyzk
        call currently in flight). Executes every currently-queued request
        in submission order via `executor(action, params) -> result` — the
        only code path permitted to touch the ZK connection for
        command-triggered work. Returns the number of requests drained."""
        drained = 0
        while True:
            try:
                req = self._queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
            if req.abandoned:
                continue
            if req.generation != self.current_generation():
                req.error = DeviceCommandCancelled(
                    "command %s cancelled — the device connection was "
                    "reconnected while this command was queued" % req.command_id
                )
                req.event.set()
                continue
            try:
                req.result = executor(req.action, req.params)
            except BaseException as e:  # noqa: BLE001 - propagate verbatim to the waiter
                req.error = e
            req.event.set()
        return drained

    def cancel_all_pending(self, reason: str) -> int:
        """Owner-thread-only entry point, called on reconnect/shutdown —
        immediately fails every currently-queued request with
        DeviceCommandCancelled rather than leaving it to expire on its own
        acquire-timeout. Never touches the connection."""
        cancelled = 0
        while True:
            try:
                req = self._queue.get_nowait()
            except queue.Empty:
                break
            cancelled += 1
            req.error = DeviceCommandCancelled(reason)
            req.event.set()
        return cancelled
