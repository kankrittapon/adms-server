# ADMS-Frontend-F2-Foundation-001 — Frontend Foundation (React + TS + Vite)

**PromptID:** `ADMS-Frontend-F1-API-001` (owner gate §51 → option A) / F2 sub-phase
**Status:** F2 FOUNDATION COMPLETE — read views live against the F1 API
**Date:** 2026-08-13
**Prerequisites:** Backend Foundation 100% COMPLETE · F1 API 100% COMPLETE (`9cd92ed`)

---

## 1. Stack (owner-approved)

- **React 18.3 + TypeScript 5.6 (strict) + Vite 5.4** (React Router 6)
- API client: hand-typed fetch layer mirroring the F1 OpenAPI contract
  (openapi-typescript codegen remains an option for F3+)
- No direct PostgreSQL / ZKTeco / Native Push access — API only

## 2. Project structure (`frontend/`)

```
frontend/
  package.json · package-lock.json · tsconfig.json · vite.config.ts
  index.html · .env.development · .gitignore
  src/
    main.tsx · App.tsx · styles.css · vite-env.d.ts
    api/client.ts · api/types.ts      (typed client + F1 contract types)
    hooks/useApi.ts                   (fetch hook: data/loading/error/reload)
    components/Layout.tsx · Status.tsx
    pages/ Dashboard · Personnel(+detail) · Devices · Attendance
           Enrollments · Mappings · System
```

## 3. Views implemented (read-only, per plan §4)

| Route | View | Live data verified |
|---|---|---|
| `/` | Dashboard (summary cards, enrollments by status) | humans 120, attendance 12, collector state |
| `/personnel` + `/personnel/:employeeId` | Human Master list (scope/search/pagination) + detail | กฤตพล หมาดเส็น, production/excluded badges, rank metadata |
| `/devices` | Device + device-user roster | SONIC ZEM560, user 1001 active, legacy 1/2 inactive |
| `/attendance` | History with status filter + limit | ON_TIME/LATE, unmapped labels |
| `/enrollments` | Workflow state (read-only) | READY_FOR_MAPPING, reserved_by owner-krittaphol |
| `/mappings` | VERIFIED temporal mappings | mapping 1, CONTROLLED_SCAN |
| `/system` | Health + RTN rank reference | HEALTHY, 16 canonical ranks |

## 4. Safety boundaries (F2)

- **No write UI.** All write endpoints remain `API_WRITE_ENABLED=false` (403).
- No biometric data rendered; attendance shows attribution, never raw_payload.
- Rank rendered as display metadata only — never used for identity.
- `API_CORS_ORIGINS` includes `http://localhost:5173` + `http://127.0.0.1:5173` (verified).

## 5. Verification

- `tsc --noEmit` PASS (strict) · `vite build` PASS (45 modules, dist 189 kB JS / 59 kB gzip)
- Headless Chrome E2E against the **live API** (`http://192.168.1.248:8081`):
  all 7 routes rendered real production data (no console errors)
- API query forms used by the frontend verified live:
  `production_scope=true` → 84 · `false` → 36 · none → 120 · search → filtered
  attendance status filter · device-users active filter · enrollments/mappings/ranks

## 6. Dev usage

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (CORS already allowlisted)
npm run build      # typecheck + production build
```

Env: `VITE_API_BASE_URL` defaults to `http://192.168.1.248:8081` (`.env.development`).

## 7. Deferred (F3+)

- Enrollment operator workflow UI (write, gated) — requires write-gate + operator auth (F5)
- Mapping/admin views with reconciliation actions
- Realtime (SSE bridge over MQTT `attendance/events`)
- Tailwind CSS / TanStack Query (optional, when views grow)

## 8. Git

- commit `e04dddf` `feat: add frontend F2 foundation — React + TS + Vite read views over F1 API`
- TELEPHONE == origin/main (`e04dddf`); ai-brain synced (ff-only)

STOP.
