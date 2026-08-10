import logging
import os
import time
from datetime import datetime, time as dt_time

import paho.mqtt.client as mqtt
import psycopg2
from zk import ZK

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("adms-listener")

DEVICE_IP = os.getenv("ZK_DEVICE_IP", "192.168.1.201")
DEVICE_PORT = int(os.getenv("ZK_DEVICE_PORT", "4370"))
DEVICE_PASSWORD = int(os.getenv("ZK_DEVICE_PASSWORD", "600"))
DB_DSN = os.environ["DATABASE_URL"]
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "attendance/events")
START_TIME = dt_time.fromisoformat(os.getenv("ON_TIME_START", "05:00:00"))
END_TIME = dt_time.fromisoformat(os.getenv("ON_TIME_END", "10:00:00"))


def db_connection():
    return psycopg2.connect(DB_DSN)


def publish_event(client, payload):
    result = client.publish(MQTT_TOPIC, payload, qos=1)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        log.warning("MQTT publish failed: %s", result.rc)


def save_log(client, attendance):
    user_id = str(attendance.user_id)
    scan_time = attendance.timestamp
    punch_type = str(attendance.punch)
    status = "ON_TIME" if START_TIME <= scan_time.time() <= END_TIME else "LATE"

    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO employees (user_id, display_name)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, f"User_{user_id}"),
        )
        cur.execute(
            """
            INSERT INTO attendance_logs
              (user_id, device_ip, scan_time, punch_type, status, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING
            RETURNING id
            """,
            (user_id, DEVICE_IP, scan_time, punch_type, status,
             '{"source":"zkteco","listener":"adms-server"}'),
        )
        inserted = cur.fetchone()

    if inserted:
        payload = (
            '{"event":"attendance","user_id":"%s","device_ip":"%s",'
            '"scan_time":"%s","punch_type":"%s","status":"%s"}'
            % (user_id, DEVICE_IP, scan_time.isoformat(), punch_type, status)
        )
        publish_event(client, payload)
        log.info("logged user=%s time=%s status=%s", user_id, scan_time, status)
    else:
        log.info("duplicate ignored user=%s time=%s", user_id, scan_time)


def run():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="adms-zkteco-listener")
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    while True:
        connection = None
        try:
            log.info("connecting to ZKTeco %s:%s", DEVICE_IP, DEVICE_PORT)
            connection = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5, password=DEVICE_PASSWORD).connect()
            connection.disable_device()
            log.info("connected; listening for attendance events")
            for attendance in connection.live_capture():
                if attendance is not None:
                    save_log(client, attendance)
        except Exception:
            log.exception("listener cycle failed; retrying in 10 seconds")
            time.sleep(10)
        finally:
            if connection:
                try:
                    connection.enable_device()
                    connection.disconnect()
                except Exception:
                    log.exception("device disconnect failed")


if __name__ == "__main__":
    run()
