# HEALTHCHECK IMPROVEMENT PLAN

## Prompt

* PromptID: `AIBRAIN-Infra-AddHealthchecks-001`
* mode: READ-ONLY / PLAN ONLY
* modifications performed: NO

## Baseline

* live state materially unchanged: YES (Verified on host `ai-brain` `192.168.1.248` / `100.68.88.63`)
* target services: `private_postgres`, `adminer`, `n8n_zort_cloudflared`
* current healthcheck state: Missing explicit Docker healthchecks in `docker-compose.yml`
* evidence: VERIFIED LIVE (Container inspection and command availability checks via SSH)

## Existing Patterns

* PostgreSQL pattern: `pg_isready` (Used by `n8n_zort_postgres` and `player_postgres`)
* HTTP/API pattern: `wget` / `fetch` / `urllib` (Used by `n8n_zort`, `garmin_api`, `private_api`, `player_api`, `paddle_ocr`)
* other relevant patterns: N/A

## private_postgres

* proposed: Add explicit Docker healthcheck in `docker-compose.yml`
* probe: `test: ["CMD-SHELL", "pg_isready -U ${PRIVATE_POSTGRES_USER:-private_app} -d ${PRIVATE_POSTGRES_DB:-private}"]`
* command availability: VERIFIED (`/usr/local/bin/pg_isready` present in `postgres:16-alpine`)
* what it proves: Proves PostgreSQL engine is running, listening on socket/port 5432, and ready to accept connections for database `private`.
* limitations: Does not execute SQL queries or verify table integrity (by design to prevent unauthenticated query side effects).
* timing: `interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 10s`
* recommendation: RECOMMENDED

## adminer

* proposed: Add explicit Docker healthcheck in `docker-compose.yml`
* probe: `test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1"]`
* command availability: VERIFIED (`/usr/bin/wget` present inside `adminer` container; tested spider HTTP check returned 200 OK)
* what it proves: Proves Adminer PHP web server process is running, bound to port 8080, and serving the management interface.
* limitations: Does not test database login or query execution.
* timing: `interval: 30s`, `timeout: 5s`, `retries: 3`, `start_period: 10s`
* recommendation: RECOMMENDED

## cloudflared

* proposed: NO HEALTHCHECK CHANGE
* probe: N/A
* diagnostic capability: Container lacks `/bin/sh` shell; `cloudflared --version` process probe proves binary existence only, not QUIC tunnel edge connectivity. Local metrics endpoint `--metrics` is unconfigured.
* what it proves: N/A (A process-only probe would introduce false-positive risk where process is alive but tunnel is disconnected).
* limitations: Cannot verify edge connection without modifying container entrypoint command or Cloudflare configuration.
* timing: N/A
* recommendation: NO HEALTHCHECK CHANGE (Avoid weak process-only probes).

## Risk / Value Matrix

| Service | Probe | Value | False Positive Risk | Compatibility Risk | Recommendation |
| ------- | ----- | ----- | ------------------- | ------------------ | -------------- |
| `private_postgres` | `pg_isready -U ${PRIVATE_POSTGRES_USER:-private_app} -d ${PRIVATE_POSTGRES_DB:-private}` | High | Low | Low | **RECOMMENDED** |
| `adminer` | `wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1` | Medium | Low | Low | **RECOMMENDED** |
| `n8n_zort_cloudflared` | N/A (Tunnel metrics unconfigured) | Low | High | Low | **NO HEALTHCHECK CHANGE** |

## Proposed Change Set

PLAN ONLY. DO NOT EXECUTE.

### [MODIFY] [docker-compose.yml](file:///home/kanfullbuster/n8n-zort/docker-compose.yml)

```yaml
  private-postgres:
    image: postgres:16-alpine
    container_name: private_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${PRIVATE_POSTGRES_DB:-private}
      POSTGRES_USER: ${PRIVATE_POSTGRES_USER:-private_app}
      POSTGRES_PASSWORD: ${PRIVATE_POSTGRES_PASSWORD}
      TZ: ${TZ:-Asia/Bangkok}
    volumes:
      - private_postgres_data:/var/lib/postgresql/data
+   healthcheck:
+     test: ["CMD-SHELL", "pg_isready -U ${PRIVATE_POSTGRES_USER:-private_app} -d ${PRIVATE_POSTGRES_DB:-private}"]
+     interval: 10s
+     timeout: 5s
+     retries: 5
+     start_period: 10s

  adminer:
    image: adminer
    container_name: adminer
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      - postgres
+   healthcheck:
+     test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1"]
+     interval: 30s
+     timeout: 5s
+     retries: 3
+     start_period: 10s
```

## Dependency Effects

* `depends_on` changes required: None mandatory. `private_api` dependency on `private-postgres` may remain `service_started` or optionally update to `service_healthy`.
* startup semantics changes required: None (Services start independently as before).
* monitoring implications: Docker daemon and container status tools (`docker ps`, `docker inspect`) will accurately report `healthy` / `unhealthy` state for `private_postgres` and `adminer`.

## Pre-Write Verification

* required checks:
  1. Re-verify live container status and SHA256 hash of `/home/kanfullbuster/n8n-zort/docker-compose.yml`.
  2. Create a unique timestamped backup: `cp docker-compose.yml docker-compose.yml.bak_YYYYMMDD_HHMMSS`.
  3. Re-verify `pg_isready` and `wget` execution inside target containers before applying Compose changes.
  4. Run `docker compose config` to validate YAML syntax.

## Documentation

* report persisted: YES (`docs/reports/AIBRAIN-Infra-AddHealthchecks-001.md`)
* reports README updated: YES (`docs/reports/README.md`)
* commit: NO (Not authorized)
* push: NO (Not authorized)

## Proposed WRITE PromptID

* PromptID: `AIBRAIN-Infra-AddHealthchecks-002`
* ready: YES
* blockers: NONE

## FINAL

* healthcheck analysis complete: YES
* private_postgres recommendation available: YES
* adminer recommendation available: YES
* cloudflared recommendation available: YES
* safe to prepare WRITE task: YES
* infrastructure WRITE authorized: NO
* infrastructure modifications performed: NO
* blockers: NONE

STOP.
