echo "=== Test pyzk connect directly ==="
docker exec adms_zkteco_listener python -c "
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
    print('Users:', len(users))
    for u in users:
        print('  user_id=%s uid=%s name=%s privilege=%s' % (u.user_id, u.uid, u.name, u.privilege))
    att = conn.get_attendance()
    print('Attendance records:', len(att))
    for a in att[:20]:
        print('  user_id=%s timestamp=%s punch=%s status=%s' % (a.user_id, a.timestamp, a.punch, a.status))
    conn.disconnect()
    print('DONE')
except Exception as e:
    print('ERROR:', e)
    traceback.print_exc()
" 2>&1