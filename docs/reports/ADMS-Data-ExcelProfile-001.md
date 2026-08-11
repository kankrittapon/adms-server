# EXCEL EMPLOYEE DATA PROFILE REPORT

## Prompt

* PromptID: `ADMS-Data-ExcelProfile-001`
* mode: READ-ONLY DATA PROFILING + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:20:00+07:00
* target file: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx`
* modifications performed: NO (Documentation writes only)

## Workbook Inventory

- file: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx` (and `รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.csv`)
- title: `รายละเอียดกำลังพล พัน.สอล.กรม สน.สอ.รฝ. ณ ม.ค.69`
- sheet name: Sheet 1 (`รายละเอียด กพ.พัน.สอล.ฯ ก.พ.6`)
- total rows: 127 raw spreadsheet rows
- total parsed employees: 120 unique employee records
- duplicate raw names: 0 (100% unique names)
- blank/null name fields: 0

## Category Breakdown

| Category | Record Count | Rank Prefixes | Branch / Batch Field |
| -------- | ------------ | ------------- | -------------------- |
| `นายทหาร` (Commissioned Officers) | 20 records | `น.ท.`, `น.ต.`, `ว่าที่ น.ต.`, `ร.อ.`, `ร.ท.`, `ว่าที่ ร.ต.`, `พ.จ.อ.` | Branch (`นว.ก.`, `สส.`, `กง.`, `พธ.`, `สอ.รฝ.`) |
| `พันจ่า` (Chief Petty Officers) | 58 records | `พ.จ.อ.`, `พ.จ.ท.`, `พ.จ.ต.` | Branch (`สส.`, `อล.`, `อร.`, `กง.`, `พธ.`, `สอ.รฝ.`) |
| `จ่า` (Petty Officers) | 6 records | `จ.อ.` | Branch (`สส.`, `อล.`, `อร.`, `กง.`) |
| `พลทหาร` (Enlisted Conscripts) | 36 records | `พลฯ` | Rotation / Batch (`2/66`, `4/66`, `1/67`, `2/67`, `3/67`, `4/67`, `1/68`, `2/68`) |

## Database Schema Mapping

- target table: `employees` in PostgreSQL (`adms-postgres`)
- `user_id`: Mapped string `'1'` to `'120'` matching ZKTeco terminal user IDs
- `display_name`: Extracted full name without rank prefix (e.g. `'จตุภัทร ลิมปนารมณ์'`)
- `rank`: Extracted rank prefix (e.g. `'น.ท.'`, `'พ.จ.อ.'`, `'จ.อ.'`, `'พลฯ'`)
- `position`: Branch or Conscript rotation batch code (e.g. `'สส.'`, `'2/66'`)
- `notes`: Preserved remarks (e.g. `'Anti Drone พื้นที่ สอ.รฝ.'`, `'เรียน นพจ.'`)
- schema extension: `ALTER TABLE employees ADD COLUMN IF NOT EXISTS notes TEXT;`

## Import Policy & Safety

- conflict policy: `ON CONFLICT (user_id) DO UPDATE SET display_name = EXCLUDED.display_name, rank = EXCLUDED.rank, position = EXCLUDED.position, notes = EXCLUDED.notes, updated_at = NOW()`
- original workbook preserved: YES (Workbook remains untouched)
- database modified: NO (Import plan only)

## Documentation

- spec created: YES ([EXCEL_EMPLOYEE_PROFILE.md](file:///d:/Dev/adms-server/docs/EXCEL_EMPLOYEE_PROFILE.md))
- report persisted: YES ([ADMS-Data-ExcelProfile-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Data-ExcelProfile-001.md))
- reports index updated: YES ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
- code modified: NO
- schema modified: NO
- database modified: NO

## Proposed Next PromptIDs

1. `# PromptID: ADMS-Data-ExcelImport-002` (WRITE Mode): Implement `scripts/import_excel_employees.py` import script and safely populate PostgreSQL `employees` table.

## FINAL

- excel profiling complete: YES
- total records verified: YES (120 unique records)
- schema mapping approved: YES
- idempotent import policy defined: YES
- safe to proceed to import script implementation: YES
- blockers: NONE

STOP.
