# Device Enrollment Workflow — Canonical Documentation**Status:** IMPLEMENTED (INFRASTRUCTURE) + PILOT EXECUTED (READY_FOR_MAPPING)  
**Classification:** IMPLEMENTED — Production enrollment infrastructure + one-human controlled pilot executed (READY_FOR_MAPPING reached; VERIFIED mapping NOT created)  
**Related PromptIDs:** `ADMS-Data-DeviceEnrollmentWorkflow-001` (PLAN), `ADMS-Data-DeviceEnrollmentWorkflow-002` (IMPLEMENTATION), `ADMS-Data-DeviceEnrollmentPilot-001` (ONE-HUMAN PILOT)  
**Related Reports:** `docs/reports/ADMS-Data-DeviceEnrollmentWorkflow-001.md`, `docs/reports/ADMS-Data-DeviceEnrollmentWorkflow-002.md`, `docs/reports/ADMS-Data-DeviceEnrollmentPilot-001.md`    

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
RESERVED → TERMINAL_ACCOUNT_CREATED → FINGERPRINT_ENROLLMENT_PENDING → FINGERPRINT_ENROLLED → CONTROLLED_SCAN_PENDING → CONTROLLED_SCAN_CONFIRMED → READY_FOR_MAPPING

Terminal states: CANCELLED, RETIRED
```

| State | Description |
|-------|-------------|
| FINGERPRINT_ENROLLMENT_PENDING | Physical fingerprint enrollment window opened |
| RESERVED | ID allocated to a Human for a device; not yet on terminal |
| TERMINAL_ACCOUNT_CREATED | Terminal account exists via set_user(); no fingerprint yet |
| FINGERPRINT_ENROLLED | Operator confirms physical enrollment occurred |
| CONTROLLED_SCAN_PENDING | Narrow controlled-scan window opened (default 5 min) |
| CONTROLLED_SCAN_CONFIRMED | Matching scan observed inside window |
| READY_FOR_MAPPING | Operator confirms Human identity; ready for VERIFIED mapping (NOT a mapping) |
| CANCELLED | Reservation cancelled before completion |
| RETIRED | Enrollment closed without a mapping |

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

### Pilot Steps (EXECUTED 2026-08-12)
1. Owner selected one Human from Human Master: **กฤตพล หมาดเส็น** (พ.จ.ต., employee_id `039c4486-b30f-4ce1-b780-783cd268858d`).
2. ADMS allocated `device_user_id = 1001` via the production allocator (RESERVED).
3. ADMS created terminal account 1001 via `set_user()` (NORMAL privilege; pyzk returned False but roster verified creation — owner-approved reconciliation via canonical module path).
4. Human enrolled fingerprint(s) at the physical terminal under User ID 1001.
5. Verified roster evidence + captured device_uid (TERMINAL_ACCOUNT_CREATED → FINGERPRINT_ENROLLED).
6. Human performed ONE controlled scan (attendance id 12, 2026-08-12 08:47:37+00, within the 5-min window).
7. Owner confirmed identity explicitly (CONTROLLED_SCAN_CONFIRMED).
8. Enrollment reached **READY_FOR_MAPPING**. VERIFIED mapping NOT created (requires HumanDeviceMapping-003).
9. Checkpoint: post-pilot backup verified, runtime HEALTHY, 168/168 tests PASS.
10. Bulk enrollment remains BLOCKED until VERIFIED mapping + post-mapping checkpoint complete.

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

## 14. Enrollment Reservation Storage (IMPLEMENTED)

```sql
-- IMPLEMENTED — sql/006_device_user_enrollment_schema.sql
-- (Historical proposal; superseded by the implemented migration)

CREATE TABLE device_user_enrollments (  -- actual implemented name
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

## 14b. Implemented API (app/enrollment.py)

The production enrollment infrastructure is implemented in `app/enrollment.py`
(deployed inside the listener image on ai-brain):

| Function | Purpose |
|----------|---------|
| `reserve_next_device_user_id(cfg, employee_id, device_id, operator, roster_user_ids)` | Reserves the next safe production ID (>= 1001) for a Human on a device; validates Human/device, prevents duplicates, advisory-lock serialized |
| `create_reserved_terminal_account(cfg, enrollment_id, display_name, device)` | Creates the terminal account via `set_user()` (NORMAL privilege, exact reserved ID); fails safe on existing account / unreachable device |
| `verify_terminal_account_created(cfg, enrollment_id, roster_users)` | Verifies roster evidence: reserved ID present, NORMAL privilege, captures `device_uid` |
| `start_fingerprint_enrollment` / `confirm_fingerprint_enrolled` | Physical enrollment window + operator confirmation evidence |
| `start_controlled_scan_window` / `confirm_controlled_scan` | Bounded controlled-scan window; matching scan recorded as supporting evidence |
| `mark_ready_for_mapping` / `cancel_enrollment` / `retire_enrollment` | Explicit operator identity confirmation; safe cancel/retire paths |
| `validate_terminal_display_name` | ASCII-safe display name policy (no UUID / placeholder / Thai until rendering verified) |

State transitions are enforced in code AND by DB constraints
(`sql/006_device_user_enrollment_schema.sql`). No function creates a VERIFIED
mapping — `employee_device_mappings` remains the sole authoritative source.

## 15. Implementation Sequence

```text
ADMS-Data-DeviceEnrollmentWorkflow-001 (COMPLETE — PLAN ONLY)
        ↓
ADMS-Data-DeviceUserLifecycle-002 (WRITE — roster lifecycle detection)
        ↓
ADMS-Data-DeviceEnrollmentWorkflow-002 (COMPLETE — enrollment infrastructure IMPLEMENTED)
        ↓
ADMS-Data-DeviceEnrollmentPilot-001 (COMPLETE — ONE-HUMAN PILOT, READY_FOR_MAPPING reached)
        ↓
ADMS-Data-HumanDeviceMapping-003 (NEXT — create first VERIFIED mapping)
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
| Classification | IMPLEMENTED (INFRASTRUCTURE) + PILOT EXECUTED (READY_FOR_MAPPING) |
| Evidence | FILE EVIDENCE + VERIFIED LIVE (terminal account 1001, controlled scan, DB state) |
| Implementation | COMPLETE (app/enrollment.py + sql/006 deployed to ai-brain; 168/168 tests) |
| Pilot | COMPLETE — account 1001 (`cpo3 Krittapon M`, NORMAL), fingerprint enrolled, controlled scan 08:47:37+00, READY_FOR_MAPPING |
| Next PromptID | `ADMS-Data-HumanDeviceMapping-003` |
| Owner approval required | YES (for any WRITE phase) |