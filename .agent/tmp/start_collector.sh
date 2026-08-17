cd /home/kanfullbuster/adms-server

echo "=== Pre-start DB state ==="
PGPASS=$(grep POSTGRES_PASSWORD .env | cut -d= -f2)
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'devices=' || count(*) FROM devices
UNION ALL SELECT 'device_users=' || count(*) FROM device_users
UNION ALL SELECT 'human_employees=' || count(*) FROM human_employees
UNION ALL SELECT 'employee_device_mappings=' || count(*) FROM employee_device_mappings
UNION ALL SELECT 'attendance_logs=' || count(*) FROM attendance_logs
UNION ALL SELECT 'sync_events=' || count(*) FROM sync_events;
"

echo "=== Start Collector ==="
docker compose up -d listener 2>&1
echo "LISTENER_START_EXIT=$?"

echo "=== Wait for backfill ==="
sleep 20

echo "=== Container status ==="
docker ps --filter name=adms_zkteco_listener --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker compose ps listener 2>&1

echo "=== Collector logs (tail 60) ==="
docker logs adms_zkteco_listener --tail 60 2>&1

echo "=== Post-backfill DB state ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'devices=' || count(*) FROM devices
UNION ALL SELECT 'device_users=' || count(*) FROM device_users
UNION ALL SELECT 'human_employees=' || count(*) FROM human_employees
UNION ALL SELECT 'employee_device_mappings=' || count(*) FROM employee_device_mappings
UNION ALL SELECT 'attendance_logs=' || count(*) FROM attendance_logs
UNION ALL SELECT 'sync_events=' || count(*) FROM sync_events;
"

echo "=== Device users detail ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_user_pk, device_user_id, device_display_name, last_seen_at FROM device_users ORDER BY device_user_id;"

echo "=== Attendance sample (first 10) ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT user_id, device_ip, scan_time, punch_type, status, device_id, device_user_pk, employee_id FROM attendance_logs ORDER BY scan_time LIMIT 10;"

echo "=== Unmapped attendance (employee_id IS NULL) ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT count(*) FROM attendance_logs WHERE employee_id IS NULL;"

echo "=== sync_events ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT event_type, message, created_at FROM sync_events ORDER BY created_at DESC LIMIT 5;"

echo "=== Unrelated containers unchanged ==="
docker ps --format '{{.Names}} {{.Status}}' | grep -v adms