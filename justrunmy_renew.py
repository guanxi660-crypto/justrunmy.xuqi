#!/usr/bin/env python3
"""Patch justrunmy_renew.py for the Reset timer label change.

Usage:
    python patch_justrunmy_renew.py /path/to/justrunmy_renew.py

A .bak backup is created before modification.
"""
from pathlib import Path
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python patch_justrunmy_renew.py /path/to/justrunmy_renew.py")

path = Path(sys.argv[1]).expanduser().resolve()
if not path.is_file():
    raise SystemExit(f"File not found: {path}")

text = path.read_text(encoding="utf-8")
original = text

old_variants = [
    "//button[contains(., 'Reset Timer')]",
    '//button[contains(., "Reset Timer")]',
]

robust_xpath = "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'reset timer')]"

replaced = False
for old in old_variants:
    if old in text:
        text = text.replace(old, robust_xpath)
        replaced = True

if not replaced:
    raise SystemExit(
        "Target XPath was not found. No changes were made. "
        "Please upload the original justrunmy_renew.py for a structure-aware edit."
    )

backup = path.with_suffix(path.suffix + ".bak")
shutil.copy2(path, backup)
path.write_text(text, encoding="utf-8")

print(f"Patched: {path}")
print(f"Backup:  {backup}")
print("New locator is case-insensitive and matches Reset timer / Reset Timer.")
