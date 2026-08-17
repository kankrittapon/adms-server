# ADMS-Frontend-F4-AdminMappingReconciliation-001 — Admin Mapping + Reconciliation Views

**Status:** COMPLETE — F4 ADMIN VIEWS LIVE, WRITES STAY GATED
**Date:** 2026-08-13
**Owner gate:** F3 gate → owner selected **F4 — Mapping/admin + reconciliation UI** (approved as planned: mapping-creation UI via the existing gated ADMIN POST + read-only reconciliation diagnostics)

---

## 1. Goal

Give ADMIN the two remaining operational views without weakening identity rules:

1. **VERIFIED mapping creation UI** — the only path to a VERIFIED temporal
   identity, driven from READY_FOR_MAPPING enrollment evidence.
2. **Reconciliation diagnostics** — unattributed attendance with canonical
   resolver reasoning. **Read-only by design**: no attribution write endpoint
   exists; identity authority stays with VERIFIED temporal mappings.

## 2. Backend changes (read-only additions)

- `GET /api/v1/mappings/eligibility` (**ADMIN role**): READY_FOR_MAPPING
  enrollments joined with device-user + controlled-scan attendance evidence
  (employee name, terminal id, pk, controlled scan time, attendance id).
  Excludes enrollments whose device user already carries an overlapping
  VERIFIED mapping (mirrors `create_verified_mapping` step 5) — a duplicate
  mapping can never be proposed. Registered before `/mappings/{mapping_id}`
  to avoid FastAPI path shadowing.
- `GET /api/v1/attendance/unattributed` (**ADMIN role**, paginated):
  unattributed rows (`employee_id` NULL) with per-row reasoning computed from
  the canonical temporal resolver (`resolve_verified_employee_mapping`):
  `NO_DEVICE_USER` / `LEGACY_USER` (terminal ids 1/2) / `NO_MAPPING` /
  `BEFORE_VALID_FROM` / `INSIDE_INTERVAL` / `AFTER_VALID_TO`.
- No schema change, no new write routes, no DELETE, no biometric data.

## 3. Frontend changes

- `src/api/client.ts` / `types.ts`: `mappingEligibility`, `createMapping`
  (POST /api/v1/mappings), `unattributedAttendance`; typed models.
- `src/pages/Mappings.tsx`: ADMIN-only **"Create VERIFIED mapping"** panel —
  picks an eligible enrollment, shows its controlled-scan evidence, verified_by
  (defaults to current operator) + note, confirm dialog, then POSTs. 403
  WRITE_DISABLED → amber banner; 409 MAPPING_CONFLICT surfaced. "No eligible
  enrollments" empty state.
- `src/pages/Attendance.tsx`: ADMIN-only **"Reconciliation diagnostics"**
  section — unattributed rows with classification badges + resolver detail.

## 4. Tests

- 5 new API tests (`TestMappingEligibility`, `TestUnattributedAttendance`):
  role gate (403 for non-ADMIN), items/empty, pagination, reasoning payload.
- **Full suite: 348 passed + 18 subtests / 0 failed** (baseline 343 + 18).
- Frontend: `tsc --noEmit` + `vite build` PASS (47 modules).

## 5. Deployment (ai-brain)

- Commit `a8b6abf` pushed; ai-brain `git pull --ff-only` → `a8b6abf`.
- `adms_api` rebuilt only; all other containers untouched. `/healthz` OK.

## 6. Live verification (temp admin token, revoked after)

- **eligibility → 200, count=0** — correct: the pilot enrollment (#1) is
  excluded because device_user_pk 7 already has the open-ended VERIFIED
  mapping 1 (duplicate-mapping guard verified live).
- **unattributed → 200, total=7** — all seven legacy rows classified
  `LEGACY_USER` ("legacy test device user 1/2 — never attributed").
- **Write guard**: `POST /api/v1/mappings` → **403 WRITE_DISABLED** even as
  ADMIN (production stays read-only).
- Reads (`/api/v1/mappings`) → 200. Token revoked → 401 on reuse; **0 active
  tokens** remain for operator 1.

## 7. Browser verification (headless Chrome + CDP)

- Mappings page (ADMIN): panel header, "No eligible enrollments" empty state,
  existing VERIFIED mapping 1 and pilot Human rendered.
- Attendance page (ADMIN): reconciliation section with the 7 `LEGACY_USER`
  rows and the valid_from identity rule. Console clean.
- (One check-string artifact in the harness — the section copy says "no row is
  ever modified here" while the check looked for "never modified"; section
  rendering itself confirmed by header + rows + rule.)

## 8. Safety / regression

- No mapping created, no attendance modified, no User created, device
  untouched. Human Master / mapping 1 / scope / attendance counts unchanged.
- Backend Foundation **REMAINS 100% COMPLETE**. Reconciliation is diagnostics
  only — any future explicit attribution write would be a separate
  owner-authorized decision with its own evidence contract.
- No secrets; parameterized SQL; LAN-only bind unchanged.

## 9. Commits

- `a8b6abf` — feat: F4 admin mapping + reconciliation views
  (# ADMS-Frontend-F4-AdminMappingReconciliation-001)

## 10. Next

- **Enable write UX** for a real enrollment + mapping session
  (`API_WRITE_ENABLED=true`; admin/operator login) — runbooks in F3/F4 reports.
- Optional: realtime SSE bridge, openapi-typescript codegen, F5 hardening
  (production CORS origin, rate limiting, audit log viewer).
