# ADMS API Contract (F1 / F5 / F3 / F4)

**PromptID:** `ADMS-Frontend-F1-API-001` / `ADMS-Frontend-F5-Auth-001`
**Status:** IMPLEMENTED / LIVE (backend foundation remains 100% COMPLETE)
**Base URL:** `http://192.168.1.248:8081` (LAN-only)
**OpenAPI:** `http://192.168.1.248:8081/openapi.json` · Swagger UI `/docs`
**Auth (F5):** DB-backed operator accounts, opaque Bearer tokens, roles VIEWER/OPERATOR/ADMIN — strict fail-closed (no/invalid token → 401, insufficient role → 403)
**Write gate:** `API_WRITE_ENABLED=false` by default (defense-in-depth on top of role auth)

---

## 1. Authentication (F5)

- `POST /api/v1/auth/login` `{username, password}` → `{token, role, expires_at, operator_id, username, display_name}` (token TTL default 12h, `API_TOKEN_TTL_HOURS`)
- `POST /api/v1/auth/logout` — revokes the presented token (reversible via `revoked_at`)
- `GET /api/v1/auth/me` — current operator context
- Send `Authorization: Bearer <token>` on all other endpoints.
- Tokens stored only as SHA-256 hashes; passwords PBKDF2-SHA256 (never plaintext).
- First ADMIN bootstrapped via `python -m app.api.bootstrap_admin --username X --password Y` (one-time).

### Role matrix

| Endpoint group | Minimum role |
|---|---|
| All read endpoints (health, dashboard, humans, devices, device-users, attendance, mappings, enrollments, ranks) | VIEWER |
| Enrollment workflow writes (reserve, fingerprint, scan, ready, cancel) | OPERATOR |
| VERIFIED mapping creation | ADMIN |
| Operator management (`/api/v1/operators*`) | ADMIN |
| `/healthz`, `/api/v1/auth/login` | public |
| `/api/v1/auth/logout`, `/api/v1/auth/me` | any authenticated |

All writes additionally require `API_WRITE_ENABLED=true` (403 `WRITE_DISABLED` otherwise).

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
| 403 | `WRITE_DISABLED` | interim write guard (API_WRITE_ENABLED=false) |
| 404 | `NOT_FOUND` | missing resource |
| 409 | `MAPPING_CONFLICT` / `ENROLLMENT_CONFLICT` | state conflict, duplicate reservation, mapping conflict |
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
| GET | `/api/v1/device-users` | `device_id`, `active` filters |
| GET | `/api/v1/device-users/{device_user_pk}` | lifecycle fields; never biometric data |

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
| POST | `/api/v1/enrollments/{id}/create-terminal-account` | **gated** — returns 501 `NOT_IMPLEMENTED` (requires live terminal connection; physical enrollment is operator-performed) |
| POST | `/api/v1/enrollments/{id}/start-fingerprint-enrollment` | **gated** — state machine |
| POST | `/api/v1/enrollments/{id}/confirm-fingerprint` | **gated** — operator confirmation only |
| POST | `/api/v1/enrollments/{id}/start-controlled-scan` | **gated** — opens 5-min window |
| POST | `/api/v1/enrollments/{id}/confirm-controlled-scan` | **gated** — scan_time + window enforced |
| POST | `/api/v1/enrollments/{id}/mark-ready-for-mapping` | **gated** — explicit identity confirmation |
| POST | `/api/v1/enrollments/{id}/cancel` | **gated** — requires notes (reason) |

### Reference
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/reference/ranks` | canonical RTN catalog from `app/rtn_ranks.py` (16 entries) |

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

`API_WRITE_ENABLED=false` (default) → all POST routes return
`403 WRITE_DISABLED` even for ADMIN tokens. F5 auth (roles) is now live; the
write flag remains an additional master switch. Enabling writes is a deliberate
operator decision (`API_WRITE_ENABLED=true` in compose env).

## 8. Environment variables (API container)

| Variable | Default | Purpose |
|---|---|---|
| `API_WRITE_ENABLED` | `false` | write gate (defense-in-depth) |
| `API_TOKEN_TTL_HOURS` | `12` | auth token expiry |
| `API_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | allowlist |
| `API_HOST` | `0.0.0.0` | uvicorn bind inside container |
| `API_PORT` | `8081` | listener port |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | (from .env) | PostgreSQL |
| `MQTT_HOST` / `MQTT_PORT` | `mqtt` / `1883` | MQTT reachability check |

## 9. F2 responsibilities (handoff)

- **F2:** consume only this API. Do NOT connect PostgreSQL directly, talk to
  ZKTeco, or consume Native Push protocol.
- **F2 env vars:** `VITE_API_BASE_URL=http://192.168.1.248:8081`,
  dev CORS origin `http://localhost:5173`; sign-in via `/api/v1/auth/login`.
- **F5 (DONE):** DB-backed operator accounts + role auth live; production CORS
  origin + rate limiting still future hardening.
- **Realtime:** MQTT `attendance/events` → SSE bridge (read-only fan-out)
  or short polling on `GET /api/v1/attendance?from=last_id` (deferred).

STOP.
