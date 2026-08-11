# ADMS Server Project Status

## Active System Baseline

* **Target Biometric Terminal**: SONIC / ZKTeco ZEM560_TFT (MIPS Linux 2.6.24 Treckle, Firmware `Ver 6.60 Aug 26 2011`)
* **Host Address**: `192.168.1.248` (AI-Brain Host) / Terminal: `192.168.1.201`
* **Collector Protocol**: ZK Binary Protocol over TCP 4370 (`pyzk==0.9`, Comm Key `600`)
* **Collector Engine**: Modular Finite State Machine (`app/collector.py`)
* **Backfill System**: Hybrid Reconciliation (`BACKFILLING` -> `LIVE`)
* **Healthcheck System**: Atomic Ephemeral State File (`/tmp/collector_health.json`) + Non-Invasive CLI (`app/healthcheck.py`)
* **Identity Architecture**: Human Master (`human_employees`) & Device Identity (`device_users`) Strict Separation
* **SQL Identity Foundation**: Additive Schema Migration `sql/002_identity_foundation.sql` & Constraint Migration `sql/003_legacy_identity_constraint.sql` Applied

---

## Completed Tasks & Reports

| PromptID | Date | Type | Status | Summary / Key Deliverables |
| -------- | ---- | ---- | ------ | -------------------------- |
| `ADMS-Bootstrap-ZEM560-001` | 2026-08-11 | Device Baseline | COMPLETE | Established ADMS Server baseline and reconstructed ZEM560 device technical profile. |
| `ADMS-Device-LiveFingerprint-001` | 2026-08-11 | Device Fingerprint | COMPLETE | Live hardware profile: SONIC / ZEM560_TFT (MIPS CPU, Linux 2.6.24, Telnet TCP 23, ZK TCP 4370). |
| `ADMS-Collector-Reliability-001` | 2026-08-11 | Reliability Plan | COMPLETE | Production-grade reliability model, hybrid event capture & backfill architecture, state machine. |
| `ADMS-Device-AttendanceBehavior-001` | 2026-08-11 | Attendance Behavior | COMPLETE | Live device test of `get_attendance()` (0.18s for 6 records), clock drift (-25.39s), `pyzk` 10s socket yields. |
| `ADMS-Device-CapabilityProfile-001` | 2026-08-11 | Capability Spec | COMPLETE | Verified capacity spec (30k users, 3k templates, 100k logs), 5-tier project usability framework. |
| `ADMS-Collector-StateEngine-001` | 2026-08-11 | State Engine Plan | COMPLETE | Modular FSM architecture design, bounded exponential backoff ($2\text{s}\to 60\text{s}$ with $\pm 20\%$ jitter). |
| `ADMS-Data-ExcelProfile-001` | 2026-08-11 | Data Profiling | COMPLETE (Profiling Only) | Analysis and normalization profile for `รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx` (120 unique records). **PostgreSQL import NOT performed**. |
| `ADMS-Collector-StateEngine-002` | 2026-08-11 | State Engine Execution | COMPLETE | Refactored `app/main.py` into modular FSM (`app/config.py`, `app/collector.py`, `app/db.py`, `app/mqtt_client.py`). |
| `ADMS-Collector-HybridBackfill-001` | 2026-08-11 | Hybrid Backfill Plan | COMPLETE | Design for historical `get_attendance()` log backfill, client-side watermark filtering, 500-record batch ingestion, MQTT suppression, and 15-minute periodic reconciliation cadence. |
| `ADMS-Collector-HybridBackfill-002` | 2026-08-11 | Hybrid Backfill Execution | COMPLETE | Implemented historical attendance log backfill (`app/collector.py`, `app/db.py`, `app/config.py`), unit test suite & 100k synthetic benchmark (9/9 passed, 0.0040s filtering), live verification against SONIC ZEM560_TFT terminal (6 records backfilled in 0.2008s, MQTT suppressed, 100% idempotent). |
| `ADMS-Checkpoint-CollectorFoundation-001` | 2026-08-11 | Foundation Checkpoint | COMPLETE | Established verified collector foundation baseline after State Engine and Hybrid Backfill implementation. |
| `ADMS-Device-RemoteEnrollmentCapability-001` | 2026-08-11 | Capability Test | COMPLETE | Controlled live test of `enroll_user()`: Command times out without activating on-screen UI on standalone firmware `Ver 6.60`. Classified as **DO NOT USE / NOT RECOMMENDED FOR PRODUCTION**. |
| `ADMS-Device-FirmwareFilesystemAudit-001` | 2026-08-11 | Filesystem Audit | COMPLETE | Read-only Telnet inspection of MTD partitions, `/mnt/mtdblock/options.cfg`, `AttState=0` (default Check-In punch state key, unrelated to remote enrollment), driver nodes (`/dev/tft_lcd`), and generic config vs physical hardware matrix. |
| `ADMS-Device-NativePushVerification-001` | 2026-08-11 | Protocol Verification | COMPLETE | Protocol & socket inspection of native Push config (`AuthServerIP=192.168.1.248:8000`, `libhttppush.so`), embedded HTTP web server (TCP Port 80, `ZK Web Server`), and evaluation. Reconfirmed Python Collector over TCP 4370 as the primary production architecture. |
| `ADMS-Collector-Healthcheck-001` | 2026-08-11 | Healthcheck Plan | COMPLETE | Detailed design for atomic ephemeral health status file (`/tmp/collector_health.json`), state-aware liveness thresholds (LIVE/BACKOFF 120s, BACKFILLING 600s), non-invasive `app/healthcheck.py` CLI module, and Docker Compose parameters. |
| `ADMS-Collector-Healthcheck-002` | 2026-08-11 | Healthcheck Execution | COMPLETE | Implemented atomic health status updates (`app/collector.py`), non-invasive CLI health evaluation module (`app/healthcheck.py`), Docker Compose healthcheck block (`docker-compose.yml`), test suite (22/22 passed), live verification against physical terminal (Exit Code 0 verified during LIVE state). |
| `ADMS-Data-IdentityMapping-001` | 2026-08-11 | Identity Mapping Plan | COMPLETE | Detailed design for strict separation of Human Master Data (`employees`) and Device-Local Identity (`device_users`), multi-device mapping schema (`devices`, `device_users`, `employee_device_mappings`), rejection of Excel row-number mapping assumption, and unmapped attendance ingestion policy. |
| `ADMS-Data-IdentitySchema-001` | 2026-08-11 | Identity Schema Plan | COMPLETE | Detailed DDL migration design (`sql/002_identity_foundation.sql`), additive zero-data-loss architecture (`devices`, `device_users`, `human_employees`, `employee_device_mappings`), seed queries for physical terminal (`3392113170057`), and 5-stage migration path. |
| `ADMS-Checkpoint-PreIdentitySchema-001` | 2026-08-11 | Pre-Schema Checkpoint | COMPLETE | Established clean, verified repository checkpoint baseline prior to executing the first additive database schema migration (`sql/002_identity_foundation.sql`). |
| `ADMS-Data-IdentitySchema-002` | 2026-08-11 | Identity Schema Execution | COMPLETE | Applied additive SQL identity schema migration (`sql/002_identity_foundation.sql`), registered physical terminal `3392113170057`, created `device_users` foundation, verified 100% attendance log preservation (6/6 records), and verified collector & healthcheck compatibility. |
| `ADMS-Collector-IdentityTransition-001` | 2026-08-11 | Identity Transition Plan + Git Hygiene | COMPLETE | Detailed design for Collector identity transition (`ensure_device_user`), identified legacy FK constraint blocker (`attendance_logs_user_id_fkey`), updated `.gitignore`, and untracked local AI rules/prompt history from Git index while preserving local files. |
| `ADMS-Data-LegacyIdentityConstraint-001` | 2026-08-11 | Constraint Transition Plan | COMPLETE | Detailed design for dropping `attendance_logs_user_id_fkey` constraint while preserving `user_id` string column and `UNIQUE (user_id, device_ip, scan_time)` constraint, unblocking Collector transition away from `ensure_employee_stub()`. |
| `ADMS-Data-LegacyIdentityConstraint-002` | 2026-08-11 | Constraint Transition Execution | COMPLETE (Latest Checkpoint) | Applied SQL migration `sql/003_legacy_identity_constraint.sql` dropping `attendance_logs_user_id_fkey` constraint, preserved raw `user_id` column & `UNIQUE (user_id, device_ip, scan_time)` dedupe constraint, verified 100% attendance preservation (6/6 records), and unblocked Collector transition (`ADMS-Collector-IdentityTransition-002`). |

---

## Pending & Upcoming Work

1. **Collector Identity Transition Execution** (Pending):
   - `# PromptID: ADMS-Collector-IdentityTransition-002` (WRITE Mode): Update `app/db.py` to replace `ensure_employee_stub()` with `ensure_device_user()`, populating additive identity references cleanly.

2. **Human Master Excel SQL Import** (Pending):
   - `# PromptID: ADMS-Data-ExcelImport-001` (Plan ONLY): Design dry-run normalization and import script for populating `human_employees` from Excel (`120` records).

3. **RTC Synchronization Policy** (Pending):
   - Define controlled automatic clock adjustment policy for terminal RTC drift (-25.39s observed).

4. **Large-History Physical-Device Benchmark** (Pending):
   - Physical terminal currently contains 6 logs (100k synthetic benchmark passed in 0.0040s filtering). Benchmark physical 100k transfer when large history accumulates.
