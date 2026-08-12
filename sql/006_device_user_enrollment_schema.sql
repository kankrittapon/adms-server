-- SQL Migration 006: Controlled Device Enrollment Infrastructure
-- PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002
-- Description: Additive reservation/enrollment state storage for the controlled
--              production enrollment workflow (ID allocation, reservation,
--              terminal account creation state, fingerprint/scan evidence).
--
--              Does NOT create mappings. employee_device_mappings remains the
--              sole authoritative source of VERIFIED Human<->Device ownership
--              and is NOT modified by enrollment infrastructure.
--              No biometric template data is stored.

BEGIN;

CREATE TABLE IF NOT EXISTS device_user_enrollments (
  enrollment_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES human_employees(employee_id),
  device_id BIGINT NOT NULL REFERENCES devices(device_id),
  reserved_device_user_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'RESERVED'
    CHECK (status IN (
      'RESERVED',
      'TERMINAL_ACCOUNT_CREATED',
      'FINGERPRINT_ENROLLMENT_PENDING',
      'FINGERPRINT_ENROLLED',
      'CONTROLLED_SCAN_PENDING',
      'CONTROLLED_SCAN_CONFIRMED',
      'READY_FOR_MAPPING',
      'CANCELLED',
      'RETIRED'
    )),
  reserved_by TEXT NOT NULL,
  reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  terminal_created_at TIMESTAMPTZ,
  device_uid INT,
  fingerprint_confirmed_at TIMESTAMPTZ,
  controlled_scan_window_until TIMESTAMPTZ,
  controlled_scan_time TIMESTAMPTZ,
  confirmed_by TEXT,
  confirmed_at TIMESTAMPTZ,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- A terminal ID can never be reserved by two enrollments on the same device,
  -- and is never immediately recyclable (CANCELLED/RETIRED rows keep the ID).
  CONSTRAINT uq_enrollment_terminal_id UNIQUE (device_id, reserved_device_user_id)

  -- Evidence constraints: confirmation states require their timestamps.
  CONSTRAINT chk_scan_confirmed_has_time CHECK (
    status <> 'CONTROLLED_SCAN_CONFIRMED' OR controlled_scan_time IS NOT NULL
  ),
  CONSTRAINT chk_ready_has_scan_time CHECK (
    status <> 'READY_FOR_MAPPING' OR controlled_scan_time IS NOT NULL
  ),
  CONSTRAINT chk_ready_has_confirmed_by CHECK (
    status <> 'READY_FOR_MAPPING' OR confirmed_by IS NOT NULL
  ),
  CONSTRAINT chk_cancelled_has_notes CHECK (
    status <> 'CANCELLED' OR notes IS NOT NULL
  )
);

CREATE INDEX IF NOT EXISTS idx_enrollments_device_status
  ON device_user_enrollments (device_id, status);
CREATE INDEX IF NOT EXISTS idx_enrollments_employee_status
  ON device_user_enrollments (employee_id, status);
CREATE INDEX IF NOT EXISTS idx_enrollments_terminal_id
  ON device_user_enrollments (device_id, reserved_device_user_id);

-- A Human may have at most ONE active enrollment per device.
-- (Partial unique index; equivalent WHERE-clause table constraints are not
-- reliably supported across PostgreSQL versions.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_enrollment_per_human_device
  ON device_user_enrollments (employee_id, device_id)
  WHERE status IN (
    'RESERVED',
    'TERMINAL_ACCOUNT_CREATED',
    'FINGERPRINT_ENROLLMENT_PENDING',
    'FINGERPRINT_ENROLLED',
    'CONTROLLED_SCAN_PENDING',
    'CONTROLLED_SCAN_CONFIRMED',
    'READY_FOR_MAPPING'
  );

COMMIT;
