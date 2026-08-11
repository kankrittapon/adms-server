# Canonical Architecture: Human ↔ Device Identity Mapping Schema Design

**PromptID:** `ADMS-Data-HumanDeviceMappingSchema-001`  
**Status:** ARCHITECTURE DESIGN COMPLETE / PLAN ONLY  

---

## 1. Executive Summary & Problem Statement

The **ADMS Identity Mapping Architecture** enforces a strict separation between **Human Master Data** (`human_employees.employee_id` UUID) and **Device-Local Identity** (`device_users(device_id, device_user_id)`).

Following the analysis in `ADMS-Data-HumanDeviceMapping-001`, the baseline mapping table `employee_device_mappings` created during `002_identity_foundation.sql` exhibits four **Critical Schema Gaps**:

1. **Lack of Auditability (`verified_by`, `verification_method`, `verification_note`):** Cannot prove *who* verified a mapping, *how* it was verified, or *why* it was established.
2. **Lack of Temporal Boundaries (`valid_from`, `valid_to`):** Cannot represent temporal ownership. If a physical terminal `user_id` is deleted and reassigned to another employee on the terminal LCD in the future, a timeless mapping will corrupt historical attendance attribution.
3. **Inflexible Active Uniqueness (`employee_device_mappings_device_user_pk_key`):** The existing `device_user_pk UNIQUE` constraint prohibits keeping historical mapping rows when a device user account is reassigned over time.
4. **Missing Status Semantics (`CANDIDATE`, `REVOKED`):** Needs explicit differentiation between active verified mappings, legacy mappings, and candidate suggestions.

This document specifies the DDL migration plan (`sql/005_human_device_mapping_schema.sql`) to resolve all critical schema gaps cleanly without altering raw attendance data or breaking existing runtime ingestion.

---

## 2. Fundamental Identity & Security Boundaries

```text
+---------------------------------------+
| HUMAN MASTER DOMAIN                   |
| Table: human_employees                |
| Canonical Key: employee_id (UUID)     |
| Attributes: display_name, rank, etc.  |
+---------------------------------------+
                   ▲
                   |  (Explicit Temporal Mapping)
                   |  Table: employee_device_mappings
                   |  [valid_from, valid_to)
                   ▼
+---------------------------------------+
| DEVICE IDENTITY DOMAIN                |
| Table: device_users                   |
| Canonical Key: (device_id, user_id)   |
| Local Keys: device_user_id, device_uid|
+---------------------------------------+
                   ▲
                   |  (Terminal Flash Ownership)
                   ▼
+---------------------------------------+
| BIOMETRIC TEMPLATE DOMAIN             |
| Owned exclusively by terminal flash   |
| NOT stored/downloaded in PostgreSQL   |
+---------------------------------------+
```

### Core Invariants
1. **Human Canonical Key:** `human_employees.employee_id` UUID.
2. **Device User Canonical Key:** `(device_id, device_user_id)` represented by `device_user_pk`.
3. **Excel Row Rule:** `Excel row number == ZKTeco user_id` is **STRICTLY PROHIBITED**.
4. **No Auto-Mapping:** No mapping row may be created automatically by Collector, Excel import, or name matching.
5. **No Biometric Storage:** Biometric templates remain on physical terminal flash. ADMS does not download or store template bytes.

---

## 3. Temporal Ownership & History Preservation Model

### Half-Open Interval Semantics: `[valid_from, valid_to)`
- `valid_from TIMESTAMPTZ NOT NULL DEFAULT now()`: The timestamp from which this mapping becomes valid.
- `valid_to TIMESTAMPTZ NULL`: The timestamp when this mapping expires. `NULL` indicates an currently active mapping.
- **Match Criteria:** An attendance punch at `scan_time` matches a mapping if and only if:
  $$\text{scan\_time} \ge \text{valid\_from} \quad \text{AND} \quad (\text{valid\_to IS NULL} \;\lor\; \text{scan\_time} < \text{valid\_to})$$

### Mapping History Preservation
Overwriting mapping records (changing `employee_id` on an existing row) is **PROHIBITED**.

When `device_user_pk = 1` is reassigned from **Human A** to **Human B** at timestamp $T_{\text{reassign}}$:
1. **Close Active Mapping:** Update Human A's mapping setting `valid_to = T_reassign`.
2. **Open New Mapping:** Insert new row for Human B with `valid_from = T_reassign` and `valid_to = NULL`.

---

## 4. Verification Audit Model

To ensure full auditability for compliance and troubleshooting, every mapping record MUST capture:

- `verified_at TIMESTAMPTZ NOT NULL DEFAULT now()`: Timestamp when verification occurred.
- `verified_by TEXT NOT NULL DEFAULT 'SYSTEM_ADMIN'`: Username, operator ID, or console role.
- `verification_method TEXT NOT NULL CHECK (...)`: Allowed values:
  - `'CONTROLLED_SCAN'`: Verified via observed real-time test punch.
  - `'TERMINAL_ROSTER_REVIEW'`: Verified by operator review of LCD roster.
  - `'MANUAL_ADMIN_CONFIRMATION'`: Explicit manual admin assignment.
  - `'LEGACY_MIGRATION'`: Initial baseline migration.
- `verification_note TEXT NULL`: Optional non-sensitive justification text.

---

## 5. Constraint & Uniqueness Design

### Replacing Legacy Constraint
The existing migration `002_identity_foundation.sql` created:
`ALTER TABLE employee_device_mappings ADD CONSTRAINT employee_device_mappings_device_user_pk_key UNIQUE (device_user_pk);`

This strict `UNIQUE` constraint prevents historical rows for the same `device_user_pk`. 

### New Partial Unique Index (Active Mapping Uniqueness)
To allow historical rows while strictly preventing multiple simultaneously active `VERIFIED` owners:

```sql
-- Drop legacy strict UNIQUE constraint
ALTER TABLE employee_device_mappings 
  DROP CONSTRAINT IF EXISTS employee_device_mappings_device_user_pk_key;

-- Create Partial Unique Index for Active VERIFIED mappings
CREATE UNIQUE INDEX idx_active_verified_device_user 
  ON employee_device_mappings (device_user_pk) 
  WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL;
```

### Overlapping Historical Protection Policy
For historical time ranges, application transactions MUST enforce:
- $T_{\text{valid\_from}} < T_{\text{valid\_to}}$
- Non-overlapping intervals for the same `device_user_pk`.
- *Note on `btree_gist`:* PostgreSQL exclusion constraints using `tstzrange` require the `btree_gist` extension. To maintain zero-dependency operational simplicity on basic PostgreSQL containers, active uniqueness is enforced via PostgreSQL Partial Unique Index, while interval overlap validation is handled cleanly within database access transactions (`app/db.py`).

---

## 6. Attendance Resolution Semantics

### Ingestion & Query Logic
When resolving `employee_id` for an attendance punch `(device_user_pk, scan_time)`:

```sql
SELECT employee_id 
FROM employee_device_mappings 
WHERE device_user_pk = %s 
  AND mapping_status = 'VERIFIED'
  AND valid_from <= %s 
  AND (valid_to IS NULL OR valid_to > %s);
```

- **Exactly 1 match:** `employee_id` populated with Human UUID.
- **0 matches:** `employee_id = NULL` (Unmapped attendance persisted cleanly).
- **> 1 matches:** Data integrity violation raised (prevented by transaction logic).

---

## 7. Migration Plan Specification (`sql/005_human_device_mapping_schema.sql`)

```sql
-- SQL Migration 005: Human ↔ Device Mapping Schema Enhancement
-- PromptID: ADMS-Data-HumanDeviceMappingSchema-002
-- Description: Add temporal ownership (valid_from, valid_to), audit fields (verified_by, verification_method, verification_note), 
--              and update active mapping uniqueness constraints.

BEGIN;

-- 1. Add audit and temporal columns to employee_device_mappings
ALTER TABLE employee_device_mappings
  ADD COLUMN IF NOT EXISTS verified_by TEXT NOT NULL DEFAULT 'SYSTEM_ADMIN',
  ADD COLUMN IF NOT EXISTS verification_method TEXT NOT NULL DEFAULT 'MANUAL_ADMIN_CONFIRMATION',
  ADD COLUMN IF NOT EXISTS verification_note TEXT,
  ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

-- 2. Add CHECK constraint for verification_method
ALTER TABLE employee_device_mappings
  ADD CONSTRAINT chk_verification_method CHECK (
    verification_method IN (
      'CONTROLLED_SCAN',
      'TERMINAL_ROSTER_REVIEW',
      'MANUAL_ADMIN_CONFIRMATION',
      'LEGACY_MIGRATION'
    )
  );

-- 3. Update mapping_status CHECK constraint to include CANDIDATE and REVOKED
ALTER TABLE employee_device_mappings
  DROP CONSTRAINT IF EXISTS employee_device_mappings_mapping_status_check;

ALTER TABLE employee_device_mappings
  ADD CONSTRAINT employee_device_mappings_mapping_status_check CHECK (
    mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY', 'CANDIDATE', 'REVOKED')
  );

-- 4. Replace legacy strict UNIQUE(device_user_pk) constraint with Partial Unique Index
ALTER TABLE employee_device_mappings 
  DROP CONSTRAINT IF EXISTS employee_device_mappings_device_user_pk_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_verified_device_user 
  ON employee_device_mappings (device_user_pk) 
  WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL;

-- 5. Performance Index for Temporal Lookup
CREATE INDEX IF NOT EXISTS idx_employee_device_mappings_temporal 
  ON employee_device_mappings (device_user_pk, mapping_status, valid_from, valid_to);

COMMIT;
```

---

## 8. Rollback Plan

If rollback of Migration 005 is required:

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

## 9. Next Phase Readiness

Upon user authorization of `ADMS-Data-HumanDeviceMappingSchema-002`:
1. Generate PostgreSQL custom-format backup `adms_pre_schema005_<timestamp>.dump`.
2. Apply `sql/005_human_device_mapping_schema.sql`.
3. Verify test suite (including temporal lookup and active uniqueness assertions).
4. Update `app/db.py` signature: `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)`.
