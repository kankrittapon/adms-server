# ADMS Current Status

**Deployed at `df6f347`**: `ADMS-Personnel-MasterData-024` — owner-approved (gate A), `adms_api`/`adms_web` rebuilt and recreated, both healthy; `adms_zkteco_listener`/`adms_postgres`/`adms_mqtt` untouched. Live `/openapi.json` confirms the new `/api/v1/humans/{export.csv,import/*}` routes; served frontend bundle hash matches the verified local build exactly. See [docs/reports/ADMS-Personnel-MasterData-024.md](docs/reports/ADMS-Personnel-MasterData-024.md). Makes Personnel Master Data manageable from the ADMS web UI: ADMIN-only add/edit of Human records (`POST`/`PATCH /api/v1/humans`, source `ADMS_MANUAL` distinct from legacy `EXCEL_IMPORT`), Thai rank dropdown validated against the canonical `RTN_RANK_CATALOG`, English-name editing, CSV export (BOM-prefixed, all roles), CSV import with a strict two-phase preview-then-commit flow (preview is read-only and NOT write-session gated; commit re-validates and re-uploads the same file, ADMIN + write-session gated), matching existing rows only by the pre-existing `personnel_id` UNIQUE column — never by name. Production data-quality audit found 0 of 120 existing Humans have `personnel_id` populated (100% legacy `EXCEL_IMPORT`), so CSV import can create new rows today but cannot update pre-existing legacy rows until an ADMIN backfills `personnel_id` via Edit first — a disclosed limitation. No migration (the UNIQUE constraint on `personnel_id` already existed). No Enrollment/Terminal Management/Mapping/DeviceOwner/Attendance logic touched. 800 tests passing (+44). Zero production mutations performed during implementation.

**Deployed at `17e657b`**: `ADMS-RBAC-OperationalRoles-023` — see [docs/reports/ADMS-RBAC-OperationalRoles-023.md](docs/reports/ADMS-RBAC-OperationalRoles-023.md). Finalizes operational role semantics: Work Session open/close widened from ADMIN-only to **OPERATOR-or-ADMIN** (`app/api/routers/write_session.py`) — OPERATOR is now the operational supervisor who controls *when* writes may happen, but this does not grant OPERATOR any ADMIN-only capability. Full source audit confirmed mapping verification, Personnel admin lifecycle, destructive Terminal Management, and operator/role management were already, and remain, ADMIN-only. New frontend capability helpers (`canOpenWorkSession`, `canVerifyIdentity`, etc.) mirror the backend role sets. 756 tests passing (+27). No migration, no production mutation.

**Deployed at `e159fa3`**: `ADMS-CurrentState-History-UXClosure-022` (including its terminal-ID reclamation DB-invariant follow-up, migration `sql/013` — **applied to production** with verified pre/post `pg_dump` backups). Fixes two confirmed production UX defects where historical DB rows were presented as current state: (A) Dashboard's headline "device users"/"mappings" KPIs now show the current-only count, not historical totals; (B) the Mapping page splits Current/History into separate sections via server-derived `Mapping.mapping_lifecycle_state`/`is_current`. Also fixed the DB-level `uq_enrollment_terminal_id` constraint to agree with the PromptID-020 terminal-ID reclamation policy (partial unique index, no row mutated) and hardened `reserve_next_device_user_id()` against raw uniqueness-violation 500s.

**Deployed at `f78d309`**: `ADMS-UX-FinalPolish-021` + `ADMS-UX-CrossLifecycleClosure-021B` + `ADMS-Dashboard-LifecycleSummary-021C` — see their respective reports. Together: fixed the auth role-badge flicker/stuck-stale-role bug (deterministic `/auth/me` refetch on login/logout); wired Enrollment completion via the already-existing `RETIRED` terminal state (no migration); added a server-derived `Enrollment.lifecycle_state` so Enrollment Workspace/Personnel/Dashboard can never disagree about whether an enrollment is genuinely unfinished (self-heals real production Enrollment #1/#4 without a backfill); confirmed rank is import-only and labeled it source-managed; fixed the Dashboard's enrollment-status widget to use the same canonical `lifecycle_state` instead of raw `status`. Live-verified against real production data (Pimai/1004, User 1001) post-deploy.

**Deployed**: `ADMS-TerminalManagement-020` — commit `f9ba44f` is live on `ai-brain` (containers rebuilt/recreated, verified healthy). Physical ZEM560 fingerprint/account lifecycle management, all device I/O routed through the existing DeviceOwner single-owner path, read-before-write/read-after-write verified mutations, idempotent, ADMIN + write-session gated, atomic Human/attendance/mapping/enrollment history preservation. Frontend UI (`frontend/src/pages/TerminalManagement.tsx`, `/terminal-management`, ADMIN-only), fingerprint re-enrollment (`State.FINGERPRINT_ENROLLING`, no mid-call cancellation possible with installed pyzk — documented), and no-migration cancelled-ID reclamation are all live. **Real production cleanup performed** (owner-approved, per-target): test terminal user 1004 (พิมาย ขาวสอาด) had its fingerprint and terminal account removed via the canonical UI/API path; mapping #2 closed automatically by the existing roster-lifecycle reconciler; Human, Enrollment #4, attendance history, and terminal user 1001/mapping #1 all preserved untouched. A real pyzk-wrapper bug (`delete_user_template` receiving a `user_id` string that the installed pyzk's TCP branch can't `struct.pack` on Python 3) was found, fixed, tested, and redeployed (`f9ba44f`) during this work — see the report for the full incident writeup.

**Deployed**: `ADMS-Personnel-Lifecycle-019` — explicit ACTIVE/INACTIVE Human lifecycle (deactivate/reactivate), atomic mapping closure on departure (`valid_to` = departure time, historical mappings/attendance never touched), Personnel list active/inactive filtering, Thai lifecycle UX. See [docs/reports/ADMS-Personnel-Lifecycle-019.md](docs/reports/ADMS-Personnel-Lifecycle-019.md).

**Real production milestone**: Enrollment #4 completed the full Step 1→6 identity-verification workflow successfully — terminal user 1004, `device_user_pk=29`, `controlled_attendance_id=38`, VERIFIED `mapping_id=2`, Human `fd63997f-b081-45bf-b74f-db224491fabc`. Temporal mapping semantics verified live (pre/post `valid_from` attendance resolution). This closed the Enrollment core work (`ADMS-FullEnrollment-E2E-Closure-017` / `ADMS-ControlledScan-EvidenceBinding-018`, both deployed) and the recurring "Attendance ID #?" incident class. See [docs/reports/ADMS-FullEnrollment-E2E-Closure-017.md](docs/reports/ADMS-FullEnrollment-E2E-Closure-017.md) and [docs/reports/ADMS-ControlledScan-EvidenceBinding-018.md](docs/reports/ADMS-ControlledScan-EvidenceBinding-018.md).

**Incident record correction (010)**: Terminal User 1002's earlier disappearance from the terminal roster was **not** a firmware/software persistence failure. The OWNER manually deleted User 1002 from the physical terminal after an earlier browser operation reported an error (itself a real, separately-fixed bug — see PromptID `ADMS-ZEM560-TerminalAccount-Idempotency-Recovery-008`). This is the authoritative account; no further hardware investigation is open on this incident.

---

## 1. Production Environment

- **Management Web Console**: `http://192.168.1.248:8082` (Container `adms_web` via Nginx, LAN bind)
- **Backend API**: `http://192.168.1.248:8081` (Container `adms_api` via FastAPI/Uvicorn, LAN bind)
- **Biometric Terminal**: `192.168.1.201:4370` (SONIC / ZKTeco ZEM560_TFT, standalone binary protocol)
- **Container Topology**: `adms_web`, `adms_api`, `adms_zkteco_listener`, `adms_postgres`, `adms_mqtt`
- **Collector Connection State**: `LIVE` / `device_connected = true`
- **Master Production Write Gate**: `API_WRITE_ENABLED = true` (Layer 1 — now the deploy-time infrastructure baseline; daily write control moved to Layer 2)
- **Runtime write-session feature (Layer 2)**: **LIVE in production as of Phase F.** ADMIN-opened, 30-minute, auto-expiring, audited. No session is open by default — production remains write-locked until an ADMIN explicitly opens one.

---

## 2. Hardening-007 Phase Status

| Phase | Scope | Status |
|---|---|---|
| A | Security correctness (operator-management write-gate bypass closed; `ENROLLMENT_ACTIONS` role-metadata drift fixed; centralized error mapping) | **COMPLETE** |
| B | Runtime write-session backend (migration 012, advisory-lock concurrency, `require_write_session` dependency, audit events) | **COMPLETE — DEPLOYED** |
| C | Admin/operator frontend controls (write-session control panel, header badge, route guard, `canWrite` fix) | **COMPLETE — DEPLOYED** |
| D | Enrollment hardening (SSE connection indicator, native alert/confirm removal, human-readable mapping confirmation) | **COMPLETE — DEPLOYED** |
| E | i18n/UX cleanup (centralized enum labels, System health-card fix, Attendance local time, role descriptions, jargon removal) | **COMPLETE — DEPLOYED** |
| F | Production deployment — migration 012 applied, `api`/`web` redeployed, `API_WRITE_ENABLED` transitioned to `true` | **COMPLETE** |

Full engineering detail: [docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md](docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md) and [docs/reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md](docs/reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md).

---

## 3. Quality Baseline

- **Repository HEAD**: see `git log -1` (this checkpoint's commits are recorded in the Phase F report)
- **Database Migrations Applied to Production**: through `012_write_session_schema.sql` (12 migrations, additive-only — applied during Phase F, verified pre/post backups taken).
- **Automated Test Baseline**: **800 passed / 0 failed** (`pytest tests/`, includes the write-session, terminal-account-idempotency, DeviceCommandBus timeout-margin, single-owner device I/O, mapping-evidence, full Step 1→6 E2E, controlled-scan evidence binding, Personnel lifecycle, Terminal Management, RBAC operational-roles, and Personnel Master Data create/edit/CSV-import matrices)
- **Frontend Typecheck & Build**: `tsc --noEmit` PASS (0 errors), `vite build` PASS
- **OpenAPI Drift Guard**: PASS (`tests/test_openapi_contract.py`, covers the `/write-session` endpoints)
- **Production write-control verification**: full two-layer matrix (Layer-1-only block, role enforcement, session open/close/idempotent-close, expiry-does-not-block-reopen, Layer-1-overrides-Layer-2) verified live against production via temporary, fully-cleaned-up test-fixture accounts — see the Phase F report.

---

## 4. Major Capabilities

1. **Human Master Registry** — authoritative personnel roster with RTN rank normalization and conscript exclusion.
2. **Attendance Processing & Reconciliation** — ZKTeco TCP ingestion, deduplication, UTC canonical storage with Thailand-local display in the console.
3. **Temporal Identity Mapping** — strict `[valid_from, valid_to)` validity interval resolution; ambiguity fails closed to `NULL`.
4. **Guided Enrollment Workspace** — state-machine-driven UI; realtime controlled-scan detection with an explicit connection-status indicator and manual reconnect.
5. **Browser-Driven Hardware Account Creation** — `set_user()` over the internal Device Command Bus (MQTT); single-socket exclusive execution inside the Collector.
6. **Realtime Attendance SSE Stream** — live scan notification and auto-refreshing tables.
7. **Bilingual Localization (TH/EN)** — typed i18n engine, Thai default; centralized enum→label mapping keeps backend status codes out of the UI.
8. **Role-Based Access Control (RBAC)** — `VIEWER`, `ENROLLMENT_OPERATOR`, `OPERATOR`, `ADMIN`, enforced server-side; frontend route guard added for a clear access-denied UX (UX-only, not a security boundary).
9. **Admin Operator Account Management** — provisioning, role selection, active toggle; role descriptions now shown in the creation form; mutations are write-gated (Phase A fix).
10. **Personnel Master Data Management** — ADMIN-only add/edit of Human records, canonical rank dropdown, bilingual name editing, CSV export/import (preview-then-commit, matched by `personnel_id` only). **In source only — see §5.**
11. **Security & System Audit Trail** — rate limiting, PBKDF2 password hashing, opaque Bearer tokens, append-only `sync_events`; new `WRITE_SESSION_OPENED`/`CLOSED`/`EXPIRED`/`OPEN_FAILED` event types, live in production as of Phase F.
12. **OpenAPI Snapshot & Typed Client Codegen** — automated schema snapshot and operation-derived TypeScript client; drift-guarded.
13. **Collector Health Bridge** — shared-volume Collector telemetry to API consumers.
14. **Runtime Write Session (Layer 2)** — ADMIN-opened, 30-minute, auto-expiring, audited work session; advisory-lock-guarded concurrency so an expired-but-unclosed session never blocks a new open and a concurrent open can never succeed twice. **In source only — see §5.**
15. **Human-readable mapping confirmation, live-connection indicators, and no native browser `alert()`/`confirm()` in the enrollment/mapping flows.**

---

## 5. Production State (post-Phase F)

- `API_WRITE_ENABLED` is now **`true`** in production — the new steady-state infrastructure baseline. It no longer needs to be toggled per session; Layer 2 (the runtime write session) is the daily control now.
- Migration `012_write_session_schema.sql` **has been applied** to production (verified schema, verified pre- and post-migration `pg_dump` backups with SHA256 + `pg_restore -l` sanity checks).
- `adms_api` and `adms_web` are running the Hardening-007 build (rebuilt and recreated during Phase F).
- The Collector, MQTT broker, and ZKTeco terminal were **not modified** — confirmed via unchanged container start times and 0 restart counts throughout the deployment.
- No real enrollment session, no real personnel/device data write, and no device write occurred during Phase F verification — all write-control verification used temporary, clearly-labeled test-fixture operator accounts that were fully deleted afterward, with their tokens revoked and their write-session rows removed.
- **Default state is write-locked**: no write session is open unless an ADMIN explicitly opens one from the System page.

---

## 6. Security & Safety Rules

- **Zero Automatic Mapping**: unchanged — no assumption that Excel row number, name, or rank equals terminal user ID.
- **Fail-Closed Write Gate**: unchanged and reinforced — every domain-mutating endpoint (including operator management, previously a gap) requires the infrastructure gate; a second, independent runtime-session gate is now live in production as of Phase F, closed by default.
- **Lifecycle & Incarnation Protection**: unchanged.
- **Biometric Boundary**: unchanged — no biometric templates ever leave hardware.
- **RBAC enforcement remains server-side**: the new frontend route guard is explicitly UX-only.

---

## 7. Roadmap & Operational Readiness

### DEPLOYED
- **Phase F** — migration 012 applied, `api`/`web` redeployed with the write-session backend live, `API_WRITE_ENABLED` transitioned to `true`. See the Phase F report for the full verification matrix.
- **PromptID 008** — idempotent, read-back-verified terminal-account creation (`create_or_reconcile_terminal_account`); root-caused and fixed the pyzk `set_user()` return-value bug.
- **PromptID 010** — derived (non-arbitrary) `DeviceCommandBus` outer timeout, distinct `DEVICE_UNAVAILABLE`/`TerminalRosterUnavailable` pre-mutation error category end-to-end, dedupe-key safety hardening. No DB migration; `api`/`web`/`listener` rebuilt. See [docs/reports/ADMS-DeviceCommandBus-TimeoutMargin-010.md](docs/reports/ADMS-DeviceCommandBus-TimeoutMargin-010.md).

### OWNER GATE PENDING
- **Enrollment #2 canonical recovery** — a real production data split-state (terminal account exists, DB row does not / vice versa, resulting from the original incident). Not recovered. Requires explicit owner approval before any real `set_user()`/`delete_user()` call on production hardware — see the PromptID-010 report's closing gate.

### READY FOR EXECUTION
- **Real Personnel Enrollment**: ready for on-site physical enrollment following the **normal browser-controlled procedure** in `docs/ENROLLMENT_SESSION_RUNBOOK.md` — an ADMIN opens a work session from the System page; no SSH/`.env` step is required for a routine session anymore.

### DEFERRED
- **Multi-Person Enrollment Validation**: verification across multiple distinct individuals.
- **Native ADMS Push**: deferred (device hardware silent; polling Collector remains authoritative primary).
