import os
import json
import logging
import random
import threading
import tempfile
import time
from enum import Enum, auto
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, List
from zk import ZK

from app.config import Config
from app.db import (
    save_attendance_log,
    save_attendance_batch,
    get_device_watermark,
    determine_status,
    log_sync_event,
    reconcile_roster_lifecycle
)
from app.mqtt_client import MQTTService
from app.timestamp_utils import normalize_device_timestamp
from app.device_owner import (
    DeviceCommandCancelled,
    DeviceCommandQueueFull,
    DeviceOwner,
    DeviceOwnerAcquireTimeout,
)
from app.enrollment import (
    DEVICE_OWNER_ACQUIRE_TIMEOUT_SECONDS,
    EnrollmentError,
    TerminalAccountConflict,
    TerminalAccountUnconfirmed,
    TerminalRosterUnavailable,
    create_or_reconcile_terminal_account,
)
from app.terminal_management import (
    ActiveHumanProtection,
    TerminalAccountNotFound,
    TerminalIdentityConflict,
    TerminalManagementError,
    read_terminal_inventory,
    remove_terminal_account,
    remove_terminal_fingerprint,
)

log = logging.getLogger(__name__)

# Bounded command queue capacity. In practice paho-mqtt's loop_start() thread
# dispatches on_message callbacks serially (one at a time), so more than one
# command is rarely genuinely in flight — this bound exists as a defensive
# cap against pathological accumulation (e.g. a stuck owner), not as a
# throughput knob.
DEVICE_COMMAND_QUEUE_MAXSIZE = 4

# ADMS-TerminalManagement-020: every action a device command may request.
# Each still goes through the exact same single-owner enqueue/drain path —
# adding an action here never grants a new code path around DeviceOwner.
SUPPORTED_DEVICE_COMMANDS = frozenset({
    "CREATE_TERMINAL_ACCOUNT",
    "TERMINAL_INVENTORY",
    "REMOVE_TERMINAL_FINGERPRINT",
    "REMOVE_TERMINAL_ACCOUNT",
    "START_FINGERPRINT_REENROLL",
})

class State(Enum):
    STARTING = auto()
    CONNECTING = auto()
    BACKFILLING = auto()
    LIVE = auto()
    DEGRADED = auto()
    # ADMS-TerminalManagement-020 Part B: a dedicated, non-capturing state
    # for pyzk's interactively-blocking enroll_user() call (confirmed by
    # reading pyzk source: up to ~60s per attempt, up to 3 attempts). Never
    # entered from inside live_capture()'s loop — only at the same safe
    # boundary the command queue is drained at (between one yielded value
    # and the next), after live_capture() has been asked to end gracefully
    # (self.connection.end_live_capture = True, the same mechanism stop()
    # already uses) and has actually returned control to handle_live().
    FINGERPRINT_ENROLLING = auto()
    BACKOFF = auto()
    STOPPING = auto()
    STOPPED = auto()

DEFAULT_PATH = "/tmp/collector_health.json" if os.name != "nt" else os.path.join(tempfile.gettempdir(), "collector_health.json")
HEALTH_FILE_PATH = os.getenv("HEALTH_FILE_PATH", DEFAULT_PATH)

class CollectorStateEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = State.STARTING
        self.stop_event = threading.Event()
        
        # Connection state
        self.zk_instance: Optional[ZK] = None
        self.connection: Optional[Any] = None
        
        # Reconnect parameters
        self.reconnect_attempt = 0
        self.current_backoff = 0.0
        self.live_start_time: Optional[float] = None
        
        # Telemetry fields for health & backfill monitoring
        self.device_connected = False
        self.last_connect_success: Optional[datetime] = None
        self.last_connect_failure: Optional[datetime] = None
        self.last_event_received: Optional[datetime] = None
        self.last_event_persisted: Optional[datetime] = None
        self.db_status = "UNKNOWN"
        self.mqtt_status = "UNKNOWN"

        # Backfill Telemetry Metrics
        self.last_backfill_started_at: Optional[datetime] = None
        self.last_backfill_completed_at: Optional[datetime] = None
        self.backfill_duration: float = 0.0
        self.device_records_seen: int = 0
        self.candidate_records_count: int = 0
        self.records_inserted_count: int = 0
        self.duplicate_records_count: int = 0
        self.malformed_records_count: int = 0
        self.last_backfill_error: Optional[str] = None

        # Roster Lifecycle Telemetry
        self.last_roster_poll_at: Optional[datetime] = None
        self.last_roster_poll_success: Optional[datetime] = None
        self.last_roster_user_count: Optional[int] = None
        self.last_roster_marked_inactive: Optional[int] = None
        self.last_roster_reappeared: Optional[int] = None
        self.last_roster_uid_anomalies: Optional[int] = None

        # Device-owner queue telemetry (ADMS-ZEM560-SingleOwnerIO-014)
        self.last_command_queued_at: Optional[datetime] = None
        self.last_command_executed_at: Optional[datetime] = None
        self.last_command_queue_wait_seconds: Optional[float] = None
        self.last_capture_paused_for_command_at: Optional[datetime] = None
        self.last_capture_resumed_at: Optional[datetime] = None

        # Services
        self.mqtt_service = MQTTService(cfg, command_handler=self.handle_device_command)

        # Single-owner device I/O (ADMS-ZEM560-SingleOwnerIO-014). The
        # Collector's main thread — already the sole owner of
        # self.connection across every state — is the only execution
        # context ever permitted to call a pyzk method. The paho-mqtt
        # network thread (which runs handle_device_command below) only
        # ever submits into this queue and waits; it never touches
        # self.connection directly. See app/device_owner.py.
        self.device_owner = DeviceOwner(
            maxsize=DEVICE_COMMAND_QUEUE_MAXSIZE,
            acquire_timeout_seconds=DEVICE_OWNER_ACQUIRE_TIMEOUT_SECONDS,
        )

        # ADMS-TerminalManagement-020 Part B: a pending fingerprint
        # re-enrollment request, set (fast, non-blocking) by the
        # START_FINGERPRINT_REENROLL command's owned execution, and
        # consumed only at handle_live()'s safe-point check — never
        # executed from inside drain_pending() itself, since enroll_user()
        # is interactively blocking and would otherwise freeze the normal
        # per-command queue drain for up to ~60-180s.
        self.pending_fingerprint_enroll: Optional[Dict[str, Any]] = None
        self.last_fingerprint_enroll_result: Optional[Dict[str, Any]] = None

    def handle_device_command(self, req: dict):
        """Runs on paho-mqtt's network thread (see MQTTService._on_message).
        MUST NOT perform any ZK/pyzk I/O directly — it only enqueues the
        request via self.device_owner and blocks on the result. All actual
        device I/O happens in _execute_owned_command, called exclusively by
        the owner (main) thread from drain_pending()."""
        command_id = req.get("command_id")
        action = req.get("action")
        params = req.get("params", {})
        if not command_id:
            return
        log.info("Received device command %s (action=%s)", command_id, action)
        if action not in SUPPORTED_DEVICE_COMMANDS:
            self.mqtt_service.publish_command_response(
                command_id,
                success=False,
                error=f"Unsupported device action: {action}"
            )
            return
        if not self.connection or self.state not in (State.LIVE, State.DEGRADED):
            # Category 4 — Collector/device unavailable. Rejected before
            # ever reaching the queue; there is no connection generation to
            # queue a command against.
            self.mqtt_service.publish_command_response(
                command_id,
                success=False,
                error=f"Collector is not in LIVE state (current state: {self.state.name})",
                error_code="COLLECTOR_UNAVAILABLE",
            )
            return

        queued_at = time.monotonic()
        self.last_command_queued_at = datetime.now(timezone.utc)
        log.info("Device command %s queued (queue depth now %d)", command_id, self.device_owner.queue_depth() + 1)
        try:
            result = self.device_owner.submit_and_wait(command_id, action, params)
            wait_s = time.monotonic() - queued_at
            self.last_command_queue_wait_seconds = wait_s
            self.last_command_executed_at = datetime.now(timezone.utc)
            log.info("Device command %s executed successfully (queue wait %.2fs)", command_id, wait_s)
            self.mqtt_service.publish_command_response(
                command_id,
                success=True,
                result=result
            )
        except DeviceCommandQueueFull as e:
            # Category 1
            log.warning("Device command %s rejected: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e), error_code=e.error_code,
            )
        except DeviceOwnerAcquireTimeout as e:
            # Category 2 — distinct from a device PROTOCOL timeout: the
            # owner never even started executing this command.
            log.warning("Device command %s: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e), error_code=e.error_code,
            )
        except DeviceCommandCancelled as e:
            log.warning("Device command %s: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e), error_code=e.error_code,
            )
        except TerminalRosterUnavailable as e:
            # Category 3 (protocol-level) — PRE-MUTATION failure —
            # set_user() was never reached. Must not be reported as
            # ENROLLMENT_CONFLICT (implies a state issue) or
            # TERMINAL_ACCOUNT_UNCONFIRMED (implies a write was attempted) —
            # neither is true here.
            log.error("Device command %s: pre-mutation roster read failed: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e),
                error_code="DEVICE_UNAVAILABLE",
            )
        except TerminalAccountConflict as e:
            log.error("Device command %s: terminal account conflict: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e),
                error_code="TERMINAL_ACCOUNT_CONFLICT",
            )
        except TerminalAccountUnconfirmed as e:
            log.error("Device command %s: terminal account unconfirmed: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e),
                error_code="TERMINAL_ACCOUNT_UNCONFIRMED",
            )
        except EnrollmentError as e:
            log.error("Device command execution failed for %s: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e),
                error_code="ENROLLMENT_CONFLICT",
            )
        except TerminalManagementError as e:
            # Covers TerminalAccountNotFound, TerminalIdentityConflict,
            # ActiveHumanProtection too (all subclasses) — each already
            # carries its own specific error_code.
            log.error("Device command %s: terminal management error: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id, success=False, error=str(e),
                error_code=e.error_code,
            )
        except Exception as e:
            log.error("Device command execution failed for %s: %s", command_id, e)
            self.mqtt_service.publish_command_response(
                command_id,
                success=False,
                error=str(e)
            )

    def _execute_owned_command(self, action: str, params: dict) -> Any:
        """Executed EXCLUSIVELY by the device owner (main thread), invoked
        from DeviceOwner.drain_pending() at a safe point. This — together
        with the state-machine's own handle_* methods — is the only code
        permitted to call a method on self.connection for command-triggered
        work. Any exception raised here propagates verbatim back to the
        waiting MQTT thread via the request's result slot."""
        if action == "CREATE_TERMINAL_ACCOUNT":
            enrollment_id = int(params["enrollment_id"])
            display_name = str(params["display_name"])
            result = create_or_reconcile_terminal_account(
                self.cfg,
                enrollment_id=enrollment_id,
                display_name=display_name,
                device=self.connection
            )
            # Reconcile roster lifecycle immediately to discover the new
            # terminal user — still inside the same owned execution, on the
            # same connection, not a separate MQTT-thread call (that used to
            # be a second, unprotected get_users() call from the MQTT
            # thread; see PromptID-013's audit finding #9).
            self.perform_roster_lifecycle_check()
            return result
        if action == "TERMINAL_INVENTORY":
            return {"items": read_terminal_inventory(self.connection)}
        if action == "REMOVE_TERMINAL_FINGERPRINT":
            result = remove_terminal_fingerprint(
                self.cfg,
                device=self.connection,
                device_id=int(params["device_id"]),
                device_user_id=str(params["device_user_id"]),
                operator=str(params["operator"]),
                finger_id=(int(params["finger_id"]) if params.get("finger_id") is not None else None),
            )
            self.perform_roster_lifecycle_check()
            return result
        if action == "REMOVE_TERMINAL_ACCOUNT":
            result = remove_terminal_account(
                self.cfg,
                device=self.connection,
                device_id=int(params["device_id"]),
                device_user_id=str(params["device_user_id"]),
                operator=str(params["operator"]),
                acknowledge_active_human=bool(params.get("acknowledge_active_human", False)),
            )
            self.perform_roster_lifecycle_check()
            return result
        if action == "START_FINGERPRINT_REENROLL":
            # Deliberately does NOT call enroll_user() here — that call
            # blocks up to ~60-180s and would freeze drain_pending() (and
            # therefore all attendance capture and other commands) for its
            # entire duration. This owned execution only fast-validates
            # the target account exists and records the pending request;
            # handle_live()'s own safe-point check picks it up on the next
            # yield and transitions the whole state machine into
            # FINGERPRINT_ENROLLING to perform the actual blocking call
            # with nothing else competing for the connection.
            device_user_id = str(params["device_user_id"])
            users = self.connection.get_users() or []
            matches = [u for u in users if str(u.user_id) == device_user_id]
            if not matches:
                raise TerminalAccountNotFound(
                    "terminal account %s not found on device" % device_user_id
                )
            self.pending_fingerprint_enroll = {
                "device_user_id": device_user_id,
                "uid": matches[0].uid,
                "operator": str(params["operator"]),
            }
            return {"device_user_id": device_user_id, "queued": True}
        raise ValueError("unsupported device action: %s" % action)

    def write_health_status(self):
        """
        Atomically writes operational health state to HEALTH_FILE_PATH.
        Guarantees zero credentials, passwords, Comm Keys, user IDs, or employee names are written.
        """
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            payload = {
                "schema_version": "1.0",
                "updated_at": now_iso,
                "state": self.state.name,
                "loop_alive": not self.stop_event.is_set(),
                "device_connected": self.device_connected,
                "db_status": self.db_status,
                "mqtt_status": self.mqtt_status,
                "reconnect_attempt": self.reconnect_attempt,
                "current_backoff_seconds": round(self.current_backoff, 2),
                "last_connect_success": self.last_connect_success.isoformat() if self.last_connect_success else None,
                "last_connect_failure": self.last_connect_failure.isoformat() if self.last_connect_failure else None,
                "last_backfill_started_at": self.last_backfill_started_at.isoformat() if self.last_backfill_started_at else None,
                "last_backfill_completed_at": self.last_backfill_completed_at.isoformat() if self.last_backfill_completed_at else None,
                "last_event_received": self.last_event_received.isoformat() if self.last_event_received else None,
                "last_event_persisted": self.last_event_persisted.isoformat() if self.last_event_persisted else None,
                "last_roster_poll_at": self.last_roster_poll_at.isoformat() if self.last_roster_poll_at else None,
                "last_roster_poll_success": self.last_roster_poll_success.isoformat() if self.last_roster_poll_success else None,
                "last_roster_user_count": self.last_roster_user_count,
                "last_roster_marked_inactive": self.last_roster_marked_inactive,
                "last_roster_reappeared": self.last_roster_reappeared,
                "last_roster_uid_anomalies": self.last_roster_uid_anomalies,
                # Device-owner / command-queue telemetry (ADMS-ZEM560-
                # SingleOwnerIO-014). Deliberately distinct from
                # device_connected: a live Python `self.connection` object
                # existing is NOT the same claim as "the device owner is
                # actively servicing commands" — e.g. the owner thread could
                # in principle be stuck inside a single pyzk call well past
                # its normal cycle time while device_connected still reads
                # True. Do not infer command-queue health from
                # device_connected alone.
                "device_owner_available": self.state in (State.LIVE, State.DEGRADED) and self.connection is not None,
                "device_command_queue_depth": self.device_owner.queue_depth() if hasattr(self, "device_owner") else 0,
                "device_command_generation": self.device_owner.current_generation() if hasattr(self, "device_owner") else 0,
                "last_command_queued_at": self.last_command_queued_at.isoformat() if self.last_command_queued_at else None,
                "last_command_executed_at": self.last_command_executed_at.isoformat() if self.last_command_executed_at else None,
                "last_command_queue_wait_seconds": self.last_command_queue_wait_seconds,
                "last_capture_paused_for_command_at": self.last_capture_paused_for_command_at.isoformat() if self.last_capture_paused_for_command_at else None,
                "last_capture_resumed_at": self.last_capture_resumed_at.isoformat() if self.last_capture_resumed_at else None,
                # ADMS-TerminalManagement-020 Part B: fingerprint
                # re-enrollment's real result (CONFIRMED/FAILED) arrives
                # asynchronously, after the MQTT command's own quick
                # "queued" ack — the API polls this via the same existing
                # Collector-health-bridge pattern used for every other
                # telemetry field, rather than a new transport.
                "pending_fingerprint_enroll_device_user_id": (
                    self.pending_fingerprint_enroll["device_user_id"] if self.pending_fingerprint_enroll else None
                ),
                "last_fingerprint_enroll_result": self.last_fingerprint_enroll_result,
            }

            dir_path = os.path.dirname(HEALTH_FILE_PATH)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)

            tmp_path = HEALTH_FILE_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, HEALTH_FILE_PATH)
        except Exception as e:
            log.warning("Failed to write atomic health status file: %s", e)

    def transition_to(self, new_state: State):
        log.info("State transition: %s -> %s", self.state.name, new_state.name)
        self.state = new_state
        self.write_health_status()

    def compute_backoff_delay(self) -> float:
        base = min(self.cfg.max_backoff, self.cfg.initial_backoff * (self.cfg.backoff_multiplier ** self.reconnect_attempt))
        jitter = random.uniform(-self.cfg.backoff_jitter, self.cfg.backoff_jitter)
        delay = max(0.5, base * (1.0 + jitter))
        return delay

    def cleanup_connection(self):
        # Owner-thread-only. Cancel any command still waiting for this
        # connection generation BEFORE tearing it down, and bump the
        # generation so nothing queued (or queued moments from now, racing
        # this call) can ever execute against a stale/disconnected
        # connection — mutation safety defaults to cancel, not delayed
        # execution against a reconnected device (PromptID-014 Phase 6).
        cancelled = self.device_owner.cancel_all_pending(
            "device connection is being reset — command cancelled rather "
            "than executed against a stale connection"
        )
        self.device_owner.bump_generation()
        if cancelled:
            log.warning("Cancelled %d pending device command(s) during connection cleanup", cancelled)
        if self.connection:
            try:
                log.info("cleaning up ZK connection...")
                self.connection.enable_device()
                self.connection.disconnect()
            except Exception as e:
                log.warning("ZK disconnect cleanup warning: %s", e)
            finally:
                self.connection = None
        self.zk_instance = None
        self.device_connected = False
        self.write_health_status()

    def handle_starting(self):
        log.info("Starting ADMS Collector Engine...")
        self.write_health_status()
        self.mqtt_service.start()
        self.transition_to(State.CONNECTING)

    def handle_connecting(self):
        if self.stop_event.is_set():
            self.transition_to(State.STOPPING)
            return

        log.info("Attempting connection to ZKTeco %s:%s (attempt %d)...",
                 self.cfg.device_ip, self.cfg.device_port, self.reconnect_attempt + 1)
        self.write_health_status()

        try:
            self.cleanup_connection()
            self.zk_instance = ZK(
                self.cfg.device_ip,
                port=self.cfg.device_port,
                timeout=self.cfg.device_timeout,
                password=self.cfg.device_password
            )
            self.connection = self.zk_instance.connect()
            self.device_connected = True
            self.last_connect_success = datetime.now()
            log.info("Connected to ZKTeco terminal successfully!")
            self.transition_to(State.BACKFILLING)
        except Exception as e:
            self.last_connect_failure = datetime.now()
            log.error("Failed to connect to ZKTeco terminal: %s", e)
            self.transition_to(State.BACKOFF)

    def perform_roster_lifecycle_check(self):
        """
        Performs a read-only terminal roster snapshot and reconciles device_users
        lifecycle metadata. Only called after a successful, complete roster read.

        If the roster read fails (timeout, disconnect, exception), NO lifecycle
        updates are made — UNKNOWN state is NOT the same as an empty roster.
        """
        if not self.connection:
            log.warning("Skipping roster lifecycle check — no active ZK connection.")
            return

        self.last_roster_poll_at = datetime.now()
        self.write_health_status()

        try:
            raw_users = self.connection.get_users()
            if raw_users is None:
                log.warning("Roster read returned None — treating as FAILED. No lifecycle updates.")
                return

            observed_users = []
            for u in raw_users:
                observed_users.append({
                    "user_id": str(u.user_id),
                    "uid": getattr(u, "uid", None),
                    "name": getattr(u, "name", None),
                })

            self.last_roster_poll_success = datetime.now()
            self.last_roster_user_count = len(observed_users)
            log.info("Roster snapshot: %d users observed on terminal.", len(observed_users))

            # Resolve device_id from DB
            from app.db import get_db_connection
            with get_db_connection(self.cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT device_id FROM devices WHERE device_ip = %s;",
                        (self.cfg.device_ip,),
                    )
                    row = cur.fetchone()
                    if not row:
                        log.error("Device not found in DB for ip=%s. Cannot reconcile roster.", self.cfg.device_ip)
                        return
                    device_id = row[0]

            # Atomic per-device reconciliation
            summary = reconcile_roster_lifecycle(self.cfg, device_id, observed_users)
            self.last_roster_marked_inactive = summary["marked_inactive"]
            self.last_roster_reappeared = summary["reappeared"]
            self.last_roster_uid_anomalies = summary["uid_anomalies"]
            self.last_roster_mappings_closed = summary.get("mappings_closed", 0)

            audit_msg = (
                f"Roster lifecycle: {summary['observed']} observed, "
                f"{summary['new_users']} new, {summary['marked_inactive']} marked_inactive, "
                f"{summary['reappeared']} reappeared, {summary['uid_anomalies']} uid_anomalies, "
                f"{summary.get('mappings_closed', 0)} mappings_closed."
            )
            log.info(audit_msg)
            log_sync_event(self.cfg, "ROSTER_LIFECYCLE", audit_msg)

        except Exception as e:
            log.warning("Roster lifecycle check FAILED: %s. No lifecycle updates applied.", e)
            # Do NOT update inactive_at on failure — UNKNOWN != empty roster
        finally:
            self.write_health_status()

    def handle_backfilling(self):
        """
        Executes historical attendance log reconciliation using get_attendance().
        Queries DB watermark, applies client-side timestamp overlap filtering,
        persists candidate records in batch chunks, and suppresses MQTT broadcasts.
        """
        if self.stop_event.is_set():
            self.transition_to(State.STOPPING)
            return

        log.info("Executing BACKFILLING state historical reconciliation...")
        self.last_backfill_started_at = datetime.now()
        t0 = time.time()
        self.last_backfill_error = None
        self.write_health_status()

        try:
            # Step 1: Query DB Watermark
            watermark = get_device_watermark(self.cfg, self.cfg.device_ip)
            boundary: Optional[datetime] = None
            if watermark:
                overlap_td = timedelta(minutes=self.cfg.backfill_overlap_minutes)
                boundary = watermark - overlap_td
                log.info("Found DB watermark %s for device %s. Overlap boundary: %s",
                         watermark.isoformat(), self.cfg.device_ip, boundary.isoformat())
            else:
                log.info("No existing DB watermark for device %s. Executing FIRST-RUN full backfill.",
                         self.cfg.device_ip)

            # Step 2: Retrieve Terminal Flash Memory Logs
            log.info("Retrieving historical attendance logs via get_attendance()...")
            self.write_health_status()
            raw_logs = self.connection.get_attendance()
            self.device_records_seen = len(raw_logs) if raw_logs else 0
            log.info("Retrieved %d raw attendance records from terminal flash memory.", self.device_records_seen)

            # Step 3: Client-Side Timestamp Filtering & Validation
            candidates = []
            malformed_count = 0
            for rec in raw_logs:
                if not hasattr(rec, 'user_id') or not hasattr(rec, 'timestamp') or not rec.timestamp:
                    malformed_count += 1
                    continue
                normalized_ts = normalize_device_timestamp(rec.timestamp)
                if boundary is None or normalized_ts >= boundary:
                    candidates.append(rec)

            self.malformed_records_count = malformed_count
            self.candidate_records_count = len(candidates)
            log.info("Filtered %d candidate records for reconciliation (boundary: %s). Malformed: %d",
                     self.candidate_records_count, boundary.isoformat() if boundary else "None", malformed_count)

            # Step 4: Batch Persistence to PostgreSQL (MQTT Broadcast is SUPPRESSED)
            inserted_count, skipped_count = 0, 0
            if candidates:
                log.info("Persisting %d candidate records to PostgreSQL in batch chunks of %d...",
                         len(candidates), self.cfg.backfill_batch_size)
                inserted_count, skipped_count = save_attendance_batch(self.cfg, candidates, self.stop_event)

            self.records_inserted_count = inserted_count
            self.duplicate_records_count = skipped_count
            self.db_status = "HEALTHY"

            # Step 5: Audit Event Logging
            self.backfill_duration = time.time() - t0
            self.last_backfill_completed_at = datetime.now()
            audit_msg = (f"Backfill complete in {self.backfill_duration:.2f}s: {self.device_records_seen} seen, "
                         f"{self.candidate_records_count} candidates, {inserted_count} inserted, {skipped_count} duplicates skipped.")
            log.info(audit_msg)
            log_sync_event(self.cfg, "HISTORICAL_BACKFILL", audit_msg)

            # Step 6: Ensure Terminal Display & Keypad remain ENABLED
            if self.connection and hasattr(self.connection, 'enable_device'):
                self.connection.enable_device()

            # Step 7: Roster Lifecycle Check (after successful backfill, before LIVE)
            self.perform_roster_lifecycle_check()

            self.live_start_time = time.time()
            self.transition_to(State.LIVE)

        except Exception as e:
            self.last_backfill_error = str(e)
            self.db_status = "ERROR" if "psycopg2" in str(type(e)) else self.db_status
            log.error("Historical backfill reconciliation failed: %s. Transitioning to BACKOFF.", e)
            log_sync_event(self.cfg, "BACKFILL_ERROR", f"Backfill failed: {e}")
            self.transition_to(State.BACKOFF)

    def handle_live(self):
        if self.stop_event.is_set():
            self.transition_to(State.STOPPING)
            return

        log.info("Entering LIVE attendance stream monitoring...")
        self.write_health_status()
        last_roster_poll_monotonic: float = time.time()
        try:
            for attendance in self.connection.live_capture():
                if self.stop_event.is_set():
                    log.info("Stop event detected during live capture loop")
                    self.transition_to(State.STOPPING)
                    return

                # Update health heartbeat on every 10s idle ping yield or scan event
                self.write_health_status()

                # Safe point (ADMS-ZEM560-SingleOwnerIO-014): live_capture()
                # is a lazy generator — no pyzk call is in flight between one
                # yielded value and the next `next()` call on it. This is
                # exactly where the owner (this thread) may safely execute
                # any queued device command on the same connection, since
                # nothing else can be mid-recv() right here. drain_pending()
                # is a cheap non-blocking no-op when the queue is empty, so
                # it is safe to call unconditionally on every iteration.
                if self.device_owner.queue_depth():
                    self.last_capture_paused_for_command_at = datetime.now(timezone.utc)
                    log.info("Live capture pausing at safe point to service queued device command(s)")
                drained = self.device_owner.drain_pending(self._execute_owned_command)
                if drained:
                    self.last_capture_resumed_at = datetime.now(timezone.utc)
                    log.info("Live capture resumed after servicing %d device command(s)", drained)
                    self.write_health_status()

                # ADMS-TerminalManagement-020 Part B: a fingerprint
                # re-enrollment request was queued and fast-validated by
                # _execute_owned_command above. This is the same safe
                # point used for normal commands — no pyzk call is in
                # flight — so it is safe to end live_capture() gracefully
                # here (the identical mechanism stop() already uses) and
                # hand the connection to a dedicated, non-capturing state
                # for the actual interactively-blocking enroll_user() call.
                if self.pending_fingerprint_enroll is not None:
                    log.info(
                        "Fingerprint re-enrollment requested for %s — ending live_capture "
                        "gracefully to enter FINGERPRINT_ENROLLING",
                        self.pending_fingerprint_enroll["device_user_id"],
                    )
                    self.connection.end_live_capture = True

                # Reset reconnect backoff counter if LIVE state has been stable > threshold
                if self.live_start_time and (time.time() - self.live_start_time) >= self.cfg.stable_live_window:
                    if self.reconnect_attempt > 0:
                        log.info("Collector has remained stably connected in LIVE for > %ss. Resetting backoff counter.", self.cfg.stable_live_window)
                        self.reconnect_attempt = 0

                if attendance is None:
                    # 10s socket timeout yield (idle ping)
                    # Periodic roster lifecycle check
                    if (time.time() - last_roster_poll_monotonic) >= self.cfg.roster_poll_interval_seconds:
                        log.info("Periodic roster lifecycle check triggered (interval=%ss).",
                                 self.cfg.roster_poll_interval_seconds)
                        self.perform_roster_lifecycle_check()
                        last_roster_poll_monotonic = time.time()
                    continue

                self.last_event_received = datetime.now()
                log.info("Attendance event captured: User %s at %s", attendance.user_id, attendance.timestamp)

                # Step 1: PostgreSQL Persistence (Primary Source of Truth)
                try:
                    inserted = save_attendance_log(self.cfg, attendance)
                    self.db_status = "HEALTHY"
                    self.last_event_persisted = datetime.now()
                    if inserted:
                        log.info("Persisted new attendance record for user %s to DB", attendance.user_id)
                    else:
                        log.info("Duplicate record skipped for user %s at %s", attendance.user_id, attendance.timestamp)
                except Exception as e:
                    self.db_status = "ERROR"
                    log.error("Database persistence failed: %s. Aborting live capture to prevent data loss.", e)
                    self.transition_to(State.BACKOFF)
                    return

                # Step 2: Mosquitto MQTT Broadcast (Downstream Notification Only - Real-time Only)
                status_str = determine_status(attendance.timestamp, self.cfg.on_time_start, self.cfg.on_time_end)
                mqtt_ok = self.mqtt_service.publish_attendance(attendance, status_str)
                if mqtt_ok:
                    self.mqtt_status = "HEALTHY"
                    if self.state == State.DEGRADED:
                        self.transition_to(State.LIVE)
                else:
                    self.mqtt_status = "DEGRADED"
                    if self.state == State.LIVE:
                        self.transition_to(State.DEGRADED)

            # live_capture()'s generator has now ended (its own cleanup —
            # socket timeout restore, reg_event(0), re-disable if it
            # wasn't enabled on entry — already ran inside pyzk itself).
            # This only happens here via our own end_live_capture=True
            # request (Part B) or shutdown (handled inside the loop via
            # explicit `return` above) — so reaching this point with a
            # pending request is the expected, sole reason for a graceful
            # (non-exception) exit from the for-loop during normal LIVE
            # operation.
            if self.pending_fingerprint_enroll is not None:
                self.transition_to(State.FINGERPRINT_ENROLLING)

        except Exception as e:
            if self.stop_event.is_set():
                self.transition_to(State.STOPPING)
            else:
                log.error("Live capture loop error: %s", e)
                self.transition_to(State.BACKOFF)

    def handle_fingerprint_enrolling(self):
        """ADMS-TerminalManagement-020 Part B. Owner-thread-only, entered
        exclusively from handle_live() at a safe point (live_capture()
        already gracefully ended). Exactly one socket owner throughout —
        this is the main thread, the same one that owns self.connection in
        every other state. Performs pyzk's enroll_user() (confirmed
        interactively blocking, up to ~60s per attempt x up to 3 attempts)
        directly — no queue, no drain, nothing else can touch the
        connection while this runs. Always returns to LIVE afterward,
        success or failure, so a single failed attempt never strands the
        Collector outside normal operation (the operator can simply
        request a fresh attempt).

        Cancellation limitation (documented, not solved): pyzk's
        enroll_user() provides no interrupt/cancel hook once its internal
        recv() loop has started — reliable mid-call cancellation is not
        possible with the installed library version. The safest operator
        behavior is therefore to let it run to its own bounded internal
        timeout rather than attempting an unsafe interrupt (e.g. closing
        the socket out from under it), which could leave the connection in
        an inconsistent state requiring a full reconnect anyway. The UI
        must say plainly that the operation cannot be cancelled mid-way.
        """
        if self.stop_event.is_set():
            self.transition_to(State.STOPPING)
            return
        req = self.pending_fingerprint_enroll
        self.pending_fingerprint_enroll = None
        if req is None or self.connection is None:
            # Structurally should never happen (this state is only ever
            # entered with a pending request and a live connection) — fail
            # safe back to LIVE rather than getting stuck.
            log.warning("Entered FINGERPRINT_ENROLLING with no pending request or no connection")
            self.transition_to(State.LIVE)
            return

        device_user_id = req["device_user_id"]
        uid = req["uid"]
        operator = req["operator"]

        log.info("Fingerprint re-enrollment starting for %s (uid=%s, operator=%s)", device_user_id, uid, operator)
        log_sync_event(
            self.cfg, "TERMINAL_FINGERPRINT_REENROLL_STARTED",
            "device_user_id=%s uid=%s operator=%s" % (device_user_id, uid, operator),
        )

        try:
            templates_before = self.connection.get_templates() or []
        except Exception:
            templates_before = []
        count_before = len([f for f in templates_before if f.uid == uid])

        try:
            done = self.connection.enroll_user(uid=uid, user_id=str(device_user_id))
        except Exception as e:
            # A raised exception (vs. enroll_user() internally returning
            # done=False for a mundane "no finger placed in time") most
            # likely means a genuine connection-level failure — treat as
            # reconnect-worthy, same as any other live-state I/O exception.
            log.error("Fingerprint re-enrollment errored for %s: %s", device_user_id, e)
            log_sync_event(
                self.cfg, "TERMINAL_FINGERPRINT_REENROLL_FAILED",
                "device_user_id=%s uid=%s operator=%s reason=%s" % (device_user_id, uid, operator, e),
            )
            self.last_fingerprint_enroll_result = {"device_user_id": device_user_id, "success": False}
            self.transition_to(State.BACKOFF)
            return

        # Never trust `done` alone (same principle as set_user() —
        # PromptID 010) — confirm via an actual template-count read-back.
        try:
            templates_after = self.connection.get_templates() or []
            count_after = len([f for f in templates_after if f.uid == uid])
        except Exception as e:
            log.warning("Fingerprint re-enrollment read-back failed for %s: %s", device_user_id, e)
            count_after = count_before

        confirmed = count_after > count_before
        if done and confirmed:
            log.info("Fingerprint re-enrollment confirmed for %s", device_user_id)
            log_sync_event(
                self.cfg, "TERMINAL_FINGERPRINT_REENROLL_CONFIRMED",
                "device_user_id=%s uid=%s operator=%s templates_before=%s templates_after=%s"
                % (device_user_id, uid, operator, count_before, count_after),
            )
            self.last_fingerprint_enroll_result = {"device_user_id": device_user_id, "success": True}
        else:
            log.warning("Fingerprint re-enrollment not confirmed for %s (done=%s, %d->%d templates)",
                        device_user_id, done, count_before, count_after)
            log_sync_event(
                self.cfg, "TERMINAL_FINGERPRINT_REENROLL_FAILED",
                "device_user_id=%s uid=%s operator=%s reason=not_confirmed done=%s "
                "templates_before=%s templates_after=%s"
                % (device_user_id, uid, operator, done, count_before, count_after),
            )
            self.last_fingerprint_enroll_result = {"device_user_id": device_user_id, "success": False}

        # Human/attendance/enrollment/mapping history is untouched by this
        # entire method — only pyzk's own template storage was written to.
        self.live_start_time = time.time()
        self.transition_to(State.LIVE)

    def handle_backoff(self):
        self.cleanup_connection()
        if self.stop_event.is_set():
            self.transition_to(State.STOPPING)
            return

        self.current_backoff = self.compute_backoff_delay()
        log.warning("Entering BACKOFF state for %.2f seconds (attempt %d)...",
                    self.current_backoff, self.reconnect_attempt + 1)
        self.write_health_status()
        
        interrupted = self.stop_event.wait(timeout=self.current_backoff)
        self.write_health_status()

        if interrupted or self.stop_event.is_set():
            self.transition_to(State.STOPPING)
        else:
            self.reconnect_attempt += 1
            self.transition_to(State.CONNECTING)

    def handle_stopping(self):
        log.info("Stopping ADMS Collector Engine...")
        self.cleanup_connection()
        self.mqtt_service.stop()
        self.transition_to(State.STOPPED)
        self.write_health_status()

    def run(self):
        log.info("CollectorStateEngine execution loop started.")
        while self.state != State.STOPPED:
            if self.state == State.STARTING:
                self.handle_starting()
            elif self.state == State.CONNECTING:
                self.handle_connecting()
            elif self.state == State.BACKFILLING:
                self.handle_backfilling()
            elif self.state in (State.LIVE, State.DEGRADED):
                self.handle_live()
            elif self.state == State.FINGERPRINT_ENROLLING:
                self.handle_fingerprint_enrolling()
            elif self.state == State.BACKOFF:
                self.handle_backoff()
            elif self.state == State.STOPPING:
                self.handle_stopping()
            else:
                log.error("Unknown state encountered: %s", self.state)
                break
        log.info("CollectorStateEngine terminated cleanly.")
        self.write_health_status()

    def stop(self):
        log.info("Stop requested for CollectorStateEngine.")
        self.stop_event.set()
        if self.connection and hasattr(self.connection, 'end_live_capture'):
            self.connection.end_live_capture = True
        self.write_health_status()
