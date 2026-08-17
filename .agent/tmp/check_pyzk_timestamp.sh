docker exec adms_zkteco_listener python3 << 'PYEOF'
from zk import ZK
zk = ZK("192.168.1.201", port=4370, timeout=5, password=600)
conn = zk.connect()
logs = conn.get_attendance()
if logs:
    rec = logs[0]
    print("type:", type(rec.timestamp))
    print("repr:", repr(rec.timestamp))
    print("tzinfo:", rec.timestamp.tzinfo)
    print("isoformat:", rec.timestamp.isoformat())
    print("uid:", rec.uid, "user_id:", rec.user_id, "punch:", rec.punch)
else:
    print("no logs")
conn.disconnect()
PYEOF