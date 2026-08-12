-- SQL Migration 007: Plothan Production Scope Exclusion
-- PromptID: ADMS-Data-PlothanProductionExclusion-001
-- Description: Additive, reversible production-scope flag for human_employees.
--              Owner policy: พลทหาร (enlisted conscripts) are EXCLUDED from the
--              production Human Master / enrollment population.
--
--              Safety:
--                - NO row deletion. UUIDs, provenance (human_employee_sources),
--                  attendance, and mapping evidence are all preserved.
--                - The column default keeps every existing/future record
--                  production-scope eligible unless deterministically flipped.
--                - Reversible: the data flip can be rolled back with
--                  UPDATE human_employees SET production_scope = true
--                  WHERE category = 'พลทหาร';
--                - Idempotent: re-running matches 0 rows for the flip.

BEGIN;

ALTER TABLE human_employees
  ADD COLUMN IF NOT EXISTS production_scope BOOLEAN NOT NULL DEFAULT true;

COMMENT ON COLUMN human_employees.production_scope IS
  'True = eligible for the production enrollment scope. '
  'False = excluded (e.g. พลทหาร). Reversible state; never deletes.';

-- Deterministic exclusion of the current พลทหาร population (36 records).
UPDATE human_employees
  SET production_scope = false
  WHERE production_scope = true
    AND (
      rank IN ('พลฯ', 'พลทหาร', 'พลทหารกองประจำการ', 'พล.ทหาร')
      OR category = 'พลทหาร'
    );

COMMIT;
