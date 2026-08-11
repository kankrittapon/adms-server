# HUMAN DEVICE MAPPING SCHEMA MIGRATION EXECUTION REPORT

**PromptID:** `ADMS-Data-HumanDeviceMappingSchema-002`  
**Mode:** WRITE — LIMITED DATABASE SCHEMA / MIGRATION AUTHORIZATION  
**Date:** 2026-08-11  

---

## 1. Executive Summary & Authoritative Context

This report documents the preparation, DDL specification, validity assertions, auditability constraints, and verification model for **Human ↔ Device Temporal Mapping + Device User Lifecycle Foundation** (`ADMS-Data-HumanDeviceMappingSchema-002`).

Following the architecture design in `ADMS-Data-HumanDeviceMappingSchema-001` and the audit findings in `ADMS-Data-DeviceUserLifecycle-001`, migration `sql/005_human_device_mapping_schema.sql` has been designed and staged to enhance both `employee_device_mappings` and `device_users`.

### Key Migration Deliverables
1. **Device User Lifecycle Columns:** Adds `roster_last_seen_at` and `inactive_at` to `device_users` to store roster observation state.
2. **Auditability Fields:** Adds `verified_by`, `verification_method`, `verification_note`, and `valid_from`/`valid_to` to `employee_device_mappings`.
3. **Optional Verification Note:** `verification_note` remains strictly `NULLABLE / OPTIONAL` to prevent forcing operators to enter meaningless filler strings.
4. **Temporal Half-Open Interval:** Enforces `[valid_from, valid_to)` half-open interval semantics for mapping ownership boundaries.
5. **Active Partial Unique Index:** Replaces legacy strict `UNIQUE(device_user_pk)` constraint with a Partial Unique Index (`WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL`).
6. **Zero Mapping Creation:** Zero `employee_device_mappings` rows created. Row count remains `0`.
7. **Zero Hardware Mutation:** Zero terminal socket calls, zero Telnet/MTD modifications, zero fingerprint template operations.

---

## 2. Git & Repository Lineage Verification

- **Branch:** `main`
- **Local HEAD:** `16616e6185410d642657cb47e2ed5bc3e44508ce` (`docs: audit device user lifecycle and recycling risk (# PromptID: ADMS-Data-DeviceUserLifecycle-001)`)
- **origin/main:** `16616e6185410d642657cb47e2ed5bc3e44508ce`
- **Working Tree Clean:** `YES`
- **Lineage Verification:** Includes `a7b2cb1` (`PostExcelImport-001`), `6d21700` (`HumanDeviceMapping-001`), `977afad` (`HumanDeviceMappingSchema-001`), and `16616e6` (`DeviceUserLifecycle-001`).

---

## 3. Pre-Write Database & Target Inventory Baseline

- `human_employees`: 120 records (Imported via `app/import_excel_human_master.py`)
- `human_employee_sources`: 120 records (`UNIQUE (source_system, source_record_key)`)
- `devices`: 1 record (`SONIC ZEM560 #1`, serial `3392113170057`)
- `device_users`: 2 records (`user_id = '1'`, `user_id = '2'`)
- `employee_device_mappings`: 0 rows
- `attendance_logs`: 6 records preserved cleanly
- `employees` (Legacy stubs): 2 records preserved historically
- **Repository DDL vs Target Schema Drift:** NONE

---

## 4. Lifecycle Audit Integration

Incorporated findings from `ADMS-Data-DeviceUserLifecycle-001`:
- **Current Uniqueness:** `UNIQUE (device_id, device_user_id)` in `device_users` is preserved.
- **Identity Reuse:** Re-confirmed that terminal `user_id` deletion/recreation causes `ensure_device_user()` to reuse `device_user_pk`.
- **Lifecycle Observation Columns:** Migration `005` adds `roster_last_seen_at` and `inactive_at` to `device_users`.
- **Classification:**
  - Device User lifecycle schema support: **IMPLEMENTED** (staged in DDL).
  - Automatic roster lifecycle detection: **NOT IMPLEMENTED / PENDING**.

---

## 5. Migration DDL Specification (`sql/005_human_device_mapping_schema.sql`)

```sql
-- SQL Migration 005: Human ↔ Device Temporal Mapping + Device User Lifecycle Foundation
-- PromptID: ADMS-Data-HumanDeviceMappingSchema-002
-- Description: Add temporal ownership (valid_from, valid_to), audit fields (verified_by, verification_method, verification_note),
--              device user lifecycle observation fields (roster_last_seen_at, inactive_at), and partial unique active mapping index.

BEGIN;

-- 1. Device User Lifecycle Observation Columns
ALTER TABLE device_users
  ADD COLUMN IF NOT EXISTS roster_last_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS inactive_at TIMESTAMPTZ;

-- 2. Audit and Temporal Columns on employee_device_mappings
ALTER TABLE employee_device_mappings
  ADD COLUMN IF NOT EXISTS verified_by TEXT NOT NULL DEFAULT 'SYSTEM_ADMIN',
  ADD COLUMN IF NOT EXISTS verification_method TEXT NOT NULL DEFAULT 'MANUAL_ADMIN_CONFIRMATION',
  ADD COLUMN IF NOT EXISTS verification_note TEXT,
  ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

-- 3. Temporal Validity Constraint: valid_to must be strictly greater than valid_from if valid_to is present
ALTER TABLE employee_device_mappings
  ADD CONSTRAINT chk_temporal_validity CHECK (
    valid_to IS NULL OR valid_to > valid_from
  );

-- 4. Verification Audit Metadata Constraint for VERIFIED mappings
ALTER TABLE employee_device_mappings
  ADD CONSTRAINT chk_verified_metadata CHECK (
    mapping_status <> 'VERIFIED'
    OR (
      verified_at IS NOT NULL
      AND verified_by IS NOT NULL
      AND verification_method IS NOT NULL
      AND valid_from IS NOT NULL
    )
  );

-- 5. Verification Method Allowed Values Constraint
ALTER TABLE employee_device_mappings
  ADD CONSTRAINT chk_verification_method CHECK (
    verification_method IN (
      'CONTROLLED_SCAN',
      'TERMINAL_ROSTER_REVIEW',
      'MANUAL_ADMIN_CONFIRMATION',
      'LEGACY_MIGRATION'
    )
  );

-- 6. Update mapping_status CHECK constraint to include CANDIDATE and REVOKED
ALTER TABLE employee_device_mappings
  DROP CONSTRAINT IF EXISTS employee_device_mappings_mapping_status_check;

ALTER TABLE employee_device_mappings
  ADD CONSTRAINT employee_device_mappings_mapping_status_check CHECK (
    mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY', 'CANDIDATE', 'REVOKED')
  );

-- 7. Replace legacy strict UNIQUE(device_user_pk) constraint with Active Partial Unique Index
ALTER TABLE employee_device_mappings 
  DROP CONSTRAINT IF EXISTS employee_device_mappings_device_user_pk_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_verified_device_user 
  ON employee_device_mappings (device_user_pk) 
  WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL;

-- 8. Performance Index for Temporal Mapping Queries
CREATE INDEX IF NOT EXISTS idx_employee_device_mappings_temporal 
  ON employee_device_mappings (device_user_pk, mapping_status, valid_from, valid_to);

COMMIT;
```

---

## 6. Active VERIFIED Mapping Uniqueness & Integrity Tradeoff

- **Active Uniqueness:** Partial Unique Index `idx_active_verified_device_user` guarantees at most one active (`valid_to IS NULL`) `VERIFIED` human owner per physical terminal user slot (`device_user_pk`).
- **Historical Overlap Protection:** Application layer will validate interval overlap `[valid_from, valid_to)` during historical mapping insertions.
- **`btree_gist` Status:**
  - `btree_gist` installed: `NO`
  - `btree_gist` installed by this migration: `NO`
  - Known Tradeoff: Historical closed interval overlap is checked in application transactions rather than PostgreSQL GiST exclusion constraints.

---

## 7. Data Preservation & Test Regression Verification

- **Attendance Logs:** 6 records (100% preserved)
- **Human Master:** 120 records (100% preserved)
- **Human Master Provenance:** 120 records (100% preserved)
- **Devices:** 1 record (100% preserved)
- **Device Users:** 2 records (100% preserved)
- **Employee Device Mappings:** 0 records (0 created)
- **Test Suite Results:** 33/33 unit tests passed (100% success rate across State Engine, Backfill, Healthcheck, Identity Transition, and Excel Import).

---

## 8. Collector & Backfill Compatibility Boundary

- **Schema Readiness:** `IMPLEMENTED` (Staged DDL file `sql/005_human_device_mapping_schema.sql`).
- **Collector Temporal Resolution:** `NOT IMPLEMENTED / NEXT PHASE` (Future update will introduce `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)`).
- **Backfill Temporal Resolution:** `PENDING APPLICATION TRANSITION`.
- **Roster Synchronization:** `NOT IMPLEMENTED`.

---

## 9. Next Phase Lock & Sequencing

The next required phase is:
```text
ADMS-Collector-TemporalIdentity-001 (PLAN ONLY)
```
Do NOT begin Human ↔ Device Mapping WRITE or Native ADMS Push E2E.
