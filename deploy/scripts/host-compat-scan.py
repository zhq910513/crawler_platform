#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan deployment scripts for accidental host Python/npm/jq hard dependencies."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [ROOT / "deploy" / "scripts", ROOT / "deploy" / "templates" / "project"]
FAILURES: list[str] = []


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def add(path: Path, line_no: int, message: str, line: str) -> None:
    FAILURES.append(f"{rel(path)}:{line_no}: {message}: {line.strip()}")


def scan_shell(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "python3 -m compileall" in line or "python -m compileall" in line:
            if "cp_python_tool" not in line and "cp_python_tool_sh" not in line:
                add(path, line_no, "禁止直接用宿主机 Python 编译", raw)
        if "python -m pytest" in line or "python3 -m pytest" in line:
            if "cp_python_tool" not in line and "cp_python_tool_sh" not in line:
                add(path, line_no, "禁止直接用宿主机 Python 跑测试", raw)
        if "npm run build" in line or "npm ci" in line:
            if "cp_node_tool_sh" not in line and "docker" not in line:
                add(path, line_no, "禁止直接用宿主机 npm 构建前端", raw)
        if "jq " in line or line.endswith("jq"):
            add(path, line_no, "部署脚本禁止依赖宿主机 jq", raw)
        if "command -v python" in line and "doctor.sh" not in rel(path) and "lib/host.sh" not in rel(path) and "bootstrap.sh" not in rel(path):
            add(path, line_no, "不应把宿主机 Python 探测散落在脚本中，请走 host.sh 工具函数", raw)
        if "command -v npm" in line and "doctor.sh" not in rel(path):
            add(path, line_no, "不应把宿主机 npm 探测散落在脚本中，请走 Node 工具容器", raw)


def main() -> int:
    for target in TARGETS:
        if not target.exists():
            continue
        for path in target.rglob("*.sh"):
            scan_shell(path)
    if FAILURES:
        print("宿主机兼容扫描失败：", file=sys.stderr)
        for item in FAILURES:
            print("- " + item, file=sys.stderr)
        return 1
    print("宿主机兼容扫描通过：未发现新增宿主机 Python/npm/jq 硬依赖。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
