# =============================================================
# 考研 AI 平台 - 正式上线部署手册
# 目标服务器: 123.57.108.93(阿里云 ECS,Ubuntu 22.04)
# 域名: www.sx01bit.cn
# 数据库: PostgreSQL 14
# LLM: 阿里云百炼(Qwen)
# =============================================================

## 0. 准备

- ✅ 阿里云控制台:
  1. ECS 安全组放行: 22 / 80 / 443
  2. 域名 DNS 解析: `www.sx01bit.cn` → `123.57.108.93`(A 记录)
  3. 百炼控制台: https://dashscope.console.aliyun.com/
     开通 "模型服务" → 创建 API-KEY(注意保存,只显示一次)
- ✅ 域名的 ICP 备案必须完成(中国大陆服务器强制要求)

## 1. 服务器初始化(在本机通过 SSH 密钥执行)

```bash
# 上传 bootstrap.sh 到服务器
scp deploy/bootstrap.sh root@123.57.108.93:/root/

# SSH 登入
ssh root@123.57.108.93

# 执行初始化
bash /root/bootstrap.sh
```

> 预计 5-10 分钟。会装好 Docker、防火墙(只放 22/80/443)、fail2ban、时区。

## 2. 上传项目代码

```bash
# 在本机项目根目录
rsync -avz --exclude '.venv' --exclude '__pycache__' \
    --exclude '.git' --exclude 'logs/*' --exclude 'pgdata' \
    --exclude 'tiku' --exclude 'cleaned' --exclude 'data_backup_*' \
    -e "ssh -i $HOME/.ssh/kaoyan_deploy_key" \
    ./ root@123.57.108.93:/opt/kaoyan-ai/
```

## 3. 配置生产 .env

```bash
ssh root@123.57.108.93
cd /opt/kaoyan-ai
cp .env.production .env
vim .env   # 填入 DASHSCOPE_API_KEY / JWT_SECRET / DB_PASSWORD
```

关键变量:
| 变量 | 来源 |
|---|---|
| `DASHSCOPE_API_KEY` | 百炼控制台创建 |
| `JWT_SECRET` | `openssl rand -hex 32` 生成 |
| `DB_PASSWORD` | 自己定一个强密码,记得同步到 `docker-compose.yml` 默认值 |

## 4. 启动 + 申请 HTTPS

```bash
cd /opt/kaoyan-ai
chmod +x deploy/deploy.sh

# 4.1 启动(只跑 80 端口的临时 nginx 配置可改为 certbot 用)
./deploy/deploy.sh up

# 4.2 申请 Let's Encrypt 证书
./deploy/deploy.sh cert

# 4.3 验证
curl -I http://www.sx01bit.cn/.well-known/acme-challenge/test   # 80 可达
curl -I https://www.sx01bit.cn/health                           # 443 正常
```

## 5. 导入题库 / 知识点 / 用户

```bash
./deploy/deploy.sh import
```

会把 `data/*.jsonl`(题库 / 知识点)与 `data/users/*.json` 灌入 PostgreSQL。

## 6. 验证

| URL | 期望 |
|---|---|
| https://www.sx01bit.cn/ | 前端首页 |
| https://www.sx01bit.cn/docs | FastAPI Swagger |
| https://www.sx01bit.cn/health | `{"status":"ok"}` |
| 浏览器锁头绿锁 | 证书有效 |

## 7. 日常运维

```bash
# 看日志
./deploy/deploy.sh logs

# 升级代码
git pull && ./deploy/deploy.sh up

# 每日自动备份(加到 crontab)
0 3 * * * /opt/kaoyan-ai/deploy/deploy.sh backup
```

## 8. 故障排查

| 现象 | 排查 |
|---|---|
| `curl /health` 502 | `docker compose logs app` 看 Python 错误 |
| HTTPS 证书无效 | `docker compose run --rm certbot certificates` 查看 |
| 浏览器打不开 | 1) 安全组 443 2) DNS 是否生效 `nslookup www.sx01bit.cn` |
| 调 LLM 报 401 | 检查 .env 里 `DASHSCOPE_API_KEY` 是否正确 |
| 数据库连接失败 | `docker exec kaoyan-ai-db pg_isready -U postgres` |

## 9. 安全清单

- [x] 防火墙仅放行 22 / 80 / 443
- [x] fail2ban 防 SSH 暴力破解
- [x] HTTPS 强制 + HSTS
- [x] JWT 密钥在 .env(已加入 .gitignore)
- [x] 数据库密码强随机
- [x] 日志集中到 /app/logs,可接云日志
- [ ] 建议开启阿里云安骑士 / 云安全中心
- [ ] 建议把每日 pg_dump 同步到 OSS
