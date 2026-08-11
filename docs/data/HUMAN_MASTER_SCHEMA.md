# ADMS Human Master Schema & Provenance Architecture

## Document Status

* **Status**: Approved Human Master Schema Architecture Specification
* **Source PromptIDs**: `ADMS-Data-HumanMasterSchema-001`
* **Target Environment**: ADMS Server PostgreSQL Database Schema (`human_employees`)
* **Prerequisite**: Stage 2 Post-Identity Checkpoint (`ADMS-Checkpoint-PostIdentityTransition-001`)

---

## 1. Executive Summary & Identity Principles

1. **Immutable Canonical Human Identity**:
   Canonical identity for human personnel is strictly **`employee_id UUID`** (auto-generated via `gen_random_uuid()`).
2. **Rejection of Name-Based Identity**:
   `display_name` does **NOT** have a unique constraint in `human_employees`. Using `ON CONFLICT (display_name)` is both **invalid PostgreSQL SQL** and **semantically unsafe** (names are mutable and non-unique).
3. **Decoupling of Provenance from Identity**:
   Excel row positions, sheet titles, and source content hashes are **import provenance metadata**, NOT canonical human identifiers.
4. **Structured Attribute Preservation**:
   Branch (`เหล่า`), Category (`นายทหาร`, `พันจ่า`, `จ่า`, `พลทหาร`), and Rank (`ยศ`) must be preserved in structured database columns rather than concatenated string blobs.

---

## 2. Proposed Additive SQL Migration Specification (`sql/004_human_master_schema.sql`)

> [!NOTE]
> This DDL is provided for architecture review only. **Do NOT execute SQL until Stage 2 execution (`ADMS-Data-HumanMasterSchema-002`)**.

```sql
-- SQL Migration 004: Human Master Additive Schema & Provenance Linkage
-- PromptID: ADMS-Data-HumanMasterSchema-001 / 002
-- Description: Add structured branch/category fields to human_employees and create human_employee_sources table

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
```

---

## 3. Provenance & Re-Import Reconciliation Contract

```text
Excel Source Workbook Row
          |
          v
Calculate Deterministic source_record_key
(e.g., EXCEL_FEB69_CAT_ROW_004)
          |
          +----> Matches human_employee_sources(source_system, source_record_key)?
          |              |
          |              +-- YES --> UPDATE human_employees attributes & source_hash
          |              |
          |              +-- NO  --> INSERT new human_employees UUID & source record link
          v
Audit Trail & Source Linkage Complete
```

---

## 4. Staged Execution Plan

1. **`ADMS-Data-HumanMasterSchema-001` (Plan ONLY)**: Architecture design & provenance model $\to$ **COMPLETE**.
2. **`ADMS-Data-HumanMasterSchema-002` (WRITE Mode)**: Apply `sql/004_human_master_schema.sql` additive schema migration.
3. **`ADMS-Data-ExcelImport-002` (WRITE Mode)**: Execute dry-run import script `app/import_excel_human_master.py` to populate 120 `human_employees` and `human_employee_sources` records cleanly.
