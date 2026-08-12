# HUMAN ↔ DEVICE MAPPING WORKFLOW PLAN REPORT

**PromptID:** `ADMS-Data-HumanDeviceMapping-002`  
**Mode:** READ-ONLY / WORKFLOW PLAN ONLY + DOCUMENTATION WRITE ONLY  
**Date:** 2026-08-11  

---

## 1. Executive Summary & Authoritative Baseline

This report documents the administrator-controlled Human ↔ Device Mapping workflow design using the 120 Human Master records, 2 current device users, temporal `[valid_from, valid_to)` semantics, audit metadata (`verified_by`, `verification_method`, `verification_note`), overlap protection, reconciliation design, and candidate reports for device users 1 and 2.

**NO mappings are created in this phase.** This is a PLAN ONLY report. Mapping WRITE requires a future explicitly authorized PromptID (`ADMS-Data-HumanDeviceMapping-003`) after owner approval.

### Authoritative Checkpoint Baseline
- **Git Checkpoint:** `d9c81c9a54886914e9288c87d753c1baff03fab9` (all 3 nodes: TELEPHONE=origin=ai-brain synced)
- **Authoritative Backup:** `adms_post_timestamp_timezone_20260811_184500.dump` (SHA256: `f0e64f477a167712eda16c8670935513b8bf8e38ce18df349d49a276674ec0b1`)
- **`human_employees`:** 120 records
- **`human_employee_sources`:** 120 provenance records
- **`devices`:** 1 registered terminal (`SONIC ZEM560 #1`, serial `3392113170057`)
- **`device_users`:** 2 accounts (device_user_pk 1, device_user_pk 2)
- **`employee_device_mappings`:** 0 rows (UNMAPPED)
- **`attendance_logs`:** 7 logs preserved cleanly
- **Tests:** 87/87 PASS
- **Runtime:** Collector LIVE+HEALTHY (0 restarts), PostgreSQL healthy, MQTT healthy
- **Fingerprints read / modified:** NONE
- **Automatic sequential mapping:** PROHIBITED
- **Native ADMS Push:** EXPERIMENTAL / DEFERRED

---

## 2. Repository & Runtime Baseline Verification

### 2.1 Git Baseline (VERIFIED LIVE)

| Node | HEAD | Status |
|------|------|--------|
| TELEPHONE (local) | `d9c81c9` | PASS |
| origin | `d9c81c9` | PASS |
| ai-brain | `d9c81c9` | PASS |

Working tree: clean (no tracked modifications). Untracked: `.agent/`, `docs/reports/ADMS-Server-DeploymentDiscovery-001.md` (pre-existing, not part of this task).

### 2.2 Runtime Baseline (VERIFIED LIVE)

| Service | Status | Uptime |
|---------|--------|--------|
| adms-postgres | Up (healthy) | 20+ hours |
| mqtt | Up (healthy) | 19+ hours |
| listener | Up (healthy) | 14+ hours |

Collector state: `LIVE` — connected to ZKTeco `192.168.1.201:4370`, backfill idempotent (0 new records, 1 duplicate skipped on last cycle).

### 2.3 Database Baseline (VERIFIED LIVE)

| Table | Count |
|-------|-------|
| `human_employees` | 120 |
| `human_employee_sources` | 120 |
| `devices` | 1 |
| `device_users` | 2 |
| `attendance_logs` | 7 |
| `employee_device_mappings` | 0 |

---

## 3. Device User Inspection (VERIFIED LIVE)

### 3.1 Device Users Detail

| device_user_pk | device_id | device_user_id | device_uid | device_display_name | privilege | active | first_seen_at | last_seen_at | roster_last_seen_at | inactive_at |
|----------------|-----------|----------------|------------|---------------------|-----------|--------|---------------|--------------|---------------------|-------------|
| 1 | 1 | `2` | (empty) | `Device User 2` | 0 | `t` | 2026-08-11 08:34:07+00 | 2026-08-11 08:34:07+00 | (empty) | (empty) |
| 2 | 1 | `1` | (empty) | `Device User 1` | 0 | `t` | 2026-08-11 08:34:07+00 | 2026-08-11 12:58:56+00 | (empty) | (empty) |

**Key Observations:**
- `device_display_name` values are generic placeholders (`Device User 1`, `Device User 2`) — NOT real human names. The terminal roster has not been enriched with actual names by the administrator.
- `device_uid` is empty for both users — no biometric UID persisted in PostgreSQL (diagnostic only).
- `privilege = 0` for both users (standard user, no admin privileges on terminal).
- Both users are `active = true`.
- `roster_last_seen_at` and `inactive_at` are NULL — roster lifecycle observation not yet populated (columns exist from Schema 005 but collector does not yet write to them).
- `device_user_pk 1` ↔ `device_user_id = '2'` (note: PK order ≠ terminal user_id order)
- `device_user_pk 2` ↔ `device_user_id = '1'`

### 3.2 Attendance Distribution by Device User

| device_user_id | device_user_pk | Record Count | First Scan | Last Scan |
|----------------|----------------|--------------|------------|-----------|
| `1` | 2 | 6 | 2021-03-02 20:14:58+00 | 2026-08-11 08:30:54+00 |
| `2` | 1 | 1 | 2026-08-10 13:07:27+00 | 2026-08-10 13:07:27+00 |

**Key Observations:**
- Device user 1 (PK 2) has 6 attendance records spanning 2021 to 2026 — this is an actively used terminal account.
- Device user 2 (PK 1) has 1 attendance record from 2026-08-10 — recently active but sparse history.
- The 2021-03-02 record for user_id=1 predates the ADMS system — this is terminal flash memory backfill.
- All 7 attendance records have `employee_id = NULL` (unmapped) — confirmed by `employee_device_mappings = 0`.

---

## 4. Human Master Candidate Review (FILE EVIDENCE)

### 4.1 Human Master Distribution

The 120 Human Master records are distributed across 4 categories:

| Category | Count | Description |
|----------|-------|-------------|
| นายทหาร | 20 | Officers |
| พันจ่า | 58 | Senior NCOs |
| จ่า | 6 | NCOs |
| พลทหาร | 36 | Enlisted |
| **Total** | **120** | |

All 120 records have:
- `employee_id`: UUID (auto-generated)
- `display_name`: Thai names (e.g., นาย..., พัน..., etc.)
- `personnel_id`: ALL EMPTY
- `rank`: ALL EMPTY
- `position`: ALL EMPTY
- `branch`: populated (military branch)
- `category`: populated (one of the 4 above)

### 4.2 Candidate Matching Challenge

**CRITICAL:** The `device_display_name` values (`Device User 1`, `Device User 2`) are generic placeholders. They do NOT contain any human name information. Therefore:

- **Tier B (exact name match) is NOT possible** with current device data.
- **Tier C (similar/abbreviated name match) is NOT possible** with current device data.
- **Only Tier A (controlled scan observation) can establish a VERIFIED mapping.**

The administrator MUST either:
1. **Enrich the terminal roster** by editing device user names directly on the ZKTeco terminal keypad (local operation, not remote), OR
2. **Use the controlled test-scan workflow** (Section 7) to physically observe which person scans as which `device_user_id`.

---

## 5. Candidate Reports for Device Users 1 and 2

### 5.1 Candidate Report: Device User 1 (device_user_pk = 2, device_user_id = '1')

```text
Device User Identity:
  device_user_pk: 2
  device_id: 1 (SONIC ZEM560 #1, serial 3392113170057)
  device_user_id: '1'
  device_display_name: 'Device User 1'
  privilege: 0 (standard)
  active: true
  first_seen_at: 2026-08-11 08:34:07+00
  last_seen_at: 2026-08-11 12:58:56+00

Attendance Evidence:
  Records: 6
  First scan: 2021-03-02 20:14:58+00 (terminal flash backfill)
  Last scan: 2026-08-11 08:30:54+00 (live capture)
  Span: ~5 years (long-term active account)

Candidate Human Master: UNKNOWN
  display_name match: NOT POSSIBLE (generic device name)
  rank match: NOT POSSIBLE (rank empty in Human Master)
  category match: NOT POSSIBLE (no device-side category)
  personnel_id match: NOT POSSIBLE (personnel_id empty in Human Master)

Evidence Strength: NONE (no name-based matching possible)
Recommended Status: CANDIDATE (pending controlled scan)
Required Verification Method: CONTROLLED_SCAN
```

### 5.2 Candidate Report: Device User 2 (device_user_pk = 1, device_user_id = '2')

```text
Device User Identity:
  device_user_pk: 1
  device_id: 1 (SONIC ZEM560 #1, serial 3392113170057)
  device_user_id: '2'
  device_display_name: 'Device User 2'
  privilege: 0 (standard)
  active: true
  first_seen_at: 2026-08-11 08:34:07+00
  last_seen_at: 2026-08-11 08:34:07+00

Attendance Evidence:
  Records: 1
  First/Last scan: 2026-08-10 13:07:27+00 (live capture)
  Span: single day (recently active account)

Candidate Human Master: UNKNOWN
  display_name match: NOT POSSIBLE (generic device name)
  rank match: NOT POSSIBLE (rank empty in Human Master)
  category match: NOT POSSIBLE (no device-side category)
  personnel_id match: NOT POSSIBLE (personnel_id empty in Human Master)

Evidence Strength: NONE (no name-based matching possible)
Recommended Status: CANDIDATE (pending controlled scan)
Required Verification Method: CONTROLLED_SCAN
```

### 5.3 Candidate Summary

| Device User | device_user_pk | Attendance Records | Name Match | Candidate Human | Recommended Action |
|-------------|----------------|--------------------|------------|-----------------|-------------------|
| User 1 | 2 | 6 | NOT POSSIBLE | UNKNOWN | Controlled scan required |
| User 2 | 1 | 1 | NOT POSSIBLE | UNKNOWN | Controlled scan required |

**No automatic or name-based mapping can be performed.** Both device users have generic placeholder display names. The controlled test-scan workflow (Section 7) is the ONLY path to VERIFIED mappings.

---

## 6. Evidence Hierarchy Design

### 6.1 Evidence Strength Tiers

| Tier | Classification | Evidence Source | Auto-Apply Eligible | Target Status | Verification Method |
|------|---------------|-----------------|---------------------|---------------|---------------------|
| **Tier A** | **STRONG** | Physical operator observation + controlled test scan | NO (requires admin confirmation) | `VERIFIED` | `CONTROLLED_SCAN` |
| **Tier B** | **HIGH CANDIDATE** | Terminal display name exact match + Human Master name + rank context | NO | `CANDIDATE` | `TERMINAL_ROSTER_REVIEW` |
| **Tier C** | **PROBABLE** | Similar/abbreviated name, rank match, timing context | NO | `CANDIDATE` | `TERMINAL_ROSTER_REVIEW` |
| **Tier D** | **LEGACY** | Pre-existing mapping from legacy system migration | NO (requires admin review) | `LEGACY` | `LEGACY_MIGRATION` |
| **Tier E** | **INVALID** | Numeric equality (Excel row # == terminal user_id) | **PROHIBITED** | `REJECTED` | N/A |
| **Tier F** | **MANUAL** | Administrator manual confirmation without scan | NO | `VERIFIED` | `MANUAL_ADMIN_CONFIRMATION` |

### 6.2 Current Applicability

Given the current device data (generic display names, empty `device_uid`, empty Human Master `personnel_id`/`rank`):

- **Tier A (CONTROLLED_SCAN)** is the **only viable path** to VERIFIED mappings.
- **Tier B/C (TERMINAL_ROSTER_REVIEW)** becomes viable ONLY after the administrator enriches terminal display names locally on the ZKTeco keypad.
- **Tier D (LEGACY_MIGRATION)** is not applicable (no legacy mappings exist).
- **Tier E (numeric equality)** is PROHIBITED per AGENTS.md §14.
- **Tier F (MANUAL_ADMIN_CONFIRMATION)** is viable if the administrator has direct knowledge of who uses each terminal account (e.g., "User 1 is Private Smith because I saw them enroll").

---

## 7. Controlled Scan Workflow Design

### 7.1 Prerequisites

1. Collector must be running and LIVE (verified).
2. Administrator must be physically present at the terminal OR have the person available to scan.
3. A target Human Master record (`employee_id`) must be pre-selected.
4. Pre-test attendance watermark must be recorded.

### 7.2 Workflow Steps

```text
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: PRE-SCAN PREPARATION                                │
│  - Administrator selects target Human Master (employee_id)  │
│  - System records current watermark:                        │
│    SELECT MAX(scan_time) FROM attendance_logs               │
│    WHERE device_ip = '192.168.1.201';                       │
│  - Administrator notes target device_user_id to test        │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: CONTROLLED SCAN                                     │
│  - Administrator instructs person to perform ONE fingerprint│
│    scan on the terminal                                     │
│  - Person scans their enrolled fingerprint                  │
│  - Terminal records attendance in flash memory              │
│  - Collector captures event via realtime stream OR          │
│    next backfill cycle                                       │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: EVENT CAPTURE & IDENTIFICATION                      │
│  - System queries for new attendance after watermark:       │
│    SELECT device_user_id, device_user_pk, scan_time         │
│    FROM attendance_logs                                      │
│    WHERE device_ip = '192.168.1.201'                        │
│      AND scan_time > <watermark>                             │
│    ORDER BY scan_time ASC;                                   │
│  - System identifies the device_user_id that scanned        │
│  - System displays:                                          │
│    "Device User <device_user_id> scanned at <scan_time>"    │
│    "Candidate Human: <display_name> (<employee_id>)"        │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: ADMINISTRATOR CONFIRMATION                          │
│  - Administrator confirms: "Yes, this person is <name>"     │
│  - Administrator provides:                                  │
│    verified_by: <admin identifier>                          │
│    verification_method: 'CONTROLLED_SCAN'                    │
│    verification_note: <free text justification>              │
│    valid_from: <scan_time or admin-specified epoch>          │
│    valid_to: NULL (open-ended, active mapping)              │
│  - System creates CANDIDATE mapping (NOT VERIFIED yet)      │
│    OR VERIFIED mapping if admin explicitly confirms         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: MAPPING CREATION (FUTURE WRITE PHASE)               │
│  - INSERT INTO employee_device_mappings (                   │
│      employee_id, device_user_pk,                           │
│      mapping_status, mapping_source,                       │
│      verified_by, verification_method, verification_note,   │
│      valid_from, valid_to, verified_at                      │
│    ) VALUES (...)                                            │
│  - Mapping is created with status='VERIFIED'                │
│  - Future attendance for this device_user_pk will resolve   │
│    to this employee_id via temporal resolver                 │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: POST-MAPPING VERIFICATION                           │
│  - Verify mapping row exists with correct fields            │
│  - Verify temporal resolver returns correct employee_id    │
│  - Verify no overlap with existing VERIFIED mappings        │
│  - Log mapping creation in audit trail                       │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Multi-User Batch Scan Variant

For efficiency, the administrator may scan multiple people in sequence:

1. Record watermark.
2. Person A scans → identify device_user_id → confirm → select Human Master.
3. Person B scans → identify device_user_id → confirm → select Human Master.
4. Repeat for all persons.
5. Batch-create mappings in a single transaction (future WRITE phase).

**Safety:** Each scan must produce exactly ONE new attendance record. If a scan produces 0 records (e.g., fingerprint not enrolled) or multiple records (e.g., double scan), the workflow must pause and alert the administrator.

---

## 8. Temporal valid_from / valid_to Policy

### 8.1 Semantics

The temporal resolver uses `[valid_from, valid_to)` interval semantics:
- `valid_from` is **inclusive** (mapping is valid AT this timestamp)
- `valid_to` is **exclusive** (mapping is valid UP TO but NOT AT this timestamp)
- `valid_to = NULL` means **open-ended** (currently active)

### 8.2 valid_from Selection Policy

| Scenario | valid_from Value | Rationale |
|----------|-----------------|-----------|
| Controlled scan confirmation | `scan_time` of the controlled scan | The mapping is proven from the scan moment |
| Manual admin confirmation | `now()` at confirmation time | The mapping is asserted from confirmation moment |
| Terminal roster review | `now()` at review time | Name match is asserted at review time, not retroactively |
| Legacy migration | Original mapping creation timestamp | Preserve historical provenance |

**IMPORTANT:** `valid_from` should NOT be backdated to before the verification event unless there is explicit evidence that the person was using the terminal account from that earlier time. Backdating without evidence creates unverified historical attribution.

### 8.3 valid_to Selection Policy

| Scenario | valid_to Value | Rationale |
|----------|---------------|-----------|
| Active mapping (person still using account) | `NULL` | Open-ended, currently valid |
| Account transferred to new person | `valid_from` of the new mapping | Previous mapping ends where new one begins |
| Account deactivated on terminal | `inactive_at` timestamp | Mapping ends when account becomes inactive |
| Mapping revoked (error discovered) | `now()` at revocation | Mapping is no longer valid from revocation moment |

### 8.4 Historical Attendance Attribution

When a VERIFIED mapping is created with `valid_from = T`:
- Attendance records with `scan_time >= T` AND (`valid_to IS NULL` OR `scan_time < valid_to`) will be attributed to the mapped Human.
- Attendance records with `scan_time < T` will remain `employee_id = NULL` (unmapped) unless a separate historical mapping is created with appropriate evidence.

**Reconciliation of pre-mapping attendance is a SEPARATE decision** that requires:
1. Evidence that the same person was using the terminal account before `valid_from`.
2. Explicit administrator authorization to backdate.
3. A separate mapping row with `valid_from` set to the earlier provenance date and `verification_method = 'MANUAL_ADMIN_CONFIRMATION'` or `'LEGACY_MIGRATION'`.

---

## 9. Audit Metadata Vocabulary

### 9.1 verified_by

| Value | Description |
|-------|-------------|
| `SYSTEM_ADMIN` | Default system administrator (placeholder for unverified rows) |
| `<admin_name>` | Real administrator identifier (e.g., username, role title) |

**Policy:** `verified_by` MUST be a real administrator identifier for `VERIFIED` mappings. `SYSTEM_ADMIN` is only acceptable as a default for non-VERIFIED rows or during schema migration.

### 9.2 verification_method (CHECK constraint enforced)

| Value | Description | Evidence Required |
|-------|-------------|-------------------|
| `CONTROLLED_SCAN` | Administrator observed a controlled test scan | New attendance record after watermark |
| `TERMINAL_ROSTER_REVIEW` | Administrator reviewed terminal roster display name | Terminal display name matches Human Master |
| `MANUAL_ADMIN_CONFIRMATION` | Administrator has direct knowledge without scan | Admin justification in `verification_note` |
| `LEGACY_MIGRATION` | Migrated from a legacy system | Legacy system export evidence |

### 9.3 verification_note

Free-text field for audit justification. Recommended content:
- For `CONTROLLED_SCAN`: "Controlled scan on YYYY-MM-DD HH:MM by admin X. Person confirmed as <name>."
- For `TERMINAL_ROSTER_REVIEW`: "Terminal display name '<name>' matches Human Master <name> on YYYY-MM-DD."
- For `MANUAL_ADMIN_CONFIRMATION`: "Admin X confirms <name> uses terminal account <user_id> based on <evidence>."
- For `LEGACY_MIGRATION`: "Migrated from <legacy_system> on <date>. Original mapping ID: <id>."

### 9.4 mapping_status (CHECK constraint enforced)

| Value | Description | Resolver Behavior |
|-------|-------------|-------------------|
| `VERIFIED` | Administrator-confirmed mapping | Resolved by `resolve_verified_employee_mapping()` |
| `PROBABLE` | Likely match, not yet confirmed | NOT resolved (resolver is VERIFIED-only) |
| `LEGACY` | Migrated from legacy system | NOT resolved (requires admin review to promote to VERIFIED) |
| `CANDIDATE` | Potential match, pending verification | NOT resolved |
| `REVOKED` | Previously VERIFIED, now invalidated | NOT resolved |

---

## 10. Overlap Protection Design

### 10.1 Active VERIFIED Unique Index

Schema 005 already implements a partial unique index:

```sql
CREATE UNIQUE INDEX idx_active_verified_device_user 
  ON employee_device_mappings (device_user_pk) 
  WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL;
```

This ensures: **At most ONE active (open-ended) VERIFIED mapping per `device_user_pk`** at any time.

### 10.2 Temporal Overlap Detection

The partial unique index prevents duplicate active mappings but does NOT prevent temporal overlaps between bounded mappings. For example:

```text
Mapping A: valid_from=2026-01-01, valid_to=2026-06-01, VERIFIED
Mapping B: valid_from=2026-03-01, valid_to=2026-09-01, VERIFIED  ← OVERLAP
```

**Detection Strategy (WRITE phase):**

Before inserting a new VERIFIED mapping, the application MUST query:

```sql
SELECT mapping_id, employee_id, valid_from, valid_to
FROM employee_device_mappings
WHERE device_user_pk = %s
  AND mapping_status = 'VERIFIED'
  AND valid_from < %s  -- new_valid_to (or now() if NULL)
  AND (valid_to IS NULL OR %s < valid_to)  -- new_valid_from
;
```

If this query returns any rows, there is a temporal overlap. The application MUST:
1. Reject the insert, OR
2. Require the administrator to explicitly close the existing mapping (`valid_to = new_valid_from`) before creating the new one.

### 10.3 Sequential Temporal Mappings (Account Transfer)

When a terminal account is transferred from Person A to Person B:

```text
1. Update existing mapping:
   UPDATE employee_device_mappings 
   SET valid_to = <transfer_time>, updated_at = now()
   WHERE device_user_pk = <pk> 
     AND mapping_status = 'VERIFIED' 
     AND valid_to IS NULL;

2. Insert new mapping:
   INSERT INTO employee_device_mappings (
     employee_id, device_user_pk, mapping_status, mapping_source,
     verified_by, verification_method, verification_note,
     valid_from, valid_to, verified_at
   ) VALUES (
     <person_b_employee_id>, <pk>, 'VERIFIED', 'ADMIN_MANUAL',
     <admin>, 'CONTROLLED_SCAN', <note>,
     <transfer_time>, NULL, now()
   );
```

This creates a clean temporal boundary: `[old_valid_from, transfer_time)` → `[transfer_time, NULL)`.

---

## 11. Reconciliation Design

### 11.1 Post-Mapping Reconciliation

When a VERIFIED mapping is created, existing attendance records for that `device_user_pk` within the temporal validity window should have their `employee_id` populated:

```sql
UPDATE attendance_logs
SET employee_id = <mapped_employee_id>
WHERE device_user_pk = <pk>
  AND scan_time >= <valid_from>
  AND (valid_to IS NULL OR scan_time < valid_to)
  AND employee_id IS NULL;
```

**Safety constraints:**
- Only update rows where `employee_id IS NULL` (do not overwrite existing mappings).
- Only update rows within the temporal validity window.
- Raw device identity (`user_id`, `device_user_pk`, `scan_time`, `raw_payload`) remains IMMUTABLE.

### 11.2 Reconciliation Verification

After reconciliation:
```sql
SELECT 
  COUNT(*) FILTER (WHERE employee_id IS NOT NULL) AS mapped,
  COUNT(*) FILTER (WHERE employee_id IS NULL) AS unmapped,
  COUNT(*) AS total
FROM attendance_logs
WHERE device_user_pk = <pk>;
```

### 11.3 Unlink / Correction Reconciliation

If a mapping is discovered to be wrong:
1. Set `mapping_status = 'REVOKED'` and `valid_to = now()`.
2. Clear `employee_id` on attendance records that were attributed by this mapping:
   ```sql
   UPDATE attendance_logs
   SET employee_id = NULL
   WHERE device_user_pk = <pk>
     AND employee_id = <wrong_employee_id>
     AND scan_time >= <valid_from>
     AND (valid_to IS NULL OR scan_time < valid_to);
   ```
3. Create the correct mapping (if known).
4. Re-run positive reconciliation.

---

## 12. Mapping Creation Transaction Design (WRITE Phase Preview)

The future WRITE phase (`ADMS-Data-HumanDeviceMapping-003`) will use a single transaction:

```python
# Pseudocode — NOT executed in this phase
def create_verified_mapping(cur, employee_id, device_user_pk, verified_by,
                            verification_method, verification_note, valid_from):
    # 1. Check temporal overlap
    cur.execute("""
        SELECT mapping_id FROM employee_device_mappings
        WHERE device_user_pk = %s AND mapping_status = 'VERIFIED'
          AND valid_from < COALESCE(NULL, 'infinity'::timestamptz)
          AND (valid_to IS NULL OR %s < valid_to)
    """, (device_user_pk, valid_from))
    if cur.fetchone():
        raise OverlapError("Temporal overlap detected for device_user_pk")
    
    # 2. Insert mapping
    cur.execute("""
        INSERT INTO employee_device_mappings (
            employee_id, device_user_pk, mapping_status, mapping_source,
            verified_by, verification_method, verification_note,
            valid_from, valid_to, verified_at
        ) VALUES (%s, %s, 'VERIFIED', 'ADMIN_MANUAL', %s, %s, %s, %s, NULL, now())
        RETURNING mapping_id
    """, (employee_id, device_user_pk, verified_by,
          verification_method, verification_note, valid_from))
    mapping_id = cur.fetchone()[0]
    
    # 3. Reconcile existing attendance
    cur.execute("""
        UPDATE attendance_logs
        SET employee_id = %s
        WHERE device_user_pk = %s
          AND scan_time >= %s
          AND employee_id IS NULL
    """, (employee_id, device_user_pk, valid_from))
    
    return mapping_id
```

---

## 13. Dry-Run Preview Design

Before any WRITE, the system should provide a dry-run preview:

```text
=== MAPPING DRY-RUN PREVIEW ===
Target Human: <display_name> (<employee_id>)
Target Device User: device_user_id='1' (device_user_pk=2)
Verification Method: CONTROLLED_SCAN
valid_from: 2026-08-11 08:30:54+00
valid_to: NULL (open-ended)

Affected Attendance Records:
  device_user_pk=2, scan_time=2021-03-02 20:14:58+00 → employee_id=NULL (before valid_from, NOT affected)
  device_user_pk=2, scan_time=2026-08-11 08:30:54+00 → employee_id=<UUID> (will be mapped)
  ... (list all affected rows)

Overlap Check: PASS (no existing VERIFIED mappings)
Constraint Check: PASS (chk_temporal_validity, chk_verified_metadata, chk_verification_method)

Confirm? [y/N]: 
```

---

## 14. Positive Resolution Plan

After mappings are created, the temporal resolver (`resolve_verified_employee_mapping`) will:

1. For each incoming attendance record (realtime or backfill):
   - Call `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)`.
   - If exactly one VERIFIED mapping matches `[valid_from, valid_to)`: return `employee_id`.
   - If zero matches: return `None` (unmapped, `employee_id = NULL`).
   - If >1 matches: return `None` + log ambiguity error (safety fail-safe).

2. The resolver is already LIVE VERIFIED (TemporalIdentity-003 checkpoint PASS) and handles all edge cases correctly.

---

## 15. Device User Recycling Safety

Per AGENTS.md §15 (Temporal Identity), terminal-local user IDs may be recycled. The temporal mapping design protects against this:

```text
Timeline:
  2026-01-01: Person A enrolls as device_user_id='1' on terminal
  2026-01-15: Mapping created: Person A ↔ device_user_pk=2, valid_from=2026-01-01, valid_to=NULL
  2027-01-01: Person A leaves. Person B enrolls as device_user_id='1' (SAME terminal user_id)
  2027-01-02: Mapping A closed: valid_to=2027-01-01
              Mapping B created: Person B ↔ device_user_pk=2, valid_from=2027-01-01, valid_to=NULL

Historical query for scan_time=2026-06-15:
  → Resolves to Person A (valid_from=2026-01-01 <= 2026-06-15 < valid_to=2027-01-01)

Historical query for scan_time=2027-06-15:
  → Resolves to Person B (valid_from=2027-01-01 <= 2027-06-15 < valid_to=NULL)
```

**Critical:** When `ensure_device_user()` encounters an existing `device_user_pk` for `(device_id, device_user_id)`, it REUSES the PK. The temporal mapping boundaries ensure historical attendance is correctly attributed even after account recycling.

**Risk:** If Person B enrolls as `device_user_id='1'` and the administrator does NOT close Person A's mapping, the partial unique index `idx_active_verified_device_user` will PREVENT creating a second active VERIFIED mapping. This is the intended safety behavior — the administrator MUST explicitly close the old mapping first.

---

## 16. Roster Lifecycle Relationship

### 16.1 Current State

- `device_users.roster_last_seen_at`: NULL for both users (column exists, not populated)
- `device_users.inactive_at`: NULL for both users (column exists, not populated)
- Collector does NOT currently write to these columns

### 16.2 Planned Relationship

| Lifecycle Event | Column Update | Mapping Impact |
|----------------|---------------|----------------|
| User seen in terminal roster | `roster_last_seen_at = now()` | None (observation only) |
| User not seen for N days | `inactive_at = now()` | Administrator review triggered |
| User deleted from terminal | `inactive_at = now()` | Mapping `valid_to` should be set |

### 16.3 Implementation Status

Roster lifecycle detection is **NOT IMPLEMENTED** in the current collector. The columns exist in the schema (Schema 005) but are not populated. This is a future enhancement, not a blocker for mapping creation.

---

## 17. parse_time Impact Assessment

### 17.1 Known Defect

`parse_time()` in `app/db.py` does `hour, minute = map(int, val.split(":"))` but `ON_TIME_START`/`ON_TIME_END` are `"05:00:00"`/`"10:00:00"` (3 parts) → `too many values to unpack` → all attendance gets `status=UNKNOWN`.

### 17.2 Impact on Mapping Workflow

- **scan_time:** NOT affected (scan_time is independently captured and normalized)
- **employee_id resolution:** NOT affected (resolver uses `device_user_pk` + `scan_time`, not `status`)
- **status field:** ALL records have `status=UNKNOWN` — this is a data quality issue but does NOT block mapping creation or temporal resolution

### 17.3 Classification

**NON-BLOCKING** for HumanDeviceMapping-002 and the future WRITE phase. Reserved for `ADMS-Collector-AttendanceParseTime-001`.

---

## 18. Schema Constraints Summary (VERIFIED LIVE)

### 18.1 employee_device_mappings Constraints

| Constraint | Type | Definition |
|-----------|------|------------|
| `employee_device_mappings_pkey` | PRIMARY KEY | `mapping_id` |
| `employee_device_mappings_employee_id_fkey` | FOREIGN KEY | `employee_id` → `human_employees(employee_id)` ON DELETE CASCADE |
| `employee_device_mappings_device_user_pk_fkey` | FOREIGN KEY | `device_user_pk` → `device_users(device_user_pk)` ON DELETE CASCADE |
| `employee_device_mappings_mapping_status_check` | CHECK | `mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY', 'CANDIDATE', 'REVOKED')` |
| `chk_temporal_validity` | CHECK | `valid_to IS NULL OR valid_to > valid_from` |
| `chk_verified_metadata` | CHECK | `mapping_status <> 'VERIFIED' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL AND verification_method IS NOT NULL AND valid_from IS NOT NULL)` |
| `chk_verification_method` | CHECK | `verification_method IN ('CONTROLLED_SCAN', 'TERMINAL_ROSTER_REVIEW', 'MANUAL_ADMIN_CONFIRMATION', 'LEGACY_MIGRATION')` |
| `idx_active_verified_device_user` | UNIQUE INDEX | `device_user_pk` WHERE `mapping_status = 'VERIFIED' AND valid_to IS NULL` |
| `idx_employee_device_mappings_temporal` | INDEX | `(device_user_pk, mapping_status, valid_from, valid_to)` |

### 18.2 Column Defaults

| Column | Default |
|--------|---------|
| `verified_by` | `'SYSTEM_ADMIN'` |
| `verification_method` | `'MANUAL_ADMIN_CONFIRMATION'` |
| `verification_note` | NULL |
| `valid_from` | `now()` |
| `valid_to` | NULL |
| `mapping_source` | `'ADMIN_MANUAL'` |
| `verified_at` | `now()` |

---

## 19. WRITE Phase Authorization

### 19.1 Next Authorized PromptID

```text
ADMS-Data-HumanDeviceMapping-003
```

**Mode:** WRITE (requires explicit owner approval)  
**Purpose:** Execute the controlled scan workflow and create VERIFIED mappings for device users 1 and 2.

### 19.2 Authorization Requirements

Before WRITE phase begins:
1. Owner must explicitly approve mapping creation.
2. Administrator must be identified (`verified_by` value).
3. At least one controlled scan must be performed per device user.
4. Target Human Master records must be selected for each device user.
5. Fresh backup must be created before any mapping INSERT.

### 19.3 Checkpoint PromptID

```text
ADMS-Data-HumanDeviceMapping-004
```

**Mode:** READ-ONLY checkpoint  
**Purpose:** Verify mapping creation, temporal resolver behavior, reconciliation correctness, and runtime health.

---

## 20. Safety Summary

| Safety Rule | Status |
|-------------|--------|
| No mappings created in this phase | PASS |
| No schema changes | PASS |
| No terminal writes | PASS |
| No automatic sequential mapping | PASS |
| No name guessing | PASS |
| No backdating without evidence | PASS |
| Temporal overlap protection (partial unique index) | VERIFIED LIVE |
| VERIFIED-only resolver | VERIFIED LIVE |
| Ambiguity fail-safe (LIMIT 2) | VERIFIED LIVE |
| Raw device identity preservation | VERIFIED LIVE |
| Human Master immutability | PASS |
| Biometric template boundary | PASS (not stored in PostgreSQL) |
| Native ADMS Push | LOCKED (experimental, deferred) |

---

## 21. Documentation Updates

- **Report:** Created `docs/reports/ADMS-Data-HumanDeviceMapping-002.md` (this file)
- **STATUS.md:** Updated with HumanDeviceMapping-002 completion and next authorized PromptID

---

## 22. FINAL

```
PromptID: ADMS-Data-HumanDeviceMapping-002

repository verified: YES
database modified: NO
application modified: NO
device modified: NO
tests: PASS (87/87 — NOT RE-RUN, no code changes)
runtime verified: YES (LIVE+HEALTHY, 0 restarts)
commit created: YES (this commit)
push completed: PENDING
mappings created: 0
schema changes: 0
terminal writes: 0

next authorized PromptID: ADMS-Data-HumanDeviceMapping-003 (WRITE, requires owner approval)
checkpoint PromptID: ADMS-Data-HumanDeviceMapping-004
safe to proceed: YES (to WRITE phase with owner approval)
blockers: NONE

STOP.
```