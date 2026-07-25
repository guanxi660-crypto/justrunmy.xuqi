#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只替换 justrunmy_renew.py 中的 renew() 函数，其余内容保持不变。"""
from pathlib import Path
import re
import shutil
import sys

TARGET = Path(sys.argv[1] if len(sys.argv) > 1 else "justrunmy_renew.py")
BACKUP = TARGET.with_suffix(TARGET.suffix + ".bak")
NEW_RENEW = 'def renew(sb) -> bool:\n    global DYNAMIC_APP_NAME\n\n    APPLICATION_URL = "https://justrunmy.app/panel/application/39529/"\n    DYNAMIC_APP_NAME = "bot"\n\n    def save_debug(name):\n        try:\n            print(f"📍 当前 URL: {sb.get_current_url()}")\n            print(f"📄 页面标题: {sb.get_title()}")\n            body = sb.get_text("body")\n            print("🧾 页面内容摘要:")\n            print((body or "")[:2000])\n        except Exception:\n            pass\n        try:\n            sb.save_screenshot(name)\n        except Exception:\n            pass\n\n    def read_timer():\n        candidates = ["span.font-mono.text-xl", ".font-mono.text-xl", "span.font-mono", ".font-mono"]\n        for selector in candidates:\n            try:\n                if sb.is_element_visible(selector):\n                    text = (sb.get_text(selector) or "").strip()\n                    match = re.search(r"\\b\\d+\\s+days?\\s+\\d{1,2}:\\d{2}\\b", text, re.I)\n                    if match:\n                        return match.group(0)\n            except Exception:\n                pass\n        try:\n            body = sb.get_text("body") or ""\n            match = re.search(r"\\b\\d+\\s+days?\\s+\\d{1,2}:\\d{2}\\b", body, re.I)\n            if match:\n                return match.group(0)\n        except Exception:\n            pass\n        return "未知"\n\n    def timer_seconds(text):\n        match = re.search(r"(\\d+)\\s+days?\\s+(\\d{1,2}):(\\d{2})", text or "", re.I)\n        if not match:\n            return None\n        days, hours, minutes = map(int, match.groups())\n        return days * 86400 + hours * 3600 + minutes * 60\n\n    print("\\n" + "=" * 50)\n    print("   🚀 开始自动续期流程")\n    print("=" * 50)\n    print(f"🌐 直接进入指定应用续期页面: {APPLICATION_URL}")\n\n    try:\n        sb.open(APPLICATION_URL)\n        sb.wait_for_ready_state_complete()\n        time.sleep(4)\n    except Exception as e:\n        print(f"❌ 应用详情页打开失败: {e}")\n        save_debug("renew_page_open_fail.png")\n        send_tg_message("❌", "续期失败(详情页无法打开)", "未知")\n        return False\n\n    if "/id/Account/Login" in sb.get_current_url():\n        print("❌ 登录状态失效，详情页被重定向到登录页面")\n        save_debug("renew_login_expired.png")\n        send_tg_message("❌", "续期失败(登录状态失效)", "未知")\n        return False\n\n    try:\n        for selector in ["main h1", "h1"]:\n            if sb.is_element_visible(selector):\n                name = (sb.get_text(selector) or "").strip()\n                if name and len(name) <= 100:\n                    DYNAMIC_APP_NAME = name\n                    break\n    except Exception:\n        pass\n    print(f"🎯 当前应用: {DYNAMIC_APP_NAME}")\n\n    before_timer = read_timer()\n    print(f"⏱️ 续期前剩余时间: {before_timer}")\n\n    print("🖱️ 点击 Reset Timer 按钮...")\n    try:\n        sb.wait_for_element_visible(\'button:contains("Reset Timer")\', timeout=20)\n        sb.click(\'button:contains("Reset Timer")\')\n        time.sleep(3)\n    except Exception as e:\n        print(f"❌ 找不到或无法点击 Reset Timer 按钮: {e}")\n        save_debug("renew_reset_btn_not_found.png")\n        send_tg_message("❌", "续期失败(找不到按钮)", before_timer)\n        return False\n\n    print("🛡️ 检查续期弹窗内是否需要 CF 验证...")\n    try:\n        needs_turnstile = bool(sb.execute_script(_EXISTS_JS))\n    except Exception:\n        needs_turnstile = False\n\n    if needs_turnstile:\n        if not handle_turnstile(sb):\n            print("❌ 弹窗内的 Turnstile 验证失败")\n            save_debug("renew_turnstile_fail.png")\n            send_tg_message("❌", "续期失败(人机验证未过)", before_timer)\n            return False\n    else:\n        print("ℹ️ 弹窗内未检测到 Turnstile")\n\n    print("🖱️ 点击 Just Reset 确认续期...")\n    try:\n        sb.wait_for_element_visible(\'button:contains("Just Reset")\', timeout=20)\n        sb.click(\'button:contains("Just Reset")\')\n        print("⏳ 提交续期请求，等待服务器处理...")\n        time.sleep(6)\n    except Exception as e:\n        print(f"❌ 找不到或无法点击 Just Reset 按钮: {e}")\n        save_debug("renew_just_reset_not_found.png")\n        send_tg_message("❌", "续期失败(无法确认)", before_timer)\n        return False\n\n    print("🔍 验证最终倒计时状态...")\n    try:\n        sb.open(APPLICATION_URL)\n        sb.wait_for_ready_state_complete()\n        time.sleep(5)\n        timer_text = read_timer()\n        print(f"⏱️ 当前应用剩余时间: {timer_text}")\n\n        before_seconds = timer_seconds(before_timer)\n        after_seconds = timer_seconds(timer_text)\n        reset_ok = False\n        if after_seconds is not None:\n            reset_ok = after_seconds >= (2 * 86400 + 20 * 3600)\n            if before_seconds is not None and after_seconds > before_seconds + 3600:\n                reset_ok = True\n\n        if reset_ok:\n            print("✅ 完美！续期任务圆满完成！")\n            sb.save_screenshot("renew_success.png")\n            send_tg_message("✅", "续期完成", timer_text)\n            return True\n\n        print("⚠️ 已执行确认操作，但倒计时未显示为接近 3 天。")\n        save_debug("renew_warning.png")\n        send_tg_message("⚠️", "续期异常(请检查)", timer_text)\n        return False\n    except Exception as e:\n        print(f"⚠️ 读取倒计时失败: {e}")\n        save_debug("renew_timer_read_fail.png")\n        send_tg_message("⚠️", "读取剩余时间失败", "未知")\n        return False\n'

if not TARGET.exists():
    raise SystemExit(f"未找到 {TARGET}。请把本补丁放到 justrunmy_renew.py 同一目录后运行。")
source = TARGET.read_text(encoding="utf-8")
start_marker = "def renew(sb) -> bool:"
end_marker = "# ============================================================\n#  脚本执行入口"
start = source.find(start_marker)
end = source.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("没有找到 renew() 函数边界，未修改任何文件。")
if not re.search(r"^import re\s*$", source, flags=re.M):
    anchor = "import requests\n"
    if anchor not in source:
        raise SystemExit("没有找到 import requests，未修改任何文件。")
    source = source.replace(anchor, anchor + "import re\n", 1)
    start = source.find(start_marker)
    end = source.find(end_marker, start)
shutil.copy2(TARGET, BACKUP)
updated = source[:start] + NEW_RENEW.rstrip() + "\n\n" + source[end:]
TARGET.write_text(updated, encoding="utf-8", newline="\n")
print(f"✅ 已修复: {TARGET}")
print(f"🧷 原文件备份: {BACKUP}")
print("ℹ️ 只替换 renew()，并在缺少时增加 import re；renew.yml 无需修改。")
