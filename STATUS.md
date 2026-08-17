# ADMS Current Status

**Latest PromptID**: `ADMS-FullSystem-P0P1-Hardening-007` (Phases A–E complete in source; Phase F pending owner deployment gate)

---

## 1. Production Environment

- **Management Web Console**: `http://192.168.1.248:8082` (Container `adms_web` via Nginx, LAN bind)
- **Backend API**: `http://192.168.1.248:8081` (Container `adms_api` via FastAPI/Uvicorn, LAN bind)
- **Biometric Terminal**: `192.168.1.201:4370` (SONIC / ZKTeco ZEM560_TFT, standalone binary protocol)
- **Container Topology**: `adms_web`, `adms_api`, `adms_zkteco_listener`, `adms_postgres`, `adms_mqtt`
- **Collector Connection State**: `LIVE` / `device_connected = true`
- **Master Production Write Gate**: `API_WRITE_ENABLED = false` (unchanged — fail-closed, Layer-1-only model still in effect in production)
- **Runtime write-session feature (Layer 2)**: implemented in source, **not yet active in production** — see §5.

---

## 2. Hardening-007 Phase Status

| Phase | Scope | Status |
|---|---|---|
| A | Security correctness (operator-management write-gate bypass closed; `ENROLLMENT_ACTIONS` role-metadata drift fixed; centralized error mapping) | **COMPLETE** |
| B | Runtime write-session backend (migration 012, advisory-lock concurrency, `require_write_session` dependency, audit events) | **COMPLETE IN SOURCE / NOT PROD MIGRATED** |
| C | Admin/operator frontend controls (write-session control panel, header badge, route guard, `canWrite` fix) | **COMPLETE IN SOURCE** |
| D | Enrollment hardening (SSE connection indicator, native alert/confirm removal, human-readable mapping confirmation) | **COMPLETE IN SOURCE** |
| E | i18n/UX cleanup (centralized enum labels, System health-card fix, Attendance local time, role descriptions, jargon removal) | **COMPLETE IN SOURCE** |
| F | Production deployment — apply migration 012, deploy `api`/`web`, transition `API_WRITE_ENABLED` | **PENDING OWNER DEPLOY GATE** |

Full engineering detail: [docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md](docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md).

---

## 3. Quality Baseline

- **Repository HEAD**: see `git log -1` (this checkpoint's commit is recorded in the Hardening-007 report)
- **Database Migrations Applied to Production**: through `011_human_english_name.sql` (11 migrations). Migration `012_write_session_schema.sql` exists in the repository, additive-only, **not yet applied to production**.
- **Automated Test Baseline**: **429 passed / 0 failed** (410 pre-existing + 19 new write-session tests, across 22 test modules — `pytest tests/`)
- **Frontend Typecheck & Build**: `tsc --noEmit` PASS (0 errors), `vite build` PASS
- **OpenAPI Drift Guard**: PASS (`tests/test_openapi_contract.py`, extended to cover the new `/write-session` endpoints)

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
11. **Security & System Audit Trail** — rate limiting, PBKDF2 password hashing, opaque Bearer tokens, append-only `sync_events`; new `WRITE_SESSION_OPENED`/`CLOSED`/`EXPIRED`/`OPEN_FAILED` event types (source only, inert until Phase F).
12. **OpenAPI Snapshot & Typed Client Codegen** — automated schema snapshot and operation-derived TypeScript client; drift-guarded.
13. **Collector Health Bridge** — shared-volume Collector telemetry to API consumers.
14. **Runtime Write Session (Layer 2)** — ADMIN-opened, 30-minute, auto-expiring, audited work session; advisory-lock-guarded concurrency so an expired-but-unclosed session never blocks a new open and a concurrent open can never succeed twice. **In source only — see §5.**
15. **Human-readable mapping confirmation, live-connection indicators, and no native browser `alert()`/`confirm()` in the enrollment/mapping flows.**

---

## 5. Production State — What Has NOT Changed

- `API_WRITE_ENABLED` is **still `false`** in production. Not touched during Hardening-007 Phases A–E.
- Migration `012_write_session_schema.sql` has **NOT been applied** to the production database.
- No Phase F deployment has occurred — `adms_api` and `adms_web` in production are still running the pre-Hardening-007 build.
- The Collector, MQTT broker, and ZKTeco terminal have **not been modified** in any way by this work.
- No real enrollment session, no production DB write, and no device write occurred as part of Phases A–E.

---

## 6. Security & Safety Rules

- **Zero Automatic Mapping**: unchanged — no assumption that Excel row number, name, or rank equals terminal user ID.
- **Fail-Closed Write Gate**: unchanged and reinforced — every domain-mutating endpoint (including operator management, previously a gap) requires the infrastructure gate; source additionally implements a second, independent runtime-session gate (inert in production until Phase F).
- **Lifecycle & Incarnation Protection**: unchanged.
- **Biometric Boundary**: unchanged — no biometric templates ever leave hardware.
- **RBAC enforcement remains server-side**: the new frontend route guard is explicitly UX-only.

---

## 7. Roadmap & Operational Readiness

### COMPLETE IN SOURCE, AWAITING DEPLOYMENT
- **Phase F** — apply migration 012, deploy `api`/`web` with the write-session backend live, transition `API_WRITE_ENABLED` per owner approval. Requires a separate Owner Gate (see the Hardening-007 report).

### READY FOR EXECUTION (unchanged from prior checkpoint, using the current Layer-1-only production model)
- **Real Personnel Enrollment**: ready for on-site physical enrollment following the current-state procedure in `docs/ENROLLMENT_SESSION_RUNBOOK.md`, which is explicitly marked with the production-state notice until Phase F ships.

### DEFERRED
- **Multi-Person Enrollment Validation**: verification across multiple distinct individuals.
- **Native ADMS Push**: deferred (device hardware silent; polling Collector remains authoritative primary).
