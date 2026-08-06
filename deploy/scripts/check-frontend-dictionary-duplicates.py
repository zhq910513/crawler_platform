#!/usr/bin/env python3
"""Fail when frontend dictionary object literals contain duplicate keys.

This catches vue-tsc TS1117 earlier with a clearer release-gate message.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [ROOT / "frontend" / "src" / "utils" / "dictionaries.ts"]
OBJECT_RE = re.compile(r"export\s+const\s+(\w+)\s*:[^{=]+?=\s*{(?P<body>.*?)}\s*", re.S)
KEY_RE = re.compile(r"(?:^|[,\n])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")

errors: list[str] = []
for path in TARGETS:
    if not path.exists():
        continue
    raw = path.read_text(encoding="utf-8")
    for obj in OBJECT_RE.finditer(raw):
        object_name = obj.group(1)
        keys = KEY_RE.findall(obj.group("body"))
        counter = Counter(keys)
        for key, count in sorted(counter.items()):
            if count > 1:
                rel = path.relative_to(ROOT)
                errors.append(f"{rel}: {object_name} 存在重复键 {key!r}，出现 {count} 次")

if errors:
    print("前端字典重复键检查失败：", file=sys.stderr)
    for item in errors:
        print("- " + item, file=sys.stderr)
    sys.exit(1)

print("前端字典重复键检查通过：未发现重复键。")
