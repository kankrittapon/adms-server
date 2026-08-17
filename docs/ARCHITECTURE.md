# ADMS Architecture & System Design

## 1. System Overview

The **Attendance Device Management System (ADMS)** is an enterprise attendance processing, identity reconciliation, and hardware management platform. It connects physical biometric terminals to authoritative personnel rosters, enforcing strict temporal identity resolution and fail-closed operational security.

```
┌────────────────────────────────────────────────────────┐
│             Official Personnel Rosters                 │
│         (Royal Thai Navy Personnel Master)             │
└──────────────────────────┬─────────────────────────────┘
                           │ Excel Ingestion (120 records)
                           ▼
               ┌───────────────────────┐
               │    human_employees    │
               │  (Immutable Identity) │
               └───────────┬───────────┘
                           │
                           │ 6-Step Controlled Enrollment
                           │ + Temporal Identity Resolution
                           ▼
┌────────────────────────────────────────────────────────┐
│               PostgreSQL Database (adms)               │
│  ├── human_employees       (authoritative master)      │
│  ├── devices               (hardware registry)         │
│  ├── device_users          (discovered terminal accts) │
│  ├── employee_device_mappings (temporal [from, to))    │
│  ├── attendance_logs       (immutable scan events)     │
│  ├── enrollment_sessions   (state machine)             │
│  ├── operators / api_tokens(PBKDF2 auth & RBAC)        │
│  └── sync_events           (append-only audit trail)   │
└───────────▲──────────────────────────────▲─────────────┘
            │ SQL & Transactions           │ SQL & Transactions
            │                              │
┌───────────┴───────────┐      ┌───────────┴─────────────┐
│  adms_zkteco_listener │      │        adms_api         │
│  (Python Collector)   │      │    (FastAPI Backend)    │
└───────────▲───────────┘      └───────────▲─────────────┘
            │                              │
     TCP 4370 (ZK Protocol)          HTTP & SSE (8081)
            │                              │
┌───────────┴───────────┐      ┌───────────┴─────────────┐
│  ZKTeco ZEM560_TFT    │      │        adms_web         │
│  Biometric Terminal   │      │    (React/TS Console)   │
│  192.168.1.201:4370   │      │  http://192.168.1.248   │
└───────────────────────┘      └─────────────────────────┘
```

---

## 2. Core Subsystems

### 2.1 Ingestion Collector (`app/collector.py`)
- **Protocol**: ZKTeco standalone binary protocol over TCP port 4370 (`pyzk==0.9`, Comm Key `600`).
- **State Machine**: Finite state machine with states `DISCONNECTED`, `CONNECTING`, `LIVE`, `BACKFILLING`, `RECONNECT_DELAY`.
- **Hybrid Event Pipeline**:
  - Realtime event capture via socket poll.
  - Automatic historical log backfill on connection establishment.
  - Multi-layer deduplication over `(user_id, device_ip, scan_time)`.
  - Client-side timestamp normalization to UTC with `ZoneInfo("Asia/Bangkok")`.
- **Health Monitoring**: Emits atomic health state to `/tmp/collector_health.json`, shared with `adms_api` via Docker volume.

### 2.2 Device Command Bus (`app/device_command_bus.py`)
- **Serialized Hardware Control**: Manages single-socket exclusive access to the ZKTeco terminal without closing or restarting the Collector.
- **Transport**: MQTT request/response queue over Mosquitto (`adms/device/command/request` and `adms/device/command/response`).
- **Command Dispatch**: Enables web browser-driven terminal account creation (`set_user()`) executed safely inside the Collector's active session.

### 2.3 Database & Temporal Identity Engine (`app/db.py`)
- **Strict Separation of Master & Hardware Identities**:
  - `human_employees`: Authoritative Human identity (UUID PK, name, rank, branch, `production_scope`, `english_name`).
  - `device_users`: Ephemeral on-device account representation discovered via roster sync (`account_incarnation` tracked).
- **Temporal Interval Resolver**:
  - Historical scans resolve using `[valid_from, valid_to)` semantics:
    $$\text{scan\_time} \ge \text{valid\_from} \quad \land \quad (\text{valid\_to IS NULL} \;\lor\; \text{scan\_time} < \text{valid\_to})$$
  - Unmapped attendance is preserved cleanly (`employee_id = NULL`).
  - Ambiguity defense: if more than one active mapping matches, resolution fails closed to `NULL` to prevent misattribution.

### 2.4 API Layer (`app/api/`)
- **Framework**: FastAPI (Python 3.12, Uvicorn, Pydantic v2).
- **OpenAPI Codegen**: Automatic snapshot generation (`frontend/openapi.json`) and typed client derivation (`frontend/src/api/client.ts`).
- **Authentication**: DB-backed PBKDF2-SHA256 password hashing with 12h opaque Bearer tokens.
- **Production Write Gate**: Fail-closed master gate (`API_WRITE_ENABLED=false` default) guarding all state-mutating endpoints.
- **Realtime Event Streaming**: `/api/v1/stream/attendance` SSE endpoint bridging internal MQTT scan events to connected web browsers.

### 2.5 Web Management Console (`frontend/`)
- **Stack**: React 18, TypeScript (strict), Vite 5, Tailwind CSS.
- **Localization**: Lightweight typed i18n engine (`th` default, `en` switchable) persisted in `localStorage`.
- **Role-Aware Navigation**: Dynamic navigation structure reflecting operator capabilities.
- **Guided Workflows**: Dedicated Enrollment Workspace with visual step guidance, live scan detection, and audit inspection.

---

## 3. Core Identity Invariants

1. **No Automatic Mapping**: Excel row order, import sequencing, and terminal IDs are completely decoupled. `Excel Row != Terminal ID`.
2. **VERIFIED Mapping Required**: An attendance scan is only attributed to a Human Master identity if an explicit `VERIFIED` temporal mapping exists covering the scan timestamp.
3. **Lifecycle & Incarnation Protection**: Inactive terminal accounts have their open mappings closed automatically. Reappearing accounts increment `account_incarnation` and require fresh verification before any new mapping is formed.
4. **Fail-Closed Write Safety**: No write operation can modify production state or device accounts unless authorized by both RBAC role checks and the `API_WRITE_ENABLED=true` master switch.
