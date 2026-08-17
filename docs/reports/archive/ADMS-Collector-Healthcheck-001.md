# COLLECTOR HEALTHCHECK PLAN

## Prompt

* PromptID: `ADMS-Collector-Healthcheck-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:52:00+07:00
* target repository: `adms-server`
* modifications performed: NO (Documentation writes only)

## Current Signals

| Signal | Status | Source |
| ------ | ------ | ------ |
| `current_state` | ALREADY IMPLEMENTED | `self.state` in `app/collector.py` |
| `device_connected` | ALREADY IMPLEMENTED | `self.device_connected` in `app/collector.py` |
| `last_connect_success` | ALREADY IMPLEMENTED | `self.last_connect_success` in `app/collector.py` |
| `last_connect_failure` | ALREADY IMPLEMENTED | `self.last_connect_failure` in `app/collector.py` |
| `last_event_received` | ALREADY IMPLEMENTED | `self.last_event_received` in `app/collector.py` |
| `last_event_persisted` | ALREADY IMPLEMENTED | `self.last_event_persisted` in `app/collector.py` |
| `last_backfill_started_at` | ALREADY IMPLEMENTED | `self.last_backfill_started_at` in `app/collector.py` |
| `last_backfill_completed_at` | ALREADY IMPLEMENTED | `self.last_backfill_completed_at` in `app/collector.py` |
| `db_status` | ALREADY IMPLEMENTED | `self.db_status` in `app/collector.py` |
| `mqtt_status` | ALREADY IMPLEMENTED | `self.mqtt_status` in `app/collector.py` |
| `reconnect_attempt` | ALREADY IMPLEMENTED | `self.reconnect_attempt` in `app/collector.py` |
| `current_backoff` | ALREADY IMPLEMENTED | `self.current_backoff` in `app/collector.py` |
| `stop_event` | ALREADY IMPLEMENTED | `self.stop_event` in `app/collector.py` |
| `loop_alive_heartbeat` | PROPOSED FOR IMPLEMENTATION | Atomic update to `/tmp/collector_health.json` |

## Health Semantics

- HEALTHY: Collector event loop is alive and actively progressing (`LIVE`, `BACKFILLING`, `BACKOFF`). Exit Code 0.
- DEGRADED: Collector loop is alive, but an external dependency is unavailable (Terminal temporarily disconnected during backoff, or MQTT down). Exit Code 0.
- UNHEALTHY: Collector process/FSM loop has stalled, crashed, deadlocked, or failed to update heartbeat file within state-aware threshold. Exit Code 1.
- device outage: Handled cleanly by FSM `BACKOFF` state. Collector loop remains HEALTHY / DEGRADED; Docker healthcheck does NOT fail.
- DB outage: Handled cleanly by FSM `BACKOFF` state. Collector loop remains HEALTHY / DEGRADED.
- MQTT outage: Handled cleanly by FSM `State.DEGRADED`. Collector loop remains DEGRADED (DB persistence intact); Docker healthcheck does NOT fail.

## Health Status File

- path: `/tmp/collector_health.json`
- format: JSON (Schema Version `"1.0"`)
- fields: `schema_version`, `updated_at`, `state`, `loop_alive`, `device_connected`, `db_status`, `mqtt_status`, `reconnect_attempt`, `current_backoff_seconds`, `last_connect_success`, `last_backfill_completed_at`, `last_event_received`, `last_event_persisted`
- update mechanism: Event-driven + 10s idle ping update in `handle_live()` / `handle_backoff()` / `handle_backfilling()`.
- write frequency: Every 10.0 seconds or on state transition.
- atomic: YES (Writes to `/tmp/collector_health.json.tmp` then `os.replace`).
- sensitive data: NO (Zero secrets, passwords, Comm Keys, employee names, user IDs, or attendance payloads).

## Stall Detection

- mechanism: Non-invasive CLI module `python -m app.healthcheck` checks `/tmp/collector_health.json` file timestamp age.
- LIVE threshold: 120.0 seconds (`live_capture()` yields every 10s).
- BACKOFF threshold: 120.0 seconds (Max backoff delay is 60s $\pm 20\%$).
- BACKFILLING threshold: 600.0 seconds (Accommodates large historical log retrieval up to 100k records).
- startup grace: 30.0 seconds (`start_period` in Docker Compose).
- physical 100k assumption: 600s threshold provides conservative headroom without false unhealthy triggers.

## Docker Healthcheck

- command: `["CMD", "python", "-m", "app.healthcheck"]`
- interval: 30s
- timeout: 10s
- retries: 3
- start_period: 30s
- automatic restart behavior: Docker Compose marks container status as healthy/unhealthy; does not force restart loop during expected dependency outages under `restart: unless-stopped`.

## Health Matrix

| Runtime Condition | App Status | Docker Health | Reason |
| ----------------- | ---------- | ------------- | ------ |
| LIVE (All dependencies healthy) | HEALTHY | HEALTHY (Exit 0) | Normal operation |
| LIVE (MQTT broker down) | DEGRADED | HEALTHY (Exit 0) | DB persistence & ZK stream intact |
| Terminal Offline (BACKOFF active) | DEGRADED | HEALTHY (Exit 0) | Reconnect FSM loop progressing |
| PostgreSQL Down (BACKOFF active) | DEGRADED | HEALTHY (Exit 0) | Reconnect FSM loop progressing |
| BACKFILLING (History retrieval active) | HEALTHY | HEALTHY (Exit 0) | Historical sync in progress (< 600s) |
| FSM Loop Stalled / Deadlocked | UNHEALTHY | UNHEALTHY (Exit 1) | Heartbeat stale > 120s threshold |
| Health File Missing / Malformed | UNHEALTHY | UNHEALTHY (Exit 1) | Collector failed to write valid health file |
| STOPPING / STOPPED | STOPPED | UNHEALTHY (Exit 1) | Shutdown in progress or complete |

## Files Proposed

- add: `app/healthcheck.py`, `tests/test_healthcheck.py`
- modify: `app/collector.py`, `docker-compose.yml`
- SQL changes: NONE
- Docker changes: Add `healthcheck:` block to `docker-compose.yml`
- device changes: NONE

## Tests

- health module: Validates LIVE, DEGRADED, BACKOFF, BACKFILLING, stale age detection, missing file, malformed JSON, and Exit Code 0 / 1 responses.
- collector integration: Verifies atomic status file creation, transition updates, and cleanup on shutdown.
- future controlled tests: Simulated process stall & heartbeat timeout test.

## Architecture Boundaries

- Native Push: Unchanged (Python Collector over TCP 4370 remains primary architecture).
- Employee Identity Mapping: Unchanged (`ensure_employee_stub` satisfies FK constraint automatically).
- RTC write: Unchanged (No automatic RTC write).
- periodic backfill: Unchanged (Disabled by default `PERIODIC_RECONCILIATION_MINUTES = 0`).

## Documentation

- healthcheck doc: Created ([COLLECTOR_HEALTHCHECK.md](file:///d:/Dev/adms-server/docs/COLLECTOR_HEALTHCHECK.md))
- report: Persisted ([ADMS-Collector-Healthcheck-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Collector-Healthcheck-001.md))
- STATUS: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))

## Proposed WRITE PromptID

- `ADMS-Collector-Healthcheck-002`
- ready: YES
- blockers: NONE

## FINAL

- health semantics defined: YES
- stall detection designed: YES
- external dependency outages separated from collector failure: YES
- backfill-safe health behavior designed: YES
- safe to implement: YES
- blockers: NONE

STOP.
