# ADMS-FullSystem-P0P1-Hardening-007-PhaseF

**Type:** Production deployment record
**Depends on:** `ADMS-FullSystem-P0P1-Hardening-007` (Phases A–E, source-complete implementation)
**Status:** **DEPLOYED.** Migration 012 applied, `adms_api`/`adms_web` redeployed, `API_WRITE_ENABLED` transitioned to `true`, two-layer write control verified live in production.

---

## 1. Pre-Deploy Verification

- HEAD == `origin/main` == `0749c66cb0d5bd9e0ab567fbc831de05349a84d3` — confirmed via `git fetch` + `git rev-parse`.
- Working tree: clean.
- Container health before deployment: `adms_api`, `adms_web`, `adms_zkteco_listener` healthy; `adms_postgres` healthy; `adms_mqtt` up (no configured healthcheck, consistent with baseline).
- `API_WRITE_ENABLED`: confirmed `false` via `docker exec adms_api printenv`.
- Pre-migration backup: `pg_dump -Fc` — `/tmp/adms_pre_migration012_20260817_163403.dump`, 80.0K, SHA256 `54ea15a5f36215ae470a517e5cd5ad027684a4cefa16ab46ba68cada8d68fd9d`, `pg_restore -l` sanity check PASS (113 TOC entries, valid archive header).

## 2. Deployment

- **Migration 012**: applied via `psql -v ON_ERROR_STOP=1 -f sql/012_write_session_schema.sql` against `adms_postgres`. Result: `BEGIN / CREATE TABLE / CREATE INDEX / CREATE INDEX / COMMIT` — clean. Post-apply schema verification (`\d write_sessions`) confirmed all columns, the partial unique index (`uq_write_sessions_one_unclosed`), the supporting index on `opened_by`, both check constraints, and both foreign keys exactly as specified in the migration file. Table confirmed empty (0 rows) immediately after.
- **`adms_api` / `adms_web`**: rebuilt via `docker compose build api web` from HEAD `0749c66` (frontend build ran inside the image build — `tsc --noEmit && vite build` succeeded producing the same bundle hashes as the local pre-deploy build, `index-BkeCVBQR.js` / `index-CyUw5ZaC.css`). Recreated via `docker compose up -d api web`.
- **`API_WRITE_ENABLED`**: set to `true` in `.env` (prior value backed up to `/tmp/env_backup_pre_phasef.bak`), `api` container recreated to pick it up.
- **Collector / MQTT**: explicitly **not** rebuilt, restarted, or recreated at any point. Confirmed via `docker inspect` after deployment: `adms_zkteco_listener` `RestartCount=0`, `StartedAt` unchanged from before this session (07:04:20, well before Phase F work began ~09:34); `adms_mqtt` `RestartCount=0`, `StartedAt` unchanged (running since Aug 13, untouched for 4+ days through this deployment).

## 3. Two-Layer Write Control — Verification Matrix

All checks performed against the live production API (`http://192.168.1.248:8081`) using two temporary, clearly-labeled test-fixture operator accounts (`phasef_verify_admin` / ADMIN, `phasef_verify_viewer` / VIEWER), created via direct SQL insert using the application's own `hash_password()` function and authenticated through the real `POST /auth/login` endpoint (not manufactured tokens) so the full stack was genuinely exercised. All checks targeted a nonexistent UUID (`00000000-...-000000000000`) on the `PATCH /humans/{id}` endpoint or the enrollment/write-session endpoints directly — no real personnel, device, or mapping data was read or written in a mutating way at any point.

| # | Check | Result |
|---|---|---|
| 1 | Master=true, no runtime session → domain write denied | **PASS** — `403 WRITE_SESSION_REQUIRED` |
| 2 | Non-ADMIN (VIEWER) attempts to open a session | **PASS** — `403 FORBIDDEN` |
| 3 | ADMIN opens a session | **PASS** — `201`, `session_id=1`, 30-minute expiry confirmed exactly (`10:07:04 - 09:37:04`) |
| 4 | Active session + authorized role → passes write-session gate | **PASS** — reached business logic, `404 NOT_FOUND` on the nonexistent probe UUID (proves the write gates passed; failure was the expected downstream lookup miss) |
| 5 | Active session + unauthorized role (VIEWER on enrollment reserve) → still denied | **PASS** — `403 FORBIDDEN`, role check independently enforced even with an active session |
| 6 | ADMIN closes the session | **PASS** — `200`, `active:false` |
| 7 | Closed session → writes denied again | **PASS** — `403 WRITE_SESSION_REQUIRED` |
| 8a | Session expiry → domain write denied with the correct distinct code | **PASS** — `403 WRITE_SESSION_EXPIRED` (session backdated via a controlled test-fixture DB update on the session row created in this same test, not real data) |
| 8b | Expired-but-unclosed session auto-reaped | **PASS** — `closed_at`/`close_reason='EXPIRED'` set automatically on first read after expiry |
| 8c | Reaping an expired session does not block a new open | **PASS** — `201` immediately, new `session_id=3` |
| 9a | Session remains technically unclosed in DB when infra gate flips off | **PASS** — confirmed via direct query |
| 9b | Infra master off + technically-active session → domain write still denied | **PASS** — `403 WRITE_DISABLED` (Layer 1 evaluated first, Layer 2 never reached) |
| 9c | Infra master off → even opening a *new* session is blocked | **PASS** — `403 WRITE_DISABLED` |

**Result: 13/13 checks passed.** Layer 1 unconditionally overrides Layer 2 in every case tested, including the specifically-required "technically active session, infra off" scenario.

### Cleanup

`API_WRITE_ENABLED` restored to `true` (the target final state) after the Layer-1-override test, `api` recreated again. All fixture write sessions closed (2 `ADMIN_CLOSED`, 1 `EXPIRED` — full audit trail confirmed in `sync_events`). Both fixture operators' tokens revoked then deleted; both fixture `write_sessions` rows deleted; both fixture `operators` rows deleted. Post-cleanup query confirms `operators` contains only the original `admin` account (`operator_id=1`).

## 4. Browser E2E Verification

**Not performed as originally scoped.** The Chrome browser automation tool was not connected/reachable in this environment when attempted (`Claude in Chrome is not connected`). Rather than fabricate a walkthrough, this is reported honestly as a gap.

**Partial substitute verification performed instead** (HTTP-level, not visual/interactive):
- Web console reachable: `GET http://192.168.1.248:8082/` → `200`.
- Served `index.html` references `index-BkeCVBQR.js` / `index-CyUw5ZaC.css` — an **exact match** to the bundle hashes produced by the local pre-deploy `npm run build`, confirming the deployed frontend is precisely the tested build, not a different or stale artifact.
- Deployed JS bundle contains write-session-related route strings (confirms the feature code shipped).
- Deployed JS bundle contains **zero** occurrences of `window.confirm(` and zero occurrences of bare `alert(` — confirms the native-dialog removal (Phase D) shipped correctly to production.
- Title tag confirms the expected page (`ADMS Console`).

**Not verified**: TH/EN visual toggle, role display rendering, the write-session LOCKED/countdown/active UI states as actually rendered, RBAC-driven writability of specific buttons, and browser console cleanliness. **This is a real gap against the original Phase F scope and should be closed with a short manual pass by someone with browser access**, or by retrying this deployment's E2E step once Claude in Chrome is reachable in this environment. It does not block the backend/API-level correctness established in §3, which is the security-critical surface.

## 5. Runtime Safety

| Check | Result |
|---|---|
| `adms_api` health | `Up, healthy` (post-recreate) |
| `adms_web` health | `Up, healthy` (post-recreate) |
| `adms_postgres` health | `Up, healthy`, untouched (`RestartCount=0`, running since Aug 13) |
| `adms_mqtt` | `Up`, untouched (`RestartCount=0`, running since Aug 13) |
| Collector state | `LIVE`, `device_connected=true`, `db_status=HEALTHY` (read from the live collector health file, timestamped fresh) |
| Collector/MQTT restarted? | **No** — confirmed via unchanged `StartedAt` and `RestartCount=0` on both |
| Unexpected container restarts | **None** — only the two intentional `api` recreates (code deploy + the Layer-1-override test + restore) and one `web` recreate occurred, all deliberate |
| Temporary auth tokens remaining | **None** — all fixture tokens revoked and deleted, confirmed by query |

## 6. Production State (final)

- `API_WRITE_ENABLED` = **`true`** (final value, confirmed via `docker exec adms_api printenv`)
- Migration 012 = **applied**, schema verified
- Runtime write session = **closed** (none active) — production is write-locked by default, exactly as designed
- DB modified = **only** by the migration 012 schema change and the fully-cleaned-up test-fixture rows (all removed) — no real personnel, device, attendance, or mapping data was touched
- Device (ZKTeco terminal) = **not modified**
- Collector / MQTT = **not modified, not restarted**

## 7. Tests

`pytest tests/` re-run post-deployment (against the same codebase, mocked DB as before — this is the source-level regression suite, not a live-production test run): **429 passed, 0 failed.**

## 8. Post-Deploy Backup

`pg_dump -Fc` — `/tmp/adms_post_migration012_20260817_164138.dump`, 84.6K (grew from the pre-migration 80.0K, consistent with the new table), SHA256 `d5012f6ca122ef92ddbb903d73f674709b83b929b00e1684fccdd05a092935e3`, `pg_restore -l` confirms 12 `TABLE public` entries (was 11 pre-migration, +1 for `write_sessions`).

## 9. Remaining Blockers / Follow-ups

1. **Browser visual E2E was not performed** (§4) — the one incomplete item against the original Phase F scope. Recommend a short manual pass (TH/EN toggle, write-session UI states, RBAC button gating, console check) at the next opportunity with working browser tooling. This does not affect the security correctness of the deployed write-control model, which was independently and thoroughly verified at the API level.
2. No other blockers. All other Phase F requirements — migration, container deployment, two-layer write-control verification, runtime safety, backups, documentation, and this report — are complete.

## 10. Rollback Plan (unused, kept for reference)

Not exercised — deployment succeeded with no failures at any gate. If ever needed: revert to the pre-Phase-F commit, `docker compose up -d api web` from the reverted build, restore `.env`'s `API_WRITE_ENABLED` to its pre-Phase-F value (`false`) together with the code rollback (not independently), and restore from `/tmp/adms_pre_migration012_20260817_163403.dump` only if the schema itself needs reverting (not required for a code-only rollback, since `write_sessions` is inert if simply unused).
