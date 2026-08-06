#!/usr/bin/env bash
echo "=== 宿主机 /opt/kaoyan-ai/static 修改时间 ==="
ls -la /opt/kaoyan-ai/static/home.html /opt/kaoyan-ai/static/home.js
echo ""
echo "=== app 容器内 /app/static 修改时间 ==="
docker exec kaoyan-ai-app ls -la /app/static/home.html /app/static/home.js
echo ""
echo "=== 容器内 home.html 是否含 loginFootRegister ==="
docker exec kaoyan-ai-app grep -c loginFootRegister /app/static/home.html
echo ""
echo "=== 容器内 home.js 是否含 loginFootRegister ==="
docker exec kaoyan-ai-app grep -c loginFootRegister /app/static/home.js
echo ""
echo "=== 容器内 home.html 是否含 registerForm(应为 0) ==="
docker exec kaoyan-ai-app grep -c registerForm /app/static/home.html
