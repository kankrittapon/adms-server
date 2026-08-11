-- SQL Migration 002: Identity Foundation
-- PromptID: ADMS-Data-IdentitySchema-002
-- Description: Additive migration separating Human Master Data (human_employees) and Device Identities (device_users)

-- Require UUID extension if available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Devices Registry Table
CREATE TABLE IF NOT EXISTS devices (
  device_id BIGSERIAL PRIMARY KEY,
  serial_number TEXT NOT NULL UNIQUE,
  device_name TEXT NOT NULL,
  device_ip INET NOT NULL,
  platform TEXT NOT NULL DEFAULT 'ZEM560_TFT',
  firmware_version TEXT,
  active BOOLEAN NOT NULL DEFAULT true,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Device-Local Users Registry Table
CREATE TABLE IF NOT EXISTS device_users (
  device_user_pk BIGSERIAL PRIMARY KEY,
  device_id BIGINT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
  device_user_id TEXT NOT NULL,
  device_uid INT,
  device_display_name TEXT,
  privilege INT NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT true,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (device_id, device_user_id)
);

-- 3. Human Master Data Table
CREATE TABLE IF NOT EXISTS human_employees (
  employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  personnel_id TEXT UNIQUE,
  display_name TEXT NOT NULL,
  rank TEXT,
  position TEXT,
  notes TEXT,
  active BOOLEAN NOT NULL DEFAULT true,
  source TEXT NOT NULL DEFAULT 'EXCEL_IMPORT',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Employee <-> Device User Mappings Table
CREATE TABLE IF NOT EXISTS employee_device_mappings (
  mapping_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES human_employees(employee_id) ON DELETE CASCADE,
  device_user_pk BIGINT NOT NULL REFERENCES device_users(device_user_pk) ON DELETE CASCADE UNIQUE,
  mapping_status TEXT NOT NULL CHECK (mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY')),
  mapping_source TEXT NOT NULL DEFAULT 'ADMIN_MANUAL',
  verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Additive Columns on attendance_logs
ALTER TABLE attendance_logs 
  ADD COLUMN IF NOT EXISTS device_id BIGINT REFERENCES devices(device_id),
  ADD COLUMN IF NOT EXISTS device_user_pk BIGINT REFERENCES device_users(device_user_pk),
  ADD COLUMN IF NOT EXISTS employee_id UUID REFERENCES human_employees(employee_id);

-- 6. Performance Indices
CREATE INDEX IF NOT EXISTS idx_attendance_logs_device_user_pk ON attendance_logs(device_user_pk);
CREATE INDEX IF NOT EXISTS idx_attendance_logs_employee_id ON attendance_logs(employee_id);
CREATE INDEX IF NOT EXISTS idx_device_users_device_id_user_id ON device_users(device_id, device_user_id);

-- 7. Seed Physical Terminal Registration
INSERT INTO devices (serial_number, device_name, device_ip, platform, firmware_version)
VALUES ('3392113170057', 'SONIC ZEM560 #1', '192.168.1.201', 'ZEM560_TFT', 'Ver 6.60 Aug 26 2011')
ON CONFLICT (serial_number) DO UPDATE SET device_ip = EXCLUDED.device_ip;
