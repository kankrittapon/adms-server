# ADMS-RBAC-OperationalRoles-023

**Scope**: finalize ADMS role semantics for real operational use — widen Work Session open/close from ADMIN-only to OPERATOR-or-ADMIN, while proving every other separation-of-duties boundary (identity verification, Personnel lifecycle, destructive Terminal Management, operator/role management) remains ADMIN-only exactly as before.

## 1. Full RBAC audit (source-derived, not guessed)

| Action | VIEWER | ENROLLMENT_OPERATOR | OPERATOR | ADMIN | Write Session | API_WRITE_ENABLED | Destructive |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Dashboard read | ✅ | ❌ | ✅ | ✅ | — | — | — |
| Attendance read | ✅ | ❌ | ✅ | ✅ | — | — | — |
| Personnel read | ✅ | ✅ | ✅ | ✅ | — | — | — |
| Personnel deactivate/reactivate | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |
| Enrollment reserve/workflow | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | no |
| Terminal-account creation | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | no |
| Fingerprint confirmation / controlled scan | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | no |
| Mapping verification (create) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | identity-critical |
| Terminal Management inventory (read) | ✅ | ✅ | ✅ | ✅ | — | — | — |
| Fingerprint delete | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |
| Fingerprint re-enrollment | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |
| Terminal-account delete | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |
| **Work Session open** | ❌ | ❌ | **✅ (new)** | ✅ | n/a | ✅ | no |
| **Work Session close** | ❌ | ❌ | **✅ (new)** | ✅ | n/a | no (never gated) | no |
| Operator account management | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |
| Role changes | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |
| Password change (own) | ✅ | ✅ | ✅ | ✅ | exempt | exempt | no |
| Audit Trail | ❌ | ❌ | ❌ | ✅ | — | — | — |
| System Health (read) | ✅ | ✅ | ✅ | ✅ | — | — | — |
| System configuration / device admin | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | yes |

Verified directly from `app/api/routers/*.py`'s `require_roles(...)` dependencies — the only change made was `write_session.py`'s `admin_only` → `operator_or_admin` (`ROLES_OPERATOR_PLUS`). Every other router's role gate was audited and confirmed unchanged.

## 2-5. Final permissions

**VIEWER**: read-only everywhere; zero write capability; cannot open/close Work Session.

**ENROLLMENT_OPERATOR** (the "ENROLLMENT" role): all VIEWER reads, plus enrollment workflow writes (reserve, terminal-account creation, fingerprint/controlled-scan progression) — only while a Work Session is active. Cannot open/close Work Session, cannot verify mapping/identity, cannot touch Personnel lifecycle, cannot delete fingerprints/terminal accounts, cannot manage operators/roles/system config.

**OPERATOR**: all VIEWER + ENROLLMENT_OPERATOR capabilities, **plus opening/closing the Work Session** (new). Cannot manage operators/roles, cannot verify mapping/identity, cannot touch Personnel admin lifecycle, cannot delete fingerprints/terminal accounts, cannot touch system/security configuration.

**ADMIN**: everything — Work Session, mapping verification, Personnel lifecycle, destructive Terminal Management, operator/role management, system/security configuration.

## 6. Work Session open roles

`OPERATOR`, `ADMIN` (was `ADMIN` only).

## 7. Work Session close roles

`OPERATOR`, `ADMIN` (was `ADMIN` only) — unchanged: still not gated by Layer 1 (closing must always be available as a de-escalation action).

## 8. Separation-of-duties result

Confirmed by source audit: final identity/mapping verification (`POST /api/v1/mappings`), Personnel admin lifecycle (`deactivate`/`reactivate`), and destructive Terminal Management (fingerprint delete, terminal-account delete, fingerprint re-enrollment) were **already** ADMIN-only in every router before this PromptID and remain so — no change was needed or made. This PromptID's only backend behavior change is the Work Session gate.

## 9. Backend enforcement changes

`app/api/routers/write_session.py`: `admin_only = require_roles(ROLES_ADMIN_ONLY)` → `operator_or_admin = require_roles(ROLES_OPERATOR_PLUS)`, applied to both `POST /open` and `POST /close`. No other router changed.

## 10. Frontend capability changes

`frontend/src/auth.tsx`: added canonical capability helpers (`canOpenWorkSession`, `canEnroll`, `canVerifyIdentity`, `canManagePersonnel`, `canManageTerminal`, `canManageOperators`) mirroring the backend `ROLES_*` sets — `canOpenWorkSession` now derives from `role === "OPERATOR" || role === "ADMIN"`; the ADMIN-only capabilities remain gated on `isAdmin`. `WriteSessionControl.tsx` now reads `canOpenWorkSession` instead of re-deriving `isAdmin` itself.

## 11. Role dropdown / help UX

Already existed (`System.tsx`'s `OperatorAccountsManagement`) — a role `<select>` with a description paragraph that updates on selection. Updated the four `roles.*Desc` i18n strings (TH/EN) to the owner's exact recommended copy, explicitly stating OPERATOR's new Work Session capability and ENROLLMENT's explicit inability to open one.

## 12. Test matrix / result

756 tests passing (733 baseline-carried-forward + 23 new in `test_rbac_operational_roles.py`, plus `test_write_session.py` updated in place: the old `test_non_admin_cannot_open` — which asserted OPERATOR was forbidden — replaced with `test_operator_can_open`/`test_operator_can_close`/`test_enrollment_operator_cannot_close`/`test_viewer_cannot_close`). Covers: the full Work Session role matrix, ENROLLMENT_OPERATOR's inability to self-unlock the write gate, every ADMIN-only router's gate re-confirmed untouched, VIEWER excluded from every write set, ADMIN included in every set, frontend/backend capability-matrix agreement, and TH/EN role-description copy presence.

## 13. Total tests

**756** (was 729).

## 14-16. OpenAPI / tsc / vite

No schema/contract change (pure RBAC-set swap + frontend capability refactor) — OpenAPI drift guard PASS unchanged. `tsc --noEmit` PASS. `vite build` PASS.

## 17. Migration required

**NO.**

## 18. Changed files

`app/api/routers/write_session.py`, `frontend/src/auth.tsx`, `frontend/src/components/WriteSessionControl.tsx`, `frontend/src/i18n/{en,th}.ts`, `tests/test_write_session.py`, `tests/test_rbac_operational_roles.py` (new), `docs/SECURITY_RBAC.md`, `docs/API_CONTRACT.md`, `docs/ENROLLMENT_SESSION_RUNBOOK.md`, `docs/reports/README.md`, `STATUS.md`.

## 19. Commit hash

See git log — committed this session, pushed to `origin/main`.

## 20. Production mutation count

**0** — no production role/account created or altered; existing `admin` operator untouched.

## 21. Remaining RBAC ambiguities

None identified. The one open design question flagged by the PromptID itself — "keep final identity verification ADMIN-only unless current policy intentionally grants it elsewhere" — was resolved by audit: no code path grants it elsewhere, so it stays ADMIN-only, matching the owner-approved policy exactly.
