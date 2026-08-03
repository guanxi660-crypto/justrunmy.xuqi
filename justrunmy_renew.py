#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JustRunMy.app 自动登录与续期。"""
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import requests
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
APP_URL = os.getenv("JUSTRUNMY_APP_URL", "https://justrunmy.app/panel/application/39529/")
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
ssh_process = None


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
    email = os.getenv("JUSTRUNMY_EMAIL", "").strip()
    password = os.getenv("JUSTRUNMY_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("缺少 JUSTRUNMY_EMAIL 或 JUSTRUNMY_PASSWORD")
    proxy = start_proxy()
    kwargs = dict(uc=True, headless=False, locale="en-US")
    if proxy:
        kwargs["proxy"] = proxy

    with SB(**kwargs) as sb:
        try:
            sb.open(LOGIN_URL)
            sb.sleep(3)
            email_sel = first_visible(sb, ["input[type='email']", "input[name='Email']", "#Email"])
            pass_sel = first_visible(sb, ["input[type='password']", "input[name='Password']", "#Password"])
            if not email_sel or not pass_sel:
                raise RuntimeError("登录页面未找到邮箱或密码输入框")
            sb.type(email_sel, email)
            sb.type(pass_sel, password)
            try:
                sb.uc_gui_click_captcha()
                sb.sleep(2)
            except Exception as exc:
                print(f"⚠️ Turnstile 自动点击未执行或页面无需验证: {exc}")
            submit = first_visible(sb, ["button[type='submit']", "input[type='submit']"], 10)
            if not submit:
                raise RuntimeError("未找到登录按钮")
            sb.click(submit)
            sb.sleep(5)
            sb.open(APP_URL)
            sb.sleep(5)

            # XPath 1.0 translate() 实现真正的不区分大小写匹配。
            reset_xpath = ("//button[contains(translate(normalize-space(.), "
                           "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset timer')]")
            reset = first_visible(sb, [reset_xpath, "button:contains('Reset timer')", "button:contains('Reset Timer')"], 25)
            if not reset:
                save_shot(sb, "renew_reset_btn_not_found.png")
                raise RuntimeError("找不到 Reset timer 按钮")
            sb.scroll_to(reset)
            sb.click(reset)
            sb.sleep(4)
            save_shot(sb, "renew_success.png")
            print("✅ 已点击 Reset timer，续期流程完成")
            notify("✅ JustRunMy.app 自动续期完成")
        except Exception as exc:
            save_shot(sb, "renew_failed.png")
            notify(f"❌ JustRunMy.app 自动续期失败: {exc}")
            raise
        finally:
            if ssh_process and ssh_process.poll() is None:
                ssh_process.terminate()


if __name__ == "__main__":
    main()
