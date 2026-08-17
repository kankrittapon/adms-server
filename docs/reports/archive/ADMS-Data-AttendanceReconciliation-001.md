# ADMS — DETERMINISTIC ATTENDANCE RECONCILIATION REPORT

**PromptID:** `ADMS-Data-AttendanceReconciliation-001`
**Mode:** WRITE — deterministic reconciliation of the controlled-scan event only
**Parent gate:** owner selected **C (Both, sequentially)** at ADMS-Data-HumanDeviceMapping-004
**Status:** **PASS**
**Date:** 2026-08-12

---

## 1. Authorization

Owner selected option C at the HumanDeviceMapping-004 SUBMIT gate, authorizing
attendance reconciliation FIRST, then พลทหาร production exclusion. This
sub-phase executes A. Scope is strictly limited to attendance events that can
be deterministically attributed via the VERIFIED temporal mapping
(mapping_id 1). No fuzzy/name/rank/timestamp-proximity matching.

## 2. Exact Proposed Mutation (presented before execution)

| Field | Value |
|-------|-------|
| Table | `attendance_logs` |
| Row | **id 12** (the controlled-scan event) |
| user_id / device_user_pk | 1001 / 7 |
| scan_time | 2026-08-12 08:47:37+00 |
| current employee_id | NULL |
| target employee_id | `039c4486-b30f-4ce1-b780-783cd268858d` |
| proof scan_time inside interval | scan_time == valid_from, inside VERIFIED `[2026-08-12 08:47:37+00, NULL)` |
| proof exactly one mapping resolves | resolver at scan_time → the pilot Human; ambiguity count = 1 |
| mutation | `UPDATE attendance_logs SET employee_id=… WHERE id=12 AND employee_id IS NULL AND device_user_pk=7;` |

**Explicitly NOT touched:** 7 historical attendance rows (legacy device users
1/2, scan_time before valid_from) — they remain `employee_id = NULL`.

## 3. Pre-Write Backup (verified)

`backups/adms_pre_reconcile_20260812_190956.dump` — 54,267 B · SHA256
`87103a73779acc00abc7ec2afdb422ee9ec0b2d7ddf8f952575e4c832e4d7a61` ·
`pg_restore -l` PASS (RC=0, 104 TOC).

## 4. Execution

Single-row transaction: `BEGIN; UPDATE …; COMMIT;` → `UPDATE 1` /
`RECON_UPDATED=1`. RECON_RC=0.

## 5. Post-Write Verification (live)

| Check | Result |
|-------|--------|
| attendance id 12 | `12\|1001\|7\|2026-08-12 08:47:37+00\|039c4486-b30f-4ce1-b780-783cd268858d` ✅ |
| rows with employee_id | 1 (only id 12) ✅ |
| attendance total | 8 (unchanged) ✅ |
| duplicates | 0 ✅ |
| legacy rows attributed | 0 ✅ |
| raw_payload id 12 | unchanged (`{"uid":1001,"punch":0,"status":1,"user_id":"1001","device_ip":"192.168.1.201","timestamp":"2026-08-12T15:47:37+07:00"}`) ✅ |
| resolver at valid_from | pilot Human ✅ |
| resolver before valid_from | None ✅ |
| resolver legacy pk 2 | None ✅ |

## 6. Post-Write Backup (verified)

`backups/adms_post_reconcile_20260812_191849.dump` — 54,317 B · SHA256
`4ccde67c75be201619439f5defe329d0bea49a3ad579e458e5433db62e329a41` ·
`pg_restore -l` PASS (RC=0, 104 TOC).

## 7. Tests / Runtime

Full suite **213/213 PASS** (run at sub-phase B; this sub-phase added no code).
Runtime unaffected (no rebuild required; no attendance-side code change).

## 8. Final

| Item | Value |
|------|-------|
| attendance reconciled | **1** (id 12) |
| historical attendance reconciled | 0 |
| raw_payload modified | NO |
| duplicates created | 0 |
| VERIFIED mappings | 1 (unchanged) |
| next sub-phase | `ADMS-Data-PlothanProductionExclusion-001` (owner-selected C) |

**STOP.**
