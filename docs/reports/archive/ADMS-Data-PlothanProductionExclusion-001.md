# ADMS — พลทหาร PRODUCTION SCOPE EXCLUSION REPORT

**PromptID:** `ADMS-Data-PlothanProductionExclusion-001`
**Mode:** WRITE — reversible production-scope exclusion (no destructive deletion)
**Parent gate:** owner selected **C (Both, sequentially)** at ADMS-Data-HumanDeviceMapping-004
**Status:** **PASS**
**Date:** 2026-08-12

---

## 1. Design (presented before execution, owner-approved at gate)

**Mechanism:** additive `production_scope BOOLEAN NOT NULL DEFAULT true` column
on `human_employees` (migration `sql/007_plothan_production_scope.sql`), with
the deterministic พลทหาร population flipped to `false`.

**Hard requirements honoured:**
- NO DELETE of Human Master rows ✅
- employee_id UUIDs preserved ✅
- `human_employee_sources` provenance preserved ✅
- historical attendance preserved ✅
- mapping evidence preserved ✅
- พลทหาร excluded from future production enrollment ✅ (enforced in
  `reserve_next_device_user_id()` via `production_scope = true`)
- existing non-พลทหาร unaffected ✅ (verified 0 collateral)
- rollback path documented ✅
  `UPDATE human_employees SET production_scope = true WHERE category = 'พลทหาร';`

**Alternatives considered (rejected):** archival state via `active=false`
(conflates personnel status with scope), enrollment-eligibility flag
(redundant with scope flag), filtered view (no enforcement at write path).

## 2. Pre-Write Evidence

36 พลทหาร records confirmed live before mutation (rank `พลฯ` / category
`พลทหาร`).

## 3. Pre-Write Backup (verified)

`backups/adms_pre_plothan_excl_20260812_192842.dump` — 54,340 B · SHA256
`5835be84a3bfbc1e422f0702e68252fed25749c8ace84ac4f04b117ac65b5764` ·
`pg_restore -l` PASS (RC=0, 104 TOC).

## 4. Migration 007 (transactional, applied on ai-brain)

```sql
BEGIN;
ALTER TABLE human_employees
  ADD COLUMN IF NOT EXISTS production_scope BOOLEAN NOT NULL DEFAULT true;
UPDATE human_employees SET production_scope = false
  WHERE production_scope = true
    AND (rank IN ('พลฯ','พลทหาร','พลทหารกองประจำการ','พล.ทหาร')
         OR category = 'พลทหาร');
COMMIT;
```

MIG_RC=0. Re-run (idempotency check) MIG_RE_RUN_RC=0, count stable.

## 5. Post-Write Verification (live)

| Check | Result |
|-------|--------|
| production_scope = false | **36** ✅ |
| production_scope = true | 84 ✅ |
| flagged rows are พลทหาร | 36 ✅ |
| non-พลทหาร flagged | **0** ✅ |
| human_employees total | 120 (no deletion) ✅ |
| human_employee_sources | 120 ✅ |
| VERIFIED mappings | 1 (intact) ✅ |
| attendance total / id 12 | 8 / attributed to pilot Human ✅ |
| pilot Human production_scope | `t` (eligible) ✅ |
| migration idempotent | YES ✅ |

## 6. Deployment

`feat: add reversible plothan production-scope exclusion` (`04ba478`) —
listener rebuilt (enforcement live), HEALTHY, restarts 0, HC_RC=0, modules OK.
PostgreSQL/MQTT untouched. Unrelated ai-brain workloads untouched.

## 7. Post-Write Backup (verified)

`backups/adms_post_plothan_excl_20260812_192923.dump` — 54,798 B · SHA256
`fe8310d842f22b42df014ebfd85bf6d5c0087a9a559da3319b07f6a4e375505c` ·
`pg_restore -l` PASS (RC=0, **105 TOC** — new column).

## 8. Tests

Full suite **213/213 PASS** (+2 new: reservation SQL requires
`production_scope = true`; excluded Human rejected with "production scope").

## 9. Final

| Item | Value |
|------|-------|
| พลทหาร production-excluded | **36** (reversible flag) |
| Human Master rows deleted | **0** |
| UUIDs changed | 0 |
| provenance rows affected | 0 |
| rollback | documented (single UPDATE) |
| schema change | additive migration 007 only |

**STOP.**
