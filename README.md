# ADMS Server

Standalone Docker service for collecting attendance events from a ZKTeco ZEM560 device.

The device firmware does not provide ADMS HTTP push, so the listener connects to the device using ZK Socket Protocol on TCP port 4370. New events are stored in PostgreSQL and published to MQTT topic `attendance/events`.

## Run

1. Copy `.env.example` to `.env` and set the real PostgreSQL password and device IP.
2. Confirm the server can reach the device on TCP `4370`.
3. Start the stack:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f listener
```

The MQTT broker is bound to localhost only. n8n can consume the database directly or subscribe through a separate integration service.

## Data

Employee master data belongs in `employees`. Attendance events belong in `attendance_logs`. The `UNIQUE` constraint prevents the listener from inserting the same user/device/timestamp twice.
