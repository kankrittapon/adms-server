# ADMS API Contract (F1)

**PromptID:** `ADMS-Frontend-F1-API-001`
**Status:** IMPLEMENTED / LIVE (backend foundation remains 100% COMPLETE)
**Base URL:** `http://192.168.1.248:8081` (LAN-only)
**OpenAPI:** `http://192.168.1.248:8081/openapi.json` · Swagger UI `/docs`
**Write gate:** `API_WRITE_ENABLED=false` by default (TEMPORARY WRITE SAFETY, NOT final auth — F5)

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
| GET | `/api/v1/attendance/{attendance_id}` | joined device + Human summary |
| GET | `/api/v1/attendance/{attendance_id}/raw-payload` | explicit diagnostics endpoint |

### Mappings
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/mappings` | `employee_id`, `device_user_pk`, `mapping_status` filters |
| GET | `/api/v1/mappings/{mapping_id}` | temporal fields |
| POST | `/api/v1/mappings` | **gated** — canonical `app.mapping.create_verified_mapping()` |

### Enrollments
| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/enrollments` | `status`, `employee_id`, `device_id` filters |
| GET | `/api/v1/enrollments/{enrollment_id}` | full workflow state |
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

## 7. Write safety (TEMPORARY)

`API_WRITE_ENABLED=false` (default) → all POST routes return
`403 WRITE_DISABLED`. This is an interim guard, not final authentication.
F5 owns full auth/production hardening. Enabling writes is a deliberate
operator decision (`API_WRITE_ENABLED=true` in compose env).

## 8. Environment variables (API container)

| Variable | Default | Purpose |
|---|---|---|
| `API_WRITE_ENABLED` | `false` | interim write gate |
| `API_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | allowlist |
| `API_HOST` | `0.0.0.0` | uvicorn bind inside container |
| `API_PORT` | `8081` | listener port |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | (from .env) | PostgreSQL |
| `MQTT_HOST` / `MQTT_PORT` | `mqtt` / `1883` | MQTT reachability check |

## 9. F2 / F5 responsibilities (handoff)

- **F2:** consume only this API. Do NOT connect PostgreSQL directly, talk to
  ZKTeco, or consume Native Push protocol.
- **F2 env vars:** `VITE_API_BASE_URL=http://192.168.1.248:8081`,
  `VITE_API_WRITE_ENABLED` (mirror), dev CORS origin `http://localhost:5173`.
- **F5:** replace the interim write guard with real authentication
  (roles viewer/operator/admin), production CORS origin, rate limiting.
- **Realtime:** MQTT `attendance/events` → SSE bridge (read-only fan-out)
  or short polling on `GET /api/v1/attendance?from=last_id` (deferred).

STOP.
