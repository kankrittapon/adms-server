# ADMS DEVICE ENROLLMENT WORKFLOW — IMPLEMENTATION REPORT

**PromptID:** `ADMS-Data-DeviceEnrollmentWorkflow-002`
**Mode:** WRITE — LIMITED ENROLLMENT INFRASTRUCTURE IMPLEMENTATION + TESTS + LIVE DEPLOYMENT
**Date:** 2026-08-12
**Status:** PASS — PILOT INFRASTRUCTURE READY

---

## AGENT HANDSHAKE

| Item | Value |
|------|-------|
| Agent / Model | Freebuff (Buffy) — deepseek-v4-flash |
| IDE / Host | Freebuff chat session |
| OS | Windows 11 (TELEPHONE, control workstation) + WSL2 |
| Repository | `D:/Dev/adms-server` |
| Branch | `main` |
| MCP pty-mcp available | YES |
| pty-mcp used | YES (stateful SSH sessions for pre-flight and deployment) |
| ai-brain verified | YES (`hostname=ai-brain`, `user=kanfullbuster`) |
| stateful SSH verified | YES (cwd persists across separate MCP calls) |
| temporary SSH transport scripts created | **0** (MCP client drivers used; deleted after use) |

## GIT BASELINE

| Item | Value |
|------|-------|
| starting HEAD | `f34ae630707f5db068e70ad1116922c61fd4a007` (checkpoint) |
| origin/main | `f34ae63` → `cdc634d` after implementation |
| ai-brain HEAD | `cdc634d` (synced via pty-mcp `git pull --ff-only`) |
| checkpoint lineage verified | YES (f34ae63 in history) |

Commits created (both pushed, no force push):

```text
4b4a716 feat: add controlled device enrollment infrastructure (# PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002)
cdc634d fix: correct migration 006 constraint syntax (# PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002)
```

## PRE-DEPLOY RUNTIME

| Item | Value |
|------|-------|
| PostgreSQL | OPERATIONAL (adms_postgres healthy) |
| MQTT | OPERATIONAL (adms_mqtt running) |
| Collector | LIVE / HEALTHY |
| Healthcheck | HC_RC=0 |
| terminal roster | 0 users |

## DATABASE BASELINE (pre- and post-deploy identical)

| Table | Count |
|-------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| devices | 1 |
| device_users | 2 (historical inactive rows) |
| attendance_logs | 7 |
| employee_device_mappings | 0 |
| device_user_enrollments | 0 (new table, empty) |

## ENROLLMENT STORAGE

| Item | Value |
|------|-------|
| existing schema sufficient | NO (no enrollment reservation/audit storage) |
| new schema required | YES |
| migration | `sql/006_device_user_enrollment_schema.sql` — additive, transactional |
| enrollment storage | `device_user_enrollments` (BIGSERIAL PK, employee_id/device_id FKs, reserved_device_user_id, status CHECK over 9 states, audit timestamps, evidence columns) |
| indexes | pkey + `idx_enrollments_device_status`, `idx_enrollments_employee_status`, `idx_enrollments_terminal_id`, partial unique `uq_active_enrollment_per_human_device` |
| constraints | `uq_enrollment_terminal_id`, `chk_scan_confirmed_has_time`, `chk_ready_has_scan_time`, `chk_ready_has_confirmed_by`, `chk_cancelled_has_notes`, status CHECK |
| applied on ai-brain | YES (MIG_RC=0) |

**Schema/backup:**

| Item | Value |
|------|-------|
| pre-write backup | `backups/adms_pre_migration_006_20260812_145700.dump` (45,669 bytes, SHA256 `d03fceb48f6defd5bd069240e53498168254f941964a4197921f09dfda82dcbc`) |
| pg_restore -l | OK (RESTORE_L_OK) |
| post-write backup | `backups/adms_post_migration_006_20260812_145711.dump` (45,683 bytes, SHA256 `28887844814ab22a59678588c113bd072ac94af8202499e58f30695a31a57e5e`) |
| destructive change | NONE (additive only; no attendance/Human Master/device_user changes) |

## STATE MODEL

Implemented in `app/enrollment.py` + DB CHECK constraint:

```text
RESERVED
  → TERMINAL_ACCOUNT_CREATED
      → FINGERPRINT_ENROLLMENT_PENDING
          → FINGERPRINT_ENROLLED
              → CONTROLLED_SCAN_PENDING
                  → CONTROLLED_SCAN_CONFIRMED
                      → READY_FOR_MAPPING
Active states may → CANCELLED; CONTROLLED_SCAN_CONFIRMED/READY_FOR_MAPPING may → RETIRED.
```

- `READY_FOR_MAPPING` is the handoff boundary. **VERIFIED mapping is NOT an
  enrollment state** — `employee_device_mappings` remains the sole
  authoritative source of VERIFIED ownership (no duplicate truth).
- Evidence enforcement: `CONTROLLED_SCAN_CONFIRMED`/`READY_FOR_MAPPING` require
  `controlled_scan_time`; `READY_FOR_MAPPING` requires `confirmed_by`;
  `CANCELLED` requires `notes`. Transition layer + DB constraints both enforce.
- No transition may skip required evidence (e.g. `RESERVED → READY_FOR_MAPPING`
  is rejected).

## ID ALLOCATION

| Item | Value |
|------|-------|
| production namespace | 1001+ |
| first eligible ID | 1001 (clean namespace) |
| legacy IDs 1/2 excluded | YES (`LEGACY_TEST_IDS`, never reused) |
| Excel row mapping | NO |
| automatic sequential Human mapping | NO |
| concurrency safe | YES (`pg_advisory_xact_lock` per device + partial unique index + monotonic scan) |
| device scoped | YES (history + reservations per device) |
| recycling | DISALLOWED BY DEFAULT (gaps not back-filled; CANCELLED/RETIRED IDs kept by `uq_enrollment_terminal_id`) |

Allocator `_find_next_available_id()` checks both DB history/reservations
(`device_users` + `device_user_enrollments`) and the live terminal roster.

## RESERVATION

| Item | Value |
|------|-------|
| implemented | YES — `reserve_next_device_user_id(cfg, employee_id, device_id, operator, roster_user_ids=None)` |
| Human required | YES (must exist and be active) |
| device required | YES (must exist and be active) |
| operator captured | YES (`reserved_by`, required non-empty) |
| duplicate prevention | PASS (active-enrollment pre-check + partial unique index; CANCELLED/RETIRED allow re-reservation with next ID) |
| terminal account created during reservation | NO (DB-only) |
| audit | `sync_events` ENROLLMENT_RESERVED |

## TERMINAL ACCOUNT CREATION

| Item | Value |
|------|-------|
| implemented | YES — `create_reserved_terminal_account(cfg, enrollment_id, display_name, device)` |
| mechanism | pyzk `set_user()` (Option A) via injected device connection |
| set_user supported | YES (`user_id`, `name`, `privilege=0`, `password=""`) |
| normal privilege verified | YES (`PRIVILEGE_NORMAL_USER = 0` = pyzk `USER_DEFAULT`; `verify_terminal_account_created` re-checks roster privilege) |
| existing-ID overwrite prevented | YES (roster pre-check + fail-safe raise; `set_user` never called if ID present) |
| device unreachable | fails safely (EnrollmentError, no account created) |
| display name | ASCII printable, ≤20 chars, no UUID/placeholder/pure-number (Thai rendering on ZEM560 not yet verified) |
| concurrent state change | guarded (`WHERE ... AND status = 'RESERVED'` + rowcount check; manual roster review on mismatch) |
| roster verification | `verify_terminal_account_created()` captures `device_uid`, verifies privilege + exact ID |
| production account created during this Prompt | **0** |

## FINGERPRINT

| Item | Value |
|------|-------|
| production enrollment method | PHYSICAL TERMINAL (Human enrolls on keypad) |
| remote fingerprint enrollment | NOT IMPLEMENTED |
| biometric templates stored by ADMS | NO |
| fingerprint evidence | operator confirmation (`FINGERPRINT_ENROLLED` + `fingerprint_confirmed_at`); strongest evidence is the controlled scan |

## CONTROLLED SCAN

| Item | Value |
|------|-------|
| workflow implemented | YES — `start_controlled_scan_window()` (default 5 min), `confirm_controlled_scan(scan_time)`, `mark_ready_for_mapping(operator)` |
| automatic mapping | NO (no mapping at scan confirmation; Human identity confirmation explicit) |
| window | narrow, bounded deadline; scan after deadline rejected; no indefinite pending |
| READY_FOR_MAPPING boundary | controlled scan confirmed + operator identity confirmation (`confirmed_by`, `confirmed_at`) |

## TEMPORAL

| Item | Value |
|------|-------|
| proposed valid_from source | `controlled_scan_time` (enrollment record) |
| valid_to default | NULL (open-ended, created at HumanDeviceMapping time) |
| ID reuse | DISALLOWED BY DEFAULT |

## TESTS

| Item | Value |
|------|-------|
| previous baseline | 105/105 |
| total | **168** |
| passed | **168** |
| failed | 0 |
| new tests | 63 (`tests/test_enrollment.py`) |
| ID allocation | PASS |
| reservation | PASS |
| state transitions | PASS |
| terminal creation | PASS |
| identity safety | PASS (full workflow never touches mappings / human master / attendance) |
| device safety | PASS (only `get_users`/`set_user`; destructive ops never triggered) |

## DEPLOYMENT

| Item | Value |
|------|-------|
| implementation commit | `4b4a716` + `cdc634d` (migration fix) |
| push | YES |
| ai-brain pull via pty-mcp | YES (`git pull --ff-only`, HEAD `cdc634d`) |
| Collector rebuilt | YES (only `listener` rebuilt + redeployed; healthy on 2nd probe) |
| PostgreSQL rebuilt | NO |
| MQTT rebuilt | NO |
| unrelated services modified | NO |
| enrollment module in container | YES (`import app.enrollment` → ENROLLMENT_MODULE_OK) |

## POST-DEPLOY

| Item | Value |
|------|-------|
| PostgreSQL | healthy |
| MQTT | running |
| Collector | LIVE / HEALTHY (HC_RC=0) |
| Healthcheck | HEALTHY |
| terminal user count | 0 |
| production users | 0 |
| employee_device_mappings | 0 |
| device_user_enrollments | 0 |
| restart counts | listener/postgres 0 |

## SAFETY

| Item | Value |
|------|-------|
| Human Master modified | NO |
| historical device users deleted | 0 |
| attendance deleted | 0 |
| Human mappings created | 0 |
| terminal users created | 0 |
| fingerprints modified | NO |
| Native ADMS Push | NOT EXECUTED |
| ai-tmux installed | NO |
| TELEPHONE Docker used | NO (control workstation only) |

## TOOLING

- Remote operations executed through pty-mcp SSH sessions (identity, git,
  backup, migration, rebuild, verification).
- Temporary SSH transport scripts created: **0**. MCP client driver scripts
  (pm_deploy*.py) were used to drive pty-mcp over stdio and were deleted
  after use; no repository or server artifacts remain.

## DOCUMENTATION

| Item | Value |
|------|-------|
| report | `docs/reports/ADMS-Data-DeviceEnrollmentWorkflow-002.md` (this file) |
| workflow doc updated | `docs/data/DEVICE_ENROLLMENT_WORKFLOW.md` (PLANNED → IMPLEMENTED) |
| STATUS updated | YES |

## FINAL

```text
PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002
Agent handshake: PASS
pty-mcp workflow: PASS
temporary SSH transport scripts: 0
enrollment infrastructure: PASS
production ID allocator: PASS
legacy IDs 1/2 protected: YES
reservation workflow: PASS
terminal account creation capability: PASS
physical fingerprint enrollment policy: PASS
controlled scan workflow: PASS
Human mappings created: 0
production terminal users created: 0
tests: 168/168
Collector: OPERATIONAL
Healthcheck: HEALTHY
pilot infrastructure ready: YES
bulk enrollment authorized: NO
HumanDeviceMapping-003 authorized: NO
next authorized PromptID: ADMS-Data-DeviceEnrollmentPilot-001
safe to proceed: YES
blockers: NONE
STOP.
```
