# LEGACY IDENTITY CONSTRAINT TRANSITION PLAN

## Prompt

* PromptID: `ADMS-Data-LegacyIdentityConstraint-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T11:28:00+07:00
* database modified: NO
* application modified: NO
* device modified: NO

## Current Constraint

- name: `attendance_logs_user_id_fkey`
- definition: `FOREIGN KEY (user_id) REFERENCES employees(user_id)`
- referenced table: `employees`
- referenced column: `user_id`
- dependent objects: `attendance_logs` table
- current purpose: Legacy integrity constraint linking raw attendance `user_id` to `employees`.
- current problem: Forces Collector to call `ensure_employee_stub()` on every scan to avoid `ForeignKeyViolation` errors, coupling device users to fake employee rows.

## Application Dependencies

- realtime: `save_attendance_log()` calls `ensure_employee_stub()` to satisfy FK.
- backfill: `save_attendance_batch()` calls `ensure_employee_stub()` to satisfy FK.
- reads/reports: SQL queries join `attendance_logs` and `employees` on `user_id`. Since `user_id` string column is preserved, string joins remain functional.
- ensure_employee_stub: Serves solely to satisfy `attendance_logs_user_id_fkey`.
- other dependencies: NONE.

## Target Model

- raw user_id retained: **YES** (`attendance_logs.user_id` string column preserved as `NOT NULL`).
- Human FK retained: **NO** (`attendance_logs_user_id_fkey` constraint dropped).
- Device FK: `attendance_logs.device_id -> devices(device_id)`, `attendance_logs.device_user_pk -> device_users(device_user_pk)`.
- employee_id nullable: **YES** (`attendance_logs.employee_id -> human_employees(employee_id)` NULLABLE).
- dedupe unchanged: **YES** (`UNIQUE (user_id, device_ip, scan_time)` constraint 100% intact).

## Proposed Migration

- file: `sql/003_legacy_identity_constraint.sql` (PLAN ONLY)
- exact logical change: `ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS attendance_logs_user_id_fkey;`
- destructive data operation: **NONE** (0 rows deleted from `attendance_logs` or `employees`).
- unrelated schema changes: **NONE**.
- replacement integrity model: Scoped device user FKs (`device_id`, `device_user_pk`).

## Locking / Availability

- expected lock: `SHARE UPDATE EXCLUSIVE` lock on `attendance_logs` (Instantaneous execution).
- maintenance window: 2-minute operational window.
- Collector pause required: Recommended brief collector pause during DDL execution.
- risk: **LOW** (Dropping FK constraint does not modify table data).

## Backup

- required method: `pg_dump` full logical PostgreSQL backup.
- schema included: YES
- data included: YES
- restore verification required: YES (Verify `pg_restore` dry-run compatibility).

## Validation

- attendance rows: Verify 6/6 attendance logs preserved (0 lost).
- raw user_id: Verify `user_id` values unchanged.
- device identity: Verify `device_id` and `device_user_pk` values intact.
- Human mapping: Verify `employee_id` remains NULL for unmapped scans.
- dedupe constraint: Verify `UNIQUE (user_id, device_ip, scan_time)` remains active.
- Collector: Verify Collector runs cleanly.
- Backfill: Verify `get_attendance()` backfill persists idempotently.
- Healthcheck: Verify `/tmp/collector_health.json` returns Exit Code 0.

## Collector Transition Readiness

- safe to remove ensure_employee_stub after migration: **YES**. Dropping `attendance_logs_user_id_fkey` unblocks `ADMS-Collector-IdentityTransition-002`.
- remaining blockers: NONE.

## Proposed WRITE PromptID

- `ADMS-Data-LegacyIdentityConstraint-002`
- ready: YES
- blockers: NONE

## FINAL

- legacy FK dependency understood: YES
- minimum migration identified: YES (`ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS attendance_logs_user_id_fkey;`)
- attendance history preserved by design: YES
- dedupe unchanged: YES
- real PostgreSQL backup required: YES
- safe to prepare limited constraint WRITE: YES
- blockers: NONE

STOP.
