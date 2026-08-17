echo "=== Host identity ==="
hostname
whoami
pwd
hostname -I

echo "=== Server git ==="
cd /home/kanfullbuster/adms-server
git status --short
git branch --show-current
echo "server_HEAD=$(git rev-parse HEAD)"
echo "origin_main=$(git rev-parse origin/main)"
git remote -v

echo "=== Docker compose ls ==="
docker compose ls 2>&1

echo "=== ADMS compose ps ==="
cd /home/kanfullbuster/adms-server
docker compose ps 2>&1

echo "=== All containers (adms filter) ==="
docker ps -a --filter name=adms --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo "=== Unrelated workloads ==="
docker ps --format '{{.Names}} {{.Status}}' | grep -v adms

echo "=== Ports ==="
ss -lntup 2>&1 | grep -E '1883|5432|4370' || echo "no ADMS-relevant host ports"

echo "=== Networks ==="
docker network inspect adms-server_default --format 'subnet={{.IPAM.Config}}' 2>&1

echo "=== Volumes ==="
docker volume ls --filter name=adms 2>&1

echo "=== Restart counts ==="
docker inspect adms_postgres --format '{{.Name}} restarts={{.RestartCount}} state={{.State.Status}} health={{.State.Health.Status}}' 2>&1
docker inspect adms_mqtt --format '{{.Name}} restarts={{.RestartCount}} state={{.State.Status}}' 2>&1
docker inspect adms_zkteco_listener --format '{{.Name}} restarts={{.RestartCount}} state={{.State.Status}} health={{.State.Health.Status}}' 2>&1