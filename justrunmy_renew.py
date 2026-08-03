#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 JustRunMy.app 续期按钮定位，使 Reset Timer 任意大小写均可识别。

用法：
    python fix_reset_timer_case.py justrunmy_renew.py

脚本会：
1. 自动备份原文件为 justrunmy_renew.py.bak
2. 将区分大小写的 Reset Timer XPath 替换为不区分大小写的 XPath
3. 保留原脚本其他内容不变
"""

from pathlib import Path
import re
import shutil
import sys

CASE_INSENSITIVE_XPATH = (
    "//button[contains("
    "translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
    "'abcdefghijklmnopqrstuvwxyz'), "
    "'reset timer')]"
)


def patch_file(filename: str) -> None:
    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"❌ 找不到文件：{path}")

    source = path.read_text(encoding="utf-8")
    patched = source

    # 匹配常见写法：
    # //button[contains(., 'Reset Timer')]
    # //button[contains(text(), "RESET TIMER")]
    # //button[contains(normalize-space(.), 'reset timer')]
    patterns = [
        r'''//button\[contains\(\s*\.\s*,\s*(['"])reset\s+timer\1\s*\)\]''',
        r'''//button\[contains\(\s*text\(\)\s*,\s*(['"])reset\s+timer\1\s*\)\]''',
        r'''//button\[contains\(\s*normalize-space\(\.\)\s*,\s*(['"])reset\s+timer\1\s*\)\]''',
    ]

    replacement_count = 0
    for pattern in patterns:
        patched, count = re.subn(
            pattern,
            CASE_INSENSITIVE_XPATH,
            patched,
            flags=re.IGNORECASE,
        )
        replacement_count += count

    # 原文件已经是新版时，不重复修改。
    if CASE_INSENSITIVE_XPATH in source:
        print("✅ 原脚本已经支持 Reset Timer 任意大小写，无需修改。")
        return

    if replacement_count == 0:
        raise SystemExit(
            "❌ 未找到 Reset Timer 定位器，未修改原文件。\n"
            "请上传 justrunmy_renew.py，我可以按实际代码结构直接改好。"
        )

    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    path.write_text(patched, encoding="utf-8")

    # 二次一致性检查。
    verify = path.read_text(encoding="utf-8")
    if CASE_INSENSITIVE_XPATH not in verify:
        shutil.copy2(backup, path)
        raise SystemExit("❌ 修改校验失败，已自动恢复原文件。")

    print(f"✅ 修改完成：{path}")
    print(f"✅ 共替换 {replacement_count} 处 Reset Timer 定位器")
    print(f"📦 原文件备份：{backup}")
    print("🔎 现在可识别 Reset timer、Reset Timer、RESET TIMER 等任意大小写。")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "用法：python fix_reset_timer_case.py justrunmy_renew.py"
        )
    patch_file(sys.argv[1])


if __name__ == "__main__":
    main()
