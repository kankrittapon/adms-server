cd /home/kanfullbuster/adms-server

TS=$(date +%Y%m%d_%H%M%S)
BACKUP="backups/adms_reconstructed_authoritative_${TS}.dump"

echo "=== Create authoritative backup ==="
docker exec adms_postgres pg_dump -Fc -U adms -d adms > "$BACKUP" 2>&1
echo "DUMP_EXIT=$?"

echo "=== Verify backup ==="
ls -la "$BACKUP"
stat "$BACKUP"
sha256sum "$BACKUP"

echo "=== pg_restore -l verification ==="
docker exec -i adms_postgres pg_restore -l < "$BACKUP" 2>&1
echo "RESTORE_L_EXIT=$?"

echo "=== pg_dump version ==="
docker exec adms_postgres pg_dump --version
docker exec adms_postgres pg_restore --version

echo "=== Absolute path ==="
readlink -f "$BACKUP"