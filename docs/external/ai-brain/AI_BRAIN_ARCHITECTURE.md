# AI-Brain Architecture

## Document Status

* **Last Verified Timestamp**: 2026-08-11T09:44:00+07:00
* **Source PromptID**: `AIBRAIN-Architecture-MapCurrentState-001`
* **Network Hardening Baseline**: `AIBRAIN-Infra-HardenNetwork-002`
* **Architecture Status**: Active Canonical Architecture Document
* **Evidence Classification**: Grounded on VERIFIED LIVE runtime state and verified repository Compose configuration.

---

## System Overview

AI-Brain is an automated workflow, data integration, and personal API ecosystem hosted on a dedicated Linux host (`ai-brain`). At its core, the platform runs an `n8n` workflow automation engine integrated with custom REST APIs (`private_api`, `player_api`, `garmin_api`, `paddle_ocr`), specialized relational databases (`n8n_zort_postgres`, `private_postgres`, `player_postgres`), and an outbound Cloudflare Tunnel (`n8n_zort_cloudflared`) for secure public webhook ingress.

---

## Host Architecture

* **Primary Hostname**: `ai-brain`
* **Operating System**: Ubuntu 24.04.1 LTS (x86_64, Linux Kernel `7.0.0-28-generic`)
* **Primary User**: `kanfullbuster` (UID: 1000)
* **LAN Address**: `192.168.1.248` (VERIFIED LIVE LAN interface)
* **Tailscale Address**: `100.68.88.63` (VERIFIED LIVE Tailscale interface)
* **Docker Runtime**: Docker Engine 29.6.1 / Docker Compose v5.3.1
* **Compose Project Directory**: `/home/kanfullbuster/n8n-zort` (`docker-compose.yml`)

---

## Component Inventory

| Component | Purpose | Network | Listening Port / Exposure | Persistence / Volume | Dependencies | Evidence Classification |
| --------- | ------- | ------- | ------------------------- | -------------------- | ------------ | ----------------------- |
| `n8n_zort` | Core workflow automation & ETL engine | `n8n-zort_default` | Host published `0.0.0.0:5678` | `n8n_data`, bind `/files` | `n8n_zort_postgres`, `private_api`, `player_api` | VERIFIED LIVE |
| `n8n_zort_postgres` | PostgreSQL database for n8n execution data & ZORT ETL storage | `n8n-zort_default` | Container internal `5432/tcp` (Host port 5432 removed) | `postgres_data`, `./postgres/init` | None | VERIFIED LIVE |
| `n8n_zort_cloudflared` | Outbound Cloudflare Tunnel routing public webhooks to `n8n_zort` | `n8n-zort_default` | None (Outbound QUIC connection to Cloudflare edge) | None | `n8n_zort` | VERIFIED LIVE |
| `paddle_ocr` | Thai receipt OCR service using PaddleOCR v5 | `n8n-zort_default` | Container internal `8010/tcp` | None | None | VERIFIED LIVE |
| `garmin_api` | Garmin Connect activity extraction & data conversion service | `n8n-zort_default` | Container internal `8000/tcp` | `garmin_tokens` | External Garmin API | VERIFIED LIVE |
| `private_api` | Private data API & file management service | `n8n-zort_default` | Container internal `3000/tcp` | Bind `/files` | `private_postgres` | VERIFIED LIVE |
| `private_postgres` | Isolated PostgreSQL database for Private API | `n8n-zort_default` | Container internal `5432/tcp` | `private_postgres_data` | None | VERIFIED LIVE |
| `player_api` | Task/queue ingest API for Player service | `n8n-zort_default` | Container internal `9733/tcp` | None | `player_postgres` | VERIFIED LIVE |
| `player_postgres` | Isolated PostgreSQL database for Player queue | `n8n-zort_default` | Container internal `5432/tcp` | `player_postgres_data` | None | VERIFIED LIVE |
| `adminer` | Web GUI for database administration | `n8n-zort_default` | Host loopback `127.0.0.1:8080` (Restricted to localhost) | None | `n8n_zort_postgres` | VERIFIED LIVE |

---

## Current Network Architecture

```text
               [ External Clients / Telegram / ZORT API ]
                                   |
                                   v (Public HTTPS Webhooks)
                         [ Cloudflare Edge ]
                                   |
                      (Outbound QUIC Tunnel)
                                   |
                         n8n_zort_cloudflared
                                   |
                        (Internal HTTP:5678)
                                   |
                                   v
  [ Host LAN 192.168.1.248 ] ---> n8n_zort:5678 <--- [ Tailscale 100.68.88.63 ]
                                   |
          =========================+=========================
          | Docker Internal Bridge Network (n8n-zort_default)|
          =========================+=========================
               |                   |                  |
               v                   v                  v
       n8n_zort_postgres      paddle_ocr:8010    garmin_api:8000
       (Internal 5432)             |                  |
               |                   +--------+---------+
               |                            |
               +---> private_api:3000 ------+---> private_postgres (Internal 5432)
               |
               +---> player_api:9733 -------+---> player_postgres (Internal 5432)


  [ Management Workstation ]
               |
               v (SSH Port Forwarding: ssh -L 8080:127.0.0.1:8080)
    http://localhost:8080
               |
               v
         adminer:8080 (Bound to 127.0.0.1 on host)
               |
               +---> (Connects to postgres:5432, private-postgres:5432, player-postgres:5432)
```

---

## Data Flow Architecture

### 1. Telegram / Personal Bot Actions Workflow
```text
Telegram User -> Telegram Webhook -> Cloudflare Tunnel -> n8n_zort:5678
      |
      +--> /eat, /caleat, /trackeat ----> n8n_zort_postgres
      +--> Receipt Slip (Image) -------> paddle_ocr:8010 -> receipt_logs in n8n_zort_postgres
      +--> Workout URL / Routine ------> garmin_api:8000 -> workout tables in n8n_zort_postgres
      +--> Private File / Profile ------> private_api:3000 -> private_postgres
      +--> Player Queue Task ----------> player_api:9733 -> player_postgres
```

### 2. ZORT E-Commerce Integration / ETL Workflow
```text
ZORT API (v4) <---> n8n_zort (Scheduled Cron / Webhook) <---> n8n_zort_postgres
                                  |
                                  +--> Daily Sales & Inventory Reports
```

---

## Database Architecture

AI-Brain strictly segregates database state into three isolated PostgreSQL instances to maintain domain boundaries:

1. **`n8n_zort_postgres`** (`postgres:16-alpine`):
   - **Database Name**: `n8n`
   - **Purpose**: Stores n8n workflow execution state, credential metadata, Telegram receipt/food logs, Garmin activity logs, and ZORT sales data.
   - **Exposure**: Docker internal network only (`postgres:5432`). Host port `5432` publishing is removed.
2. **`private_postgres`** (`postgres:16-alpine`):
   - **Database Name**: `private`
   - **Purpose**: Stores private profile data, user secrets, and file metadata accessed exclusively by `private_api`.
   - **Exposure**: Docker internal network only (`private-postgres:5432`).
3. **`player_postgres`** (`postgres:16-alpine`):
   - **Database Name**: `player_queue`
   - **Purpose**: Stores task queues and device ingest states accessed exclusively by `player_api`.
   - **Exposure**: Docker internal network only (`player-postgres:5432`).

---

## Storage / Persistence

| Volume / Bind Mount | Type | Host Source | Container Target | Owning Service | Content Category |
| ------------------- | ---- | ----------- | ---------------- | -------------- | ---------------- |
| `postgres_data` | Named Volume | `/var/lib/docker/volumes/n8n-zort_postgres_data` | `/var/lib/postgresql/data` | `n8n_zort_postgres` | Relational DB Data (`n8n`, ZORT, Receipt logs) |
| `private_postgres_data` | Named Volume | `/var/lib/docker/volumes/n8n-zort_private_postgres_data` | `/var/lib/postgresql/data` | `private_postgres` | Relational DB Data (`private`) |
| `player_postgres_data` | Named Volume | `/var/lib/docker/volumes/n8n-zort_player_postgres_data` | `/var/lib/postgresql/data` | `player_postgres` | Relational DB Data (`player_queue`) |
| `n8n_data` | Named Volume | `/var/lib/docker/volumes/n8n-zort_n8n_data` | `/home/node/.n8n` | `n8n_zort` | n8n encryption keys, workflow definitions |
| `garmin_tokens` | Named Volume | `/var/lib/docker/volumes/n8n-zort_garmin_tokens` | `/tokens` | `garmin_api` | OAuth authentication tokens for Garmin Connect |
| `/home/kanfullbuster/n8n-zort/data` | Bind Mount | `/home/kanfullbuster/n8n-zort/data` | `/files` | `n8n_zort`, `private_api` | Local file uploads, receipt images, private files |

---

## Administrative Access

1. **SSH Management Access**:
   - **Protocol**: SSH over TCP port `22`
   - **LAN Path**: `kanfullbuster@192.168.1.248`
   - **Tailscale Path**: `kanfullbuster@100.68.88.63`
   - **Authentication**: Ed25519 public key authentication (`~/.ssh/id_ed25519`)
2. **Adminer Web GUI Access**:
   - **Binding**: Host loopback only (`127.0.0.1:8080:8080`)
   - **Tunnel Command**: `ssh -L 8080:127.0.0.1:8080 kanfullbuster@192.168.1.248`
   - **Web Access**: `http://localhost:8080` (Connects internally to `postgres:5432`, `private-postgres:5432`, `player-postgres:5432`)

---

## Security & Trust Boundaries

1. **Edge Boundary**: Cloudflare Tunnel (`cloudflared`) forms the perimeter for incoming webhooks. TLS is terminated at Cloudflare edge; traffic enters `n8n_zort:5678` via outbound QUIC tunnel.
2. **Management Boundary**: SSH on port 22 requires trusted key authentication. Host administrative interfaces (Adminer) are restricted to local loopback `127.0.0.1`.
3. **Database Isolation Boundary**: PostgreSQL databases are isolated from host network interfaces and reachable strictly within the Docker internal bridge network `n8n-zort_default`.
4. **API Authentication Boundary**: Custom APIs (`private_api`, `player_api`, `paddle_ocr`) require Bearer token header authentication (`PRIVATE_API_TOKEN`, `PLAYER_INGEST_TOKEN`, `OCR_API_TOKEN`).

---

## External Integrations

* **Cloudflare Zero Trust**: Tunnel routing for `n8n.kankrittapon.online`
* **ZORT API (v4)**: E-Commerce inventory, order sync, and reporting integration (`open-api.zortout.com`)
* **Garmin Connect API**: Fitness activity extraction and workout data sync
* **Telegram Bot API**: Webhook notification and command interaction interface

---

## Failure Dependencies

```text
n8n_zort_cloudflared Failure ---> Incoming Telegram webhooks & external API webhooks fail to reach n8n.
n8n_zort_postgres Failure ----> n8n engine crashes; receipt/food/workout logging stops.
private_postgres failure -----> private_api endpoints fail (401/500); private file services unavailable.
player_postgres failure ------> player_api queue ingest fails; player tasks halt.
```

---

## Evidence Status

### VERIFIED LIVE
* Host identity `ai-brain`, Ubuntu 24.04.1, Kernel 7.0.0-28
* Verified LAN address `192.168.1.248`, verified host Tailscale IP `100.68.88.63`
* 10 primary AI-Brain containers running, 0 restarts
* PostgreSQL host port 5432 removal (`5432/tcp` internal only)
* Adminer loopback binding (`127.0.0.1:8080->8080/tcp`)
* `n8n_zort` health 200 OK (`http://localhost:5678/healthz`)
* PostgreSQL databases (`n8n_zort_postgres`, `private_postgres`, `player_postgres`) accepting connections

### REPOSITORY / FILE EVIDENCE
* `/home/kanfullbuster/n8n-zort/docker-compose.yml` service definitions, environment variable names, volume mappings
* `docs/reports/AIBRAIN-Audit-LiveBaseline-001.md`, `AIBRAIN-Infra-HardenNetwork-001.md`, `AIBRAIN-Infra-HardenNetwork-002.md`

### HISTORICAL CHECKPOINT
* Baseline Docker Audit (10 August 2026)

### INFERENCE
* n8n internal sub-workflows routing logic based on environment variable names (`PRIVATE_API_URL`, `PADDLE_OCR_URL`)

### NOT VERIFIED
* Outer router NAT port forwarding rules to host WAN IP
* Cloudflare Zero Trust remote dashboard ingress routing configuration for non-n8n endpoints

---

## Known Unknowns

1. Remote Cloudflare Zero Trust dashboard ingress rule mapping outside `n8n.kankrittapon.online` (Managed via Cloudflare dashboard).
2. Host gateway router WAN IP and external port-forwarding rules (Unverified from host local scope).

---

## Architecture Recommendations

### Critical
* NONE

### High
* NONE

### Medium
1. **Container Healthchecks**: Add Docker healthchecks to `private_postgres`, `adminer`, and `n8n_zort_cloudflared` in `docker-compose.yml` (`# PromptID: AIBRAIN-Infra-AddHealthchecks-001`).

### Low
1. **Log Retention**: Implement explicit log rotation for custom API services (`private_api`, `player_api`).

---

*Canonical architecture checkpoint: `AIBRAIN-Architecture-MapCurrentState-001`*
