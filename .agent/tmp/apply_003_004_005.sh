cd /home/kanfullbuster/adms-server

echo "=== Apply Migration 003 ==="
docker cp sql/003_legacy_identity_constraint.sql adms_postgres:/tmp/003.sql 2>&1
docker exec adms_postgres psql -U adms -d adms -v ON_ERROR_STOP=1 -f /tmp/003.sql 2>&1
echo "MIGRATION_003_EXIT=$?"
docker exec adms_postgres rm -f /tmp/003.sql 2>&1

echo "=== Verify: attendance_logs_user_id_fkey should be ABSENT ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname = 'attendance_logs_user_id_fkey';" 2>&1

echo "=== Apply Migration 004 ==="
docker cp sql/004_human_master_schema.sql adms_postgres:/tmp/004.sql 2>&1
docker exec adms_postgres psql -U adms -d adms -v ON_ERROR_STOP=1 -f /tmp/004.sql 2>&1
echo "MIGRATION_004_EXIT=$?"
docker exec adms_postgres rm -f /tmp/004.sql 2>&1

echo "=== Verify: human_employees new columns ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='human_employees' AND column_name IN ('branch','category') ORDER BY column_name;" 2>&1
echo "=== Verify: human_employee_sources table ==="
docker exec adms_postgres psql -U adms -d adms -c "\d human_employee_sources" 2>&1

echo "=== Apply Migration 005 ==="
docker cp sql/005_human_device_mapping_schema.sql adms_postgres:/tmp/005.sql 2>&1
docker exec adms_postgres psql -U adms -d adms -v ON_ERROR_STOP=1 -f /tmp/005.sql 2>&1
echo "MIGRATION_005_EXIT=$?"
docker exec adms_postgres rm -f /tmp/005.sql 2>&1

echo "=== Verify: device_users lifecycle fields ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='device_users' AND column_name IN ('roster_last_seen_at','inactive_at') ORDER BY column_name;" 2>&1
echo "=== Verify: employee_device_mappings temporal fields ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name IN ('verified_by','verification_method','verification_note','valid_from','valid_to') ORDER BY column_name;" 2>&1
echo "=== Verify: verification_note nullable ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT is_nullable FROM information_schema.columns WHERE table_name='employee_device_mappings' AND column_name='verification_note';" 2>&1
echo "=== Verify: active VERIFIED unique index ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT indexname FROM pg_indexes WHERE indexname='idx_active_verified_device_user';" 2>&1
echo "=== Verify: VERIFIED metadata constraint ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname='chk_verified_metadata';" 2>&1
echo "=== Verify: temporal validity constraint ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname='chk_temporal_validity';" 2>&1
echo "=== Verify: verification_method constraint ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname='chk_verification_method';" 2>&1
echo "=== Verify: mapping_status check (CANDIDATE, REVOKED) ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='employee_device_mappings_mapping_status_check';" 2>&1
echo "=== Verify: legacy FK absent ==="
docker exec adms_postgres psql -U adms -d adms -c "SELECT conname FROM pg_constraint WHERE conname = 'attendance_logs_user_id_fkey';" 2>&1
echo "=== Final table list ==="
docker exec adms_postgres psql -U adms -d adms -c "\dt" 2>&1
echo "=== Final row counts ==="
for t in employees attendance_logs sync_events devices device_users human_employees human_employee_sources employee_device_mappings; do
  cnt=$(docker exec adms_postgres psql -U adms -d adms -tAc "SELECT count(*) FROM $t;" 2>&1)
  echo "$t: $cnt"
done