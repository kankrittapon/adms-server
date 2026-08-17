# EMPLOYEE IDENTITY MAPPING PLAN

## Prompt

* PromptID: `ADMS-Data-IdentityMapping-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T11:05:00+07:00
* target repository: `adms-server`
* modifications performed: NO (Documentation writes only)

## Current Identity Model

- employees table role: Mixed (Currently holds both human master data and auto-generated `ensure_employee_stub` device user rows).
- attendance identity: Raw device `user_id` string stored directly in `attendance_logs`.
- ensure_employee_stub behavior: Auto-creates stub row `INSERT INTO employees (user_id, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING` to satisfy foreign-key constraint.
- human/device identity mixed: YES (Current schema mixes human personnel with device-local user IDs).
- multi-device safe: NO (Current single-column FK `user_id REFERENCES employees(user_id)` would cause collisions if two terminals share `user_id='1'`).
- primary architectural risk: Conflating Excel row numbers with physical terminal user IDs and risk of overwriting employee records with auto-stubs.

## Verified Device Identity

- device: SONIC / ZEM560_TFT (`192.168.1.201`, Serial: `3392113170057`)
- current users: 2 enrolled users (`uid=1, user_id='1'` and `uid=2, user_id='2'`)
- device user_id semantics: String identifier local to biometric terminal hardware.
- UID semantics: Internal integer index (`User.uid`).
- fingerprint ownership: Terminal flash memory hardware (`libfpsensor.so`).
- remote enrollment: UNSUPPORTED on current standalone firmware `Ver 6.60` (`CMD_STARTENROLL` times out).
- local enrollment: VERIFIED SUPPORTED via physical terminal keypad and LCD display.

## Excel Human Master

- records: 120 unique employee records profiled (`ADMS-Data-ExcelProfile-001`).
- stable human identifier available: Organization Thai Rank + Display Name (No explicit military ID in workbook).
- row number semantics: Presentation / entry sequence in spreadsheet.
- Excel -> ZKTeco mapping verified: NO.
- safe to auto-create ZKTeco users: **NO** (Excel import MUST NOT create terminal users or assign ZKTeco `user_id`s).

## Identity Boundary

- Human Identity: Real physical person stored in `employees` table (`employee_id` UUID).
- Device Identity: Account local to physical terminal stored in `device_users` (`device_id, device_user_id`).
- Biometric Identity: Hardware fingerprint template owned by terminal flash memory.
- Attendance Identity: Raw event from `(device_id, device_user_id, scan_time)` resolving via `employee_device_mappings`.

## 1..120 Mapping Decision

- classification: UNSUPPORTED / UNVERIFIED
- evidence: Zero technical evidence connects Excel spreadsheet row numbers (1..120) to physical terminal fingerprint slots.
- safe to use: **NO**
- reason: Automatic row-number mapping risks misidentifying employees and creating false attendance records.

## Recommended Data Model

### employees
- purpose: Represents HUMAN MASTER personnel only.
- canonical identifier: `employee_id` (UUID primary key).

### devices
- purpose: Represents physical ZKTeco biometric terminals.
- stable identifier: `serial_number` (e.g. `'3392113170057'`).

### device_users
- purpose: Represents terminal-local user account slots.
- uniqueness: `UNIQUE (device_id, device_user_id)`.

### employee_device_mappings
- purpose: Explicit identity resolution link between human and terminal account.
- verification model: `mapping_status` ('VERIFIED', 'PROBABLE', 'LEGACY').

### attendance_logs
- raw identity preservation: Stores `device_id` and raw `device_user_id`.
- employee_id nullable: `employee_id` UUID column is **NULLABLE**.
- unmapped attendance supported: YES (Unmapped scans ingested cleanly without rejection).

## Enrollment Workflow

1. Human Master record exists in `employees` table (imported from Excel or HR).
2. Operator physically enrolls employee fingerprint on terminal keypad.
3. Terminal creates local account (`device_user_id`).
4. ADMS discovers new terminal user via `get_users()` roster sync.
5. Administrator explicitly links `device_user` to `employee_id` in `employee_device_mappings`.
6. Future attendance events resolve through the verified mapping.

## Device Discovery Strategy

- get_users roster sync: Safe read-only poll of `connection.get_users()` registers new `device_users`.
- attendance-based discovery: Auto-creates `device_users` record if unknown scan arrives.
- terminal writes required: NO.
- recommendation: Hybrid `get_users()` poll + attendance auto-discovery.

## Stub Migration

- current stub behavior: `ensure_employee_stub()` creates placeholder rows in `employees`.
- safe long-term: NO.
- recommended replacement: Deprecate `ensure_employee_stub()`; store unmapped scans directly into `attendance_logs` with `employee_id = NULL`.
- historical stub classification: Classify existing auto-stubs as `LEGACY / UNVERIFIED`.

## Matching Policy

| Match Type | Confidence | Auto Apply | Human Review |
| ---------- | ---------- | ---------- | ------------ |
| Explicit Admin Link | VERIFIED | YES | NO (Already confirmed) |
| Exact Unique Name Match | EXACT_NAME | NO | YES |
| Probable Rank + Name Match | PROBABLE | NO | YES |
| Unmapped Device User | UNMAPPED | NO | REQUIRED |

## Multi-Device Model

- identity key: `(device_id, device_user_id)`
- duplicate user_id across devices supported: YES (User `'1'` on Device A and User `'1'` on Device B map independently).
- IP used as canonical identity: NO (Use permanent `serial_number`).
- serial/device ID recommendation: Primary device key is `devices.serial_number`.

## Attendance Resolution

- unmapped scans persisted: YES
- mapping required for ingestion: NO
- enrichment strategy: Query-time JOIN or background asynchronous resolver.
- historical reconciliation: Re-evaluating unmapped logs when new mapping is established.

## SQL Migration Proposal

- schema change required: YES (Separate human master from device users).
- new tables: `devices`, `device_users`, `employee_device_mappings`.
- modified tables: `employees` (convert PK to UUID), `attendance_logs` (add `device_id`, make `employee_id` nullable).
- migration stages:
  1. Stage 1: Create `devices`, `device_users`, `employee_device_mappings`.
  2. Stage 2: Register physical terminal (`3392113170057`).
  3. Stage 3: Import Excel Human Master data into `employees`.
  4. Stage 4: Sync device roster via `get_users()`.
  5. Stage 5: Execute explicit mapping review.
- backward compatibility: Preserve legacy `attendance_logs` table during migration.
- rollback: Revert schema additions; legacy table structure preserved.

## Excel Import Policy

- Human Master only: YES
- creates terminal users: NO
- assigns ZKTeco user_id: NO
- modifies fingerprints: NO
- import key: `display_name` + `rank` composite key
- dry-run required: YES

## Privacy Boundary

- fingerprint templates stored in ADMS: NO (Templates remain on terminal hardware)
- PII handling: Display names stored securely in PostgreSQL
- report/log restrictions: Redact individual biometric data and credentials

## Documentation

- identity mapping document: Created ([EMPLOYEE_IDENTITY_MAPPING.md](file:///d:/Dev/adms-server/docs/EMPLOYEE_IDENTITY_MAPPING.md))
- architecture updated: Updated ([ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/ADMS_ARCHITECTURE.md))
- report: Persisted ([ADMS-Data-IdentityMapping-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Data-IdentityMapping-001.md))
- STATUS: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
- code modified: NO
- schema modified: NO
- database modified: NO
- device modified: NO

## Proposed Next PromptIDs

Recommended Next PromptIDs:
1. `# PromptID: ADMS-Data-IdentitySchema-001` (Plan ONLY): Design exact SQL DDL migration scripts for `devices`, `device_users`, and `employee_device_mappings`.
2. `# PromptID: ADMS-Data-ExcelImport-001` (Plan ONLY): Design dry-run normalization and import script for populating `employees` from Excel.

## FINAL

- Human Master / Device Identity separation established: YES
- Excel row number treated as ZKTeco user_id: NO
- ZKTeco users automatically created from Excel: NO
- remote fingerprint enrollment required by architecture: NO
- attendance can exist without employee mapping: YES
- multi-device identity model available: YES
- existing stub migration understood: YES
- SQL schema change recommended: YES
- safe to prepare schema migration: YES
- safe to import Excel now: NO (Blocked pending Identity Schema migration approval)
- blockers: NONE

STOP.
