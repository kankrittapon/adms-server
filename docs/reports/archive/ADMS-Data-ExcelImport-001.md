# EXCEL HUMAN MASTER IMPORT — DRY-RUN DESIGN & PLAN REPORT

## Prompt

* PromptID: `ADMS-Data-ExcelImport-001`
* mode: READ-ONLY DATA ANALYSIS + PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T11:46:00+07:00
* database modified: NO
* application modified: NO
* device modified: NO

## Pre-Flight Git Baseline

- branch: `main`
- HEAD: `4eae292cefd439496762f4057ec062cc587dde83`
- working tree: CLEAN (`nothing to commit, working tree clean`)
- latest commit: `docs: establish post identity transition checkpoint (# PromptID: ADMS-Checkpoint-PostIdentityTransition-001)`

## Dataset Profiling Summary

- source workbook: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx`
- active sheet: `ยอด ม.ค.69`
- title header: `รายละเอียดกำลังพล พัน.สอล.กรม สน.สอ.รฝ. ณ ม.ค.69`
- column headers: `ที่`, `ยศ-ชื่อ-สกุล`, `เหล่า`, `หมายเหตุ`
- total clean records: **120 personnel**
- duplicate display names: **0 (ZERO)**

### Category Breakdown

- `นายทหาร` (Commissioned Officers): 20 personnel
- `พันจ่า` (Chief Petty Officers): 58 personnel
- `จ่า` (Petty Officers): 6 personnel
- `พลทหาร` (Privates / Enlisted): 36 personnel
- total: 120 personnel

## Mandatory Safety Boundary Enforcement

- Excel row number == ZKTeco user_id: **REJECTED / UNSUPPORTED**
- automatic human-device mapping: **PROHIBITED**
- terminal user creation from Excel: **PROHIBITED**
- fingerprint template modification: **PROHIBITED**
- terminal configuration writes: **PROHIBITED**
- target table: `human_employees` **ONLY**
- unmapped attendance handling: Supported cleanly (`employee_id = NULL`)

## Schema Mapping Contract

- `employee_id`: Auto-generated UUID (`gen_random_uuid()`)
- `personnel_id`: `NULL`
- `display_name`: Extracted clean name (e.g. `จตุภัทร ลิมปนารมณ์`)
- `rank`: Extracted rank prefix (e.g. `น.ท.`, `พ.จ.อ.`, `จ.อ.`, `พลฯ`)
- `position`: Category title (e.g. `นายทหาร`, `พันจ่า`, `จ่า`, `พลทหาร`)
- `notes`: Metadata string (e.g. `เหล่า: สส. | หมายเหตุ: ป่วย`)

## Dry-Run & Import Execution Design

- dry-run script: `app/import_excel_human_master.py` (To be implemented in Stage 2)
- normalization logic: Regex-based rank parsing + category header tracking + string trimming.
- idempotency: `ON CONFLICT (display_name)` or unique constraint handling.
- pre-import backup: `adms_post_identity_20260811_113944.dump` verified.

## Proposed WRITE PromptID

- `# PromptID: ADMS-Data-ExcelImport-002` (WRITE Mode: Import 120 records into `human_employees`)
- ready: YES
- blockers: NONE

## FINAL

- Excel master dataset profiled: YES (120 records verified across 4 categories)
- zero duplicate names confirmed: YES
- Excel row number -> ZKTeco user_id assumption rejected: YES
- safety boundary enforced: YES (`human_employees` target ONLY)
- database modified: NO
- application modified: NO
- device modified: NO
- safe to proceed to Excel import execution: YES
- blockers: NONE

STOP.
