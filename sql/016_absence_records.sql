-- SQL Migration 016: Absence records (leave / official duty / secondment)
-- Record-only: leave is signed off on paper by the battalion commander
-- before it is entered, so there is no approval workflow. A recorded
-- absence means "not expected to scan on these days".
BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS absence_types (
  code               TEXT PRIMARY KEY,
  name_th            TEXT NOT NULL,
  name_en            TEXT NOT NULL,
  counts_as          TEXT NOT NULL CHECK (counts_as IN ('LEAVE', 'DUTY')),
  requires_order_ref BOOLEAN NOT NULL DEFAULT false,
  sort_order         INT NOT NULL DEFAULT 100,
  active             BOOLEAN NOT NULL DEFAULT true
);

INSERT INTO absence_types (code, name_th, name_en, counts_as, requires_order_ref, sort_order) VALUES
  ('SICK',          'ลาป่วย',          'Sick leave',       'LEAVE', false, 10),
  ('PERSONAL',      'ลากิจ',           'Personal leave',   'LEAVE', false, 20),
  ('VACATION',      'ลาพักผ่อน',        'Vacation',         'LEAVE', false, 30),
  ('MATERNITY',     'ลาคลอดบุตร',       'Maternity leave',  'LEAVE', false, 40),
  ('ORDINATION',    'ลาอุปสมบท',        'Ordination leave', 'LEAVE', false, 50),
  ('OFFICIAL_DUTY', 'ไปราชการ',        'Official duty',    'DUTY',  true,  60),
  ('SECONDMENT',    'ไปช่วยราชการ',     'Secondment',       'DUTY',  true,  70),
  ('TRAINING',      'ไปศึกษา / อบรม',   'Training',         'DUTY',  true,  80)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS absence_records (
  absence_id     BIGSERIAL PRIMARY KEY,
  employee_id    UUID NOT NULL REFERENCES human_employees(employee_id),
  type_code      TEXT NOT NULL REFERENCES absence_types(code),
  start_date     DATE NOT NULL,
  end_date       DATE NOT NULL,
  order_ref      TEXT,
  destination    TEXT,
  note           TEXT,
  status         TEXT NOT NULL DEFAULT 'RECORDED' CHECK (status IN ('RECORDED', 'CANCELLED')),
  recorded_by    TEXT NOT NULL,
  recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  cancelled_by   TEXT,
  cancelled_at   TIMESTAMPTZ,
  cancel_reason  TEXT,
  CONSTRAINT absence_records_date_order CHECK (end_date >= start_date),
  -- One person cannot have two recorded absences covering the same day.
  CONSTRAINT absence_records_no_overlap EXCLUDE USING gist (
    employee_id WITH =,
    daterange(start_date, end_date, '[]') WITH &&
  ) WHERE (status = 'RECORDED')
);

CREATE INDEX IF NOT EXISTS absence_records_dates_idx ON absence_records (start_date, end_date) WHERE status = 'RECORDED';
CREATE INDEX IF NOT EXISTS absence_records_employee_idx ON absence_records (employee_id);

CREATE TABLE IF NOT EXISTS holidays (
  holiday_date DATE PRIMARY KEY,
  name_th      TEXT NOT NULL,
  created_by   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Late threshold for the daily roster (first scan after this = LATE).
INSERT INTO system_configurations (key, value)
VALUES ('attendance_policy', '{"late_after": "10:00", "timezone": "Asia/Bangkok", "workdays": [1,2,3,4,5]}'::jsonb)
ON CONFLICT (key) DO NOTHING;

COMMIT;
