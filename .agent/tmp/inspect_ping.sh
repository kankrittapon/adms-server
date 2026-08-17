docker exec adms_zkteco_listener python -c "
import inspect, zk.base
src = inspect.getsource(zk.base.ZK_helper.test_ping)
print('=== test_ping ===')
print(src)
src2 = inspect.getsource(zk.base.ZK_helper.test_tcp)
print('=== test_tcp ===')
print(src2)
"