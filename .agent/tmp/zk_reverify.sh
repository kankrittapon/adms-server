echo "=== ZKTECO PING ==="
ping -c 3 192.168.1.201 2>&1
echo "=== ZKTECO TCP ==="
nc -z -w 3 192.168.1.201 4370 2>&1 && echo "TCP OK" || echo "TCP FAIL"