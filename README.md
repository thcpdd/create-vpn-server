# VLESS + Clash Subscription One-Click Setup

**English** | [简体中文](README.zh-CN.md)

Deploy a **VLESS-Reality** proxy on a Linux server with a single command (with optional **VLESS-WS-TLS** for CDN fronting), and get a ready-to-use Clash subscription URL.

## Features

- **One command**: installs Xray, generates keys, writes config, and starts all services
- **VLESS + Reality + XTLS Vision**: TLS 1.3 fingerprint camouflage, no domain or certificate needed
- **VLESS + WebSocket + TLS (optional, CDN-ready)**: provide a domain to deploy WS-TLS with auto-renewing TLS certificates alongside Reality—put it behind a CDN (such as Cloudflare) to hide your origin IP and prevent or recover from IP blocks
- **Built-in subscription server**: a zero-dependency Python service converts the VLESS links into Clash YAML, no third-party subconverter; serves HTTPS over your domain when WS-TLS is enabled
- **Traffic info header**: optional `subscription-userinfo` support so Clash can show usage and expiry

## Requirements

- A Linux server with systemd (Debian / Ubuntu recommended)
- Root privileges
- Inbound access to the proxy port(s) and subscription port
- **If enabling VLESS-WS-TLS (CDN mode)**: a domain resolved to the server IP, with port `80` free and open for `acme.sh` HTTP-01 certificate issuance

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
│ (your device)│  (HTTP / HTTPS)  │  (Python)            │
└──────┬───────┘                  └──────────┬───────────┘
       │                                     │ convert.py
       │                                     │ VLESS links → Clash YAML
       │  VLESS-Reality (direct)   ┌─────────┴──────────────┐
       ├─────────────────────────► │   Xray (proxy)         │
       │                           │   - VLESS + Reality    │
       │  VLESS-WS-TLS (optional)  │   - VLESS + WS + TLS   │
       └──► [CDN / direct] ──────► │     (when domain set)  │
                                   └────────────────────────┘
```

The script runs in 5 steps:

### 1. Install Xray and configure inbound protocols

When started, the script prompts for:
- **Subscription name**: shown in your Clash client's profile list and proxy group (press Enter for `VPN`)
- **WS-TLS domain (optional)**: press Enter to skip (VLESS-Reality only), or enter a domain to deploy VLESS-WS-TLS alongside Reality

Then it performs:
- Install [Xray-core](https://github.com/XTLS/Xray-core) if not already present
- Generate a random Reality port (10000–49999), UUID, X25519 key pair, Short ID, and pick a camouflage domain at random from a preset list (e.g. `www.microsoft.com`)
- If a WS-TLS domain is provided:
  - Prefer Cloudflare-supported HTTPS ports (`443, 8443, 2053, 2083, 2087, 2096`, preferring `443` for WS-TLS) for both WS-TLS and the subscription server, and generate a random WebSocket path
  - Open port `80` and obtain an auto-renewing Let's Encrypt EC-256 certificate via `acme.sh` (HTTP-01), installed to `/usr/local/etc/xray/cert/` with reload hooks
- Write `/usr/local/etc/xray/config.json`, validate it and start Xray
- Open the ports via `ufw` or `firewalld` if either is detected

| Protocol | Description |
|----------|-------------|
| **VLESS-Reality** | `protocol: vless`, `flow: xtls-rprx-vision`, `security: reality`, `dest: $SNI:443` (TLS 1.3 fingerprint camouflage for direct connections) |
| **VLESS-WS-TLS (optional)** | `protocol: vless`, `network: ws`, `security: tls`, random `path` (supports fronting with CDNs like Cloudflare to hide origin IP) |

### 2. Install the subscription server

- Install Python 3 if missing
- Download `server.py` and `convert.py` to `/opt/clash-sub-server/`
- If a WS-TLS domain is enabled, reuse the `/usr/local/etc/xray/cert/` certificate to serve subscriptions over HTTPS
- Register and enable the `clash-sub-server` systemd service

### 3. Generate the VLESS links

Saved to `/root/vless-link.txt` (includes both links when WS-TLS is enabled):

```
vless://UUID@SERVER_IP:PORT?encryption=none&flow=xtls-rprx-vision&security=reality&sni=SNI&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp&headerType=none#VLESS-Reality
vless://UUID@WS_DOMAIN:WS_PORT?encryption=none&security=tls&sni=WS_DOMAIN&fp=chrome&type=ws&host=WS_DOMAIN&path=WS_PATH#VLESS-WS-TLS
```

### 4. Generate the Clash subscription URL

The MD5 of the VLESS-Reality link is used as the access token:

- VLESS-Reality only: `http://SERVER_IP:SUB_PORT/sub?token=<md5_token>`
- With VLESS-WS-TLS: `https://WS_DOMAIN:SUB_PORT/sub?token=<md5_token>`

On each request the server checks the token and calls `convert.py` to build the Clash YAML from `/root/vless-link.txt` on the fly.

### 5. Verify

- Check that the subscription server responds
- Check that Xray is listening on the Reality port (and WS-TLS port if enabled)
- Print the subscription URL and the backup VLESS links

## Using a CDN to Prevent IP Blocking (VLESS-WS-TLS)

VLESS-Reality is ideal for direct connections, but if your VPS IP is prone to blocking—or already blocked—you can enter a domain during `setup.sh` to enable **VLESS-WS-TLS** and route traffic through a CDN such as Cloudflare:

1. **DNS record**: Point your domain's `A` / `AAAA` record to your VPS IP.
2. **Certificate issuance**: `setup.sh` uses port `80` (HTTP-01) to obtain a Let's Encrypt certificate. Ensure port `80` is not occupied by Nginx/Apache; if Cloudflare proxy is already enabled, make sure **Always Use HTTPS** is turned off during initial issuance.
3. **Enable CDN proxy**: After deployment, enable Cloudflare's proxy (orange cloud) on the domain and set **SSL/TLS encryption mode** to **Full** or **Full (strict)**.
4. **Subscription URL is also CDN-protected**: When a domain is enabled, both WS-TLS and the subscription server prefer Cloudflare-supported HTTPS ports (`443, 8443, 2053, 2083, 2087, 2096`), and the subscription URL switches to `https://YOUR_DOMAIN:SUB_PORT/sub?token=...`. With Cloudflare proxy enabled, both **proxy traffic** and **subscription updates** go through CDN IPs without exposing your server IP.
5. **Switching nodes in Clash**: The Clash subscription includes both `VLESS-Reality` and `VLESS-WS-TLS` nodes so you can use Reality for direct speed or switch to WS-TLS whenever your IP is throttled or blocked.

## Server Layout

### Files

| Path | Content |
|------|---------|
| `/root/vless-link.txt` | VLESS share link(s) (backup; contains two links when WS-TLS is enabled) |
| `/root/clash-subscription.txt` | Clash subscription URL |
| `/root/clash-token.txt` | Subscription access token |
| `/root/clash-sub-name.txt` | Subscription name (default `VPN`) |
| `/root/clash-sub-port.txt` | Subscription server port |
| `/root/clash-sub-tls.txt` | Whether HTTPS is enabled on the subscription server (`1` / `0`) |
| `/root/clash-sub-userinfo.txt` | Traffic info header value (optional, written by you) |
| `/usr/local/etc/xray/config.json` | Xray config |
| `/usr/local/etc/xray/cert/` | TLS certificate (`fullchain.cer`, `private.key`) shared by WS-TLS and the subscription server |
| `/opt/clash-sub-server/` | Subscription server scripts |

### Services

| Service | Port | Description |
|---------|------|-------------|
| `xray` | Random Reality port + optional WS-TLS port (prefers `443`) | Proxy service |
| `clash-sub-server` | Random or CF HTTPS port (saved in `/root/clash-sub-port.txt`) | Subscription service |

### Subscription endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /sub?token=<token>` | Returns the Clash YAML config |
| `GET /sub?token=<token>&reality_server=<addr>&reality_port=<port>&ws_server=<addr>&ws_port=<port>` | Same as above, with per-node endpoint overrides (all optional and composable):<br>- `reality_server` / `reality_port`: override `server` / `port` of Reality nodes (IPv4/IPv6 or domain), for connecting through a relay server<br>- `ws_server` / `ws_port`: override `server` / `port` of WS-TLS nodes (preferred IP or domain, keeping the original `servername` and `Host`), for CDN preferred endpoints |
| `GET /version` | Health check |

## Traffic Info Header

Clash reads the `subscription-userinfo` response header of a subscription URL, for example:

```
subscription-userinfo: upload=1234; download=2234; total=1024000; expire=2218532293
```

With it, Clash can show traffic usage and the subscription expiry date. Traffic is in bytes, expiry is a Unix timestamp.

Every self-hosted server tracks traffic differently, so you need to provide this value yourself: use any script (a cron job, vnstat, your cloud provider's API, ...) to write the **full header value** to `/root/clash-sub-userinfo.txt`. The subscription server sends it as-is with every subscription response.

```bash
echo "upload=1234; download=2234; total=1024000; expire=2218532293" > /root/clash-sub-userinfo.txt
```

- If the file is missing or empty, the header is not sent. Only the first non-empty line is used
- The file is re-read on every request, so changes take effect immediately without a restart
- The file lives in `/root`, so re-running `setup.sh` won't overwrite it
- Clash clients only read this header when they update the subscription, so updating the file periodically (e.g. every 5 minutes) is enough

To stay compatible with as many clients as possible (Clash Verge parses strictly), use this format:

- Lowercase keys `upload`, `download`, `total`, `expire`, separated by `; `, with no spaces around `=`
- Values must be non-negative integers: traffic in bytes, expiry as a Unix timestamp in seconds, no decimals or units
- Omit fields you don't need, e.g. leave out `expire` if you don't want an expiry date shown

Write to a temp file and `mv` it into place so the server never reads a half-written file:

```bash
echo "upload=0; download=38225207705; total=214748364800" > /root/clash-sub-userinfo.txt.tmp
mv /root/clash-sub-userinfo.txt.tmp /root/clash-sub-userinfo.txt
```

## Troubleshooting

- **Client cannot connect**: besides the server firewall, make sure your cloud provider's security group allows the proxy port(s) (Reality / WS-TLS) and the subscription port
- **WS-TLS certificate issuance fails**: ensure your domain resolves to the server IP, port `80` is free and allowed through the firewall/security group, and if Cloudflare proxy is already enabled, turn off **Always Use HTTPS** during issuance
- **Cannot connect after enabling Cloudflare proxy (orange cloud)**: set Cloudflare **SSL/TLS encryption mode** to **Full** or **Full (strict)** (do not use Flexible)
- **Subscription server logs**: `journalctl -u clash-sub-server -n 50`
- **Xray logs**: `journalctl -u xray -n 50`

## Tech Stack

- **Proxy protocol**: VLESS + Reality + XTLS Vision (default); VLESS + WebSocket + TLS (optional, CDN-ready)
- **Transport security**: Reality (TLS 1.3 fingerprint camouflage) / TLS (Let's Encrypt EC-256, CDN-compatible)
- **Subscription conversion**: self-hosted Python server (standard library only, HTTP / HTTPS)
- **Clients**: Clash Verge / Clash Meta / any client supporting Clash subscriptions
