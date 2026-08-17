docker exec adms_zkteco_listener python -c "
import inspect, zk.base
src = inspect.getsource(zk.base.ZK.connect)
print(src[:3000])
"