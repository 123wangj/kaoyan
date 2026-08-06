# =============================================================
# 考研 AI 平台 - 服务器初始化(Alibaba Cloud Linux 3)
# 在 123.57.108.93 上以 root 密钥执行
# 适配 alinux3 / dnf / 1.8G 内存
# =============================================================
set -euo pipefail

echo "=========== 1. 系统更新 ==========="
dnf update -y

echo "=========== 2. 必备工具 ==========="
dnf install -y curl wget git vim htop jq rsync ca-certificates \
    firewalld chrony

echo "=========== 3. 时区 ==========="
timedatectl set-timezone Asia/Shanghai || true
ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

echo "=========== 4. 防火墙(只放行 22/80/443) ==========="
systemctl enable --now firewalld
firewall-cmd --permanent --zone=public --remove-service=ssh || true
firewall-cmd --permanent --zone=public --add-port=22/tcp
firewall-cmd --permanent --zone=public --add-port=80/tcp
firewall-cmd --permanent --zone=public --add-port=443/tcp
firewall-cmd --reload
firewall-cmd --list-all

echo "=========== 5. 安装 Docker ==========="
if ! command -v docker >/dev/null 2>&1; then
    dnf install -y dnf-utils
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
fi

echo "=========== 6. 验证 Docker ==========="
docker --version
docker compose version
docker info 2>&1 | grep -E "Server Version|Storage Driver|Cgroup"

echo "=========== 7. 部署目录 ==========="
mkdir -p /opt/kaoyan-ai/{data,data/users,logs,logs/nginx,pgdata,certbot/conf,certbot/www,backups}
chown -R root:root /opt/kaoyan-ai

echo "=========== 8. 内核优化 ==========="
cat >> /etc/sysctl.conf <<'EOF'
# 考研 AI 平台调优
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 4096
vm.overcommit_memory = 1
EOF
sysctl -p

echo "=========== 9. 自动备份 cron ==========="
cat > /etc/cron.d/kaoyan-backup <<'EOF'
# 每天凌晨 3 点自动备份
0 3 * * * root /opt/kaoyan-ai/deploy/deploy.sh backup >> /opt/kaoyan-ai/logs/backup.log 2>&1
EOF
chmod 644 /etc/cron.d/kaoyan-backup

echo "=========== ✅ 初始化完成 ==========="
echo "下一步:把代码 + .env 拷到 /opt/kaoyan-ai,然后 docker compose up -d --build"
