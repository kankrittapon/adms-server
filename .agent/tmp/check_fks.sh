echo "=== FKs referencing devices table ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname, conrelid::regclass AS table_from, confrelid::regclass AS table_to FROM pg_constraint WHERE confrelid = 'devices'::regclass;" 2>&1
echo "=== FKs from attendance_logs ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname, conrelid::regclass AS table_from, confrelid::regclass AS table_to FROM pg_constraint WHERE conrelid = 'attendance_logs'::regclass AND contype = 'f';" 2>&1
echo "=== All FKs ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname, conrelid::regclass AS table_from, confrelid::regclass AS table_to FROM pg_constraint WHERE contype = 'f' ORDER BY conrelid::regclass::text;" 2>&1