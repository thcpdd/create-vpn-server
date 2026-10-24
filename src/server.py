"""
Clash 订阅服务器

监听 25500 端口，将 VLESS 链接动态转换为 Clash YAML 配置供客户端订阅。
零外部依赖，仅使用 Python 内置库。

端点:
  GET /sub?token=<token>  — 返回 Clash YAML 配置（token 由 setup.sh 生成）
  GET /version            — 返回服务器状态
"""

import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 确保当前目录在 path 中，以便 import convert 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convert
from subscription_userinfo import get_subscription_userinfo

TOKEN_FILE = "/root/clash-token.txt"
VLESS_FILE = "/root/vless-link.txt"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 25500


def load_token():
    """读取 auth token"""
    try:
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def load_vless_text():
    """读取 VLESS 链接文本"""
    try:
        with open(VLESS_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


class RequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def _send_response(self, code, content, content_type="text/plain; charset=utf-8"):
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Connection", "close")

        # 设置订阅流量、订阅过期请求头
        subscription_userinfo = get_subscription_userinfo()
        if subscription_userinfo:
            self.send_header("subscription-userinfo", subscription_userinfo)

        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        token = load_token()

        if path == "/version":
            self._send_response(200, '{"status":"ok"}', "application/json")
            return

        if path == "/sub":
            req_token = params.get("token", [""])[0]

            if not token or not req_token:
                self._send_response(403, "缺少 token 参数")
                return

            if req_token != token:
                self._send_response(403, "token 无效")
                return

            vless_text = load_vless_text()
            if not vless_text:
                self._send_response(500, "VLESS 链接文件不存在，请先运行 setup.sh")
                return

            try:
                config = convert.build_clash_config(vless_text)
                self._send_response(200, config, "text/yaml; charset=utf-8")
            except Exception as e:
                sys.stderr.write("生成配置失败: %s\n" % e)
                self._send_response(500, "配置生成失败: %s" % e)
            return

        self._send_response(404, "Not Found")


def main():
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), RequestHandler)
    print("Clash 订阅服务器已启动: http://%s:%s" % (LISTEN_HOST, LISTEN_PORT), file=sys.stderr)
    token = load_token()
    if token:
        print("订阅端点: /sub?token=%s" % token, file=sys.stderr)
    print("状态检查: /version", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
