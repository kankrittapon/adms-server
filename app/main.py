import sys
import signal
import logging
from app.config import Config
from app.collector import CollectorStateEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("adms")

def main():
    cfg = Config.from_env()
    log.info("Loaded configuration for ZKTeco device %s:%s", cfg.device_ip, cfg.device_port)
    
    engine = CollectorStateEngine(cfg)

    def signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        log.info("Received signal %s (%d). Initiating graceful shutdown...", sig_name, signum)
        engine.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        engine.run()
    except Exception as e:
        log.exception("Fatal unhandled exception in main: %s", e)
        sys.exit(1)
    
    log.info("ADMS Collector Daemon exiting cleanly (Exit Code 0).")
    sys.exit(0)

if __name__ == "__main__":
    main()
