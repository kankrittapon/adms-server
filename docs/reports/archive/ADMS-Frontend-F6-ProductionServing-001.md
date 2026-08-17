# ADMS-Frontend-F6-ProductionServing-001 — Production Frontend Serving

**Status:** COMPLETE — PRODUCTION CONSOLE LIVE AT `http://192.168.1.248:8082`
**Date:** 2026-08-13
**Owner gate:** Roadmap audit → owner selected **A — Production frontend serving** (recommended)

---

## 1. Goal

Make the F1–F4 console actually usable from any LAN browser. Previously the
frontend only ran via `npm run dev` on a workstation. Per the architecture
plan ("static build served by the API or a tiny nginx", same ai-brain host),
a tiny nginx container now serves the production SPA.

## 2. Deliverables

- `docker/frontend.Dockerfile` — multi-stage: Node 22 builds `frontend/dist`
  (`npm ci` + `npm run build`) inside the image; `nginx:alpine` serves it.
  `dist/` stays gitignored; nothing built is committed.
- `docker/nginx.conf` — SPA fallback (`try_files … /index.html`), gzip,
  security headers (`X-Content-Type-Options`, `X-Frame-Options`, referrer),
  dotfile/source-map denial, immutable cache for hashed assets.
- `docker-compose.yml` — new `web` service: container `adms_web`,
  **LAN-only bind `192.168.1.248:8082:80`** (8082 verified free; 8000/8080/
  8081/3000/3001/5678 in use by other projects), healthcheck via `wget`.
- API CORS: default `API_CORS_ORIGINS` now includes
  `http://192.168.1.248:8082` (dev origins retained).

## 3. Design

- **Cross-origin by design**: nginx serves only static; the SPA calls the API
  at `http://192.168.1.248:8081` with `Authorization: Bearer` (no cookies), so
  the explicit CORS allowlist applies. The client's default
  `VITE_API_BASE_URL` is exactly the LAN API URL — no client code change.
- No auth change: login/role flow (F5) unchanged; `/login` redirect for
  unauthenticated visitors works from the production origin.

## 4. Deployment (ai-brain)

- Commit `0290744` pushed; ai-brain `git pull --ff-only` → `0290744`.
- `docker compose build web` (npm ci + vite build inside the image) then
  `docker compose up -d web api` — the API container was recreated only to
  pick up the new CORS origin (read-only service, no state). PostgreSQL/MQTT/
  Collector untouched.

## 5. Server-side live verification

- `GET http://192.168.1.248:8082/` → **200**, ADMS SPA, `Server: nginx/1.27.5`.
- SPA fallback `GET /mappings` → **200** index.html (client routing works).
- CORS preflight `OPTIONS /api/v1/humans` with `Origin: http://192.168.1.248:8082`
  → `access-control-allow-origin: http://192.168.1.248:8082`.
- API auth still strict (no token → 401).

## 6. Browser E2E (headless Chrome against the production URL)

- Unauthenticated root → **redirected to `/login`**, login page renders.
- With a temp ADMIN token (seeded, revoked after): Dashboard renders live data
  (humans 120, attendance 12); Mappings shows the admin panel + VERIFIED
  mapping 1 (pilot Human); Attendance shows the reconciliation section with
  7 `LEGACY_USER` rows. **Console errors: none.**
- Token revoked after the run (0 active tokens remain).

## 7. Safety / regression

- No database/schema/device change. adms_api recreated with CORS env only.
- Backend Foundation **REMAINS 100% COMPLETE**; write gate untouched
  (`API_WRITE_ENABLED=false`).
- LAN-only binds (8081 API, 8082 web); no public exposure; no secrets.

## 8. Usage

```text
Console:  http://192.168.1.248:8082   (nginx SPA)
API:      http://192.168.1.248:8081   (OpenAPI /docs)
Dev:      cd frontend && npm run dev  (http://localhost:5173, CORS allowlisted)
```

## 9. Commits

- `0290744` — feat: production frontend serving — nginx container on ai-brain
  (# ADMS-Frontend-F6-ProductionServing-001)

## 10. Next (from the roadmap audit)

- **Write UX enablement** for real enrollment/mapping sessions (runbooks in
  F3/F4) — needs personnel + `API_WRITE_ENABLED=true`.
- **F5 hardening**: production rate limiting, audit-log viewer (sync_events),
  token rotation, operator password self-change.
- Realtime SSE + openapi-typescript codegen (polish).
