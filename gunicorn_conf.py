"""
Gunicorn 生产配置 - FastAPI (Uvicorn ASGI workers)
====================================================

通过环境变量调优:
    WEB_CONCURRENCY     worker 数量 (默认 = CPU*2+1)
    WEB_HOST            绑定地址 (默认 0.0.0.0)
    WEB_PORT            绑定端口 (默认 8000)
    GUNICORN_TIMEOUT    单请求超时秒数 (默认 120,LLM 调用可能较慢)
    GUNICORN_GRACEFUL_TIMEOUT  graceful shutdown 超时 (默认 30)
    GUNICORN_KEEPALIVE  keep-alive 秒数 (默认 5)
    GUNICORN_LOG_LEVEL  日志级别 (默认 info)
    GUNICORN_MAX_REQUESTS  worker 处理多少请求后回收 (默认 1000,防内存泄漏)
    GUNICORN_MAX_REQUESTS_JITTER  抖动值 (默认 100)
"""

import multiprocessing
import os


# ---------- 绑定地址 / 端口 ----------
_host = os.environ.get("WEB_HOST", "0.0.0.0")
_port = os.environ.get("WEB_PORT", "8000")
bind = f"{_host}:{_port}"

# ---------- Worker 配置 ----------
# uvicorn.workers.UvicornWorker 让 Gunicorn 直接管理 ASGI worker,
# 比 SyncWorker 性能高,适合 FastAPI 这种异步框架
worker_class = "uvicorn.workers.UvicornWorker"

# 默认 worker 数 = CPU 核数 * 2 + 1 (IO 密集型可上调)
_web_concurrency = int(os.environ.get("WEB_CONCURRENCY",
                                       multiprocessing.cpu_count() * 2 + 1))
workers = _web_concurrency

# 单个 worker 的线程数 (uvicorn worker 本身是单线程异步,这里主要是 worker 间负载)
threads = int(os.environ.get("WEB_THREADS", "1"))

# ---------- 超时配置 ----------
# LLM 调用可能耗时较长,默认 30s 不够,生产建议 120s
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

# ---------- 内存保护 ----------
# 每个 worker 处理 N 个请求后优雅重启,防止内存累积
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# ---------- 日志 ----------
accesslog = "-"          # stdout
errorlog = "-"           # stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sus'

# ---------- 进程名 ----------
proc_name = "kaoyan-ai"

# ---------- 预加载 ----------
# 预加载应用,节省内存(各 worker 共享只读部分)
preload_app = True


def post_fork(server, worker):
    """worker fork 之后的钩子,适合做连接初始化。"""
    server.log.info(f"Worker {worker.pid} spawned")


def worker_int(worker):
    """worker 接收到 SIGINT/SIGQUIT 时的钩子。"""
    worker.log.info(f"Worker {worker.pid} received INT/QUIT signal")


def on_exit(server):
    """master 退出钩子。"""
    server.log.info("Gunicorn master exiting")
