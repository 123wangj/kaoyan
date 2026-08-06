#!/usr/bin/env bash
set -e
cd /opt/kaoyan-ai

echo "=== 1. 验证 80 端口能访问(Let's Encrypt 校验用)==="
curl -s -o /dev/null -w "127.0.0.1 -> %{http_code}\n" http://127.0.0.1/.well-known/acme-challenge/test
curl -s -o /dev/null -w "www.sx01bit.cn -> %{http_code}\n" --resolve www.sx01bit.cn:80:123.57.108.93 http://www.sx01bit.cn/.well-known/acme-challenge/test

echo ""
echo "=== 2. DNS 解析验证 ==="
getent hosts www.sx01bit.cn 2>&1 || true
getent hosts sx01bit.cn 2>&1 || true

echo ""
echo "=== 3. 用 webroot 模式申请证书 ==="
docker run --rm \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/certbot/www:/var/www/certbot \
  certbot/certbot certonly \
    --webroot --webroot-path /var/www/certbot \
    -d www.sx01bit.cn -d sx01bit.cn \
    --email admin@sx01bit.cn \
    --agree-tos --no-eff-email \
    --force-renewal 2>&1 | tail -20

echo ""
echo "=== 4. 检查证书 ==="
ls -la certbot/conf/live/www.sx01bit.cn/ 2>&1 || echo "证书未生成"
echo ""
echo "=== 5. 证书详情 ==="
if [ -f certbot/conf/live/www.sx01bit.cn/fullchain.pem ]; then
  openssl x509 -in certbot/conf/live/www.sx01bit.cn/fullchain.pem -noout -subject -dates 2>&1
fi
