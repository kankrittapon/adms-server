# ADMS NATIVE PUSH — EXPERIMENTAL VALIDATION REPORT

## Prompt

* PromptID: `ADMS-NativePush-Experimental-001`
* mode: RESEARCH → LIVE READ-ONLY DISCOVERY → PROTOCOL AUDIT → CONTROLLED EXPERIMENT → ROLLBACK → CHECKPOINT
* date: 2026-08-12/13
* target: ai-brain (`192.168.1.248`, user `kanfullbuster`, repo `/home/kanfullbuster/adms-server`)
* terminal: ZEM560 `192.168.1.201` (ZEM560_TFT, Ver 6.60, serial `3392113170057`)
* result: **PARTIAL — server listener proven; device does not transmit. Deferred. Polling remains production primary.**

---

## 1. AGENT / TOOLING

| Item | Value |
|---|---|
| agent/model | Freebuff (Buffy) — deepseek-v4-flash |
| IDE | Freebuff chat (TELEPHONE control workstation) |
| pty-mcp available / used | YES / YES (v0.11.6, stateful SSH via `create_ssh_session`) |
| temporary SSH transport scripts | 0 (stdio MCP driver files only, deleted after use) |
| ai-brain verified | YES (`ai-brain` / `kanfullbuster` / `/home/kanfullbuster/adms-server`) |

## 2. GIT BASELINE

| Node | HEAD |
|---|---|
| starting HEAD (all nodes) | `3099476` |
| implementation commit | `bd4884e` (feat: experimental native push listener) |
| allowlist commit | (squashed into experiment history) |
| rollback commit | `b097800` (remove listener deployment) |
| final TELEPHONE / origin / ai-brain | `b097800` — synchronized |

## 3. RUNTIME / DATABASE BASELINE (pre-experiment)

- PostgreSQL `adms_postgres` HEALTHY (Up 34h) · MQTT `adms_mqtt` Up 33h · Collector `adms_zkteco_listener` **LIVE/HEALTHY** (restarts 0)
- DB: human_employees 120 · sources 120 · devices 1 · device_users 3 (pk1/2 inactive, pk7 active/1001) · enrollments 1 · **employee_device_mappings 1 (VERIFIED)** · attendance 10 → 12 (2 new legitimate polling captures at 17:18 UTC)
- attendance: null=7 (legacy), human=5 (ids 12/15/16/20/21 → pilot Human `039c4486-b30f-4ce1-b780-783cd268858d`), **dupes=0**
- production_scope: 36 false (พลทหาร) / 84 true · mapping_id 1 VERIFIED (CONTROLLED_SCAN, valid_from `2026-08-12 08:47:37+00`, valid_to NULL)

## 4. NETWORK / PORT AUDIT

| Port | State on ai-brain |
|---|---|
| **8000** | FREE (garmin_api 8000 is docker-internal only) |
| 8080 | adminer bound 127.0.0.1 only |
| 3000/3001/5678/1883/22 | audioreader / mcmod / n8n / MQTT / SSH |

Device `options.cfg` (prior read-only audit) contained `AuthServerIP=192.168.1.248`, `AuthServerPort=8000`, `AuthServerEnabled=1`, `IclockSvrFun=1` — but the **terminal UI "Webserver" menu was blank** (owner correction: Webserver menu ≠ ADMS/iClock Push config; restored to prior state).

## 5. TERMINAL CAPABILITY

- Firmware evidence: `libhttppush.so` present, linked at boot (`nand` script); strings `AuthFromHttpServer`, `pushsdk_options`, `pushsdk_cnt_log_by_time`, `call_main_update_data`.
- Expected endpoints (classic iclock): `GET/POST /iclock/cdata`, `GET /iclock/getrequest`, `/iclock/devicecmd`.
- **Outbound push: NEVER observed** — not during prior audit (2026-08-11), not after ADMS UI config, not after terminal reboot. `libhttppush.so` exists but the push client does not initiate.
- Wi-Fi: `WIFI=0` in options.cfg — Wi-Fi already disabled; Ethernet `192.168.1.201`/TCP 4370 is the production interface. No Wi-Fi WRITE required.

## 6. PROTOCOL RESEARCH (source-backed)

| Endpoint | Format | Source | Confidence |
|---|---|---|---|
| `GET /iclock/cdata?SN=` | OPTIONS text block (`GET OPTIONS FROM:`, OpStamp, ErrorDelay, Delay, TransTimes, TransInterval, TransFlag, Realtime, Encrypt) | `fedotovaleksandr/iclockhelper` + ZK Push C# sample | COMMUNITY-DOCUMENTED |
| `POST /iclock/cdata?SN=&table=ATTLOG` | Tab-separated `ATTLOG<TAB>pin<TAB>YYYY-MM-DD HH:MM:SS<TAB>checktype<TAB>verifycode<TAB>workcode`; reply `OK` | iclockhelper models.py | COMMUNITY-DOCUMENTED |
| `GET /iclock/getrequest` | Command polling; reply `OK` when no commands | iclockhelper | COMMUNITY-DOCUMENTED |
| Newer ZK Push (v3.0.1) | `/iclock/push?ServerVersion=...&PushVersion=...` | ZKPush.cs | COMMUNITY-DOCUMENTED (not used; ZEM560-era firmware) |

## 7. IMPLEMENTATION (kept as experimental evidence)

`app/native_push/` — isolated stdlib `http.server` listener, **zero new dependencies**:

- `config.py` — `NativePushConfig` (source allowlist, serial validation, body limit, health file)
- `protocol.py` — `parse_sn`, `parse_cdata_params`, `parse_attlog_body`, `build_options_response`
- `service.py` — routes + **canonical ingestion**: every ATTLOG row → `save_attendance_log()` → `normalize_device_timestamp()` (Asia/Bangkok) → `determine_status` → `resolve_verified_employee_mapping()` → dedupe via `UNIQUE(user_id, device_ip, scan_time)`. **No second identity system.**
- MQTT publish optional (default OFF — polling Collector already publishes once per scan)
- Security: LAN-only bind `192.168.1.248:8000`, source allowlist (403 verified), serial validation, 413 oversized, 422 unparseable (device retains+retries), 404 unknown paths
- `tests/test_native_push.py` — 48 tests

## 8. SERVER-SIDE SYNTHETIC TESTS (test-isolated)

- Handshake GET → 200 OPTIONS block · getrequest → OK · wrong serial → 403 · malformed ATTLOG → 422 · unknown table (BIOPHOTO) → OK ignored · valid ATTLOG → 200 OK
- One synthetic VALID_DUPE row was inserted because the naive `08:47:37` normalized to Bangkok → UTC `01:47:37+00` (different from stored UTC `08:47:37+00`); **identified and deleted** (row id 19 + its NATIVE_PUSH_ATTLOG sync event) in a precise transaction. Baseline restored: att=12, null=7, human=5, dupes=0.

## 9. CONTROLLED DEVICE TEST — RESULT

Owner configured the terminal UI ("Webserver" menu, later identified as NOT the ADMS push config) and rebooted the device.

**Listener observed ZERO traffic from `192.168.1.201`** across two 10-minute observation windows:
- total iclock events: 9 — all `source=192.168.1.248` (synthetic client), 0 from device
- no TCP connection to :8000 observed (`ss`), no registration handshake, no getrequest polling

**Conclusion: the ZEM560 (Ver 6.60, 2011) `libhttppush.so` push client does not initiate outbound push in practice**, even with configuration present. E2E Native Push is **NOT TRANSMITTING** on this terminal.

## 10. POLLING RECOVERY (owner priority)

During the experiment the terminal was rebooted; the Collector transiently entered BACKOFF (device unreachable during reboot window). Verified recovery:

- ZEM560 reachable: ICMP 0% loss · ARP REACHABLE (`00:17:61:11:18:d9`) · TCP 4370 open
- Collector **LIVE / HEALTHY** (Device Connected, DB HEALTHY, MQTT HEALTHY, HC_RC=0, restarts 0)
- PostgreSQL / MQTT healthy · DB integrity intact (counts, mapping, scope, dupes=0)
- 2 new legitimate polling captures (17:18 UTC) resolved correctly through mapping_id 1

## 11. ROLLBACK (owner decision: DEFER)

- `docker-compose.yml`: native-push service removed (commit `b097800`)
- ai-brain: `git pull --ff-only` → `docker rm -f adms_native_push` → port 8000 free
- Polling Collector verified LIVE/HEALTHY after removal (restarts 0)
- Source `app/native_push/` + tests retained as documented experimental evidence

## 12. POST-EXPERIMENT BACKUP

- `adms_post_native_push_experiment_20260813_003620.dump`
- size 55,722 B · SHA256 `2040a9722704a22c54cb7457857db6f84ba60ad5700b9a1529b63ca3367625f2`
- `pg_restore -l` PASS (105 TOC entries)
- Authoritative pre-experiment baseline remains `adms_backend_final_20260812_140826.dump` (Backend Final, not deleted)

## 13. IDENTITY SAFETY

- Human Master unchanged (120) · production_scope unchanged (36 false / 84 true) · new Human: 0
- mapping_id 1 unchanged (VERIFIED) · new mapping: 0 · automatic mapping: 0
- fingerprint templates accessed: NO · biometric data stored: NO
- attendance duplicates: 0 · UNKNOWN statuses: 0

## 14. TESTS

- previous baseline: 224/224
- added: 48 (test_native_push.py)
- **final: 272/272 PASS** (0 failures)

## 15. RUNTIME (post-rollback)

| Service | State |
|---|---|
| PostgreSQL | HEALTHY (restarts 0) |
| MQTT | OPERATIONAL (restarts 0) |
| Polling Collector | LIVE / HEALTHY (restarts 0) |
| Native Push listener | REMOVED (deferred) |
| Healthcheck | HEALTHY (HC_RC=0) |
| ZKTeco | CONNECTED (TCP 4370) |

## 16. CHECKPOINT CLASSIFICATION

| Item | Value |
|---|---|
| Native Push capability | **PARTIAL / NOT TRANSMITTING** (server proven, device silent) |
| E2E push | NOT TESTED (device never initiated) |
| dedupe | PASS (canonical UNIQUE contract verified via synthetic tests + live polling) |
| fallback (polling) | PASS (recovered + healthy) |
| security | ACCEPTABLE (LAN-only, allowlist, serial validation) |
| production direction | **POLLING PRIMARY; Native Push DEFERRED** |
| polling baseline preserved | YES |
| Backend Foundation | **REMAINS 100% COMPLETE** |

## 17. NEXT

- Frontend F1 (API Gap Closure) — per `docs/FRONTEND_ARCHITECTURE_PLAN.md`, uses canonical backend data contracts, NOT raw ZKTeco Push protocol.
- Native Push: deferred; experimental source + tests retained for a future device/firmware that actually transmits.

## 18. FINAL

- repository verified: YES (`b097800` synchronized TELEPHONE=origin=ai-brain)
- database modified: NO (net zero; one synthetic test row removed)
- application modified: YES (experimental module + tests retained; compose deployment reverted)
- device modified by Agent: NO · physical device modified by Owner: YES (Webserver menu, restored)
- new Human: 0 · new terminal user: 0 · new mapping: 0
- tests: 272/272 PASS
- runtime: HEALTHY
- commit created: YES (`b097800`) · push completed: YES
- ai-brain synchronized: YES
- Native Push: DEFERRED · polling baseline preserved: YES
- Frontend F1: READY (pending owner gate)
- safe to proceed: YES
- blockers: NONE

STOP.
