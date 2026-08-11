# HUMAN ↔ DEVICE MAPPING PLAN REPORT

**PromptID:** `ADMS-Data-HumanDeviceMapping-001`  
**Mode:** READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY  
**Date:** 2026-08-11  

---

## 1. Executive Summary & Authoritative Baseline

This report documents the architectural design, discovery, verification workflow, and schema gap analysis for mapping **Human Identities** (`human_employees.employee_id` UUID) to **Device Identities** (`device_users.device_user_pk` / `(device_id, device_user_id)`).

### Authoritative Checkpoint Baseline
- **Git Checkpoint:** `a7b2cb1` (`docs: establish post Excel import checkpoint (# PromptID: ADMS-Checkpoint-PostExcelImport-001)`)
- **Database Recovery Archive:** `adms_post_excel_import_20260811_121449.dump` (SHA256: `d621f280af2fc3ebcf7e927afd55486cf5b9009cc1603300cc0d2ac60f9ed00a`)
- **`human_employees`:** 120 imported records
- **`human_employee_sources`:** 120 provenance records
- **`devices`:** 1 registered terminal (`SONIC ZEM560 #1`, serial `3392113170057`)
- **`device_users`:** 2 accounts (`user_id = '1'`, `user_id = '2'`)
- **`employee_device_mappings`:** 0 rows (Unmapped)
- **`attendance_logs`:** 6 logs preserved cleanly
- **Fingerprints read / modified:** NONE
- **Automatic sequential mapping:** PROHIBITED
- **Native ADMS Push:** EXPERIMENTAL / DEFERRED (Python Collector TCP 4370 remains authoritative)

---

## 2. Current Identity Architecture

The system strictly enforces separation across three distinct domains:

```text
+---------------------------------------+
| HUMAN MASTER DOMAIN                   |
| Table: human_employees                |
| Canonical Key: employee_id (UUID)     |
| Attributes: display_name, rank, etc.  |
+---------------------------------------+
                   ▲
                   |  (Explicit Resolution)
                   |  Table: employee_device_mappings
                   ▼
+---------------------------------------+
| DEVICE IDENTITY DOMAIN                |
| Table: device_users                   |
| Canonical Key: (device_id, user_id)   |
| Local Keys: device_user_id, device_uid|
+---------------------------------------+
                   ▲
                   |  (Terminal Flash Ownership)
                   ▼
+---------------------------------------+
| BIOMETRIC TEMPLATE DOMAIN             |
| Owned exclusively by terminal flash   |
| NOT stored/downloaded in PostgreSQL   |
+---------------------------------------+
```

### Critical Identity Safety Rule
The assumption `Excel row number == ZKTeco user_id` is **STRICTLY PROHIBITED**.
- Excel Employee #1 $\neq$ Device User `'1'`
- Excel Employee #2 $\neq$ Device User `'2'`
- Sequential auto-mapping based on row index, UUID order, or insertion sequence is **REJECTED**.

---

## 3. Physical Device Baseline & Roster Inspection

- **Terminal OEM / Platform:** SONIC ZEM560_TFT (MIPS Linux 2.6.24, Firmware `Ver 6.60 Aug 26 2011`)
- **Serial / IP:** `3392113170057` / `192.168.1.201:4370`
- **Known Terminal Accounts:**
  1. `user_id = '1'` (device_user_pk 1) — UNMAPPED
  2. `user_id = '2'` (device_user_pk 2) — UNMAPPED
- **Remote Enrollment Boundary:** Socket-driven `CMD_STARTENROLL` (0x0277) fails with a 60s timeout without activating UI on standalone firmware `Ver 6.60`. Remote biometric enrollment is **UNSUPPORTED / NOT USED**. All terminal user creation & fingerprint enrollment MUST occur locally on the physical terminal keypad.

---

## 4. Evidence Hierarchy & Controlled Test-Scan Workflow

Mapping decisions MUST follow a strict evidence strength model:

| Tier | Classification | Evidence Source | Auto-Apply Eligible | Target Status |
| :--- | :--- | :--- | :---: | :--- |
| **Tier A** | **STRONG** | Physical operator observation, controlled test scan | **NO** (Req. Admin Confirmation) | `VERIFIED` |
| **Tier B** | **HIGH CANDIDATE** | Terminal display name exact match + Human Master name + rank context | **NO** | `CANDIDATE` |
| **Tier C** | **PROBABLE** | Similar/abbreviated name, rank match, timing context | **NO** | `CANDIDATE` |
| **Tier D** | **INVALID** | Numeric equality (Excel row # == terminal user_id) | **PROHIBITED** | `REJECTED` |

### Recommended Controlled Test-Scan Procedure
1. Administrator selects one Human Master record (`employee_id`).
2. Record pre-test attendance watermark timestamp for target device.
3. Administrator instructs person to perform **ONE** normal fingerprint scan on terminal.
4. System observes newly captured `attendance_log` event `(device_id, device_user_id)`.
5. System displays candidate association `Human Identity` $\leftrightarrow$ `Device Identity`.
6. Administrator explicitly confirms verification.
7. Future authorized WRITE transaction creates `VERIFIED` mapping row.

---

## 5. Live Schema & Gap Analysis

Inspection of the current database contract in `sql/002_identity_foundation.sql`:

```sql
CREATE TABLE employee_device_mappings (
  mapping_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES human_employees(employee_id) ON DELETE CASCADE,
  device_user_pk BIGINT NOT NULL REFERENCES device_users(device_user_pk) ON DELETE CASCADE UNIQUE,
  mapping_status TEXT NOT NULL CHECK (mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY')),
  mapping_source TEXT NOT NULL DEFAULT 'ADMIN_MANUAL',
  verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Capability Assessment Matrix

| Capability Requirement | Current Schema Status | Description / Gap |
| :--- | :--- | :--- |
| **`employee_id` FK** | **SUPPORTED NOW** | References `human_employees(employee_id)` |
| **`device_user_pk` FK** | **SUPPORTED NOW** | References `device_users(device_user_pk)` |
| **One owner per device user** | **SUPPORTED NOW** | `device_user_pk` has `UNIQUE` constraint |
| **`mapping_status`** | **PARTIAL** | Supports `VERIFIED`, `PROBABLE`, `LEGACY`. Lacks `CANDIDATE`, `REJECTED`, `UNMAPPED`. |
| **`verified_at` timestamp** | **SUPPORTED NOW** | Column exists |
| **`verified_by` (Audit WHO)** | **NEEDS ADDITIVE SCHEMA** | **MISSING** — Cannot record administrator user/ID who verified mapping |
| **`verification_method` (Audit HOW)**| **NEEDS ADDITIVE SCHEMA** | **MISSING** — Cannot record `CONTROLLED_SCAN` vs `ADMIN_MANUAL` |
| **`verification_note` (Audit WHY)** | **NEEDS ADDITIVE SCHEMA** | **MISSING** — Cannot record audit justification text |
| **Temporal Identity (`valid_from` / `valid_to`)** | **NEEDS ADDITIVE SCHEMA** | **MISSING** — If terminal `user_id` is deleted and reassigned to another person, historical attendance identity cannot be bounded. |
| **`device_uid` persistence** | **SUPPORTED NOW** | Stored in `device_users.device_uid` |
| **Device User Lifecycle (`active`, `last_seen_at`)** | **SUPPORTED NOW** | Present on `device_users` table |

---

## 6. Critical User-ID Reuse & Audit Safety Analysis

### Questions Evaluated
1. **Can we prove WHO verified a mapping?**  
   **NO.** Current `employee_device_mappings` lacks `verified_by`.
2. **Can we prove HOW it was verified?**  
   **NO.** Current table lacks `verification_method`.
3. **Can we determine WHEN the mapping is valid temporally?**  
   **NO.** Current table lacks `valid_from` / `valid_to`.
4. **Can we prevent reused terminal `user_id` values from corrupting historical Human identity?**  
   **NO.** If terminal `user_id '1'` is deleted on terminal and re-enrolled for a different physical person in 2027, a timeless mapping will incorrectly attribute 2026 attendance to the new person upon backfill/enrichment.

### Mandatory Safety Gate Result
Because critical answers 1, 2, 3, and 4 are **NO**, proceeding directly to `ADMS-Data-HumanDeviceMapping-002` (Mapping WRITE) is **REJECTED**.

---

## 7. Next Authorized Phase Decision & Sequencing

### Chosen Route: ROUTE B (Schema Enhancement Required First)

The next authorized PromptID MUST be:
```text
ADMS-Data-HumanDeviceMappingSchema-001 (PLAN ONLY)
```

### Complete Sequencing Path
```text
ADMS-Data-HumanDeviceMapping-001  (PLAN ONLY - CURRENT)
        ↓
ADMS-Data-HumanDeviceMappingSchema-001  (Schema Enhancement PLAN ONLY)
        ↓
Schema WRITE (after explicit user approval)
        ↓
ADMS-Data-HumanDeviceMapping-002  (Human ↔ Device Mapping WRITE after explicit approval)
        ↓
ADMS-Checkpoint-PostHumanDeviceMapping-001
        ↓
Native ADMS Push Experimental Track
```

---

## 8. Historical Attendance Reconciliation & Correction Design

When a mapping status becomes `VERIFIED` in a future WRITE phase:
1. **Raw Device Identity Preservation:** `attendance_logs.user_id`, `device_id`, `device_user_pk`, `scan_time`, and `raw_payload` are IMMUTABLE and remain unchanged.
2. **Enrichment:** `attendance_logs.employee_id` will be populated for matching `device_user_pk` records where `employee_id IS NULL` within temporal validity `[valid_from, valid_to]`.
3. **Mapping Correction / Unlink:** If a mapping is corrected or removed, `attendance_logs.employee_id` can be updated/cleared via reconciliation without destroying raw terminal attendance logs.

---

## 9. Privacy & Component Boundaries

- **Human Master Boundary:** Excel Human Master (`human_employees`) remains authoritative. Mapping will never alter employee display names or ranks to match terminal strings.
- **Device User Boundary:** Device Users represent physical terminal state. Mapping will never modify terminal user accounts, passwords, or fingerprint templates.
- **Privacy Policy:** Reports and logs suppress fingerprint template bytes, passcodes, secret tokens, and full personal identification numbers.

---

## 10. Native ADMS Push Status

- **Status:** `EXPERIMENTAL / DEFERRED`
- **Lock Rule:** Native ADMS Push receiver implementation and socket port 8000 binding remain locked until Human ↔ Device Mapping and Post-Mapping Checkpoints are fully complete.

---

## 11. Documentation & STATUS Updates Complete

- **Report:** Created `docs/reports/ADMS-Data-HumanDeviceMapping-001.md`
- **Canonical Architecture:** Created `docs/data/HUMAN_DEVICE_MAPPING.md`
- **STATUS.md:** Updated with latest phase findings and next authorized PromptID (`ADMS-Data-HumanDeviceMappingSchema-001`).

---

## 12. FINAL Summary

- **Mapping Plan Complete:** YES
- **Database / Application / Device Modified:** NO
- **Mapping Rows Created:** 0
- **Sequential Mapping:** REJECTED / PROHIBITED
- **Safe to proceed directly to Mapping WRITE:** NO (Critical schema gaps in auditability & temporal identity exist)
- **Next Authorized PromptID:** `ADMS-Data-HumanDeviceMappingSchema-001` (PLAN ONLY)
