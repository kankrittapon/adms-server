# HUMAN ↔ DEVICE MAPPING SCHEMA PLAN REPORT

**PromptID:** `ADMS-Data-HumanDeviceMappingSchema-001`  
**Mode:** READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY  
**Date:** 2026-08-11  

---

## 1. Executive Summary & Authoritative Baseline

This report documents the architectural design, DDL specification, temporal attribution rules, and verification audit model for **Human ↔ Device Mapping Schema Enhancement** (`ADMS-Data-HumanDeviceMappingSchema-001`).

### Target Objectives Addressed
1. **Verification Auditability:** Captures `verified_by`, `verification_method`, and `verification_note`.
2. **Temporal Ownership:** Introduces half-open interval `[valid_from, valid_to)` semantics to prevent misattribution when physical terminal `user_id` values are recycled over time.
3. **Active Uniqueness:** Replaces strict `UNIQUE(device_user_pk)` constraint with a Partial Unique Index (`WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL`), allowing historical ownership rows while guaranteeing at most one active `VERIFIED` owner per device user slot.
4. **Status Expansion:** Adds `CANDIDATE` and `REVOKED` mapping statuses.
5. **Zero Terminal / Zero Database Mutation:** PLAN ONLY. Database schema migrations, mapping insertions, and terminal socket calls remain strictly unexecuted.

---

## 2. Repository & Database Baseline Verification

### Repository Verification
- **Branch:** `main`
- **Local HEAD:** `6d21700c0eb90179afac7b829c6b3a7d7d740fa5`
- **origin/main:** `6d21700c0eb90179afac7b829c6b3a7d7d740fa5`
- **Working Tree Clean:** YES
- **Checkpoint Commit Lineage:** `a7b2cb1` (`ADMS-Checkpoint-PostExcelImport-001`) found.
- **Mapping Plan Lineage:** `6d21700` (`ADMS-Data-HumanDeviceMapping-001`) found.

### Live Database Schema Inspection Baseline
- `human_employees`: 120 records (UUID PK `employee_id`)
- `human_employee_sources`: 120 provenance records (`UNIQUE (source_system, source_record_key)`)
- `devices`: 1 record (`SONIC ZEM560 #1`, serial `3392113170057`)
- `device_users`: 2 records (`user_id = '1'`, `user_id = '2'`)
- `employee_device_mappings`: 0 rows
- `attendance_logs`: 6 records preserved cleanly
- `employees` (Legacy stubs): 2 records preserved historically
- **Repository DDL vs Live Schema Drift:** NONE

---

## 3. Temporal Ownership & History Preservation Model

### Half-Open Interval Semantics: `[valid_from, valid_to)`
- `valid_from TIMESTAMPTZ NOT NULL DEFAULT now()`: Timestamp when the mapping becomes active.
- `valid_to TIMESTAMPTZ NULL`: Timestamp when the mapping expires. `NULL` indicates currently active.
- **Attendance Match Formula:**
  $$\text{scan\_time} \ge \text{valid\_from} \quad \text{AND} \quad (\text{valid\_to IS NULL} \;\lor\; \text{scan\_time} < \text{valid\_to})$$

### Reassignment Workflow
When a terminal `user_id` is reassigned from Human A to Human B at $T_{\text{reassign}}$:
- Human A mapping: Set `valid_to = T_reassign`.
- Human B mapping: Insert new record with `valid_from = T_reassign` and `valid_to = NULL`.

---

## 4. Verification Audit Model

Required audit fields on `employee_device_mappings`:
- `verified_at`: Timestamp of verification (`TIMESTAMPTZ`).
- `verified_by`: Operator identifier or console user (`TEXT`).
- `verification_method`: Controlled string (`TEXT CHECK (...)`):
  - `'CONTROLLED_SCAN'`
  - `'TERMINAL_ROSTER_REVIEW'`
  - `'MANUAL_ADMIN_CONFIRMATION'`
  - `'LEGACY_MIGRATION'`
- `verification_note`: Optional justification text (`TEXT NULL`).

---

## 5. Active Mapping Uniqueness & Overlap Protection

### Replacing Legacy Strict Constraint
`ALTER TABLE employee_device_mappings DROP CONSTRAINT IF EXISTS employee_device_mappings_device_user_pk_key;`

### Creating Partial Unique Index
```sql
CREATE UNIQUE INDEX idx_active_verified_device_user 
  ON employee_device_mappings (device_user_pk) 
  WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL;
```
This guarantees at most one active `VERIFIED` human owner per physical terminal user slot while enabling historical retention.

---

## 6. Proposed Migration Script (`sql/005_human_device_mapping_schema.sql`)

```sql
-- SQL Migration 005: Human ↔ Device Mapping Schema Enhancement
-- PromptID: ADMS-Data-HumanDeviceMappingSchema-002

BEGIN;

ALTER TABLE employee_device_mappings
  ADD COLUMN IF NOT EXISTS verified_by TEXT NOT NULL DEFAULT 'SYSTEM_ADMIN',
  ADD COLUMN IF NOT EXISTS verification_method TEXT NOT NULL DEFAULT 'MANUAL_ADMIN_CONFIRMATION',
  ADD COLUMN IF NOT EXISTS verification_note TEXT,
  ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

ALTER TABLE employee_device_mappings
  ADD CONSTRAINT chk_verification_method CHECK (
    verification_method IN (
      'CONTROLLED_SCAN',
      'TERMINAL_ROSTER_REVIEW',
      'MANUAL_ADMIN_CONFIRMATION',
      'LEGACY_MIGRATION'
    )
  );

ALTER TABLE employee_device_mappings
  DROP CONSTRAINT IF EXISTS employee_device_mappings_mapping_status_check;

ALTER TABLE employee_device_mappings
  ADD CONSTRAINT employee_device_mappings_mapping_status_check CHECK (
    mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY', 'CANDIDATE', 'REVOKED')
  );

ALTER TABLE employee_device_mappings 
  DROP CONSTRAINT IF EXISTS employee_device_mappings_device_user_pk_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_verified_device_user 
  ON employee_device_mappings (device_user_pk) 
  WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_employee_device_mappings_temporal 
  ON employee_device_mappings (device_user_pk, mapping_status, valid_from, valid_to);

COMMIT;
```

---

## 7. Rollback Plan

```sql
BEGIN;

DROP INDEX IF EXISTS idx_employee_device_mappings_temporal;
DROP INDEX IF EXISTS idx_active_verified_device_user;

ALTER TABLE employee_device_mappings
  DROP CONSTRAINT IF EXISTS chk_verification_method,
  DROP CONSTRAINT IF EXISTS employee_device_mappings_mapping_status_check;

ALTER TABLE employee_device_mappings
  ADD CONSTRAINT employee_device_mappings_mapping_status_check CHECK (
    mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY')
  );

ALTER TABLE employee_device_mappings
  DROP COLUMN IF EXISTS verified_by,
  DROP COLUMN IF EXISTS verification_method,
  DROP COLUMN IF EXISTS verification_note,
  DROP COLUMN IF EXISTS valid_from,
  DROP COLUMN IF EXISTS valid_to;

ALTER TABLE employee_device_mappings
  ADD CONSTRAINT employee_device_mappings_device_user_pk_key UNIQUE (device_user_pk);

COMMIT;
```

---

## 8. Test Plan for Future Execution (`002`)

1. **Schema Integrity:** Verify new columns (`verified_by`, `verification_method`, `valid_from`, `valid_to`) exist.
2. **Active Uniqueness:** Verify inserting two active `VERIFIED` mappings for the same `device_user_pk` fails.
3. **Historical Non-Overlapping Mapping:** Verify setting `valid_to` on old mapping and inserting new active `VERIFIED` mapping succeeds.
4. **Temporal Lookup Verification:** Verify `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` returns correct Human UUID for historical timestamps inside interval `[valid_from, valid_to)`.

---

## 9. Next Phase Decision & Sequencing

- **Safe to prepare Mapping Schema WRITE:** YES
- **Next Authorized PromptID:** `ADMS-Data-HumanDeviceMappingSchema-002` (WRITE mode — pending explicit user authorization)
- **Safe to proceed directly to Human ↔ Device Mapping WRITE:** NO (Schema migration must be applied and verified first in `002`).

### Sequence Path
```text
ADMS-Data-HumanDeviceMappingSchema-001 (PLAN ONLY - CURRENT)
        ↓
ADMS-Data-HumanDeviceMappingSchema-002 (Schema Migration WRITE after explicit user approval)
        ↓
ADMS-Data-HumanDeviceMapping-002 (Human ↔ Device Mapping WRITE after explicit user approval)
        ↓
ADMS-Checkpoint-PostHumanDeviceMapping-001
        ↓
Native ADMS Push Experimental Track
```
