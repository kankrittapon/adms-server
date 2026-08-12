"""
Entry point: python -m app.native_push

Starts the isolated experimental Native Push listener (LAN-only, allowlist,
canonical ingestion). Intentionally separate from the polling Collector.
"""
import logging
import signal
import sys

from app.native_push.config import NativePushConfig
from app.native_push.service import NativePushServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("adms.native_push")


def main() -> int:
    npc = NativePushConfig.from_env()
    log.info(
        "Native Push listener config: bind=%s:%s allowlist=%s serial_validation=%s",
        npc.host, npc.port,
        ",".join(sorted(npc.allowed_sources)) if npc.source_allowlist_enabled else "DISABLED",
        npc.serial_validation_enabled,
    )

    mqtt_service = None
    if npc.mqtt_publish_enabled:
        from app.mqtt_client import MQTTService
        from app.native_push.service import build_canonical_config

        mqtt_service = MQTTService(build_canonical_config(npc))
        mqtt_service.start()
        log.info("Push-side MQTT publishing ENABLED (PUSH_MQTT_PUBLISH=true).")

    server = NativePushServer((npc.host, npc.port), npc, mqtt_service=mqtt_service)

    def _shutdown(signum, frame):
        log.info("Signal %s received — shutting down listener.", signum)
        server.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever_loop()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.exception("Fatal listener error: %s", e)
        return 1
    log.info("Native Push listener stopped cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
