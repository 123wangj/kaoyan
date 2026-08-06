#!/usr/bin/env bash
echo "=== 1. 清 certbot lock ==="
docker run --rm -v /opt/kaoyan-ai/certbot/conf:/etc/letsencrypt -v /opt/kaoyan-ai/certbot/www:/var/www/certbot alpine sh -c "find /var/log/letsencrypt -name '*.lock' -delete 2>/dev/null; rm -f /var/lib/letsencrypt/*.lock 2>/dev/null; echo OK"

echo ""
echo "=== 2. certbot 续期 dry-run ==="
docker run --rm -v /opt/kaoyan-ai/certbot/conf:/etc/letsencrypt -v /opt/kaoyan-ai/certbot/www:/var/www/certbot certbot/certbot renew --dry-run 2>&1 | tail -6

echo ""
echo "=== 3. LLM 真实调用(POST /chat)==="
curl -sk --max-time 60 -X POST https://www.sx01bit.cn/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test01","message":"你好,简单介绍一下你自己,50 字以内","subject":"数据结构"}' 2>&1 | head -c 800
echo ""
