# ADMS API Contract (F1 / F5 / F3 / F4 / P0P1-Hardening-007)

**PromptID:** `ADMS-Frontend-F1-API-001` / `ADMS-Frontend-F5-Auth-001` / `ADMS-FullSystem-P0P1-Hardening-007`
**Status:** IMPLEMENTED / LIVE (backend foundation remains 100% COMPLETE). The write-session endpoints and two-layer write model described in §1a below are **implemented in source (Phases A–E) but not yet deployed to production** — see [STATUS.md](../STATUS.md) and [docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md](reports/ADMS-FullSystem-P0P1-Hardening-007.md). Production currently still enforces only the Layer-1 `API_WRITE_ENABLED` gate described below, with `API_WRITE_ENABLED=false`.
**Base URL:** `http://192.168.1.248:8081` (LAN-only)
**OpenAPI:** `http://192.168.1.248:8081/openapi.json` · Swagger UI `/docs`
**Frontend types (codegen):** committed snapshot `frontend/openapi.json` + `openapi-typescript` → `frontend/src/api/generated.ts`; `types.ts` re-exports generated components. Regenerate with `npm run codegen:api`; `tests/test_openapi_contract.py` fails when the snapshot is stale (`ADMS-Frontend-Codegen-001`).
**Auth (F5):** DB-backed operator accounts, opaque Bearer tokens, roles VIEWER/ENROLLMENT_OPERATOR/OPERATOR/ADMIN — strict fail-closed (no/invalid token → 401, insufficient role → 403)
**Write gate:** two layers as of Hardening-007 — see §1a. `API_WRITE_ENABLED=false` by default (Layer 1, defense-in-depth on top of role auth; production value today).

---

## 1. Authentication (F5)

- `POST /api/v1/auth/login` `{username, password}` → `{token, role, expires_at, operator_id, username, display_name}` (token TTL default 12h, `API_TOKEN_TTL_HOURS`; per-IP rate limit default 5/min → 429 `RATE_LIMITED` + `Retry-After`)
- `POST /api/v1/auth/logout` — revokes the presented token (reversible via `revoked_at`)
- `POST /api/v1/auth/change-password` `{current_password, new_password ≥ 12}` — rehashes and revokes all other sessions (keeps current); logs `AUTH_PASSWORD_CHANGE`
- `GET /api/v1/auth/me` — current operator context; response now additionally includes `write_session` (see §1a), reflecting the Layer-2 status even though Layer 2 is not yet production-active
- Send `Authorization: Bearer <token>` on all other endpoints.
- Tokens stored only as SHA-256 hashes; passwords PBKDF2-SHA256 (never plaintext).
- First ADMIN bootstrapped via `python -m app.api.bootstrap_admin --username X --password Y` (one-time).
- Auth/session-maintenance endpoints (`login`, `logout`, `me`, `change-password`) are exempt from both write-gate layers by design — they establish or terminate the caller's own session, not domain state, so an operator can always log in or change a compromised password even while writes are locked.

### Role matrix

| Endpoint group | Minimum role |
|---|---|
| All read endpoints (health, dashboard, humans, devices, device-users, attendance, mappings, enrollments, ranks) | VIEWER |
| Enrollment workflow writes (reserve, terminal account, fingerprint, scan, ready, cancel) | ENROLLMENT_OPERATOR (also OPERATOR, ADMIN) |
| VERIFIED mapping creation | ADMIN |
| Personnel English name edit (`PATCH /humans/{id}`) | ADMIN |
| Operator management (`/api/v1/operators*`) | ADMIN |
| Write-session status (`GET /write-session`) | any authenticated |
| Write-session open/close (`POST /write-session/open`, `/close`) | ADMIN |
| `/healthz`, `/api/v1/auth/login` | public |
| `/api/v1/auth/logout`, `/api/v1/auth/me`, `/api/v1/auth/change-password` | any authenticated |

All domain-mutating writes require `API_WRITE_ENABLED=true` (Layer 1; 403 `WRITE_DISABLED` otherwise) — this now correctly includes operator management, which previously bypassed the gate (fixed in Hardening-007 Phase A). Once Phase F is deployed, the same writes additionally require an active runtime write session (Layer 2; see §1a).

## 1a. Write-Session Endpoints (Layer 2 — source-complete, not yet production-active)

Implemented in `app/api/routers/write_session.py`. Requires migration `012_write_session_schema.sql`, which has not yet been applied to production — these endpoints will 500 against the production database until Phase F applies it.

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/api/v1/write-session` | any authenticated | Read-only status: `{active, session_id?, opened_by?, opened_by_name?, opened_at?, expires_at?, reason?, closed_at?}`. Also lazily reaps (and audits, at most once) an expired-but-unclosed session as a side effect. |
| POST | `/api/v1/write-session/open` | ADMIN | Body `{reason}`. Fixed 30-minute duration (not client-configurable). Requires Layer 1 (`API_WRITE_ENABLED=true`) to succeed — Layer 1 unconditionally gates Layer 2. Rejected with `WRITE_SESSION_ALREADY_ACTIVE` (409) if one is already open. |
| POST | `/api/v1/write-session/close` | ADMIN | No body. Idempotent — closing when nothing is active returns `{active: false, closed_at: null}`, not an error. **Not** gated by Layer 1 — closing (a de-escalation) must always be available to an ADMIN even if the infrastructure gate is already off. |

At most one session may be active at a time, enforced via a Postgres transaction-scoped advisory lock (`pg_advisory_xact_lock`) so concurrent open attempts across any number of API workers cannot both succeed. Effective write permission for every domain-mutating endpoint:

```
allow_write = API_WRITE_ENABLED (Layer 1) AND write_session_active (Layer 2) AND role_permits_action
```

New error codes (added alongside the existing `WRITE_DISABLED`, which is unchanged and still governs Layer 1):

| Code | Status | Meaning |
|---|---|---|
| `WRITE_SESSION_REQUIRED` | 403 | Layer 1 is open but no runtime write session is active. |
| `WRITE_SESSION_EXPIRED` | 403 | A session existed but its `expires_at` has passed — distinct from "never opened" so the frontend can show "your session expired" rather than a generic locked message. |
| `WRITE_SESSION_ALREADY_ACTIVE` | 409 | `open` attempted while a session is already active. |

---

## 1. Stack

- FastAPI `0.135.3` · Pydantic v2 `2.12.5` · Uvicorn `0.40.0`
- Separate container `adms_api` (image built from `docker/Dockerfile.api`),
  isolated from the polling Collector (`adms_zkteco_listener`)
- LAN-only bind `192.168.1.248:8081` — no public exposure

## 2. Error model

Every error uses the envelope:

```json
{"error": {"code": "...", "message": "..."}}
```

| Status | Code | Meaning |
|---|---|---|
| 400 | (domain) | validation / domain error |
| 403 | `WRITE_DISABLED` | Layer 1 write guard (API_WRITE_ENABLED=false) |
| 403 | `WRITE_SESSION_REQUIRED` | Layer 2 — no runtime write session active (source-complete, inert until Phase F) |
| 403 | `WRITE_SESSION_EXPIRED` | Layer 2 — session existed but expired (source-complete, inert until Phase F) |
| 404 | `NOT_FOUND` | missing resource |
| 409 | `MAPPING_CONFLICT` / `ENROLLMENT_CONFLICT` | state conflict, duplicate reservation, mapping conflict |
| 409 | `WRITE_SESSION_ALREADY_ACTIVE` | a write session is already open (source-complete, inert until Phase F) |
| 422 | `VALIDATION_ERROR` | request validation |
| 500 | `INTERNAL_ERROR` | unexpected internal error (no secrets/stack/SQL leaked) |

## 3. Endpoint table

### System / health
| Method | Path | Notes |
|---|---|---|
| GET | `/healthz` | API process liveness, no dependencies |
| GET | `/api/v1/health` | DB (required), MQTT (optional), collector state summary |
| GET | `/api/v1/dashboard/summary` | single aggregation query for F2/F3 dashboard |

### Human Master
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/humans` | pagination, `production_scope`, `search`, `category` filters |
| GET | `/api/v1/humans/{employee_id}` | UUID validated; 404 when missing; rank metadata included |

### Devices
| Method | Path |
|---|---|
| GET | `/api/v1/devices` |
| GET | `/api/v1/devices/{device_id}` |

### Device users
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/device-users` | `device_id`, `active` filters; includes `account_incarnation` (how many times the terminal account has been (re)created) |
| GET | `/api/v1/device-users/{device_user_pk}` | lifecycle fields incl. `account_incarnation`; never biometric data |

### Realtime stream (SSE)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/stream/attendance` | **SSE** (VIEWER+) — live `ATTENDANCE_SCAN` events fan-out from the Collector's MQTT `attendance/events` topic; heartbeat `: ping` every 15s; **live-only (no replay)** — use the attendance GET endpoints for history; Bearer via `fetch` + ReadableStream (no token in URL) |

### Attendance
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/attendance` | `date_from`, `date_to`, `employee_id`, `device_user_pk`, `status` filters; no raw_payload |
| GET | `/api/v1/attendance/unattributed` | **ADMIN** — read-only reconciliation diagnostics: unattributed rows with canonical resolver reasoning (NO_DEVICE_USER/LEGACY_USER/NO_MAPPING/BEFORE_VALID_FROM/INSIDE_INTERVAL/AFTER_VALID_TO); never writes |
| GET | `/api/v1/attendance/{attendance_id}` | joined device + Human summary |
| GET | `/api/v1/attendance/{attendance_id}/raw-payload` | explicit diagnostics endpoint |

### Mappings
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/mappings` | `employee_id`, `device_user_pk`, `mapping_status` filters |
| GET | `/api/v1/mappings/eligibility` | **ADMIN** — READY_FOR_MAPPING enrollments with controlled-scan evidence (excludes already-mapped device users); feeds the mapping form |
| GET | `/api/v1/mappings/{mapping_id}` | temporal fields |
| POST | `/api/v1/mappings` | **gated + ADMIN** — canonical `app.mapping.create_verified_mapping()` |

### Enrollments
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/enrollments` | `status`, `employee_id`, `device_id` filters |
| GET | `/api/v1/enrollments/{enrollment_id}` | full workflow state |
| GET | `/api/v1/enrollments/{enrollment_id}/next-actions` | valid next operator actions from the canonical state machine (`ENROLLMENT_ACTIONS` + `ALLOWED_TRANSITIONS`); empty at READY_FOR_MAPPING / terminal states |
| POST | `/api/v1/enrollments/reserve` | **gated** — `reserve_next_device_user_id()` |
| POST | `/api/v1/enrollments/{id}/create-terminal-account` | **gated** — dispatches `CREATE_TERMINAL_ACCOUNT` over the `DeviceCommandBus` (MQTT) to the live Collector, which performs the serialized `set_user()` on its single exclusive terminal connection; 409 `ENROLLMENT_CONFLICT` on invalid state/duplicate, 503 `DEVICE_UNAVAILABLE` on command timeout. A direct-executor test-injection path exists for unit tests only. |
| POST | `/api/v1/enrollments/{id}/start-fingerprint-enrollment` | **gated** — state machine |
| POST | `/api/v1/enrollments/{id}/confirm-fingerprint` | **gated** — operator confirmation only |
| POST | `/api/v1/enrollments/{id}/start-controlled-scan` | **gated** — opens 5-min window |
| POST | `/api/v1/enrollments/{id}/confirm-controlled-scan` | **gated** — scan_time + window enforced |
| POST | `/api/v1/enrollments/{id}/mark-ready-for-mapping` | **gated** — explicit identity confirmation |
| POST | `/api/v1/enrollments/{id}/cancel` | **gated** — requires notes (reason) |

### Audit (F5 hardening, ADMIN)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/audit/events` | paginated `sync_events` with `event_type` + `date_from`/`date_to` filters; read-only |
| GET | `/api/v1/audit/event-types` | distinct event types for the filter UI |

### Reference
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/reference/ranks` | canonical RTN catalog from `app/rtn_ranks.py` (16 entries) |

### Operator management (ADMIN)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/operators` | list operator accounts |
| POST | `/api/v1/operators` | **gated** — create operator account (username/display_name/password/role). Previously bypassed `API_WRITE_ENABLED` entirely; fixed in Hardening-007 Phase A — this is now correctly treated as a protected production write. |
| POST | `/api/v1/operators/{id}/toggle-active` | **gated** — activate/deactivate an operator account. Same Phase A fix applies. |

### Write session (see §1a)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/write-session` | any authenticated — status |
| POST | `/api/v1/write-session/open` | ADMIN, **gated by Layer 1 only** |
| POST | `/api/v1/write-session/close` | ADMIN, **not gated** (always available) |

## 4. Pagination

List endpoints: `limit` (1–200, default 50) + `offset` (default 0).
Response: `{"items": [...], "total": N, "limit": L, "offset": O}`.

## 5. Timestamps

All timestamps are timezone-aware ISO 8601 (UTC offset preserved from DB).
Attendance `scan_time` is canonical UTC; timezone normalization is owned by
`normalize_device_timestamp()` — never re-implemented in the API.

## 6. Data safety rules (enforced)

- **No raw_payload by default** — only via explicit `/raw-payload` diagnostics endpoint.
- **No biometric data** — device-user endpoints expose lifecycle fields only.
- **No destructive routes** — zero DELETE endpoints in F1.
- **No automatic mapping** — the mapping POST wraps the single canonical
  `create_verified_mapping()` with full evidence preconditions.
- **Rank is metadata only** — never used for identity matching.
- **No SQL injection** — all repository queries are parameterized.
- **CORS** — explicit env allowlist (`API_CORS_ORIGINS`), never `*` with credentials.

## 7. Write safety (defense-in-depth)

`API_WRITE_ENABLED=false` (default) → all domain-mutating POST/PATCH routes
return `403 WRITE_DISABLED` even for ADMIN tokens. F5 auth (roles) is live;
the write flag is an additional master switch (Layer 1), independent of role
authorization. Enabling writes today is a server-owner decision
(`API_WRITE_ENABLED=true` in compose env, requiring an `api` container
recreate) — this remains the only mechanism in production.

As of Hardening-007 (Phases A–E, source-complete), a second independent
layer exists: a runtime write session (§1a), opened/closed by an ADMIN from
the browser, auto-expiring after 30 minutes. Both layers are required for a
write to succeed once Phase F is deployed; until then, Layer 2 is present in
the code and schema but has no effect in production because migration 012
has not been applied and the deployed `api`/`web` containers predate this
work.

## 8. Environment variables (API container)

| Variable | Default | Purpose |
|---|---|---|
| `API_WRITE_ENABLED` | `false` | write gate (defense-in-depth) |
| `API_TOKEN_TTL_HOURS` | `12` | auth token expiry |
| `API_RATE_LIMIT_ENABLED` | `true` | master switch for rate limiting |
| `API_LOGIN_RATE_PER_MIN` | `5` | per-IP login attempts per minute (429 + Retry-After) |
| `API_GLOBAL_RATE_PER_MIN` | `600` | per-IP backstop for all /api/v1 traffic |
| `API_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.248:8082` | allowlist (dev + production console) |
| `API_HOST` | `0.0.0.0` | uvicorn bind inside container |
| `API_PORT` | `8081` | listener port |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | (from .env) | PostgreSQL |
| `MQTT_HOST` / `MQTT_PORT` | `mqtt` / `1883` | MQTT reachability check |

## 9. Production console (F6)

- Console (nginx SPA): **`http://192.168.1.248:8082`** — container `adms_web`,
  LAN-only bind; SPA fallback + gzip + security headers. Cross-origin calls to
  this API with `Authorization: Bearer` (no cookies); the origin is on the CORS
  allowlist. Dev flow (`npm run dev` at `http://localhost:5173`) unchanged.

## 10. F2 responsibilities (handoff)

- **F2:** consume only this API. Do NOT connect PostgreSQL directly, talk to
  ZKTeco, or consume Native Push protocol.
- **F2 env vars:** `VITE_API_BASE_URL=http://192.168.1.248:8081`,
  dev CORS origin `http://localhost:5173`; sign-in via `/api/v1/auth/login`.
- **F5 (DONE):** DB-backed operator accounts + role auth live; production CORS
  origin + rate limiting still future hardening.
- **Realtime:** MQTT `attendance/events` → SSE bridge (read-only fan-out)
  or short polling on `GET /api/v1/attendance?from=last_id` (deferred).
- **Codegen (DONE):** `npm run codegen:api` exports `app.openapi()` →
  `frontend/openapi.json` and regenerates `frontend/src/api/generated.ts`;
  `tests/test_openapi_contract.py` guards drift. **Typed client:** `client.ts`
  method signatures derive from the generated `operations` types via
  `QueryOf`/`BodyOf`/`JsonResponse` helpers in `types.ts`; all write/transition
  response routes declare `response_model=` so the spec is precise, not
  `unknown` (`ADMS-Frontend-Codegen-001`, typed-client phase; commit `274fb06`).

STOP.
