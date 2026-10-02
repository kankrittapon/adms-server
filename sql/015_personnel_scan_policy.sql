-- SQL Migration 015: Personnel scan policy (scan-exempt personnel)
-- Some personnel (commander's office, finance) are not required to scan in/out.
-- Exempt people are excluded from "needs fingerprint enrollment" lists and,
-- later, from absence computation. Purely additive; defaults keep every
-- existing person scan-required.
BEGIN;

ALTER TABLE human_employees
  ADD COLUMN IF NOT EXISTS scan_exempt BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS scan_exempt_reason TEXT;

COMMENT ON COLUMN human_employees.scan_exempt IS
  'true = not required to scan in/out (e.g. commander office, finance); excluded from enrollment-needed and absence computation';
COMMENT ON COLUMN human_employees.scan_exempt_reason IS 'why this person is scan-exempt (required when scan_exempt=true)';

COMMIT;
