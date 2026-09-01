#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import socket
import subprocess
import time
from pathlib import Path

import requests
from seleniumbase import SB

APP_URL = os.getenv("JUSTRUNMY_APP_URL", "").strip() or "https://justrunmy.app/panel/application/57562/"
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "screenshots"))
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
RAW_COOKIE = os.getenv("JUSTRUNMY_COOKIE", "").strip()
RAW_PROXY = os.getenv("JUSTRUNMY_PROXY", "").strip()
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


def force_cdp_click_cf(sb):
    """CDP 物理坐标精准击穿（优化版：全 DOM 树 + Shadow DOM 深度递归）"""
    check_token_js = """
    (() => {
        let el = document.querySelector('[name=cf-turnstile-response], [name=g-recaptcha-response]');
        return el ? el.value : '';
    })()
    """
    token = sb.execute_script(check_token_js)
    if token and len(token) > 20:
        print("🎉 Cloudflare 自动检测已通过，无需点击！")
        return True

    print("🎯 启动 CDP 物理坐标定位...")
    get_rect_js = """
    (() => {
        function getAllElements(root) {
            let els = Array.from(root.querySelectorAll('*'));
            let shadowEls = [];
            for (let el of els) {
                if (el.shadowRoot) {
                    shadowEls.push(...getAllElements(el.shadowRoot));
                }
            }
            return els.concat(shadowEls);
        }

        let all = getAllElements(document);

        // 策略 1: 寻找 Cloudflare / Turnstile 相关的 iframe
        for (let el of all) {
            if (el.tagName === 'IFRAME') {
                let src = (el.src || '').toLowerCase();
                let title = (el.title || '').toLowerCase();
                let r = el.getBoundingClientRect();
                if (r.width > 30 && r.height > 20 && r.top > 0) {
                    if (src.includes('cloudflare') || src.includes('challenge') || src.includes('turnstile') ||
                        title.includes('cloudflare') || title.includes('challenge') || title.includes('widget') ||
                        title.includes('human') || title.includes('verify')) {
                        return {left: r.left, top: r.top, width: r.width, height: r.height};
                    }
                }
            }
        }

        // 策略 2: 匹配包含 Verify you are human 文本的容器节点
        for (let el of all) {
            if (el.innerText && el.innerText.includes('Verify you are human')) {
                let r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 20 && r.top > 0) {
                    return {left: r.left, top: r.top, width: r.width, height: r.height};
                }
            }
        }

        // 策略 3: 匹配弹窗中的任何可见 iframe
        for (let el of all) {
            if (el.tagName === 'IFRAME') {
                let r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 30 && r.top > 0) {
                    return {left: r.left, top: r.top, width: r.width, height: r.height};
                }
            }
        }

        // 策略 4: Turnstile 容器 class/id
        for (let el of all) {
            let cls = (el.className || '').toString().toLowerCase();
            let id = (el.id || '').toLowerCase();
            if (cls.includes('turnstile') || id.includes('turnstile') || el.hasAttribute('data-sitekey')) {
                let r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 20 && r.top > 0) {
                    return {left: r.left, top: r.top, width: r.width, height: r.height};
                }
            }
        }

        return null;
    })()
    """

    for attempt in range(1, 5):
        print(f"🔄 正在进行第 {attempt} 次 Cloudflare 验证击穿尝试...")
        
        rect = None
        for _ in range(10):
            rect = sb.execute_script(get_rect_js)
            if rect:
                break
            time.sleep(1)

        if rect and rect['width'] > 0 and rect['height'] > 0:
            click_x = int(rect['left'] + min(30, rect['width'] * 0.15))
            click_y = int(rect['top'] + (rect['height'] / 2))
            print(f"📍 精准锁定复选框坐标: X={click_x}, Y={click_y}")

            try:
                sb.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                    'type': 'mouseMoved', 'x': click_x, 'y': click_y
                })
                time.sleep(0.2)
                sb.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                    'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1
                })
                time.sleep(0.15)
                sb.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                    'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1
                })
                print("💥 拟人化 CDP 物理点击事件已注入！")
            except Exception as e:
                print(f"⚠️ CDP 注入异常: {e}")
        else:
            print("⚠️ JS 节点锁定超时，尝试 UC 盲点击方案...")
            try:
                if hasattr(sb, "uc_gui_click_captcha"):
                    sb.uc_gui_click_captcha()
                else:
                    sb.uc_click("iframe[src*='challenge']")
            except Exception as e:
                print(f"盲击穿方案提示: {e}")

        print("⏳ 正在等待 Cloudflare 响应生成 Token...")
        for i in range(15):
            time.sleep(1)
            token = sb.execute_script(check_token_js)
            if token and len(token) > 20:
                print(f"🎉 验证成功！耗时 {i+1} 秒捕获 Token！")
                return True

        print(f"⚠️ 第 {attempt} 次尝试未成功完成验证，暂停 3 秒后重试...")
        time.sleep(3)

    return False


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

    if RAW_PROXY:
        proxy = RAW_PROXY
        print(f"✅ 使用外部 SOCKS5 代理: {proxy}")
    else:
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

            # 2. 进入应用详情页
            sb.open(APP_URL)
            sb.wait_for_ready_state_complete(timeout=30)
            sb.sleep(5)

            current_url = (sb.get_current_url() or "").lower()
            if "/account/login" in current_url:
                save_shot(sb, "cookie_expired.png")
                raise RuntimeError("Cookie 已失效，页面被重定向到了登录页，请更换最新的 JUSTRUNMY_COOKIE！")

            print(f"✅ 成功进入应用页面: {sb.get_current_url()}")

            # 2.1 自动清理未读消息/系统公告弹窗
            close_btns = [
                "button:contains('Confirm')",
                "button:contains('Close')",
                "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm')]",
                "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]",
                "div[role='dialog'] button"
            ]
            for btn in close_btns:
                try:
                    if sb.is_element_visible(btn):
                        print(f"🔔 检测到未读消息/弹窗，自动点击关闭: {btn}")
                        sb.click(btn)
                        sb.sleep(2)
                        break
                except Exception:
                    pass

            # 2.2 仅当应用真正为 Stopped 状态时，精准匹配并点击独占的 Start 按钮
            page_src = sb.get_page_source()
            if "Application is stopped" in page_src:
                print("▶️ 判定应用确实处于 Stopped 状态，准备启动...")
                exact_start_xpath = "//button[translate(normalize-space(text()), 'START', 'start')='start']"
                try:
                    if sb.is_element_visible(exact_start_xpath):
                        sb.click(exact_start_xpath)
                        print("✅ 已点击 Start 启动按钮")
                        sb.sleep(5)
                except Exception as e:
                    print(f"⚠️ 启动操作提示: {e}")

            # 2.3 路由安全检查：确保当前页面处于主概览页而非 Deployment 页
            target_app_id = APP_URL.rstrip("/").split("/")[-1]
            if target_app_id not in sb.get_current_url():
                print(f"🔄 检测到页面偏离，重新切回应用概览主页: {APP_URL}")
                sb.open(APP_URL)
                sb.wait_for_ready_state_complete(timeout=30)
                sb.sleep(3)

            # 3. 点击 Reset timer 按钮打开弹窗
            reset_xpath = ("//button[contains(translate(normalize-space(.), "
                           "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset timer')]")
            reset = first_visible(sb, [reset_xpath, "button:contains('Reset timer')"], 25)
            if not reset:
                save_shot(sb, "renew_reset_btn_not_found.png")
                raise RuntimeError("找不到 Reset timer 按钮")
            
            sb.scroll_to(reset)
            sb.click(reset)
            print("✅ 已打开续期弹窗，等待动画与 Cloudflare 渲染...")
            sb.sleep(6)
            save_shot(sb, "renew_confirmation_opened.png")

            # 4. 执行 CDP 物理点击击穿
            success = force_cdp_click_cf(sb)
            if not success:
                save_shot(sb, "renew_captcha_failed.png")
                raise RuntimeError("物理击穿未成功生成 Token，暂停提交。")

            # 5. 点击 Just Reset 确认按钮
            confirm_xpath = ("//button[contains(translate(normalize-space(.), "
                             "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'just reset')]")
            confirm_btn = first_visible(sb, [confirm_xpath, "button:contains('Just Reset')"], 10)
            
            if not confirm_btn:
                save_shot(sb, "confirm_btn_not_found.png")
                raise RuntimeError("已通过验证，但未找到 Just Reset 按钮")
            
            print("👉 Token 已就绪，正在点击最终续期确认按钮...")
            sb.click(confirm_btn)
            sb.sleep(5)

            # 6. 判断最终结果
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
