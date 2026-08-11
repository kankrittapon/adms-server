# ADMS Excel Human Master Import Architecture & Contract

## Document Status

* **Status**: Approved Excel Import Architecture Specification & Contract
* **Source PromptIDs**: `ADMS-Data-ExcelImport-001` / `ADMS-Data-HumanMasterSchema-001`
* **Dataset File**: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx`
* **Sheet Name**: `ยอด ม.ค.69`
* **Target Table**: `human_employees` & `human_employee_sources` ONLY

---

## 1. Core Principles & Safety Boundaries

1. **Human Master Domain Isolation**:
   Importing Excel personnel creates records in `human_employees` and `human_employee_sources` **ONLY**. It MUST NOT interact with biometric terminal hardware, create ZKTeco `user_id` accounts, or assign fingerprint slots.
2. **Rejection of Name-Based Identity**:
   `display_name` does **NOT** have a unique constraint. `ON CONFLICT (display_name)` is **invalid SQL** and **semantically unsafe**. Import idempotency relies on `human_employee_sources(source_system, source_record_key)`.
3. **Excel Row Number Is NOT Device User ID**:
   Excel row positions (1..120) **MUST NOT** be assigned as ZKTeco `user_id` values. Terminal `user_id` values originate strictly from local terminal enrollment (`ADMS-Device-RemoteEnrollmentCapability-001`).
4. **No Automatic Human-Device Mapping**:
   `employee_device_mappings` table remains empty (`0` records) until explicit, verified evidence is provided.
5. **Attendance Compatibility**:
   Unmapped attendance records persist cleanly with `employee_id = NULL`. Import of `human_employees` does not disrupt raw attendance ingestion.

---

## 2. Dataset Profiling & Category Breakdown

* **Source Title**: `รายละเอียดกำลังพล พัน.สอล.กรม สน.สอ.รฝ. ณ ม.ค.69`
* **Total Clean Human Master Records**: **120 personnel**
* **Duplicate Names**: **0** (100% Unique Names)

### Category Breakdown

| Category Index | Category Name | Thai Title | Personnel Count | Rank Examples |
| -------------- | ------------- | ---------- | --------------- | ------------- |
| 1 | Commissioned Officers | `นายทหาร` | 20 | `น.ท.`, `น.ต.`, `ว่าที่ น.ต.`, `ร.อ.`, `ร.ท.`, `ว่าที่ ร.ต.` |
| 2 | Chief Petty Officers | `พันจ่า` | 58 | `พ.จ.อ.`, `พ.จ.ท.`, `พ.จ.ต.` |
| 3 | Petty Officers | `จ่า` | 6 | `จ.อ.`, `จ.ท.`, `จ.ต.` |
| 4 | Privates / Enlisted | `พลทหาร` | 36 | `พลฯ` (Branch contains intake batch e.g. `2/66`, `1/67`) |
| **Total** | | | **120** | |

---

## 3. Database Schema Mapping Contract

| Source Excel Column | Clean Extracted Field | Target Database Column | Data Transformation / Rules |
| ------------------- | --------------------- | ---------------------- | --------------------------- |
| N/A | `employee_id` | `human_employees.employee_id` (UUID) | Auto-generated via `gen_random_uuid()` |
| N/A | `personnel_id` | `human_employees.personnel_id` (TEXT) | `NULL` (Not present in source Excel) |
| Column 2 (`ยศ-ชื่อ-สกุล`) | `clean_display_name` | `human_employees.display_name` (TEXT NOT NULL) | Name extracted after stripping rank prefix |
| Column 2 (`ยศ-ชื่อ-สกุล`) | `rank` | `human_employees.rank` (TEXT) | Extracted rank prefix (e.g. `น.ท.`, `พ.จ.อ.`, `จ.อ.`, `พลฯ`) |
| Category Header | `category` | `human_employees.category` (TEXT) | Category title (e.g. `นายทหาร`, `พันจ่า`, `จ่า`, `พลทหาร`) |
| Column 3 (`เหล่า`) | `branch` | `human_employees.branch` (TEXT) | Service branch / Intake batch (e.g. `สส.`, `นว.ก.`, `2/66`) |
| Column 4 (`หมายเหตุ`) | `notes` | `human_employees.notes` (TEXT) | Remarks string (e.g. `ป่วย`, `ศปก.ทร.`) |
| Record Metadata | `source_record_key` | `human_employee_sources.source_record_key` | Deterministic import key (`EXCEL_FEB69_ROW_XXX`) |

---

## 4. Import Provenance Contract (`human_employee_sources`)

```sql
-- Provenance Table Schema (sql/004_human_master_schema.sql)
CREATE TABLE human_employee_sources (
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

## 5. Staged Execution Plan

1. **`ADMS-Data-ExcelImport-001` (Plan ONLY)**: Normalization, architecture contract, dry-run design $\to$ **COMPLETE**.
2. **`ADMS-Data-HumanMasterSchema-001` (Plan ONLY)**: Provenance architecture design $\to$ **COMPLETE**.
3. **`ADMS-Data-HumanMasterSchema-002` (WRITE Mode)**: Apply `sql/004_human_master_schema.sql` additive schema migration.
4. **`ADMS-Data-ExcelImport-002` (WRITE Mode)**: Dry-run script execution, SQL commit, database verification (`human_employees` = 120 records).
