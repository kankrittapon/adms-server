# Device Enrollment Workflow — Canonical Documentation

**Status:** IMPLEMENTED (PLAN)  
**Classification:** PLANNED — Production enrollment workflow design  
**Related PromptID:** `ADMS-Data-DeviceEnrollmentWorkflow-001`  
**Related Report:** `docs/reports/ADMS-Data-DeviceEnrollmentWorkflow-001.md`  

---

## Overview

This document defines the production workflow for enrolling Human Master records onto the ZKTeco ZEM560 terminal. It covers ID allocation, account creation, fingerprint enrollment, controlled scan verification, and VERIFIED mapping creation.

**Prerequisite:** Roster lifecycle detection must be implemented before production enrollment begins (`ADMS-Data-DeviceUserLifecycle-002`).

---

## 1. Identity Domains

| Domain | Table | Canonical Key | Scope |
|--------|-------|---------------|-------|
| Human | `human_employees` | `employee_id` (UUID) | Global |
| Device | `devices` | `device_id` / `serial_number` | Physical terminal |
| Device User | `device_users` | `device_user_pk` (BIGSERIAL) | Per-device account |
| Terminal ID | `device_users.device_user_id` | Terminal-visible ID (e.g., "1001") | Per-device |

**Rule:** No identity domain is interchangeable. No automatic or sequential mapping is performed.

---

## 2. Production ID Namespace

| Property | Value |
|----------|-------|
| Starting range | 1001 |
| Initial pool | 1001–1120 (120 IDs for 120 Humans) |
| Max capacity | 30,000 (ZEM560 limit) |
| Allocation | Monotonic (next = max(allocated) + 1) |
| Recycling | NO immediate reuse |
| Excel row mapping | PROHIBITED |
| Legacy IDs 1, 2 | RETIRED (LEGACY_TEST_ID) |

---

## 3. Account State Machine

```text
AVAILABLE → RESERVED → CREATED_ON_TERMINAL → FINGERPRINT_ENROLLED → CONTROLLED_SCAN_CONFIRMED → VERIFIED_MAPPING

Terminal states: CANCELLED, RETIRED, RE_ENROLL_REQUIRED
```

| State | Description |
|-------|-------------|
| AVAILABLE | ID is in the pool, not yet reserved |
| RESERVED | ID allocated to a Human, not yet on terminal |
| CREATED_ON_TERMINAL | Terminal account exists, no fingerprint yet |
| FINGERPRINT_ENROLLED | Biometric template stored on terminal |
| CONTROLLED_SCAN_CONFIRMED | Scan observed, administrator confirms |
| VERIFIED_MAPPING | Temporal mapping active, attendance resolves |
| CANCELLED | Reservation released before terminal creation |
| RETIRED | Mapping closed, account decommissioned |
| RE_ENROLL_REQUIRED | Fingerprint quality issue, same account |

---

## 4. Enrollment Workflow (12 Steps)

### Step 1: Select Human
- Administrator selects Human from Human Master.
- System confirms: `employee_id` (UUID), `display_name`, `rank`, `branch`, `category`.

### Step 2: Allocate Device User ID
- ADMS allocates next safe `device_user_id` from production namespace (1001+).
- Reservation created with status = `RESERVED`.

### Step 3: Create Terminal Account
- ADMS calls `set_user()` with allocated `device_user_id`.
- Account created on terminal (empty, no fingerprint).
- Reservation status → `CREATED`.
- Audit event logged in `sync_events`.

### Step 4: Fingerprint Enrollment
- Human goes to physical terminal.
- Human enrolls fingerprint(s) into the allocated account.
- Enrollment is performed locally on terminal keypad.
- Administrator verifies via `get_users()` roster check.
- Reservation status → `ENROLLED`.

### Step 5: Roster Verification
- System reads terminal roster (`get_users()`).
- Confirms account exists with fingerprint template.
- Does NOT extract fingerprint template data.

### Step 6: Controlled Scan
- Record pre-scan watermark.
- Human performs ONE fingerprint scan on terminal.
- Collector captures event via `live_capture()`.
- System identifies new attendance record.
- Reservation status → `CONFIRMED`.

### Step 7: Administrator Confirmation
- System displays scan details and candidate Human.
- Administrator confirms: "Yes, this person is <name>".
- Administrator provides: `verified_by`, `verification_method`, `verification_note`.

### Step 8: Mapping Creation
- `INSERT INTO employee_device_mappings` with:
  - `mapping_status = 'VERIFIED'`
  - `verification_method = 'CONTROLLED_SCAN'`
  - `valid_from = controlled scan timestamp`
  - `valid_to = NULL`
  - `verified_at = now()`

### Step 9: Post-Mapping Verification
- Verify mapping row exists with correct fields.
- Verify temporal resolver returns correct `employee_id`.
- Verify no overlap with existing VERIFIED mappings.

### Step 10: Reconciliation (Future)
- Existing attendance for this `device_user_pk` within `[valid_from, valid_to)` may be attributed to the Human.
- Only if evidence supports historical ownership.

### Step 11: Audit Logging
- Log mapping creation in audit trail.
- Log reservation state transition.
- Log sync_event for enrollment completion.

### Step 12: Future Scans Resolve Automatically
- All future scans from this `device_user_id` resolve to the mapped Human via temporal resolver.
- No manual intervention required for subsequent attendance.

---

## 5. Account Creation Responsibility

**Recommended:** ADMS creates terminal account via `set_user()`.

| Criterion | ADMS (Option A) | Manual (Option B) |
|-----------|-----------------|-------------------|
| Auditability | HIGH | MEDIUM |
| Risk of wrong ID | LOW | MEDIUM |
| Operator workload | LOW | MEDIUM |
| Device write safety | SAFE | SAFE |

ADMS ensures the exact reserved `device_user_id` is used, eliminating transcription errors. The administrator still performs fingerprint enrollment locally at the terminal.

---

## 6. Fingerprint Enrollment

| Property | Value |
|----------|-------|
| Location | PHYSICAL TERMINAL |
| Remote enrollment (`enroll_user()`) | DO NOT USE (timeout on firmware Ver 6.60) |
| Human chooses own ID | NO |
| Administrator guides enrollment | YES |
| Multiple fingers per Human | YES (one account, multiple templates) |
| One user_id per finger | NO (avoid) |

---

## 7. Name Policy

| Preference | Example |
|------------|---------|
| Short Romanized name | `Somsak` |
| Short name + initial | `Somsak P.` |
| Rank + short name | `PFC Somsak` |
| ID + short name | `1001-Somsak` |

**NOT recommended:**
- Full Thai names (may not render on legacy TFT display — requires pilot test).
- Generic placeholders (`Device User N`).
- Full UUID or database identifiers.

**Decision gate:** Before bulk enrollment, test Thai character rendering on terminal display.

---

## 8. Temporal Policy

### valid_from
- Default: controlled scan timestamp (post-normalization).
- Prohibited backdating to `first_seen_at`, first attendance, Excel import date, or deployment date.
- Manual backdating allowed only with `verification_method = 'MANUAL_ADMIN_CONFIRMATION'` and justification.

### valid_to
- Active: `NULL` (open-ended).
- Retired: ownership end boundary.
- Closing a mapping: `UPDATE ... SET valid_to = <end>, mapping_status = 'REVOKED'`.

### ID Recycling
- NO immediate reuse.
- Monotonically allocated IDs preferred while namespace capacity allows.

### Re-enrollment (Same Human, New Fingerprint)
- `device_user_id`: UNCHANGED.
- `device_user_pk`: UNCHANGED.
- Human mapping: UNCHANGED.
- `valid_from`: UNCHANGED.
- Only fingerprint template on terminal changes.

---

## 9. Retirement Workflow

1. Identify active VERIFIED mapping for this `device_user_pk`.
2. Determine ownership end boundary.
3. Close mapping: `valid_to = <end>`, `mapping_status = 'REVOKED'`.
4. Capture final roster evidence (`get_users()` snapshot).
5. Mark lifecycle: `inactive_at = now()`, `active = false`.
6. Delete terminal account (manual at terminal or future ADMS function).
7. Preserve database `device_users` row for historical audit.
8. Do NOT recycle `device_user_id` immediately.

---

## 10. Pilot Design

| Parameter | Value |
|-----------|-------|
| Pilot Humans | 1 |
| Pilot accounts | 1 |
| Pilot device_user_id | 1001 |
| Bulk before pilot checkpoint | NO |

### Pilot Steps
1. Owner selects one Human from Human Master.
2. ADMS allocates `device_user_id = 1001`.
3. ADMS creates terminal account 1001 via `set_user()`.
4. Human enrolls fingerprint at terminal.
5. Administrator verifies enrollment via roster check.
6. Human performs controlled scan.
7. Administrator confirms.
8. ADMS creates VERIFIED mapping.
9. Checkpoint: verify end-to-end flow.
10. Only after pilot PASS → bulk enrollment begins.

---

## 11. Bulk Rollout

| Property | Value |
|----------|-------|
| Batch size | 5–10 Humans per session |
| Per-Human steps | reserve → create → enroll → controlled scan → verify → map → checkpoint |
| Batch checkpoint | Verify mappings, test resolver, log audit, backup DB |
| Estimated sessions | 12–24 (for 120 Humans) |

---

## 12. Failure Handling

| Scenario | Action |
|----------|--------|
| Reserved but never enrolled | Release/retire reservation. No mapping. |
| Wrong Human enrolled | Do not map. Re-enroll under controlled procedure. |
| Controlled scan not observed | Do not map. Administrator reviews. |
| Terminal offline | Pause enrollment. Do not invent state. |
| Database unavailable | Do not continue without audit persistence. |
| `set_user()` fails | Log error. Retry or abort. No mapping. |
| Fingerprint enrollment fails | Account exists, no fingerprint. Human re-enrolls. No mapping until controlled scan. |

**Principle:** No mapping without evidence. No state invention. No silent recovery.

---

## 13. Security / Biometric Boundary

| Action | Allowed |
|--------|---------|
| Read roster (`get_users()`) | YES |
| Read fingerprint template bytes | NO |
| Export fingerprint templates | NO |
| Store templates in PostgreSQL | NO |
| Delete templates remotely | NO |

ADMS does NOT store fingerprint templates. The controlled scan proves possession/use of the account — it does NOT require template extraction.

---

## 14. Proposed Future Schema

```sql
-- PROPOSED — NOT YET CREATED
-- Requires ADMS-Data-DeviceEnrollmentWorkflow-002 (WRITE)

CREATE TABLE enrollment_reservations (
  reservation_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES human_employees(employee_id),
  device_id INTEGER NOT NULL REFERENCES devices(device_id),
  allocated_device_user_id TEXT NOT NULL,
  reserved_by TEXT NOT NULL,
  reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'RESERVED'
    CHECK (status IN ('AVAILABLE', 'RESERVED', 'CREATED', 'ENROLLED',
                      'CONFIRMED', 'CANCELLED', 'RETIRED')),
  terminal_account_created BOOLEAN NOT NULL DEFAULT false,
  fingerprint_enrolled BOOLEAN NOT NULL DEFAULT false,
  controlled_scan_verified BOOLEAN NOT NULL DEFAULT false,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (device_id, allocated_device_user_id)
);
```

---

## 15. Implementation Sequence

```text
ADMS-Data-DeviceEnrollmentWorkflow-001 (CURRENT — PLAN ONLY)
        ↓
ADMS-Data-DeviceUserLifecycle-002 (WRITE — roster lifecycle detection)
        ↓
ADMS-Data-DeviceEnrollmentWorkflow-002 (WRITE — enrollment infrastructure)
        ↓
FIRST PRODUCTION ENROLLMENT — ONE HUMAN ONLY (pilot)
        ↓
ADMS-Data-HumanDeviceMapping-003 (WRITE — create first VERIFIED mapping)
        ↓
ADMS-Data-HumanDeviceMapping-004 (READ-ONLY checkpoint)
        ↓
BULK ENROLLMENT (5–10 Humans per batch)
```

---

## 16. Multiple Devices

One Human may be enrolled on multiple physical terminals. Each device has its own:
- `device_user_id` (terminal-visible, scoped to device).
- `device_user_pk` (database PK).
- VERIFIED mapping (independent temporal interval).

The temporal resolver resolves per `device_user_pk`, so attendance from different devices resolves independently.

---

## Document Status

| Field | Value |
|-------|-------|
| Classification | PLANNED |
| Evidence | FILE EVIDENCE + VERIFIED LIVE (terminal state, DB baseline) |
| Implementation | NOT STARTED |
| Next PromptID | `ADMS-Data-DeviceUserLifecycle-002` |
| Owner approval required | YES (for any WRITE phase) |