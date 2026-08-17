# LIVE BASELINE AUDIT REPORT

## Prompt

* PromptID: `AIBRAIN-Audit-LiveBaseline-001`
* mode: READ-ONLY
* timestamp: 2026-08-11T09:27:40+07:00
* target host: `ai-brain` (`192.168.1.248` LAN / `100.68.88.63` Tailscale)
* modifications performed: NO

## Host

* hostname: `ai-brain`
* user: `kanfullbuster` (uid=1000, gid=1000, groups: sudo, docker, adm)
* OS: Ubuntu 24.04.1 LTS (x86_64)
* kernel: `7.0.0-28-generic`
* uptime: 1 day, 14 hours, 20 minutes
* CPU/resource status: 4 vCPUs (`nproc`=4), load average: 0.19, 0.15, 0.07
* memory status: 13.5 GiB total (2.0 GiB used, 9.3 GiB free, 11.5 GiB available)
* disk status: `/` on `/dev/mapper/ubuntu--vg--1-ubuntu--lv` total 232G, used 143G (65%), available 79G
* evidence: VERIFIED LIVE (SSH output from `hostname`, `uname -a`, `uptime`, `df -h /`, `free -m`, `nproc`, `tailscale status`)

## Docker Runtime

* Docker: Docker Engine - Community 29.6.1 (API v1.55, Go go1.26.4, build 8900f1d)
* Compose: Docker Compose version v5.3.1
* total containers observed: 21 containers total (16 running, 5 exited)
* AI-Brain containers: 10 containers running (`n8n_zort`, `n8n_zort_postgres`, `n8n_zort_cloudflared`, `paddle_ocr`, `garmin_api`, `private_api`, `private_postgres`, `player_api`, `player_postgres`, `adminer`)
* stopped/restarting/unhealthy: 
  - AI-Brain scope: 0 stopped, 0 restarting, 0 unhealthy.
  - Unrelated scope: 1 container unhealthy (`sailfish_collector`, 35 restarts), 4 containers exited (`private_ocr`, `mc-superior`, `terraria-server`, `nblm-auth-4`).
* unrelated containers observed: 7 running (`sailfish_collector`, `sailfish_archive_postgres`, `mcmod-mcp-server`, `minecraft-console`, `audioreader-next`, `notebooklm-mcp`, `notebooklm-tunnel`)
* evidence: VERIFIED LIVE (`docker version`, `docker compose version`, `docker ps -a`, `docker inspect`)

## AI-Brain Services

| Service | Container State | Health Evidence | Exposure | Classification |
| ------- | --------------- | --------------- | -------- | -------------- |
| `n8n_zort` | running (Up 38h) | healthy (RestartCount: 0) | `0.0.0.0:5678->5678/tcp` | VERIFIED LIVE |
| `n8n_zort_postgres` | running (Up 38h) | healthy (RestartCount: 0, pg_isready: accepting) | `0.0.0.0:5432->5432/tcp` | VERIFIED LIVE |
| `n8n_zort_cloudflared` | running (Up 38h) | no-healthcheck (RestartCount: 0, registered quic tunnel) | None (Outbound tunnel) | VERIFIED LIVE |
| `paddle_ocr` | running (Up 38h) | healthy (RestartCount: 0) | `172.20.0.9:8010/tcp` (Docker-internal) | VERIFIED LIVE |
| `garmin_api` | running (Up 38h) | healthy (RestartCount: 0, HTTP 200 on `/docs`) | `172.20.0.6:8000/tcp` (Docker-internal) | VERIFIED LIVE |
| `private_api` | running (Up 38h) | healthy (RestartCount: 0, HTTP 401 auth guard) | `172.20.0.7:3000/tcp` (Docker-internal) | VERIFIED LIVE |
| `private_postgres` | running (Up 38h) | no-healthcheck (RestartCount: 0, pg_isready: accepting) | `172.20.0.4:5432/tcp` (Docker-internal) | VERIFIED LIVE |
| `player_api` | running (Up 38h) | healthy (RestartCount: 0) | `172.20.0.5:9733/tcp` (Docker-internal) | VERIFIED LIVE |
| `player_postgres` | running (Up 38h) | healthy (RestartCount: 0, pg_isready: accepting) | `172.20.0.3:5432/tcp` (Docker-internal) | VERIFIED LIVE |
| `adminer` | running (Up 38h) | no-healthcheck (RestartCount: 0, HTTP 200) | `0.0.0.0:8080->8080/tcp` | VERIFIED LIVE |

## Compose

* compose file: `/home/kanfullbuster/n8n-zort/docker-compose.yml`
* file exists: YES (Size: 7,490 bytes, Modified: Aug 2 15:49)
* config valid: YES (`docker compose config` executed cleanly without errors)
* expected services present: YES (`postgres`, `adminer`, `garmin-api`, `player-postgres`, `player-api`, `private-postgres`, `private-api`, `n8n`, `paddle-ocr`, `cloudflared`)
* networks: `default` (bridge network `n8n-zort_default`)
* volumes: `postgres_data`, `private_postgres_data`, `garmin_tokens`, `n8n_data`, `player_postgres_data`
* differences: NONE
* evidence: VERIFIED LIVE (`ls -la`, `docker compose config --services`, `--volumes`, `--networks`)

## Network Exposure

* published ports:
  - `0.0.0.0:5678` / `[::]:5678` (`n8n_zort`)
  - `0.0.0.0:5432` / `[::]:5432` (`n8n_zort_postgres`) — **Public database port exposure**
  - `0.0.0.0:8080` / `[::]:8080` (`adminer`) — **Public adminer web UI exposure**
  - `0.0.0.0:3000` / `[::]:3000` (`audioreader-next`, unrelated service)
  - `0.0.0.0:3001` / `[::]:3001` (`mcmod-mcp-server`, unrelated service)
  - `127.0.0.1:5433` (`sailfish_archive_postgres`, local loopback only)
  - `0.0.0.0:22` / `[::]:22` (SSH)
* relevant listeners: `5678`, `5432`, `8080`, `22`, `3000`, `3001`
* unexpected exposure: PostgreSQL port `5432` and Adminer web interface port `8080` are published on all network interfaces (`0.0.0.0`) without host interface binding restrictions.
* evidence: VERIFIED LIVE (`ss -tulpn`, `docker ps --format 'table {{.Names}}\t{{.Ports}}'`)

## Cloudflare Tunnel

* runtime state: Running (`Up 38 hours`)
* health evidence: Active QUIC tunnel connection registered to edge (`Registered tunnel connection ... location=bkk02 protocol=quic`)
* configuration checked safely: YES (Routing n8n public traffic to `n8n_zort:5678`)
* secrets exposed: NO (Token values masked/redacted in report)
* evidence: VERIFIED LIVE (`docker ps`, `docker logs --tail 5 n8n_zort_cloudflared`)

## Databases

| Database Service | Runtime | Readiness | Connectivity | Classification |
| ---------------- | ------- | --------- | ------------ | -------------- |
| `n8n_zort_postgres` | Running (Up 38h) | Accepting connections (`pg_isready`) | Port 5432 open, healthy | VERIFIED LIVE |
| `player_postgres` | Running (Up 38h) | Accepting connections (`pg_isready`) | Internal port 5432 open, healthy | VERIFIED LIVE |
| `private_postgres` | Running (Up 38h) | Accepting connections (`pg_isready`) | Internal port 5432 open, running | VERIFIED LIVE |

## Application Verification

| Application | Verification Method | Result | Classification |
| ----------- | ------------------- | ------ | -------------- |
| `n8n_zort` | HTTP GET `/healthz` | 200 OK | VERIFIED LIVE |
| `adminer` | HTTP GET `/` | 200 OK | VERIFIED LIVE |
| `garmin_api` | HTTP GET `/docs` | 200 OK | VERIFIED LIVE |
| `private_api` | HTTP GET `/health` | 401 Unauthorized (Auth guard active) | VERIFIED LIVE |
| `paddle_ocr` | HTTP GET `/` | 404 (Server up, route not found on `/`) | VERIFIED LIVE |
| `player_api` | HTTP GET `/` | 404 (Server up, route not found on `/`) | VERIFIED LIVE |

## Runtime Warnings

* restart loops: 0 restart loops in AI-Brain scope. Unrelated service `sailfish_collector` has 35 restarts.
* unhealthy services: 0 unhealthy services in AI-Brain scope. `sailfish_collector` is unhealthy.
* resource pressure: NONE (Disk `/` usage at 65%, free memory 9.3 GiB, CPU load average 0.19).
* recent critical errors: NONE observed in primary AI-Brain containers.
* host key / IP discrepancy warning: Tailscale client on local management workstation is attached to a separate tailnet (`tail7e6889.ts.net`), resolving `ai-brain` via MagicDNS as `100.71.100.77`. Host `ai-brain`'s own internal Tailscale interface IP is `100.68.88.63`, matching documentation. LAN direct IP `192.168.1.248` is verified operational.

## Documented vs Live

| Item | Documented State | Verified Live State | Classification |
| ---- | ---------------- | ------------------- | -------------- |
| Host Identity | `ai-brain` | `ai-brain` (Ubuntu 24.04.1, Linux 7.0.0-28) | MATCH |
| Tailscale IP | `100.68.88.63` | `100.68.88.63` (Verified on host) | MATCH |
| LAN IP | Unspecified | `192.168.1.248` | VERIFIED LIVE |
| Workstation Tailscale DNS | N/A | `100.71.100.77` (Local workstation tailnet mapping) | DIFFERENT |
| Compose Path | `/home/kanfullbuster/n8n-zort/docker-compose.yml` | Present, valid, 10 services | MATCH |
| Primary AI-Brain Containers | 10 services running | 10 services running, 0 restarts | MATCH |
| Container Health (n8n stack) | Healthy / Running | `n8n_zort`, `n8n_zort_postgres`, `garmin_api`, `paddle_ocr`, `private_api`, `player_api`, `player_postgres` healthy | MATCH |
| Unhealthy Services | `sailfish_collector` unhealthy | `sailfish_collector` unhealthy (35 restarts) | MATCH |
| Public Port Exposure | PostgreSQL 5432 & Adminer 8080 published on 0.0.0.0 | Published on 0.0.0.0:5432 and 0.0.0.0:8080 | MATCH |

## Findings

### Critical
* NONE

### High
* NONE

### Medium
1. **Public PostgreSQL Exposure (`0.0.0.0:5432`)**: `n8n_zort_postgres` publishes port 5432 to all network interfaces (`0.0.0.0`), exposing PostgreSQL externally beyond Docker internal networks or Tailscale.
2. **Public Adminer Exposure (`0.0.0.0:8080`)**: `adminer` web UI is exposed publicly on `0.0.0.0:8080` without VPN or Tailscale binding restrictions.

### Low
1. **Missing Container Healthchecks**: `private_postgres`, `adminer`, and `n8n_zort_cloudflared` do not define Docker container healthchecks in `docker-compose.yml`.
2. **Workstation Tailscale DNS Routing Mismatch**: Local management workstation Tailscale network maps `ai-brain` to `100.71.100.77`, whereas `ai-brain` native Tailscale interface IP is `100.68.88.63`. LAN IP `192.168.1.248` provides direct local connection.

## Not Tested

* n8n production workflow execution (to prevent external side effects or duplicate automation executions)
* Direct database SQL query execution / tables inspection (READ-ONLY metadata verification performed via `pg_isready` only)
* Garmin API mutation endpoints
* Telegram bot command execution
* Cloudflare tunnel credential rotation / token inspection

## Recommended Next Actions

1. Propose PromptID `# PromptID: AIBRAIN-Infra-HardenNetwork-001` (Plan ONLY): Investigate network dependencies and produce a safe network hardening plan.
2. Propose PromptID `# PromptID: AIBRAIN-Infra-HardenNetwork-002` (Plan ONLY, WRITE mode require explicit approval): Restrict PostgreSQL `5432` and Adminer `8080` port bindings in `docker-compose.yml` to localhost / Tailscale or Docker-internal network.

## FINAL

* live baseline established: YES
* documentation materially matches live state: YES
* critical blockers: NONE
* safe to proceed to planning: YES
* safe to perform writes: NOT AUTHORIZED
* modifications performed: NO

STOP.
