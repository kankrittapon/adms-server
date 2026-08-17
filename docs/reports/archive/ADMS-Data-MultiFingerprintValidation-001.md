# ADMS — SAME HUMAN / MULTI-FINGERPRINT PRODUCTION VALIDATION

**PromptID:** `ADMS-Data-MultiFingerprintValidation-001`
**Mode:** LIVE VALIDATION → OWNER PHYSICAL ACTION GATE → CONTROLLED SCAN GATE → VERIFY → CHECKPOINT → DOCUMENT → FINALIZE
**Status:** **PASS**
**Production target:** `ai-brain` (192.168.1.248) · user `kanfullbuster` · repo `/home/kanfullbuster/adms-server`
**Control workstation:** TELEPHONE (source/control only — no TELEPHONE Docker used)

---

## AGENT / MCP HANDSHAKE

| Item | Value |
|---|---|
| agent/model | Freebuff (Buffy) — deepseek-v4-flash |
| IDE | Freebuff chat (TELEPHONE control workstation) |
| pty-mcp available | YES |
| pty-mcp used | YES (stateful SSH session, reused per phase) |
| SSH target | `ai-brain` (192.168.1.248) / `kanfullbuster` |
| remote repo | `/home/kanfullbuster/adms-server` |
| temporary SSH transport scripts | **0** |

## BASELINE (read-only, independently verified LIVE)

| Item | Value |
|---|---|
| Human | กฤตพล หมาดเส็น — `039c4486-b30f-4ce1-b780-783cd268858d` |
| device_user_id | **1001** (uid 1, privilege 0 / NORMAL, active) |
| device_user_pk | **7** |
| mapping_id | **1** (VERIFIED, valid_from `2026-08-12 08:47:37+00`, valid_to NULL) |
| mapping count before | **1** |
| terminal user count before | **1** (User 1001 only) |
| attendance count before | **8** (MAX id 12) |
| Git | TELEPHONE = origin = ai-brain = `0064512`, branch main, clean |
| Runtime | PostgreSQL Up 30h healthy · MQTT Up 29h · listener Up 53min healthy · restarts 0 · HC_RC=0 (LIVE, Device Connected, DB HEALTHY) |
| DB counts | `120 / 120 / 1 / 3 / 1 / 1 / 8` (human/sources/devices/device_users/enrollments/mappings/attendance) |
| Production scope | 36 พลทหาร → `false` · 84 → `true` · pilot Human → `true` · non-พลทหาร flagged: 0 |

## FINGERPRINT SLOT OBSERVABILITY

- Read-only pyzk capability probe (User object fields): `card, encoding, group_id, json_unpack, name, password, privilege, repack29, repack73, uid, user_id`
- **No fingerprint slot/count field is safely exposed.** Template retrieval (`get_templates`) would download biometric data → NOT authorized.
- **FINGERPRINT SLOT COUNT: NOT SAFELY OBSERVABLE** → behavioral validation used (per §6 fallback).

## PHYSICAL ENROLLMENT (OWNER GATE #1)

| Item | Value |
|---|---|
| second fingerprint owner-confirmed | YES (option A) |
| existing User 1001 retained | YES (roster re-read: `1001 / uid 1 / cpo3 Krittapon M / privilege 0`, ROSTER_COUNT=1) |
| User 1002 created | **NO** |
| fingerprint template extracted | NO |
| fingerprint template stored in ADMS | NO |

## CONTROLLED SCAN (OWNER GATE #2)

| Item | Value |
|---|---|
| window | `2026-08-12 13:26:56+00` → `13:31:56+00` (5 min) |
| new attendance events | **id 15** (`13:28:04+00`) and **id 16** (`13:30:47+00`) — owner confirmed BOTH were second-finger scans under User 1001 (single-scope confirmation; second scan disclosed transparently) |
| device_user_pk | 7 (both) |
| user_id | 1001 (both; raw_payload `{"uid":1,"user_id":"1001","device_ip":"192.168.1.201",…}`) |
| employee_id | `039c4486-b30f-4ce1-b780-783cd268858d` (both) |
| owner identity confirmation | YES (option A; second scan also confirmed as owner's) |
| **realtime resolver** | **PASS** — both new events resolved AUTOMATICALLY through mapping_id 1; no manual UPDATE performed |

## IDENTITY (acceptance)

| Item | Value |
|---|---|
| same Human | YES (`039c4486…`) |
| same device user | YES (pk 7, User 1001) |
| same mapping | YES (mapping_id 1) |
| mapping count after | **1** (VERIFIED_COUNT=1) |
| automatic mappings | 0 |
| ambiguity | 0 (all events resolve to the same single VERIFIED interval) |

## HISTORICAL / TEMPORAL SAFETY

| Item | Value |
|---|---|
| attendance id 12 preserved | YES (scan_time `08:47:37+00`, raw_payload intact, employee_id `039c4486…`) |
| legacy attendance preserved | YES (ATT_BEFORE12 = 7 untouched, employee_id NULL) |
| duplicates | **0** |
| valid_from unchanged | YES (`2026-08-12 08:47:37+00`) |
| valid_to | NULL (unchanged) |

## PRODUCTION SCOPE (regression check)

| Item | Value |
|---|---|
| พลทหาร excluded | YES (36 → `production_scope=false`) |
| pilot Human production_scope | `true` |
| non-พลทหาร incorrectly excluded | **0** |

## TESTS / RUNTIME / RECOVERY

| Item | Value |
|---|---|
| tests | **213/213 PASS** (no code change — runtime data only) |
| PostgreSQL / MQTT | OPERATIONAL / OPERATIONAL |
| Collector | LIVE / HEALTHY (HC_RC=0, restarts 0) |
| ZKTeco | CONNECTED (roster reads succeeded, ROSTER_COUNT=1) |
| post-validation backup | `backups/adms_post_multifinger_20260812_133403.dump` |
| size | 55,013 B |
| SHA256 | `69bd1be8777a68ea566dbe19a6f7dfe5b83aa3724bf350a510174504b45593b5` |
| pg_restore -l | **PASS (105 TOC, RC=0)** |

## GIT

| Item | Value |
|---|---|
| starting HEAD | `0064512` (all 3 nodes) |
| final HEAD | `0064512` (docs commit added, pushed, ai-brain synced) |
| synchronized | YES |

## LIMITATION — EXPLICIT

> **THIS TEST DOES NOT VALIDATE MULTI-PERSON ENROLLMENT.**
> It validates **SAME-HUMAN MULTI-FINGERPRINT** behavior only:
> **ONE HUMAN → ONE TERMINAL ACCOUNT → MULTIPLE PHYSICAL FINGERPRINTS → ONE VERIFIED TEMPORAL IDENTITY.**

## FINAL

- new Human created: **0**
- new terminal user created: **0** (no User 1002)
- new mapping created: **0**
- VERIFIED mappings: **1** (unchanged)
- multi-fingerprint validation: **PASS**
- multi-person enrollment validated: **NO**
- automatic mapping: **NO**
- Native ADMS Push: NOT EXECUTED
- safe to proceed: YES · blockers: NONE
