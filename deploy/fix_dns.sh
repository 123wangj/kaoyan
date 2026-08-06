#!/usr/bin/env bash
# 修复 Docker 镜像源 + 重启
set -e

echo "=== 1. DNS 检查 ==="
cat /etc/resolv.conf
echo "---"
# 测试域名解析
for d in mirror.ccs.aliyun.com docker.io registry-1.docker.io; do
  echo -n "$d -> "
  getent hosts $d 2>&1 | head -1 || echo "解析失败"
done

echo ""
echo "=== 2. 测试外网连通性 ==="
curl -s -o /dev/null -w "mirror.ccs.aliyun.com: %{http_code} %{time_total}s\n" --max-time 8 https://mirror.ccs.aliyun.com/v2/ 2>&1 || true
curl -s -o /dev/null -w "docker.m.daocloud.io: %{http_code} %{time_total}s\n" --max-time 8 https://docker.m.daocloud.io/v2/ 2>&1 || true

echo ""
echo "=== 3. 写入阿里云 mirror ==="
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.aliyun.com",
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com"
  ],
  "log-driver": "json-file",
  "log-opts": {"max-size": "50m", "max-file": "3"}
}
EOF

echo ""
echo "=== 4. 重启 Docker ==="
pkill -9 dockerd 2>/dev/null || true
pkill -9 containerd 2>/dev/null || true
sleep 2
systemctl reset-failed docker
systemctl start docker
sleep 5
systemctl is-active docker

echo ""
echo "=== 5. 验证 mirror ==="
docker info 2>&1 | grep -A 5 "Registry Mirrors"
