# ADMS Current Status

**Latest PromptID**: `ADMS-FullEnrollment-E2E-Closure-017` (committed, **NOT yet deployed** — pending owner deployment gate; see [docs/reports/ADMS-FullEnrollment-E2E-Closure-017.md](docs/reports/ADMS-FullEnrollment-E2E-Closure-017.md)). Fixes the root cause of the recurring Step 6 "Attendance ID #?" / 422 failure (a second, independent exact-timestamp-equality check inside `create_verified_mapping()` that PromptID-016's eligibility-query fix never touched); adds a single canonical controlled-scan evidence resolver used by both the eligibility listing and mapping creation; gates `READY_FOR_MAPPING` on resolvable evidence so a broken evidence chain fails at Step 5, not Step 6; simplifies `POST /api/v1/mappings` to `{enrollment_id, verified_by, verification_note}` (server derives the rest); adds a full Step 1→6→post-mapping-attendance E2E test. Deployed most recently before this: `ADMS-DeviceCommandBus-TimeoutMargin-010` (see [docs/reports/ADMS-DeviceCommandBus-TimeoutMargin-010.md](docs/reports/ADMS-DeviceCommandBus-TimeoutMargin-010.md)).

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
- **Automated Test Baseline**: **534 passed / 0 failed** (`pytest tests/`, includes the write-session, terminal-account-idempotency, DeviceCommandBus timeout-margin, single-owner device I/O, mapping-evidence, and full Step 1→6 E2E matrices)
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
10. **Personnel English Name Support** — bilingual display, Admin-only inline editing.
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
