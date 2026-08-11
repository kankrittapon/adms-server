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
