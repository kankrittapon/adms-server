echo "=== Stored scan_time values ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT scan_time, pg_typeof(scan_time) FROM attendance_logs ORDER BY scan_time LIMIT 5;"

echo "=== Check if timestamps are UTC or local ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT scan_time, scan_time AT TIME ZONE 'Asia/Bangkok' AS bangkok_local FROM attendance_logs ORDER BY scan_time LIMIT 5;"

echo "=== PostgreSQL timezone setting ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SHOW timezone;"

echo "=== Check device_users device_uid ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_user_pk, device_user_id, device_uid, device_display_name FROM device_users ORDER BY device_user_pk;"

echo "=== employee_device_mappings full schema ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name='employee_device_mappings' ORDER BY ordinal_position;"

echo "=== attendance_logs full schema ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name='attendance_logs' ORDER BY ordinal_position;"