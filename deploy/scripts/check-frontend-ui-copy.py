#!/usr/bin/env python3
"""Fail if frontend templates expose raw database field names or developer-only prompt banners."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
BAD_PATTERNS = [
    r"companyCode", r"platformCode", r"credentialKey", r"taskCode", r"projectCode", r"serverCode",
    r"entryPath", r"lastRunStatus", r"runId", r"taskId", r"projectId", r"serverId",
    r"\bJSON\b", r"\bCron\b", r"\bAgent\b", r"\bRun\b", r"\bAPI\b", r"\bToken\b", r"\bCookie\b",
    r"前端合约", r"字段", r"数据库字段", r"直接展示",
]
ATTR_RE = re.compile(r"(?:label|title|placeholder|content|description)=\"([^\"]*)\"")
TEXT_RE = re.compile(r">([^<>]+)<")

FORBIDDEN_PHRASES = ["阻断阻断", "需确认必须处理", "平台脚本可处理", "平台可一键处理"]

errors: list[str] = []
for path in sorted(SRC.rglob("*.vue")):
    raw = path.read_text(encoding="utf-8")
    for phrase in FORBIDDEN_PHRASES:
        if phrase in raw:
            errors.append(f"{path.relative_to(ROOT)}: 可见文案存在未产品化表达: {phrase}")
    match = re.search(r"<template>(.*?)</template>", raw, flags=re.S)
    if not match:
        continue
    template = re.sub(r"{{.*?}}", "", match.group(1), flags=re.S)
    visible_chunks = [m.group(1).strip() for m in ATTR_RE.finditer(template)]
    visible_chunks += [m.group(1).strip() for m in TEXT_RE.finditer(template)]
    visible_chunks = [chunk for chunk in visible_chunks if chunk and not chunk.startswith(":")]
    for chunk in visible_chunks:
        for pattern in BAD_PATTERNS:
            if re.search(pattern, chunk):
                errors.append(f"{path.relative_to(ROOT)}: 可见文案包含禁用词 {pattern!r}: {chunk}")

if errors:
    print("前端可见文案检查失败：", file=sys.stderr)
    for item in errors:
        print("- " + item, file=sys.stderr)
    sys.exit(1)
print("前端可见文案检查通过：未发现数据库字段名或开发提示直出。")
