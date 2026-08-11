# ADMS Excel Human Master Import Architecture & Contract

## Document Status

* **Status**: Approved Excel Import Architecture Specification & Contract
* **Source PromptID**: `ADMS-Data-ExcelImport-001`
* **Dataset File**: `excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx`
* **Sheet Name**: `ยอด ม.ค.69`
* **Target Table**: `human_employees` ONLY

---

## 1. Core Principles & Safety Boundaries

1. **Human Master Domain Isolation**:
   Importing Excel personnel creates records in `human_employees` **ONLY**. It MUST NOT interact with biometric terminal hardware, create ZKTeco `user_id` accounts, or assign fingerprint slots.
2. **Excel Row Number Is NOT Device User ID**:
   Excel row positions (1..120) **MUST NOT** be assigned as ZKTeco `user_id` values. Terminal `user_id` values originate strictly from local terminal enrollment (`ADMS-Device-RemoteEnrollmentCapability-001`).
3. **No Automatic Human-Device Mapping**:
   `employee_device_mappings` table remains empty (`0` records) until explicit, verified evidence is provided.
4. **Attendance Compatibility**:
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

| Source Excel Column | Clean Extracted Field | Target Database Column (`human_employees`) | Data Transformation / Rules |
| ------------------- | --------------------- | ------------------------------------------ | --------------------------- |
| N/A | `employee_id` | `employee_id` (UUID) | Auto-generated via `gen_random_uuid()` |
| N/A | `personnel_id` | `personnel_id` (TEXT) | `NULL` (Not present in source Excel) |
| Column 2 (`ยศ-ชื่อ-สกุล`) | `clean_display_name` | `display_name` (TEXT NOT NULL) | Name extracted after stripping rank prefix (e.g. `จตุภัทร ลิมปนารมณ์`) |
| Column 2 (`ยศ-ชื่อ-สกุล`) | `rank` | `rank` (TEXT) | Extracted rank prefix (e.g. `น.ท.`, `พ.จ.อ.`, `จ.อ.`, `พลฯ`) |
| Category Header | `category` | `position` (TEXT) | Category title (e.g. `นายทหาร`, `พันจ่า`, `จ่า`, `พลทหาร`) |
| Column 3 & 4 (`เหล่า` / `หมายเหตุ`) | `notes` | `notes` (TEXT) | Concatenated metadata (e.g. `เหล่า: สส. | หมายเหตุ: ป่วย`) |

---

## 4. Import Execution Contract (`sql/004_human_master_import.sql` PLAN ONLY)

> [!NOTE]
> Dry-run verification script `app/import_excel_human_master.py` will generate idempotent SQL `INSERT INTO human_employees (display_name, rank, position, notes)` statements for review before Stage 2 execution (`ADMS-Data-ExcelImport-002`).

```sql
-- SQL Template: Human Master Import
INSERT INTO human_employees (display_name, rank, position, notes)
VALUES (%s, %s, %s, %s)
ON CONFLICT (display_name) DO UPDATE 
  SET rank = EXCLUDED.rank, 
      position = EXCLUDED.position, 
      notes = EXCLUDED.notes, 
      updated_at = now();
```

---

## 5. Staged Execution Plan

1. **`ADMS-Data-ExcelImport-001` (Plan ONLY)**: Normalization, architecture contract, dry-run design $\to$ **COMPLETE**.
2. **`ADMS-Data-ExcelImport-002` (WRITE Mode)**: Dry-run script execution, SQL commit, database verification (`human_employees` = 120 records).
3. **`ADMS-Data-EmployeeDeviceMapping-001` (Future Plan)**: Manual/assisted identity verification mapping interface.
