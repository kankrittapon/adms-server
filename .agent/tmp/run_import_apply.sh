cd /home/kanfullbuster/adms-server

echo "=== Run import --apply ==="
PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)

docker run --rm \
  --network adms-server_default \
  -v /home/kanfullbuster/adms-server:/app \
  -e DB_HOST=adms_postgres \
  -e DB_PORT=5432 \
  -e DB_NAME=adms \
  -e DB_USER=adms \
  -e DB_PASSWORD="$PGPASS" \
  -w /app \
  adms-import-temp \
  python -m app.import_excel_human_master --apply 2>&1
echo "APPLY_EXIT=$?"

echo "=== Verify counts ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(*) AS human_employees FROM human_employees;" 2>&1
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(*) AS human_employee_sources FROM human_employee_sources;" 2>&1
echo "=== UUID uniqueness ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(DISTINCT employee_id) AS unique_uuids, count(*) AS total FROM human_employees;" 2>&1
echo "=== Orphan provenance ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(*) AS orphan_sources FROM human_employee_sources s LEFT JOIN human_employees e ON s.employee_id = e.employee_id WHERE e.employee_id IS NULL;" 2>&1
echo "=== Duplicate source keys ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT source_record_key, count(*) FROM human_employee_sources GROUP BY source_record_key HAVING count(*) > 1;" 2>&1
echo "=== Category breakdown ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT category, count(*) FROM human_employees GROUP BY category ORDER BY category;" 2>&1
echo "=== employee_device_mappings (must be 0) ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(*) AS employee_device_mappings FROM employee_device_mappings;" 2>&1

echo "=== Run second dry-run (idempotency check) ==="
docker run --rm \
  --network adms-server_default \
  -v /home/kanfullbuster/adms-server:/app \
  -e DB_HOST=adms_postgres \
  -e DB_PORT=5432 \
  -e DB_NAME=adms \
  -e DB_USER=adms \
  -e DB_PASSWORD="$PGPASS" \
  -w /app \
  adms-import-temp \
  python -m app.import_excel_human_master --dry-run 2>&1
echo "IDEMPOTENCY_EXIT=$?"