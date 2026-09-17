#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 JUSTRUNMY_PROXY 节点链接解析成 sing-box 客户端配置。

生成结果：本地 socks5 入站（127.0.0.1:SOCKS_PORT）→ 远程节点出站，
浏览器（SeleniumBase）只需连接本地 socks5 即可，无需关心节点协议。

支持的链接格式：
  socks5:// / socks:// / http:// / https://  （兼容旧版用法，可带账号密码）
  ss://  vmess://  vless://  trojan://  hysteria2://(hy2://)  tuic://

环境变量：
  JUSTRUNMY_PROXY  节点链接（必填）
  SOCKS_PORT       本地 socks5 监听端口（默认 51080）
  SOCKS_LISTEN     本地监听地址（默认 127.0.0.1）
  SINGBOX_CONFIG   配置输出路径（默认 singbox/config.json）
"""
import base64
import json
import os
import sys
import urllib.parse

INBOUND_LISTEN = os.getenv("SOCKS_LISTEN") or "127.0.0.1"
INBOUND_PORT = int(os.getenv("SOCKS_PORT") or "51080")
CONFIG_PATH = os.getenv("SINGBOX_CONFIG") or "singbox/config.json"


def log(msg):
    print(f"[singbox-config] {msg}", flush=True)


def fail(msg):
    print(f"[singbox-config] ❌ {msg}", flush=True)
    sys.exit(1)


def b64decode_str(text):
    """宽容的 Base64 解码（兼容 urlsafe 与缺失 padding）"""
    text = text.strip().replace("-", "+").replace("_", "/")
    text += "=" * (-len(text) % 4)
    return base64.b64decode(text).decode("utf-8", "replace")


def as_int(value, default=None):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def as_bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def split_host_port(text, default_port=None):
    """拆 host:port，兼容 IPv6 字面量 [::1]:443"""
    text = text.strip()
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        return host, as_int(rest.lstrip(":"), default_port)
    host, sep, port = text.rpartition(":")
    if not sep:
        return text, default_port
    return host, as_int(port, default_port)


def query_of(url):
    return {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}


def alpn_of(value):
    return [x for x in str(value or "").split(",") if x]


def apply_transport(out, net, path, host):
    """根据传输层类型写入 sing-box transport 字段"""
    net = (net or "tcp").lower()
    if net == "ws":
        transport = {"type": "ws", "path": path or "/"}
        if host:
            transport["headers"] = {"Host": host}
        out["transport"] = transport
    elif net == "grpc":
        out["transport"] = {"type": "grpc", "service_name": path or ""}
    elif net == "httpupgrade":
        transport = {"type": "httpupgrade", "path": path or "/"}
        if host:
            transport["host"] = host
        out["transport"] = transport
    elif net in ("h2", "http"):
        transport = {"type": "http"}
        if host:
            transport["host"] = [host]
        out["transport"] = transport
    return out


# ---------------------------------------------------------------- 各协议解析

def parse_socks_or_http(link):
    url = urllib.parse.urlsplit(link)
    is_socks = url.scheme in ("socks", "socks5", "socks4", "socks4a")
    out = {
        "type": "socks" if is_socks else "http",
        "server": url.hostname,
        "server_port": url.port or (1080 if is_socks else 8080),
    }
    if url.username:
        out["username"] = urllib.parse.unquote(url.username)
    if url.password:
        out["password"] = urllib.parse.unquote(url.password)
    if is_socks:
        out["version"] = "4" if url.scheme.startswith("socks4") else "5"
    if url.scheme == "https":
        out["tls"] = {"enabled": True, "server_name": url.hostname}
    return out


def parse_ss(link):
    body = link.split("://", 1)[1]
    body = body.split("#", 1)[0].split("?", 1)[0]
    if "@" in body:
        userinfo, hostport = body.rsplit("@", 1)
        if ":" not in userinfo:          # SIP002：userinfo 为 base64(method:password)
            userinfo = b64decode_str(userinfo)
    else:                                # 旧格式：整体 base64(method:password@host:port)
        userinfo, _, hostport = b64decode_str(body).rpartition("@")
    method, _, password = userinfo.partition(":")
    server, port = split_host_port(hostport, 8388)
    return {
        "type": "shadowsocks",
        "server": server,
        "server_port": port,
        "method": method.strip(),
        "password": password,
    }


def parse_vmess(link):
    data = json.loads(b64decode_str(link.split("://", 1)[1]))
    server = data.get("add")
    host = data.get("host") or ""
    path = data.get("path") or ""
    out = {
        "type": "vmess",
        "server": server,
        "server_port": as_int(data.get("port"), 443),
        "uuid": data.get("id"),
        "security": (data.get("scy") or "auto").lower() or "auto",
    }
    alter_id = as_int(data.get("aid"), 0)
    if alter_id:
        out["alter_id"] = alter_id

    net = (data.get("net") or "tcp").lower()
    if net == "tcp" and (data.get("type") or "").lower() == "http":
        net = "http"                      # vmess tcp+http 伪装
    apply_transport(out, net, path, host)

    tls_mode = (data.get("tls") or "").lower()
    if tls_mode in ("tls", "reality"):
        tls = {
            "enabled": True,
            "server_name": data.get("sni") or host or server,
            "insecure": as_bool(data.get("allowInsecure") or data.get("allowlnsecure")),
        }
        if data.get("alpn"):
            tls["alpn"] = alpn_of(data.get("alpn"))
        fingerprint = (data.get("fp") or "").lower()
        if tls_mode == "reality":
            tls["reality"] = {
                "enabled": True,
                "public_key": data.get("pbk") or "",
                "short_id": data.get("sid") or "",
            }
        if fingerprint:
            tls["utls"] = {"enabled": True, "fingerprint": fingerprint}
        out["tls"] = tls
    return out


def parse_vless(link):
    url = urllib.parse.urlsplit(link)
    q = query_of(url)
    server = url.hostname
    out = {
        "type": "vless",
        "server": server,
        "server_port": url.port or 443,
        "uuid": urllib.parse.unquote(url.username or ""),
    }
    if q.get("flow"):
        out["flow"] = q["flow"]

    apply_transport(out, q.get("type"), q.get("path"), q.get("host"))

    security = (q.get("security") or "none").lower()
    if security in ("tls", "reality"):
        tls = {
            "enabled": True,
            "server_name": q.get("sni") or server,
            "insecure": as_bool(q.get("allowInsecure")),
        }
        if q.get("alpn"):
            tls["alpn"] = alpn_of(q["alpn"])
        if security == "reality":
            tls["reality"] = {
                "enabled": True,
                "public_key": q.get("pbk") or "",
                "short_id": q.get("sid") or "",
            }
        fingerprint = (q.get("fp") or ("chrome" if security == "reality" else "")).lower()
        if fingerprint:
            tls["utls"] = {"enabled": True, "fingerprint": fingerprint}
        out["tls"] = tls
    return out


def parse_trojan(link):
    url = urllib.parse.urlsplit(link)
    q = query_of(url)
    out = {
        "type": "trojan",
        "server": url.hostname,
        "server_port": url.port or 443,
        "password": urllib.parse.unquote(url.username or ""),
    }
    tls = {
        "enabled": True,
        "server_name": q.get("sni") or url.hostname,
        "insecure": as_bool(q.get("allowInsecure")),
    }
    if q.get("alpn"):
        tls["alpn"] = alpn_of(q["alpn"])
    out["tls"] = tls
    apply_transport(out, q.get("type"), q.get("path"), q.get("host"))
    return out


def parse_hysteria2(link):
    url = urllib.parse.urlsplit(link)
    q = query_of(url)
    password = urllib.parse.unquote(url.username or "") or urllib.parse.unquote(url.password or "")
    out = {
        "type": "hysteria2",
        "server": url.hostname,
        "server_port": url.port or 443,
        "password": password,
    }
    tls = {
        "enabled": True,
        "server_name": q.get("sni") or url.hostname,
        "insecure": as_bool(q.get("insecure") or q.get("allowInsecure")),
    }
    if q.get("alpn"):
        tls["alpn"] = alpn_of(q["alpn"])
    out["tls"] = tls
    if q.get("obfs"):
        out["obfs"] = {
            "type": q["obfs"],
            "password": q.get("obfs-password") or q.get("obfs_password") or "",
        }
    return out


def parse_tuic(link):
    url = urllib.parse.urlsplit(link)
    q = query_of(url)
    out = {
        "type": "tuic",
        "server": url.hostname,
        "server_port": url.port or 443,
        "uuid": urllib.parse.unquote(url.username or ""),
        "password": urllib.parse.unquote(url.password or ""),
    }
    tls = {
        "enabled": True,
        "server_name": q.get("sni") or url.hostname,
        "insecure": as_bool(q.get("allow_insecure") or q.get("insecure") or q.get("allowInsecure")),
    }
    if q.get("alpn"):
        tls["alpn"] = alpn_of(q["alpn"])
    out["tls"] = tls
    if q.get("congestion_control"):
        out["congestion_control"] = q["congestion_control"]
    return out


HANDLERS = {
    "socks": parse_socks_or_http,
    "socks5": parse_socks_or_http,
    "socks4": parse_socks_or_http,
    "socks4a": parse_socks_or_http,
    "http": parse_socks_or_http,
    "https": parse_socks_or_http,
    "ss": parse_ss,
    "vmess": parse_vmess,
    "vless": parse_vless,
    "trojan": parse_trojan,
    "hysteria2": parse_hysteria2,
    "hy2": parse_hysteria2,
    "tuic": parse_tuic,
}


def parse_link(link):
    if "://" not in link:
        fail("JUSTRUNMY_PROXY 格式不正确，需形如 socks5://user:pass@host:port 或 vless://...")
    scheme = link.split("://", 1)[0].strip().lower()
    handler = HANDLERS.get(scheme)
    if not handler:
        fail(f"不支持的代理协议 {scheme}://，支持：{', '.join(sorted(HANDLERS))}")
    out = handler(link)
    out["tag"] = "proxy"
    if not out.get("server"):
        fail(f"未能从链接中解析出服务器地址：{link[:60]}...")
    if not out.get("server_port"):
        fail(f"未能从链接中解析出端口：{link[:60]}...")
    return out


def main():
    raw = (os.getenv("JUSTRUNMY_PROXY") or "").strip()
    if not raw:
        fail("JUSTRUNMY_PROXY 为空，无法生成 sing-box 配置")

    outbound = parse_link(raw)

    config = {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": [{
            "type": "socks",
            "tag": "socks-in",
            "listen": INBOUND_LISTEN,
            "listen_port": INBOUND_PORT,
        }],
        "outbounds": [
            outbound,
            {"type": "direct", "tag": "direct"},
        ],
        "route": {"final": outbound["tag"]},
    }

    path = os.path.abspath(CONFIG_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)

    log(f"节点协议: {outbound['type']}  服务器: {outbound['server']}:{outbound['server_port']}")
    log(f"本地入站: socks5://{INBOUND_LISTEN}:{INBOUND_PORT}")
    log(f"配置已写入: {path}")


if __name__ == "__main__":
    main()
