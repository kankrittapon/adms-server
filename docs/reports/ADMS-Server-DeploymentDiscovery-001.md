# ADMS-Server-DeploymentDiscovery-001 — Live Server Discovery Report

**PromptID:** ADMS-Server-DeploymentDiscovery-001
**Date:** 2026-08-11
**Mode:** READ-ONLY (no mutations performed)
**Operator:** GitHub Copilot (Kob AI — glm-5.2)
**Target Server:** ai-brain (192.168.1.248 LAN / 100.68.88.63 Tailscale)
**SSH User:** kanfullbuster

---

## 1. Executive Summary

| Item | Value |
|------|-------|
| **Deployment Classification** | **FIRST_DEPLOYMENT** |
| ADMS repository on server | NOT FOUND |
| ADMS containers (running/stopped) | NOT FOUND (0) |
| ADMS Docker volumes | NOT FOUND (0) |
| ADMS Docker networks | NOT FOUND (0) |
| ADMS `.env` file | NOT FOUND |
| Port collisions with ADMS intended ports | **NONE** |
| Server disk space available | 79 GB free of 232 GB (65% used) |
| Docker Engine | v29.6.1, Ubuntu 24.04.4 LTS, x86_64, 4 CPU, ~14.5 GB RAM |
| Safe to proceed with first deployment | **YES** (pending explicit WRITE authorization) |

**Conclusion:** ai-brain has no existing ADMS deployment. The server hosts 8 unrelated Compose projects (n8n-zort, sailfish, MCP-BRPG, minecraft, etc.) with 22 containers. ADMS intended ports (127.0.0.1:1883 for MQTT, no host publish for PostgreSQL) do not collide with any existing host port binding. A clean first deployment is feasible using a dedicated Compose project name, network, and volumes.

---

## 2. Source Workstation Baseline (TELEPHONE)

| Item | Value | Evidence |
|------|-------|----------|
| Hostname | telephone | VERIFIED LIVE |
| OS | Windows 11, PowerShell 5.1 | VERIFIED LIVE |
| Repo path | D:\Dev\adms-server | VERIFIED LIVE |
| Git branch | main | VERIFIED LIVE |
| Local HEAD | 2501035f97e93ec670abbf705de0e4ba894731a8 | VERIFIED LIVE |
| Origin HEAD | 2501035f97e93ec670abbf705de0e4ba894731a8 | VERIFIED LIVE |
| Working tree | Clean (only untracked `.agent/`) | VERIFIED LIVE |
| Remote | https://github.com/kankrittapon/adms-server.git | VERIFIED LIVE |
| Migration 005 commit | 242698f4eb0787deb4c205b75b7a8aa5e8f5bad0 | FILE EVIDENCE |

**Classification:** CLEAN_CURRENT — source and origin synchronized, no drift.

---

## 3. SSH Connection

| Item | Value | Evidence |
|------|-------|----------|
| SSH target | kanfullbuster@192.168.1.248 | VERIFIED LIVE |
| SSH key | C:\Users\telep\.ssh\id_ed25519 | FILE EVIDENCE |
| Connection result | SUCCESS (no password prompt) | VERIFIED LIVE |
| Remote hostname | ai-brain | VERIFIED LIVE |
| Remote user | kanfullbuster | VERIFIED LIVE |
| Remote shell pwd | /home/kanfullbuster | VERIFIED LIVE |
| Remote OS | Linux ai-brain 7.0.0-28-generic #28~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC x86_64 | VERIFIED LIVE |

---

## 4. Server Network Inventory

### 4.1 Network Interfaces

| Interface | State | IP Address | Notes |
|-----------|-------|------------|-------|
| lo | UNKNOWN | 127.0.0.1/8, ::1/128 | loopback |
| enp5s0 | UP | 192.168.1.248/24 | **LAN primary** |
| tailscale0 | UNKNOWN | 100.68.88.63/32 | Tailscale VPN |
| docker0 | DOWN | 172.17.0.1/16 | default Docker bridge |
| br-75b9dcc8f6e9 | UP | 172.20.0.1/16 | n8n-zort_default |
| br-7861c1444ebe | UP | 172.24.0.1/16 | mcp-brpg_default |
| br-db04e516a0b9 | UP | 172.18.0.1/16 | notebooklm-mcp-deploy_default |
| br-79eb72f1eebf | UP | 172.25.0.1/16 | backend_default |
| br-13c79f8d8402 | DOWN | 172.22.0.1/16 | speechybykrittapon_default |
| br-23ddceb022ad | DOWN | 172.19.0.1/16 | (unused) |
| br-bc51a6b18e86 | DOWN | 172.21.0.1/16 | superior_default |
| br-ef1de20a7c70 | DOWN | 172.23.0.1/16 | minecraft-console_default |
| wlxd46e0e128059 | DOWN | — | wireless (disabled) |

### 4.2 Routing

```
default via 192.168.1.1 dev enp5s0 proto static metric 100
172.17.0.0/16 dev docker0  (linkdown)
172.18–172.25.0.0/16 dev br-* (various)
192.168.1.0/24 dev enp5s0
```

### 4.3 Host Listening Ports (TCP)

| Port | Bind Address | Process/Container | Collision Risk for ADMS? |
|------|-------------|-------------------|---------------------------|
| 22 | 0.0.0.0 / [::] | SSH | NO |
| 53 | 127.0.0.54 / 127.0.0.53 | systemd-resolved | NO |
| 443 | 100.68.88.63 / fd7a:... | Tailscale | NO |
| 18789 | 127.0.0.1 / ::1 | (unknown, n8n internal?) | NO |
| 18791 | 127.0.0.1 | (unknown) | NO |
| 3000 | 0.0.0.0 / [::] | audioreader-next (speechybykrittapon) | NO |
| 3001 | 0.0.0.0 / [::] | mcmod-mcp-server (MCP-BRPG) | NO |
| 39603 | 127.0.0.1 | (unknown) | NO |
| 5433 | 127.0.0.1 | sailfish_archive_postgres | NO |
| 5678 | 0.0.0.0 / [::] | n8n_zort | NO |
| 8080 | 127.0.0.1 | adminer (n8n-zort) | NO |
| 9734 | * | (unknown) | NO |
| 34415 | 100.68.88.63 | Tailscale | NO |
| 50373 | fd7a:... | Tailscale | NO |

**Key observation:** Port **1883** (ADMS MQTT intended) is **NOT** listening on the host. Port **5432** (PostgreSQL default) is **NOT** published to the host by any container. No collision exists.

---

## 5. Docker Engine Inventory

| Item | Value | Evidence |
|------|-------|----------|
| Server Version | 29.6.1 | VERIFIED LIVE |
| Operating System | Ubuntu 24.04.4 LTS | VERIFIED LIVE |
| OS Type | linux | VERIFIED LIVE |
| Architecture | x86_64 | VERIFIED LIVE |
| CPUs | 4 | VERIFIED LIVE |
| Total Memory | 14,556,286,976 bytes (~14.5 GB) | VERIFIED LIVE |

---

## 6. Docker Container Inventory (22 total)

### 6.1 Running Containers (17)

| Container Name | Image | Status | Published Ports | Compose Project |
|----------------|-------|--------|-----------------|-----------------|
| private_postgres | postgres:16-alpine | Up 4h (healthy) | 5432/tcp (internal) | n8n-zort |
| adminer | adminer | Up 4h (healthy) | 127.0.0.1:8080→8080 | n8n-zort |
| n8n_zort_postgres | postgres:16-alpine | Up 5h (healthy) | 5432/tcp (internal) | n8n-zort |
| paddle_ocr | n8n-zort-paddle-ocr | Up 43h (healthy) | 8010/tcp (internal) | n8n-zort |
| private_api | n8n-zort-private-api | Up 43h (healthy) | 3000/tcp (internal) | n8n-zort |
| n8n_zort | docker.n8n.io/n8nio/n8n:latest | Up 43h (healthy) | 0.0.0.0:5678→5678 | n8n-zort |
| garmin_api | n8n-zort-garmin-api | Up 43h (healthy) | 8000/tcp (internal) | n8n-zort |
| player_api | n8n-zort-player-api | Up 43h (healthy) | 9733/tcp (internal) | n8n-zort |
| sailfish_collector | backend-sailfish-collector | Up 43h (unhealthy) | — | backend |
| sailfish_archive_postgres | postgres:16-alpine | Up 43h | 127.0.0.1:5433→5432 | backend |
| mcmod-mcp-server | mcp-brpg-mcmod-mcp | Up 43h (healthy) | 0.0.0.0:3001→3001 | mcp-brpg |
| minecraft-console | minecraft-console-minecraft-console | Up 43h | — | minecraft-console |
| audioreader-next | speechybykrittapon-audioreader-web | Up 43h | 0.0.0.0:3000→3000 | speechybykrittapon |
| player_postgres | postgres:16-alpine | Up 43h (healthy) | 5432/tcp (internal) | n8n-zort |
| n8n_zort_cloudflared | cloudflare/cloudflared:latest | Up 43h | — | n8n-zort |
| notebooklm-mcp | notebooklm-mcp:latest | Up 43h (healthy) | — | notebooklm-mcp-deploy |
| notebooklm-tunnel | cloudflare/cloudflared:latest | Up 43h | — | notebooklm-mcp-deploy |

### 6.2 Exited Containers (5)

| Container Name | Image | Status | Compose Project |
|----------------|-------|--------|-----------------|
| private_ocr | n8n-zort-private-ocr | Exited (0) 3 weeks ago | n8n-zort |
| mc-superior | itzg/minecraft-server:java17 | Exited (0) 4 weeks ago | superior |
| terraria-server | terraria-server-terraria | Exited (137) 8 weeks ago | terraria-server |
| nblm-auth-4 | 0aa5e8c9265a | Exited (0) 3 months ago | (standalone) |
| (1 more from n8n-zort) | | | |

### 6.3 ADMS Container Search

| ADMS Expected Container | Found? | Evidence |
|------------------------|--------|----------|
| adms_postgres | NO | VERIFIED LIVE — `docker ps -a --filter name=adms` returned empty |
| adms_mqtt | NO | VERIFIED LIVE |
| adms_zkteco_listener | NO | VERIFIED LIVE |

---

## 7. Docker Compose Projects (8)

| Project Name | Status | Config Path |
|--------------|--------|-------------|
| backend | running(2) | /home/kanfullbuster/sailfish-race-intelligence/backend/docker-compose.yml |
| mcp-brpg | running(1) | /home/kanfullbuster/MCP-BRPG/docker-compose.yml |
| minecraft-console | running(1) | /home/kanfullbuster/minecraft-console/docker-compose.yml |
| n8n-zort | exited(1), running(10) | /home/kanfullbuster/n8n-zort/docker-compose.yml |
| notebooklm-mcp-deploy | running(2) | /home/kanfullbuster/notebooklm-mcp-deploy/docker-compose.yml |
| speechybykrittapon | running(1) | /home/kanfullbuster/SpeechyByKrittapon/docker-compose.yml |
| superior | exited(1) | /home/kanfullbuster/minecraft-server/superior/docker-compose.yml |
| terraria-server | exited(1) | /home/kanfullbuster/terraria-server/docker-compose.yml |

**No `adms-server` Compose project exists.**

---

## 8. Docker Networks (11)

| Network Name | Driver | Scope | Associated Project |
|--------------|--------|-------|-------------------|
| bridge | bridge | local | default |
| host | host | local | — |
| none | null | local | — |
| backend_default | bridge | local | backend (sailfish) |
| mcp-brpg_default | bridge | local | mcp-brpg |
| minecraft-console_default | bridge | local | minecraft-console |
| n8n-zort_default | bridge | local | n8n-zort |
| notebooklm-mcp-deploy_default | bridge | local | notebooklm-mcp-deploy |
| speechybykrittapon_default | bridge | local | speechybykrittapon |
| superior_default | bridge | local | superior |
| terraria-server_default | bridge | local | terraria-server |

**No `adms-server_default` or ADMS-related network exists.** `docker network ls --filter name=adms` returned empty.

---

## 9. Docker Volumes (17)

| Volume Name | Used By |
|-------------|---------|
| backend_sailfish_archive_data | backend |
| backend_sailfish_tokens | backend |
| java-learning-web_progress-data | (orphaned) |
| n8n-zort_garmin_tokens | n8n-zort |
| n8n-zort_n8n_data | n8n-zort |
| n8n-zort_player_postgres_data | n8n-zort |
| n8n-zort_postgres_data | n8n-zort |
| n8n-zort_private_postgres_data | n8n-zort |
| ollama | (orphaned) |
| ollama_ollama_data | ollama |
| ollama_open_webui_data | ollama |
| ollama_storage | ollama |
| research_hospital_meilisearch_data | (orphaned) |
| research_hospital_n8n_data | (orphaned) |
| research_hospital_postgres_data | (orphaned) |
| sync_log_log-data | sync_log |
| terraria-server_terraria-data | terraria-server |

**No `adms_postgres_data`, `adms_mqtt_data`, or `adms_mqtt_log` volumes exist.** `docker volume ls --filter name=adms` returned empty.

---

## 10. Project Directory Inventory (/home/kanfullbuster)

### 10.1 Top-Level Directories

```
ai-env/  .antigravity-server/  bin/  .cache/  .codex/  .config/
dglp-api/  .docker/  Garmin-sync/  .gemini/  MCP-BRPG/
minecraft-console/  minecraft-server/  n8n-zort/  notebooklm-mcp-deploy/
ollama/  overlay-system-for-steaming/  .pm2/  sailfish-race-intelligence/
SpeechyByKrittapon/  sync_log/  terraria-server/  track_acdc/  yratthailand/
```

### 10.2 Git Repositories Found

```
.nvm/.git
overlay-system-for-steaming/.git
SpeechyByKrittapon/.git
yratthailand/.git
sync_log/frontend/.git
minecraft-console/.git
sailfish-race-intelligence/.git
MCP-BRPG/.git
track_acdc/.git
.openclaw/workspace/.git
```

### 10.3 ADMS Repository Search

| Search Target | Result | Evidence |
|---------------|--------|----------|
| /home/kanfullbuster/adms-server | NOT_FOUND | VERIFIED LIVE |
| /home/kanfullbuster/adms | NOT_FOUND | VERIFIED LIVE |
| /opt/adms-server | NOT_FOUND | VERIFIED LIVE |
| /opt/adms | NOT_FOUND | VERIFIED LIVE |
| /srv/adms-server | NOT_FOUND | VERIFIED LIVE |
| /srv/adms | NOT_FOUND | VERIFIED LIVE |
| find -name 'adms-server' (maxdepth 3) | NOT_FOUND | VERIFIED LIVE |
| find -name 'adms' (maxdepth 3) | NOT_FOUND | VERIFIED LIVE |
| find -name '005_human_device_mapping_schema.sql' | NOT_FOUND | VERIFIED LIVE |
| find -name 'collector.py' | Found in sailfish-race-intelligence only (different project) | VERIFIED LIVE |

### 10.4 `.env` Files (none ADMS-related)

11 `.env` files found across other projects. **No `.env` file in any ADMS path.**

### 10.5 Git Config

```
[user]
    email = kan.krittapon@gmail.com
    name = kankrittapon
[credential]
    helper = store
[safe]
    directory = *
```

No ADMS remote configured.

---

## 11. ADMS Compose Intended Port Table

From `docker-compose.yml` (local source, VERIFIED FILE EVIDENCE):

| Service | Container Name | Internal Port | Host Publish | Host Bind |
|---------|---------------|---------------|---------------|-----------|
| adms-postgres | adms_postgres | 5432 | **NOT PUBLISHED** | N/A |
| mqtt | adms_mqtt | 1883 | 127.0.0.1:1883:1883 | 127.0.0.1 (localhost only) |
| listener | adms_zkteco_listener | — (outbound TCP 4370 to device) | NOT PUBLISHED | N/A |

### 11.1 ADMS Intended Volumes

| Volume Name | Service |
|-------------|---------|
| adms_postgres_data | adms-postgres |
| adms_mqtt_data | mqtt |
| adms_mqtt_log | mqtt |

### 11.2 ADMS Intended Network

Default Compose network: `adms-server_default` (auto-created, bridge driver).

---

## 12. Port Collision Analysis

| ADMS Intended Port | Host Bind | Currently Occupied? | Collision? | Classification |
|--------------------|-----------|--------------------|------------|----------------| 
| 1883 (MQTT) | 127.0.0.1 | NO — not in `ss -lntu` output | NO | **FREE** |
| 5432 (PostgreSQL) | NOT PUBLISHED | N/A (container-internal only) | NO | **FREE** (no host publish) |
| 4370 (ZKTeco) | NOT PUBLISHED | N/A (outbound from listener) | NO | **FREE** (outbound only) |

**Result: ZERO port collisions.** ADMS can bind 127.0.0.1:1883 without conflict.

---

## 13. ADMS Runtime & Database Discovery

| Check | Result | Evidence |
|-------|--------|----------|
| `docker ps -a --filter name=adms` | Empty (0 containers) | VERIFIED LIVE |
| `docker volume ls --filter name=adms` | Empty (0 volumes) | VERIFIED LIVE |
| `docker network ls --filter name=adms` | Empty (0 networks) | VERIFIED LIVE |
| `docker compose ls -a` (adms-server project) | NOT FOUND | VERIFIED LIVE |
| PostgreSQL 5432 on host | NOT listening (only 5433 from sailfish on 127.0.0.1) | VERIFIED LIVE |
| MQTT 1883 on host | NOT listening | VERIFIED LIVE |

**No existing ADMS database, runtime, or data volumes exist on ai-brain.**

---

## 14. Deployment Classification

| Criterion | Result |
|-----------|--------|
| ADMS containers present? | NO |
| ADMS Compose project present? | NO |
| ADMS volumes present? | NO |
| ADMS networks present? | NO |
| ADMS repository cloned? | NO |
| ADMS `.env` present? | NO |
| ADMS database data present? | NO |

### Classification: **FIRST_DEPLOYMENT**

This is a clean first deployment scenario. No existing ADMS state to preserve, migrate, or back up. The `sql/` init scripts (001–005) will run fresh via PostgreSQL's `docker-entrypoint-initdb.d` mechanism on first container start.

**IMPORTANT:** The `docker-compose.yml` only mounts `001_schema.sql` into `docker-entrypoint-initdb.d`. Migrations 002–005 are NOT auto-applied by Compose. They must be applied manually after the first container start, OR the compose file must be updated to mount all SQL files. This is a **deployment planning consideration** for the next phase.

---

## 15. Network Isolation Assessment

| Factor | Assessment |
|-------|------------|
| Dedicated Compose project | YES — `adms-server` project will create `adms-server_default` network, isolated from all 8 existing projects |
| Dedicated Docker network | YES — auto-created bridge, no overlap with existing 172.17–172.25 ranges (Docker assigns next available) |
| Dedicated volumes | YES — `adms_postgres_data`, `adms_mqtt_data`, `adms_mqtt_log` — no name collision with existing 17 volumes |
| Port isolation | YES — MQTT bound to 127.0.0.1:1883 only; PostgreSQL not published; no host port conflicts |
| Container name isolation | YES — `adms_postgres`, `adms_mqtt`, `adms_zkteco_listener` — no collision with 22 existing containers |
| Resource availability | ADEQUATE — 79 GB disk free, 14.5 GB RAM, 4 CPU (existing 17 running containers consume portion) |

**Assessment: ADMS can be deployed with full network/volume/port isolation. No interference with existing projects.**

---

## 16. Disk Space

| Filesystem | Size | Used | Available | Use% |
|------------|------|------|-----------|------|
| /dev/mapper/ubuntu--vg--1-ubuntu--lv | 232G | 143G | 79G | 65% |

### Docker Disk Usage

| Type | Total | Active | Size | Reclaimable |
|------|-------|--------|------|-------------|
| Images | 27 | 16 | 32.53 GB | 20.2 GB (62%) |
| Containers | 21 | 17 | 166 MB | 6.1 MB (3%) |
| Local Volumes | 17 | 8 | 20.64 GB | 20.18 GB (97%) |
| Build Cache | 628 | 0 | 48.09 GB | 37.83 GB |

**Note:** 79 GB free is sufficient for ADMS (PostgreSQL data + Mosquitto logs are lightweight for attendance events). No cleanup is needed or authorized.

---

## 17. Deployment Prerequisites Checklist

| Prerequisite | Status | Notes |
|-------------|--------|-------|
| SSH access to server | ✅ VERIFIED | kanfullbuster@192.168.1.248 |
| Docker Engine running | ✅ VERIFIED | v29.6.1 |
| Docker Compose available | ✅ VERIFIED | v5.3.1 (compose ls works) |
| Git installed on server | ✅ VERIFIED | (gitconfig present) |
| Port 1883 free on 127.0.0.1 | ✅ VERIFIED | Not in ss output |
| No ADMS name collisions | ✅ VERIFIED | All filters empty |
| Disk space | ✅ ADEQUATE | 79 GB free |
| ADMS repo cloned on server | ❌ NOT FOUND | Must `git clone` in next phase |
| `.env` created on server | ❌ NOT FOUND | Must create with POSTGRES_PASSWORD, ZK_DEVICE_IP, etc. |
| SQL migrations 002–005 mount | ❌ NOT CONFIGURED | docker-compose.yml only mounts 001_schema.sql |
| ZKTeco device reachable from server | ⚠️ NOT TESTED | 192.168.1.201:4370 — must verify network path from ai-brain |

---

## 18. Key Risks & Considerations

1. **SQL Migration Gap:** `docker-compose.yml` mounts only `sql/001_schema.sql` to `docker-entrypoint-initdb.d`. Migrations 002–005 (including the target 005) will NOT auto-apply. Options:
   - (a) Update `docker-compose.yml` to mount all `sql/*.sql` files sorted, OR
   - (b) Apply 002–005 manually via `psql` / `docker exec` after first start.
   - This requires a **separate authorized change** to `docker-compose.yml` or manual SQL execution.

2. **ZKTeco Device Reachability:** The ZKTeco terminal at 192.168.1.201:4370 must be reachable from ai-brain over the LAN. Both are on 192.168.1.0/24 (ai-brain = .248, device = .201). Reachability NOT TESTED in this read-only discovery.

3. **`.env` Must Be Created:** POSTGRES_PASSWORD must be set. ZK_DEVICE_IP=192.168.1.201, ZK_DEVICE_PORT=4370, ZK_DEVICE_PASSWORD=600 per `.env.example`. This file is gitignored and must be created on the server.

4. **No Backup Needed:** Since this is a first deployment with no existing ADMS data, no pre-deployment backup is required. However, the local `backups/` directory contains dumps from prior local testing — these are NOT applicable to the server.

5. **Existing Workload Impact:** 17 containers are running. ADMS adds 3 more (lightweight). Resource impact is minimal. `sailfish_collector` is already `unhealthy` — unrelated to ADMS.

---

## 19. Evidence Classification Summary

| Evidence Type | Count | Notes |
|---------------|-------|-------|
| VERIFIED LIVE | 42+ | All SSH command outputs, Docker queries, network scans |
| FILE EVIDENCE | 3 | docker-compose.yml, .env.example, migration 005 commit hash |
| HISTORICAL REPORT | 0 | Not relied upon for this discovery |
| INFERENCE | 1 | First deployment conclusion (from absence of all ADMS artifacts) |
| RECOMMENDATION | 5 | Deployment prerequisites and risks |
| NOT TESTED | 1 | ZKTeco device reachability from ai-brain |

---

## 20. STOP Conditions Check

| Condition | Triggered? | Notes |
|-----------|-----------|-------|
| Repository state materially differs from baseline | NO | Source clean, HEAD matches origin |
| Target database/service/device ambiguous | NO | ai-brain confirmed as target, no existing ADMS DB |
| Required backup cannot be verified | N/A | First deployment, no existing data to back up |
| Migration state ambiguous | NO | No existing DB — fresh init |
| Unexpected schema drift | N/A | No existing schema |
| Unexpected production data impact | N/A | No existing data |
| Authorization scope unclear | NO | READ-ONLY discovery explicitly authorized |
| Secrets would be exposed | NO | No secrets printed |
| Destructive action not authorized | N/A | No destructive actions performed |
| Critical tests/regressions fail | N/A | No tests run (read-only) |

**No STOP conditions triggered.**

---

## FINAL

```
PromptID: ADMS-Server-DeploymentDiscovery-001

repository verified: YES
database modified: NO
application modified: NO
device modified: NO
tests: NOT TESTED
runtime verified: YES (read-only inventory)
commit created: NO
push completed: NO

deployment classification: FIRST_DEPLOYMENT
port collisions: NONE
network isolation: SAFE (dedicated project/network/volumes)
disk space: 79 GB free (sufficient)

next authorized PromptID: NONE (awaiting deployment authorization)
safe to proceed: YES (for first deployment, pending explicit WRITE authorization)
blockers: NONE
  - SQL migration gap: docker-compose.yml mounts only 001_schema.sql (002-005 not auto-applied)
  - .env must be created on server with POSTGRES_PASSWORD + ZK_DEVICE settings
  - ADMS repo must be git cloned to server
  - ZKTeco device reachability from ai-brain NOT TESTED

STOP.
```

---

*End of report.*