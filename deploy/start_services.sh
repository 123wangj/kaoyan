#!/usr/bin/env bash
# 在服务器上启动所有服务
set -e
cd /opt/kaoyan-ai

# 创建数据卷目录(权限给 PostgreSQL 用户 999)
mkdir -p pgdata certbot/conf certbot/www logs logs/nginx data/users backups
chown -R 999:999 pgdata 2>/dev/null || true

echo "=== 1. 检查 .env 完整性 ==="
test -f .env || { echo "❌ .env 不存在"; exit 1; }

echo ""
echo "=== 2. 检查 docker-compose.yml 引用 ==="
grep -E 'image:|container_name:' docker-compose.yml

echo ""
echo "=== 3. 拉取基础镜像 ==="
docker compose pull 2>&1 | tail -20

echo ""
echo "=== 4. 构建 app 镜像(本地 Dockerfile) ==="
docker compose build app 2>&1 | tail -10

echo ""
echo "=== 5. 启动所有服务 ==="
docker compose up -d 2>&1 | tail -20

echo ""
echo "=== 6. 等 10 秒看启动情况 ==="
sleep 10
docker compose ps

echo ""
echo "=== 7. 资源占用 ==="
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'
