# IDENTITY SCHEMA MIGRATION PLAN

## Prompt

* PromptID: `ADMS-Data-IdentitySchema-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T11:08:00+07:00
* database modified: NO
* schema modified: NO
* application modified: NO
* device modified: NO

## Live Schema Baseline

### employees
- columns: `id` (BIGSERIAL PK), `user_id` (TEXT UNIQUE), `display_name`, `rank`, `position`, `military_id`, `national_id_masked`, `date_of_birth`, `created_at`, `updated_at`.
- PK: `id` (BIGSERIAL)
- FK/unique: `user_id` UNIQUE
- rows: 2 rows (Stubs created by collector runtime)
- stub classification: Auto-generated stubs (`User 1`, `User 2`)

### devices
- current status: Not yet present in database.

### attendance_logs
- columns: `id` (BIGSERIAL PK), `user_id` (TEXT REFERENCES employees), `device_ip` (INET), `scan_time` (TIMESTAMPTZ), `punch_type`, `status`, `raw_payload`, `created_at`.
- PK: `id` (BIGSERIAL)
- unique: `UNIQUE (user_id, device_ip, scan_time)`
- FKs: `user_id REFERENCES employees(user_id)`
- rows: 6 stored logs

### live vs repository drift
- status: NO DRIFT. Live schema matches `sql/001_schema.sql` baseline.

## Target Model

### Human Master
- table: `human_employees`
- PK: `employee_id` (UUID PRIMARY KEY DEFAULT `gen_random_uuid()`)
- canonical identity: `employee_id` UUID
- Excel relationship: Populated from Excel master workbook (`120` records).

### devices
- PK: `device_id` (BIGSERIAL)
- stable identity: `serial_number` (e.g. `'3392113170057'`)
- IP role: Network location (`device_ip` INET), updated on discovery.

### device_users
- PK: `device_user_pk` (BIGSERIAL)
- unique identity: `UNIQUE (device_id, device_user_id)`
- UID handling: `device_uid` (Integer index reported by ZKTeco hardware).

### employee_device_mappings
- relationship: Links `human_employees` (UUID) to `device_users` (`device_user_pk`).
- status model: `'VERIFIED'`, `'PROBABLE'`, `'LEGACY'`
- uniqueness: `UNIQUE (device_user_pk)` (One device user maps to at most one employee).

### attendance_logs
- raw device identity: Preserved (`device_id`, `device_user_pk`, `user_id`, `device_ip`).
- resolved human identity: `employee_id` (UUID REFERENCES `human_employees`).
- nullable employee: **YES** (`employee_id` is NULLABLE for unmapped scans).
- legacy compatibility: Legacy columns (`user_id`, `device_ip`) preserved during Stage 1-4 transition.

## Dedupe Strategy

- current: `UNIQUE (user_id, device_ip, scan_time)`
- transitional: Preserve current constraint during Stage 1-4.
- target: `UNIQUE (device_user_pk, scan_time)`
- residual risks: Single-second timestamp resolution (users cannot scan twice in exact same second).

## Existing Device Migration

- serial: `3392113170057` (SONIC ZEM560_TFT)
- device registration: Injected via DDL seed into `devices` table.
- roster source: `get_users()` poll + historical `attendance_logs` distinct `user_id` query.
- historical user discovery: `INSERT INTO device_users ... SELECT DISTINCT user_id FROM attendance_logs`.

## Stub Migration

- current stubs: `ensure_employee_stub()` creates placeholder rows in `employees`.
- classification: `UNVERIFIED / LEGACY`
- migration target: Retire `ensure_employee_stub()`. New scans stored into `attendance_logs` with `employee_id = NULL`.
- deletion planned: NO (Legacy rows preserved in Stage 1).
- collector dependency: Removed in Stage 4.

## Excel Strategy

- records: 120 unique records profiled (`ADMS-Data-ExcelProfile-001`).
- stable identifier: `display_name` + `rank` composite key.
- UUID strategy: `gen_random_uuid()` generated on import.
- staging recommended: YES (`employee_import_staging` table).
- canonical key: `employee_id` UUID.
- direct ZKTeco mapping: **NO**
- terminal writes: **NONE**

## Migration Stages

1. **Stage 1**: `ADMS-Data-IdentitySchema-001` (Plan ONLY) $\to$ **COMPLETE**
2. **Stage 2**: `ADMS-Data-IdentitySchema-002` (WRITE Mode): Apply `sql/002_identity_foundation.sql`.
3. **Stage 3**: `ADMS-Data-ExcelImport-001` / `002`: Import 120 Human Master records into `human_employees`.
4. **Stage 4**: Collector DB Transition (`app/db.py`): Update collector queries to use `device_user_pk`.
5. **Stage 5**: Legacy Cleanup (Future): Retire legacy stub columns after full validation.

## Proposed Stage-1 DDL

Provided for PLAN ONLY review in [IDENTITY_SCHEMA_MIGRATION.md](file:///d:/Dev/adms-server/docs/IDENTITY_SCHEMA_MIGRATION.md).

## Data Migration Plan

- device: Insert physical device row (`3392113170057`).
- device_users: Populate `device_users` from distinct `attendance_logs` raw `user_id`s.
- attendance: Populate `attendance_logs.device_id` and `attendance_logs.device_user_pk`.
- stubs: Legacy stubs untouched; `attendance_logs.employee_id` remains `NULL` for unmapped scans.
- employee mappings: Populated by administrator review or exact matching workflow.

## Locking / Availability

- expected locks: `ALTER TABLE attendance_logs ADD COLUMN` requires brief `SHARE UPDATE EXCLUSIVE` lock.
- collector downtime required: NO (Additive columns permit concurrent collector execution).
- maintenance window: 5-minute window recommended for Stage 2 execution.
- risks: LOW (Additive columns do not break existing queries).

## Backup / Rollback

- required backup: `pg_dump` of database before Stage 2 execution.
- rollback principle: Revert DDL changes (`DROP TABLE employee_device_mappings, human_employees, device_users, devices`).
- attendance preservation: Legacy `attendance_logs` table remains untouched throughout rollback.

## Validation

- row counts: Verify `attendance_logs` count before and after migration.
- constraints: Verify foreign keys and unique indices.
- collector: Verify collector streams live events without error.
- backfill: Verify `get_attendance()` backfill persists logs idempotently.
- healthcheck: Verify `/tmp/collector_health.json` returns Exit Code 0.
- identity correctness: Verify unmapped scans persist cleanly with `employee_id = NULL`.

## Files Proposed

- future migration file: `sql/002_identity_foundation.sql`
- future backfill file: N/A
- code changes: `app/db.py` (Stage 4)
- Docker changes: NONE
- device changes: NONE

## Documentation

- identity schema migration doc: Created ([IDENTITY_SCHEMA_MIGRATION.md](file:///d:/Dev/adms-server/docs/IDENTITY_SCHEMA_MIGRATION.md))
- identity mapping doc: Updated ([EMPLOYEE_IDENTITY_MAPPING.md](file:///d:/Dev/adms-server/docs/EMPLOYEE_IDENTITY_MAPPING.md))
- architecture: Updated ([ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/ADMS_ARCHITECTURE.md))
- STATUS: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- report: Persisted ([ADMS-Data-IdentitySchema-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Data-IdentitySchema-001.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))

## Proposed WRITE PromptID

- `ADMS-Data-IdentitySchema-002`
- ready: YES
- blockers: NONE

## FINAL

- current schema understood: YES
- Human/Device separation implementable additively: YES
- attendance history can be preserved: YES
- legacy stubs can be migrated safely: YES
- Excel import remains blocked: YES (Blocked pending Stage 2 DDL execution)
- schema migration plan complete: YES
- safe to prepare limited schema WRITE: YES
- blockers: NONE

STOP.
