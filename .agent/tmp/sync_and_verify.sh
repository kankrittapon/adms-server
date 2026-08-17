set -e
cd /home/kanfullbuster/adms-server

echo "=== Hostname ==="
hostname

echo "=== Pre-pull git state ==="
git status --short
git branch --show-current
echo "pre_pull_HEAD=$(git rev-parse HEAD)"

echo "=== Pull ==="
git fetch origin
git pull --ff-only origin main 2>&1

echo "=== Post-pull git state ==="
echo "post_pull_HEAD=$(git rev-parse HEAD)"
echo "origin_main=$(git rev-parse origin/main)"
git status --short

echo "=== Verify Dockerfile synced ==="
cat docker/Dockerfile
echo "---requirements---"
cat app/requirements.txt

echo "=== Port/workload safety ==="
docker compose ls 2>&1
docker ps --format '{{.Names}} {{.Status}}' | grep -v adms
ss -lntup 2>&1 | grep -E '1883|5432' || echo "no 1883/5432 host collision"

echo "=== Pre-collector DB state ==="
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

echo "=== Schema 005 verification ==="
docker exec adms_postgres psql -U adms -d adms -t -c "
SELECT 'device_users.roster_last_seen_at=' || count(*) FROM information_schema.columns WHERE table_name='device_users' AND column_name='roster_last_seen_at'
UNION ALL SELECT 'device_users.inactive_at=' || count(*) FROM information_schema.columns WHERE table_name='device_users' AND column_name='inactive_at'
UNION ALL SELECT 'edm.verified_by=' || count(*) FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name='verified_by'
UNION ALL SELECT 'edm.verification_method=' || count(*) FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name='verification_method'
UNION ALL SELECT 'edm.valid_from=' || count(*) FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name='valid_from'
UNION ALL SELECT 'edm.valid_to=' || count(*) FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name='valid_to';
"
echo "=== Constraints ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname IN ('chk_temporal_validity','chk_verified_metadata','chk_verification_method') ORDER BY conname;"

echo "=== MQTT state ==="
docker ps --filter name=adms_mqtt --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker inspect adms_mqtt --format '{{.RestartCount}} restarts' 2>&1