# ADMS Current Status

**Latest (2026-10-02 → 10-28, HEAD — see git log)**: Personnel workflows, leave register, attendance reporting and go-live — all deployed (`adms_api`/`adms_web` rebuilt; migrations 014–017 applied; collector untouched). Plan and decisions: [docs/plans/personnel-workflow-and-leave.md](docs/plans/personnel-workflow-and-leave.md); audit follow-up: [docs/audits/ADMS-audit-2026-09-03.md](docs/audits/ADMS-audit-2026-09-03.md). Highlights:
- **Ops fixes**: write-window timer had failed every run since 09-23 (token parse bug) — fixed, then retired; admin password moved out of systemd units and rotated; nightly backup was reported failed every night (empty-glob `ls` under `pipefail`) — fixed; `/data` (2nd disk) had silently dropped out of fstab mounting on the 09-23 reboot (`fsck` SIGTERM, `nofail`) — remounted with `x-systemd.automount`; header "LIVE" badge now reads real collector state.
- **Personnel**: navigation by job (attendance / roster / fingerprints / admin); roster hub with attention counts; scan-exempt per row or in bulk (finance — some people, commander's office) with section filter and position column; one-step leave-unit (close + remove from scanner); conscripts (`production_scope=false`) outside roster and scanning.
- **Enrollment**: 4 visible steps with auto-advance, auto-confirm on live test scan, inline ADMIN verification.
- **Leave register** (record-only — signed by the battalion commander on paper): leave / official duty / secondment / training, no-overlap constraint, cancel-with-reason, holidays.
- **Attendance**: scans count only 06:30–11:00, late after 10:00; daily roster and monthly report (+ Excel CSV); people count only from the day after their fingerprint is verified (`NOT_ENROLLED` otherwise).
- **Go-live switch** (`attendance_policy.tracking_mode`, default `auto`): absences are trial until everyone who must scan is enrolled (excluding exempt, people on duty/secondment, conscripts); ADMIN can force on/off. Going live is latched (`live_since`) so people returning from duty later don't revert the unit to trial (`eacd606`).
- **Scanner name sync** (`65ec80e`): the scanner name is derived only from rank + English name; new owner-thread command `RENAME_TERMINAL_ACCOUNT` (in-place `set_user` on the same uid, read-back verified, fingerprints untouched) behind `POST /humans/{id}/sync-terminal-name`; person page flags device-vs-roster mismatch. Verified on device: 1001 renamed `cpo3 → CPO2 Krittapon M`, 2 templates kept. **Automatic since 10-07**: saving a rank / English name (form or Excel import) pushes the new name to the scanner (best effort — an offline scanner leaves the mismatch listed); manual buttons per person and 'update all' on the Personnel page. Open item: 1006 has no English name (device shows `thapakorn chalui`).
- **Exemption presets**: finance, commander's office, official duty, secondment (long-running duty can be a standing exemption).
- **Telegram**: daily absent-only report Mon–Fri 11:05 (`deploy/systemd/adms-telegram-report.timer`), silent before go-live.
- **Write policy**: Work Session disabled in production (`API_WORK_SESSION_REQUIRED=false`) — edits and enrollment are allowed any time, still role-gated, `API_WRITE_ENABLED`-gated and audited.
- **Go-live date** (10-28): `tracking_mode=date`, `counting_from=2026-11-09` (9 พ.ย. 2569) — counting is real from that day whatever readiness is (not-enrolled = `NOT_ENROLLED`, never absent); earlier days are trial and blank in the monthly report.
- **Scanner clock**: corrected automatically on reconnect (10-28: device was back at 2026-10-12 after a 16-day outage); tolerance 90s because the ZEM560 reports minute resolution.
- **Scanner offline alert**: `app/device_alert.py` + `deploy/systemd/adms-device-alert.timer` (every 5 min) — Telegram after 30 min offline, recovery message when back; `TELEGRAM_ALERT_CHAT_ID` (dev chat) optional.
- **10-28 follow-ups** (`deffb50` → HEAD):
  - **Holiday calendar** on the Leave page (click a weekday to add, a holiday to remove; one button fills the 14 fixed-date Thai holidays for the year — lunar and cabinet-announced days still added by hand).
  - **Weekly Docker prune** timer `deploy/systemd/adms-docker-prune.{service,timer}` (Sun 03:30, build cache >7 days + dangling images; never volumes) — install with `sudo cp … && systemctl enable --now`.
  - **Managed department list** (migration 018, `system_configurations['departments']`, `PUT /api/v1/humans/branches`, System-page card): the Personnel form's แผนก is now a dropdown; values already on people stay listed. Existing data still has dotted variants (`กง.` vs `กง`) to reconcile.
  - **Enrollment Operator role** removed from account creation (API/DB still accept it; no account uses it). Roles in use: ADMIN (`headofcommu` battalion commander, `admin` developer), OPERATOR ×2.
  - **Dashboard** is attendance-first: today's totals, 7-workday trend, readiness by section, per-department table; technical counters folded below.
  - **Absence import**: CSV template on the server (`app/templates/absence_import_template.csv`, `GET /absences/import-template`), preview then all-or-nothing commit (`app/absence_import.py`).
  - **Manuals** (Thai, static): `/manual/` — user / operator / admin, linked from the sidebar.
  - **Exempt wording**: roster / monthly / personnel show scan-exempt people as **"ปฏิบัติหน้าที่"** (monthly code **ป**, was ย "ไม่ต้องสแกน"); the exemption controls are unchanged.
  - **Personnel section owns the roster** (`b7dc725`, owner decision): every `humans` endpoint — create / edit / CSV import / scan-exempt / leave-unit / scanner-name sync / departments — is OPERATOR+ (was ADMIN-only). New `POST /humans/{id}/remove-from-scanner` removes a closed person's scanner accounts, scoped to that person (Terminal Management stays ADMIN-only). Fingerprint enrollment, mapping verification, user accounts and go-live mode stay ADMIN.
  - **Leave-unit from Excel**: import preview lists active people missing from an *exported* file (matched by `employee_id`, error rows still count as present); the operator ticks who actually left → closed + removed from the scanner. Never automatic; warning when >20% are missing; hand-made files without `employee_id` never flag anyone. Verified on production (preview only): untouched export → 0 missing, one row removed → exactly that person.
  - **Acting ranks** (`144b829`): `ว่าที่ <officer rank>` is valid in the form, the import and the rank dropdown (`is_canonical_rank`); scanner name uses the plain abbreviation (ว่าที่ ร.ต. → `Sub Lt`). A fresh export now re-imports with 0 errors (was 9: ว่าที่ ร.ต. ×7, ว่าที่ น.ต. ×2).
- 904 tests passing. Listener rebuilt on 10-07 (new device command); collector LIVE. Web: http://192.168.1.248:8082 (LAN only).

**Deployed (previous latest)**: `ADMS-PersonnelIdentity-AttendanceClosure-025` — closes two defects found in production after 024's deployment; see [docs/reports/ADMS-PersonnelIdentity-AttendanceClosure-025.md](docs/reports/ADMS-PersonnelIdentity-AttendanceClosure-025.md). **(A) Personnel identity correction**: `personnel_id` was never actually required by `create_human`/`update_human`/the Add/Edit form (024's backend and UI were already correct), but PromptID 024's CSV import mistakenly made `personnel_id` the CSV matching key AND required it on every row — meaning the 120 legacy Humans (0 with `personnel_id`) could never be updated via CSV, and even the downloadable template's own blank-`personnel_id` example row would have been rejected as an error. Fixed: CSV round-trip matching now uses `employee_id` (the system's own canonical UUID, included only in ADMS-generated exports) — `personnel_id` remains a fully optional business field, never required, never a matching key, never backfilled. New-person import rows (no `employee_id`) always classify NEW; a same-name match against an existing Human is a non-blocking advisory only, never an auto-update. **(B) Attendance `/unattributed` 500 fixed**: root cause was `app/api/repository.py` calling `resolve_verified_employee_mapping()` without importing it (`NameError`, confirmed via production traceback) — the bug escaped test coverage because the only prior tests mocked the whole function away. Also fixed a genuine (not merely apparent) CORS gap: Starlette routes any handler registered for the base `Exception` class into `ServerErrorMiddleware`, which sits outside `CORSMiddleware`, so a handled 500 previously carried no CORS header at all — the browser's "CORS error" was a real secondary symptom of the crash. Both fixed; 41 new/changed tests; 825 tests passing. No migration. Deployed (`adms_api`/`adms_web` rebuilt and recreated).

**Deployed at `df6f347`**: `ADMS-Personnel-MasterData-024` — owner-approved (gate A), `adms_api`/`adms_web` rebuilt and recreated, both healthy; `adms_zkteco_listener`/`adms_postgres`/`adms_mqtt` untouched. Makes Personnel Master Data manageable from the ADMS web UI: ADMIN-only add/edit of Human records (`POST`/`PATCH /api/v1/humans`, source `ADMS_MANUAL` distinct from legacy `EXCEL_IMPORT`), Thai rank dropdown validated against the canonical `RTN_RANK_CATALOG`, English-name editing, CSV export/import. **Superseded by 025 above**: the CSV identity/matching design described in the original 024 report was corrected in 025 — see that report for the current behavior. No migration. 800 tests passing (+44) at the time of this deployment. Zero production mutations performed during implementation.

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
- **Runtime write-session feature (Layer 2)**: **disabled in production since 2026-10-02** (`API_WORK_SESSION_REQUIRED=false`). Code and tests remain; set it back to `true` to restore the ADMIN-opened work session. The host timers that opened/closed it are disabled.
- **Attendance policy**: scan window 06:30–11:00, late after 10:00, go-live `auto` (currently **trial** — 4/84 enrolled).
- **Telegram report**: configured (`.env`), timer `adms-telegram-report.timer` enabled, silent until go-live.
- **Backups**: nightly 02:15 to `/home/.../backups` and `/data/adms/backups` (2nd disk, `x-systemd.automount` — verified mounting after the 10-06 reboot), 14-day retention; no off-site copy.

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
- **Database Migrations Applied to Production**: through `018_departments.sql` (014 schedule config, 015 scan-exempt, 016 absences/holidays/attendance_policy, 017 scan window, 018 department list — all additive).
- **Automated Test Baseline**: **904 passed / 0 failed** (2026-10-28). Earlier baseline: 800 passed (`pytest tests/`, includes the write-session, terminal-account-idempotency, DeviceCommandBus timeout-margin, single-owner device I/O, mapping-evidence, full Step 1→6 E2E, controlled-scan evidence binding, Personnel lifecycle, Terminal Management, RBAC operational-roles, and Personnel Master Data create/edit/CSV-import matrices)
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
8. **Role-Based Access Control (RBAC)** — `VIEWER`, `OPERATOR` (personnel section: roster, leave, import, leave-unit), `ADMIN` (fingerprints, scanner, accounts, go-live); `ENROLLMENT_OPERATOR` retired from the UI; enforced server-side; frontend route guard added for a clear access-denied UX (UX-only, not a security boundary).
9. **Admin Operator Account Management** — provisioning, role selection, active toggle; role descriptions now shown in the creation form; mutations are write-gated (Phase A fix).
10. **Personnel Master Data Management** — ADMIN-only add/edit of Human records, canonical rank dropdown, bilingual name editing, CSV export/import (preview-then-commit, matched by `personnel_id` only). **In source only — see §5.**
11. **Security & System Audit Trail** — rate limiting, PBKDF2 password hashing, opaque Bearer tokens, append-only `sync_events`; new `WRITE_SESSION_OPENED`/`CLOSED`/`EXPIRED`/`OPEN_FAILED` event types, live in production as of Phase F.
12. **OpenAPI Snapshot & Typed Client Codegen** — automated schema snapshot and operation-derived TypeScript client; drift-guarded.
13. **Collector Health Bridge** — shared-volume Collector telemetry to API consumers.
14. **Runtime Write Session (Layer 2)** — ADMIN-opened, 30-minute, auto-expiring, audited work session; advisory-lock-guarded concurrency so an expired-but-unclosed session never blocks a new open and a concurrent open can never succeed twice. **In source only — see §5.**
15. **Human-readable mapping confirmation, live-connection indicators, and no native browser `alert()`/`confirm()` in the enrollment/mapping flows.**
16. **Leave register & attendance reporting** — record-only leave/duty/secondment, holidays, scan window, daily roster, monthly report + CSV, fingerprint readiness, go-live switch, Telegram absence report.
17. **Personnel workflows** — scan-exempt (row/bulk), leave-unit, readiness by section, 4-step enrollment.

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
- **Fail-Closed Write Gate**: every domain-mutating endpoint requires the infrastructure gate (`API_WRITE_ENABLED`) and its role. The runtime-session gate (Layer 2) is switched off in production since 2026-10-02 by owner decision; edits are audited in `sync_events`.
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
- **Before go-live 9 Nov 2569**: holidays for the year, English names + departments for everyone (OPERATOR staff), scan-exempt list, people currently on duty, remaining fingerprint enrollment (1007 needs its scan window reopened). Counting starts on the date whatever readiness is.
- **Off-site backup copy**: not set up — recommended target another machine over Tailscale (rsync nightly).
- **Waiting on owner**: n8n access (MCP or URL + API key) for LINE Flex report and dev Telegram; LINE leave request + approval flow (after go-live); install the docker-prune timer.

### DEFERRED
- **Multi-Person Enrollment Validation**: verification across multiple distinct individuals.
- **Native ADMS Push**: deferred (device hardware silent; polling Collector remains authoritative primary).
