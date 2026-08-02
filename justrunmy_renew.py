#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import socket
import signal
import subprocess
import requests
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
DOMAIN    = "justrunmy.app"

# ============================================================
#  环境变量与全局变量
# ============================================================
EMAIL        = os.environ.get("JUSTRUNMY_EMAIL")
PASSWORD     = os.environ.get("JUSTRUNMY_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID")
SSH_HOST     = os.environ.get("SSH_HOST", "")
SSH_PORT     = int(os.environ.get("SSH_PORT", "22"))
SSH_USER     = os.environ.get("SSH_USER", "")
SSH_PASS     = os.environ.get("SSH_PASS", "")
SOCKS_PORT = int(os.environ.get("SOCKS_PORT", "51080"))

if not EMAIL or not PASSWORD:
    print("❌ 致命错误：未找到 JUSTRUNMY_EMAIL 或 JUSTRUNMY_PASSWORD 环境变量！")
    print("💡 请检查 GitHub Repository Secrets 是否配置正确。")
    sys.exit(1)

DYNAMIC_APP_NAME = "未知应用"
CURRENT_IP_INFO = "未知 IP"

# ============================================================
#  SSH 隧道直连代理模块
# ============================================================
class SshProxy:
    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.proc = None

    def start(self):
        if not self.host or not self.user:
            print("⚠️ 未提供完整的 SSH 配置")
            return False
        print("📡 正在建立 SSH 动态直连隧道 (SOCKS5 代理代理映射)...")
        print(f"🔗 目标节点: {self.user}@{self.host}:{self.port}")
        cmd = [
            "sshpass", "-p", self.password, "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=15",
            "-N", "-D", f"127.0.0.1:{SOCKS_PORT}",
            "-p", str(self.port), f"{self.user}@{self.host}"
        ]
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, text=True
        )
        for _ in range(30):
            time.sleep(1)
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", SOCKS_PORT)) == 0:
                    print("✅ SSH 动态直连隧道已就绪！")
                    break
        else:
            print("❌ SSH 隧道启动失败或超时，请检查您的主机 Secrets 配置以及网络连通性。")
            try:
                _, stderr = self.proc.communicate(timeout=1)
                if stderr:
                    print(f"SSH 错误信息: {stderr}")
            except Exception:
                pass
            return False
        time.sleep(2)
        return True

    def stop(self):
        if self.proc:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                print("🛑 SSH 隧道已安全关闭")
            except Exception:
                pass

    @property
    def proxy(self):
        return f"socks5://127.0.0.1:{SOCKS_PORT}"


def get_proxy_manager() -> Optional[SshProxy]:
    """根据环境变量判断是否需要启动并挂载 SSH 隧道代理"""
    if SSH_HOST and SSH_USER:
        return SshProxy(SSH_HOST, SSH_PORT, SSH_USER, SSH_PASS)
    return None


def mask_ip(ip: str) -> str:
    """脱敏 IP 地址"""
    if not ip or "." not in ip:
        return ip
    return ip.rsplit(".", 1)[0] + ".***"


def mask_email(email: str) -> str:
    """脱敏邮箱地址"""
    if "@" not in email:
        if len(email) <= 2:
            return email
        return email[0] + "*" * (len(email) - 2) + email[-1]
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def check_ip(proxy: Optional[str] = None) -> str:
    """检查落地 IP，明确指出是否使用了代理"""
    try:
        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}
        r = requests.get(
            "http://ip-api.com/json/?fields=status,query,countryCode",
            proxies=proxies, timeout=30
        ).json()
        if r.get("status") == "success":
            ip_str = f"{mask_ip(r['query'])} ({r['countryCode']})"
            mode = "✅ SSH 代理" if proxy else "⚠️ 直连"
            return f"{ip_str} [{mode}]"
    except Exception:
        pass
    mode = "✅ SSH 代理" if proxy else "⚠️ 直连"
    return f"未知 IP [{mode}]"


def start_proxy_with_retry(max_retries=3):
    """启动代理，失败时重试"""
    proxy_manager = get_proxy_manager()
    proxy_url = None
    if not proxy_manager:
        return None, None
    for attempt in range(1, max_retries + 1):
        print(f"🔄 尝试启动 SSH 动态隧道 ({attempt}/{max_retries})...")
        if proxy_manager.start():
            proxy_url = proxy_manager.proxy
            print(f"✅ 代理已成功挂载：{proxy_url}")
            return proxy_manager, proxy_url
        else:
            if attempt < max_retries:
                print("⏳ 等待 5 秒后重试...")
                time.sleep(5)
            else:
                print("⚠️ SSH 隧道多次启动失败，继续使用默认环境直连模式。")
    return None, None

# ============================================================
#  Telegram 推送模块
# ============================================================
def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return
    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    masked = mask_email(EMAIL)
    account_line = f"<a href='tg://user?id={TG_CHAT_ID}'>{masked}</a>"
    text = (
        f"🎮 justrunmy.app 续期报告\n🖥 {DYNAMIC_APP_NAME}\n"
        f"👤 账号: {account_line}\n"
        f"🌐 IP: {CURRENT_IP_INFO}\n"
        f"🕐 运行时间: {current_time_str}\n"
        f"{status_icon} {status_text}\n"
        f"⏱️ 剩余: {time_left}"
    )
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("  📩 Telegram 通知发送成功！")
        else:
            print(f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")

# ============================================================
#  页面注入脚本
# ============================================================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {sx: window.screenX || 0, sy: window.screenY || 0, oh: window.outerHeight, ih: window.innerHeight};
})()
"""

# ============================================================
#  底层输入工具与多重行为模拟引擎
# ============================================================
def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{ nativeInputValueSetter.call(el, "{safe_text}"); }}
        else {{ el.value = "{safe_text}"; }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)


def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _xdotool_click(x: int, y: int, penetration_mode: bool = False):
    _activate_window()
    import random
    if penetration_mode:
        print("  ⚡ [底层击穿模式激活] 正在为您模拟人类鼠标变速平滑轨迹滑动...")
        try:
            res = subprocess.run(["xdotool", "getmouselocation", "--shell"], capture_output=True, text=True, timeout=2)
            lines = res.stdout.strip().split("\n")
            curr_x = int(lines[0].split("=")[1])
            curr_y = int(lines[1].split("=")[1])
        except Exception:
            curr_x, curr_y = 0, 0
        target_x = x + random.randint(-4, 4)
        target_y = y + random.randint(-4, 4)
        steps = random.randint(15, 25)
        for i in range(1, steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)
            next_x = int(curr_x + (target_x - curr_x) * t + random.randint(-1, 1))
            next_y = int(curr_y + (target_y - curr_y) * t + random.randint(-1, 1))
            subprocess.run(["xdotool", "mousemove", str(next_x), str(next_y)], stderr=subprocess.DEVNULL)
            time.sleep(random.uniform(0.01, 0.02))
        subprocess.run(["xdotool", "mousemove", str(target_x), str(target_y)], stderr=subprocess.DEVNULL)
        time.sleep(random.uniform(0.12, 0.25))
        subprocess.run(["xdotool", "mousedown", "1"], stderr=subprocess.DEVNULL)
        time.sleep(random.uniform(0.07, 0.16))
        subprocess.run(["xdotool", "mouseup", "1"], stderr=subprocess.DEVNULL)
        print(f"  🎯 击穿点击执行完毕，随机模拟坐标落点: ({target_x}, {target_y})")
    else:
        rx = x + random.randint(-2, 2)
        ry = y + random.randint(-2, 2)
        print(f"  🖱️ 物理级常规点击 Turnstile 坐标: ({rx}, {ry})")
        try:
            subprocess.run(["xdotool", "mousemove", "--sync", str(rx), str(ry)], timeout=3, stderr=subprocess.DEVNULL)
            time.sleep(random.uniform(0.1, 0.2))
            subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
        except Exception:
            os.system(f"xdotool mousemove {rx} {ry} click 1 2>/dev/null")

# ============================================================
#  人机验证处理
# ============================================================
def _click_turnstile(sb, penetration_mode: bool = False):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  ⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  ⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
    bar = wi["oh"] - wi["ih"]
    ax = coords["cx"] + wi["sx"]
    ay = coords["cy"] + wi["sy"] + bar
    _xdotool_click(ax, ay, penetration_mode=penetration_mode)


def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    import random
    time.sleep(2)
    if sb.execute_script(_SOLVED_JS):
        print("  ✅ 已静默通过")
        return True
    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)
    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)
        penetration_mode = (attempt >= 2)
        _click_turnstile(sb, penetration_mode=penetration_mode)
        for _ in range(8):
            time.sleep(random.uniform(0.4, 0.6))
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")
    print("  ❌ Turnstile 6 次均失败")
    return False

# ============================================================
#  账户登录模块
# ============================================================
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(4)
    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
    except Exception:
        print("❌ 页面未加载出登录表单")
        sb.save_screenshot("login_load_fail.png")
        return False
    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass
    print("📧 填写邮箱...")
    js_fill_input(sb, 'input[name="Email"]', EMAIL)
    time.sleep(0.3)
    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="Password"]', PASSWORD)
    time.sleep(1)
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")
    print("🖱️ 提交登录表单...")
    try:
        sb.click('button[type="submit"]')
    except Exception:
        sb.press_keys('input[name="Password"]', '\n')

    print("⏳ 等待登录完成并验证会话...")
    time.sleep(5)

    # 不能仅凭 URL 变化判断登录成功。登录失败页面也可能改变查询参数或尾部斜杠。
    # 直接访问控制面板并检查登录表单是否再次出现，以确认认证 Cookie 真正生效。
    sb.open("https://justrunmy.app/panel")
    time.sleep(5)

    current_url = sb.get_current_url()
    login_form_visible = sb.is_element_present('input[name="Email"]')
    if "/id/Account/Login" not in current_url and not login_form_visible:
        print("✅ 登录成功，会话验证通过！")
        return True

    print(f"❌ 登录失败或登录会话未生效，当前页面: {current_url}")
    sb.save_screenshot("login_failed.png")
    return False

# ============================================================
#  自动续期模块 (动态抓取名称 + TG 通知)
# ============================================================
def renew(sb) -> bool:
    global DYNAMIC_APP_NAME

    print("\n" + "="*50)
    print("   🚀 开始自动续期流程")
    print("="*50)

    DYNAMIC_APP_NAME = "bot"
    print("🌐 直接进入指定应用详情页: https://justrunmy.app/panel/application/39529/")
    sb.open("https://justrunmy.app/panel/application/39529/")
    time.sleep(5)
    print(f"🎯 当前应用名称: {DYNAMIC_APP_NAME}")
    print(f"📍 当前应用详情页: {sb.get_current_url()}")

    print("🖱️ 点击 Reset Timer 按钮...")
    try:
        sb.click('button:contains("Reset Timer")')
        time.sleep(3)
    except Exception as e:
        print(f"❌ 找不到 Reset Timer 按钮: {e}")
        sb.save_screenshot("renew_reset_btn_not_found.png")
        send_tg_message("❌", "续期失败(找不到按钮)", "未知")
        return False

    print("🛡️ 检查续期弹窗内是否需要 CF 验证...")
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 弹窗内的 Turnstile 验证失败")
            sb.save_screenshot("renew_turnstile_fail.png")
            send_tg_message("❌", "续期失败(人机验证未过)", "未知")
            return False
    else:
        print("ℹ️ 弹窗内未检测到 Turnstile")

    print("🖱️ 点击 Just Reset 确认续期...")
    try:
        sb.click('button:contains("Just Reset")')
        print("⏳ 提交续期请求，等待服务器处理...")
        time.sleep(5)
    except Exception as e:
        print(f"❌ 找不到 Just Reset 按钮: {e}")
        sb.save_screenshot("renew_just_reset_not_found.png")
        send_tg_message("❌", "续期失败(无法确认)", "未知")
        return False

    print("🔍 验证最终倒计时状态...")
    try:
        sb.refresh()
        time.sleep(4)
        timer_text = sb.get_text('span.font-mono.text-xl')
        print(f"⏱️ 当前应用剩余时间: {timer_text}")
        if "2 days 23" in timer_text or "3 days" in timer_text:
            print("✅ 完美！续期任务圆满完成！")
            sb.save_screenshot("renew_success.png")
            send_tg_message("✅", "续期完成", timer_text)
            return True
        else:
            print("⚠️ 倒计时似乎没有重置到最高值，请人工检查截图确认。")
            sb.save_screenshot("renew_warning.png")
            send_tg_message("⚠️", "续期异常(请检查)", timer_text)
            return True
    except Exception as e:
        print(f"⚠️ 读取倒计时失败，但流程已执行完毕: {e}")
        sb.save_screenshot("renew_timer_read_fail.png")
        send_tg_message("⚠️", "读取剩余时间失败", "未知")
        return False

# ============================================================
#  脚本执行入口
# ============================================================
def main():
    print("=" * 50)
    print("   JustRunMy.app 自动登录与续期脚本 (SSH 动态直连升级版)")
    print("=" * 50)
    proxy_manager, proxy_url = start_proxy_with_retry(max_retries=5)
    print(f"🔍 正在检查 IP 信息（使用代理: {bool(proxy_url)})...")
    ip_info = check_ip(proxy_url)
    print(f"🌐 IP 信息：{ip_info}")
    global CURRENT_IP_INFO
    CURRENT_IP_INFO = ip_info
    sb_kwargs = {"uc": True, "test": True, "headless": False}
    if proxy_url:
        print(f"🔗 挂载隧道代理至浏览器后端: {proxy_url}")
        sb_kwargs["proxy"] = proxy_url
    else:
        print("🌐 未配置安全隧道，正在使用默认 Actions 裸奔直连访问")
    try:
        with SB(**sb_kwargs) as sb:
            print("✅ 自动化安全浏览器已成功拉起")
            try:
                sb.open("https://api.ipify.org/?format=json")
                print(f"🌐 浏览器端实测出口真实 IP: {sb.get_text('body')}")
            except Exception:
                pass
            if login(sb):
                renew(sb)
            else:
                print("\n❌ 登录环节失败，终止后续续期操作。")
                send_tg_message("❌", "登录失败", "未知")
    finally:
        if proxy_manager:
            proxy_manager.stop()

if __name__ == "__main__":
    main()
