# ADMS COLLECTOR FOUNDATION CHECKPOINT

## Prompt

* PromptID: `ADMS-Checkpoint-CollectorFoundation-001`
* timestamp: 2026-08-11T10:35:00+07:00
* mode: DOCUMENTATION WRITE ONLY
* application modified: NO
* schema modified: NO
* Docker modified: NO
* device modified: NO

---

## 1. Current Foundation Summary

* **Device Profile**: SONIC / ZKTeco ZEM560_TFT Terminal (MIPS CPU, Linux 2.6.24 Treckle, Firmware `Ver 6.60 Aug 26 2011`, Management Plane: Telnet TCP/23, Data Plane: ZK Protocol TCP/4370, Comm Key `600`).
* **Collector State Engine**: Implemented modular FSM (`app/collector.py`, `app/config.py`, `app/db.py`, `app/mqtt_client.py`, `app/main.py`) supporting states `STARTING`, `CONNECTING`, `BACKFILLING`, `LIVE`, `DEGRADED`, `BACKOFF`, `STOPPING`, `STOPPED`.
* **Hybrid Backfill**: Implemented startup/reconnect historical reconciliation (`handle_backfilling()`). Uses client-side watermark timestamp filtering ($\text{MAX(scan\_time)} - 5\text{ mins}$ safety overlap), 500-record batch chunk persistence (`ON CONFLICT DO NOTHING`), and MQTT notification suppression for historical scans.
* **PostgreSQL Role**: Primary authoritative persistence layer (`adms-postgres`, `attendance_logs`, `employees`, `sync_events`).
* **MQTT Role**: Downstream notification broker (`attendance/events`). MQTT failure is non-blocking (engine transitions to `DEGRADED`, DB persistence and ZK stream continue).
* **Reliability Status**: Production-grade reconnect backoff ($2\text{s} \to 60\text{s}$ with $\pm 20\%$ jitter), interruptible sleep via `threading.Event()`, graceful `SIGTERM`/`SIGINT` shutdown.

---

## 2. Invariants & Architecture Principles Established

1. **Realtime-Only Ingestion Deprecated**: Realtime-only stream monitoring is no longer the intended architecture; historical backfill is required to recover downtime scans.
2. **Startup/Reconnect Reconciliation Active**: The collector automatically reconciles terminal flash memory history upon TCP socket connection.
3. **MQTT Replay Suppressed**: Backfilled historical attendance records do NOT publish to MQTT to prevent false real-time alerts on downstream systems.
4. **Periodic Reconciliation Disabled by Default**: `PERIODIC_RECONCILIATION_MINUTES = 0` (Disabled by default until large-history physical benchmarks are evaluated).
5. **No Automatic RTC Write**: Device clock modifications remain disabled pending explicit write authorization.
6. **No Excel Import Executed**: Master data profiling complete (`120` records profiled in `ADMS-Data-ExcelProfile-001`); database import has **NOT** occurred.
7. **Identity Mapping Unverified**: Mapping spreadsheet rows 1..120 to ZKTeco `user_id` values `1..120` remains **NOT VERIFIED**.
8. **Employee Stub Invariant**: `ensure_employee_stub()` is an ingestion compatibility mechanism satisfying foreign-key constraints; it is **NOT** proof of human identity.
9. **No Raw Biometric Template Transport**: Biometric template wire operations are excluded from the production design for security and privacy.

---

## 3. Verified State & Test Status

* **Device Connectivity**: VERIFIED (`192.168.1.201:4370` reachable and authenticated via Comm Key `600`).
* **Realtime Streaming**: VERIFIED (`live_capture()` loop yields events; terminal display/keypad remains **ENABLED**).
* **Historical Log Retrieval**: VERIFIED (`get_attendance()` retrieved 6 raw logs in 0.1803s).
* **Backfill Reconciliation**: VERIFIED (6 records processed and batch-persisted in 0.2008s; 100% idempotent on second run).
* **Deduplication**: VERIFIED (`UNIQUE (user_id, device_ip, scan_time)` with `ON CONFLICT DO NOTHING`).
* **Graceful Shutdown**: VERIFIED (`stop_event` interrupts wait, cleans up ZK socket & MQTT, exits code 0).
* **Automated Unit Tests**: 9/9 unit tests passed (including 100,000-record synthetic benchmark: 0.1180s generation, 0.0040s filtering).

---

## 4. Pending & Not Yet Verified Work

1. **Remote Enrollment Capability**: Unverified on physical unit.
2. **Collector Docker Healthcheck**: Pending design (`ADMS-Collector-Healthcheck-001`).
3. **Employee Identity Mapping & SQL Import**: Pending review (`ADMS-Data-IdentityMapping-001` / `ADMS-Data-ExcelImport-002`).
4. **RTC Synchronization Policy**: Pending write policy design.
5. **Physical 100,000-Record Backfill Benchmark**: NOT TESTED on physical hardware (Physical unit currently contains 6 attendance logs).

---

## 5. Documentation

* checkpoint report: Created ([ADMS-Checkpoint-CollectorFoundation-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Checkpoint-CollectorFoundation-001.md))
* STATUS.md: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
* reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
* commit: NO
* push: NO

---

## 6. FINAL

* foundation checkpoint established: YES
* safe to perform controlled capability testing: YES
* next recommended PromptID: `# PromptID: ADMS-Collector-Healthcheck-001` (Plan ONLY)
* blockers: NONE

STOP.
