# ADMS DEVICE ENROLLMENT — ONE-HUMAN CONTROLLED PILOT REPORT

**PromptID:** `ADMS-Data-DeviceEnrollmentPilot-001`
**Status:** **PASS — READY_FOR_MAPPING REACHED**
**Mode:** WRITE — ONE-HUMAN CONTROLLED PILOT / LIMITED DEVICE MUTATION
**Date:** 2026-08-12

---

## AGENT / TOOLING

| Item | Value |
|------|-------|
| Agent / Model | Freebuff (Buffy) — deepseek-v4-flash |
| IDE | Freebuff chat (TELEPHONE control workstation) |
| pty-mcp | AVAILABLE (v0.11.6, 16 tools) — used via stdio client driver |
| pty-mcp used | YES |
| stateful ai-brain session | PASS (`ai-brain` / `kanfullbuster` / cwd persisted across separate MCP calls) |
| temporary SSH transport scripts | 0 (MCP client drivers, deleted after use) |

## GIT BASELINE

| Item | Value |
|------|-------|
| starting HEAD | `003cfb9` |
| origin/main | `003cfb9` |
| ai-brain HEAD | `003cfb9` |
| synchronized | YES (all three nodes) |

## PILOT HUMAN

| Item | Value |
|------|-------|
| employee_id | `039c4486-b30f-4ce1-b780-783cd268858d` |
| business identifier | personnel_id: (empty) · rank: **พ.จ.ต.** · category: พันจ่า · branch: อล. |
| display name | **กฤตพล หมาดเส็น** |
| record uniqueness | 1 match (exact, verified before reservation) |
| owner explicitly confirmed | YES (Gate #1 `CONFIRM PILOT HUMAN` + Gate #4 `CONFIRM CONTROLLED SCAN`) |

## PRODUCTION ID

| Item | Value |
|------|-------|
| allocated device_user_id | **1001** (allocator result) |
| namespace | 1001+ |
| allocator used | YES (`reserve_next_device_user_id()`) |
| legacy IDs 1/2 protected | YES (never reused; both remain inactive) |
| candidate verified | NOT on terminal · NOT reserved · NOT retired · ≥ 1001 |

## PRE-WRITE BACKUP

| Item | Value |
|------|-------|
| filename | `backups/adms_pre_pilot_20260812_153220.dump` |
| size | 52,840 bytes |
| SHA256 | `56ffb4ef33487c1a25ae8fd344a7f4f1657db1fb6cb9893d63a6089cdfff6904` |
| pg_restore -l | PASS |

## RESERVATION

| Item | Value |
|------|-------|
| created | YES |
| count | 1 |
| enrollment_id | 1 |
| status | RESERVED |
| reserved_device_user_id | 1001 |
| employee correct | YES (`039c4486-b30f-4ce1-b780-783cd268858d`) |
| device correct | YES (device_id 1, SONIC ZEM560, 192.168.1.201) |
| reserved_by | `owner-krittaphol` |
| reserved_at | 2026-08-12 08:32:24+00 |
| DB integrity | 120 / 120 / 1 / 2 / 7 / **0** / **1** (enrollments) — mappings still 0 |

## TERMINAL ACCOUNT

| Item | Value |
|------|-------|
| created | YES (single authorized `set_user()` call) |
| accounts created | 1 |
| device_user_id | 1001 |
| device_uid | 1 |
| display name | `cpo3 Krittapon M` (ASCII-safe, 16 chars — owner-chosen rank+shortname+initial) |
| privilege | **NORMAL (0)** — verified in roster and DB |
| existing account overwritten | NO (roster re-checked before write; fail-safe held on unexpected presence) |
| device_users row | pk **7** · `1001` / uid 1 / privilege 0 / active / inactive_at NULL |
| legacy IDs 1/2 | still INACTIVE (untouched) |

**Note (set_user quirk):** pyzk returned `False` for `set_user()`, yet the terminal
roster proved the account was created exactly as intended (1 user: 1001 /
`cpo3 Krittapon M` / priv 0). This is a known pyzk response-parsing quirk. The
fail-safe state machine correctly did NOT advance on the `False` return. Owner
approved reconciliation (`APPROVE reconciliation`) via the canonical module path:
`ensure_device_user()` audit row + `_transition(RESERVED → TERMINAL_ACCOUNT_CREATED)`
with `terminal_created_at` + `device_uid=1` + `verify_terminal_account_created()`
roster evidence. No mapping created; no further device writes.

## FINGERPRINT

| Item | Value |
|------|-------|
| method | PHYSICAL TERMINAL (User ID 1001) |
| owner reported enrollment complete | YES (`FINGERPRINT ENROLLED` at Gate #2) |
| state | FINGERPRINT_ENROLLED · confirmed_at 2026-08-12 08:46:42+00 |
| remote fingerprint operation | NO |
| templates stored in ADMS | NO |

## CONTROLLED SCAN

| Item | Value |
|------|-------|
| window started | 2026-08-12 08:46:45+00 (state CONTROLLED_SCAN_PENDING) |
| deadline | 2026-08-12 08:51:45+00 (5-min window) |
| owner scan completed | YES (`SCAN COMPLETE` at Gate #3) |
| attendance event found | YES — attendance id **12** |
| device | 192.168.1.201 (SONIC ZEM560, device_id 1) |
| device_user_id | 1001 |
| device_user_pk | 7 (matches new account) |
| scan_time | **2026-08-12 08:47:37+00** (within window) |
| event unambiguous | YES (exactly 1 event in window) |
| owner explicitly confirmed identity | YES (`CONFIRM CONTROLLED SCAN` at Gate #4) |

## ENROLLMENT FINAL STATE

| Item | Value |
|------|-------|
| state | **READY_FOR_MAPPING** (via CONTROLLED_SCAN_CONFIRMED) |
| enrollment row | `1 | 039c4486-… | 1 | 1001 | READY_FOR_MAPPING | 1 | 08:47:37+00 | owner-krittaphol | 08:50:39 | 08:43:21` |
| controlled_scan_time | 2026-08-12 08:47:37+00 |
| recommended mapping valid_from | `2026-08-12 08:47:37+00` (controlled scan / confirmed ownership boundary) |
| evidence | CONTROLLED_SCAN (STRONG) |

## MAPPING SAFETY

| Item | Value |
|------|-------|
| employee_device_mappings | **0** |
| automatic mapping | NO |
| attendance employee_id | **NULL** (id 12 verified) |
| historical reconciliation | NOT EXECUTED |
| sync_events | `ENROLLMENT_SCAN_CONFIRMED` + roster lifecycle `NEW USER 1001 (pk=7)` observed |

## LIFECYCLE

| Item | Value |
|------|-------|
| production device_user (1001, pk 7) active | YES |
| roster_last_seen_at | populated (roster lifecycle observed new user) |
| inactive_at | NULL |
| legacy ID 1 inactive | YES |
| legacy ID 2 inactive | YES |

## DATABASE

| Item | Value |
|------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| devices | 1 |
| device_users | 3 (2 historical inactive + 1 production active) |
| device_user_enrollments | 1 (READY_FOR_MAPPING) |
| attendance_logs | 8 (7 historical preserved + 1 controlled scan) |
| employee_device_mappings | **0** |

## TESTS

| Item | Value |
|------|-------|
| total | 168 |
| passed | 168 |
| failed | 0 |

## POST-PILOT BACKUP

| Item | Value |
|------|-------|
| filename | `backups/adms_post_pilot_20260812_155112.dump` |
| size | 53,334 bytes |
| SHA256 | `80aaed5522ea98175bbf5cd3a590e225ee039b3698699b5c98869000cace3f2d` |
| pg_restore -l | PASS |

## RUNTIME

| Item | Value |
|------|-------|
| PostgreSQL | OPERATIONAL / healthy · restarts 0 |
| MQTT | OPERATIONAL / healthy · restarts 0 |
| Collector | LIVE / HEALTHY (DB healthy, MQTT healthy, Device Connected) |
| Healthcheck | HEALTHY (HC_RC=0) |
| restart count | 0 |
| ZKTeco | CONNECTED |

## DEVICE SAFETY

| Item | Value |
|------|-------|
| terminal users | 1 (1001) |
| delete_user calls | 0 |
| clear_attendance calls | 0 |
| clear_data calls | 0 |
| remote enroll_user calls | 0 |
| device reset | NO |

## DOCUMENTATION

| Item | Value |
|------|-------|
| report | `docs/reports/ADMS-Data-DeviceEnrollmentPilot-001.md` |
| workflow doc updated | YES (`docs/data/DEVICE_ENROLLMENT_WORKFLOW.md`) |
| STATUS updated | YES (`STATUS.md`) |

---

## FINAL

| Item | Value |
|------|-------|
| PromptID | ADMS-Data-DeviceEnrollmentPilot-001 |
| pilot | **PASS** |
| Human explicitly verified | YES |
| production account created | YES (device_user_id 1001, NORMAL, device_uid 1) |
| fingerprint physically enrolled | YES (owner-confirmed, physical terminal) |
| controlled scan | PASS (attendance id 12, 08:47:37+00, unambiguous) |
| owner scan confirmation | YES |
| READY_FOR_MAPPING | **YES** |
| Human mappings created | 0 |
| bulk enrollment performed | NO |
| tests | 168/168 |
| Collector | OPERATIONAL |
| Healthcheck | HEALTHY |
| authoritative post-pilot backup | VERIFIED |
| next authorized PromptID | `ADMS-Data-HumanDeviceMapping-003` |
| safe to proceed | YES |
| blockers | NONE |

**STOP.**
