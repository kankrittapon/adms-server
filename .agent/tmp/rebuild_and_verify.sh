cd /home/kanfullbuster/adms-server

echo "=== Rebuild Collector image ==="
docker compose build listener 2>&1
echo "BUILD_EXIT=$?"

echo "=== Verify image filesystem ==="
docker run --rm adms-server-listener ls -la /app/app/ 2>&1

echo "=== Verify imports ==="
docker run --rm adms-server-listener python -c "import app; print('import app: OK')" 2>&1
docker run --rm adms-server-listener python -c "import app.config; print('import app.config: OK')" 2>&1
docker run --rm adms-server-listener python -c "import app.collector; print('import app.collector: OK')" 2>&1
docker run --rm adms-server-listener python -c "import app.db; print('import app.db: OK')" 2>&1
docker run --rm adms-server-listener python -c "import app.mqtt_client; print('import app.mqtt_client: OK')" 2>&1
docker run --rm adms-server-listener python -c "import app.healthcheck; print('import app.healthcheck: OK')" 2>&1

echo "=== Verify healthcheck module entrypoint (dry, no DB) ==="
docker run --rm adms-server-listener python -c "import app.healthcheck; print('healthcheck importable: OK')" 2>&1