# ADMS DEVICE ENROLLMENT WORKFLOW — POST-RESET LIVE AUDIT & PRODUCTION PLAN

**PromptID:** `ADMS-Data-DeviceEnrollmentWorkflow-001`  
**Mode:** READ-ONLY LIVE AUDIT / PLAN ONLY + DOCUMENTATION WRITE ONLY  
**Date:** 2026-08-12  
**Production Target:** `ai-brain` (`192.168.1.248`)  
**Source / Control Workstation:** `TELEPHONE`  

---

## 1. Executive Summary

The physical ZKTeco terminal has been manually reset at the user-account level by the owner. All terminal users were manually deleted from the ZKTeco terminal, and the system/Collector was restarted afterward.

This report documents the LIVE terminal state after manual deletion, verifies how the Collector/database reacted, preserves historical device identity and attendance evidence, designs a production-safe Device User ID allocation policy, and defines the complete enrollment workflow for the 120 Human Master records.

**NO terminal users were created, modified, or deleted by this Prompt.**  
**NO Human ↔ Device mappings were created.**  
**NO schema changes, application changes, or terminal writes were performed.**

---

## 2. Git Baseline (VERIFIED LIVE)

### 2.1 TELEPHONE

| Item | Value |
|------|-------|
| Branch | `main` |
| HEAD | `dafb851a9b90d927a4343d8552e0eb49fb7c3bf1` |
| origin/main | `dafb851a9b90d927a4343d8552e0eb49fb7c3bf1` |
| Working tree | Clean (no tracked modifications) |

### 2.2 ai-brain

| Item | Value |
|------|-------|
| Branch | `main` |
| HEAD | `dafb851a9b90d927a4343d8552e0eb49fb7c3bf1` |
| origin/main | `dafb851a9b90d927a4343d8552e0eb49fb7c3bf1` |
| Working tree | Clean |

### 2.3 Synchronization

```
TELEPHONE = origin/main = ai-brain = dafb851
```

**Synchronized: YES**

---

## 3. Runtime Verification (VERIFIED LIVE)

### 3.1 Docker Compose Services

| Service | Image | Status | Uptime | Health |
|---------|-------|--------|--------|--------|
| adms-postgres | postgres:16-alpine | Up | 20 hours | healthy |
| mqtt | eclipse-mosquitto:2 | Up | 20 hours | — |
| listener | adms-server-listener | Up | 15 hours | healthy |

### 3.2 Collector Health File (`/tmp/collector_health.json`)

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-08-12T03:51:59.458730+00:00",
  "state": "LIVE",
  "loop_alive": true,
  "device_connected": true,
  "db_status": "HEALTHY",
  "mqtt_status": "UNKNOWN",
  "reconnect_attempt": 0,
  "current_backoff_seconds": 0.0,
  "last_connect_success": "2026-08-11T12:58:56.626781",
  "last_connect_failure": null,
  "last_backfill_started_at": "2026-08-11T12:58:56.627864",
  "last_backfill_completed_at": "2026-08-11T12:58:56.857532",
  "last_event_received": null,
  "last_event_persisted": null
}
```

### 3.3 Collector Logs (Last Startup)

```
2026-08-11 12:58:56 [INFO] State transition: STARTING -> CONNECTING
2026-08-11 12:58:56 [INFO] Connected to ZKTeco terminal successfully!
2026-08-11 12:58:56 [INFO] State transition: CONNECTING -> BACKFILLING
2026-08-11 12:58:56 [INFO] Retrieved 7 raw attendance records from terminal flash memory.
2026-08-11 12:58:56 [INFO] Filtered 1 candidate records for reconciliation. Malformed: 0
2026-08-11 12:58:56 [INFO] Committed backfill batch chunk 1-1: 0 inserted, 1 duplicate skipped
2026-08-11 12:58:56 [INFO] Backfill complete in 0.23s: 7 seen, 1 candidates, 0 inserted, 1 duplicates skipped.
2026-08-11 12:58:56 [INFO] State transition: BACKFILLING -> LIVE
2026-08-11 12:58:56 [INFO] Entering LIVE attendance stream monitoring...
```

### 3.4 Runtime Summary

| Item | Value |
|------|-------|
| PostgreSQL | OPERATIONAL (healthy, 20h uptime) |
| MQTT | OPERATIONAL (20h uptime) |
| Collector | LIVE / HEALTHY (15h uptime, 0 restarts) |
| Collector restart count | 0 (since last startup) |
| FSM state | LIVE |
| Healthcheck | PASS (healthy) |
| ZKTeco connectivity | CONNECTED (192.168.1.201:4370) |

---

## 4. LIVE Terminal Roster — CRITICAL CHECK (VERIFIED LIVE)

A read-only Python script was executed inside the `listener` container using `pyzk==0.9` to query the physical terminal at `192.168.1.201:4370`.

### 4.1 Terminal Info

| Property | Value |
|----------|-------|
| firmware_version | `Ver 6.60 Aug 26 2011` |
| platform | `ZEM560_TFT` |

### 4.2 Terminal Users (Roster)

```
=== TERMINAL USERS (ROSTER) ===
  NO USERS FOUND (terminal roster is empty)
```

**Terminal user count: 0**

The owner's manual deletion is confirmed. The terminal roster is completely empty. No users remain on the physical terminal.

### 4.3 Terminal Attendance

```
attendance_count: 7
  user_id=1, timestamp=2021-03-03 03:14:58, status=1, punch=4
  user_id=1, timestamp=2021-03-03 03:15:01, status=1, punch=4
  user_id=1, timestamp=2021-03-03 03:16:40, status=1, punch=0
  user_id=1, timestamp=2021-03-03 07:46:03, status=1, punch=0
  user_id=1, timestamp=2026-08-10 19:47:39, status=1, punch=0
  user_id=2, timestamp=2026-08-10 20:07:27, status=1, punch=0
  user_id=1, timestamp=2026-08-11 15:30:54, status=1, punch=0
```

**Key Finding:** Deleting terminal users did NOT delete terminal attendance records. The 7 attendance records remain in terminal flash memory. This is important evidence — terminal account deletion preserves attendance history in flash memory.

### 4.4 Owner Manual Deletion Reflected

**YES** — Terminal roster is empty (0 users). The owner's manual deletion is fully reflected in the live terminal state.

---

## 5. LIVE Database Baseline (VERIFIED LIVE)

### 5.1 Row Counts

| Table | Count |
|-------|-------|
| `human_employees` | 120 |
| `human_employee_sources` | 120 |
| `devices` | 1 |
| `device_users` | 2 |
| `employee_device_mappings` | 0 |
| `attendance_logs` | 7 |

### 5.2 Attendance Mapping Status

| Status | Count |
|--------|-------|
| mapped (`employee_id IS NOT NULL`) | 0 |
| unmapped (`employee_id IS NULL`) | 7 |

### 5.3 Devices Table

| device_id | serial_number | device_name | device_ip | platform | firmware_version | last_seen_at |
|-----------|---------------|-------------|-----------|----------|------------------|--------------|
| 1 | 3392113170057 | SONIC ZEM560 #1 | 192.168.1.201 | ZEM560_TFT | Ver 6.60 Aug 26 2011 | 2026-08-11 12:58:56+00 |

### 5.4 Sync Events

| ID | Event Type | Message | Created At |
|----|-----------|---------|------------|
| 3 | HISTORICAL_BACKFILL | Backfill complete in 0.23s: 7 seen, 1 candidates, 0 inserted, 1 duplicates skipped. | 2026-08-11 12:58:56+00 |
| 2 | HISTORICAL_BACKFILL | Backfill complete in 0.22s: 7 seen, 1 candidates, 0 inserted, 1 duplicates skipped. | 2026-08-11 11:43:30+00 |
| 1 | HISTORICAL_BACKFILL | Backfill complete in 0.23s: 7 seen, 7 candidates, 7 inserted, 0 duplicates skipped. | 2026-08-11 08:34:07+00 |

### 5.5 Integrity Verification

- **Human Master:** 120/120 preserved — PASS
- **Mappings:** 0 — PASS (no unexpected mappings)
- **Attendance:** 7/7 preserved — PASS
- **No unexpected drift detected**

---

## 6. Former Device User Records (VERIFIED LIVE)

### 6.1 Device Users Detail

| device_user_pk | device_id | device_user_id | device_uid | device_display_name | privilege | active | first_seen_at | last_seen_at | roster_last_seen_at | inactive_at |
|----------------|-----------|----------------|------------|---------------------|-----------|--------|---------------|--------------|---------------------|-------------|
| 1 | 1 | `2` | (empty) | `Device User 2` | 0 | `t` | 2026-08-11 08:34:07+00 | 2026-08-11 08:34:07+00 | NULL | NULL |
| 2 | 1 | `1` | (empty) | `Device User 1` | 0 | `t` | 2026-08-11 08:34:07+00 | 2026-08-11 12:58:56+00 | NULL | NULL |

### 6.2 Attendance by Former Device User

| user_id | device_user_pk | Records | First Scan | Last Scan | Mapped |
|---------|----------------|---------|------------|-----------|--------|
| `1` | 2 | 6 | 2021-03-02 20:14:58+00 | 2026-08-11 08:30:54+00 | 0 |
| `2` | 1 | 1 | 2026-08-10 13:07:27+00 | 2026-08-10 13:07:27+00 | 0 |

### 6.3 Lifecycle Classification

| device_user_pk | device_user_id | Terminal Status | DB Status | Classification |
|----------------|----------------|-----------------|-----------|----------------|
| 1 | `2` | DELETED from terminal | `active = true`, `inactive_at = NULL` | **STALE** (DB still shows active, terminal has no such user) |
| 2 | `1` | DELETED from terminal | `active = true`, `inactive_at = NULL` | **STALE** (DB still shows active, terminal has no such user) |

### 6.4 Historical Records Preserved

**YES** — The database `device_users` rows for former terminal users 1 and 2 are preserved. They were NOT automatically deleted when the terminal users were physically removed. The `attendance_logs` FK references to `device_users.device_user_pk` remain valid.

### 6.5 inactive_at State

Both former device users have `inactive_at = NULL`. The Collector did NOT detect that the terminal users disappeared. This is expected evidence of the lifecycle implementation gap (Section 9).

### 6.6 Automatic Disappearance Detection

**NO** — The Collector does not compare the terminal roster against the database `device_users` table. When terminal users are deleted, the database records remain with `active = true` and `inactive_at = NULL`. There is no automatic mechanism to detect terminal-side user deletion.

---

## 7. Lifecycle Gap Verification

### 7.1 Current State

| Column | Exists | Populated | Automatic Detection |
|--------|--------|-----------|---------------------|
| `roster_last_seen_at` | YES (Schema 005) | NO (NULL for all users) | NO |
| `inactive_at` | YES (Schema 005) | NO (NULL for all users) | NO |

### 7.2 Gap Confirmation

After the owner deleted users 1 and 2 from the terminal:
- `inactive_at` remains NULL for both former device users.
- `roster_last_seen_at` remains NULL for both.
- `active` remains `true` for both.
- The Collector's `ensure_device_user()` function only performs INSERT/UPDATE (upsert) — it has no DELETE or deactivation logic.
- The Collector's backfill path calls `ensure_device_user()` only for `user_id` values found in attendance records. Since no new attendance has been generated by the deleted users, no upsert was triggered.

### 7.3 Automatic Lifecycle Detection

**NOT IMPLEMENTED** — Confirmed. The Collector does not:
1. Periodically read the terminal roster (`get_users()`) and compare against `device_users`.
2. Set `inactive_at` when a terminal user disappears.
3. Update `roster_last_seen_at` when a terminal user is observed in the roster.

### 7.4 Lifecycle Implementation Required Before Enrollment

**YES** — Roster lifecycle tracking should be implemented before production enrollment begins. Without it:
- The system cannot distinguish between active and stale device users.
- Account retirement cannot be automated.
- Historical audit lineage relies entirely on manual documentation.
- The `active` flag and `inactive_at` column provide no operational value if never populated.

**Recommended PromptID:** `ADMS-Data-DeviceUserLifecycle-002` (WRITE — implement roster lifecycle detection)

---

## 8. Historical Identity Preservation

### 8.1 Principle

```
Terminal account deletion != Database historical identity deletion
```

### 8.2 Verification

The database `device_users` rows for former terminal users 1 and 2 are **PRESERVED**. The `attendance_logs` FK references to `device_users.device_user_pk` remain valid. No historical attendance was deleted.

| Evidence | Status |
|----------|--------|
| `device_users` rows for user_id 1 and 2 | PRESERVED |
| `attendance_logs` FK references | VALID |
| `attendance_logs` records | 7/7 PRESERVED |
| `employee_device_mappings` | 0 (no mappings to preserve) |

### 8.3 Design Principle Confirmed

The database is an audit/history system and must NOT be cleaned merely to mirror terminal deletion. Historical device identity provides audit lineage for all attendance records.

---

## 9. Old User ID 1 / 2 Policy

### 9.1 Classification

The previous terminal accounts with `device_user_id = 1` and `device_user_id = 2` were test enrollments belonging to the owner (OWNER-PROVIDED FACT). They are classified as:

```
LEGACY_TEST_ID
```

### 9.2 Reuse Policy

| User ID | Reuse for Production | Reason |
|---------|--------------------|----|
| `1` | **NO** | Legacy test enrollment. Historical attendance (6 records) associated with this ID must not be conflated with a new production Human. |
| `2` | **NO** | Legacy test enrollment. Historical attendance (1 record) associated with this ID must not be conflated with a new production Human. |

### 9.3 Documentation Classification

These IDs are classified as `LEGACY_TEST_ID` in documentation and policy. No schema change is needed for this label — it is a policy/documentation classification only.

---

## 10. Production ID Namespace Design

### 10.1 Prohibited Allocation Methods

| Method | Status |
|--------|--------|
| Excel row number | PROHIBITED |
| Human Master row order | PROHIBITED |
| 1, 2, 3... derived from spreadsheet position | PROHIBITED |
| Employee UUID converted to integer | PROHIBITED |
| Fingerprint slot number as Human identity | PROHIBITED |

### 10.2 Production Namespace

```
Starting range: 1001+
Initial pool:   1001 - 1120 (120 IDs for 120 Human Master records)
```

**IMPORTANT:** The range 1001–1120 is a POOL of available identifiers, NOT a sequential assignment. `1001` is NOT assigned to Excel row 1 or Human Master record 1. Each ID is allocated individually by the ADMS ID allocator when a Human is selected for enrollment.

### 10.3 Allocation Strategy

```
next_available_id = MAX(allocated_ids) + 1, starting from 1001
```

- IDs are allocated monotonically (never recycled while namespace capacity allows).
- The ZEM560 supports 30,000 max users — namespace 1001+ provides ample capacity.
- IDs 1 and 2 are retired from production use (LEGACY_TEST_ID).

### 10.4 Uniqueness

- `device_user_id` is unique within the scope of a single physical device (`UNIQUE (device_id, device_user_id)` in `device_users`).
- The same `device_user_id` may exist on different physical devices (scoped to device).

### 10.5 Reservation Policy

- An ID can be reserved before terminal account creation.
- Reserved IDs are not yet active on the terminal.
- Reservation prevents duplicate allocation.

### 10.6 Reuse Policy

- **NO immediate reuse.** Once an ID is allocated to a Human, it is not reused for another Human even after the mapping is closed.
- If the namespace approaches capacity (30,000), a separate reuse policy may be designed with explicit temporal boundary management.

### 10.7 Retirement Policy

- When a Human leaves or an account is decommissioned:
  1. Close the VERIFIED mapping (`valid_to = ownership_end_boundary`).
  2. Record `inactive_at` on `device_users`.
  3. The `device_user_id` enters retirement (not reused).
  4. The terminal account may be deleted from the physical terminal.
  5. The database `device_users` row is PRESERVED for historical audit.

---

## 11. Identity Separation Model

### 11.1 Four Distinct Identity Domains

```text
┌─────────────────────────────────────────────────────┐
│ HUMAN IDENTITY                                       │
│ Table: human_employees                               │
│ Canonical Key: employee_id (UUID)                    │
│ Attributes: display_name, rank, branch, category    │
│ Source: Excel Human Master (120 records)             │
└─────────────────────────────────────────────────────┘
           │
           │ VERIFIED temporal mapping
           │ Table: employee_device_mappings
           │ [valid_from, valid_to)
           ▼
┌─────────────────────────────────────────────────────┐
│ DEVICE ACCOUNT IDENTITY                              │
│ Table: device_users                                  │
│ Canonical Key: device_user_pk (BIGSERIAL)            │
│ Natural Key: (device_id, device_user_id)             │
│ Attributes: device_display_name, privilege, active   │
└─────────────────────────────────────────────────────┘
           │
           │ terminal account representation
           ▼
┌─────────────────────────────────────────────────────┐
│ TERMINAL-VISIBLE ACCOUNT                             │
│ device_user_id (e.g., "1001")                        │
│ Visible on terminal keypad/display                   │
│ Enrolled with fingerprint template(s)               │
└─────────────────────────────────────────────────────┘
           │
           │ physical device ownership
           ▼
┌─────────────────────────────────────────────────────┐
│ DEVICE IDENTITY                                      │
│ Table: devices                                        │
│ Canonical Key: device_id (SERIAL)                    │
│ Natural Key: serial_number                            │
│ Attributes: device_ip, platform, firmware_version    │
└─────────────────────────────────────────────────────┘
```

### 11.2 Identity Boundary Rules

| Identity | Interchangeable? | Reason |
|----------|-----------------|--------|
| Human UUID ↔ device_user_pk | NO | Different domains, linked only by VERIFIED temporal mapping |
| device_user_pk ↔ device_user_id | NO | PK is database-internal; device_user_id is terminal-visible |
| device_user_id ↔ Human UUID | NO | Terminal account ID is NOT Human identity |
| Excel row ↔ device_user_id | NO | PROHIBITED (AGENTS.md §14) |
| device_id ↔ device_user_id | NO | Device identity is scoped to physical terminal |

### 11.3 Identity Boundaries Preserved

**YES** — All four identity domains remain strictly separated. No automatic or sequential mapping is performed.

---

## 12. Proposed Account State Machine

### 12.1 Enrollment State Model

```text
        ┌────────────┐
        │ AVAILABLE  │  ← ID is in the pool, not yet reserved
        └─────┬──────┘
              │ Administrator selects Human, ADMS allocates ID
              ▼
        ┌────────────┐
        │ RESERVED   │  ← ID allocated to a Human, not yet on terminal
        └─────┬──────┘
              │ Account created on physical terminal
              ▼
        ┌────────────────────────┐
        │ CREATED_ON_TERMINAL    │  ← Terminal account exists, no fingerprint yet
        └─────┬─────────────────┘
              │ Human enrolls fingerprint at terminal
              ▼
        ┌────────────────────────┐
        │ FINGERPRINT_ENROLLED   │  ← Biometric template stored on terminal
        └─────┬─────────────────┘
              │ Human performs controlled attendance scan
              ▼
        ┌──────────────────────────────┐
        │ CONTROLLED_SCAN_CONFIRMED    │  ← Scan observed, administrator confirms
        └─────┬───────────────────────┘
              │ VERIFIED mapping created in database
              ▼
        ┌──────────────────────┐
        │ VERIFIED_MAPPING     │  ← Temporal mapping active, attendance resolves
        └──────────────────────┘
```

### 12.2 Terminal/Abort States

```text
        ┌────────────┐
        │ CANCELLED  │  ← Reservation released before terminal creation
        └────────────┘

        ┌────────────┐
        │ RETIRED    │  ← Mapping closed, account decommissioned
        └────────────┘

        ┌─────────────────────────┐
        │ RE_ENROLL_REQUIRED       │  ← Fingerprint quality issue, same account
        └─────────────────────────┘
```

### 12.3 Schema Support Assessment

| State | Current Schema Support | Gap |
|-------|------------------------|-----|
| AVAILABLE | NO — no enrollment state table | Needs future table or status field |
| RESERVED | NO — no reservation mechanism | Needs future reservation table |
| CREATED_ON_TERMINAL | PARTIAL — `device_users` row exists | No enrollment-specific status |
| FINGERPRINT_ENROLLED | NO — no fingerprint enrollment tracking | Needs future field/table |
| CONTROLLED_SCAN_CONFIRMED | PARTIAL — attendance record exists | No explicit confirmation flag |
| VERIFIED_MAPPING | YES — `employee_device_mappings.mapping_status = 'VERIFIED'` | Sufficient |
| CANCELLED | NO | Needs future table |
| RETIRED | PARTIAL — `mapping_status = 'REVOKED'`, `valid_to` set | Sufficient for mapping |
| RE_ENROLL_REQUIRED | NO | Needs future field |

### 12.4 Future Schema/Application Change

**PROPOSED** — A future `enrollment_reservations` table could track:
- `reservation_id` (PK)
- `employee_id` (FK to `human_employees`)
- `device_id` (FK to `devices`)
- `allocated_device_user_id` (TEXT — the planned terminal ID)
- `reserved_by` (TEXT — administrator)
- `reserved_at` (TIMESTAMPTZ)
- `status` (TEXT — AVAILABLE, RESERVED, CREATED, ENROLLED, CONFIRMED, CANCELLED, RETIRED)
- `terminal_account_created` (BOOLEAN)
- `fingerprint_enrolled` (BOOLEAN)
- `controlled_scan_verified` (BOOLEAN)
- `notes` (TEXT)

**This is PLAN ONLY.** No schema is created in this Prompt.

---

## 13. Account Creation Responsibility

### 13.1 Option Comparison

| Criterion | Option A (ADMS creates) | Option B (Admin creates manually) |
|-----------|------------------------|----------------------------------|
| ZEM560 capabilities | `set_user()` is SUPPORTED (pyzk capability matrix) | N/A — manual keypad operation |
| pyzk reliability | `set_user()` verified as SAFE in capability matrix | No socket dependency |
| Auditability | HIGH — ADMS logs the creation with exact parameters | MEDIUM — admin must document manually |
| Risk of wrong ID | LOW — ADMS allocates and creates the exact reserved ID | MEDIUM — admin may mistype the ID |
| Operator workload | LOW — automated creation | MEDIUM — manual keypad entry |
| Device write safety | SAFE — `set_user()` is classified as SAFE | SAFE — no socket interaction |
| Recovery behavior | ADMS can retry or rollback reservation | Admin must manually delete wrong account |
| Fingerprint enrollment | Still manual at terminal | Still manual at terminal |

### 13.2 Recommendation

**Option A — ADMS creates terminal account** is recommended.

Rationale:
1. `set_user()` is verified as SAFE on the ZEM560 (capability matrix Tier 2).
2. ADMS can ensure the exact reserved `device_user_id` is used — eliminates transcription errors.
3. ADMS can log the creation event in `sync_events` for audit.
4. The administrator still performs fingerprint enrollment locally at the terminal.
5. The account is created empty (no fingerprint) — the Human enrolls their own biometric.

### 13.3 Workflow (Option A)

```text
1. Administrator selects Human from Human Master
2. ADMS allocates next safe device_user_id (e.g., 1001)
3. Reservation created (status = RESERVED)
4. ADMS calls set_user() to create empty terminal account with device_user_id = 1001
5. Human goes to terminal and enrolls fingerprint into account 1001
6. Administrator verifies enrollment from terminal roster (get_users())
7. Human performs controlled attendance scan
8. Administrator confirms scan
9. ADMS creates VERIFIED mapping
```

---

## 14. Fingerprint Enrollment Policy

### 14.1 Location

```
Fingerprint enrollment: PHYSICAL TERMINAL
```

Remote enrollment via `enroll_user()` (CMD_STARTENROLL) is classified as **DO NOT USE / NOT RECOMMENDED FOR PRODUCTION** on firmware `Ver 6.60` (verified — command times out without activating UI).

### 14.2 Human Knowledge Boundary

The Human should NOT need to know:
- `employee_id` (UUID)
- `device_user_pk` (database PK)
- Excel row number
- Any database internal identifier

At most, the operator may need the allocated `device_user_id` (e.g., `1001`) to guide the Human to the correct account on the terminal keypad.

### 14.3 Administrator-Guided Enrollment

The administrator:
1. Knows the allocated `device_user_id`.
2. Creates the account (via ADMS or manually at terminal).
3. Guides the Human to enroll their fingerprint at the terminal.
4. Verifies enrollment success via roster inspection.

The Human does not invent or choose their own ID.

---

## 15. Name Policy

### 15.1 Current Problem

The previous device users had generic placeholder names:
```
Device User 1
Device User 2
```

These provide no identification value and make name-based matching impossible.

### 15.2 Terminal Character/Encoding Constraints

The ZEM560_TFT firmware (`Ver 6.60`) is a MIPS Linux 2.6.24 device from 2011. Key constraints:

| Constraint | Assessment |
|------------|------------|
| Thai character support | UNCERTAIN — legacy firmware may not render Thai UTF-8 correctly on TFT display |
| ASCII character support | YES — verified (English text displays correctly) |
| Maximum name length | Unknown — ZKTeco typically supports 24-28 characters |
| Encoding | pyzk sends UTF-8; terminal may display garbled Thai characters |

### 15.3 Recommended Display Name Format

Given the uncertainty of Thai character rendering on the legacy ZEM560 TFT display:

**Recommended: Short Romanized name or employee code + short name**

Examples:
```
Somsak
Somsak P.
PFC Somsak
1001-Somsak
```

**NOT recommended:**
- Full Thai names (may not render correctly on TFT display)
- Generic placeholders (`Device User N`)
- Full UUID or database identifiers

### 15.4 Decision Gate

Before bulk enrollment, a **pilot test** should verify Thai character rendering on the terminal display:
1. Create a test account with a Thai name via `set_user()`.
2. Verify the terminal displays the name correctly.
3. If Thai renders correctly: use Thai short names.
4. If Thai does NOT render correctly: use Romanized short names.

**This test is NOT performed in this Prompt.** It is a prerequisite for the enrollment WRITE phase.

---

## 16. Reservation Design

### 16.1 Reservation Requirements

Before creating a terminal account, ADMS should know:

| Field | Purpose |
|-------|---------|
| Human | `employee_id` from `human_employees` |
| Device | `device_id` from `devices` |
| Allocated `device_user_id` | The planned terminal account ID (e.g., `1001`) |
| Operator | Administrator identifier |
| Reservation timestamp | When the reservation was made |
| Status | Current enrollment state |

### 16.2 Current Schema Sufficiency

The current schema does NOT have a reservation table. The `employee_device_mappings` table is designed for VERIFIED mappings, not for pre-enrollment reservations.

### 16.3 Proposed Future Schema

```sql
-- PROPOSED — NOT CREATED IN THIS PROMPT
CREATE TABLE enrollment_reservations (
  reservation_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES human_employees(employee_id),
  device_id INTEGER NOT NULL REFERENCES devices(device_id),
  allocated_device_user_id TEXT NOT NULL,
  reserved_by TEXT NOT NULL,
  reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  status TEXT NOT NULL DEFAULT 'RESERVED'
    CHECK (status IN ('AVAILABLE', 'RESERVED', 'CREATED', 'ENROLLED', 'CONFIRMED', 'CANCELLED', 'RETIRED')),
  terminal_account_created BOOLEAN NOT NULL DEFAULT false,
  fingerprint_enrolled BOOLEAN NOT NULL DEFAULT false,
  controlled_scan_verified BOOLEAN NOT NULL DEFAULT false,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (device_id, allocated_device_user_id)
);
```

**PLAN ONLY.** This schema is proposed for the future WRITE phase (`ADMS-Data-DeviceEnrollmentWorkflow-002`).

---

## 17. Controlled Enrollment Workflow

### 17.1 Complete Workflow (12 Steps)

```text
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: SELECT HUMAN                                        │
│  Administrator selects Human from Human Master              │
│  System displays: display_name, rank, branch, category     │
│  System confirms: employee_id (UUID)                       │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: ALLOCATE DEVICE USER ID                            │
│  ADMS allocates next safe device_user_id (e.g., 1001)      │
│  ID is from production namespace (1001+), NOT legacy IDs    │
│  Reservation created with status = RESERVED                │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: CREATE TERMINAL ACCOUNT                             │
│  ADMS calls set_user() with allocated device_user_id       │
│  Account created on terminal (empty, no fingerprint)       │
│  Reservation status → CREATED                              │
│  Audit event logged in sync_events                         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: FINGERPRINT ENROLLMENT                             │
│  Human goes to physical terminal                           │
│  Human enrolls fingerprint(s) into account 1001             │
│  Enrollment is performed locally on terminal keypad         │
│  Administrator verifies via get_users() roster check       │
│  Reservation status → ENROLLED                             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: ROSTER VERIFICATION                                │
│  System reads terminal roster (get_users())                │
│  Confirms account 1001 exists with fingerprint template    │
│  Does NOT extract fingerprint template data                │
│  Records: user exists, template count > 0                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: CONTROLLED SCAN                                    │
│  Record pre-scan watermark                                 │
│  Human performs ONE fingerprint scan on terminal            │
│  Collector captures event via live_capture()                │
│  System identifies new attendance record                   │
│  Reservation status → CONFIRMED                            │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 7: ADMINISTRATOR CONFIRMATION                         │
│  System displays:                                          │
│    "Device User 1001 scanned at <scan_time>"               │
│    "Candidate Human: <display_name> (<employee_id>)"        │
│  Administrator confirms: "Yes, this person is <name>"      │
│  Administrator provides:                                   │
│    verified_by, verification_method, verification_note     │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 8: MAPPING CREATION                                    │
│  INSERT INTO employee_device_mappings (                    │
│    employee_id, device_user_pk,                             │
│    mapping_status = 'VERIFIED',                             │
│    verified_by, verification_method, verification_note,    │
│    valid_from, valid_to = NULL, verified_at = now()        │
│  )                                                          │
│  Temporal resolver now resolves future scans to this Human │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 9: POST-MAPPING VERIFICATION                          │
│  Verify mapping row exists with correct fields              │
│  Verify temporal resolver returns correct employee_id      │
│  Verify no overlap with existing VERIFIED mappings         │
│  Verify reservation status → VERIFIED_MAPPING              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 10: RECONCILIATION (FUTURE)                           │
│  Existing attendance for this device_user_pk within         │
│  [valid_from, valid_to) may be attributed to the Human     │
│  Only if evidence supports historical ownership             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 11: AUDIT LOGGING                                     │
│  Log mapping creation in audit trail                       │
│  Log reservation state transition                          │
│  Log sync_event for enrollment completion                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 12: FUTURE SCANS RESOLVE AUTOMATICALLY                │
│  All future scans from device_user_id 1001 resolve to      │
│  the mapped Human via temporal resolver                     │
│  No manual intervention required for subsequent attendance  │
└─────────────────────────────────────────────────────────────┘
```

### 17.2 Safety Rule

**No step may infer Human identity solely from numeric ID.** The controlled scan (Step 6) and administrator confirmation (Step 7) are mandatory.

---

## 18. Mapping Creation Boundary

### 18.1 Insufficient Evidence for VERIFIED Mapping

A VERIFIED mapping MUST NOT be created merely because:

| Condition | Sufficient? |
|-----------|------------|
| ID was reserved | NO |
| Account was created on terminal | NO |
| Fingerprint was enrolled | NO |
| Terminal display name matches Human Master | NO |
| Numeric ID matches Excel row | NO (PROHIBITED) |

### 18.2 Required Evidence

The strongest production evidence for a VERIFIED mapping is:

```
CONTROLLED_ENROLLMENT_SCAN
```

This combines:
1. Known Human (selected from Human Master)
2. Known reserved account (allocated by ADMS)
3. Physical enrollment (fingerprint at terminal)
4. Controlled scan (observed attendance event)
5. Administrator confirmation (explicit verification)

### 18.3 Verification Method

The `verification_method` for enrollment-based mappings should be:

```
CONTROLLED_SCAN
```

This is already supported by the `chk_verification_method` CHECK constraint.

---

## 19. valid_from Policy

### 19.1 Recommended Default

For a newly enrolled production account:

```
valid_from = controlled scan timestamp (the scan that proved ownership)
```

### 19.2 Prohibited Backdating

Do NOT automatically backdate `valid_from` to:

| Source | Prohibited? | Reason |
|--------|------------|--------|
| `first_seen_at` | YES | First DB observation ≠ proven ownership |
| First attendance ever | YES | Cannot prove same Human owned the account then |
| Excel import date | YES | Import date ≠ terminal enrollment date |
| Server deployment date | YES | Deployment ≠ enrollment |
| `now()` at mapping creation | ACCEPTABLE | But controlled scan time is more precise |

### 19.3 Recommended Timestamp Source

The controlled scan's `scan_time` (post-normalization via `normalize_device_timestamp()`) is the strongest ownership boundary. It proves:
- The account existed on the terminal.
- A fingerprint was enrolled.
- A live scan was performed.
- The scan was observed by the Collector.

If the administrator has direct knowledge that the Human owned the account from an earlier time, `valid_from` can be set to that earlier time with `verification_method = 'MANUAL_ADMIN_CONFIRMATION'` and a justification in `verification_note`.

---

## 20. valid_to / Retirement Policy

### 20.1 Active Mapping

```
valid_to = NULL (open-ended, currently active)
```

### 20.2 Ownership End

When ownership ends:
1. Close the VERIFIED mapping: `valid_to = known ownership end boundary`.
2. Record the end boundary in `verification_note` or audit trail.
3. Set `mapping_status = 'REVOKED'` if the mapping was wrong, or leave as `VERIFIED` with `valid_to` set if the ownership simply ended.

### 20.3 Account Retirement

After closing the mapping:
1. Set `inactive_at` on `device_users` (requires lifecycle implementation).
2. Delete the terminal account from the physical terminal (manual or future ADMS function).
3. Preserve the database `device_users` row for historical audit.
4. Do NOT recycle the `device_user_id` immediately.

### 20.4 ID Recycling Policy

```
NO immediate reuse of device_user_id.
```

Prefer monotonically allocated IDs while namespace capacity allows (30,000 max users). This minimizes historical ambiguity and simplifies audit lineage.

---

## 21. Re-enrollment Policy

### 21.1 Same Human, New Fingerprint

If the same Human needs another fingerprint (poor scan quality, finger injury, finger change, template replacement):

| Keep | Change |
|------|--------|
| `device_user_id` | Fingerprint template on terminal |
| `device_user_pk` | — |
| Human mapping (`employee_id`) | — |
| `valid_from` | — |

### 21.2 Mapping valid_from

```
valid_from remains UNCHANGED.
```

If account ownership never changed, the temporal mapping boundary should not change. Re-enrolling a fingerprint is a biometric update, not an ownership change.

### 21.3 Re-enrollment Procedure

1. Human goes to terminal.
2. Administrator deletes old fingerprint template at terminal (local operation).
3. Human enrolls new fingerprint into the same account.
4. No database changes required.
5. No mapping changes required.
6. Log the re-enrollment in audit trail (future enhancement).

---

## 22. Multiple Fingers for Same Human

### 22.1 Preferred Model

```
one terminal account (device_user_id)
multiple fingerprint templates
one device_user_pk
one VERIFIED Human mapping
```

### 22.2 ZEM560 Support

The ZEM560 supports up to 3,000 fingerprint templates across 30,000 users. Multiple templates per user are supported by the ZKTeco platform — a single `user_id` can have multiple fingerprint templates enrolled.

### 22.3 Prohibited Model

```
one user_id per finger — AVOID
```

Creating separate terminal accounts for each finger of the same Human would:
- Consume unnecessary user slots.
- Create multiple `device_user_pk` values for one Human.
- Complicate temporal mapping (multiple mappings per Human per device).
- Increase ambiguity risk.

### 22.4 Exception

If the device forces one template per account (not the case for ZEM560), then multiple accounts would be unavoidable. The ZEM560 does NOT force this architecture.

---

## 23. Multiple Devices

### 23.1 Future Expansion Design

One Human may be enrolled on multiple physical terminals:

```text
Device A (serial XXX) → device_user_id = 1001
Device B (serial YYY) → device_user_id = 2042
```

Both map to the same:
```
human_employees.employee_id (UUID)
```

### 23.2 Device-Scoped Identity

`device_user_id` is scoped to a physical device. The same `device_user_id` value on different devices does NOT represent the same terminal account. Canonical device account identity is:

```
(device_id, device_user_id) → device_user_pk
```

### 23.3 Mapping Independence

Each device has its own independent VERIFIED mapping:
- `employee_device_mappings` row for Device A: `device_user_pk` A, `valid_from`, `valid_to`.
- `employee_device_mappings` row for Device B: `device_user_pk` B, `valid_from`, `valid_to`.

The temporal resolver resolves per `device_user_pk`, so attendance from different devices resolves independently.

---

## 24. Terminal Account Deletion Workflow

### 24.1 Safe Deletion Sequence

Before deleting a production terminal account:

```text
1. Identify active VERIFIED mapping for this device_user_pk
2. Determine ownership end boundary
3. Close mapping: UPDATE employee_device_mappings SET valid_to = <end>, mapping_status = 'REVOKED'
4. Capture final roster evidence (get_users() snapshot)
5. Mark lifecycle state: UPDATE device_users SET inactive_at = now()
6. Delete terminal account (manual at terminal or future ADMS function)
```

### 24.2 Historical Preservation

Do NOT delete:
- `device_users` database rows
- `attendance_logs` records
- `employee_device_mappings` history (including REVOKED mappings)

---

## 25. Device User Reuse Policy

### 25.1 Immediate Reuse

```
NO immediate reuse.
```

### 25.2 Future Reuse (If Required)

If reuse is eventually required (namespace exhaustion):

1. Old mapping `valid_to` must be closed.
2. Old lifecycle recorded (`inactive_at` set).
3. New ownership receives new temporal interval (`valid_from`).
4. Controlled verification required again (new controlled scan).
5. New `employee_device_mappings` row created with new `employee_id`.

### 25.3 Critical Rule

```
Never assume same device_user_id means same Human forever.
```

The temporal resolver handles this correctly via `[valid_from, valid_to)` semantics — historical attendance resolves to the old Human, new attendance resolves to the new Human.

---

## 26. Attendance Reconciliation

### 26.1 No Reconciliation in This Prompt

No attendance reconciliation is performed. The existing 7 test attendance rows remain unmapped (`employee_id = NULL`).

### 26.2 Future Reconciliation

Future reconciliation may update historical attendance only when temporal ownership is proven. The 7 test attendance rows MUST NOT automatically be assigned to a production Human simply because a new account later receives a similar ID.

### 26.3 Reason for Legacy ID Retirement

This is one major reason to avoid reusing `device_user_id` 1 and 2 for production:
- If user_id 1 is reused for a production Human, the 6 historical test attendance records would fall within the new mapping's `[valid_from, valid_to)` interval if `valid_from` is backdated.
- Even with `valid_from` set to the new enrollment time, the historical records remain unmapped but the ID conflation creates audit confusion.

---

## 27. Old Test Attendance Classification

### 27.1 Owner-Provided Evidence

```
Both previous fingerprint enrollments belonged to the owner.
```

**Classification:** OWNER-PROVIDED FACT

### 27.2 Documentation Classification

The existing 7 historical attendance records are classified as:

```
historical test attendance
unmapped
preserved
```

### 27.3 No Automatic Mapping

This Prompt MUST NOT create a mapping for those rows. Future owner instruction may explicitly request historical attribution, but this is NOT performed automatically.

### 27.4 Preservation Status

| Evidence | Status |
|----------|--------|
| `attendance_logs` (7 records) | PRESERVED |
| `device_users` (2 records) | PRESERVED |
| `employee_device_mappings` (0 records) | N/A |
| Terminal flash memory (7 records) | PRESERVED (confirmed via `get_attendance()`) |

---

## 28. Automatic Roster Lifecycle Assessment

### 28.1 Current State

| Feature | Status |
|---------|--------|
| `roster_last_seen_at` column | EXISTS (Schema 005) |
| `inactive_at` column | EXISTS (Schema 005) |
| Automatic roster lifecycle detection | NOT IMPLEMENTED |
| `ensure_device_user()` upsert only | CONFIRMED (no deactivation logic) |
| Roster comparison against DB | NOT IMPLEMENTED |

### 28.2 Implementation Recommendation

**YES** — Roster lifecycle tracking should be implemented before production enrollment.

Reasons:
1. Accounts will now be created/deleted intentionally — lifecycle tracking is operationally important.
2. Without it, the system cannot distinguish between active and stale device users.
3. The `active` flag and `inactive_at` column provide no value if never populated.
4. Account retirement workflow (Section 20) depends on `inactive_at` being set.
5. The current state (2 stale device users with `active = true`) demonstrates the gap.

### 28.3 Recommended PromptID

```
ADMS-Data-DeviceUserLifecycle-002
```

**Mode:** WRITE (requires explicit owner approval)  
**Purpose:** Implement automatic roster lifecycle detection — periodic `get_users()` comparison against `device_users`, populate `roster_last_seen_at` and `inactive_at`, set `active = false` when terminal user disappears.

### 28.4 Sequencing

```
ADMS-Data-DeviceEnrollmentWorkflow-001 (CURRENT — PLAN ONLY)
        ↓
ADMS-Data-DeviceUserLifecycle-002 (WRITE — implement lifecycle detection)
        ↓
ADMS-Data-DeviceEnrollmentWorkflow-002 (WRITE — implement enrollment infrastructure)
        ↓
FIRST PRODUCTION ENROLLMENT — ONE HUMAN ONLY
        ↓
ADMS-Data-HumanDeviceMapping-003 (WRITE — create first VERIFIED mapping)
        ↓
ADMS-Data-HumanDeviceMapping-004 (READ-ONLY checkpoint)
        ↓
BULK ENROLLMENT
```

---

## 29. Enrollment WRITE Phase

### 29.1 Next Recommended PromptID

```
ADMS-Data-DeviceEnrollmentWorkflow-002
```

**Mode:** WRITE (requires explicit owner approval)  
**Purpose:** Implement minimum infrastructure for controlled enrollment:
- ID allocator (next available production ID from 1001+)
- Reservation mechanism (`enrollment_reservations` table)
- Safe account creation path (`set_user()` wrapper with audit)
- Roster verification (post-creation `get_users()` check)

### 29.2 Prerequisites

Before `ADMS-Data-DeviceEnrollmentWorkflow-002`:
1. `ADMS-Data-DeviceUserLifecycle-002` should be completed (roster lifecycle detection).
2. Owner must explicitly approve enrollment infrastructure implementation.
3. Thai character rendering test on terminal display (Section 15.4).

### 29.3 HumanDeviceMapping-003 Readiness

```
HumanDeviceMapping-003 ready immediately: NO
```

**Reason:** The enrollment infrastructure (ID allocator, reservation table, safe account creation) must be implemented first. Without it, there is no safe mechanism to create production terminal accounts. Additionally, roster lifecycle detection should be implemented to track account state transitions.

---

## 30. First Production Enrollment — Pilot Design

### 30.1 Pilot Recommendation

**YES** — A pilot enrollment is required before bulk rollout.

### 30.2 Pilot Parameters

| Parameter | Value |
|-----------|-------|
| Pilot Humans | 1 |
| Pilot accounts | 1 |
| Pilot device_user_id | 1001 (first production ID) |
| Bulk enrollment before pilot checkpoint | NO |

### 30.3 Pilot Workflow

1. Owner selects one Human from Human Master (owner decision required).
2. ADMS allocates `device_user_id = 1001`.
3. ADMS creates terminal account 1001 via `set_user()`.
4. Human enrolls fingerprint at terminal.
5. Administrator verifies enrollment via roster check.
6. Human performs controlled scan.
7. Administrator confirms.
8. ADMS creates VERIFIED mapping.
9. Checkpoint: verify end-to-end flow.
10. Only after pilot PASS → bulk enrollment begins.

### 30.4 Owner as Pilot Human

The owner may be a suitable pilot Human because the owner is present in Human Master and is physically available. However, this Prompt MUST NOT select or map the Human automatically. **Owner decision required.**

---

## 31. Bulk Rollout Design

### 31.1 Batching Strategy

After successful pilot, bulk enrollment for 120 Humans should use **small batches**:

**Recommended batch size: 5–10 Humans per session**

Rationale:
- Each enrollment requires physical presence at the terminal.
- Fingerprint enrollment takes 30–60 seconds per person.
- Controlled scan verification adds time.
- Small batches allow error recovery without large rollback.
- Administrator fatigue is reduced.

### 31.2 Per-Human Steps (Bulk)

For each Human in a batch:
```
reserve → create → enroll → controlled scan → verify → map → checkpoint/audit
```

### 31.3 Batch Checkpoint

After each batch:
1. Verify all mappings created correctly.
2. Verify temporal resolver returns correct employee_id for test scans.
3. Log batch completion in audit trail.
4. Create database backup (recommended after each batch or daily).

### 31.4 Estimated Timeline

| Batch Size | Humans | Sessions | Est. Time per Session |
|-------------|--------|----------|----------------------|
| 5 | 120 | 24 | ~15–20 min |
| 10 | 120 | 12 | ~30–40 min |

---

## 32. Failure / Abort Behavior

### 32.1 Failure Scenarios

| Scenario | Action |
|----------|--------|
| Reserved but never enrolled | Release or retire reservation. No VERIFIED mapping. |
| Account created but wrong Human enrolled | Do not map. Remove/re-enroll under controlled procedure. Record incident. |
| Controlled scan not observed | Do not map. Administrator reviews. |
| Duplicate/ambiguous scan | Do not map. Administrator review. |
| Terminal offline | Pause enrollment. Do not invent state. |
| Database unavailable | Do not continue account provisioning without audit persistence. |
| `set_user()` fails | Log error. Retry or abort. Do not create mapping. |
| Fingerprint enrollment fails | Account exists but no fingerprint. Human re-enrolls. No mapping until controlled scan succeeds. |

### 32.2 Abort Principle

```
No mapping without evidence.
No state invention.
No silent recovery.
```

---

## 33. Security / Biometric Boundary

### 33.1 Architecture

```
Fingerprint template → ZKTeco terminal responsibility (flash memory)
Human identity       → ADMS Human Master (human_employees)
Binding              → Temporal verified mapping (employee_device_mappings)
```

### 33.2 Boundary Rules

- ADMS does NOT store fingerprint templates in Human Master.
- ADMS does NOT export biometric templates for identity mapping.
- ADMS does NOT need to read fingerprint data to create a VERIFIED mapping.
- The controlled scan proves possession/use of the account — it does NOT require template extraction.

### 33.3 Template Safety

| Action | Allowed? |
|--------|----------|
| Read roster (user list) | YES (read-only) |
| Read fingerprint template bytes | NO (not needed, privacy boundary) |
| Export fingerprint templates | NO |
| Store templates in PostgreSQL | NO |
| Delete templates remotely | NO (manual at terminal) |

---

## 34. Native ADMS Push

```
Status: EXPERIMENTAL / DEFERRED
```

Enrollment workflow is NOT coupled to Native ADMS Push testing. Native ADMS Push remains locked until:
1. Human ↔ Device Mapping workflow is complete.
2. Bulk enrollment is complete.
3. Post-mapping checkpoint passes.

---

## 35. Documentation Updates

| Document | Status |
|----------|--------|
| `docs/reports/ADMS-Data-DeviceEnrollmentWorkflow-001.md` | CREATED (this file) |
| `docs/data/DEVICE_ENROLLMENT_WORKFLOW.md` | CREATED (canonical workflow document) |
| `STATUS.md` | UPDATED |

---

## 36. Test Status

```
tests executed this Prompt: NO

previous verified baseline: 87/87 PASS
```

No code changes were made in this Prompt. Tests were not re-run.

---

## 37. Required Report

```
ADMS DEVICE ENROLLMENT WORKFLOW — POST-RESET AUDIT & PLAN REPORT

PromptID:
ADMS-Data-DeviceEnrollmentWorkflow-001


GIT

TELEPHONE HEAD:
dafb851a9b90d927a4343d8552e0eb49fb7c3bf1

origin/main:
dafb851a9b90d927a4343d8552e0eb49fb7c3bf1

ai-brain HEAD:
dafb851a9b90d927a4343d8552e0eb49fb7c3bf1

synchronized:
YES


RUNTIME

PostgreSQL:
OPERATIONAL (healthy, 20h uptime)

MQTT:
OPERATIONAL (20h uptime)

Collector:
LIVE / HEALTHY (15h uptime, 0 restarts)

restart count:
0

FSM:
LIVE

Healthcheck:
PASS (healthy)

ZKTeco:
CONNECTED (192.168.1.201:4370)


LIVE TERMINAL

terminal user count:
0

terminal users:
NONE (roster empty — owner manual deletion confirmed)

terminal attendance count:
7 (preserved in flash memory)

owner manual deletion reflected:
YES


DATABASE

human_employees:
120

human_employee_sources:
120

devices:
1

device_users:
2

employee_device_mappings:
0

attendance_logs:
7

unmapped attendance:
7 (all employee_id = NULL)


FORMER DEVICE USERS

user_id 1:
device_user_pk=2, active=true, inactive_at=NULL, 6 attendance records, STALE

user_id 2:
device_user_pk=1, active=true, inactive_at=NULL, 1 attendance record, STALE

historical records preserved:
YES

inactive_at state:
NULL for both (lifecycle gap confirmed)

automatic disappearance detection:
NO


LIFECYCLE

roster_last_seen_at supported:
YES (column exists)

inactive_at supported:
YES (column exists)

automatic lifecycle operational:
NO

lifecycle implementation required before enrollment:
YES

recommended PromptID if required:
ADMS-Data-DeviceUserLifecycle-002


PRODUCTION ID POLICY

legacy test IDs:
1, 2 — classified as LEGACY_TEST_ID, retired from production reuse

reuse user_id 1:
NO

reuse user_id 2:
NO

production namespace:
1001+ (initial pool 1001-1120 for 120 Humans)

allocation strategy:
Monotonic allocation from 1001+, no recycling, no Excel row mapping

Excel row mapping:
PROHIBITED

automatic sequential Human mapping:
PROHIBITED


IDENTITY MODEL

Human:
human_employees.employee_id (UUID)

Device:
devices.device_id / serial_number

Device User:
device_users.device_user_pk (BIGSERIAL)

Terminal ID:
device_user_id (terminal-visible, e.g., "1001")

identity boundaries preserved:
YES


ENROLLMENT DESIGN

recommended account creation:
ADMS (Option A — set_user() with audit logging)

fingerprint enrollment:
PHYSICAL TERMINAL

Human chooses own ID:
NO

controlled scan required:
YES

administrator confirmation required:
YES

VERIFIED mapping creation point:
After controlled scan + admin confirmation (Step 8 of workflow)


ACCOUNT STATE MODEL

states:
AVAILABLE → RESERVED → CREATED_ON_TERMINAL → FINGERPRINT_ENROLLED → CONTROLLED_SCAN_CONFIRMED → VERIFIED_MAPPING
Terminal states: CANCELLED, RETIRED, RE_ENROLL_REQUIRED

schema support sufficient:
NO (current schema lacks reservation/enrollment state tracking)

future schema/application change:
PROPOSED enrollment_reservations table (PLAN ONLY)


TEMPORAL POLICY

valid_from:
Controlled scan timestamp (post-normalization)

valid_to:
NULL (active) or ownership end boundary (retired)

ID recycling:
NO immediate reuse — monotonically allocated IDs preferred

re-enrollment changes mapping boundary:
NO (same Human, same account, valid_from unchanged)


BIOMETRIC MODEL

multiple fingers same Human:
YES — one terminal account, multiple templates, one mapping

one user_id per finger:
NO (avoid — unnecessary complexity)

fingerprint templates stored in Human Master:
NO


HISTORICAL TEST DATA

existing test attendance:
7 records (6 for user_id=1, 1 for user_id=2), all unmapped, all preserved

automatically map to production Human:
NO

preserved:
YES


PILOT

recommended:
YES

pilot Humans:
1

pilot accounts:
1

bulk enrollment before pilot checkpoint:
NO


NEXT PHASE

next recommended PromptID:
ADMS-Data-DeviceUserLifecycle-002

mode:
WRITE (requires owner approval)

HumanDeviceMapping-003 ready immediately:
NO

reason:
Enrollment infrastructure (ID allocator, reservation, safe account creation) and
roster lifecycle detection must be implemented before the first production
enrollment and VERIFIED mapping creation.


SAFETY

database modified:
NO

schema modified:
NO

application modified:
NO

terminal modified by Agent:
NO

fingerprints modified by Agent:
NO

mappings created:
0

automatic mappings:
0

Native ADMS Push:
NOT EXECUTED


TESTS

tests executed this Prompt:
NO

result:
N/A

previous verified baseline:
87/87 PASS


DOCUMENTATION

report:
docs/reports/ADMS-Data-DeviceEnrollmentWorkflow-001.md

canonical workflow doc:
docs/data/DEVICE_ENROLLMENT_WORKFLOW.md

STATUS updated:
YES

commit:
(this commit)

push:
YES
```

---

## 38. FINAL

```
PromptID:
ADMS-Data-DeviceEnrollmentWorkflow-001

post-reset terminal state verified:
YES

historical DB identity preserved:
YES

Human Master preserved:
YES

employee_device_mappings:
0

production ID policy defined:
YES

legacy test IDs retired from reuse:
YES

controlled enrollment workflow defined:
YES

fingerprint enrollment location:
PHYSICAL TERMINAL

automatic Human mapping:
PROHIBITED

sequential Excel mapping:
PROHIBITED

roster lifecycle blocker:
YES (automatic lifecycle detection NOT IMPLEMENTED — required before enrollment)

pilot required:
YES

HumanDeviceMapping WRITE:
NOT AUTHORIZED

Native ADMS Push:
NOT AUTHORIZED

next authorized PromptID:
ADMS-Data-DeviceUserLifecycle-002 (WRITE — implement roster lifecycle detection)

safe to proceed:
YES (to lifecycle implementation with owner approval)

blockers:
Roster lifecycle detection NOT IMPLEMENTED — must be implemented before production enrollment

STOP.
```