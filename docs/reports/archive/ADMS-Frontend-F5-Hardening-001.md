# ADMS-Frontend-F5-Hardening-001 — Auth Hardening (Rate Limit + Audit Viewer + Password Change)

**Status:** COMPLETE — F5 HARDENING LIVE
**Date:** 2026-08-13
**Owner gate:** roadmap audit → owner selected **F5 hardening** (approved as planned)

---

## 1. Goal

Harden the F5 auth layer for daily operation:
1. **Rate limiting** — brute-force / abuse backstop (login + global).
2. **Audit trail visibility** — admin viewer over `sync_events` + richer auth
   audit events.
3. **Password self-change** — operators change their own password; other
   sessions revoked.

## 2. Backend changes

- `app/api/ratelimit.py` — in-process **fixed-window** limiter (thread-safe,
  lazy eviction, stdlib only). Accurate because the API runs as a single
  uvicorn worker.
- **Login limit**: per-IP 5/min (`API_LOGIN_RATE_PER_MIN`) → **429
  `RATE_LIMITED`** with `Retry-After`. **Global backstop**: per-IP 600/min
  (`API_GLOBAL_RATE_PER_MIN`) middleware on all `/api/v1`.
  `API_RATE_LIMIT_ENABLED` (default true) toggles all of it.
- **Audit events**: `AUTH_LOGIN_FAILED` (username only, never passwords) on
  failed login; `RATE_LIMITED` on login-scope 429s.
- `GET /api/v1/audit/events` (**ADMIN**, paginated, `event_type` + date
  filters) and `GET /api/v1/audit/event-types` — read-only over `sync_events`.
- `POST /api/v1/auth/change-password` (any authenticated operator): verifies
  current password, updates PBKDF2 hash, **revokes all other tokens** (keeps
  the presenting session), logs `AUTH_PASSWORD_CHANGE`.
- `ApiError` now supports response headers (Retry-After).
- No schema change.

## 3. Frontend changes

- **Audit page** (`/audit`, admin-only nav link): event table with
  event-type filter + refresh, read-only notice.
- **System page**: "Change password" form (current + new ≥12; shows the
  other-sessions-signed-out note; success/error states).

## 4. Tests

- 15 new tests (`tests/test_api_hardening.py`): limiter window/eviction/scope
  independence, login 429 + Retry-After, failed-login audit (no password in
  message), audit endpoint role gate/filters/pagination/422, change-password
  (wrong current 401, weak new 422, revoke-others-keep-current SQL shape).
- **Full suite: 363 passed + 18 subtests / 0 failed** (baseline 348 + 18).
- Frontend `tsc --noEmit` + `vite build` PASS.

## 5. Deployment (ai-brain)

- Commit `dd9ae0e` pushed; ai-brain `git pull --ff-only` → `dd9ae0e`.
- `adms_api` rebuilt (rate-limit env added); `adms_web` rebuilt (Audit +
  System pages). PostgreSQL/MQTT/Collector untouched.

## 6. Live verification (temp admin token, revoked after)

- Audit: event-types 200 (AUTH_LOGIN, AUTH_LOGOUT, ENROLLMENT_*, MAPPING_VERIFIED,
  HISTORICAL_BACKFILL, ROSTER_LIFECYCLE); events 200 **total=437** (full live
  trail — roster lifecycle every 5 min visible).
- **Real rate limiting**: 5 failed logins → 401 each, 6th → **429
  RATE_LIMITED** with Retry-After.
- Audit reflects it: `AUTH_LOGIN_FAILED` total=5, `RATE_LIMITED` total=1.
- Write guard still 403 (production read-only). Revoked token → 401.

## 7. Browser verification (headless Chrome, production URL)

- **Audit page**: header, event-type filter, live events rendered, read-only
  note. **System page**: change-password form + sessions note, RTN ranks still
  render. Console clean.

## 8. Safety / regression

- No DB/schema/device change; the live admin password was **not** touched
  (change-password verified by tests only). 0 active temp tokens remain.
- Backend Foundation **REMAINS 100% COMPLETE**.

## 9. Commits

- `dd9ae0e` — feat: F5 hardening — rate limiting, audit viewer, password
  self-change (# ADMS-Frontend-F5-Hardening-001)

## 10. Next (remaining roadmap)

- **Write UX enablement** for real enrollment/mapping sessions (runbooks F3/F4;
  needs personnel + `API_WRITE_ENABLED=true`).
- Realtime SSE bridge + openapi-typescript codegen (polish).
- Multi-person enrollment validation (personnel), Native Push (firmware).
