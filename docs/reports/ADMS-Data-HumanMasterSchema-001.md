# HUMAN MASTER SCHEMA READINESS PLAN

## Prompt

* PromptID: `ADMS-Data-HumanMasterSchema-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T11:48:00+07:00
* database modified: NO
* schema modified: NO
* Excel imported: NO
* device modified: NO

## Live Human Master Schema

- table: `human_employees`
- rows: 0
- PK: `employee_id UUID DEFAULT gen_random_uuid()`
- UUID: YES (`gen_random_uuid()`)
- display_name unique: **NO** (No UNIQUE constraint exists on `display_name`)
- current provenance: NONE
- current import key: NONE
- current schema sufficient: **NO** (Lacks structured category/branch fields and provenance linkage table)

## Previous Import Contract Review

- ON CONFLICT(display_name) valid SQL: **NO** (Triggers PostgreSQL syntax/constraint error due to missing UNIQUE constraint)
- semantically safe: **NO** (Names are mutable and non-unique)
- display_name canonical identity: **REJECTED**
- display_name + rank canonical identity: **REJECTED**
- correction required: YES (Replace name-based idempotency with explicit provenance table `human_employee_sources`)

## Human Identity

- canonical identity: `employee_id UUID`
- organization stable identifier available: NO (Excel workbook contains no official personnel IDs)
- Excel source identifier available: YES (`source_record_key` derived deterministically)
- future personnel_identifier: Retained nullable for future organization-issued IDs

## Provenance Design

- source_system: `'EXCEL_HUMAN_MASTER'`
- source_record_key: `'EXCEL_FEB69_CAT_ROW_XXX'`
- source_file: `'excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx'`
- source_sheet: `'ยอด ม.ค.69'`
- source_row: Excel row index (1..127)
- source_hash: SHA256 content hash of normalized row values
- import_batch: Timestamped batch identifier

## Recommended Architecture

- Human Master table: `human_employees` (with additive `branch` and `category` text columns)
- source linkage table: `human_employee_sources` (`UNIQUE (source_system, source_record_key)`)
- staging: In-memory dry-run validation script `app/import_excel_human_master.py`
- import batches: Audit logs in `sync_events` or `human_employee_sources`
- structured branch/category fields: `branch` (`เหล่า`), `category` (`นายทหาร`, `พันจ่า`, `จ่า`, `พลทหาร`)

## Re-Import Semantics

- NEW: Insert new `human_employees` UUID + insert `human_employee_sources` linkage.
- UNCHANGED: Skip update when `source_hash` matches.
- CHANGED: Update `human_employees` attributes & update `source_hash` without changing `employee_id` UUID.
- AMBIGUOUS: Flag for manual review.
- MISSING_FROM_SOURCE: Retain existing `human_employees` record (No deletion).

## Source Row Semantics

- canonical Human ID: `employee_id UUID` (NOT source row)
- ZKTeco ID: Independent (`device_users` table)
- provenance use: Import reconciliation ONLY
- row reorder risk: Mitigated via content hashing and source key mapping

## Proposed Additive Schema

- migration required: **YES**
- migration file: `sql/004_human_master_schema.sql` (PLAN ONLY)
- tables: `human_employee_sources`
- columns: `human_employees.branch`, `human_employees.category`
- constraints: `UNIQUE (source_system, source_record_key)`
- indexes: `human_employee_sources_employee_id_idx`

## Import Safety

- fresh pg_dump required: YES (`pg_dump -Fc` immediately prior to WRITE execution)
- pg_restore -l required: YES
- dry-run default: YES (`--dry-run` flag in python import script)
- explicit apply: YES (`--apply` flag required for database commit)
- transaction: YES (Single atomic PostgreSQL transaction)
- ZKTeco access: NONE (0 network or device API calls)

## Privacy

- workbook tracked: YES (`excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx`)
- CSV tracked: NO
- repository risk: Personnel names and ranks tracked in repository
- remediation recommended: Retain tracked status per project baseline, exclude ad-hoc dumps

## Documentation

- HUMAN_MASTER_SCHEMA.md: Created ([HUMAN_MASTER_SCHEMA.md](file:///d:/Dev/adms-server/docs/HUMAN_MASTER_SCHEMA.md))
- Excel import doc: Updated ([EXCEL_HUMAN_MASTER_IMPORT.md](file:///d:/Dev/adms-server/docs/EXCEL_HUMAN_MASTER_IMPORT.md))
- identity mapping: Updated ([EMPLOYEE_IDENTITY_MAPPING.md](file:///d:/Dev/adms-server/docs/EMPLOYEE_IDENTITY_MAPPING.md))
- architecture: Updated ([ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/ADMS_ARCHITECTURE.md))
- STATUS: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- report: Persisted ([ADMS-Data-HumanMasterSchema-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Data-HumanMasterSchema-001.md))

## Proposed Next PromptID

- next: `# PromptID: ADMS-Data-HumanMasterSchema-002` (WRITE Mode: Additive Schema DDL)
- ready: YES
- reason: Additive schema migration `sql/004_human_master_schema.sql` must be applied before importing 120 records into `human_employees` and `human_employee_sources`.
- blockers: NONE

## FINAL

- current schema safe for repeatable import: NO (Requires additive schema migration)
- name-based identity rejected: YES
- Human canonical identity remains UUID: YES
- provenance strategy defined: YES (`human_employee_sources` table)
- re-import strategy defined: YES
- additive migration required: YES (`sql/004_human_master_schema.sql`)
- Excel import remains blocked: YES (Pending additive schema migration)
- safe to prepare next stage: YES
- blockers: NONE

STOP.
