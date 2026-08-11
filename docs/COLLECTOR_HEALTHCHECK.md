# ADMS Collector Healthcheck & Liveness Specification

## Document Status

* **Status**: Approved Collector Healthcheck Architecture Plan
* **Source PromptID**: `ADMS-Collector-Healthcheck-001`
* **Target Container**: `adms_zkteco_listener`
* **Implementation Target Phase**: `ADMS-Collector-Healthcheck-002`

---

## 1. Executive Summary

The **Collector Healthcheck Architecture** establishes an ephemeral, non-invasive liveness monitoring system for the ADMS Python Collector.

It distinguishes between:
1. **Collector Process / FSM Loop Stalled** $\to$ **UNHEALTHY** (Docker healthcheck fails).
2. **External Dependency Outage (Terminal / MQTT Offline)** $\to$ **HEALTHY / DEGRADED** (Collector recovery loop is alive; Docker healthcheck passes).

---

## 2. Health Semantics & Application States

```text
  +-------------------------------------------------------+
  |                   State Engine Loop                   |
  +-------------------------------------------------------+
                              |
       +----------------------+----------------------+
       |                      |                      |
       v                      v                      v
+--------------+       +--------------+       +--------------+
|   HEALTHY    |       |   DEGRADED   |       |  UNHEALTHY   |
|              |       |              |       |              |
| - LIVE       |       | - Terminal   |       | - FSM Loop   |
| - BACKFILL   |       |   Offline    |       |   Stalled    |
| - BACKOFF    |       | - MQTT Down  |       | - Heartbeat  |
| - DB Good    |       | - Recovery   |       |   Stale      |
|              |       |   Active     |       | - Dead       |
+--------------+       +--------------+       +--------------+
(Exit Code 0)           (Exit Code 0)          (Exit Code 1)
```

### Definitions:
* **HEALTHY** (`Exit Code 0`): Collector loop is actively progressing. Terminal is connected and streaming live events or completing backfill reconciliation.
* **DEGRADED** (`Exit Code 0`): Collector loop is alive and actively running recovery logic, but an external dependency is unavailable (e.g. MQTT broker offline, or device temporarily disconnected during exponential backoff).
* **UNHEALTHY** (`Exit Code 1`): Collector event loop itself has stalled, crashed, deadlocked, or failed to update its heartbeat file within state-aware thresholds.

---

## 3. Ephemeral Health Status File (`/tmp/collector_health.json`)

To prevent corrupt or partial reads during health probing, updates are written **atomically** using a temporary file and atomic replace (`os.replace`).

### Status File JSON Schema:
```json
{
  "schema_version": "1.0",
  "updated_at": "2026-08-11T10:52:00.123456Z",
  "state": "LIVE",
  "loop_alive": true,
  "device_connected": true,
  "db_status": "HEALTHY",
  "mqtt_status": "HEALTHY",
  "reconnect_attempt": 0,
  "current_backoff_seconds": 0.0,
  "last_connect_success": "2026-08-11T10:50:00Z",
  "last_backfill_completed_at": "2026-08-11T10:50:02Z",
  "last_event_received": "2026-08-11T10:51:30Z",
  "last_event_persisted": "2026-08-11T10:51:30Z"
}
```

> [!IMPORTANT]
> The health status file contains **zero secret or sensitive data** (no passwords, Comm Keys, employee names, user IDs, or attendance payloads).

---

## 4. State-Aware Liveness & Stall Thresholds

| State Engine State | Maximum Allowed Stale Age | Rationale |
| ------------------ | ------------------------- | --------- |
| **`LIVE` / `DEGRADED`** | **120.0 seconds** | `live_capture()` yields `None` every 10s idle ping. Heartbeat is updated every 10s. |
| **`BACKOFF`** | **120.0 seconds** | Max backoff delay is 60s ($\pm 20\%$ jitter = ~72s). Heartbeat updated before and after backoff sleep. |
| **`BACKFILLING`** | **600.0 seconds** | Accommodates large historical flash log retrieval (up to 100k records) without false unhealthy triggers. |
| **`STARTING`** | **30.0 seconds** | Startup grace window (`start_period`). |
| **`STOPPING` / `STOPPED`** | **Exits 1** | Graceful shutdown in progress or complete. |

---

## 5. Non-Invasive Healthcheck Module (`app/healthcheck.py`)

A lightweight CLI tool executed by Docker healthcheck:
```bash
python -m app.healthcheck
```

### Execution Logic:
1. Reads `/tmp/collector_health.json`.
2. Validates JSON schema version (`"1.0"`).
3. Verifies `"loop_alive": true`.
4. Calculates file age ($\Delta t = \text{now} - \text{updated\_at}$).
5. Compares $\Delta t$ against the state-aware threshold (`120s` for LIVE/BACKOFF, `600s` for BACKFILLING).
6. Returns `Exit Code 0` for HEALTHY / DEGRADED states.
7. Returns `Exit Code 1` if file missing, malformed, or stale beyond threshold.

---

## 6. Docker Compose Configuration (`docker-compose.yml`)

```yaml
services:
  listener:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: adms_zkteco_listener
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-m", "app.healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```
