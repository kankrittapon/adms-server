# ADMS Server System Architecture

## Document Status

* **Status**: Canonical Architecture Specification
* **Source PromptID**: `ADMS-Data-IdentityMapping-001`
* **Target Hardware**: SONIC ZEM560_TFT (MIPS Linux 2.6.24, Firmware `Ver 6.60 Aug 26 2011`)
* **Primary Collector Architecture**: Python Finite State Machine (`app/collector.py`, `pyzk==0.9`, TCP 4370)

---

## 1. System Overview & Data Flow

```text
+-----------------------+           +-----------------------------+
| Physical ZKTeco       |           | ADMS Python Collector Engine|
| ZEM560_TFT Terminal   |           | (CollectorStateEngine)      |
| (192.168.1.201:4370)  |           |                             |
|                       |  TCP 4370 |  1. live_capture()          |
|  - Flash Log Memory   |==========>|  2. get_attendance()        |
|  - Keypad & TFT LCD   |           |  3. Watermark Filter        |
+-----------------------+           +-----------------------------+
                                                   |
                                                   | Single-Second Deduplication
                                                   v
                                    +-----------------------------+
                                    | PostgreSQL Database         |
                                    | (adms-postgres / 5432)      |
                                    |                             |
                                    |  - attendance_logs          |
                                    |  - employees                |
                                    |  - sync_events              |
                                    +-----------------------------+
                                                   |
                                                   | Real-time Events Only (Suppressed for Backfill)
                                                   v
                                    +-----------------------------+
                                    | Mosquitto MQTT Broker       |
                                    | (mqtt:1883)                 |
                                    |                             |
                                    |  - attendance/events        |
                                    +-----------------------------+
```

---

## 2. Identity Architecture & Separation Rules

1. **Human Master Data vs Device Identity Separation**:
   - **`employees`**: Represents physical personnel from HR / Excel master files.
   - **`device_users`**: Represents local accounts on physical ZKTeco hardware.
   - **Core Invariant**: ZKTeco `user_id` is **NOT** a human employee ID. Excel import must **NEVER** create terminal users or assign fingerprint slots.
2. **Local Biometric Enrollment**:
   - Fingerprint enrollment is performed locally on the physical terminal keypad (`ADMS-Device-RemoteEnrollmentCapability-001`).
   - Device users enter ADMS only after physical enrollment or read-only `get_users()` discovery.
3. **Attendance Ingestion Independence**:
   - Raw scan events store `(device_id, device_user_id, scan_time)`.
   - Attendance ingestion **NEVER** fails or rejects records due to missing employee mappings. Unmapped scans remain stored with `employee_id = NULL`.

---

## 3. Ingestion & Reliability Architecture

1. **State Machine Execution Loop**:
   - `STARTING` $\to$ `CONNECTING` $\to$ `BACKFILLING` $\to$ `LIVE` (or `DEGRADED` / `BACKOFF` / `STOPPING`).
   - Clean socket disposal and fresh instantiation on every reconnection attempt.
2. **Hybrid Backfill Reconciliation**:
   - Executes `get_attendance()` during `BACKFILLING` state upon startup/reconnect.
   - Computes DB watermark boundary: $\text{MAX(scan\_time)} - 5\text{ mins}$.
   - Filters candidate records client-side in Python.
   - Batch-persists candidates into PostgreSQL in 500-record transaction chunks (`ON CONFLICT DO NOTHING`).
   - Suppresses MQTT broadcast for historical scans to prevent downstream false alerts.
3. **Database & Service Failure Isolation**:
   - Database persistence is the authoritative primary source of truth.
   - If PostgreSQL persistence fails, state engine transitions to `BACKOFF` (logs remain buffered in terminal flash memory).
   - If MQTT broadcast fails, state engine transitions to `DEGRADED` state while continuing DB persistence and live event streaming.

---

## 4. Healthcheck & Liveness Monitoring

- Ephemeral status file `/tmp/collector_health.json` written atomically.
- Non-invasive CLI evaluator `python -m app.healthcheck` checks heartbeat freshness.
- State-aware thresholds: LIVE/BACKOFF $\le 120\text{s}$, BACKFILLING $\le 600\text{s}$.
- Docker healthcheck probes `python -m app.healthcheck` every 30s (`start_period: 30s`).
