echo "=== Copy dump into container ==="
docker cp /home/kanfullbuster/adms-server/backups/adms_post_excel_import_20260811_121449.dump adms_postgres:/tmp/test.dump 2>&1
echo "=== pg_restore -l test ==="
docker exec adms_postgres pg_restore -l /tmp/test.dump 2>&1
echo "EXIT_CODE=$?"
echo "=== Cleanup ==="
docker exec adms_postgres rm -f /tmp/test.dump 2>&1