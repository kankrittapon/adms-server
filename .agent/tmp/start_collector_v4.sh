set -e
cd /home/kanfullbuster/adms-server

echo "=== Pull ==="
git fetch origin
git pull --ff-only origin main 2>&1
echo "post_pull_HEAD=$(git rev-parse HEAD)"
git status --short

echo "=== Restart Collector with new env ==="
docker compose up -d listener 2>&1
echo "START_EXIT=$?"

echo "=== Wait 45s for startup + backfill ==="
sleep 45

echo "=== Container status ==="
docker ps --filter name=adms_zkteco_listener --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker inspect adms_zkteco_listener --format 'restart_count={{.RestartCount}} state={{.State.Status}} health={{.State.Health.Status}}' 2>&1

echo "=== Collector logs (tail 80) ==="
docker logs adms_zkteco_listener --tail 80 2>&1

echo "=== Wait for healthcheck ==="
sleep 35

echo "=== Health status ==="
docker inspect adms_zkteco_listener --format 'restart_count={{.RestartCount}} state={{.State.Status}} health={{.State.Health.Status}}' 2>&1
docker inspect adms_zkteco_listener --format '{{range .State.Health.Log}}exit={{.ExitCode}} out={{.Output}}{{end}}' 2>&1

echo "=== Post-collector DB state ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'devices=' || count(*) FROM devices
UNION ALL SELECT 'device_users=' || count(*) FROM device_users
UNION ALL SELECT 'human_employees=' || count(*) FROM human_employees
UNION ALL SELECT 'human_employee_sources=' || count(*) FROM human_employee_sources
UNION ALL SELECT 'employee_device_mappings=' || count(*) FROM employee_device_mappings
UNION ALL SELECT 'attendance_logs=' || count(*) FROM attendance_logs
UNION ALL SELECT 'employees=' || count(*) FROM employees
UNION ALL SELECT 'sync_events=' || count(*) FROM sync_events;
"

echo "=== Device users ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_user_pk, device_user_id, device_display_name, last_seen_at FROM device_users ORDER BY device_user_id;"

echo "=== Attendance ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT user_id, device_ip, scan_time, punch_type, status, device_id, device_user_pk, employee_id FROM attendance_logs ORDER BY scan_time;"

echo "=== Unmapped ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT count(*) FROM attendance_logs WHERE employee_id IS NULL;"

echo "=== sync_events ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT event_type, message, created_at FROM sync_events ORDER BY created_at;"

echo "=== Unrelated workloads ==="
docker ps --format '{{.Names}} {{.Status}}' | grep -v adms