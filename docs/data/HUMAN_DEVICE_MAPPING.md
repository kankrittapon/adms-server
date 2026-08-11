# Canonical Architecture: Human ↔ Device Identity Mapping Workflow

**PromptID:** `ADMS-Data-HumanDeviceMapping-001`  
**Status:** ARCHITECTURE DESIGN COMPLETE / PLAN ONLY  

---

## 1. Overview & Purpose

This document defines the production mapping architecture for linking **Human Identities** (`human_employees.employee_id` UUID) with **Device Identities** (`device_users.device_user_pk` / `(device_id, device_user_id)`).

The workflow enables administrators to explicitly verify which real physical human employee owns each terminal-local account without relying on numeric row ordering or name guessing.

---

## 2. Fundamental Principles

1. **Strict Domain Separation:**
   - `human_employees` = Physical HR records (Excel imported). Primary Key: `employee_id` UUID.
   - `device_users` = Physical ZKTeco terminal local slots. Primary Key: `(device_id, device_user_id)`.
   - `employee_device_mappings` = Explicit, verified linking entity.
2. **Prohibition of Sequential Auto-Mapping:**
   - Excel row 1 $\neq$ ZKTeco `user_id '1'`.
   - Mapping based on insertion order, row number, or numeric coincidence is **STRICTLY PROHIBITED**.
3. **Verified-Only Attendance Enrichment:**
   - Raw `attendance_logs` always preserve raw `device_id` and `device_user_id`.
   - `attendance_logs.employee_id` is populated **ONLY** when an `employee_device_mappings` record has `mapping_status = 'VERIFIED'`. Unmapped attendance remains with `employee_id = NULL`.
4. **Local Biometric Enrollment:**
   - Remote enrollment (`CMD_STARTENROLL`) is unsupported on standalone firmware `Ver 6.60`.
   - User creation & fingerprint registration occur physically on terminal hardware.

---

## 3. Evidence Hierarchy

- **Tier A (Strong):** Observed physical test scan by known employee $\to$ Target `VERIFIED` (Requires explicit administrator confirmation).
- **Tier B (High Candidate):** Exact match of terminal display name + Human Master display name + rank context $\to$ Target `CANDIDATE`.
- **Tier C (Probable):** Partial/similar name match, rank match $\to$ Target `CANDIDATE`.
- **Tier D (Prohibited):** Numeric equality (Excel row # == terminal user_id) $\to$ **INVALID / REJECTED**.

---

## 4. Controlled Test-Scan Procedure

1. Admin selects Human employee record (`employee_id`).
2. Record latest attendance timestamp.
3. Person performs ONE normal scan on the terminal.
4. System detects new `attendance_log` entry `(device_id, device_user_id)`.
5. System displays candidate link for admin review.
6. Admin explicitly confirms verification $\to$ `VERIFIED` mapping row inserted via WRITE transaction.

---

## 5. Schema Gap Analysis & Next Phase Requirements

Current `employee_device_mappings` table lacks:
- `verified_by`: Audit identifier of verifying administrator.
- `verification_method`: `CONTROLLED_SCAN`, `ADMIN_MANUAL`, etc.
- `verification_note`: Justification notes.
- `valid_from` / `valid_to`: Temporal validity bounds to prevent misattribution if terminal `user_id` values are recycled/reassigned.

### Decision Gate Result
Because auditability and temporal identity bounds are required before writing production mappings, the project MUST proceed to:
```text
ADMS-Data-HumanDeviceMappingSchema-001 (PLAN ONLY)
```
prior to executing Mapping WRITE.
