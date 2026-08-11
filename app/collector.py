import os
import json
import logging
import random
import threading
import tempfile
import time
from enum import Enum, auto
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, List
from zk import ZK

from app.config import Config
from app.db import (
    save_attendance_log,
    save_attendance_batch,
    get_device_watermark,
    determine_status,
    log_sync_event
)
from app.mqtt_client import MQTTService

log = logging.getLogger(__name__)

class State(Enum):
    STARTING = auto()
    CONNECTING = auto()
    BACKFILLING = auto()
    LIVE = auto()
    DEGRADED = auto()
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

        # Services
        self.mqtt_service = MQTTService(cfg)

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
                "last_event_persisted": self.last_event_persisted.isoformat() if self.last_event_persisted else None
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
                if boundary is None or rec.timestamp >= boundary:
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
        try:
            for attendance in self.connection.live_capture():
                if self.stop_event.is_set():
                    log.info("Stop event detected during live capture loop")
                    self.transition_to(State.STOPPING)
                    return

                # Update health heartbeat on every 10s idle ping yield or scan event
                self.write_health_status()

                # Reset reconnect backoff counter if LIVE state has been stable > threshold
                if self.live_start_time and (time.time() - self.live_start_time) >= self.cfg.stable_live_window:
                    if self.reconnect_attempt > 0:
                        log.info("Collector has remained stably connected in LIVE for > %ss. Resetting backoff counter.", self.cfg.stable_live_window)
                        self.reconnect_attempt = 0

                if attendance is None:
                    # 10s socket timeout yield (idle ping)
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

        except Exception as e:
            if self.stop_event.is_set():
                self.transition_to(State.STOPPING)
            else:
                log.error("Live capture loop error: %s", e)
                self.transition_to(State.BACKOFF)

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
