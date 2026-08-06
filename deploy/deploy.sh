# =============================================================
# 考研 AI 平台 - 日常部署脚本
# 部署到 /opt/kaoyan-ai
# 用法: ./deploy.sh [up|down|restart|logs|status|import|backup|rollback|cert]
# =============================================================
set -euo pipefail

APP_DIR="/opt/kaoyan-ai"
COMPOSE="docker compose"
PG_CONTAINER="kaoyan-ai-db"

cd "$APP_DIR"

action="${1:-up}"

case "$action" in
    up|build)
        echo ">>> 构建并启动"
        $COMPOSE up -d --build
        echo ">>> 等 PostgreSQL 就绪"
        for i in {1..30}; do
            if docker exec $PG_CONTAINER pg_isready -U postgres >/dev/null 2>&1; then
                echo "    PG ready"; break
            fi
            sleep 2
        done
        echo ">>> 等 app 健康"
        for i in {1..30}; do
            if curl -fsS http://127.0.0.1/health >/dev/null 2>&1; then
                echo "    APP healthy"; break
            fi
            sleep 2
        done
        $COMPOSE ps
        ;;

    down)
        echo ">>> 停止(数据卷保留)"
        $COMPOSE down
        ;;

    restart)
        echo ">>> 重启"
        $COMPOSE restart
        ;;

    logs)
        $COMPOSE logs -f --tail=200 app
        ;;

    status)
        $COMPOSE ps
        echo ""
        echo "--- /health ---"
        curl -sS http://127.0.0.1/health || echo "(unreachable)"
        ;;

    import)
        echo ">>> 导入题库/知识点/用户到 PostgreSQL"
        docker exec -it kaoyan-ai-app \
            bash -c "cd /app && python -m scripts.import_to_postgres" || \
        docker exec kaoyan-ai-app \
            bash -c "cd /app && python -m scripts.import_to_postgres"
        ;;

    backup)
        echo ">>> 备份数据"
        DATE=$(date +%F-%H%M)
        mkdir -p "$APP_DIR/backups"
        # 1) PostgreSQL
        docker exec $PG_CONTAINER pg_dump -U postgres kaoyan_ai | \
            gzip > "$APP_DIR/backups/pg_${DATE}.sql.gz"
        # 2) 题库/用户 JSONL
        tar czf "$APP_DIR/backups/data_${DATE}.tgz" -C "$APP_DIR" data
        echo "    -> backups/pg_${DATE}.sql.gz"
        echo "    -> backups/data_${DATE}.tgz"
        # 清理 30 天前的备份
        find "$APP_DIR/backups" -type f -mtime +30 -delete
        ;;

    rollback)
        echo ">>> 回滚到上一个镜像版本"
        $COMPOSE down
        $COMPOSE up -d
        ;;

    cert)
        echo ">>> 申请 Let's Encrypt 证书(首次)"
        docker run --rm \
            -v /opt/kaoyan-ai/certbot/conf:/etc/letsencrypt \
            -v /opt/kaoyan-ai/certbot/www:/var/www/certbot \
            certbot/certbot certonly \
                --webroot --webroot-path /var/www/certbot \
                -d www.sx01bit.cn -d sx01bit.cn \
                --email admin@sx01bit.cn --agree-tos --no-eff-email
        $COMPOSE restart nginx
        ;;

    renew)
        echo ">>> 续期证书(加入 crontab 每月执行)"
        docker run --rm \
            -v /opt/kaoyan-ai/certbot/conf:/etc/letsencrypt \
            -v /opt/kaoyan-ai/certbot/www:/var/www/certbot \
            certbot/certbot renew
        $COMPOSE restart nginx
        ;;

    *)
        echo "用法: $0 {up|down|restart|logs|status|import|backup|rollback|cert|renew}"
        exit 1
        ;;
esac
