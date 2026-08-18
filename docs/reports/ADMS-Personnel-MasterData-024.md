# ADMS-Personnel-MasterData-024 — IMPLEMENTATION REPORT

**Status:** Implementation complete, tested, committed, pushed, and **DEPLOYED** (owner-approved, gate A). `adms_api`/`adms_web` rebuilt and recreated at commit `df6f347`; all 5 containers healthy post-deploy. See §25a for the deployment record.

> **SUPERSEDED NOTICE (`ADMS-PersonnelIdentity-AttendanceClosure-025`)**: §9 (CSV import design) and §14 below described `personnel_id` as the CSV matching key and required it on every import row — an owner-corrected mistake. `personnel_id` is, and was always meant to be, a fully optional business field, never a required identity. As of 025, CSV round-trip matching uses `employee_id` (the system's own canonical UUID) instead; `personnel_id` is never required and never used for matching. See [ADMS-PersonnelIdentity-AttendanceClosure-025.md](ADMS-PersonnelIdentity-AttendanceClosure-025.md) for the corrected design — that report is now authoritative for CSV identity semantics.

---

## 1. Existing source-of-truth finding

`app/rtn_ranks.py` (`RTN_RANK_CATALOG`, `normalize_rtn_rank()`, `all_canonical_ranks()`) is confirmed as the sole canonical rank source. It is not duplicated anywhere in the frontend; the new `RankSelect.tsx` component fetches ranks from `GET /api/v1/reference/ranks` at runtime rather than hardcoding a list.

## 2. Editable-vs-imported field policy

New Human records created through the UI are tagged `source = ADMS_MANUAL`, distinct from the legacy `EXCEL_IMPORT` provenance tag, so the two origins remain distinguishable in the data forever. Editable fields (create and edit) are whitelisted in `app/personnel.py::_EDITABLE_HUMAN_FIELDS`: `display_name`, `english_name`, `rank`, `position`, `branch`, `category`, `personnel_id`. `employee_id`, `active`, `production_scope`, and all lifecycle/device-linkage fields are never editable through this route — `active` continues to be managed exclusively by the existing `ADMS-Personnel-Lifecycle-019` deactivate/reactivate flow.

## 3. Stable identity key

`human_employees.personnel_id` already carries a `UNIQUE` constraint (`human_employees_personnel_id_key`) from a prior migration — confirmed via `\d human_employees` before writing any code. This is used as the sole matching key for CSV import; no migration was required for 024.

## 4. Add/edit implementation

`app/personnel.py`: `create_human()` (validates operator + display_name + rank, checks `personnel_id` uniqueness, audits `PERSONNEL_CREATED`) and `update_human()` (whitelist-validated PATCH, uniqueness check excluding self, audits `PERSONNEL_UPDATED` with a `changed_fields` diff, no-op edits emit no audit event). Both are exposed via `POST /api/v1/humans` and `PATCH /api/v1/humans/{employee_id}` (ADMIN + write-session gated). Frontend: `PersonnelFormModal.tsx` (shared create/edit form), wired into `Personnel.tsx`'s list view (Add) and detail view (Edit), both gated on the `canManagePersonnel` capability.

## 5. Rank dropdown

`RankSelect.tsx` — reusable `<select>` sourced from `GET /api/v1/reference/ranks`, storing the canonical Thai abbreviation as the field value. Server-side, `_validate_rank()` rejects any value not present in `RTN_RANK_CATALOG` (empty/`None` is allowed).

## 6. English-name edit

Retained and generalized: `english_name` is one of the whitelisted editable fields on both create and edit, validated identically to the other name fields (non-destructive, free text).

## 7. Terminal-name preview

`PersonnelFormModal.tsx` reuses the existing canonical `computeTerminalNamePreview()` helper (`frontend/src/lib/terminalName.ts`) — not reimplemented — to show what the terminal display name would look like given the selected rank and names, with a hint (`englishNameRequiredForTerminalHint`) when the English name is still missing.

## 8. CSV export design

`app/personnel_csv.py::export_humans_csv()` — read-only, never write-session gated, optional `active` filter, UTF-8 BOM-prefixed for Excel-on-Windows Thai-text compatibility. Never exports `employee_id`, tokens, or any device/terminal identifier. Exposed as `GET /api/v1/humans/export.csv`, available to VIEWER and above.

## 9. CSV import design

Strict two-phase flow, no server-side session state:
- **Preview** (`POST /api/v1/humans/import/preview`, ADMIN, **not** write-session gated — pure read): `classify_csv_rows()` parses the file and classifies every row NEW / UPDATE / UNCHANGED / ERROR, diffing against the current DB state. Contains no INSERT/UPDATE/DELETE anywhere (verified by a dedicated test).
- **Commit** (`POST /api/v1/humans/import/commit`, ADMIN + write-session gated): re-uploads and re-classifies the *same* file server-side — it never trusts a stale client-held preview result — then writes only the NEW and UPDATE rows in one transaction. UNCHANGED and ERROR rows are always skipped.

Matching is performed solely by `personnel_id`; per the explicit instruction, name-based matching was never implemented, even as a fallback.

## 10. Duplicate prevention

`personnel_id` collisions on create/edit return `409 PERSONNEL_DUPLICATE` (a new error code) rather than a raw DB constraint violation; the frontend shows friendly Thai copy (`duplicatePersonnelIdBody`). Within a single CSV file, a duplicate `personnel_id` across rows is reported as a per-row `ERROR` classification during preview, never silently merged.

## 11. Audit behavior

`PERSONNEL_CREATED`, `PERSONNEL_UPDATED` (only emitted when a field actually changed, with the changed-field list), and `PERSONNEL_CSV_IMPORT` (counts only — created/updated/unchanged/error — never raw CSV content, verified by test) are appended to the existing `sync_events` audit trail.

## 12. RBAC / write-session policy

| Endpoint | Role | Write-session gated |
|---|---|---|
| `POST /humans`, `PATCH /humans/{id}` | ADMIN | Yes |
| `GET /humans/export.csv` | VIEWER+ | No (read-only) |
| `GET /humans/import/template.csv` | ADMIN | No (read-only) |
| `POST /humans/import/preview` | ADMIN | No (read-only) |
| `POST /humans/import/commit` | ADMIN | Yes |

Verified end-to-end via `TestPersonnelMasterDataRBAC` (10 `TestClient` tests): non-admin roles get 403 on create/commit, write-disabled/closed-session blocks create and commit, preview is confirmed to bypass the write-session gate, and export is confirmed available to VIEWER/OPERATOR/ADMIN.

## 13. Enrollment handoff

On successful create, `PersonnelFormModal` shows an internal Thai success screen (`createSuccessTitle`) with a `[ลงทะเบียนเครื่องสแกน]` button that navigates to `/enrollments` — a UX handoff only; no enrollment record is created automatically, and no terminal/device write occurs as part of Personnel creation.

## 14. Production data-quality audit (read-only, Phase 16)

Query run against production `human_employees` (120 rows):
- `personnel_id` populated: **0 / 120**
- `source`: 100% `EXCEL_IMPORT` (1 distinct source)
- `english_name` missing: 119 / 120
- `rank` missing: 0 / 120
- Duplicate `display_name` values: 0

**Consequence, disclosed as a limitation, not silently worked around:** because no existing production Human has a `personnel_id`, CSV import can create new rows immediately but **cannot match/update any of the 120 existing legacy rows** until an ADMIN manually assigns each one a `personnel_id` via Edit first. This is documented in `app/personnel_csv.py`'s module docstring and in this report, per the explicit instruction to stop and report rather than invent name-based matching.

## 15. Tests

44 new tests in `tests/test_personnel_master_data.py` (create, update, CSV export, CSV import preview, CSV import commit, RBAC/write-session matrix — all using fakes/mocks, no real DB or terminal I/O), plus fixes to 2 pre-existing tests (`test_api_auth.py`, `test_rank_source_of_truth.py`) whose assumptions were superseded by this PromptID's scope change. Full suite: **800 passed, 0 failed**.

## 16. OpenAPI / tsc / build

- OpenAPI snapshot regenerated (`frontend/openapi.json`, 52 paths / 69 schemas) and `frontend/src/api/generated.ts` regenerated; `tests/test_openapi_contract.py` passes (drift guard).
- `npx tsc --noEmit` — **PASS**, 0 errors.
- `npm run build` (`vite build`) — **PASS**.

## 17. Migration required

**No.** `personnel_id` already carried the needed `UNIQUE` constraint from a prior migration; no schema change was necessary for this PromptID.

## 18. Changed files

Backend: `app/personnel.py`, `app/personnel_csv.py` (new), `app/api/schemas.py`, `app/api/routers/humans.py`, `app/requirements-api.txt`.
Tests: `tests/test_personnel_master_data.py` (new), `tests/test_api_auth.py`, `tests/test_rank_source_of_truth.py`.
Frontend: `frontend/src/components/RankSelect.tsx` (new), `frontend/src/components/PersonnelFormModal.tsx` (new), `frontend/src/components/CsvImportModal.tsx` (new), `frontend/src/pages/Personnel.tsx`, `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/i18n/types.ts`, `frontend/src/i18n/en.ts`, `frontend/src/i18n/th.ts`, `frontend/openapi.json`, `frontend/src/api/generated.ts`.
Docs: `docs/API_CONTRACT.md`, `docs/SECURITY_RBAC.md`, `STATUS.md`, `README.md`, `docs/reports/README.md`, this report.

## 19. Commit hash

See `git log -1` after the commit made immediately following this report (commit created and pushed per the PromptID's standing "commit and push allowed" permission).

## 20. Production mutations performed during implementation

**Zero.** No real Personnel record was created or edited, no real CSV was imported, and no Enrollment/Terminal Management/Mapping/DeviceOwner/Attendance logic was touched. All 44 new tests use fakes/mocks; the Phase 16 data-quality audit was strictly read-only (`SELECT` queries only).

## 21. Enrollment/Terminal Management/Mapping/DeviceOwner/Attendance scope

Confirmed untouched — this PromptID's backend functions (`create_human`, `update_human`, `classify_csv_rows`, `commit_csv_rows`) never reference `attendance_logs`, `employee_device_mappings`, `device_user_enrollments`, or `device_users` tables (verified by dedicated tests).

## 22. Elderly/non-technical Thai UX

All new UI text is in Thai by default (via the i18n system), with plain-language labels (e.g., "หมายเลขประจำตัว" not "personnel_id"), a single obvious primary action per screen (Add/Edit/Export/Import buttons), and friendly translated error copy for every backend error code encountered (`PERSONNEL_DUPLICATE`, `CSV_MALFORMED`, `WRITE_DISABLED`/`WRITE_SESSION_REQUIRED`/`WRITE_SESSION_EXPIRED`) — no raw backend/Python exception text or raw error codes are ever shown to the operator.

## 23. Internal ID exposure

No UUID, `device_user_pk`, `account_incarnation`, or raw lifecycle enum is exposed in any new operator-facing screen; all new components operate purely on `display_name`, `english_name`, `rank`, `personnel_id`, `branch`, `category`.

## 24. Remaining limitations

- CSV import cannot update the 120 pre-existing legacy Human rows until an ADMIN backfills each one's `personnel_id` via the new Edit form first (§14) — by design, not a defect.
- "Delete Human" was explicitly out of scope and was not implemented.
- No bulk-edit or bulk-deactivate UI was added; deactivate/reactivate remains the single-record flow from `ADMS-Personnel-Lifecycle-019`.

## 25. Owner deployment gate

Owner selected **A. APPROVE PRODUCTION DEPLOYMENT**.

## 25a. Deployment record

- `docker compose build api web` — both images built successfully from commit `df6f347` (includes `python-multipart==0.0.20`, all new backend modules, and the frontend bundle with the verified `tsc`/`vite build` output).
- `docker compose up -d --no-deps api web` — `adms_api` and `adms_web` recreated; `adms_zkteco_listener`, `adms_postgres`, `adms_mqtt` were **not** touched (`--no-deps`, confirmed unchanged container start times/restart counts).
- Post-deploy: all 5 containers report `Up ... (healthy)`.
- `GET /healthz` → `{"status":"ok"}`.
- Live `GET /openapi.json` confirms the new routes are present: `/api/v1/humans/export.csv`, `/api/v1/humans/import/preview`, `/api/v1/humans/import/commit`, `/api/v1/humans/import/template.csv`.
- Served frontend bundle hash (`assets/index-CSXO_O6g.js`) matches the locally-built and verified bundle exactly — confirms the deployed console is running the exact code that passed `tsc --noEmit` and `vite build`.
- No real Personnel record was created/edited and no real CSV was imported during deployment verification — all checks were read-only (`/healthz`, `/openapi.json`, served-asset comparison).

STOP.
