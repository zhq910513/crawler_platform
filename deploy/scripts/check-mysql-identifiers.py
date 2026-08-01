#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check migration/model files for MySQL identifier names longer than 64 chars."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [ROOT / "backend/migrations", ROOT / "backend/app/models.py"]
PATTERN = re.compile(r"['\"]([A-Za-z][A-Za-z0-9_]{64,})['\"]")


def main() -> int:
    problems = []
    for target in TARGETS:
        if target.is_dir():
            files = list(target.rglob("*.py"))
        elif target.is_file():
            files = [target]
        else:
            continue
        for file in files:
            text = file.read_text(encoding="utf-8")
            for match in PATTERN.finditer(text):
                name = match.group(1)
                problems.append((file.relative_to(ROOT), len(name), name))
    if problems:
        print("MySQL 标识符长度检查失败：以下名称超过 64 字符", file=sys.stderr)
        for file, length, name in sorted(problems):
            print(f"- {file}: {length} {name}", file=sys.stderr)
        return 1
    print("MySQL 标识符长度检查通过：未发现超过 64 字符的表/索引/外键名。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
