# ADMS Server

An Attendance Device Management System connecting physical ZKTeco biometric terminals to an authoritative personnel roster, with browser-driven enrollment, temporal identity verification, and role-based access control.

---

## Current Status

- **Backend API**: implemented and running in production (FastAPI, PostgreSQL, MQTT).
- **Frontend operational console**: implemented and running in production (React/TypeScript, Tailwind).
- **TH/EN UI**: implemented, runtime-switchable, Thai default.
- **Realtime attendance (SSE)**: implemented and running.
- **Guided enrollment workflow**: implemented and running.
- **VERIFIED temporal identity mapping**: implemented and running.
- **Role-based access control (RBAC)**: implemented — `VIEWER`, `ENROLLMENT_OPERATOR`, `OPERATOR`, `ADMIN`.
- **OpenAPI-generated TypeScript client**: implemented; `frontend/src/api/generated.ts` is derived from the live backend contract and drift-guarded by a test.
- **Runtime write-session feature** (`ADMS-FullSystem-P0P1-Hardening-007`): **live in production as of Phase F.**
  - Migration `012_write_session_schema.sql` has been applied to the production database.
  - `API_WRITE_ENABLED` is now `true` in production — the infrastructure gate is the deploy-time baseline; daily write control is the runtime write session (Layer 2), which is closed by default.
  - See [STATUS.md](STATUS.md), [docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md](docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md), and [docs/reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md](docs/reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md) for the full picture and deployment verification record.

---

## Architecture

Attendance ingestion (device → database):

```
ZKTeco Terminal
      ↓
Collector (adms_zkteco_listener)
      ↓
PostgreSQL / MQTT
      ↓
FastAPI (adms_api)
      ↓
React ADMS Console (adms_web)
```

Terminal commands (browser → device), issued during enrollment:

```
Browser
   ↓
FastAPI
   ↓
DeviceCommandBus (MQTT)
   ↓
Collector
   ↓
ZKTeco Terminal
```

**The frontend never connects directly to PostgreSQL or to the ZKTeco terminal.** All reads and writes go through the FastAPI HTTP/SSE API; all terminal commands are serialized through the Collector's single exclusive device connection via the MQTT-backed `DeviceCommandBus` — the API never opens a second connection to the terminal.

---

## Main Features

- **Dashboard** — operational overview: personnel, device, attendance, and mapping summaries; collector telemetry.
- **Personnel** — Human Master roster (Thai + English names, rank, branch, production scope).
- **Attendance** — historical scan log plus a realtime feed (SSE); Thailand local time is the primary display, UTC is preserved as the canonical stored value and available on hover.
- **Devices** — registered terminal fleet and discovered terminal accounts.
- **Enrollment** — guided, step-by-step workflow: reserve a terminal ID, create a terminal account, physical fingerprint enrollment, controlled verification scan, mark ready for mapping.
- **Mapping** — ADMIN-only creation of `VERIFIED` temporal identity mappings from controlled-scan evidence, with a human-readable confirmation step (no raw ID dumps).
- **Audit** — append-only security/operational event trail (ADMIN only).
- **System** — service health, password change, operator account management, rank reference table, and the runtime write-session control panel.
- **TH/EN language switching** — runtime toggle, Thai default, persisted per browser.
- **Role-based UX** — navigation and available actions adapt to the signed-in role; backend RBAC remains the actual authorization boundary regardless of what the UI shows.
- **Realtime attendance** — live scan detection during both normal monitoring and the enrollment controlled-scan step, with an explicit connection-status indicator and manual reconnect.
- **Write-session architecture** — see below.

---

## Identity Model

```
Human Master
    ↓
Enrollment (reserve → terminal account → fingerprint → controlled scan)
    ↓
Device User (terminal account)
    ↓
Controlled Scan Evidence
    ↓
ADMIN-created VERIFIED Mapping
    ↓
Attendance Attribution
```

- **No fuzzy identity matching.** Identity is never inferred from name similarity, rank, or sequential/numeric ordering.
- **No automatic VERIFIED mapping.** Every mapping is created by an explicit ADMIN action against a specific enrollment's controlled-scan evidence.
- **Identity authority is the `VERIFIED` mapping**, not the enrollment or the terminal account alone — a terminal account never establishes identity by itself.
- **The temporal `[valid_from, valid_to)` model remains authoritative** for attributing attendance scans to a person; a scan outside a mapping's valid interval is never attributed.
- Terminal-account lifecycle protections are unchanged: a disappeared terminal account closes its open mapping, and a reappeared/recycled account never inherits the prior identity automatically.

---

## Roles

| Role | What they can do |
|---|---|
| **VIEWER** | View-only access — dashboard, personnel, attendance, devices, mappings. |
| **ENROLLMENT_OPERATOR** | Enroll personnel on the fingerprint terminal. Scope is strictly limited to the enrollment workflow, personnel lookup, and the realtime stream. |
| **OPERATOR** | View operational data and manage enrollments (broader read access than ENROLLMENT_OPERATOR, plus the same enrollment-mutation capability). |
| **ADMIN** | Manage the system, accounts, and confirm identity mappings — full administrative authority, including operator account management, `VERIFIED` mapping creation, and audit trail access. |

These descriptions match the TH/EN copy shown in the console's operator-account creation screen.

---

## Write Safety Model

ADMS uses a **two-layer write-control model**, live in production as of Phase F.

**Layer 1 — Infrastructure master gate** (`API_WRITE_ENABLED`)
Server-owner controlled, environment-variable driven, fail-closed. Now `true` in production as the steady-state deploy-time baseline — a rarely-touched emergency lock, not a daily toggle.

**Layer 2 — Runtime write session**
An ADMIN-opened, time-boxed permission window:
- ADMIN-only open/close, from the browser (System page).
- Fixed 30-minute duration, no automatic renewal.
- Auto-expiring; every open/close/expiry is audited.
- At most one session active at a time.
- **Closed by default** — no write session is open unless an ADMIN explicitly opens one.

Effective write permission:

```
allow_write =
    infrastructure_master_enabled (API_WRITE_ENABLED)
    AND runtime_write_session_active
    AND role_permits_action
```

Layer 1 unconditionally overrides Layer 2 — if a server owner sets the infrastructure gate off, no runtime session can be opened or can authorize anything, regardless of its state in the database. This was verified in production during Phase F deployment.

---

## Enrollment Workflow

The normal, browser-controlled workflow (live in production):

1. ADMIN opens a work session from the browser (System page).
2. Enrollment Operator selects the Human to enroll.
3. Reserve a terminal ID.
4. Create the terminal account on the device.
5. Physical fingerprint enrollment at the terminal.
6. Controlled attendance scan (live-detected via the realtime stream, with a manual fallback).
7. Operator marks the enrollment ready for mapping.
8. ADMIN reviews the human-readable evidence and creates the `VERIFIED` mapping.
9. Work session closes (manually or by expiry) — no lingering write access.

See [docs/ENROLLMENT_SESSION_RUNBOOK.md](docs/ENROLLMENT_SESSION_RUNBOOK.md) for the full step-by-step procedure.

The CLI-based terminal-account creation path (`app.enrollment_cli`) is **emergency/fallback tooling only** — used when the browser→Collector command path is unavailable — never the normal workflow.

---

## Development

```bash
# Backend tests
pytest

# Frontend
cd frontend
npm install
npm run dev         # local dev server, :5173
npm run typecheck   # tsc --noEmit
npm run build        # tsc --noEmit && vite build

# OpenAPI codegen (regenerate the typed client after any backend contract change)
npm run codegen:api
```

`tests/test_openapi_contract.py` fails if the committed `frontend/openapi.json` snapshot drifts from the live backend contract — always regenerate and commit both `frontend/openapi.json` and `frontend/src/api/generated.ts` together with any backend schema change.

Current verified baseline (see [STATUS.md](STATUS.md) for the authoritative up-to-date figures): backend tests passing, frontend `tsc --noEmit` and `vite build` passing, OpenAPI drift guard passing.

---

## Deployment

Services (`docker-compose.yml`):

| Service | Container | Purpose |
|---|---|---|
| `adms-postgres` | `adms_postgres` | PostgreSQL persistence |
| `mqtt` | `adms_mqtt` | MQTT broker — realtime events + Device Command Bus |
| `listener` | `adms_zkteco_listener` | Collector — owns the single ZKTeco terminal connection |
| `api` | `adms_api` | FastAPI backend |
| `web` | `adms_web` | Nginx-served React console |

**Normal deploy:**
```bash
docker compose up -d
```

**Database migration:** apply new `sql/NNN_*.sql` files against `adms_postgres` following the procedure in [docs/DATABASE_MIGRATIONS.md](docs/DATABASE_MIGRATIONS.md) — always take a `pg_dump` backup first.

**Emergency infrastructure write lock:** a server owner can unconditionally block all domain writes at any time by setting `API_WRITE_ENABLED=false` in `.env` and recreating the `api` container — this overrides any runtime write session once Phase F is live, and is the mechanism today regardless.

No secrets, passwords, or tokens are stored in this repository or its documentation — configure them via `.env` (see `.env.example`; never commit `.env`).

---

## Documentation

- [Current Status Checkpoint](STATUS.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [API Contract](docs/API_CONTRACT.md)
- [Security & RBAC](docs/SECURITY_RBAC.md)
- [Enrollment Session Runbook](docs/ENROLLMENT_SESSION_RUNBOOK.md)
- [Database Schema & Migrations](docs/DATABASE_MIGRATIONS.md)
- [Deployment & Infrastructure Guide](docs/DEPLOYMENT.md)
- [Operations & Troubleshooting](docs/OPERATIONS.md)
- [P0/P1 Hardening Engineering Report](docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md) — the write-session architecture, security fixes, and UX hardening described above
- [Historical Reports Archive](docs/reports/README.md)

---

## Operational Safety Invariants

1. **Zero automatic Human mapping** — no assumption that sequential or numeric hardware IDs correspond to Human Master entries.
2. **VERIFIED mapping authority** — scans are attributed strictly within an explicit temporal interval mapping (`[valid_from, valid_to)`).
3. **Hardware lifecycle protection** — a terminal account's disappearance closes its active mapping; reappearance increments `account_incarnation` without inheriting the prior identity.
4. **Biometric security** — biometric templates remain on hardware; they are never extracted, transmitted, or stored in application databases.
5. **RBAC enforcement is server-side.** Any frontend role-aware UI (navigation, disabled buttons, access-denied screens) is UX only — the backend role/write-gate checks are the actual authorization boundary.
