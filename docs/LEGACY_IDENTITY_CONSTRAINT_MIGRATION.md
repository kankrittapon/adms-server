# ADMS Legacy Identity Constraint Transition Architecture

## Document Status

* **Status**: Approved Constraint Transition Architecture Specification
* **Source PromptID**: `ADMS-Data-LegacyIdentityConstraint-001`
* **Target Subsystem**: PostgreSQL Database Schema (`attendance_logs`) & Collector Ingestion Layer (`app/db.py`)
* **Prerequisite**: Stage 2 Additive Schema Migration (`ADMS-Data-IdentitySchema-002`) Applied

---

## 1. Executive Summary & Constraint Problem

In the legacy baseline schema (`sql/001_schema.sql`), `attendance_logs` contains:
```sql
user_id TEXT NOT NULL REFERENCES employees(user_id)
```

### The Blocker
This foreign key constraint (`attendance_logs_user_id_fkey`) forces every raw `user_id` captured by the ZKTeco terminal to have a corresponding row in the legacy `employees` table. To satisfy this constraint, the Collector currently calls `ensure_employee_stub()`, which automatically creates fake employee rows (`User 1`, `User 2`).

### Target Resolution
Dropping `attendance_logs_user_id_fkey` decouples raw attendance ingestion from Human Master data. The raw `user_id` string column remains intact, but the Collector is no longer forced to auto-generate fake employee rows.

---

## 2. Target Constraint & Data Model

```text
BEFORE (Legacy Coupled Model):
[attendance_logs.user_id] ----(FK)----> [employees.user_id]  (Forces stub creation)

AFTER (Decoupled Identity Foundation Model):
[attendance_logs.user_id]               (Raw String Preserved / No FK)
[attendance_logs.device_id] ---------> [devices.device_id]
[attendance_logs.device_user_pk] ----> [device_users.device_user_pk]
[attendance_logs.employee_id] -------> [human_employees.employee_id] (NULLABLE)
```

---

## 3. Plan-Only DDL Specification (`sql/003_legacy_identity_constraint.sql`)

> [!NOTE]
> This DDL is provided for architecture review only. **Do NOT execute SQL until Stage 2 execution (`ADMS-Data-LegacyIdentityConstraint-002`)**.

```sql
-- SQL Migration 003: Legacy Identity Constraint Removal
-- PromptID: ADMS-Data-LegacyIdentityConstraint-001 / 002
-- Description: Drop obsolete foreign key constraint coupling raw attendance user_id to legacy employees table

ALTER TABLE attendance_logs 
  DROP CONSTRAINT IF EXISTS attendance_logs_user_id_fkey;
```

---

## 4. Zero Data Loss & Deduplication Safeguards

1. **Column Preservation**: `attendance_logs.user_id` string column remains `NOT NULL` and untouched.
2. **Deduplication Unchanged**: Constraint `UNIQUE (user_id, device_ip, scan_time)` remains **100% UNCHANGED**.
3. **Zero Row Deletion**: 0 rows are deleted from `attendance_logs` or `employees`.
4. **Historical Log Preservation**: All historical attendance records remain 100% intact.

---

## 5. Staged PromptID Execution Sequence

1. **`ADMS-Data-LegacyIdentityConstraint-001` (Plan ONLY)**: Architecture design $\to$ **COMPLETE**.
2. **`ADMS-Data-LegacyIdentityConstraint-002` (WRITE Mode)**: Full `pg_dump` backup, followed by executing `ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS attendance_logs_user_id_fkey;`.
3. **`ADMS-Collector-IdentityTransition-002` (WRITE Mode)**: Update `app/db.py` to replace `ensure_employee_stub()` with `ensure_device_user()`, populating additive identity references cleanly.
4. **`ADMS-Data-ExcelImport-001` (Plan ONLY)**: Design dry-run normalization and import script for populating `human_employees` from Excel (`120` records).
