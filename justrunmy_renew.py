#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
RAW_COOKIE = os.getenv("JUSTRUNMY_COOKIE", "").strip()
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
    if not RAW_COOKIE:
        raise RuntimeError("缺少 JUSTRUNMY_COOKIE 环境变量，无法注入 Cookie 登录！")

    proxy = start_proxy()
    kwargs = dict(uc=True, headless=False, locale="en-US")
    if proxy:
        kwargs["proxy"] = proxy

    with SB(**kwargs) as sb:
        try:
            sb.maximize_window()
            # 1. 打开首页并注入 Cookie
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

            # 2. 直奔应用详情页
            sb.open(APP_URL)
            sb.wait_for_ready_state_complete(timeout=30)
            sb.sleep(5)

            current_url = (sb.get_current_url() or "").lower()
            if "/account/login" in current_url:
                save_shot(sb, "cookie_expired.png")
                raise RuntimeError("Cookie 已失效，页面被重定向到了登录页，请更换最新的 JUSTRUNMY_COOKIE！")

            print(f"✅ 成功进入应用页面: {sb.get_current_url()}")

            # 3. 点击 Reset timer 按钮打开弹窗
            reset_xpath = ("//button[contains(translate(normalize-space(.), "
                           "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset timer')]")
            reset = first_visible(sb, [reset_xpath, "button:contains('Reset timer')"], 25)
            if not reset:
                save_shot(sb, "renew_reset_btn_not_found.png")
                raise RuntimeError("找不到 Reset timer 按钮")
            
            sb.scroll_to(reset)
            sb.click(reset)
            print("✅ 已打开续期弹窗，等待动画加载...")
            sb.sleep(3)
            save_shot(sb, "renew_confirmation_opened.png")

            # 4. 【核心攻坚】切入 iframe 内部点击验证框
            print("⏳ 正在定位 Cloudflare iframe 框架...")
            iframe_xpath = "//iframe[contains(@src, 'challenges.cloudflare.com') or contains(@title, 'Cloudflare')]"
            
            # 等待 iframe 渲染
            sb.wait_for_element_present(iframe_xpath, timeout=15)
            
            # 切换到 iframe 内部
            sb.switch_to_frame(iframe_xpath)
            print("🎯 成功切入 Cloudflare iframe 内部！")
            sb.sleep(1)

            # 点击 iframe 内部的复选框区域
            cb_selectors = ["#challenge-stage", "input[type='checkbox']", ".mark", "body"]
            clicked_cf = False
            for cb in cb_selectors:
                try:
                    if sb.is_element_visible(cb):
                        sb.click(cb)
                        print(f"👆 成功点击 iframe 内的验证节点: {cb}")
                        clicked_cf = True
                        break
                except Exception:
                    pass
            
            if not clicked_cf:
                # 备用：直接对 iframe 触发 UC 点击
                sb.switch_to_parent_frame()
                sb.uc_gui_click_captcha()
            else:
                sb.switch_to_parent_frame()

            # 5. 轮询检测 Token 状态
            print("⏳ 正在等待 Cloudflare 完成鉴权生成 Token...")
            token_acquired = False
            for i in range(20):
                token = sb.execute_script(
                    "let el = document.querySelector('[name=cf-turnstile-response]'); return el ? el.value : '';"
                )
                if token and len(token) > 20:
                    print(f"🎉 成功获取到验证 Token (耗时 {i+1} 秒)！")
                    token_acquired = True
                    break
                sb.sleep(1)

            if not token_acquired:
                save_shot(sb, "renew_captcha_failed.png")
                raise RuntimeError("Cloudflare 验证未通过：未检测到生成的 Token，暂停提交以避免失败。")

            # 6. 点击 Just Reset 确认按钮
            confirm_xpath = ("//button[contains(translate(normalize-space(.), "
                             "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'just reset')]")
            confirm_btn = first_visible(sb, [confirm_xpath, "button:contains('Just Reset')"], 10)
            
            if not confirm_btn:
                save_shot(sb, "confirm_btn_not_found.png")
                raise RuntimeError("已通过验证，但未找到 Just Reset 按钮")
            
            print("👉 Token 已就绪，正在点击最终续期确认按钮...")
            sb.click(confirm_btn)
            sb.sleep(5)

            # 7. 判断最终结果
            page_text = sb.get_page_source()
            if "Please complete the captcha verification" in page_text:
                save_shot(sb, "renew_captcha_failed.png")
                raise RuntimeError("续期失败：服务器校验 Token 失败。")

            save_shot(sb, "renew_success.png")
            print("🎉 自动续期成功！")
            notify("✅ JustRunMy.app 自动续期成功！")

        except Exception as exc:
            save_shot(sb, "renew_failed.png")
            notify(f"❌ JustRunMy.app 自动续期失败: {exc}")
            raise
        finally:
            if ssh_process and ssh_process.poll() is None:
                ssh_process.terminate()


if __name__ == "__main__":
    main()
