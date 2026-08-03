#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 GitHub Actions 中修复 Reset Timer 大小写定位后，立即运行续期脚本。

直接替换原来 pytest 后面的执行入口：
  xvfb-run ... python run_justrunmy_casefix.py

也可指定文件并追加 pytest 参数：
  python run_justrunmy_casefix.py justrunmy_renew.py -s
"""
from pathlib import Path
import os
import re
import shutil
import sys

XPATH = (
    "//button[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset timer')]"
)

PATTERNS = [
    r'''//button\[contains\(\s*\.\s*,\s*(['"])reset\s+timer\1\s*\)\]''',
    r'''//button\[contains\(\s*text\(\)\s*,\s*(['"])reset\s+timer\1\s*\)\]''',
    r'''//button\[contains\(\s*normalize-space\(\.\)\s*,\s*(['"])reset\s+timer\1\s*\)\]''',
]


def patch(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"❌ 找不到续期脚本：{path}")

    source = path.read_text(encoding="utf-8")
    if XPATH in source:
        print("✅ Reset timer 定位器已支持任意大小写")
        return

    output = source
    total = 0
    for pattern in PATTERNS:
        output, count = re.subn(pattern, XPATH, output, flags=re.IGNORECASE)
        total += count

    if total == 0:
        raise SystemExit(
            "❌ 在 justrunmy_renew.py 中没有找到 Reset Timer XPath。"
            "请上传原文件以便按实际结构修改。"
        )

    backup = path.with_name(path.name + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(output, encoding="utf-8")

    if XPATH not in path.read_text(encoding="utf-8"):
        raise SystemExit("❌ 修复后的文件校验失败")
    print(f"✅ 已修复 {total} 处按钮定位，可识别 Reset timer / Reset Timer / RESET TIMER")


def main() -> None:
    args = sys.argv[1:]
    target = Path("justrunmy_renew.py")
    if args and args[0].endswith(".py"):
        target = Path(args.pop(0))

    patch(target)
    print(f"🚀 立即通过 pytest 运行：{target}")
    os.execvp("pytest", ["pytest", str(target), *args])


if __name__ == "__main__":
    main()
