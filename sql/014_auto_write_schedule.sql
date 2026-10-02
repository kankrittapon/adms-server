-- PRM-ADMS-004: Automated Business Hours Write Window
-- System configuration persistence + synthetic scheduler operator
BEGIN;

-- Generic K/V for system toggles
CREATE TABLE IF NOT EXISTS system_configurations (
  key         TEXT PRIMARY KEY,
  value       JSONB NOT NULL,
  updated_by  BIGINT REFERENCES operators(operator_id),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed auto_write_schedule with enabled=false (safe rollout, per confirmation)
INSERT INTO system_configurations (key, value, updated_by)
VALUES (
  'auto_write_schedule',
  '{"enabled": false, "days": "1-5", "start_time": "09:00", "end_time": "18:00", "timezone": "Asia/Bangkok"}'::jsonb,
  (SELECT operator_id FROM operators WHERE role='ADMIN' ORDER BY operator_id LIMIT 1)
)
ON CONFLICT (key) DO NOTHING;

-- Synthetic actor for scheduler (ADMIN, active=false so login disabled, filtered from UI)
-- Use fixed password_hash '!' (never valid) and display_name
INSERT INTO operators (username, display_name, role, password_hash, active)
VALUES ('SYSTEM_SCHEDULER', 'System Scheduler', 'ADMIN', '!', false)
ON CONFLICT (username) DO NOTHING;

COMMENT ON TABLE system_configurations IS 'PRM-ADMS-004: system toggles; auto_write_schedule {enabled, days, start_time, end_time, timezone}';
COMMENT ON COLUMN system_configurations.value IS 'JSONB: enabled bool, days "1-5", start_time "HH:MM", end_time "HH:MM", timezone Asia/Bangkok';

COMMIT;
