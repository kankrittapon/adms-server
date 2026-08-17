cd /home/kanfullbuster/adms-server

echo "=== Verify Excel file on ai-brain ==="
ls -la 'excel/files/รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx' 2>&1

echo "=== Build temporary import container ==="
# Create a temporary Dockerfile for the import tool
cat > /tmp/Dockerfile.import << 'EOF'
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir openpyxl psycopg2-binary
COPY . /app
WORKDIR /app
EOF

# Build the image
docker build -f /tmp/Dockerfile.import -t adms-import-temp /home/kanfullbuster/adms-server 2>&1
echo "BUILD_EXIT=$?"

echo "=== Run dry-run ==="
# Get the postgres password from .env
PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)

docker run --rm \
  --network adms-server_default \
  -v /home/kanfullbuster/adms-server:/app \
  -e DB_HOST=adms_postgres \
  -e DB_PORT=5432 \
  -e DB_NAME=adms \
  -e DB_USER=adms \
  -e DB_PASSWORD="$PGPASS" \
  -w /app \
  adms-import-temp \
  python -m app.import_excel_human_master --dry-run 2>&1
echo "DRY_RUN_EXIT=$?"