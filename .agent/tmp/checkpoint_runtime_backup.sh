echo "=== Collector logs (tail 30) ==="
docker logs adms_zkteco_listener --tail 30 2>&1

echo "=== Healthcheck detail ==="
docker inspect adms_zkteco_listener --format '{{range .State.Health.Log}}exit={{.ExitCode}} out={{.Output}}{{end}}' 2>&1

echo "=== MQTT logs ==="
docker logs adms_mqtt --tail 5 2>&1

echo "=== ZKTeco reachability (read-only) ==="
docker exec adms_zkteco_listener python -c "
from zk import ZK
zk = ZK('192.168.1.201', port=4370, timeout=5, password=600)
try:
    conn = zk.connect()
    print('ZK_CONNECTED serial=' + str(conn.get_serialnumber()) + ' platform=' + conn.get_platform())
    conn.disconnect()
except Exception as e:
    print('ZK_ERROR:', e)
" 2>&1

echo "=== Backup file verification ==="
ls -l /home/kanfullbuster/adms-server/backups/adms_reconstructed_authoritative_20260811_153725.dump
stat /home/kanfullbuster/adms-server/backups/adms_reconstructed_authoritative_20260811_153725.dump
sha256sum /home/kanfullbuster/adms-server/backups/adms_reconstructed_authoritative_20260811_153725.dump

echo "=== pg_restore -l ==="
docker exec -i adms_postgres pg_restore -l < /home/kanfullbuster/adms-server/backups/adms_reconstructed_authoritative_20260811_153725.dump 2>&1
echo "RESTORE_L_EXIT=$?"

echo "=== pg versions ==="
docker exec adms_postgres pg_dump --version
docker exec adms_postgres pg_restore --version

echo "=== Git ignore check ==="
cd /home/kanfullbuster/adms-server
git check-ignore .env backups/ .agent/ 2>&1 || echo "check-ignore done"
cat .gitignore 2>&1 | head -20