-- SQL Migration 004: Human Master Additive Schema & Provenance Linkage
-- PromptID: ADMS-Data-HumanMasterSchema-002
-- Description: Add structured branch and category fields to human_employees table and create human_employee_sources provenance linkage table.

-- Step 1: Add structured organizational columns to human_employees
ALTER TABLE human_employees 
  ADD COLUMN IF NOT EXISTS branch TEXT,
  ADD COLUMN IF NOT EXISTS category TEXT;

-- Step 2: Create source provenance tracking table
CREATE TABLE IF NOT EXISTS human_employee_sources (
  source_link_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES human_employees(employee_id) ON DELETE CASCADE,
  source_system TEXT NOT NULL DEFAULT 'EXCEL_HUMAN_MASTER',
  source_file TEXT NOT NULL,
  source_sheet TEXT NOT NULL,
  source_row INT NOT NULL,
  source_record_key TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_system, source_record_key)
);

CREATE INDEX IF NOT EXISTS human_employee_sources_employee_id_idx ON human_employee_sources(employee_id);
