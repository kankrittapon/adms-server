set -e
cd /home/kanfullbuster/adms-server

echo "=== Pull ==="
git fetch origin
git pull --ff-only origin main 2>&1
echo "post_pull_HEAD=$(git rev-parse HEAD)"
echo "origin_main=$(git rev-parse origin/main)"
git status --short

echo "=== Stop collector ==="
docker compose stop listener 2>&1

echo "=== Rebuild ==="
docker compose build listener 2>&1
echo "BUILD_EXIT=$?"

echo "=== Verify ping in image ==="
docker run --rm adms-server-listener which ping 2>&1
docker run --rm adms-server-listener ping -c 1 -W 2 192.168.1.201 2>&1

echo "=== Test pyzk connect ==="
docker run --rm --network adms-server_default adms-server-listener python -c "
from zk import ZK
import traceback
zk = ZK('192.168.1.201', port=4370, timeout=5, password=600)
try:
    conn = zk.connect()
    print('CONNECTED')
    print('Serial:', conn.get_serial_number())
    print('Platform:', conn.get_platform())
    print('Firmware:', conn.get_firmware_version())
    users = conn.get_users()
    print('Users count:', len(users))
    for u in users:
        print('  user_id=%s uid=%s name=%s privilege=%s' % (u.user_id, u.uid, u.name, u.privilege))
    att = conn.get_attendance()
    print('Attendance records:', len(att))
    for a in att[:30]:
        print('  user_id=%s timestamp=%s punch=%s status=%s' % (a.user_id, a.timestamp, a.punch, a.status))
    conn.disconnect()
    print('PYZK_TEST_DONE')
except Exception as e:
    print('ERROR:', e)
    traceback.print_exc()
" 2>&1