# ADMS Deployment & Infrastructure Guide

## 1. Production Target Environment

- **Host**: `ai-brain` (`192.168.1.248`, Ubuntu 24.04 LTS x86_64)
- **Terminal Hardware**: SONIC / ZKTeco ZEM560_TFT (`192.168.1.201:4370`)
- **Docker Compose Topology**: 5 orchestrated services (`adms-server` compose project)

```
                          ┌────────────────────────┐
                          │   Host: 192.168.1.248  │
                          └───────────┬────────────┘
                                      │
     ┌──────────────────┬─────────────┼─────────────┬──────────────────┐
     │                  │             │             │                  │
┌────┴────────┐   ┌─────┴───────┐ ┌───┴─────────┐ ┌─┴────────────┐ ┌───┴──────────────┐
│  adms_web   │   │  adms_api   │ │adms_postgres│ │  adms_mqtt   │ │adms_zkteco_list. │
│(nginx:1.27) │   │ (FastAPI)   │ │(Postgres 16)│ │ (Mosquitto 2)│ │ (Python PyZK)    │
│  Port 8082  │   │  Port 8081  │ │(Internal)   │ │(127.0.0.1:   │ │(Internal to ZK)  │
│  (LAN bind) │   │  (LAN bind) │ │  5432/tcp   │ │   1883/tcp)  │ │                  │
└─────────────┘   └─────────────┘ └─────────────┘ └──────────────┘ └──────────────────┘
```

---

## 2. Service Matrix & Endpoints

| Service Name | Container Name | Base Image / Runtime | Published Ports / Bind | Purpose |
| ------------ | -------------- | -------------------- | ---------------------- | ------- |
| `web` | `adms_web` | `nginx:1.27-alpine` | `192.168.1.248:8082:80` | Production React SPA web console serving. |
| `api` | `adms_api` | `python:3.12-slim` | `192.168.1.248:8081:8081` | REST API, SSE streaming, authentication, and dispatch. |
| `adms-postgres` | `adms_postgres` | `postgres:16-alpine` | Internal `5432` only | Authoritative persistent database storage. |
| `mqtt` | `adms_mqtt` | `eclipse-mosquitto:2`| `127.0.0.1:1883:1883` | Internal realtime event broker & Device Command Bus. |
| `listener` | `adms_zkteco_listener` | `python:3.12-slim` | Host Network (ZK access) | Background ZKTeco polling, ingestion, and hardware dispatch. |

---

## 3. Configuration & Environment Variables

All services consume environment variables from `.env` in the repository root:

```bash
# Database Connection
POSTGRES_DB=adms
POSTGRES_USER=adms
POSTGRES_PASSWORD=<SECURE_DB_PASSWORD>
POSTGRES_HOST=adms_postgres
POSTGRES_PORT=5432

# ZKTeco Terminal Configuration
ZKTECO_DEVICE_IP=192.168.1.201
ZKTECO_DEVICE_PORT=4370
ZKTECO_COMM_KEY=600
ZKTECO_TIMEOUT_SECONDS=10
ZKTECO_POLL_INTERVAL_SECONDS=5

# MQTT Configuration
MQTT_BROKER_HOST=adms_mqtt
MQTT_BROKER_PORT=1883

# Production Write Gate (DEFAULT: false)
API_WRITE_ENABLED=false

# Security & Tokens
API_TOKEN_SECRET=<SECRET_TOKEN_SALT>
API_TOKEN_TTL_HOURS=12
API_RATE_LIMIT_ENABLED=true
API_LOGIN_RATE_PER_MIN=5
API_GLOBAL_RATE_PER_MIN=600

# CORS & Public URL
CORS_ALLOW_ORIGINS=http://192.168.1.248:8082,http://localhost:5173
```

---

## 4. Deployment & Lifecycle Procedures

### 4.1 Rebuilding & Synchronizing Code
When code changes are pushed to `origin/main`, pull and rebuild only affected services on `ai-brain`:

```bash
cd /home/kanfullbuster/adms-server
git pull origin main

# Rebuild API and Web containers:
docker compose build api web
docker compose up -d api web

# Verify container health:
docker compose ps
```

### 4.2 Database Migrations
Always verify pre-flight backups before applying SQL migrations to `adms_postgres`:

```bash
# Backup first:
docker exec adms_postgres pg_dump -U adms -d adms -Fc -f /tmp/pre_migration_backup.dump
docker exec adms_postgres pg_restore -l /tmp/pre_migration_backup.dump >/dev/null && echo BACKUP_OK

# Apply migration:
docker exec -i adms_postgres psql -U adms -d adms < sql/010_enrollment_operator_role.sql
docker exec -i adms_postgres psql -U adms -d adms < sql/011_human_english_name.sql
```

### 4.3 Collector Health Bridge
The polling Collector writes health telemetry atomically to `/tmp/collector_health.json`. This directory is mounted into `adms_api` via a shared volume (`collector_health_vol`), enabling `/api/v1/health` to report real-time ZKTeco socket status without extra network polling.
