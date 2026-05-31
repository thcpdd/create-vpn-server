# VLESS-Reality + Clash 订阅一键部署脚本

在 Linux 服务器上一键部署 VLESS-Reality 代理，并自动生成 Clash 订阅链接。

## 快速使用

在 root 权限下直接运行以下命令即可：

```bash
bash <(curl -sL https://raw.githubusercontent.com/thcpdd/self-vpn/main/setup.sh)
```

> 注意：需以 root 身份运行，脚本会自动完成所有配置。

## 脚本原理

整个脚本分为 5 个步骤，在服务器上搭建了一套完整的代理 + 订阅转换链路：

```
┌─────────────┐     VLESS-Reality     ┌──────────────────────┐
│  Clash 客户端 │ ◄──── 订阅拉取 ──── │  clash-sub-server    │
│  (你的电脑)   │                      │  (Python, 端口25500)  │
└─────────────┘                      └──────────┬───────────┘
                                                │
                                       convert.py 动态转换
                                                │
                                       VLESS 链接 (原始格式)
                                                │
                                       ┌────────▼─────────┐
                                       │  Xray (代理服务)   │
                                       │  VLESS + Reality  │
                                       └──────────────────┘
```

### 脚本执行流程

#### 1. 安装 Xray 并配置 VLESS-Reality

- 安装 [Xray-core](https://github.com/XTLS/Xray-core)（若尚未安装）
- 生成随机端口（10000-50000）、UUID、X25519 密钥对、Short ID
- 从预设列表随机选取一个伪装域名（如 `www.microsoft.com`）
- 写入 Xray 配置文件 `/usr/local/etc/xray/config.json`
- 验证配置并启动 Xray 服务

关键配置项：

| 配置 | 说明 |
|------|------|
| `protocol: vless` | 使用 VLESS 协议 |
| `flow: xtls-rprx-vision` | 启用 XTLS Vision 流控 |
| `security: reality` | 使用 Reality 传输层加密 |
| `dest: $SNI:443` | 伪装成访问目标网站的 TLS 握手 |

#### 2. 安装订阅服务器

- 安装 Python3（如未安装）
- 下载 `server.py` 和 `convert.py` 到 `/opt/clash-sub-server/`
- 注册为 systemd 服务（`clash-sub-server`）并自启

自建的 Python 服务器将 VLESS 链接动态转换为 Clash YAML 订阅格式，替代第三方 subconverter。

#### 3. 生成 VLESS 链接

拼接标准 VLESS-Reality 分享链接格式：

```
vless://UUID@SERVER_IP:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp#VLESS-Reality
```

#### 4. 生成 Clash 订阅地址

使用 VLESS 链接的 MD5 作为访问令牌，生成订阅地址：

```
http://SERVER_IP:25500/sub?token=<md5_token>
```

服务器根据 token 匹配请求，动态调用 convert.py 返回 Clash YAML 配置。

#### 5. 测试验证

- 测试订阅服务器接口是否正常响应
- 检查 Xray 端口是否监听
- 输出订阅地址和备用 VLESS 链接

## 输出文件

| 文件 | 内容 |
|------|------|
| `/root/vless-link.txt` | VLESS 分享链接（备用） |
| `/root/clash-subscription.txt` | Clash 订阅地址 |

## 系统服务

| 服务 | 端口 | 说明 |
|------|------|------|
| `xray` | 随机端口 | 代理服务 |
| `clash-sub-server` | 25500 | 订阅转换服务 |

## 技术栈

- **代理协议**: VLESS + Reality + XTLS Vision
- **加密传输**: Reality (TLS 1.3 指纹伪装)
- **订阅转换**: 自建 Python 服务器 (server.py + convert.py)
- **客户端**: Clash Verge / Clash Meta / 任何支持 Clash 订阅的客户端

## 流量信息响应头

Clash 会识别订阅链接的响应头是中否包含`subscription-userinfo`。

例如：

```
subscription-userinfo: upload=1234; download=2234; total=1024000; expire=2218532293
```

这个响应头可以在 Clash 中展示流量的使用情况以及订阅的到期时间。

如果是自己用服务器搭建的 VPN，那每个人都有自己的流量信息获取方式。

文件：`subscription_userinfo.py`

```python
def custom_hook() -> str:
    """
    自定义获取流量信息逻辑

    最终需要返回："upload=1234; download=2234; total=1024000; expire=2218532293"
    流量信息(单位: 字节)、到期信息(时间戳)
    """

    return ""
```

你需要编写这个函数的逻辑，最终返回完整的响应头。

编写完以后重启后端服务：

```bash
sudo systemctl restart clash-sub-server.service
```
