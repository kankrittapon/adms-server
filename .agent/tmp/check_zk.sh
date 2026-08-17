echo "=== ping from ai-brain host ==="
ping -c 3 -W 2 192.168.1.201 2>&1

echo "=== tcp 4370 from ai-brain host ==="
timeout 3 bash -c 'echo > /dev/tcp/192.168.1.201/4370' 2>&1 && echo "TCP_OK" || echo "TCP_FAIL"

echo "=== tcp 4370 from collector container ==="
docker exec adms_zkteco_listener python -c "
import socket
s = socket.socket()
s.settimeout(3)
try:
    s.connect(('192.168.1.201', 4370))
    print('docker_tcp_OK')
    s.close()
except Exception as e:
    print('docker_tcp_FAIL:', e)
" 2>&1

echo "=== docker network ==="
docker network inspect adms-server_default --format '{{range .IPAM.Config}}subnet={{.Subnet}} gateway={{.Gateway}}{{end}}' 2>&1
docker inspect adms_zkteco_listener --format '{{.NetworkSettings.Networks}}' 2>&1