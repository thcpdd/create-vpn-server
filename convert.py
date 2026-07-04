"""
VLESS 订阅链接 → Clash Meta 配置转换工具

既可作为命令行工具使用，也可作为模块被 server.py 导入。

用法:
  python convert.py "vless://..."                     # 单节点，输出到 stdout
  python convert.py "vless://..." -o config.yaml      # 保存到文件
  python convert.py -f urls.txt -o config.yaml        # 从文件读取
  python convert.py -u "https://订阅地址" -o config.yaml # 从订阅 URL 读取（兼容 base64）
"""

import argparse
import base64
import re
import sys
import urllib.request
import urllib.parse
from urllib.parse import parse_qs, urlparse

# ──────────────────────────────────────
# Clash 配置文件模板
# ──────────────────────────────────────
CONFIG_TEMPLATE = """port: 7890
socks-port: 7891
allow-lan: true
mode: Rule
log-level: info
external-controller: 127.0.0.1:9090

proxies:
{proxies}

proxy-groups:
  - name: {group_name}
    type: select
    proxies:
{group_proxies}

rules:
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,100.64.0.0/10,DIRECT,no-resolve
  - IP-CIDR6,::1/128,DIRECT,no-resolve
  - IP-CIDR6,fc00::/7,DIRECT,no-resolve
  - IP-CIDR6,fe80::/10,DIRECT,no-resolve
  - IP-CIDR6,fd00::/8,DIRECT,no-resolve
  - GEOSITE,category-ads-all,REJECT
  - GEOSITE,google,{group_name_raw}
  - GEOSITE,cn,DIRECT
  - GEOIP,CN,DIRECT
  - MATCH,{group_name_raw}
"""

DEFAULT_GROUP_NAME = "🚀 代理"


def parse_vless_url(url: str) -> dict:
    """解析单条 VLESS 链接，返回节点信息字典"""
    if not url.startswith("vless://"):
        raise ValueError(f"不是有效的 VLESS 链接: {url[:30]}...")

    parsed = urlparse(url)
    uuid = parsed.username
    server = parsed.hostname
    port = parsed.port
    name = parsed.fragment or f"{server}:{port}"
    params = parse_qs(parsed.query)

    def param(key, default=""):
        v = params.get(key, [default])
        return v[0] if v else default

    return {
        "name": urllib.parse.unquote(name) if name else f"VLESS-{server}",
        "server": server,
        "port": int(port) if port else 443,
        "uuid": uuid,
        "network": param("type", "tcp"),
        "security": param("security", "none"),
        "flow": param("flow", ""),
        "sni": param("sni", ""),
        "fp": param("fp", "chrome"),
        "pbk": param("pbk", ""),
        "sid": param("sid", ""),
    }


def node_to_clash_proxy(node: dict) -> str:
    """将一个节点信息转为 Clash VLESS 代理格式"""
    lines = [
        f'  - name: "{node["name"]}"',
        f'    type: vless',
        f'    server: {node["server"]}',
        f'    port: {node["port"]}',
        f'    uuid: {node["uuid"]}',
        f'    network: {node["network"]}',
    ]

    if node["security"] == "reality":
        lines.append("    tls: true")
        lines.append(f'    flow: {node["flow"]}')
        lines.append(f'    servername: {node["sni"]}')
        lines.append("    reality-opts:")
        lines.append(f'      public-key: {node["pbk"]}')
        lines.append(f'      short-id: "{node["sid"]}"')
        lines.append(f'    client-fingerprint: {node["fp"]}')
    elif node["security"] == "tls":
        lines.append("    tls: true")
        if node["sni"]:
            lines.append(f'    servername: {node["sni"]}')
        if node["flow"]:
            lines.append(f'    flow: {node["flow"]}')

    return "\n".join(lines)


def fetch_subscription(url: str) -> str:
    """从订阅地址获取内容（自动处理 base64）"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "clash-verge/1.0")
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8", errors="ignore").strip()

    try:
        decoded = base64.b64decode(content, validate=True).decode("utf-8", errors="ignore")
        if "vless://" in decoded:
            return decoded
    except Exception:
        pass

    return content


def extract_vless_links(text: str) -> list:
    """从文本中提取所有 VLESS 链接"""
    lines = text.splitlines()
    urls = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        matches = re.findall(r"vless://\S+", line)
        for m in matches:
            m = m.rstrip(",;")
            urls.append(m)
    return urls


def generate_config(nodes: list, group_name: str = DEFAULT_GROUP_NAME) -> str:
    """根据节点列表生成完整 Clash 配置 YAML"""
    if not nodes:
        raise ValueError("没有找到任何 VLESS 节点")

    # 去重（按 name）
    seen = set()
    unique_nodes = []
    for n in nodes:
        if n["name"] not in seen:
            seen.add(n["name"])
            unique_nodes.append(n)

    # 生成 proxies 块
    proxy_lines = "\n".join(node_to_clash_proxy(n) for n in unique_nodes)

    # 生成 proxy-groups 中的节点列表（缩进 6 空格）
    group_lines = "\n".join(f'      - "{n["name"]}"' for n in unique_nodes)
    group_lines += "\n      - DIRECT"

    # YAML 中 group_name 需要加引号（处理包含特殊字符的情况）
    quoted_name = f'"{group_name}"'

    config = CONFIG_TEMPLATE.format(
        proxies=proxy_lines,
        group_name=quoted_name,
        group_name_raw=group_name,
        group_proxies=group_lines,
    )
    return config


def build_clash_config(vless_text: str, sub_name: str = "VPN") -> str:
    """一站式转换：从 VLESS 文本直接生成 Clash YAML 配置

    vless_text: 包含 VLESS 链接的原始文本（可含多条）
    sub_name:   订阅名称，用于 proxy-groups 显示
    """
    links = extract_vless_links(vless_text)
    if not links:
        raise ValueError("未找到任何 VLESS 链接")

    nodes = []
    for link in links:
        nodes.append(parse_vless_url(link))

    group_name = f"🚀 {sub_name}"
    return generate_config(nodes, group_name)


def main():
    parser = argparse.ArgumentParser(
        prog="vless2clash",
        description="VLESS 订阅 → Clash Meta 配置转换",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", "--url", help="订阅地址（URL）")
    group.add_argument("-f", "--file", help="包含 VLESS 链接的文件")
    group.add_argument("link", nargs="?", help="单条 VLESS 链接（直接传入）")
    parser.add_argument("-o", "--output", help="输出文件路径（默认 stdout）")
    parser.add_argument("-n", "--name", default="VPN", help="订阅名称（默认 VPN）")

    args = parser.parse_args()

    # 获取原始内容
    if args.url:
        print(f"正在从订阅地址获取: {args.url}", file=sys.stderr)
        raw = fetch_subscription(args.url)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = args.link

    # 提取 VLESS 链接
    links = extract_vless_links(raw)
    print(f"找到 {len(links)} 个 VLESS 节点", file=sys.stderr)

    # 解析
    nodes = []
    for link in links:
        try:
            node = parse_vless_url(link)
            nodes.append(node)
            print(f"  ✓ {node['name']} ({node['server']}:{node['port']})", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ 解析失败: {e}", file=sys.stderr)

    # 生成配置
    group_name = f"🚀 {args.name}"
    config = generate_config(nodes, group_name)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(config)
        print(f"\n已保存到: {args.output}", file=sys.stderr)
    else:
        print(config)


if __name__ == "__main__":
    main()
