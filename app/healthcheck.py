import os
import sys
import json
import logging
import tempfile
from datetime import datetime, timezone

DEFAULT_PATH = "/tmp/collector_health.json" if os.name != "nt" else os.path.join(tempfile.gettempdir(), "collector_health.json")
HEALTH_FILE_PATH = os.getenv("HEALTH_FILE_PATH", DEFAULT_PATH)
SCHEMA_VERSION = "1.0"

# State-aware maximum allowed stale age (in seconds)
STALE_THRESHOLDS = {
    "STARTING": 30.0,
    "CONNECTING": 60.0,
    "BACKFILLING": 600.0,
    "LIVE": 120.0,
    "DEGRADED": 120.0,
    "BACKOFF": 120.0,
    "STOPPING": 0.0,
    "STOPPED": 0.0
}

def parse_iso_datetime(dt_str: str) -> datetime:
    """Parses ISO 8601 string to timezone-aware datetime."""
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def evaluate_health(file_path: str = HEALTH_FILE_PATH) -> int:
    """
    Evaluates collector liveness from health status file.
    Returns 0 for HEALTHY / DEGRADED, 1 for UNHEALTHY.
    """
    if not os.path.exists(file_path):
        print(f"Collector Health: UNHEALTHY - Health file {file_path} missing")
        return 1

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Collector Health: UNHEALTHY - Failed to parse health file: {e}")
        return 1

    # Validate Schema Version
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        print(f"Collector Health: UNHEALTHY - Unsupported schema version: {version}")
        return 1

    # Validate Loop Alive Flag
    if not data.get("loop_alive", False):
        print("Collector Health: UNHEALTHY - loop_alive is False")
        return 1

    # Validate State
    state = data.get("state")
    if not state or state in ("STOPPING", "STOPPED"):
        print(f"Collector Health: UNHEALTHY - Collector in terminal state: {state}")
        return 1

    max_stale_seconds = STALE_THRESHOLDS.get(state, 120.0)

    # Validate Timestamp Age
    updated_at_str = data.get("updated_at")
    if not updated_at_str:
        print("Collector Health: UNHEALTHY - Missing updated_at timestamp")
        return 1

    try:
        updated_at = parse_iso_datetime(updated_at_str)
        now = datetime.now(timezone.utc)
        age_seconds = (now - updated_at).total_seconds()
    except Exception as e:
        print(f"Collector Health: UNHEALTHY - Invalid timestamp format: {e}")
        return 1

    if age_seconds < 0:
        # Clock skew protection (allow small negative drift due to precision)
        age_seconds = 0.0

    if age_seconds > max_stale_seconds:
        print(f"Collector Health: UNHEALTHY - Heartbeat stale for state {state}: {age_seconds:.1f}s > max {max_stale_seconds:.1f}s")
        return 1

    db_stat = data.get("db_status", "UNKNOWN")
    mqtt_stat = data.get("mqtt_status", "UNKNOWN")
    conn_stat = "Connected" if data.get("device_connected") else "Disconnected"

    print(f"Collector Health: HEALTHY - State: {state}, Age: {age_seconds:.1f}s, Device: {conn_stat}, DB: {db_stat}, MQTT: {mqtt_stat}")
    return 0

if __name__ == "__main__":
    sys.exit(evaluate_health())
