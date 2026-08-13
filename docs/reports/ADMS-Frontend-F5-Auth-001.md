# ADMS-Frontend-F5-Auth-001 — Operator Auth & Role-Based Access

**PromptID:** `ADMS-Frontend-F5-Auth-001`
**Owner gate:** F3 gate → owner selected **B. F5 AUTH EARLY**; auth mechanism: **DB-backed operator accounts** + **STRICT posture**
**Result:** F5 AUTH IMPLEMENTED + LIVE VERIFIED — strict 401/403 fail-closed
**Date:** 2026-08-13

---

## 1. Design (owner-approved)

- **DB-backed operators** (`operators` table): username, display_name, role
  (VIEWER / OPERATOR / ADMIN), PBKDF2-SHA256 password hash (260k iterations,
  per-user salt). No plaintext passwords anywhere.
- **Opaque Bearer tokens** (`api_tokens` table): stored ONLY as SHA-256 hashes,
  with role snapshot + expiry (`API_TOKEN_TTL_HOURS`, default 12h) + reversible
  revocation (`revoked_at`).
- **Strict posture:** missing/invalid/expired/revoked token → 401 `UNAUTHORIZED`;
  insufficient role → 403 `FORBIDDEN`. `/healthz` stays public for the Docker
  healthcheck; `/api/v1/auth/login` is the only other public route.
- **Role hierarchy:** VIEWER (1) < OPERATOR (2) < ADMIN (3).
- **Defense in depth:** `API_WRITE_ENABLED=false` (default) still blocks all
  writes even with an ADMIN token (403 `WRITE_DISABLED`).
- **Bootstrap:** first ADMIN created once via CLI
  `python -m app.api.bootstrap_admin --username admin --password …`
  (refuses if any operator exists; never auto-created from env).

## 2. Schema — `sql/008_operator_auth_schema.sql` (additive)

- `operators` (operator_id, username UNIQUE, display_name, role CHECK, password_hash, active)
- `api_tokens` (token_id, operator_id FK, token_hash UNIQUE, role CHECK, issued_at, expires_at, revoked_at, last_used_at)
- indexes: `idx_api_tokens_hash`, `idx_api_tokens_operator_active`
- Applied on ai-brain with verified pre-backup (`adms_pre_f5auth_20260813_212454.dump`)

## 3. API surface added

| Method | Path | Access |
|---|---|---|
| POST | `/api/v1/auth/login` | public |
| POST | `/api/v1/auth/logout` | any authenticated (revokes presented token) |
| GET | `/api/v1/auth/me` | any authenticated |
| GET | `/api/v1/operators` | ADMIN |
| POST | `/api/v1/operators` | ADMIN (password ≥12 chars, PBKDF2-hashed) |
| POST | `/api/v1/operators/{id}/toggle-active` | ADMIN (self-deactivation blocked) |

Role gating applied to existing surface:
- All read routers: VIEWER+
- Enrollment workflow writes: OPERATOR+ (plus `API_WRITE_ENABLED`)
- VERIFIED mapping creation: ADMIN+ (plus `API_WRITE_ENABLED`)

## 4. Implementation

- `app/api/auth.py` — PBKDF2 hashing (`hash_password`/`verify_password`, constant-time),
  token issue (`issue_token`), `verify_token_row`, `authenticate_operator`, `role_required`
- `app/api/dependencies.py` — `OperatorContext`, `_load_token_context` (Bearer → DB lookup),
  `require_auth`, `require_role(min_role)` factory, `require_writes` (write flag)
- `app/api/routers/auth.py` — login/logout/me
- `app/api/routers/operators.py` — admin operator management
- `app/api/bootstrap_admin.py` — one-time initial ADMIN CLI
- `app/api/main.py` — app-level `/healthz` (public) + router-level role dependencies
- Frontend: `Login` page, Bearer header in `client.ts`, `RequireAuth` guard,
  operator identity + sign-out in `Layout`

## 5. Tests

- `tests/test_api_auth.py` (28 new): hashing round-trip/salting/garbage,
  token verify (valid/expired/revoked/inactive/None), login success/wrong-password/
  unknown/inactive, strict 401 on every route without token, bad token 401,
  role matrix (viewer read OK / viewer write 403 / operator reserve 201 /
  operator mapping 403 / admin mapping 201), write-flag blocks even ADMIN,
  operator mgmt (viewer 403 / admin create+list / weak password 422 /
  self-deactivation 422)
- `tests/test_api.py` updated for auth-aware contexts
- **Full suite: 336 passed + 18 subtests, 0 failed** (308 → +28)

## 6. Deployment (ai-brain)

- git pull ff-only → `7aca662`
- pre-backup `adms_pre_f5auth_20260813_212454.dump` (58,823 B, SHA256 `03aac28e…`)
- migration 008 applied (operators=0, api_tokens=0 initially)
- `adms_api` rebuilt (compose, API service only; PostgreSQL/MQTT/Collector untouched)
- bootstrap: `admin` ADMIN created (operator_id 1)
- post-backup `adms_post_f5auth_20260813_212601.dump` (65,640 B, SHA256 `85ee9398…`, pg_restore -l PASS)

## 7. Live verification

- Login (admin) → 200 token · `/me` → correct operator
- Authenticated reads → 200 (dashboard 120/12, humans, mappings, ranks)
- Write gate → 403 WRITE_DISABLED (ADMIN token, flag still off)
- Operators admin list → 200
- Wrong password → 401 · logout → token revoked → 401 on reuse
- No token → 401 · bad token → 401 · `/healthz` → 200 (public)
- DB regression clean: 120/120/1/3/1/1/12 attendance + 1 operator
- Containers: restarts 0 · Collector LIVE/HEALTHY (HC_RC=0)
- Frontend: unauthenticated `/` → Login page; API-only data flow intact

## 8. Security posture

- LAN-only bind (`192.168.1.248:8081`) · CORS restricted allowlist
- Passwords PBKDF2-hashed; tokens stored hashed; revocation reversible
- No secrets in repo; bootstrap password passed at CLI, rotate after first use
- No biometric data, no raw_payload by default, no destructive routes

## 9. Git

- commit `7aca662` `feat: add F5 auth — DB operator accounts with role tokens`
- TELEPHONE == origin/main == ai-brain (`7aca662`), clean trees

STOP.
