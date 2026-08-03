#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JustRunMy.app 自动续期 (Cookie 免登录版)。"""
import os
import socket
import subprocess
import time
from pathlib import Path

import requests
from seleniumbase import SB

APP_URL = os.getenv("JUSTRUNMY_APP_URL", "").strip() or "https://justrunmy.app/panel/application/39529/"
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
ssh_process = None

# 从环境变量读取 Cookie（建议将长串 Cookie 保存到 GitHub Secrets 中）
RAW_COOKIE = os.getenv("JUSTRUNMY_COOKIE", "").strip()


def notify(message):
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message}, timeout=15,
        ).raise_for_status()
        print("📩 Telegram 通知发送成功！")
    except Exception as exc:
        print(f"⚠️ Telegram 通知失败: {exc}")


def wait_port(port, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def start_proxy():
    global ssh_process
    host = os.getenv("SSH_HOST", "").strip()
    user = os.getenv("SSH_USER", "").strip()
    password = os.getenv("SSH_PASS", "")
    port = os.getenv("SSH_PORT", "22").strip() or "22"
    socks_port = int(os.getenv("SOCKS_PORT", "51080"))
    if not host or not user:
        print("⚠️ 未配置 SSH 代理，使用直连")
        return None
    cmd = ["sshpass", "-p", password, "ssh", "-N", "-D", f"127.0.0.1:{socks_port}",
           "-p", port, "-o", "StrictHostKeyChecking=no", "-o", "ExitOnForwardFailure=yes",
           "-o", "ServerAliveInterval=30", f"{user}@{host}"]
    ssh_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if not wait_port(socks_port):
        err = ssh_process.stderr.read().decode("utf-8", "replace") if ssh_process.stderr else ""
        raise RuntimeError(f"SSH 动态隧道启动失败: {err[-500:]}")
    proxy = f"socks5://127.0.0.1:{socks_port}"
    print(f"✅ SSH 动态隧道已就绪: {proxy}")
    return proxy


def save_shot(sb, name):
    path = SCREENSHOT_DIR / name
    try:
        sb.save_screenshot(str(path))
        print(f"📸 截图已保存: {path}")
    except Exception as exc:
        print(f"⚠️ 截图保存失败: {exc}")


def first_visible(sb, selectors, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for selector in selectors:
            try:
                if sb.is_element_visible(selector):
                    return selector
            except Exception:
                pass
        time.sleep(0.5)
    return None


def main():
    if not RAW_COOKIE:
        raise RuntimeError("缺少 JUSTRUNMY_COOKIE 环境变量，无法进行免登录续期")

    proxy = start_proxy()
    kwargs = dict(uc=True, headless=False, locale="en-US")
    if proxy:
        kwargs["proxy"] = proxy

    with SB(**kwargs) as sb:
        try:
            # 1. 打开主域名以建立域名上下文，然后注入 Cookie
            sb.open("https://justrunmy.app")
            sb.sleep(2)

            for cookie_pair in RAW_COOKIE.split(";"):
                if "=" in cookie_pair:
                    parts = cookie_pair.strip().split("=", 1)
                    if len(parts) == 2:
                        c_name, c_val = parts
                        try:
                            sb.add_cookie({
                                "name": c_name.strip(),
                                "value": c_val.strip(),
                                "domain": "justrunmy.app"
                            })
                        except Exception:
                            pass
            print("🍪 已成功注入 Cookie")

            # 2. 直接打开应用详情页
            sb.open(APP_URL)
            sb.wait_for_ready_state_complete(timeout=30)
            sb.sleep(5)

            current_url = (sb.get_current_url() or "").lower()
            if "/account/login" in current_url:
                save_shot(sb, "cookie_expired.png")
                raise RuntimeError("Cookie 已失效，被重定向到了登录页，请更新 JUSTRUNMY_COOKIE")

            print(f"✅ 成功进入应用页面: {sb.get_current_url()}")

            # 3. 寻找并点击 Reset timer 按钮
            reset_xpath = ("//button[contains(translate(normalize-space(.), "
                           "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset timer')]")
            reset = first_visible(sb, [reset_xpath, "button:contains('Reset timer')", "button:contains('Reset Timer')"], 25)
            if not reset:
                save_shot(sb, "renew_reset_btn_not_found.png")
                raise RuntimeError("找不到 Reset timer 按钮")
            
            sb.scroll_to(reset)
            sb.click(reset)
            sb.sleep(3)
            save_shot(sb, "renew_confirmation_opened.png")

            # 4. 点击弹窗确认 (Just Reset / Confirm)
            confirm_xpath = ("//button[contains(translate(normalize-space(.), "
                             "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'just reset') "
                             "or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm')]")
            confirm_btn = first_visible(sb, [confirm_xpath, "button:contains('Just Reset')", "button:contains('Confirm')"], 10)
            
            if confirm_btn:
                sb.click(confirm_btn)
                sb.sleep(5)
                save_shot(sb, "renew_success.png")
                print("🎉 自动续期指令已成功提交！")
                notify("✅ JustRunMy.app 自动续期成功！")
            else:
                save_shot(sb, "confirm_btn_not_found.png")
                raise RuntimeError("已打开确认弹窗，但未找到确认/Just Reset 按钮")

        except Exception as exc:
            save_shot(sb, "renew_failed.png")
            notify(f"❌ JustRunMy.app 自动续期失败: {exc}")
            raise
        finally:
            if ssh_process and ssh_process.poll() is None:
                ssh_process.terminate()


if __name__ == "__main__":
    main()
