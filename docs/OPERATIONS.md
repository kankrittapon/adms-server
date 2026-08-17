# ADMS Operations & Maintenance Manual

## 1. Routine Monitoring & Health Checks

### 1.1 Web Console Dashboard
Access the production dashboard at `http://192.168.1.248:8082` to inspect:
- Collector connection state (Target: `LIVE` / Device: `Connected`).
- API and PostgreSQL database health (Target: `HEALTHY`).
- Mosquitto MQTT message broker status (Target: `HEALTHY`).
- Live KPI counts for Personnel, Devices, Attendance Today, and Active Mappings.

### 1.2 CLI Health Inspection
Run non-invasive health evaluation on `ai-brain`:

```bash
docker exec adms_zkteco_listener python -m app.healthcheck
```
- **Exit Code 0**: System is healthy and operational.
- **Exit Code 1**: Stale heartbeat, disconnected socket, or backoff condition.

---

## 2. Backup & Disaster Recovery Procedures

### 2.1 Generating a Fresh Custom Dump
PostgreSQL backups MUST use custom format (`-Fc`):

```bash
docker exec adms_postgres pg_dump -U adms -d adms -Fc -f /tmp/adms_backup_$(date +%Y%m%d_%H%M%S).dump
```

### 2.2 Verifying Backup Readability
Verify archive integrity and Table of Contents (TOC) readability using `pg_restore -l`:

```bash
docker exec adms_postgres sh -c 'ls -lh /tmp/adms_backup_*.dump'
docker exec adms_postgres pg_restore -l /tmp/adms_backup_<TIMESTAMP>.dump | head -20
```

### 2.3 Restoring from Backup
> [!CAUTION]
> Restoring a database drops and recreates schema tables. Ensure you have an offline copy of your verified dump before proceeding.

```bash
docker compose stop api listener web
docker exec -i adms_postgres pg_restore -U adms -d adms --clean --if-exists /tmp/adms_backup_<TIMESTAMP>.dump
docker compose start api listener web
```

---

## 3. Operator Security & Password Management

### 3.1 Initial Administrator Bootstrap
If creating the first administrator on a fresh database:

```bash
docker exec -it adms_api python -m app.api.bootstrap_admin
```

### 3.2 Password Updates
Operators can update their password directly in the Web Console under **System → Operator Account Security** or via `POST /api/v1/auth/change-password`. Updating a password revokes all other active sessions for that account.

### 3.3 Adding Operators
Administrators can provision new accounts under **System → Operator Accounts Management** or via `POST /api/v1/operators`. Supported roles are `VIEWER`, `ENROLLMENT_OPERATOR`, `OPERATOR`, and `ADMIN`.

---

## 4. Troubleshooting Guide

| Symptom | Probable Cause | Corrective Action |
| ------- | -------------- | ----------------- |
| `Collector state: DISCONNECTED` | Terminal `192.168.1.201` unreachable or powered off. | Verify network cable, ping `192.168.1.201`, check Comm Key (default `600`). |
| `403 WRITE_DISABLED` | Server write gate is locked. | Set `API_WRITE_ENABLED=true` in `.env` and restart `api` service for enrollment sessions. |
| `401 UNAUTHORIZED` | Session token expired (12h TTL) or password changed. | Log in again at `/login`. |
| `429 RATE_LIMITED` | Too many failed login attempts (>5/min). | Wait 60 seconds before retrying login. |
| Realtime scan banner not appearing | Web browser SSE disconnected or MQTT broker issue. | Check network connectivity to port 8081; verify `adms_mqtt` container is running. |
