# ADMS Server

An enterprise Attendance Device Management System and identity reconciliation platform connecting physical ZKTeco biometric terminals to authoritative personnel rosters with temporal identity resolution.

---

## 1. What ADMS Is

ADMS manages the complete attendance and biometric identity lifecycle across:
**Official Personnel Master → ZKTeco Biometric Terminal → Collector Ingestion Engine → PostgreSQL Database → REST API / SSE → Web Management Console**.

It provides evidence-gated personnel enrollment, realtime attendance monitoring, temporal identity mapping, and fail-closed production write safety.

---

## 2. System Architecture

```
ZKTeco ZEM560_TFT (192.168.1.201:4370)
  │
  │ TCP 4370 (ZK Binary Protocol)
  ▼
Collector (adms_zkteco_listener)
  ├── PostgreSQL (adms_postgres) — Relational persistence & temporal resolver
  └── MQTT Broker (adms_mqtt) — Realtime events & Device Command Bus
        │
        ▼
      FastAPI Backend (adms_api :8081)
        │
        ▼
   Web Console (adms_web :8082) — React / TypeScript / Tailwind
```

---

## 3. Key Features

- **Human Master Registry**: Authoritative personnel roster with RTN rank normalization and conscript exclusion.
- **Biometric Ingestion**: Realtime polling, historical backfill, deduplication, and UTC timestamp normalization.
- **Temporal Identity Mapping**: Scans resolve against strict `[valid_from, valid_to)` validity intervals.
- **Guided Enrollment Workspace**: 6-step guided UI for reserving IDs, creating device accounts, and confirming controlled scans.
- **Browser-Driven Hardware Control**: Serialized `set_user()` account creation via MQTT Device Command Bus.
- **Realtime Attendance SSE**: Instant scan alerts and live table updates via Server-Sent Events.
- **Bilingual Localization**: Seamless runtime switching between Thai (`th`) and English (`en`).
- **Role-Based Access Control (RBAC)**: Fine-grained permissions matrix with capability-limited roles.
- **Personnel English Name Editing**: Admin-gated bilingual name management.
- **System Audit Trail**: Complete append-only audit trail for authentication, rate limiting, and lifecycle events.

---

## 4. Roles & Access Control

| Role | Access Scope |
| ---- | ------------ |
| `VIEWER` | Read-only access to dashboard, personnel, devices, attendance, and mappings. |
| `ENROLLMENT_OPERATOR` | **Capability-limited operational role.** Access is strictly confined to the Enrollment Workspace, personnel lookup, and realtime stream. Forbidden from general attendance, audit logs, and dashboard summaries. |
| `OPERATOR` | General read access plus enrollment workflow execution. |
| `ADMIN` | Full authority including `VERIFIED` mapping creation, operator account provisioning, personnel English name updates, and audit trail inspection. |

---

## 5. Quick Start (Production)

To launch the complete multi-container stack:

```bash
docker compose up -d
```

### Access URLs
- **Web Management Console**: `http://192.168.1.248:8082` (or `http://localhost:8082`)
- **API Documentation (Swagger)**: `http://192.168.1.248:8081/docs`
- **API Health Check**: `http://192.168.1.248:8081/api/v1/healthz`

---

## 6. Configuration

Configure runtime parameters via `.env` in the project root:

```bash
# Database Settings
POSTGRES_DB=adms
POSTGRES_USER=adms
POSTGRES_PASSWORD=<SECURE_DB_PASSWORD>
POSTGRES_HOST=adms_postgres
POSTGRES_PORT=5432

# ZKTeco Hardware Settings
ZKTECO_DEVICE_IP=192.168.1.201
ZKTECO_DEVICE_PORT=4370
ZKTECO_COMM_KEY=600

# Production Write Gate (Fail-closed by default)
API_WRITE_ENABLED=false

# Security & Tokens
API_TOKEN_SECRET=<SECRET_TOKEN_SALT>
API_TOKEN_TTL_HOURS=12
```

> [!IMPORTANT]
> `API_WRITE_ENABLED=false` is a fail-closed safety gate. All state mutations and device writes are blocked until explicitly enabled for an operational session.

---

## 7. Production Physical Enrollment

To conduct an on-site physical fingerprint enrollment session, follow the authoritative runbook:
👉 [Enrollment Session Runbook](file:///d:/Dev/adms-server/docs/ENROLLMENT_SESSION_RUNBOOK.md) (`docs/ENROLLMENT_SESSION_RUNBOOK.md`)

---

## 8. Development & Testing

### Backend Automated Test Suite
```bash
pytest
```
*Current test suite baseline: **408 passed / 0 failed** across 21 test modules.*

### Frontend Development
```bash
cd frontend
npm install
npm run dev        # Launch local dev server on :5173
npm run typecheck  # TypeScript strict type checking
npm run build      # Vite production build
```

### OpenAPI Codegen
```bash
npm run codegen:api
```

---

## 9. Canonical Documentation

- [System Architecture](file:///d:/Dev/adms-server/docs/ARCHITECTURE.md) (`docs/ARCHITECTURE.md`)
- [Deployment & Infrastructure Guide](file:///d:/Dev/adms-server/docs/DEPLOYMENT.md) (`docs/DEPLOYMENT.md`)
- [Security & RBAC Matrix](file:///d:/Dev/adms-server/docs/SECURITY_RBAC.md) (`docs/SECURITY_RBAC.md`)
- [Database Schema & Migrations](file:///d:/Dev/adms-server/docs/DATABASE_MIGRATIONS.md) (`docs/DATABASE_MIGRATIONS.md`)
- [Operations & Troubleshooting](file:///d:/Dev/adms-server/docs/OPERATIONS.md) (`docs/OPERATIONS.md`)
- [Historical Reports Archive](file:///d:/Dev/adms-server/docs/reports/README.md) (`docs/reports/README.md`)

---

## 10. Operational Safety Invariants

1. **Zero Automatic Human Mapping**: No automatic assumption that sequential hardware IDs correspond to Human Master entries.
2. **VERIFIED Mapping Authority**: Scans are attributed strictly when supported by explicit temporal interval mappings (`[valid_from, valid_to)`).
3. **Hardware Lifecycle Protection**: Terminal account disappearance closes active mappings; reappearance increments `account_incarnation`.
4. **Biometric Security**: Biometric templates remain on hardware; templates are never extracted or stored in software databases.
