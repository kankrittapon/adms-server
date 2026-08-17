echo "=== IDENTITY ==="
hostname
whoami
pwd
echo "=== GIT ==="
cd /home/kanfullbuster/adms-server
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
echo "=== COMPOSE PROJECTS ==="
docker compose ls 2>&1
echo "=== ADMS CONTAINERS ==="
docker ps -a --filter name=adms --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "=== ALL CONTAINERS ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "=== NETWORKS ==="
docker network ls --format 'table {{.Name}}\t{{.Driver}}'
echo "=== VOLUMES ==="
docker volume ls --filter name=adms --format '{{.Name}}'
echo "=== DISK ==="
df -h /
echo "=== LISTENING PORTS ==="
ss -lntup 2>&1 | head -40