# Canonical Architecture: Device User Lifecycle & Account Incarnation Audit

**PromptID:** `ADMS-Data-DeviceUserLifecycle-001`  
**Status:** READ-ONLY VERIFIED ANALYSIS COMPLETE / PLAN ONLY  

---

## 1. Executive Summary & Audit Context

Following the initial schema design in `ADMS-Data-HumanDeviceMappingSchema-001`, this audit evaluates the exact lifecycle mechanics of ZKTeco terminal users (`device_users`) and how account recycling (deletion and recreation of terminal `user_id` values) affects identity continuity and historical attendance attribution.

### Core Audit Questions & Findings

1. **Identity Key in `ensure_device_user()`:** Lookup key is `(device_id, device_user_id)`.
2. **Account Recycling Identity Reuse:** If terminal user `'1'` is deleted and recreated on the physical device, `ensure_device_user()` will reuse the exact same existing `device_user_pk` row.
3. **`device_uid` Storage & Uniqueness:** `device_uid` (`INT`) is present in the schema but **does NOT participate** in any uniqueness constraint (`UNIQUE (device_id, device_user_id)`). It is `NULL` for attendance-discovered records.
4. **Roster Synchronization Status:** Automatic roster sync (`get_users()`) is **NOT implemented** in production Collector (`app/collector.py`). Ingestion relies strictly on attendance log events (`get_attendance()` backfill & `live_capture()`).
5. **Disappearance / Reappearance / UID Change Detection:** Current runtime **cannot detect** account disappearance, account recreation, or `device_uid` changes.
6. **Temporal Human Mapping Sufficiency:** Temporal Human mapping (`[valid_from, valid_to)`) is **CONDITIONAL**. It is sufficient *if and only if* administrative workflows explicitly record accurate ownership boundaries (`valid_from`/`valid_to`) when account reassignments occur. However, adding lifecycle metadata to `device_users` significantly strengthens automated safeguards against silent misattribution.

---

## 2. Technical Semantics of `device_users` and Ingestion

```text
+-------------------------------------------------------------------------+
|                       ZKTeco Physical Terminal                          |
|  Local Slot: user_id (string "1") <---> internal index: uid (integer 1) |
+-------------------------------------------------------------------------+
                                     │
           Ingestion via pyzk (Attendance Events / Logs)
                                     ▼
+-------------------------------------------------------------------------+
|                    app/db.py :: ensure_device_user()                    |
|  INSERT INTO device_users (device_id, device_user_id, last_seen_at)     |
|  ON CONFLICT (device_id, device_user_id) DO UPDATE SET last_seen_at=now()|
|  RETURNING device_user_pk;                                              |
+-------------------------------------------------------------------------+
                                     │
                   Reuses exact same device_user_pk!
                                     ▼
+-------------------------------------------------------------------------+
|                      PostgreSQL: device_users                           |
|  device_user_pk = 1  | device_id = 1 | device_user_id = '1'             |
|  device_uid = NULL   | display_name = 'Device User 1'                   |
+-------------------------------------------------------------------------+
```

### Key Semantics of `ensure_device_user()`
- **Input:** `(cur, device_id, device_user_id, display_name)`
- **Conflict Target:** `(device_id, device_user_id)`
- **On Conflict Action:** `DO UPDATE SET last_seen_at = now()`
- **Identity Reuse:** If user `'1'` is deleted and recreated on the terminal LCD, any new attendance log containing `user_id = '1'` will resolve to the existing `device_user_pk` row without creating a new incarnation key or raising an alert.

---

## 3. ZKTeco Identifier Mechanics: `user_id` vs `uid`

- **`user_id` (String):** The primary user identifier displayed on the LCD and printed on badges (e.g., `'1'`, `'1002'`). Handled as a string across the codebase.
- **`uid` (Integer):** Terminal internal slot index assigned sequentially by ZKTeco firmware (e.g., `1`, `2`).
- **Recycling Behavior:** 
  - Both `user_id` and `uid` can be deleted and reused on ZKTeco standalone terminals.
  - When account `'1'` (with `uid = 1`) is deleted and a new user `'1'` is enrolled later, firmware may assign a new `uid` (e.g., `uid = 5`).
  - **Continuity Signal:** A change in `device_uid` for the same `device_user_id` is a strong technical signal of account recreation/reassignment.

---

## 4. Roster Sync & Lifecycle Metadata Evaluation

### Current Capability
- `get_users()` is supported by `pyzk` but **only executed during manual inspection/tests**.
- `app/collector.py` does NOT run periodic or startup roster syncs.
- `last_seen_at` in `device_users` is updated only when an attendance log event occurs.

### Evaluated Lifecycle Fields for `device_users`
1. `first_seen_at` (`TIMESTAMPTZ`): **RECOMMENDED NOW** (Tracks initial observation bound).
2. `last_seen_at` (`TIMESTAMPTZ`): **EXISTING / RECOMMENDED** (Tracks latest attendance activity).
3. `roster_last_seen_at` (`TIMESTAMPTZ NULL`): **RECOMMENDED FOR FUTURE ROSTER SYNC** (Tracks latest successful roster snapshot presence).
4. `active` (`BOOLEAN NOT NULL DEFAULT true`): **RECOMMENDED NOW** (Flags whether account is active or missing).
5. `inactive_at` (`TIMESTAMPTZ NULL`): **RECOMMENDED NOW** (Timestamp when marked missing from roster).

---

## 5. Account Incarnation & Decision Gate

### Decision Gate Result: **Decision B — Add Device User Lifecycle Fields to Migration 005**

Rather than creating a complex separate `device_user_incarnations` table (Option C) or relying solely on mapping boundaries without device-side flags (Option A), **Decision B** provides the optimal balance:

1. **Enhance Migration `005` (`sql/005_human_device_mapping_schema.sql`):**
   - Add audit fields to `employee_device_mappings` (`verified_by`, `verification_method`, `verification_note`, `valid_from`, `valid_to`).
   - Add active partial unique index on `employee_device_mappings` (`WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL`).
   - Add basic lifecycle metadata columns to `device_users` (`roster_last_seen_at`, `inactive_at`).
2. **Verification Note Nullability:** `verification_note` is recommended as **NULLABLE / OPTIONAL** to prevent forcing operators to type meaningless filler strings during manual verification.
3. **Historical Overlap Protection:** Retain PostgreSQL Partial Unique Index for active mappings, enforced alongside application-level interval validation (`[valid_from, valid_to)`). `btree_gist` is NOT required.

---

## 6. Implementation & Ingestion Impact Matrix

| Case | Continuity Signal | Lifecycle Action | Mapping Action | Admin Action Required |
| ---- | ----------------- | ---------------- | -------------- | -------------------- |
| **Case 1:** Same `user_id`, same `UID` | High continuity | Update `last_seen_at` | Retain active mapping | None |
| **Case 2:** Same `user_id`, absent from roster | Account missing | Set `active = false`, set `inactive_at` | Auto-close mapping at `inactive_at` (or set `valid_to`) | Flag for administrative review |
| **Case 3:** Same `user_id`, different `UID` | Account recreated | Mark previous row inactive, create new incarnation / flag UID change | Close existing mapping `valid_to = now()` | **REQUIRED:** Re-verify new human owner |
| **Case 4:** Attendance scan for unmapped `user_id` | New terminal user | `ensure_device_user()` inserts slot | Attendance stored with `employee_id = NULL` | **REQUIRED:** Perform controlled test-scan mapping |

---

## 7. Next Execution Phase

The project sequence proceeds to:
```text
ADMS-Data-HumanDeviceMappingSchema-002 (WRITE mode — pending explicit user authorization)
```
Migration script `sql/005_human_device_mapping_schema.sql` will include both mapping table enhancements and device user lifecycle columns.
