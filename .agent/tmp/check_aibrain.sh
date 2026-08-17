echo "=== ADMS containers ==="
docker ps -a --filter name=adms --format '{{.Names}} {{.Status}}'
echo "=== ADMS volumes ==="
docker volume ls --filter name=adms --format '{{.Name}}'
echo "=== ADMS networks ==="
docker network ls --filter name=adms --format '{{.Name}}'
echo "=== Backup files ==="
ls -lh /home/kanfullbuster/adms-server/backups/ 2>/dev/null || echo "no backups dir"
echo "=== Dump SHA256 ==="
sha256sum /home/kanfullbuster/adms-server/backups/adms_post_excel_import_20260811_121449.dump 2>/dev/null || echo "dump not found"
echo "=== Dump header ==="
head -1 /home/kanfullbuster/adms-server/backups/adms_post_excel_import_20260811_121449.dump 2>/dev/null | cat -v | head -c 200
echo ""
echo "=== pg_restore -l test ==="
docker exec adms_postgres pg_restore -l /backups/adms_post_excel_import_20260811_121449.dump 2>&1 || echo "pg_restore FAILED"