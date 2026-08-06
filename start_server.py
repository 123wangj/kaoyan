# -*- coding: utf-8 -*-
"""一键启动项目：后台拉起 FastAPI (uvicorn) 并对外提供带反向代理的静态服务。

访问 http://localhost:8765/ 即可同时使用前端页面和后端 API。
"""
import http.server
import socketserver
import os
import sys
import time
import threading
import subprocess
import webbrowser
import urllib.request
from pathlib import Path
from http.client import HTTPConnection

ROOT = Path(r'c:\Users\wang\Desktop\考研学习')
STATIC_DIR = ROOT / 'static'
API_PORT = 8000   # FastAPI 后端端口
PORT = 8765      # 对外暴露的端口（前端 + 反向代理）

os.chdir(ROOT)


def wait_for_api(timeout: float = 30.0) -> bool:
    """轮询等待 FastAPI /health 返回 200。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = HTTPConnection('127.0.0.1', API_PORT, timeout=1.0)
            conn.request('GET', '/health')
            resp = conn.getresponse()
            resp.read()
            conn.close()
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start_api():
    """在后台启动 uvicorn 服务。"""
    print(f'  - 启动后端 uvicorn (端口 {API_PORT})...', flush=True)
    creationflags = 0
    if os.name == 'nt':
        # 不弹黑窗
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'kaoyan_ai.api:app',
         '--host', '127.0.0.1', '--port', str(API_PORT)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return proc


# 启动后端
api_proc = start_api()
if not wait_for_api():
    print('  ! 后端启动超时，请手动检查。', flush=True)
else:
    print(f'  - 后端就绪: http://127.0.0.1:{API_PORT}/', flush=True)


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    """静态资源直接返回；其它请求全部转发到后端 FastAPI。"""

    # 这些路径前缀视为静态资源（直接由本进程返回）
    STATIC_PREFIXES = (
        '/static/', '/cleaned/', '/tiku/', '/wangdao/',
        '/favicon.ico', '/.vscode/', '/__pycache__/',
    )

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def _is_static(self, path: str) -> bool:
        if path == '/' or path == '/index.html':
            return False
        return any(path.startswith(p) for p in self.STATIC_PREFIXES)

    def _proxy(self):
        """把请求原样转发到 FastAPI。"""
        try:
            content_length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(content_length) if content_length else b''
            url = f'http://127.0.0.1:{API_PORT}{self.path}'
            req = urllib.request.Request(
                url,
                data=body if self.command in ('POST', 'PUT', 'PATCH', 'DELETE') else None,
                method=self.command,
                headers={k: v for k, v in self.headers.items()
                         if k.lower() not in ('host', 'content-length')},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ('transfer-encoding', 'connection'):
                        continue
                    self.send_header(k, v)
                payload = resp.read()
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            try:
                payload = e.read()
            except Exception:
                payload = b''
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)
        except Exception as e:
            msg = f'{{"detail":"proxy error: {e}"}}'.encode('utf-8')
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self._is_static(self.path):
            # 静态资源直接由本进程返回
            return super().do_GET()
        if self.path == '/' or self.path == '/index.html':
            self.path = '/static/index.html'
            return super().do_GET()
        return self._proxy()

    def do_POST(self):
        return self._proxy()

    def do_PUT(self):
        return self._proxy()

    def do_DELETE(self):
        return self._proxy()

    def do_PATCH(self):
        return self._proxy()

    def log_message(self, format, *args):
        # 简化日志
        sys.stderr.write('  %s - %s\n' % (self.address_string(), format % args))


def serve():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('', PORT), ProxyHandler) as httpd:
        print(f'  - 前端服务: http://localhost:{PORT}/', flush=True)
        print(f'  - PDF 列表: http://localhost:{PORT}/cleaned/', flush=True)
        print(f'  - 按 Ctrl+C 退出', flush=True)
        try:
            webbrowser.open(f'http://localhost:{PORT}/')
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n正在关闭...')
        finally:
            if api_proc and api_proc.poll() is None:
                api_proc.terminate()
                try:
                    api_proc.wait(timeout=5)
                except Exception:
                    api_proc.kill()


if __name__ == '__main__':
    print('=' * 50)
    print('  考研学习项目 - 一键启动')
    print('=' * 50)
    serve()
