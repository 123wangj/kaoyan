#!/usr/bin/env bash
# 写入 .env(强 JWT + 真实 API Key)
set -e
cd /opt/kaoyan-ai

JWT=$(openssl rand -hex 32)
sed -i "s|JWT_SECRET=PLACEHOLDER_WILL_BE_REPLACED|JWT_SECRET=${JWT}|" /tmp/.env.tmp
mv /tmp/.env.tmp /opt/kaoyan-ai/.env
chmod 600 /opt/kaoyan-ai/.env

echo "=== .env 已就位 ==="
ls -la /opt/kaoyan-ai/.env
echo ""
echo "DASHSCOPE_API_KEY 前 8 位: $(grep ^DASHSCOPE_API_KEY /opt/kaoyan-ai/.env | cut -d= -f2 | cut -c1-8)..."
echo "JWT_SECRET 前 16 位: $(grep ^JWT_SECRET /opt/kaoyan-ai/.env | cut -d= -f2 | cut -c1-16)..."
