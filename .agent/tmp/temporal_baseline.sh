echo "=== Docker compose ps ==="
docker compose ps 2>&1

echo "=== All adms containers ==="
docker ps --filter name=adms --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1

echo "=== Restart counts ==="
for c in adms_postgres adms_mqtt adms_zkteco_listener; do
  r=$(docker inspect "$c" --format '{{.RestartCount}}' 2>&1)
  s=$(docker inspect "$c" --format '{{.State.Status}}' 2>&1)
  h=$(docker inspect "$c" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}N/A{{end}}' 2>&1)
  echo "$c restarts=$r state=$s health=$h"
done

echo "=== Collector logs tail 5 ==="
docker logs adms_zkteco_listener --tail 5 2>&1

echo "=== DB row counts ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'human_employees=' || count(*) FROM human_employees
UNION ALL SELECT 'human_employee_sources=' || count(*) FROM human_employee_sources
UNION ALL SELECT 'devices=' || count(*) FROM devices
UNION ALL SELECT 'device_users=' || count(*) FROM device_users
UNION ALL SELECT 'attendance_logs=' || count(*) FROM attendance_logs
UNION ALL SELECT 'employee_device_mappings=' || count(*) FROM employee_device_mappings
UNION ALL SELECT 'employees=' || count(*) FROM employees
UNION ALL SELECT 'sync_events=' || count(*) FROM sync_events;
"

echo "=== Schema 005 constraints ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname IN ('chk_temporal_validity','chk_verified_metadata','chk_verification_method') ORDER BY conname;"

echo "=== Schema 005 partial unique index ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT indexname FROM pg_indexes WHERE tablename='employee_device_mappings' AND indexname='idx_active_verified_device_user';"

echo "=== Dedupe constraint ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='attendance_logs_user_id_device_ip_scan_time_key';"

echo "=== attendance_logs scan_time type ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT column_name || '=' || data_type || ' tz=' || datetime_precision FROM information_schema.columns WHERE table_name='attendance_logs' AND column_name='scan_time';"

echo "=== employee_device_mappings valid_from/valid_to types ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT column_name || '=' || data_type FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name IN ('valid_from','valid_to') ORDER BY column_name;"

echo "=== PostgreSQL timezone ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SHOW timezone; SELECT now();"

echo "=== All indexes on employee_device_mappings ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='employee_device_mappings' ORDER BY indexname;"

echo "=== All indexes on attendance_logs ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='attendance_logs' ORDER BY indexname;"

echo "=== All indexes on device_users ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='device_users' ORDER BY indexname;"

echo "=== Server timezone ==="
date 2>&1
timedatectl 2>&1 | head -5