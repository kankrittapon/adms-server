echo "=== DB INFO ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT current_database(), current_user();" 2>&1
docker exec adms_postgres psql -U adms -d adms -c "SELECT version();" 2>&1
echo "=== SCHEMAS ==="
docker exec adms_postgres psql -U adms -d adms -c "\dn" 2>&1
echo "=== TABLES ==="
docker exec adms_postgres psql -U adms -d adms -c "\dt" 2>&1
echo "=== ALL NON-SYSTEM TABLES ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename;" 2>&1
echo "=== ROW COUNTS ==="
for t in employees attendance_logs sync_events devices device_users human_employees human_employee_sources employee_device_mappings; do
  cnt=$(docker exec adms_postgres psql -U adms -d adms -tAc "SELECT count(*) FROM $t;" 2>&1)
  echo "$t: $cnt"
done
echo "=== COLUMNS: employees ==="
docker exec adms_postgres psql -U adms -d adms -c "\d employees" 2>&1
echo "=== COLUMNS: attendance_logs ==="
docker exec adms_postgres psql -U adms -d adms -c "\d attendance_logs" 2>&1
echo "=== COLUMNS: devices ==="
docker exec adms_postgres psql -U adms -d adms -c "\d devices" 2>&1
echo "=== FK CHECK: attendance_logs_user_id_fkey ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname = 'attendance_logs_user_id_fkey';" 2>&1