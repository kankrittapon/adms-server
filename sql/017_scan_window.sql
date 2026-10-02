-- SQL Migration 017: attendance scan window
-- Attendance scans count only between 06:30 and 11:00 local time (first scan
-- after 10:00 inside the window = late). Scans outside the window are still
-- stored but never make anyone present. The scanner stays usable all day for
-- fingerprint enrollment.
UPDATE system_configurations
SET value = value || '{"scan_window_start": "06:30", "scan_window_end": "11:00"}'::jsonb
WHERE key = 'attendance_policy';
