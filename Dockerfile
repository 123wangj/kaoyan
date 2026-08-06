# =============================================================
# 考研 AI 平台 - 生产镜像
# Python 3.11-slim + Gunicorn + Uvicorn workers
# =============================================================
FROM python:3.11-slim AS base

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 替换 Debian 源为阿里云 mirror(国内构建加速)
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi && \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi

# 安装系统依赖(matplotlib 需要的 libgomp 等)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        tzdata \
        libgomp1 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先 copy 依赖文件,利用 Docker 缓存
COPY pyproject.toml ./
# 如果有 requirements.txt 也支持
COPY requirements.txt* ./

# 配置 pip 国内 mirror
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.aliyun.com

# 安装项目依赖(生产环境,不安装 dev/test 依赖)
RUN pip install --upgrade pip && \
    pip install -e . && \
    pip install "gunicorn>=22.0.0" "uvicorn[standard]>=0.30.0"

# 复制项目代码
COPY . .

# 创建数据目录(可被挂载覆盖)
RUN mkdir -p /app/data /app/data/users

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# 启动命令(由 gunicorn_conf.py 读取环境变量)
CMD ["gunicorn", "-c", "gunicorn_conf.py", "kaoyan_ai.api:app"]
