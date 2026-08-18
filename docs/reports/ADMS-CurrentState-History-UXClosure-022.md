# ADMS-CurrentState-History-UXClosure-022

**Scope**: separate "what is true now" from "what used to be true" across primary operator-facing pages. Preserve all history; fix presentation and read-side semantics only.

## 1. Dashboard "5 / 1 active" — exact root cause

`app/api/repository.py::dashboard_summary()` already computed both `device_users_total` (`SELECT COUNT(*) FROM device_users`, **5** on real production — every historical row including removed 1002/1004 and two odd legacy rows) and `device_users_active` (`WHERE active`, **1** — only 1001). The backend numbers were correct. The defect was in `frontend/src/pages/Dashboard.tsx`: the StatCard bound `value={data.device_users_total}` (the big headline number) with `hint={data.device_users_active} active` (small secondary text) — exactly backwards from what an operator needs.

## 2. Canonical current terminal-account definition

**Current terminal account** = `device_users.active = true`. This is the same source-of-truth the roster-lifecycle reconciler (`app/db.py::reconcile_roster_lifecycle`) already maintains and Terminal Management already reads from — no second competing truth model introduced. Historical/inactive rows remain in `device_users`, untouched, still queryable.

## 3. Dashboard before/after

Before: primary KPI = `device_users_total` (5), labeled "รายชื่อผู้ใช้ที่ตรวจพบบนเครื่องสแกน" (reads as a historical detection log).
After: primary KPI = `device_users_active` (1), labeled "บัญชีที่อยู่บนเครื่องสแกนขณะนี้" ("accounts on the scanner right now"), with the historical total shown only as small secondary hint text ("5 เคยพบทั้งหมด (รวมที่นำออกแล้ว)").

The identical pattern was found and fixed for the Mappings KPI card on the same page: `mappings_total` (2, includes Pimai's closed #2) was primary; now `mappings_verified_active` (1) is primary, with the historical total as hint.

## 4. Mapping page before/after semantics

Before: a single flat table listed every mapping regardless of `valid_to`, using `StatusBadge(mapping_status)` — a closed, historical `VERIFIED` mapping (Pimai/#2) rendered with the identical green "VERIFIED" badge as a genuinely current one (#1).

After: `app/api/repository.py` adds `_derive_mapping_lifecycle_state(mapping_status, valid_to, device_user_active)` → `CURRENT` / `REMOVED_FROM_TERMINAL` / `ENDED`, reused by both `list_mappings()` and `get_mapping()` (no duplicated CASE logic). `REMOVED_FROM_TERMINAL` is only asserted when `device_users.active = false` proves the account was actually removed — never fabricated; an unproven closure falls back to the neutral `ENDED`. New `Mapping.is_current: bool` / `mapping_lifecycle_state: str` fields expose this canonically via the API. `frontend/src/pages/Mappings.tsx` now renders two visually separated sections: "ผู้ใช้ที่ยืนยันและกำลังใช้งานอยู่" (Current) and "ประวัติการยืนยัน" (History) — filtered purely on `m.is_current`, never reconstructing lifecycle from `valid_to` itself.

## 5. Mapping #1 — expected section/state

**CURRENT** section, badge "กำลังใช้งาน" (Active).

## 6. Mapping #2 — expected section/state

**History** section, badge "นำออกจากเครื่องแล้ว" (Removed from terminal) — provable since `device_users.active=false` for pk=29. Shows started/ended timestamps with Thai labels ("เริ่มใช้งาน"/"สิ้นสุดการใช้งาน"), never a raw blank-vs-filled `valid_to` column for the operator to interpret.

## 7. Personnel / 8. Enrollment / 11. Terminal Management consistency

Reconfirmed only — no regression, no changes needed. 021B's `has_active_terminal_account`/`lifecycle_state` fields and their frontend consumers (Personnel's "no scanner account" card, Enrollment Workspace's Active Queue/History split) are untouched by this PromptID and still behave correctly. Terminal Management already reads only the live physical roster (`TERMINAL_INVENTORY`), which inherently excludes 1004 — no change needed.

## 12. Other pages audited

Dashboard KPI sweep (Phase 7): Personnel count, device count, attendance-today/total, and the new enrollment "needing action" count (021C) were all checked — none mix historical rows into a current-state headline except the two defects fixed above. Navigation badges (STEP/LIVE pills in the sidebar) are static UI chrome, not data-derived counts — no defect. Audit/Security Audit Trail page intentionally shows full history — left untouched, as required.

## 13. Additional semantic defects found

One: the Dashboard Mappings KPI card had the identical primary/hint inversion as the terminal-account KPI (documented above, fixed in the same commit since it's the same defect class discovered mid-audit).

## 14. Tests before/after

704 passing (692 baseline + 12 new: mapping lifecycle derivation unit tests, production-shaped #1/#2 current/history split, dashboard terminal-account KPI production-shaped fixture, no-regression checks for 021B/021C, no-write-side-invocation check). 0 failed.

## 15-17. OpenAPI / tsc / vite

OpenAPI regenerated (new `Mapping.mapping_lifecycle_state`/`is_current` fields), drift guard PASS. `tsc --noEmit` PASS. `vite build` PASS.

## 18. Migration required?

**No.** Both fixes are read-time derivations over existing columns (`device_users.active`, `employee_device_mappings.valid_to`) — no schema change.

## 19-20. Mutation counts

Production mutation count: **0**. Device mutation count: **0**. No write-side function (`create_verified_mapping`, `INSERT`/`UPDATE`/`DELETE`) is invoked by any of this session's changes — confirmed by test.

## 21-22. Changed files / commit

`app/api/repository.py`, `app/api/schemas.py`, `frontend/openapi.json`, `frontend/src/api/generated.ts`, `frontend/src/i18n/{en,th,types}.ts`, `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Mappings.tsx`, `tests/test_api.py`, `tests/test_current_state_history_uxclosure.py` (new). Commit: see git log.

## 23. Remaining known UX inconsistencies

- The Mappings page header badge label ("Verified Identity Mappings" / "รายการที่ยืนยันความถูกต้องแล้ว") is generic enough to remain accurate now that it shows the current count, but doesn't explicitly say "currently" — a minor future polish, not a correctness defect.
- No live-browser click-through performed this session for the Mapping/Dashboard changes specifically (structural/unit tests only); recommend confirming visually before or during the deployment gate, following the same pattern used for prior PromptIDs in this chain.
