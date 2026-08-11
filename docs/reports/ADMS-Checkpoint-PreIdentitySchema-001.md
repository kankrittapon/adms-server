# ADMS PRE-IDENTITY-SCHEMA CHECKPOINT REPORT

## Checkpoint Metadata

* PromptID: `ADMS-Checkpoint-PreIdentitySchema-001`
* timestamp: 2026-08-11T11:13:00+07:00
* branch: `main`
* remote: `https://github.com/kankrittapon/adms-server.git`
* checkpoint goal: Establish a clean, verified project baseline prior to executing the first additive database schema migration (`sql/002_identity_foundation.sql`).

---

## Current Architecture & System State

1. **Collector State Engine (`app/collector.py`)**:
   - Explicit FSM: `STARTING` $\to$ `CONNECTING` $\to$ `BACKFILLING` $\to$ `LIVE` (or `DEGRADED` / `BACKOFF` / `STOPPING`).
   - Bounded exponential backoff ($2\text{s}\to 60\text{s}$ with $\pm 20\%$ jitter).
   - Interruptible sleep & graceful SIGTERM/SIGINT handler.
   - Socket disposal & fresh instantiation on every reconnect attempt.

2. **Hybrid Attendance Backfill (`app/collector.py`, `app/db.py`)**:
   - Executes historical log reconciliation via `get_attendance()` during `BACKFILLING` state.
   - Computes DB watermark: $\text{MAX(scan\_time)} - 5\text{ mins}$.
   - Filters candidate records client-side in Python.
   - Batch-persists candidate records into PostgreSQL in 500-record chunks (`ON CONFLICT DO NOTHING`).
   - Suppresses MQTT broadcast for historical scans to prevent downstream false alerts.

3. **Collector Healthcheck (`app/healthcheck.py`, `docker-compose.yml`)**:
   - Writes atomic ephemeral status file `/tmp/collector_health.json`.
   - Non-invasive CLI module `python -m app.healthcheck` checks heartbeat freshness.
   - State-aware liveness thresholds: `LIVE`/`BACKOFF` $\le 120\text{s}$, `BACKFILLING` $\le 600\text{s}$.
   - Docker Compose healthcheck block attached to `adms_zkteco_listener` container (`interval: 30s`).

4. **Target Hardware Baseline (SONIC ZEM560_TFT)**:
   - IP: `192.168.1.201`, Serial: `3392113170057`.
   - Platform: ZEM560_TFT (MIPS Linux 2.6.24 Treckle, Firmware `Ver 6.60 Aug 26 2011`).
   - ZK Protocol: TCP 4370 (`pyzk==0.9`, Comm Key `600`).
   - Live roster: 2 enrolled users (`uid=1, user_id='1'` and `uid=2, user_id='2'`).

5. **Data & Identity Boundary Status**:
   - **Excel Employee Master**: 120 unique records profiled (`ADMS-Data-ExcelProfile-001`).
   - **Excel Import Status**: **NOT PERFORMED**. Excel records have NOT been written to PostgreSQL tables.
   - **Terminal User Creation**: **NOT CREATED**. ZKTeco users are NOT automatically created from Excel.
   - **Human Master & Device Identity Separation**: Established and documented ([EMPLOYEE_IDENTITY_MAPPING.md](file:///d:/Dev/adms-server/docs/EMPLOYEE_IDENTITY_MAPPING.md)).
   - **Current Stub Behavior**: Collector currently uses legacy `ensure_employee_stub()` compatibility function to satisfy single-column FK.
   - **Identity Schema Migration**: Stage 1 DDL plan complete (`ADMS-Data-IdentitySchema-001`), **NOT YET APPLIED** to live database.

---

## Known Technical Debt & Not Tested Items

* **Legacy Stub Dependency**: Collector database layer still invokes `ensure_employee_stub()` pending Stage 2 & Stage 4 migration execution.
* **Native Push Protocol**: Push server HTTP endpoint and end-to-end delivery remain unverified (`ADMS-Device-NativePushVerification-001`). Primary production architecture remains Python Collector over TCP 4370.
* **Physical 100k Performance**: 100,000 synthetic benchmark passed in **0.0030s** filtering, but physical terminal transfer of 100k history remains **NOT TESTED** (Unit currently contains 6 logs).
* **RTC Drift**: Terminal clock exhibits -25.39s drift. Automatic RTC sync policy remains **PENDING**.

---

## Explicit Boundary Declarations

- Excel employee import has **NOT** occurred.
- Physical ZKTeco users are **NOT** created from Excel data.
- Remote fingerprint enrollment is **NOT** used (Terminal uses local keypad enrollment).
- Human Master data and Device Identities **WILL** be strictly separated.
- Collector still uses legacy `ensure_employee_stub()` compatibility behavior.
- Identity Schema Stage 1 DDL is **NOT** yet applied to the database.
- Native Push E2E remains **UNVERIFIED**.
- Physical 100k history transfer performance remains **NOT TESTED**.

---

## Verification & Safety Audit

- secret scan: PASSED (Zero passwords, Comm Keys, Telnet credentials, or biometric template blobs present in diff)
- database modified: NO
- runtime container modified: NO
- device modified: NO

---

## Checkpoint Status

* Checkpoint Established: YES
* Safe to proceed to Identity Schema Migration (`ADMS-Data-IdentitySchema-002`): YES
* Blockers: NONE
