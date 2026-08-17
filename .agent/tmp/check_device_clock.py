from zk import ZK
from datetime import datetime, timezone
zk = ZK("192.168.1.201", port=4370, timeout=5, password=600)
conn = zk.connect()
# Get device time
dev_time = conn.get_time()
print("device_time:", repr(dev_time), "tzinfo:", dev_time.tzinfo)
print("device_time_iso:", dev_time.isoformat())
# Compare with actual UTC and local
now_utc = datetime.now(timezone.utc)
print("actual_utc:", now_utc.isoformat())
# Get device options for timezone
try:
    options = conn.get_options()
    for k, v in options.items():
        print(f"  option {k}={v}")
except Exception as e:
    print("get_options error:", e)
conn.disconnect()