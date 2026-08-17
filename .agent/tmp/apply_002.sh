cd /home/kanfullbuster/adms-server

echo "=== STEP 0: Drop 001 devices table (0 rows, no FKs, safe) ==="
docker exec adms_postgres psql -U adms -d adms -c "DROP TABLE IF EXISTS devices CASCADE;" 2>&1

echo "=== STEP 1: Apply Migration 002 ==="
docker exec adms_postgres psql -U adms -d adms -v ON_ERROR_STOP=1 -f /dev/stdin < sql/002_identity_foundation.sql 2>&1
echo "MIGRATION_002_EXIT=$?"

echo "=== Verify after 002 ==="
docker exec adms_postgres psql -U adms -d adms -c "\dt" 2>&1
docker exec adms_postgres psql -U adms -d adms -c "SELECT count(*) AS devices FROM devices;" 2>&1
docker exec adms_postgres psql -U adms -d adms -c "SELECT device_id, serial_number, device_name, device_ip FROM devices;" 2>&1