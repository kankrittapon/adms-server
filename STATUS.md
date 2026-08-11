# ADMS Server Project Status

## Active System Baseline

* **Target Biometric Terminal**: SONIC / ZKTeco ZEM560_TFT (MIPS Linux 2.6.24 Treckle, Firmware `Ver 6.60 Aug 26 2011`)
* **Host Address**: `192.168.1.248` (AI-Brain Host) / Terminal: `192.168.1.201`
* **Collector Protocol**: ZK Binary Protocol over TCP 4370 (`pyzk==0.9`, Comm Key `600`)
* **Collector Engine**: Modular Finite State Machine (`app/collector.py`)
* **Backfill System**: Hybrid Reconciliation (`BACKFILLING` -> `LIVE`)
* **Healthcheck System**: Atomic Ephemeral State File (`/tmp/collector_health.json`) + Non-Invasive CLI (`app/healthcheck.py`)
* **Identity Architecture**: Human Master (`human_employees`) & Device Identity (`device_users`) Strict Separation
* **SQL Identity Foundation**: Additive Migration `sql/002_identity_foundation.sql`, Constraint Migration `sql/003_legacy_identity_constraint.sql` & Provenance Schema `sql/004_human_master_schema.sql` Applied
* **Collector Ingestion Pipeline**: Upgraded to Device Identity First (`ensure_device_user()`). Legacy stub creation (`ensure_employee_stub()`) **REMOVED**.
* **Documentation Architecture**: Categorized into 6 domain directories (`docs/architecture/`, `docs/device/`, `docs/collector/`, `docs/data/`, `docs/database/`, `docs/operations/`, `docs/external/ai-brain/`).

---

## Locked Execution Sequence

The project SHALL follow this order:

1. **`ADMS-Docs-Categorize-002`**: Documentation reorganization (**COMPLETE**).
2. **`ADMS-Data-ExcelImport-002`**: Human Master Excel Import (**COMPLETE**).
3. **`ADMS-Checkpoint-PostExcelImport-001`**: Post-import checkpoint (**COMPLETE**).
4. **`ADMS-Data-HumanDeviceMapping-001`**: Human ↔ Device Mapping Workflow Plan (**COMPLETE**).
5. **`ADMS-Data-HumanDeviceMappingSchema-001`**: Human ↔ Device Mapping Schema Enhancement (**COMPLETE** — Designed DDL migration `sql/005_human_device_mapping_schema.sql`).
6. **`ADMS-Data-DeviceUserLifecycle-001`**: Device User Lifecycle / Account Incarnation Audit (**COMPLETE** — Verified `ensure_device_user()` identity reuse, recycling risks, selected Decision B).
7. **`ADMS-Data-HumanDeviceMappingSchema-002`**: Human ↔ Device Mapping Schema Migration Execution (**COMPLETE** — Created migration DDL `sql/005_human_device_mapping_schema.sql`).
8. **`ADMS-Checkpoint-PostMappingSchema-001`**: Post Mapping Schema Recovery Checkpoint (**COMPLETE** — Resolved backup metadata conflict, verified 33/33 tests pass, locked next phase).
9. **`ADMS-Server-DatabaseRebuild-001`**: Server Database Rebuild (**COMPLETE** — 3 Docker fixes, Collector operational, 7 attendance backfilled, authoritative backup verified).
10. **`ADMS-Checkpoint-PostServerRebuild-001`**: Post-Rebuild Checkpoint (**COMPLETE** — READ-ONLY validation PASS, all 3 nodes synced at `a240061`).
11. **`ADMS-Collector-TemporalIdentity-001`**: Collector Temporal Identity Audit & Plan (**COMPLETE — PLAN ONLY** — Audited current timeless resolver, designed temporal `[valid_from, valid_to)` contract, identified TIMEZONE BLOCKER).
12. **`ADMS-Collector-TimestampTimezone-001`**: Timestamp Timezone Audit & Plan (**COMPLETE — PLAN ONLY** — Verified +7h offset on all 7 rows, designed `normalize_device_timestamp()` with `ZoneInfo("Asia/Bangkok")`, deterministic historical correction strategy, 17 planned tests).
13. **`ADMS-Collector-TimestampTimezone-002`**: Timestamp Timezone Implementation (**COMPLETE** — Implemented `normalize_device_timestamp()` with `ZoneInfo("Asia/Bangkok")`, corrected 7 existing rows -7h, rebuilt collector, verified runtime deduplication, 54/54 tests pass).
14. **`ADMS-Collector-TimestampTimezone-003`**: Timestamp Timezone Live Verification Checkpoint (**COMPLETE** — READ-ONLY checkpoint PASS, all 7 rows round-trip verified, 0 duplicates, 54/54 tests pass, backups verified, TemporalIdentity-002 UNBLOCKED).
15. **`ADMS-Collector-TemporalIdentity-002`**: Temporal Identity Implementation (**COMPLETE** — Implemented temporal `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` with `[valid_from, valid_to)` semantics, VERIFIED-only, LIMIT 2 ambiguity defense, realtime + backfill integration, 33 new tests (87/87 total pass), deployed to ai-brain, collector rebuilt, runtime LIVE+HEALTHY, 0 mappings, all attendance employee_id NULL).
16. **`ADMS-Collector-TemporalIdentity-003`**: Temporal Identity Live Verification Checkpoint (**COMPLETE** — READ-ONLY checkpoint PASS, resolver source verified on ai-brain, VERIFIED-only + `[valid_from, valid_to)` + ambiguity fail-safe confirmed, realtime + backfill paths verified, 87/87 tests pass, 0 mappings, runtime LIVE+HEALTHY, backup verified, Human ↔ Device Mapping PLAN AUTHORIZED).
17. **`ADMS-Collector-AttendanceParseTime-001`**: Parse_Time Bug Fix (**RECOMMENDED — NON-BLOCKING** — `parse_time()` fails on `HH:MM:SS` format, only affects `status` field).
18. **`ADMS-Data-HumanDeviceMapping-002`**: Human ↔ Device Mapping Workflow Plan (**NEXT — READ-ONLY / WORKFLOW PLAN ONLY** — Design administrator-controlled mapping workflow using 120 Human Master records, 2 device users, temporal valid_from/valid_to, verified_by, verification_method, verification_note).
19. **Native ADMS Push E2E**: EXPERIMENTAL TRACK ONLY (Isolated verification after identity workflow foundation is complete).

---

## Current Identity & Checkpoint State

* **Collector Identity Transition**: COMPLETE (`ADMS-Collector-IdentityTransition-002`)
* **Device Identity Model**: OPERATIONAL (`devices` PK 1, `device_users` 2 accounts)
* **Human Master Auto-Creation**: DISABLED (Collector NEVER auto-creates Human rows)
* **Legacy Stub Creation**: DISABLED (0 new stubs created)
* **Unmapped Attendance**: SUPPORTED (`employee_id = NULL` persisted cleanly)
* **Human Master Schema Foundation**: COMPLETE (`sql/004_human_master_schema.sql`: `branch`, `category`, `human_employee_sources` applied)
* **Documentation Categorization**: COMPLETE (`ADMS-Docs-Categorize-002`: 20 canonical docs moved to category directories, relative Markdown links active)
* **Human Master Excel Data Import**: COMPLETE (`human_employees` 120 records, `human_employee_sources` 120 records, dry-run verified 0 NEW / 120 UNCHANGED)
* **Human ↔ Device Mapping Plan**: COMPLETE (`ADMS-Data-HumanDeviceMapping-001` — PLAN ONLY)
* **Human ↔ Device Mapping Schema Plan**: COMPLETE (`ADMS-Data-HumanDeviceMappingSchema-001` — PLAN ONLY)
* **Device User Lifecycle Audit**: COMPLETE (`ADMS-Data-DeviceUserLifecycle-001` — PLAN ONLY)
* **device_user recycling**: VERIFIED RISK (Reuses `device_user_pk` on conflict `(device_id, device_user_id)`)
* **current account incarnation support**: PARTIAL / MODIFIED FOR MIGRATION 005 (Decision B selected)
* **Human ↔ Device Mapping Schema Migration**: COMPLETE (`sql/005_human_device_mapping_schema.sql` created incorporating `roster_last_seen_at`, `inactive_at`, `valid_from`, `valid_to`, `verified_by`, `verification_method`, `verification_note`)
* **Device User Lifecycle Storage**: IMPLEMENTED (`roster_last_seen_at`, `inactive_at` in migration DDL)
* **Automatic Roster Lifecycle Detection**: NOT IMPLEMENTED / PENDING
* **Human ↔ Device VERIFIED Mappings**: 0 records (UNMAPPED)
* **Human ↔ Device Mapping WRITE**: NOT AUTHORIZED
* **Automatic Sequential user_id Mapping**: PROHIBITED (Excel row 1 != ZKTeco user_id 1)
* **ZKTeco Terminal Writes from Human Import**: NONE (0 terminal socket calls)
* **Remote Fingerprint Enrollment**: UNSUPPORTED / NOT USED
* **Native ADMS Push E2E**: NOT STARTED (EXPERIMENTAL / DEFERRED)
* **Real PostgreSQL Post-Import Recovery Backup**: VERIFIED (`adms_post_excel_import_20260811_121449.dump`, SHA256 `d621f280...`)
* **Backup Format**: `pg_dump` Custom Format (PGDMP_V1)
* **Database Rebuild**: COMPLETE (`ADMS-Server-DatabaseRebuild-001` — database reconstructed from canonical sources: migrations 001-005, Excel Human Master 120 records, live ZKTeco terminal 7 attendance records, 2 device users)
* **Collector Docker Package Fix**: COMPLETE (3 fixes: Dockerfile `COPY app/ ./app/` + `CMD python -m app.main`, `iputils-ping`, DB env vars in docker-compose.yml)
* **Authoritative Reconstructed Backup**: VERIFIED (`adms_reconstructed_authoritative_20260811_153725.dump`, 44980 bytes, SHA256 `5386681d...`, `pg_restore -l` VERIFIED 79 TOC entries)
* **Backup Archive Readability**: VERIFIED via `pg_restore -l`
* **Temporal Identity Audit**: COMPLETE (`ADMS-Collector-TemporalIdentity-001` — PLAN ONLY — current resolver is TIMELESS, temporal contract designed `[valid_from, valid_to)`)
* **Timezone Blocker**: RESOLVED (`ADMS-Collector-TimestampTimezone-002` — `normalize_device_timestamp()` with `ZoneInfo("Asia/Bangkok")` implemented in `app/timestamp_utils.py`, applied to realtime/backfill/MQTT/watermark paths, 7 historical rows corrected -7h, runtime deduplication verified, 54/54 tests pass)
* **Parse_Time Bug**: IDENTIFIED (NON-BLOCKING — `parse_time()` fails on `HH:MM:SS`, only affects `status` field, `scan_time` unaffected)
* **Temporal Resolver**: IMPLEMENTED (`ADMS-Collector-TemporalIdentity-002` — `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` with `[valid_from, valid_to)` semantics, VERIFIED-only, LIMIT 2 ambiguity defense, realtime + backfill integration, 87/87 tests pass, deployed to ai-brain, 0 mappings, all attendance employee_id NULL)
* **Historical Reconciliation**: PLANNED (NOT IMPLEMENTED — future unmapped-only retroactive resolution)
* **Device UID Role**: DIAGNOSTIC ONLY (not canonical identity, not tracked by current ingestion)

---

## Recovery Coordinates

* **SOURCE RECOVERY POINT**: Git Commit `242698f` (`feat: design temporal human-device mapping and lifecycle schema foundation (# PromptID: ADMS-Data-HumanDeviceMappingSchema-002)`)
* **DATABASE RECOVERY POINT**: Archive `adms_post_excel_import_20260811_121449.dump` (7,389 bytes, SHA256 `d621f280af2fc3ebcf7e927afd55486cf5b9009cc1603300cc0d2ac60f9ed00a`)

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
| `ADMS-Data-LegacyIdentityConstraint-002` | 2026-08-11 | Constraint Transition Execution | COMPLETE | Applied SQL migration `sql/003_legacy_identity_constraint.sql` dropping `attendance_logs_user_id_fkey` constraint, preserved raw `user_id` column & `UNIQUE (user_id, device_ip, scan_time)` dedupe constraint, verified 100% attendance preservation (6/6 records), and unblocked Collector transition (`ADMS-Collector-IdentityTransition-002`). |
| `ADMS-Collector-IdentityTransition-002` | 2026-08-11 | Identity Transition Execution | COMPLETE | Implemented Collector database layer identity transition (`app/db.py`), removed `ensure_employee_stub()`, added `get_or_create_device()`, `ensure_device_user()`, and `resolve_verified_employee_mapping()`, added test suite (28/28 passed 100%), verified live against physical terminal `192.168.1.201` (0 new stubs created, unmapped scans stored cleanly with `employee_id = NULL`). |
| `ADMS-Checkpoint-PostIdentityTransition-001` | 2026-08-11 | Post-Identity Checkpoint | COMPLETE | Formal recovery checkpoint post-identity transition. Verified `human_employees` 0 records, verified 0 new legacy stubs created, generated real PostgreSQL custom-format backup archive (`adms_post_identity_20260811_113944.dump`), and verified archive listing via `pg_restore -l`. |
| `ADMS-Data-ExcelImport-001` | 2026-08-11 | Excel Import Plan | COMPLETE | Profiled 120 clean Human Master records across 4 categories (`นายทหาร` 20, `พันจ่า` 58, `จ่า` 6, `พลทหาร` 36), verified 0 duplicates, established mapping contract for `human_employees`, rejected 1..120 row mapping assumption. |
| `ADMS-Data-HumanMasterSchema-001` | 2026-08-11 | Schema Readiness Plan | COMPLETE | Reviewed `human_employees` schema, rejected invalid/unsafe `ON CONFLICT (display_name)` idempotency, designed additive migration `sql/004_human_master_schema.sql` (`branch`, `category`, `human_employee_sources` provenance table), selected Option B decision gate. |
| `ADMS-Data-HumanMasterSchema-002` | 2026-08-11 | Schema Foundation Execution | COMPLETE | Applied SQL migration `sql/004_human_master_schema.sql` adding `branch` & `category` columns to `human_employees`, created `human_employee_sources` provenance linkage table (`UNIQUE (source_system, source_record_key)`), created pre-migration backup (`adms_pre_schema004_20260811_115214.dump`), and verified unit test suite (28/28 passed). |
| `ADMS-Docs-Categorize-001` | 2026-08-11 | Docs Categorization Plan | COMPLETE | Inventoried 55 documentation files, classified 20 canonical root docs into 6 domain categories (`architecture/`, `device/`, `collector/`, `data/`, `database/`, `operations/`), mapped flat reports retention, designed `docs/README.md` navigation map. |
| `ADMS-Docs-Categorize-002` | 2026-08-11 | Docs Categorization Execution | COMPLETE | Reorganized 20 canonical docs into 6 domain subdirectories using `git mv`, separated AI-Brain docs under `docs/external/ai-brain/`, created top-level `docs/README.md` navigation map using relative Markdown links, updated project cross-references. |
| `ADMS-Data-ExcelImport-002` | 2026-08-11 | Excel Import Execution | COMPLETE | Implemented import utility `app/import_excel_human_master.py`, verified dry-run (120 records, 4 categories), generated pre-import recovery backup `adms_pre_excel_import_20260811_120503.dump`, added test suite (33/33 passed 100%), verified zero terminal access. |
| `ADMS-Checkpoint-PostExcelImport-001` | 2026-08-11 | Post-Import Checkpoint | COMPLETE | Verified 120 `human_employees` & 120 `human_employee_sources` records, 0 mappings created, 6/6 attendance logs preserved, generated post-import recovery backup `adms_post_excel_import_20260811_121449.dump`, verified archive via `pg_restore -l`. |
| `ADMS-Data-HumanDeviceMapping-001` | 2026-08-11 | Human Device Mapping Plan | COMPLETE | Designed Human ↔ Device mapping architecture, evidence hierarchy, controlled test-scan workflow, schema gap analysis. Identified missing auditability & temporal identity. Selected Route B: `ADMS-Data-HumanDeviceMappingSchema-001`. |
| `ADMS-Data-HumanDeviceMappingSchema-001` | 2026-08-11 | Mapping Schema Plan | COMPLETE | Designed DDL migration `sql/005_human_device_mapping_schema.sql` adding temporal bounds (`valid_from`, `valid_to`), audit fields (`verified_by`, `verification_method`, `verification_note`), active partial unique index, and rollback plan. |
| `ADMS-Data-HumanDeviceMappingSchema-002` | 2026-08-11 | Mapping Schema Execution | COMPLETE | Applied migration `sql/005_human_device_mapping_schema.sql` — temporal bounds, audit fields, `chk_temporal_validity`, `chk_verified_metadata`, `chk_verification_method`, partial unique index `idx_active_verified_device_user`. |
| `ADMS-Data-DeviceUserLifecycle-001` | 2026-08-11 | Lifecycle Audit | COMPLETE | Verified `ensure_device_user()` identity reuse, recycling risks, selected Decision B (roster lifecycle columns). |
| `ADMS-Checkpoint-PostMappingSchema-001` | 2026-08-11 | Post-Schema Checkpoint | COMPLETE | Resolved backup metadata conflict, verified 33/33 tests pass, locked next phase. |
| `ADMS-Server-DatabaseRebuild-001` | 2026-08-11 | Server Rebuild | COMPLETE | Reconstructed ADMS deployment: 3 Docker build fixes (package layout, iputils-ping, DB env vars), Collector fully operational (LIVE state, 7 attendance records backfilled from live terminal), 33 tests passed, authoritative backup created and verified. |
| `ADMS-Checkpoint-PostServerRebuild-001` | 2026-08-11 | Post-Rebuild Checkpoint | COMPLETE | READ-ONLY validation of reconstructed deployment. Verified git sync (TELEPHONE=origin=ai-brain=`a240061`), 3 ADMS containers running 0 restarts, DB row counts match (human_employees=120, attendance_logs=7, mappings=0), schema 005 constraints present, Collector LIVE+HEALTHY, ZKTeco connected, backup 44980 bytes SHA256 `5386681d...` verified 79 TOC entries, 33 tests passed. |
| `ADMS-Collector-TemporalIdentity-001` | 2026-08-11 | Temporal Identity Audit & Plan | COMPLETE | PLAN ONLY — Audited current timeless resolver (`resolve_verified_employee_mapping`), designed temporal `[valid_from, valid_to)` contract, traced realtime & backfill ingestion paths, identified TIMEZONE BLOCKER (pyzk naive Bangkok local UTC+7 stored as TIMESTAMPTZ interpreted as UTC → +7h offset), classified parse_time bug as NON-BLOCKING, verified Schema 005 & existing indexes sufficient, produced implementation plan for `ADMS-Collector-TemporalIdentity-002`. |
| `ADMS-Collector-TimestampTimezone-001` | 2026-08-11 | Timestamp Timezone Audit & Plan | COMPLETE | PLAN ONLY — Independently verified +7h offset on all 7 attendance rows (raw_payload + terminal data confirm), designed `normalize_device_timestamp()` with `ZoneInfo("Asia/Bangkok")` (Python 3.12 zoneinfo available), deterministic Strategy A correction (-7h UPDATE), 17 planned tests, identified latent watermark comparison bug (naive vs aware TypeError), confirmed no PostgreSQL/container TZ change needed. |
| `ADMS-Collector-TimestampTimezone-002` | 2026-08-11 | Timestamp Timezone Implementation | COMPLETE | Implemented `normalize_device_timestamp()` in `app/timestamp_utils.py`, updated `app/db.py` (realtime + backfill), `app/collector.py` (watermark comparison), `app/mqtt_client.py` (MQTT payload), corrected 7 historical rows -7h in single transaction, 21 new tests (54/54 total pass), rebuilt collector, runtime verified (0 duplicates, backfill idempotent, LIVE+HEALTHY), pre/post backups verified, all 3 nodes synced at `44202d4`. |
| `ADMS-Collector-TimestampTimezone-003` | 2026-08-11 | Timestamp Timezone Live Verification Checkpoint | COMPLETE | READ-ONLY checkpoint. Verified git sync (all 3 nodes at `5adae55`), runtime healthy (3 containers, collector LIVE), DB integrity (all counts match), 7/7 attendance rows round-trip PASS (0 remaining +7h errors), 0 duplicates (UNIQUE constraint intact), `normalize_device_timestamp()` present in all 4 code paths, 54/54 tests pass, pre/post backups verified (`pg_restore -l` PASS), ZKTeco connected (no writes), parse_time defect NON-BLOCKING, TemporalIdentity-002 UNBLOCKED. |
| `ADMS-Collector-TemporalIdentity-002` | 2026-08-11 | Temporal Identity Implementation | COMPLETE | Implemented temporal `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` with `[valid_from, valid_to)` semantics (valid_from inclusive, valid_to exclusive), VERIFIED-only filtering, LIMIT 2 ambiguity defense (multiple matches → None + error log), updated realtime path (`save_attendance_log`) and backfill path (`save_attendance_batch` — per-record resolution), 33 new tests (87/87 total pass), deployed to ai-brain, collector rebuilt, runtime LIVE+HEALTHY (0 restarts), 0 mappings, all 7 attendance rows employee_id NULL, Human Master 120 preserved, no device writes. |
| `ADMS-Collector-TemporalIdentity-003` | 2026-08-11 | Temporal Identity Live Verification Checkpoint | COMPLETE (Latest Task) | READ-ONLY checkpoint PASS. Verified git sync (all 3 nodes at `ea80fb4`), resolver source verified on ai-brain (VERIFIED-only, `[valid_from, valid_to)`, LIMIT 2 ambiguity defense, canonical scan_time post-normalization), realtime + backfill paths verified, dedupe constraint unchanged (0 duplicates), timestamp regression PASS (0 +7h errors), runtime LIVE+HEALTHY (0 restarts), 87/87 tests pass, Human Master 120/120 preserved, backup verified (`pg_restore -l` PASS), 0 mappings, device unmodified. Human ↔ Device Mapping PLAN AUTHORIZED. |

---

## Pending & Upcoming Work

1. **Human ↔ Device Mapping Workflow Plan**:
   - `# PromptID: ADMS-Data-HumanDeviceMapping-002` (READ-ONLY / WORKFLOW PLAN ONLY — Design administrator-controlled mapping workflow using 120 Human Master records, 2 device users, temporal valid_from/valid_to, verified_by, verification_method, verification_note. **AUTHORIZED by TemporalIdentity-003 checkpoint.**)

2. **Parse_Time Bug Fix (NON-BLOCKING, recommended)**:
   - `# PromptID: ADMS-Collector-AttendanceParseTime-001` (WRITE mode — Fix `parse_time()` to handle `HH:MM:SS` format, restore correct `status` field computation).

3. **Native ADMS Push E2E** (Locked Step):
   - Experimental track only. Deferred until identity workflow foundation is complete.
