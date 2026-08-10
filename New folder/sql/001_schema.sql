CREATE TABLE IF NOT EXISTS devices (
  id BIGSERIAL PRIMARY KEY,
  device_name TEXT NOT NULL,
  device_ip INET NOT NULL UNIQUE,
  device_port INTEGER NOT NULL DEFAULT 4370,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employees (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  rank TEXT,
  position TEXT,
  military_id TEXT,
  national_id_masked TEXT,
  date_of_birth DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attendance_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES employees(user_id),
  device_ip INET NOT NULL,
  scan_time TIMESTAMPTZ NOT NULL,
  punch_type TEXT,
  status TEXT NOT NULL CHECK (status IN ('ON_TIME', 'LATE', 'UNKNOWN')),
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, device_ip, scan_time)
);

CREATE INDEX IF NOT EXISTS attendance_logs_scan_time_idx ON attendance_logs (scan_time DESC);
CREATE INDEX IF NOT EXISTS attendance_logs_user_scan_time_idx ON attendance_logs (user_id, scan_time DESC);

CREATE TABLE IF NOT EXISTS sync_events (
  id BIGSERIAL PRIMARY KEY,
  device_ip INET,
  event_type TEXT NOT NULL,
  message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
