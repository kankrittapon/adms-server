-- SQL Migration 011: Add English Name to Human Master
-- PromptID: ADMS-Frontend-I18n-RBAC-Personnel-004
-- Description: Add nullable english_name column to human_employees table.

BEGIN;

ALTER TABLE human_employees
  ADD COLUMN IF NOT EXISTS english_name TEXT;

COMMIT;
