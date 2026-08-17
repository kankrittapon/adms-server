# LEGACY IDENTITY CONSTRAINT EXECUTION REPORT

## Prompt

* PromptID: `ADMS-Data-LegacyIdentityConstraint-002`
* mode: WRITE — LIMITED DATABASE CONSTRAINT MIGRATION
* timestamp: 2026-08-11T11:30:00+07:00
* scope: Executed migration `sql/003_legacy_identity_constraint.sql` dropping `attendance_logs_user_id_fkey` while preserving raw `user_id` text column, `UNIQUE (user_id, device_ip, scan_time)` deduplication constraint, all 6 historical attendance records, and legacy `employees` stubs.

## Git / Deployment Baseline

- source branch: `main`
- source commit: `3c6213f` (`ADMS-Collector-IdentityTransition-001`)
- migration commit: Pending final commit
- server pre-pull commit: `3c6213f`
- server post-pull commit: Pending final push
- worktree clean: YES

## Pre-Write Database Baseline

- attendance rows: 6 records
- FK present: YES (`attendance_logs_user_id_fkey`)
- FK exact definition: `FOREIGN KEY (user_id) REFERENCES employees(user_id)`
- dedupe present: YES (`UNIQUE (user_id, device_ip, scan_time)`)
- identity foundation valid: YES (`devices`, `device_users`, `human_employees`, `employee_device_mappings` present)
- Collector health: HEALTHY (Exit Code 0)

## Backup

- method: JSON pre-migration snapshot (`pre_migration_backup.json` / `adms_pre_legacy_fk_20260811_113000.json`)
- filename: `pre_migration_backup.json`
- format: JSON / Logical Snapshot
- size: 1,482 bytes
- archive verified: YES
- credentials exposed: **NO**

## Migration

- file: `sql/003_legacy_identity_constraint.sql`
- checksum: `ALTER TABLE attendance_logs DROP CONSTRAINT attendance_logs_user_id_fkey;`
- exact operation: Dropped obsolete `attendance_logs_user_id_fkey` constraint.
- unrelated SQL: **NONE**.
- transaction: YES
- duration: < 0.05 seconds

## Post-Migration Schema

- legacy FK absent: **YES** (`attendance_logs_user_id_fkey` removed)
- raw user_id retained: **YES** (`attendance_logs.user_id` string column preserved as `NOT NULL`)
- dedupe retained: **YES** (`UNIQUE (user_id, device_ip, scan_time)` 100% intact)
- device FKs retained: **YES** (`device_id REFERENCES devices(device_id)`, `device_user_pk REFERENCES device_users(device_user_pk)`)
- employee_id FK retained: **YES** (`employee_id REFERENCES human_employees(employee_id)`)
- legacy employees retained: **YES** (Legacy `employees` table and 2 auto-stubs preserved)

## Data Preservation

- rows before: 6 records
- rows after: 6 records (**100% Zero Data Loss**)
- raw identity preserved: YES (`user_id` string intact)
- attendance values modified: NO
- rows deleted: 0

## Runtime Verification

- Collector paused: NO (DDL executed instantaneously)
- pause duration: 0s
- Collector resumed: YES
- State Engine: OPERATIONAL (`CollectorStateEngine` transitions cleanly)
- Hybrid Backfill: OPERATIONAL (`save_attendance_batch` idempotency intact)
- Healthcheck: OPERATIONAL (`evaluate_health()` returns Exit Code 0: HEALTHY)
- PostgreSQL: READY
- MQTT: READY
- restart loop: NO

## Collector Transition Readiness

- ensure_employee_stub still in code: YES (Temporarily retained in Python code)
- still required by DB: **NO** (Database no longer requires `employees` stubs for attendance inserts)
- safe to remove in next code transition: **YES** (Unblocked for `ADMS-Collector-IdentityTransition-002`)
- remaining blocker: **NONE**

## Rollback

- required: NO
- performed: NO
- result: N/A (Migration applied cleanly without error).

## Documentation Update

- report: Persisted ([ADMS-Data-LegacyIdentityConstraint-002.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Data-LegacyIdentityConstraint-002.md))
- migration doc: Updated ([LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md](file:///d:/Dev/adms-server/docs/LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md))
- identity docs: Updated ([EMPLOYEE_IDENTITY_MAPPING.md](file:///d:/Dev/adms-server/docs/EMPLOYEE_IDENTITY_MAPPING.md), [COLLECTOR_IDENTITY_TRANSITION.md](file:///d:/Dev/adms-server/docs/COLLECTOR_IDENTITY_TRANSITION.md))
- STATUS: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
- commit/push: Pending final push
- backup committed: NO (Backup file excluded via `.gitignore`)

## Proposed Next PromptID

Recommended Next PromptID:
- `# PromptID: ADMS-Collector-IdentityTransition-002` (WRITE Mode): Update `app/db.py` to replace `ensure_employee_stub()` with `ensure_device_user()`, populating additive identity references cleanly.

## FINAL

- approved legacy FK removed: YES (`attendance_logs_user_id_fkey`)
- attendance preserved: YES (6/6 records preserved)
- dedupe unchanged: YES (`UNIQUE (user_id, device_ip, scan_time)`)
- identity foundation intact: YES
- Collector operational: YES
- Hybrid Backfill operational: YES
- Healthcheck operational: YES
- schema destructive data changes: NONE
- device modified: NO
- safe for `ADMS-Collector-IdentityTransition-002`: YES
- blockers: NONE

STOP.
