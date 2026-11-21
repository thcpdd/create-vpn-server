# VLESS + Clash 订阅一键部署脚本

[English](README.md) | **简体中文**

在 Linux 服务器上一条命令部署 **VLESS-Reality** 代理（可选同时部署支持套 CDN 的 **VLESS-WS-TLS** 协议），并自动生成可直接使用的 Clash 订阅链接。

## 特性

- **一键部署**：自动安装 Xray、生成密钥、写入配置并启动所有服务
- **VLESS + Reality + XTLS Vision**：TLS 1.3 指纹伪装，无需域名和证书，适合直连
- **VLESS + WebSocket + TLS（可选，支持套 CDN）**：输入域名即可同时部署 WS-TLS 协议与自动续签证书，配合 Cloudflare 等 CDN 隐藏源站 IP，防止或应对服务器 IP 被墙
- **自建订阅服务器**：零依赖的 Python 服务将 VLESS 链接转换为 Clash YAML，无需第三方 subconverter；启用域名后自动提供 HTTPS 订阅地址
- **流量信息响应头**：可选支持 `subscription-userinfo`，在 Clash 中展示流量用量和到期时间

## 环境要求

- 使用 systemd 的 Linux 服务器（推荐 Debian / Ubuntu）
- root 权限
- 放行随机代理端口和随机订阅端口的入站流量
- **若启用 VLESS-WS-TLS（套 CDN 模式）**：需要一个已解析到本机 IP 的域名，且 80 端口空闲并放行入站（用于 `acme.sh` HTTP-01 自动申请证书）

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
│ (your device)│  (HTTP / HTTPS)  │  (Python)            │
└──────┬───────┘                  └──────────┬───────────┘
       │                                     │ convert.py
       │                                     │ VLESS links → Clash YAML
       │  VLESS-Reality (直连)     ┌─────────┴──────────────┐
       ├─────────────────────────► │   Xray (proxy)         │
       │                           │   - VLESS + Reality    │
       │  VLESS-WS-TLS (可选)      │   - VLESS + WS + TLS   │
       └──► [CDN / 直连] ────────► │     (启用域名时开启)   │
                                   └────────────────────────┘
```

整个脚本分为 5 个步骤：

### 1. 安装 Xray 并配置入站协议

脚本运行后会交互式询问：
- **订阅名称**：显示在 Clash 客户端的订阅列表与代理组中（直接回车默认 `VPN`）
- **WS-TLS 域名（可选）**：直接回车跳过则仅部署 VLESS-Reality；输入域名则同时部署 VLESS-WS-TLS

随后执行：
- 安装 [Xray-core](https://github.com/XTLS/Xray-core)（若尚未安装）
- 生成随机 Reality 端口（10000–49999）、UUID、X25519 密钥对、Short ID，并从预设列表随机选取伪装域名（如 `www.microsoft.com`）
- 若输入了 WS-TLS 域名：
  - 为 WS-TLS 和订阅服务优先分配 Cloudflare 支持的 HTTPS 端口（`443, 8443, 2053, 2083, 2087, 2096`，WS-TLS 优先使用 `443`），并生成随机 WebSocket 路径
  - 放行 80 端口，使用 `acme.sh`（Let's Encrypt EC-256，HTTP-01 验证）自动申请证书并安装到 `/usr/local/etc/xray/cert/`，同时配置自动续签和重启钩子
- 写入 `/usr/local/etc/xray/config.json`，验证配置并启动 Xray
- 检测到 `ufw` 或 `firewalld` 时自动放行相关端口

| 协议 | 配置说明 |
|------|----------|
| **VLESS-Reality** | `protocol: vless`、`flow: xtls-rprx-vision`、`security: reality`、`dest: $SNI:443`（TLS 1.3 指纹伪装，适合直连） |
| **VLESS-WS-TLS（可选）** | `protocol: vless`、`network: ws`、`security: tls`、随机 `path`（支持套 Cloudflare 等 CDN 隐藏源站 IP） |

### 2. 安装订阅服务器

- 安装 Python3（如未安装）
- 下载 `server.py` 和 `convert.py` 到 `/opt/clash-sub-server/`
- 若启用了 WS-TLS 域名，复用 `/usr/local/etc/xray/cert/` 证书为订阅服务开启 HTTPS
- 注册为 systemd 服务（`clash-sub-server`）并设置开机自启

### 3. 生成 VLESS 链接

链接保存在 `/root/vless-link.txt`（启用 WS-TLS 时会同时包含两条链接）：

```
vless://UUID@SERVER_IP:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp&headerType=none#VLESS-Reality
vless://UUID@WS_DOMAIN:WS_PORT?encryption=none&security=tls&sni=WS_DOMAIN&fp=chrome&type=ws&host=WS_DOMAIN&path=WS_PATH#VLESS-WS-TLS
```

### 4. 生成 Clash 订阅地址

使用 VLESS-Reality 链接的 MD5 作为访问令牌：

- 仅 VLESS-Reality：`http://SERVER_IP:SUB_PORT/sub?token=<md5_token>`
- 启用 VLESS-WS-TLS：`https://WS_DOMAIN:SUB_PORT/sub?token=<md5_token>`

每次请求时，服务器校验 token，并调用 `convert.py` 将 `/root/vless-link.txt` 中的节点动态转换为 Clash YAML 配置。

### 5. 测试验证

- 测试订阅服务器接口是否正常响应
- 检查 Xray Reality（以及可选的 WS-TLS）端口是否在监听
- 输出订阅地址和备用 VLESS 链接

## 套 CDN 防被墙说明（VLESS-WS-TLS）

VLESS-Reality 适合直连场景，但如果你的 VPS IP 容易被墙、或已经出现连接异常，可以在运行 `setup.sh` 时输入域名启用 **VLESS-WS-TLS**，并通过 Cloudflare 等 CDN 中转流量：

1. **域名解析**：将域名的 `A` / `AAAA` 记录解析到你的 VPS IP。
2. **申请证书阶段**：`setup.sh` 会通过 80 端口执行 HTTP-01 验证申请 Let's Encrypt 证书。运行脚本前请确保 80 端口未被 Nginx/Apache 等占用；如果已经提前在 Cloudflare 开启小黄云代理，请先确认未开启「始终使用 HTTPS（Always Use HTTPS）」，避免验证请求被重定向失败。
3. **开启 CDN 代理（小黄云）**：部署完成后，在 Cloudflare 中开启该域名的代理（橙色云朵），并将 **SSL/TLS 加密模式** 设置为 **完全（Full）** 或 **完全（严格）（Full (strict)）**。
4. **为什么订阅地址也能防被墙**：启用域名后，WS-TLS 代理和订阅服务器都会优先选用 Cloudflare 支持的 HTTPS 端口（`443, 8443, 2053, 2083, 2087, 2096`），并且订阅链接自动切换为 `https://你的域名:订阅端口/sub?token=...`。开启小黄云后，**代理流量**和**订阅拉取**都会走 CDN IP，无需暴露源站 IP。
5. **客户端切换**：Clash 订阅会自动包含 `VLESS-Reality` 和 `VLESS-WS-TLS` 两个节点，直连顺畅时用 Reality，遇到 IP 阻断或限速时切换为 WS-TLS 即可。

## 服务器上的部署内容

### 文件

| 路径 | 内容 |
|------|------|
| `/root/vless-link.txt` | VLESS 分享链接（备用，启用 WS-TLS 时含两条链接） |
| `/root/clash-subscription.txt` | Clash 订阅地址 |
| `/root/clash-token.txt` | 订阅访问令牌 |
| `/root/clash-sub-name.txt` | 订阅名称（默认 `VPN`） |
| `/root/clash-sub-port.txt` | 订阅服务端口 |
| `/root/clash-sub-tls.txt` | 订阅服务是否启用 HTTPS（`1` / `0`） |
| `/root/clash-sub-userinfo.txt` | 流量信息响应头内容（可选，需自行写入） |
| `/usr/local/etc/xray/config.json` | Xray 配置文件 |
| `/usr/local/etc/xray/cert/` | WS-TLS 与订阅服务共用的 TLS 证书（`fullchain.cer`、`private.key`） |
| `/opt/clash-sub-server/` | 订阅服务器脚本 |

### 系统服务

| 服务 | 端口 | 说明 |
|------|------|------|
| `xray` | Reality 随机端口 + 可选 WS-TLS 端口（优先 `443`） | 代理服务 |
| `clash-sub-server` | 随机端口或 CF HTTPS 端口（保存在 `/root/clash-sub-port.txt`） | 订阅转换服务 |

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

自建服务器的流量统计方式因人而异，需要你自行提供这个值：用任意脚本（cron 定时任务、vnstat、云厂商 API 等）把**完整的响应头值**写入 `/root/clash-sub-userinfo.txt`，订阅服务器会在返回订阅时原样带上它。

```bash
echo "upload=1234; download=2234; total=1024000; expire=2218532293" > /root/clash-sub-userinfo.txt
```

- 文件不存在或为空时不发送该响应头；只读取第一个非空行
- 每次请求都会重新读取文件，修改后立即生效，无需重启服务
- 该文件位于 `/root` 下，重新运行 `setup.sh` 不会被覆盖
- Clash 客户端只在更新订阅时读取该响应头，所以写入脚本定时更新即可（如每 5 分钟），无需实时计算

为兼容尽可能多的客户端（Clash Verge 的解析较严格），请按以下格式输出：

- 键使用小写的 `upload`、`download`、`total`、`expire`，用 `; ` 分隔，`=` 两边不要有空格
- 值只能是非负整数：流量单位为字节，到期时间为秒级 Unix 时间戳，不要带小数或单位
- 不需要的字段可以省略，例如不想显示到期时间就不写 `expire`

建议先写临时文件再 `mv` 覆盖，避免读取到写了一半的内容：

```bash
echo "upload=0; download=38225207705; total=214748364800" > /root/clash-sub-userinfo.txt.tmp
mv /root/clash-sub-userinfo.txt.tmp /root/clash-sub-userinfo.txt
```

## 常见问题

- **客户端无法连接**：除服务器防火墙外，还需在云厂商的安全组中放行代理端口（Reality / WS-TLS）和订阅端口
- **WS-TLS 证书申请失败**：确保域名已正确解析到本机 IP、80 端口未被占用且安全组/防火墙已放行 80 端口；若已开启 Cloudflare 代理，请先关闭「始终使用 HTTPS」
- **开启 Cloudflare 小黄云后无法连接**：确认 Cloudflare **SSL/TLS 加密模式** 为 **完全（Full）** 或 **完全（严格）**（不要使用「灵活 Flexible」）
- **查看订阅服务器日志**：`journalctl -u clash-sub-server -n 50`
- **查看 Xray 日志**：`journalctl -u xray -n 50`

## 技术栈

- **代理协议**：VLESS + Reality + XTLS Vision（默认）；VLESS + WebSocket + TLS（可选，支持套 CDN）
- **加密传输**：Reality（TLS 1.3 指纹伪装）/ TLS（Let's Encrypt EC-256，支持 CDN 中转）
- **订阅转换**：自建 Python 服务器（仅使用标准库，支持 HTTP / HTTPS）
- **客户端**：Clash Verge / Clash Meta / 任何支持 Clash 订阅的客户端
