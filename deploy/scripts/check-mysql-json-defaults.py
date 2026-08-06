#!/usr/bin/env python3
"""Fail release if migrations/models define server_default on MySQL forbidden LOB columns.

MySQL rejects DEFAULT values on JSON/TEXT/BLOB/GEOMETRY columns. SQLite based
migration tests do not expose this, so the deploy gate must catch it statically
before customer upgrades run real MySQL DDL.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = [ROOT / "backend" / "migrations" / "versions", ROOT / "backend" / "app"]
FORBIDDEN_TYPES = (
    "JSON", "Text", "TEXT", "UnicodeText", "LargeBinary", "BLOB", "Blob", "PickleType",
)
TYPE_RE = re.compile(r"(?:sa\.)?(?:" + "|".join(re.escape(t) for t in FORBIDDEN_TYPES) + r")\s*\(", re.I)


def _statement_from(text: str, start: int) -> str:
    depth = 0
    started = False
    quote: str | None = None
    triple_quote: str | None = None
    escape = False
    out: list[str] = []
    i = start
    while i < len(text):
        ch = text[i]
        out.append(ch)
        nxt3 = text[i:i + 3]
        if triple_quote:
            if nxt3 == triple_quote:
                out.extend(text[i + 1:i + 3])
                i += 3
                triple_quote = None
                continue
            i += 1
            continue
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if nxt3 == "'''" or nxt3 == '"""':
            triple_quote = nxt3
            out.extend(text[i + 1:i + 3])
            i += 3
            continue
        if ch == '"' or ch == "'":
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            started = True
        elif ch == ")":
            depth -= 1
            if started and depth <= 0:
                break
        i += 1
    return "".join(out)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    findings: list[tuple[int, str]] = []
    for match in re.finditer(r"(?:sa\.)?(?:Column|mapped_column)\(", text):
        stmt = _statement_from(text, match.start())
        if "server_default" not in stmt:
            continue
        type_part = stmt.split("server_default", 1)[0]
        if TYPE_RE.search(type_part):
            line = text.count("\n", 0, match.start()) + 1
            summary = " ".join(stmt.split())[:300]
            findings.append((line, summary))
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
                problems.append(f"{rel}:{line}: MySQL forbidden LOB column must not use server_default -> {stmt}")
    if problems:
        print("FAIL: 检测到 MySQL 不兼容的 JSON/TEXT/BLOB server_default：", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        print("修复方式：JSON/TEXT/BLOB 等列不要设置 server_default；新增到已有表时先 nullable=True，回填，再按需 alter nullable=False。", file=sys.stderr)
        return 1
    print("MySQL JSON/TEXT/BLOB 默认值兼容检查通过：未发现禁止默认值的列使用 server_default。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
