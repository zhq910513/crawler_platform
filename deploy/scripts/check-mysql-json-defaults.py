#!/usr/bin/env python3
"""Fail release if migrations/models define server_default on MySQL JSON columns.

MySQL rejects DEFAULT values on JSON/TEXT/BLOB/GEOMETRY columns. The deploy gate
must catch this statically because SQLite-based migration tests will not expose
it, and real customer upgrades may fail midway.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = [ROOT / "backend" / "migrations" / "versions", ROOT / "backend" / "app"]

# Covers common project style: sa.Column(... sa.JSON() ... server_default=...) and
# mapped_column(JSON, ..., server_default=...). Kept intentionally conservative.
INLINE_PATTERN = re.compile(r"(?:sa\.)?(?:Column|mapped_column)\([^\n]*(?:sa\.)?JSON\s*(?:\(\))?[^\n]*server_default", re.I)


def _statement_from(text: str, start: int) -> str:
    depth = 0
    started = False
    quote: str | None = None
    escape = False
    out: list[str] = []
    for ch in text[start:]:
        out.append(ch)
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
            continue
        if ch == "(":
            depth += 1
            started = True
        elif ch == ")":
            depth -= 1
            if started and depth <= 0:
                break
    return "".join(out)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    findings: list[tuple[int, str]] = []
    for match in re.finditer(r"(?:sa\.)?(?:Column|mapped_column)\(", text):
        stmt = _statement_from(text, match.start())
        if re.search(r"(?:sa\.)?JSON\s*(?:\(\))?", stmt) and "server_default" in stmt:
            line = text.count("\n", 0, match.start()) + 1
            summary = " ".join(stmt.split())[:240]
            findings.append((line, summary))
    for m in INLINE_PATTERN.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        if all(line != item[0] for item in findings):
            findings.append((line, m.group(0)[:240]))
    return findings


def main() -> int:
    problems: list[str] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for line, stmt in _scan_file(path):
                rel = path.relative_to(ROOT)
                problems.append(f"{rel}:{line}: JSON column must not use server_default -> {stmt}")
    if problems:
        print("FAIL: 检测到 MySQL 不兼容的 JSON server_default：", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        print("修复方式：JSON 列不要设置 server_default；新增到已有表时先 nullable=True，回填，再在 MySQL 上 alter nullable=False。", file=sys.stderr)
        return 1
    print("MySQL JSON 默认值兼容检查通过：未发现 JSON/TEXT 类列使用 server_default。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
