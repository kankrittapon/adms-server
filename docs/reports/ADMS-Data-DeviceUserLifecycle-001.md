# DEVICE USER LIFECYCLE & ACCOUNT INCARNATION AUDIT REPORT

**PromptID:** `ADMS-Data-DeviceUserLifecycle-001`  
**Mode:** READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY  
**Date:** 2026-08-11  

---

## 1. Executive Summary & Prompt Identity

This report documents the findings of the **Device User Lifecycle / Account Incarnation Audit** (`ADMS-Data-DeviceUserLifecycle-001`).

The goal of this audit was to resolve architectural uncertainty surrounding how `device_users` and the ADMS Collector ingest, track, and manage physical terminal accounts on ZKTeco terminals—specifically evaluating the risk of terminal `user_id` deletion and recycling over time.

---

## 2. Repository & Live Database Baseline Verification

### Git Baseline
- **Branch:** `main`
- **Local HEAD:** `977afadc7b3738eeae3e0186cfb47b467d0ad985`
- **origin/main:** `977afadc7b3738eeae3e0186cfb47b467d0ad985`
- **Working Tree Clean:** `YES`
- **Checkpoint Commit Lineage Verified:**
  - `a7b2cb1` (`ADMS-Checkpoint-PostExcelImport-001`)
  - `6d21700` (`ADMS-Data-HumanDeviceMapping-001`)
  - `977afad` (`ADMS-Data-HumanDeviceMappingSchema-001`)

### Schema & Live Inventory
- `devices`: 1 record (`SONIC ZEM560 #1`, serial `3392113170057`)
- `device_users`: 2 records (`user_id = '1'`, `user_id = '2'`)
- `employee_device_mappings`: 0 rows
- `human_employees`: 120 rows
- `attendance_logs`: 6 rows
- **Repository DDL / Live Schema Drift:** `NO`

---

## 3. Live `device_users` Schema Definition

Exact PostgreSQL table structure for `device_users`:
- `device_user_pk`: `BIGINT` Primary Key (`BIGSERIAL`)
- `device_id`: `BIGINT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE`
- `device_user_id`: `TEXT NOT NULL`
- `device_uid`: `INT NULL`
- `device_display_name`: `TEXT NULL`
- `privilege`: `INT NOT NULL DEFAULT 0`
- `active`: `BOOLEAN NOT NULL DEFAULT true`
- `first_seen_at`: `TIMESTAMPTZ NOT NULL DEFAULT now()`
- `last_seen_at`: `TIMESTAMPTZ NOT NULL DEFAULT now()`
- `created_at`: `TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at`: `TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Unique Constraints:** `UNIQUE (device_id, device_user_id)`
- **Explicit Incarnation Key:** `NO` (Table lacks `generation` or `incarnation_key` columns).

---

## 4. Semantics of `ensure_device_user()`

Code location: [app/db.py](file:///D:/Dev/adms-server/app/db.py#L61-L80)

1. **Function Name:** `ensure_device_user(cur, device_id, device_user_id, display_name=None)`
2. **Lookup & Conflict Key:** `(device_id, device_user_id)`
3. **INSERT Behavior:** Inserts `(device_id, device_user_id, device_display_name, last_seen_at=now())`.
4. **ON CONFLICT Target:** `(device_id, device_user_id)`
5. **UPDATE Behavior:** `DO UPDATE SET last_seen_at = now()`
6. **`device_uid` Participation:** `device_uid` does **NOT** participate in identity lookup or conflict target.
7. **Identity Reuse Verification:** If terminal user `'1'` is deleted and recreated on the terminal LCD, subsequent attendance logs with `user_id = '1'` will hit `ON CONFLICT (device_id, device_user_id)` and return the **exact same `device_user_pk = 1`**.

---

## 5. Device Identity Uniqueness & Terminal Roster Comparison

- **Identity Constraint:** `UNIQUE (device_id, device_user_id)`
- **`device_uid` Constraint:** `device_uid` is NOT unique scoped to device, nor globally unique.
- **Terminal User Roster vs Database:**
  - Database currently stores 2 device user records (`user_id = '1'`, `user_id = '2'`).
  - Terminal roster contains matching accounts `user_id = '1'` and `user_id = '2'`.
- **`user_id` vs `uid` Semantics:**
  - `user_id` is a terminal-local string identifier (e.g. `'1'`).
  - `uid` is an internal integer index (e.g. `1`).
  - Both `user_id` and `uid` can be deleted and recycled by terminal operators.

---

## 6. Collector Roster Sync & Attendance Discovery Behavior

- **Automatic Roster Sync:** `NO` (Production Collector in `app/collector.py` does NOT execute `get_users()` during startup or periodic loops; attendance logs are the sole discovery trigger).
- **Disappearance Detection:** `NO` (Current Collector cannot detect when a user is removed from terminal LCD roster).
- **Reappearance / UID Change Detection:** `NO` (Reappearance or UID change updates `last_seen_at` on existing row silently).

---

## 7. Account Incarnation & UID Continuity Analysis

### Continuity Matrix
| Scenario | Technical Signal | Risk / Interpretation | Recommended Action |
| -------- | ---------------- | --------------------- | ------------------ |
| **Case A:** Same `user_id`, same `UID` | Continuous account | Normal ongoing activity | Retain active temporal mapping |
| **Case B:** Same `user_id`, different `UID` | Terminal account recreated | Slot reassigned on terminal | Flag account recreation, close old `valid_to`, require re-verification |
| **Case C:** Different `user_id`, same `UID` | Terminal roster restructure | Internal index reused | Rely on `device_user_id` separation |
| **Case D:** `UID` unavailable (`NULL`) | Ingestion via attendance | Standard backfill behavior | Normal attendance ingestion |

---

## 8. Evaluated Lifecycle Metadata & Incarnation Options

### Decision Gate Result: **Decision B — Add Device User Lifecycle Fields to Migration `005`**

- **Option A (Current model only):** Rejected (Insufficient lifecycle visibility).
- **Option B (Add modest lifecycle fields to `device_users` in Migration `005`):** **SELECTED**. Adding `roster_last_seen_at` and `inactive_at` to `device_users` closes the visibility gap cleanly without structural overkill.
- **Option C (Separate `device_user_incarnations` table):** Rejected (Over-engineered for current scope).
- **Option D (Temporal mapping only):** Rejected (Leaves `device_users` without status flags).

### Proposed DDL additions for Migration `005`:
```sql
ALTER TABLE device_users
  ADD COLUMN IF NOT EXISTS roster_last_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS inactive_at TIMESTAMPTZ;
```

---

## 9. Verification Audit & Overlap Enforcement Re-check

- **`verification_note` Requirement:** Recommended as **NULLABLE / OPTIONAL** (`verification_note TEXT NULL`). Forcing operators to enter mandatory text creates friction and filler data.
- **Historical Overlap Protection:** Retain PostgreSQL Partial Unique Index (`idx_active_verified_device_user`), combined with application-level interval checks for historical records.
- **`btree_gist` Extension:**
  - `btree_gist` installed: `NO`
  - `btree_gist` recommended now: `NO` (Avoid adding unnecessary PostgreSQL extension dependencies).

---

## 10. Direct Impact on Collector & Backfill Modules

- **Ingestion Query (`resolve_verified_employee_mapping`):** Update parameter signature in `app/db.py` to accept `scan_time`:
  ```python
  def resolve_verified_employee_mapping(cur: Any, device_user_pk: int, scan_time: datetime) -> Optional[str]:
      ...
  ```
- **Historical Backfill (`save_attendance_batch`):** Pass each record's `scan_time` to temporal resolver during batch persistence.

---

## 11. Final Checklist & Safe Verification Assertions

- Database modified: **NO**
- Schema modified: **NO**
- Application modified: **NO**
- Device modified: **NO**
- Terminal users modified: **NO**
- Fingerprints read/written: **NO**
- Mapping rows created: **0**
- Native ADMS Push authorized: **NO**
- Documentation updated: **YES** ([HUMAN_DEVICE_MAPPING_SCHEMA.md](file:///D:/Dev/adms-server/docs/data/HUMAN_DEVICE_MAPPING_SCHEMA.md))
- Report persisted: **YES** ([ADMS-Data-DeviceUserLifecycle-001.md](file:///D:/Dev/adms-server/docs/reports/ADMS-Data-DeviceUserLifecycle-001.md))
- STATUS.md updated: **YES** ([STATUS.md](file:///D:/Dev/adms-server/STATUS.md))

---

## 12. Decision & Next Steps

- **Selected Decision Gate:** **Decision B — Add Device User Lifecycle Fields to Migration 005**
- **Next Authorized PromptID:** `ADMS-Data-HumanDeviceMappingSchema-002` (WRITE mode — pending explicit user authorization)
- **Safe to proceed to Mapping Schema Execution (`002`):** `YES`
- **Safe to proceed directly to Mapping WRITE:** `NO`
