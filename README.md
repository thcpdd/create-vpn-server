# VLESS-Reality + Clash Subscription One-Click Setup

**English** | [简体中文](README.zh-CN.md)

Deploy a VLESS-Reality proxy on a Linux server with a single command, and get a ready-to-use Clash subscription URL.

## Features

- **One command**: installs Xray, generates keys, writes config, and starts all services
- **VLESS + Reality + XTLS Vision**: TLS 1.3 fingerprint camouflage, no domain or certificate needed
- **Built-in subscription server**: a zero-dependency Python service converts the VLESS link into Clash YAML, no third-party subconverter
- **Traffic info header**: optional `subscription-userinfo` support so Clash can show usage and expiry

## Requirements

- A Linux server with systemd (Debian / Ubuntu recommended)
- Root privileges
- Inbound access to the random proxy port and the random subscription port

> Choosing a VPS? See the [overseas VPS provider guide](海外VPS云厂商选择.md) (Chinese only).

## Quick Start

Run as root:

```bash
bash <(curl -sL https://raw.githubusercontent.com/thcpdd/create-vpn-server/main/setup.sh)
```

When it finishes, copy the printed Clash subscription URL into your client:

1. Open Clash Verge / Clash Meta
2. Profiles → Import / New → paste the URL → Update

## How It Works

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

The script runs in 5 steps:

### 1. Install Xray and configure VLESS-Reality

- Install [Xray-core](https://github.com/XTLS/Xray-core) if not already present
- Generate a random port (10000–49999), UUID, X25519 key pair and Short ID
- Pick a camouflage domain at random from a preset list (e.g. `www.microsoft.com`)
- Write `/usr/local/etc/xray/config.json`, validate it and start Xray
- Open the ports via `ufw` or `firewalld` if either is detected

| Setting | Description |
|---------|-------------|
| `protocol: vless` | VLESS protocol |
| `flow: xtls-rprx-vision` | XTLS Vision flow control |
| `security: reality` | Reality transport security |
| `dest: $SNI:443` | TLS handshake disguised as the target website |

### 2. Install the subscription server

- Install Python 3 if missing
- Download `server.py`, `convert.py` and `subscription_userinfo.py` to `/opt/clash-sub-server/`
- Register and enable the `clash-sub-server` systemd service

### 3. Generate the VLESS link

```
vless://UUID@SERVER_IP:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp#VLESS-Reality
```

### 4. Generate the Clash subscription URL

The MD5 of the VLESS link is used as the access token:

```
http://SERVER_IP:SUB_PORT/sub?token=<md5_token>
```

On each request the server checks the token and calls `convert.py` to build the Clash YAML on the fly.

### 5. Verify

- Check that the subscription server responds
- Check that Xray is listening on its port
- Print the subscription URL and the backup VLESS link

## Server Layout

### Files

| Path | Content |
|------|---------|
| `/root/vless-link.txt` | VLESS share link (backup) |
| `/root/clash-subscription.txt` | Clash subscription URL |
| `/root/clash-token.txt` | Subscription access token |
| `/usr/local/etc/xray/config.json` | Xray config |
| `/opt/clash-sub-server/` | Subscription server scripts |

### Services

| Service | Port | Description |
|---------|------|-------------|
| `xray` | random | Proxy service |
| `clash-sub-server` | Random (saved in `/root/clash-sub-port.txt`) | Subscription service |

### Subscription endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /sub?token=<token>` | Returns the Clash YAML config |
| `GET /sub?token=<token>&node_ip=<ip>&node_port=<port>` | Same as above, but the proxy `server` / `port` are set to `<ip>` (IPv4/IPv6) / `<port>`. Use it when clients connect through a relay server that forwards to this server. Both parameters are optional and can be used separately |
| `GET /version` | Health check |

## Traffic Info Header

Clash reads the `subscription-userinfo` response header of a subscription URL, for example:

```
subscription-userinfo: upload=1234; download=2234; total=1024000; expire=2218532293
```

With it, Clash can show traffic usage and the subscription expiry date. Traffic is in bytes, expiry is a Unix timestamp.

Every self-hosted server tracks traffic differently, so you need to provide this value yourself. There are two ways:

**Option 1: write a custom hook** in `/opt/clash-sub-server/subscription_userinfo.py`:

```python
def custom_hook() -> str:
    """
    自定义获取流量信息逻辑

    最终需要返回："upload=1234; download=2234; total=1024000; expire=2218532293"
    流量信息(单位: 字节)、到期信息(时间戳)
    """

    return ""
```

Return the full header value from this function.

**Option 2: provide an executable** named `subinfo` in `/opt/clash-sub-server/`. If `custom_hook()` returns an empty string, the server runs `./subinfo` and uses its output as the header value.

Restart the service after making changes:

```bash
sudo systemctl restart clash-sub-server.service
```

## Troubleshooting

- **Client cannot connect**: besides the server firewall, make sure your cloud provider's security group allows the proxy port and the subscription port
- **Subscription server logs**: `journalctl -u clash-sub-server -n 50`
- **Xray logs**: `journalctl -u xray -n 50`

## Tech Stack

- **Proxy protocol**: VLESS + Reality + XTLS Vision
- **Transport security**: Reality (TLS 1.3 fingerprint camouflage)
- **Subscription conversion**: self-hosted Python server (standard library only)
- **Clients**: Clash Verge / Clash Meta / any client supporting Clash subscriptions
