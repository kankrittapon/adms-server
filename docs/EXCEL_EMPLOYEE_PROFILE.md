# ADMS Employee Master Data & Excel Import Specification

## Document Status

* **Status**: Approved Master Data Normalization & Import Spec
* **Source PromptID**: `ADMS-Data-ExcelProfile-001`
* **Target Workbook**: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx` (and `รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.csv`)
* **Target Database Table**: `employees` in PostgreSQL (`adms-postgres`)

---

## 1. Source Workbook Profile

* **File Location**: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx`
* **Title Header**: `รายละเอียดกำลังพล พัน.สอล.กรม สน.สอ.รฝ. ณ ม.ค.69`
* **Total Parsed Employee Records**: 120 unique personnel rows
* **Duplicate Names**: 0 (100% unique names)
* **Missing Identifiers**: 0 (All 120 rows contain valid names)

---

## 2. Category & Rank Breakdown

| Category Index | Category Name (`หมวด`) | Record Count | Rank Prefixes Observed | Branch / Batch Field (`เหล่า/ผลัด`) |
| -------------- | ---------------------- | ------------ | ---------------------- | ----------------------------------- |
| **Category 1** | `นายทหาร` (Commissioned Officers) | 20 records | `น.ท.`, `น.ต.`, `ว่าที่ น.ต.`, `ร.อ.`, `ร.ท.`, `ว่าที่ ร.ต.`, `พ.จ.อ.` | Branch (`นว.ก.`, `สส.`, `กง.`, `พธ.`, `สอ.รฝ.`) |
| **Category 2** | `พันจ่า` (Chief Petty Officers) | 58 records | `พ.จ.อ.`, `พ.จ.ท.`, `พ.จ.ต.` | Branch (`สส.`, `อล.`, `อร.`, `กง.`, `พธ.`, `สอ.รฝ.`) |
| **Category 3** | `จ่า` (Petty Officers) | 6 records | `จ.อ.` | Branch (`สส.`, `อล.`, `อร.`, `กง.`) |
| **Category 4** | `พลทหาร` (Enlisted Conscripts) | 36 records | `พลฯ` | Rotation / Batch (`2/66`, `4/66`, `1/67`, `2/67`, `3/67`, `4/67`, `1/68`, `2/68`) |

---

## 3. Database Schema Mapping Plan

To accommodate all business metadata from the Excel spreadsheet without overloading device-specific fields, the `employees` table schema in `sql/001_schema.sql` will be safely extended:

```sql
ALTER TABLE employees ADD COLUMN IF NOT EXISTS notes TEXT;
```

### Field Mapping Specification:

| Excel Source Column | Schema Column | Data Type | Parsing & Normalization Rule | Example Input -> Output |
| ------------------- | ------------- | --------- | ---------------------------- | ----------------------- |
| *(Derived)* | `user_id` | `TEXT` (NOT NULL, UNIQUE) | Mapped ZKTeco terminal user ID string (e.g. `'1'`, `'2'`, ... `'120'`). | Row #1 -> `'1'` |
| `ยศ-ชื่อ-สกุล` | `display_name` | `TEXT` (NOT NULL) | First Name + Last Name without rank prefix. | `'น.ท.จตุภัทร ลิมปนารมณ์'` -> `'จตุภัทร ลิมปนารมณ์'` |
| `ยศ-ชื่อ-สกุล` | `rank` | `TEXT` | Extracted Thai rank prefix string. | `'น.ท.จตุภัทร ลิมปนารมณ์'` -> `'น.ท.'` |
| `เหล่า` / `ผลัด` | `position` | `TEXT` | Military branch abbreviation or conscript rotation batch code. | `'สส.'` -> `'สส.'`, `'2/66'` -> `'2/66'` |
| `หมายเหตุ` | `notes` | `TEXT` | Preserved business remarks, detached duty, or special assignment notes. | `'Anti Drone พื้นที่ สอ.รฝ.'` -> `'Anti Drone พื้นที่ สอ.รฝ.'` |

---

## 4. `user_id` Mapping Strategy

The ZKTeco ZEM560 terminal and PostgreSQL foreign keys require string `user_id` values:
1. **Existing Device User Alignment**:
   - Terminal User `1`: `user_id = '1'` (Mapped to `จตุภัทร ลิมปนารมณ์`)
   - Terminal User `2`: `user_id = '2'` (Mapped to `นำโชค บุญพิทักษ์`)
2. **Sequential Assignment**: Rows 1 through 120 in the Excel file are mapped to `user_id` strings `'1'` through `'120'`.

---

## 5. Idempotent Import & Conflict Resolution Policy

1. **Idempotent SQL Upsert**:
   ```sql
   INSERT INTO employees (user_id, display_name, rank, position, notes, updated_at)
   VALUES (%s, %s, %s, %s, %s, NOW())
   ON CONFLICT (user_id) DO UPDATE SET
     display_name = EXCLUDED.display_name,
     rank = EXCLUDED.rank,
     position = EXCLUDED.position,
     notes = EXCLUDED.notes,
     updated_at = NOW();
   ```
2. **Immutability Invariant**: The original Excel workbook file `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx` MUST remain untouched and unchanged.

---

## 6. Audit & Rollback Strategy

1. **Pre-Import Dry Run Script**: An automated python validation script (`scripts/import_excel_employees.py`) will parse, validate, and verify zero name collisions before executing database writes.
2. **Audit Event Logging**: Upon completion of import, record audit log entry in PostgreSQL `sync_events`:
   - `event_type`: `'EXCEL_EMPLOYEE_IMPORT'`
   - `message`: `'Successfully imported/upserted 120 employee records from Excel'`
