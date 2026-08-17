echo "=== .ENV CHECK ==="
cd /home/kanfullbuster/adms-server
ls -la .env .env.example 2>/dev/null
git check-ignore .env 2>&1
stat -c '%a %n' .env 2>/dev/null
echo "=== .ENV VARS (no secrets) ==="
grep -E '^(POSTGRES_DB|POSTGRES_USER|ZK_DEVICE_IP|ZK_DEVICE_PORT|ZK_DEVICE_PASSWORD|MQTT_TOPIC|ON_TIME_START|ON_TIME_END)=' .env 2>/dev/null | sed 's/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD: SET/'
echo "=== POSTGRES_PASSWORD SET? ==="
grep -q '^POSTGRES_PASSWORD=' .env 2>/dev/null && echo "POSTGRES_PASSWORD: SET" || echo "POSTGRES_PASSWORD: NOT SET"
echo "=== ZKTECO PING ==="
ping -c 3 192.168.1.201 2>&1
echo "=== ZKTECO TCP ==="
nc -z -w 3 192.168.1.201 4370 2>&1 && echo "TCP OK" || echo "TCP FAIL"