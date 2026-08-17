# NETWORK HARDENING PLAN

## Prompt

* PromptID: `AIBRAIN-Infra-HardenNetwork-001`
* mode: READ-ONLY / PLAN ONLY
* modifications performed: NO

## Baseline Re-check

* baseline materially unchanged: YES (Verified live on host `ai-brain` `192.168.1.248` / `100.68.88.63`)
* PostgreSQL binding: `0.0.0.0:5432->5432/tcp`, `[::]:5432->5432/tcp` (Container `n8n_zort_postgres`, Status: `Up 38 hours (healthy)`)
* Adminer binding: `0.0.0.0:8080->8080/tcp`, `[::]:8080->8080/tcp` (Container `adminer`, Status: `Up 38 hours`)
* evidence classification: VERIFIED LIVE (SSH inspection of live runtime container states and sockets via `docker ps`, `docker compose config`, `ss -tulpn`)

## PostgreSQL Dependency Analysis

* n8n dependency: Docker-internal (`DB_POSTGRESDB_HOST: postgres` on Docker bridge network `n8n-zort_default:5432`). Does NOT use host port 5432.
* Adminer dependency: Docker-internal (Connects to `postgres:5432`, `private-postgres:5432`, or `player-postgres:5432` via Docker network DNS). Does NOT use host port 5432.
* other AI-Brain dependencies:
  - `private_api`: Uses `private-postgres:5432` (Separate internal container/volume, does NOT use host port 5432).
  - `player_api`: Uses `player-postgres:5432` (Separate internal container/volume, does NOT use host port 5432).
* host-local dependencies: NONE (Verified no crontab, systemd service, or background host script connects to `localhost:5432`).
* known remote dependencies: NONE (ZORT ETL workflows execute inside `n8n_zort`).
* unknown dependencies: NONE identified.

## Adminer Analysis

* operational purpose: Web GUI for database administration and interactive SQL queries.
* service dependencies: None (No background service or API relies on Adminer).
* Cloudflare exposure: NOT VERIFIED (No Adminer ingress rule present in inspected local Compose configuration; managed Cloudflare tunnel routes n8n traffic).
* reverse-proxy exposure: NONE (No local reverse proxy configured for Adminer).
* continuous availability required: NO (Intended solely for periodic human administration).
* unknowns: Cloudflare Zero Trust dashboard remote ingress rules for Adminer classified as `NOT VERIFIED`.

## Exposure Matrix

| Service | Host Bound | LAN Reachable | Tailscale Reachable | Host Firewall (UFW) | Cloudflare | Router/NAT | Internet |
| ------- | ---------- | ------------- | ------------------- | ------------------- | ---------- | ---------- | -------- |
| `n8n_zort_postgres:5432` | VERIFIED (`0.0.0.0:5432`) | VERIFIED | VERIFIED | INACTIVE (`ENABLED=no`, Docker iptables active) | N/A | NOT VERIFIED | NOT VERIFIED |
| `adminer:8080` | VERIFIED (`0.0.0.0:8080`) | VERIFIED | VERIFIED | INACTIVE (`ENABLED=no`, Docker iptables active) | NOT VERIFIED | NOT VERIFIED | NOT VERIFIED |

*Firewall classification notes:*
- UFW status is `ENABLED=no` (Inactive). Host OS firewall does not restrict ingress.
- Docker manages iptables/nftables forwarding rules directly when container ports are published.
- Direct port reachability is VERIFIED on LAN (`192.168.1.248`) and Tailscale (`100.68.88.63`).
- Upstream gateway router NAT/port-forwarding rules and public Internet reachability are classified as `NOT VERIFIED`.

## Architecture Options

| Option | Security | Compatibility Risk | Operational Complexity | Recommendation |
| ------ | -------- | ------------------ | ---------------------- | -------------- |
| **Option A — Docker Internal Only** | High (Complete isolation from host network) | None for PostgreSQL (n8n & Adminer use internal DNS) | Low | **RECOMMENDED for PostgreSQL (`5432`)** |
| **Option B — Loopback Binding (`127.0.0.1`)** | High (Restricted to host localhost) | None (Reachable via SSH tunnel) | Low | **RECOMMENDED for Adminer (`8080`)** |
| **Option C — Tailscale-Specific Binding** | Medium-High | Medium (Risk if Tailscale IP changes) | Medium | Not Recommended |
| **Option D — Current Binding + UFW Firewall** | Medium | Low | High (Docker iptables bypass complexity) | Not Recommended |

## Recommended Target

1. **`n8n_zort_postgres`**:
   - **Target**: Docker Internal Only (Remove host port publishing `- "5432:5432"`).
   - **Expected Connectivity**: `n8n_zort` and `adminer` connect seamlessly via Docker bridge network DNS `postgres:5432`.
   - **Impact**: Port 5432 is closed on host interfaces. Zero impact on n8n workflows or Adminer database operations.

2. **`adminer`**:
   - **Target**: Loopback Binding (`"127.0.0.1:8080:8080"`).
   - **Expected Connectivity**: Accessible on host `127.0.0.1:8080`.
   - **Administrator Access**: Secure SSH Tunnel (`ssh -L 8080:127.0.0.1:8080 kanfullbuster@192.168.1.248` or via Tailscale SSH).
   - **Impact**: Prevents unauthenticated LAN/WAN access to database GUI while preserving full administrator access.

## Proposed Change Set

PLAN ONLY. DO NOT EXECUTE.

### [MODIFY] [docker-compose.yml](file:///home/kanfullbuster/n8n-zort/docker-compose.yml)

* **Target File**: `/home/kanfullbuster/n8n-zort/docker-compose.yml`
* **Exact Logical Change**:
  - Under `postgres:` service, REMOVE host port publishing:
    ```yaml
    ports:
      - "5432:5432"
    ```
  - Under `adminer:` service, CHANGE host port publishing:
    ```yaml
    # FROM:
    ports:
      - "8080:8080"
    # TO:
    ports:
      - "127.0.0.1:8080:8080"
    ```
* **Reason**: Eliminate unauthenticated public port bindings (`0.0.0.0`) for PostgreSQL database port 5432 and Adminer web interface port 8080.
* **Expected Impact**:
  - PostgreSQL port 5432 will no longer accept connections on external host IP.
  - Adminer web UI will respond only to local loopback `127.0.0.1:8080`.
  - All internal n8n workflows and container APIs are expected to operate without interruption; mandatory post-change runtime verification will be performed to confirm.
* **Verification Method**:
  - Execute `docker compose up -d`
  - Run `ss -tulpn | grep -E '5432|8080'` to confirm 5432 is not listening on host and 8080 is bound to `127.0.0.1:8080`.
  - Verify `n8n_zort` health endpoint (`curl http://localhost:5678/healthz`).
  - Verify Adminer via SSH tunnel (`curl http://127.0.0.1:8080`).
* **Rollback Method**:
  - Restore original `docker-compose.yml` from the uniquely named pre-change backup file `docker-compose.yml.bak_YYYYMMDD_HHMMSS` and execute `docker compose up -d`.

## Pre-Write Verification

Immediately before executing any future WRITE prompt:
1. Re-check live status of `n8n_zort`, `n8n_zort_postgres`, and `adminer` (`docker ps`).
2. Create a uniquely named timestamped backup file: `cp /home/kanfullbuster/n8n-zort/docker-compose.yml /home/kanfullbuster/n8n-zort/docker-compose.yml.bak_$(date +%Y%m%d_%H%M%S)`.
3. Confirm `docker compose config` syntax validity before applying changes.

## Proposed WRITE PromptID

Proposing future WRITE task:

`# PromptID: AIBRAIN-Infra-HardenNetwork-002`

*(Requires explicit user authorization before execution)*

## FINAL

* dependency analysis complete: YES
* actual Internet exposure verified: NOT VERIFIED (LAN/Tailscale exposure verified; Internet WAN exposure unverified)
* recommended architecture available: YES
* unresolved blockers: NONE
* safe to prepare WRITE prompt: YES
* WRITE authorized: NO
* modifications performed: NO

STOP.
