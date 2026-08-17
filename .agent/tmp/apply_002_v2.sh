cd /home/kanfullbuster/adms-server
echo "=== Check if devices table exists ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" 2>&1
echo "=== Apply 002 via docker cp ==="
docker cp sql/002_identity_foundation.sql adms_postgres:/tmp/002.sql 2>&1
docker exec adms_postgres psql -U adms -d adms -v ON_ERROR_STOP=1 -f /tmp/002.sql 2>&1
echo "MIGRATION_002_EXIT=$?"
docker exec adms_postgres rm -f /tmp/002.sql 2>&1
echo "=== Verify after 002 ==="
docker exec adms_postgres psql -U adms -d adms -c "\dt" 2>&1
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(*) AS devices FROM devices;" 2>&1
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_id, serial_number, device_name, device_ip, platform FROM devices;" 2>&1
echo "=== device_users table ==="
docker exec adms_postgres psql -U adms -d adms -c "\d device_users" 2>&1
echo "=== human_employees table ==="
docker exec adms_postgres psql -U adms -d adms -c "\d human_employees" 2>&1
echo "=== employee_device_mappings table ==="
docker exec adms_postgres psql -U adms -d adms -c "\d employee_device_mappings" 2>&1
echo "=== attendance_logs columns ==="
docker exec adms_postgres psql -U adms -d adms -c "\d attendance_logs" 2>&1