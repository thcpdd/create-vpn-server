"""
Clash 订阅服务器

监听随机端口（由 setup.sh 首次运行时生成，保存在 /root/clash-sub-port.txt），将 VLESS 链接动态转换为 Clash YAML 配置供客户端订阅。
零外部依赖，仅使用 Python 内置库。

端点:
  GET /sub?token=<token>  — 返回 Clash YAML 配置（token 由 setup.sh 生成）
  GET /version            — 返回服务器状态
"""

import sys
import os
import ipaddress
import re
import shutil
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

# 确保当前目录在 path 中，以便 import convert 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import convert
from subscription_userinfo import get_subscription_userinfo

TOKEN_FILE = "/root/clash-token.txt"
VLESS_FILE = "/root/vless-link.txt"
SUB_NAME_FILE = "/root/clash-sub-name.txt"
DEFAULT_SUB_NAME = "VPN"
# Xray 从该版本起 REALITY 支持后量子密钥交换 X25519MLKEM768
MLKEM_MIN_XRAY_VERSION = (25, 5, 16)
LISTEN_HOST = "0.0.0.0"
PORT_FILE = "/root/clash-sub-port.txt"
DEFAULT_PORT = 25500


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


def load_sub_name():
    """读取订阅名称，未设置时使用默认值"""
    try:
        with open(SUB_NAME_FILE, "r", encoding="utf-8") as f:
            name = f.read().strip()
            return name or DEFAULT_SUB_NAME
    except FileNotFoundError:
        return DEFAULT_SUB_NAME


def load_port():
    """读取监听端口，文件不存在或无效时使用默认端口"""
    try:
        with open(PORT_FILE, "r") as f:
            port = int(f.read().strip())
            if 1 <= port <= 65535:
                return port
    except (FileNotFoundError, ValueError):
        pass
    return DEFAULT_PORT


def get_xray_version():
    """获取本机 Xray 版本号元组，如 (25, 10, 15)；获取失败返回 None"""
    xray = shutil.which("xray") or "/usr/local/bin/xray"
    try:
        out = subprocess.run([xray, "version"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"Xray\s+v?(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m.groups()) if m else None


def xray_supports_mlkem():
    """服务端 Xray 是否支持 X25519MLKEM768（每次请求时检测，升级 Xray 后自动生效）"""
    version = get_xray_version()
    return version is not None and version >= MLKEM_MIN_XRAY_VERSION


def parse_node_ip(value):
    """校验 node_ip 参数，返回规范化的 IP 字符串；不是合法 IPv4/IPv6 地址时返回 None"""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def parse_node_port(value):
    """校验 node_port 参数，返回 1-65535 的整数；无效时返回 None"""
    value = value.strip()
    if not value.isdigit():
        return None
    port = int(value)
    return port if 1 <= port <= 65535 else None


class RequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def _send_response(self, code, content, content_type="text/plain; charset=utf-8", extra_headers=None):
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Connection", "close")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)

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

            node_ip = None
            raw_node_ip = params.get("node_ip", [""])[0]
            if raw_node_ip:
                node_ip = parse_node_ip(raw_node_ip)
                if not node_ip:
                    self._send_response(400, "node_ip 不是有效的 IP 地址")
                    return

            node_port = None
            raw_node_port = params.get("node_port", [""])[0]
            if raw_node_port:
                node_port = parse_node_port(raw_node_port)
                if not node_port:
                    self._send_response(400, "node_port 不是有效的端口（1-65535）")
                    return

            vless_text = load_vless_text()
            if not vless_text:
                self._send_response(500, "VLESS 链接文件不存在，请先运行 setup.sh")
                return

            try:
                sub_name = load_sub_name()
                config = convert.build_clash_config(vless_text, sub_name, xray_supports_mlkem(), node_ip, node_port)
                # Clash 客户端从 Content-Disposition 读取订阅名称（缺失时会用 URL 路径 "sub"）
                # 使用 RFC 5987 编码以支持中文
                headers = {
                    "Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(sub_name, safe=""),
                }
                self._send_response(200, config, "text/yaml; charset=utf-8", headers)
            except Exception as e:
                sys.stderr.write("生成配置失败: %s\n" % e)
                self._send_response(500, "配置生成失败: %s" % e)
            return

        self._send_response(404, "Not Found")


def main():
    port = load_port()
    server = ThreadingHTTPServer((LISTEN_HOST, port), RequestHandler)
    print("Clash 订阅服务器已启动: http://%s:%s" % (LISTEN_HOST, port), file=sys.stderr)
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
