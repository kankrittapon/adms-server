echo "=== SERVER GIT ==="
cd /home/kanfullbuster/adms-server
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git status --short
echo "=== .ENV ==="
git check-ignore .env 2>&1
stat -c '%a %n' .env 2>/dev/null || echo "no .env"
echo "=== MIGRATIONS ==="
ls -1 sql/00*.sql 2>/dev/null
echo "=== POSTGRES CONTAINER ==="
docker ps --filter name=adms_postgres --format '{{.Names}} {{.Status}} {{.Ports}}'
echo "=== POSTGRES NETWORK ==="
docker network inspect adms-server_default --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null
echo "=== POSTGRES VOLUME ==="
docker volume ls --filter name=adms --format '{{.Name}}'
echo "=== BOOTSTRAP TABLES ==="
docker exec adms_postgres psql -U adms -d adms -c "\dt" 2>&1
echo "=== UNRELATED CONTAINERS ==="
docker ps --format '{{.Names}} {{.Status}}' | grep -v adms