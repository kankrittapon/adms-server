# ADMS Audit — 2026-09-03 (Read-Only, Non-Destructive)

**Host:** `ai-brain` — Ubuntu 24.04.4 LTS, Kernel 7.0.0-30-generic, PRIME A320M-K, 13GiB RAM, 232GiB `/` 75% used, Load 0.87  
**Scope:** Containerized ADMS (Time Attendance & Personnel Management) — `adms_postgres`, `adms_mqtt`, `adms_zkteco_listener`, `adms_api:8081`, `adms_web:8082` + ZKTeco ZEM560 `192.168.1.201:4370`  
**Mode:** Read-only discovery only. No `docker compose restart`, no `UPDATE`/`DELETE`, no `pg_reload` beyond read-only `SELECT`.  
**Baseline refs:** `STATUS.md` HEAD `ADMS-PersonnelIdentity-AttendanceClosure-025` (41 new tests, 825 passing), `docker-compose.yml` 7.0.0-30, `collector_health.json` schema 1.0

---

## 1. Non-Destructive Live Host & Container Discovery

### 1.1 Host Resources (Actual Outputs 2026-09-03T05:38 Asia/Bangkok)

```
hostname: ai-brain
OS: Ubuntu 24.04.4 LTS (noble) / Kernel 7.0.0-30-generic x86_64
Uptime: 1 day 19:07, 6 users, load 0.87/0.46/0.38
Mem: 13Gi total, 4.0Gi used, 1.0Gi free, 9.0Gi buff/cache, 9.6Gi available
Disk: / (ext4 232G) 165G used 57G free 75% | /boot 1.6G free 12% | Swap 8Gi 0 used
iostat: %user 3.39 %system 1.06 %iowait 0.08 %idle 95.45 — dm-0 12.34 w/s 177kB/s aq 0.03
top: PID 2008246 opencode 72.2g VIRT 1.0g RES 7.3% CPU (heaviest), adms_api uvicorn 8.3% 57MiB
```

**Assessment:** `iowait 0.08`, `idle 95%` healthy; `MEM 4Gi used` generous headroom; disk 75% warrants pruning (`/backups`, Docker volumes) before 85%.

### 1.2 Docker Topology — Actual

```
docker ps (adms-server filtered):
adms_web                    adms-server-web              Up 27h (healthy) 192.168.1.248:8082->80/tcp
adms_api                    adms-server-api              Up 43h (healthy) 192.168.1.248:8081->8081/tcp
adms_zkteco_listener        adms-server-listener         Up 43h (healthy)
adms_mqtt                   eclipse-mosquitto:2          Up 43h           127.0.0.1:1883->1883/tcp
adms_postgres               postgres:16-alpine           Up 43h (healthy) 5432/tcp

Other stacks co-resident: vocab-*, sailfish_*, n8n_zort, private_* (total 23 containers)
docker stats (ADMS subset):
adms_api           0.18% 57MiB /13.56GiB  31kB/126B NetIO
adms_zkteco_listener 0.10% 26MiB  3.45MB/3.34MB
adms_mqtt          0.03% 10MiB  595kB/393kB
adms_postgres      0.00% 25MiB  2.61MB/2.63MB
adms_web           0.00% 4.5MiB
Health streaks all 0 failing, 5 logs each ExitCode 0.
Collector: HEALTHY - State LIVE Age 2.1s Device Connected DB HEALTHY MQTT UNKNOWN
```

**Volumes:** `adms_postgres_data`, `adms_mqtt_data`, `adms_mqtt_log`, `adms_collector_health` (shared `/var/run/adms`).

### 1.3 LAN Ports & Network

```
ss -tulpn (filtered):
0.0.0.0:5432 (vocab pg) 
192.168.1.248:8082 (adms_web)
192.168.1.248:8081 (adms_api)
127.0.0.1:1883 (adms_mqtt)
0.0.0.0:6379, 3000, 9000 etc (vocab stack, unrelated)
Missing: 4370 not LISTEN locally (correct — remote device port)

Ping 192.168.1.201: 3/3 rx, 0% loss, avg 0.75ms, ttl 64 (LAN, excellent)
TCP 4370: /dev/tcp probe → open
ARP: 192.168.1.201 lladdr 00:17:61:11:18:d9 DELAY (SONIC)
ip r: 192.168.1.0/24 dev enp5s0 (expected)
```

**No firewall block;** `192.168.1.248` binds are LAN-only (no `0.0.0.0:8081`), reducing WAN exposure.

### 1.4 PostgreSQL Pools & Locks (Read-Only)

```sql
-- pg_stat_activity (5 conns idle, 1 active psql, 0 locks waiting)
pid 116374 psql active SELECT pid... (self)
-- pg_locks WHERE NOT granted → 0 rows (no contention at audit time)
-- pg_stat_replication → 0 rows (no physical replica — correct for ADMS)
-- connections: 5 idle, 1 active
-- DB size: 10 MB, top tables:
sync_events 6129, human_employees 120, human_employee_sources 120, api_tokens 36, attendance_logs 20

-- migrations: no schema_migrations table, but STATUS.md confirms 012..025 applied via sql/013 terminal-ID reclamation
-- Operators: 2 rows — admin ADMIN active, commu1 OPERATOR active
-- sync_events counts: ROSTER_LIFECYCLE 5988, HISTORICAL_BACKFILL 24, AUTH_LOGIN 23, WRITE_SESSION_OPENED 17, AUTH_LOGIN_FAILED 11, etc.
```

**Anomaly:** No waiting locks — indicates no current `advisory-lock` contention on `write_sessions` (`uq_write_sessions_one_unclosed` UNIQUE WHERE `closed_at IS NULL`).

### 1.5 Collector Health Bridge (Actual JSON 2026-09-03T05:38:32Z)

```json
{
  "schema_version": "1.0",
  "state": "LIVE", "loop_alive": true, "device_connected": true,
  "db_status": "HEALTHY", "mqtt_status": "UNKNOWN",
  "reconnect_attempt": 0, "current_backoff_seconds": 0.0,
  "last_connect_success": "2026-09-01T10:30:38.317691",
  "last_roster_poll_at": "2026-09-03T05:34:52.381648",
  "last_roster_user_count": 4, "last_roster_marked_inactive": 0,
  "device_owner_available": true, "device_command_queue_depth": 0,
  "device_command_generation": 1
}
```
Shared via `adms_collector_health:/var/run/adms` to both `listener` and `api` (`:ro`).

---

## 2. Deep-Dive Root Cause & Log Analysis

### 2.1 Listener Logs (24h) — No Socket Disconnect Storm

**Sample 2026-09-03 01:29–05:34, every 300s:**
```
[INFO] app.collector: Periodic roster lifecycle check triggered (interval=300s).
[INFO] app.collector: Roster snapshot: 4 users observed on terminal.
[INFO] app.db: Roster lifecycle reconciliation complete for device_id=1: 4 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies, 0 mappings_closed.
```
*0* `DEVICE_UNAVAILABLE`, `TerminalRosterUnavailable`, `struct.pack`, `TimeoutMargin`, `DEVICE_USER_INACTIVE` in last 24h window. `device_connected` held `true` continuously, `reconnect_attempt 0`. **Conclusion:** Single-socket pyzk ownership is currently quiescent; no concurrent enrollment is contending for TCP `4370`. This matches `device_command_queue_depth 0` and `pending_fingerprint_enroll_device_user_id null`.

**Historical root causes preserved in docs (not currently firing):**
- `delete_user_template` receiving `user_id` string → `struct.pack` Py3 failure (fixed `f9ba44f`, `STATUS.md:13`). Signature: `TypeError: required argument is not an integer` in `pyzk/tcp.py`.
- `DeviceCommandBus` outer timeout derived (010) → distinguish `DEVICE_UNAVAILABLE` (TCP down) vs `TerminalRosterUnavailable` (DB) — now surfaced via `healthcheck.py`.
- If `mqtt_status UNKNOWN` persists, the bridge does not fail health currently (see anomaly matrix).

### 2.2 Auth & Write-Session Audit Trail

**`sync_events` (last 20, non-rate-limited):**
- `AUTH_LOGIN_FAILED` 11 total, last `2026-08-17 18:15:16` `username=admin`, then 6-day silence → no brute-force at present.
- `AUTH_LOGIN` 23, `AUTH_LOGOUT` 4, `RATE_LIMITED` 1 (single), `OPERATOR_CREATED` 2.
- `WRITE_SESSION_OPENED` 17, `CLOSED` 9, `EXPIRED` 8 → `admin` opened 15, `commu1` (OPERATOR) opened 1 (`session 17`, 2026-08-18 07:26, Thai `ลงลายนิ้วมือ`), closed by `commu1` once. Expiry rate 47% (8/17) indicates sessions often left to auto-expire (30m) rather than explicit `ADMIN_CLOSED` — expected but wasteful.

**`write_sessions` (last 10, truncated):**
```
17 commu1 07:26 → 07:56 EXPIRED (auto)
16 admin 07:08 → 07:08 ADMIN_CLOSED (39s)
13 admin 04:12 → 05:01 EXPIRED
```
No open session currently (`WHERE closed_at IS NULL` → 0 rows). This is the **steady-state write-locked posture** from Phase F (`STATUS.md:88`).

**`adms_api` logs (48h):** Only `GET /healthz 200` from `127.0.0.1` healthchecks; zero `401`/`403`/`429`/`500`/`NameError` in live window → the `resolve_verified_employee_mapping` 500 (025) and CORS-masked 500 are fixed and not recurring.

**Host auth:** `journalctl -p err` shows repetitive `fwupd` failures (firmware updater) and `pam_lastlog.so: No such file` — unrelated to ADMS, but noise obscures real alerts. No `Failed password` for `adms` in inspected `auth.log` slice (requires `sudo -S` to fully tail).

### 2.3 Data Drift / Split-State Instances

**Current snapshot (read-only SELECTs):**

| Store | Count | Detail |
|---|---|---|
| `device_users` (terminal memory mirrored) | 8 rows (5 `device_user_id` 1,2,1001-1004,1005,1006 + 2 inactive) | `1001` active `cpo3 Krittapon M` `device_uid 1`, `1003` active `CPO3 Pimai Khawsaad` `device_uid 2`, `1004` **inactive** `2026-08-18 02:48:56` (post-cleanup, expected), `1`/`2` inactive |
| `employee_device_mappings` (temporal `[valid_from, valid_to)`) | 5 rows, 3 `valid_to IS NULL` (current): `mapping 1` `039c...`→`7(1001)` `2026-08-12`, `mapping 3` `fd63...`→`35(1003)`, `mapping 4,5` `1005,1006` (recent) | `mapping 2`→`29(1004)` correctly closed `valid_to 2026-08-18 02:48` — matches terminal removal, **no drift** |
| `device_user_enrollments` | 5 rows | `enrollment 4` `RETIREMENT` 1004 → mapping 3 re-assigned (reclamation), `enrollment 1` `READY_FOR_MAPPING` 1001 (pilot) |
| `human_employees` | 120 | `with_personnel 0` — confirms 025 report: 120 legacy Humans lack `personnel_id`, CSV import must not require it |
| `attendance_logs` | 20 | Not enumerated here (read-only) |

**Anomaly check via LEFT JOIN (read-only):**
```sql
SELECT du.device_user_id, du.active, m.mapping_id, m.valid_to
FROM device_users du LEFT JOIN employee_device_mappings m ON m.device_user_pk=du.device_user_pk AND m.valid_to IS NULL
WHERE du.device_id=1 ORDER BY du.device_user_id::int;
```
Result: `1003` and `1001,1005,1006` have `VERIFIED` current mappings; `1,2,1004` inactive with NULL mapping — **no slot lacks matching active mapping** (expected `2` inactive devices historically had mappings revoked). No `uid_anomalies` in 5988 lifecycle rows.

**Pending gate:** `Enrollment #2` split-state (terminal vs DB mismatch) noted `STATUS.md:110` — not auto-reconciled; remains `CANCELLED` rows `enrollment 2/3` with `notes: cancelled by admin: Delete`, no `reserved_device_user_id` leak.

---

## 3. Ergonomic & Architectural Remediation Roadmap

### 3.1 Anomaly Matrix (Live Evidence)

| ID | Anomaly | Impact | Root Cause | Severity |
|---|---|---|---|---|
| **A1** | `mqtt_status UNKNOWN` in `collector_health.json` while `device_connected true`, `adms_mqtt` logs only `Saving in-memory database` | Silent MQTT not failing health, attendance `attendance/events` may drop without alert | `docker/mosquitto.conf` `allow_anonymous true`, no `client_id` health ping; `listener` healthcheck checks `device`+`db` only, not `mqtt` | Medium |
| **A2** | Disk `/` 75% (165G used), `adms_postgres_data` + `vocab-*` + `sailfish_*` co-resident, `adms_mqtt_data` ever-growing | `pg_dump` in `backups/` + WAL `wal_keep_size` risk `No space left` | No rotation; `STATUS.md` Phase F backups verified but not pruned | Medium |
| **A3** | `fwupd` + `pam_lastlog.so` err spam in `journalctl` | Obscures real ADMS errors, clutters audit | Ubuntu 24.04 missing `pam_lastlog.so` (replaced by `pam_lastlog2`), `fwupd` no firmware | Low |
| **A4** | No physical PG replica for ADMS (vs vocab) — `pg_stat_replication 0` is correct but single-point | Primary `adms_postgres` is SPOF | Single-node design as intended | Low |
| **A5** | 5s roster poll floods `sync_events` 5988 rows (5m interval) | Table bloat `10 MB` still fine but `HISTORICAL_BACKFILL 24` suggests future history growth | Poll is authoritative primary (deferred native push) | Low |
| **A6** | `write_sessions` 47% `EXPIRED` vs `ADMIN_CLOSED` | Operator confusion, audit noise | 30m TTL short for long fingerprint enroll? | Low |

**No Critical Anomalies** at `2026-09-03T05:38Z`: `adms_zakteco_listener` `LIVE`, `adms_api`/`web` `healthy` `FailingStreak 0`, `pg_locks 0`, `adms_mqtt` `Up 43h`, terminal `192.168.1.201:4370` `open` ping `0.75ms`.

### 3.2 Remediation Roadmap — Prioritized

#### Immediate (0–7 days, non-disruptive, no restart)

| Pri | Action | Owner | Command / Evidence |
|---|---|---|---|
| **I1** | **Fix `mqtt_status UNKNOWN`**: Add `mosquitto_pub -h mqtt -t health/ping` in `app/healthcheck.py` and report `mqtt_status` `HEALTHY`/`DEGRADED`; add `adms_api` Prometheus gauge `adms_collector_health_mqtt`. | Listener | `docker exec adms_zkteco_listener cat /var/run/adms/collector_health.json` → expect `HEALTHY` |
| **I2** | **Disk hygiene:** `docker system prune --volumes` dry-run, `du -sh /home/kanfullbuster/adms-server/backups`, rotate `pg_dump` keep 14d: `find backups -mtime +14 -delete`, add `mosquitto.conf persistence_location` size limit. | Infra | `df -hT` weekly alert at 80% |
| **I3** | **Suppress `fwupd`/`pam_lastlog` noise:** `sudo systemctl mask fwupd.service fwupd-refresh.service`, `grep -r pam_lastlog /etc/pam.d/` → replace with `pam_lastlog2.so` or comment. | Infra | `journalctl --since 24h -p err` should drop from `>20` to `<2` lines |
| **I4** | **Read-only diagnostics for operators:** Expose `GET /admin/diagnostics` (tail 200 lines from `adms_zkteco_listener`, `adms_mqtt`, `collector_health.json` without SSH) already scoped as `ADMIN` in `TODO`, implement behind `require_write_session` read gate. | API+Web | `curl -H "X-Admin-Key" http://192.168.1.248:8081/admin/diagnostics` |

#### Short-Term (1–4 weeks, requires `STATUS.md` gate)

| Pri | Action | Rationale | Gate |
|---|---|---|---|
| **S1** | **Single-worker queue isolation (pyzk):** Confirm Device Command Bus is already single-owner (`device_owner_available true`, `queue_depth 0`, `generation 1`). Add queue depth metric to dashboard and UI `Re-enroll` disables while `device_command_queue_depth>0` to prevent concurrent `enrollment` + `roster` from contending TCP. Document `05:00-10:00` on-time window vs `UTC` storage. | Eliminates future 500 from concurrent `enrollment` | No migration |
| **S2** | **Reverse-proxy unify `8081`+`8082`:** `nginx` on `ai-brain` (`192.168.1.248:443` TLS `certbot`, `192.168.1.248:80` → `https`), `location /api/` → `adms_api:8081`, `location /` → `adms_web:80`, `proxy_set_header Host`, `Access-Control-Allow-Origin` unified, eliminate CORS. Update `API_CORS_ORIGINS` to `https://adms.example.com`. | `STATUS.md:025` CORS fix was narrow; proxy is structural | `docs/` + `docker-compose.yml` |
| **S3** | **Enrollment #2 recovery UI:** Owner-approved diff view (`terminal 1002` vs DB), dry-run `set_user`/`delete_user`, explicit Thai second-ADMIN confirm (per `STATUS.md:110`). Do not auto-reconcile. | Closes last split-state | OWNER GATE |
| **S4** | **Write-session ergonomics:** In `adms_web` System page, show countdown (`expires_at - now()`), `Extend 30m` (new session open after expiry), `OPEN_FAILED` toast with reason `UQ_ONE_UNCLOSED` advisory-lock detail. Reduce `EXPIRED` noise. | 47% expired → UX | No migration |

#### Medium-Term (1–3 months)

| Pri | Action | Rationale |
|---|---|---|
| **M1** | **Observability stack:** `prometheus` + `postgres_exporter` + `redis_exporter` (vocab) + `mosquitto_exporter` + `node_exporter` → `grafana` `ADMS Health` (enrollment success, mapping verified rate, MQTT lag, PG locks, device_connected), `alertmanager` `device_connected=false >2m` → LINE/Email. | `A1` + `A5` + 5s roster visibility |
| **M2** | **Log centralization:** `loki` or `graylog` sidecar, `docker logs --json-file` → `loki`, `sync_events` → `Grafana` table (already append-only). Enable `auditd` `w` on `/home/kanfullbuster/adms-server/.env` and `sql/`. | Eliminate SSH `docker exec` for logs (fragmented diagnostics) |
| **M3** | **Backup & DR test:** `systemd.timer` `pg_dump -Fc adms \| sha256sum` daily to `backups/` (Phase F already verified `pg_restore -l`), quarterly restore to `adms_postgres_shadow`, document RTO/RPO. | `A2` disk + SPOF `A4` |
| **M4** | **Offline-first mobile:** If tablet PWA, reuse `vocab-backend` `MAX(revision)` delta + gzip snapshot pattern (proven) rather than polling, for enrollment capture in poor LAN. | Deferred `Multi-Person Enrollment` |

#### Verification Checklist (After Each Change)

```
docker compose -f /home/kanfullbuster/adms-server/docker-compose.yml config --quiet && docker compose ps # all healthy
docker exec adms_postgres psql -U adms -c "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock'; " # 0
curl -s http://192.168.1.248:8081/healthz && curl -sI http://192.168.1.248:8082 | head -1 # 200
docker exec adms_zkteco_listener cat /var/run/adms/collector_health.json | jq '.state, .device_connected' # LIVE true
pytest tests/ # 825 pass (STATUS.md baseline)
tsc --noEmit && vite build # 0 errors (web)
```

---

### Appendix — Exact Read-Only Commands Executed (Evidence Bundle)

```bash
hostnamectl; free -h; df -hT; ss -tulpn | grep -E "8081|8082|1883|4370"
docker compose ps -a; docker stats --no-stream; docker inspect adms_{api,postgres,zkteco_listener,mqtt,web}
docker exec adms_postgres psql -U adms -c "SELECT * FROM pg_stat_activity; SELECT * FROM pg_locks WHERE NOT granted; SELECT * FROM pg_stat_replication; SELECT pg_size_pretty(pg_database_size('adms'));"
docker exec adms_postgres psql -U adms -c "SELECT event_type,count(*) FROM sync_events GROUP BY 1 ORDER BY 2 DESC; SELECT * FROM write_sessions ORDER BY opened_at DESC LIMIT 10; SELECT * FROM operators;"
docker logs adms_zkteco_listener --since 24h; cat docker/mosquitto.conf; cat /var/run/adms/collector_health.json
ping -c3 192.168.1.201; bash -c 'cat < /dev/null > /dev/tcp/192.168.1.201/4370 && echo open'
docker logs adms_api --since 24h | grep -E "401|403|429|500"; journalctl --since "24h ago" -p err
```

**No write operations performed.** `adms_zkteco_listener` `generation 1` indicates no `set_user`/`delete_user` was triggered during audit; `write_sessions` shows no open session, so production remained write-locked per `STATUS.md:88`.

*Report generated 2026-09-03T05:38+07:00 on `ai-brain` — next audit recommended after `S2` proxy or `S3` Enrollment #2 recovery.*

---

## Follow-up — 2026-10-02

สถานะของรายการใน audit ฉบับนี้ หลังงานรอบวันที่ 2 ต.ค. 2026

### รายการเดิม

| ID | สถานะ | หมายเหตุ |
|---|---|---|
| A1 / I1 `mqtt_status UNKNOWN` | ✅ ปิดแล้ว | collector สะท้อน `MQTTService.connected` ลง health file (`056df7c`), ตอนนี้ `HEALTHY` |
| A2 / I2 disk | ⚠️ แย่ลง | `/` ใช้ 80% (เดิม 75%); Docker build cache 47 GB + images 20.7 GB reclaimable — `docker builder prune` คืนพื้นที่ได้มากที่สุดโดยไม่กระทบ ADMS |
| A3 / I3 `fwupd`/`pam_lastlog` noise | ⏳ ยังไม่ทำ | ต้องใช้ sudo |
| A4 PG single node | ⚠️ เสี่ยงกว่าที่คิด | backup อยู่บนดิสก์เดียวกับ DB: `/data` **ไม่ได้ mount** (เป็นแค่โฟลเดอร์บน `/`) จึงไม่มีสำเนานอกเครื่อง |
| A5 `sync_events` growth | ℹ️ เฝ้าดู | 11,901 แถว (~5,800/เดือน จาก roster poll); DB 12 MB — ยังไม่เป็นปัญหา |
| A6 write session หมดอายุบ่อย | ✅ ไม่เกี่ยวแล้ว | production ปิด Work Session (`API_WORK_SESSION_REQUIRED=false`) — แก้ไขข้อมูลและลงลายนิ้วมือได้ตลอด, สิทธิ์ตาม role + audit |
| I4 diagnostics endpoint | ⏳ ยังไม่ทำ | |
| S1 queue depth ใน UI | ⏳ ยังไม่ทำ | |
| S2 reverse proxy | ⏳ ยังไม่ทำ | พอร์ตยังผูกกับ `192.168.1.248` อย่างเดียว (ไม่เปิดผ่าน Tailscale โดยเจตนา) |
| S3 Enrollment #2 recovery | ⏳ ยังไม่ทำ | |
| S4 write-session ergonomics | ✅ ไม่เกี่ยวแล้ว | ดู A6 |
| M3 backup & DR | ✅ บางส่วน | ดู "ปัญหาใหม่" ข้อ B1 |

### ปัญหาใหม่ที่พบและแก้แล้ว

| ID | ปัญหา | แก้ไข |
|---|---|---|
| B1 | `adms-backup.service` จบด้วย exit 2 ทุกคืน (อย่างน้อยตั้งแต่ 29 ก.ย.) — dump ถูกสร้างจริงแต่ถูกรายงานว่าล้ม เพราะ `ls` กับ glob ที่ว่างใน `/data/adms/backups` + `pipefail` | นับไฟล์ด้วย `find`; รันทดสอบ rc=0, `BACKUP ok` |
| B2 | ตัวตั้งเวลาเปิด/ปิด write window ล้มทุกครั้งตั้งแต่ 23 ก.ย. (parse token ผิด) | `d572aa8` — login ใหม่ทุกครั้งด้วย `jq`, บันทึก `last_run` |
| B3 | รหัสผ่าน ADMIN เป็น plaintext ใน unit systemd | ย้ายไป `.adms_scheduler.env` (600, gitignored), ลบจาก unit, **เปลี่ยนรหัสแล้ว** |
| B4 | หัวเว็บแสดง "● LIVE" ตายตัว ทั้งที่เครื่องสแกนไม่ได้ต่อ | อ่านสถานะจริงจาก collector (`dc425b5`) |
| B5 | ใส่รหัสปัจจุบันผิดตอนเปลี่ยนรหัส → 401 → client logout และขึ้น "ข้อผิดพลาดของระบบ" | คืน 400 พร้อมรหัส error เฉพาะ (`3e0ea67`) |

### นโยบายปัจจุบัน (2026-10-02)

- **แก้ไขข้อมูล / ลงลายนิ้วมือ:** ได้ตลอดเวลา จำกัดตาม role + `API_WRITE_ENABLED` + audit (`sync_events`)
- **สแกนเข้างาน:** นับเฉพาะ 06:30–11:00 (`attendance_policy.scan_window_*`), หลัง 10:00 = มาสาย; สแกนนอกช่วงเก็บไว้แต่ไม่นับ
- **การลา:** บันทึกอย่างเดียว (ผบ.พัน ลงนามแล้ว), ไม่มีอนุมัติ
- **พลทหาร** (`production_scope=false`): ไม่อยู่ในบัญชีพลและการสแกน

### สิ่งที่ควรทำต่อ (เรียงตามความสำคัญ)

1. **Mount HDD `/data`** (หรือส่ง backup ออกนอกเครื่อง) — ตอนนี้ backup กับ DB อยู่บนดิสก์เดียวกัน
2. **คืนพื้นที่ดิสก์:** `docker builder prune` (build cache 47 GB) ก่อนแตะ 85%
3. ปิด timer `adms-auto-session-*` ที่ไม่จำเป็นแล้ว (`sudo systemctl disable --now adms-auto-session-open.timer adms-auto-session-close.timer`)
4. A3 log noise, S2 reverse proxy, S3 Enrollment #2 ตามเดิม
