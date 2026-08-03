#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Actions 入口：兼容 Reset timer 大小写，然后运行原续期脚本。

无需参数：python run_justrunmy_fixed.py
默认运行同目录的 justrunmy_renew.py。
"""
from pathlib import Path
import os
import re
import sys

TARGET = Path(__file__).resolve().parent / "justrunmy_renew.py"

if not TARGET.is_file():
    print(f"❌ 找不到原续期脚本: {TARGET}", flush=True)
    raise SystemExit(2)

source = TARGET.read_text(encoding="utf-8")

# 不再猜测原 XPath 结构。只把源码中按钮文案的所有大小写形式
# 统一为网页当前实际显示的 Reset timer，适用于 XPath、CSS 后文本判断、变量等写法。
patched, count = re.subn(r"reset\s+timer", "Reset timer", source, flags=re.IGNORECASE)
if count:
    TARGET.write_text(patched, encoding="utf-8")
    print(f"✅ 已统一 {count} 处按钮文案为 Reset timer", flush=True)
else:
    # 不因没找到字面量而提前退出，确保浏览器照常启动并产生诊断截图。
    print("⚠️ 源码中未发现 Reset Timer 字面量，将直接运行原续期脚本", flush=True)

# 兼容脚本把截图保存在当前目录或 screenshots 目录。
(Path.cwd() / "screenshots").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SCREENSHOT_DIR", "screenshots")

print(f"🚀 正在运行: pytest -s {TARGET.name}", flush=True)
os.execvp("pytest", ["pytest", "-s", str(TARGET)])
