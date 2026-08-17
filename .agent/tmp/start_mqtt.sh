cd /home/kanfullbuster/adms-server

echo "=== Re-check port 1883 ==="
ss -lntup 2>&1 | grep 1883 || echo "1883 not in use"

echo "=== Start MQTT ==="
docker compose up -d mqtt 2>&1
echo "MQTT_START_EXIT=$?"

echo "=== Verify MQTT ==="
sleep 3
docker ps --filter name=adms_mqtt --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker compose ps mqtt 2>&1
echo "=== MQTT logs ==="
docker logs adms_mqtt --tail 10 2>&1
echo "=== Port 1883 now ==="
ss -lntup 2>&1 | grep 1883 || echo "1883 not listening"
echo "=== Unrelated containers unchanged ==="
docker ps --format '{{.Names}} {{.Status}}' | grep -v adms