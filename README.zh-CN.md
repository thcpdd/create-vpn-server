# VLESS-Reality + Clash 订阅一键部署脚本

[English](README.md) | **简体中文**

在 Linux 服务器上一条命令部署 VLESS-Reality 代理，并自动生成可直接使用的 Clash 订阅链接。

## 特性

- **一键部署**：自动安装 Xray、生成密钥、写入配置并启动所有服务
- **VLESS + Reality + XTLS Vision**：TLS 1.3 指纹伪装，无需域名和证书
- **自建订阅服务器**：零依赖的 Python 服务将 VLESS 链接转换为 Clash YAML，无需第三方 subconverter
- **流量信息响应头**：可选支持 `subscription-userinfo`，在 Clash 中展示流量用量和到期时间

## 环境要求

- 使用 systemd 的 Linux 服务器（推荐 Debian / Ubuntu）
- root 权限
- 放行随机代理端口和随机订阅端口的入站流量

> 还没有服务器？可参考 [海外 VPS 云厂商选择](海外VPS云厂商选择.md)。

## 快速使用

以 root 身份运行：

```bash
bash <(curl -sL https://raw.githubusercontent.com/thcpdd/create-vpn-server/main/setup.sh)
```

执行完成后，将输出的 Clash 订阅地址填入客户端：

1. 打开 Clash Verge / Clash Meta 客户端
2. 订阅管理 → 添加 → 粘贴地址 → 更新

## 脚本原理

```
┌──────────────┐   subscription   ┌──────────────────────┐
│ Clash client │ ◄─────────────── │  clash-sub-server    │
│ (your device)│                  │  (Python, rand port) │
└──────┬───────┘                  └──────────┬───────────┘
       │                                     │ convert.py
       │                                     │ VLESS link → Clash YAML
       │       VLESS-Reality       ┌─────────┴──────────┐
       └─────────────────────────► │   Xray (proxy)     │
                                   │   VLESS + Reality  │
                                   └────────────────────┘
```

整个脚本分为 5 个步骤：

### 1. 安装 Xray 并配置 VLESS-Reality

- 安装 [Xray-core](https://github.com/XTLS/Xray-core)（若尚未安装）
- 生成随机端口（10000–49999）、UUID、X25519 密钥对、Short ID
- 从预设列表随机选取一个伪装域名（如 `www.microsoft.com`）
- 写入 `/usr/local/etc/xray/config.json`，验证配置并启动 Xray
- 检测到 `ufw` 或 `firewalld` 时自动放行端口

| 配置 | 说明 |
|------|------|
| `protocol: vless` | 使用 VLESS 协议 |
| `flow: xtls-rprx-vision` | 启用 XTLS Vision 流控 |
| `security: reality` | 使用 Reality 传输层加密 |
| `dest: $SNI:443` | 伪装成访问目标网站的 TLS 握手 |

### 2. 安装订阅服务器

- 安装 Python3（如未安装）
- 下载 `server.py`、`convert.py` 和 `subscription_userinfo.py` 到 `/opt/clash-sub-server/`
- 注册为 systemd 服务（`clash-sub-server`）并设置开机自启

### 3. 生成 VLESS 链接

```
vless://UUID@SERVER_IP:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp#VLESS-Reality
```

### 4. 生成 Clash 订阅地址

使用 VLESS 链接的 MD5 作为访问令牌：

```
http://SERVER_IP:SUB_PORT/sub?token=<md5_token>
```

每次请求时，服务器校验 token，并调用 `convert.py` 动态生成 Clash YAML 配置。

### 5. 测试验证

- 测试订阅服务器接口是否正常响应
- 检查 Xray 端口是否在监听
- 输出订阅地址和备用 VLESS 链接

## 服务器上的部署内容

### 文件

| 路径 | 内容 |
|------|------|
| `/root/vless-link.txt` | VLESS 分享链接（备用） |
| `/root/clash-subscription.txt` | Clash 订阅地址 |
| `/root/clash-token.txt` | 订阅访问令牌 |
| `/usr/local/etc/xray/config.json` | Xray 配置文件 |
| `/opt/clash-sub-server/` | 订阅服务器脚本 |

### 系统服务

| 服务 | 端口 | 说明 |
|------|------|------|
| `xray` | 随机端口 | 代理服务 |
| `clash-sub-server` | 随机（保存在 `/root/clash-sub-port.txt`） | 订阅转换服务 |

### 订阅接口

| 接口 | 说明 |
|------|------|
| `GET /sub?token=<token>` | 返回 Clash YAML 配置 |
| `GET /sub?token=<token>&node_ip=<ip>&node_port=<port>` | 同上，但代理节点的 `server` / `port` 改为 `<ip>`（支持 IPv4/IPv6）/ `<port>`，适用于客户端经中转服务器转发到本机的场景。两个参数均可选，可单独使用 |
| `GET /version` | 健康检查 |

## 流量信息响应头

Clash 会读取订阅链接响应头中的 `subscription-userinfo`，例如：

```
subscription-userinfo: upload=1234; download=2234; total=1024000; expire=2218532293
```

有了它，Clash 就能展示流量使用情况和订阅到期时间。流量单位为字节，到期时间为 Unix 时间戳。

自建服务器的流量统计方式因人而异，需要你自行提供这个值，有两种方式：

**方式一：编写自定义函数**，文件：`/opt/clash-sub-server/subscription_userinfo.py`

```python
def custom_hook() -> str:
    """
    自定义获取流量信息逻辑

    最终需要返回："upload=1234; download=2234; total=1024000; expire=2218532293"
    流量信息(单位: 字节)、到期信息(时间戳)
    """

    return ""
```

在这个函数中编写获取逻辑，返回完整的响应头内容。

**方式二：提供可执行文件**，在 `/opt/clash-sub-server/` 下放置名为 `subinfo` 的可执行文件。当 `custom_hook()` 返回空字符串时，服务器会执行 `./subinfo`，并将其输出作为响应头内容。

修改完成后重启服务：

```bash
sudo systemctl restart clash-sub-server.service
```

## 常见问题

- **客户端无法连接**：除服务器防火墙外，还需在云厂商的安全组中放行代理端口和订阅端口
- **查看订阅服务器日志**：`journalctl -u clash-sub-server -n 50`
- **查看 Xray 日志**：`journalctl -u xray -n 50`

## 技术栈

- **代理协议**：VLESS + Reality + XTLS Vision
- **加密传输**：Reality（TLS 1.3 指纹伪装）
- **订阅转换**：自建 Python 服务器（仅使用标准库）
- **客户端**：Clash Verge / Clash Meta / 任何支持 Clash 订阅的客户端
