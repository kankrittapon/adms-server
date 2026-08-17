echo "=== Database identity ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT current_database();"
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT version();"

echo "=== Row counts ==="
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

echo "=== Human Master integrity ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'unique_uuids=' || count(DISTINCT employee_id) || ' total=' || count(*) FROM human_employees;
"
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'orphan_sources=' || count(*) FROM human_employee_sources s LEFT JOIN human_employees e ON s.employee_id = e.employee_id WHERE e.employee_id IS NULL;
"
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT source_record_key, count(*) FROM human_employee_sources GROUP BY source_record_key HAVING count(*) > 1;
"

echo "=== Device identity ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_id, serial_number, device_name, device_ip, platform, firmware_version, active, last_seen_at FROM devices;"

echo "=== Device users ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_user_pk, device_user_id, device_display_name, last_seen_at FROM device_users ORDER BY device_user_id;"

echo "=== Attendance ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT user_id, device_ip, scan_time, punch_type, status, device_id, device_user_pk, employee_id FROM attendance_logs ORDER BY scan_time;"

echo "=== Unmapped ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT count(*) FROM attendance_logs WHERE employee_id IS NULL;"

echo "=== Legacy stubs ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT count(*) FROM employees;"

echo "=== Schema 005: device_users columns ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT column_name || '=' || data_type || ' nullable=' || is_nullable FROM information_schema.columns WHERE table_name='device_users' AND column_name IN ('roster_last_seen_at','inactive_at') ORDER BY column_name;
"

echo "=== Schema 005: employee_device_mappings columns ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT column_name || '=' || data_type || ' nullable=' || is_nullable FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name IN ('verified_by','verification_method','verification_note','valid_from','valid_to') ORDER BY column_name;
"

echo "=== Schema 005: constraints ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname IN ('chk_temporal_validity','chk_verified_metadata','chk_verification_method') ORDER BY conname;"

echo "=== Schema 005: active VERIFIED partial unique index ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='employee_device_mappings' AND indexname LIKE '%active%' OR indexname LIKE '%verified%' ORDER BY indexname;"

echo "=== Legacy FK check (must be ABSENT) ==="
docker exec adms_postgres psql -U adms -d adms -t -c "SELECT conname FROM pg_constraint WHERE conname='attendance_logs_user_id_fkey';"

echo "=== sync_events ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT event_type, message, created_at FROM sync_events ORDER BY created_at;"