#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAILURES: list[str] = []
WARNINGS: list[str] = []


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def add_failure(message: str) -> None:
    FAILURES.append(message)


def add_warning(message: str) -> None:
    WARNINGS.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def scan_select_star() -> None:
    pattern = re.compile(r"\bselect\s+\*\b", re.IGNORECASE)
    for path in list((ROOT / "backend" / "app").rglob("*.py")) + list((ROOT / "backend" / "migrations").rglob("*.py")):
        if pattern.search(read_text(path)):
            add_failure(f"禁止 SELECT *：{rel(path)}")


def scan_frontend_direct_network() -> None:
    dirs = [ROOT / "frontend" / "src" / name for name in ("views", "layouts", "components")]
    pattern = re.compile(r"\b(fetch\s*\(|axios\s*\.|axios\s*\()")
    for base in dirs:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".vue", ".ts", ".tsx"}:
                continue
            if pattern.search(read_text(path)):
                add_failure(f"前端组件/页面禁止直接网络请求：{rel(path)}")


def scan_route_contract() -> None:
    router_pattern = re.compile(r"@router\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]*)['\"]")
    verb_segments = {"create", "update", "delete", "reset-password", "change-password", "download-log", "start", "stop", "run", "cancel", "enable", "disable"}
    for path in (ROOT / "backend" / "app" / "api").rglob("*.py"):
        for match in router_pattern.finditer(read_text(path)):
            route = match.group(2)
            literal_segments = [item for item in route.split("/") if item and not item.startswith("{")]
            for segment in literal_segments:
                if segment != segment.lower():
                    add_failure(f"API 路径必须小写：{rel(path)} -> {route}")
                if segment in verb_segments:
                    add_failure(f"API 路径禁止动词片段：{rel(path)} -> {route}")


def scan_hardcoded_sensitive_values() -> None:
    # 只扫描运行代码，不扫描 .env.example / README / docs，避免把示例配置当生产密钥误报。
    bases = [ROOT / "backend" / "app", ROOT / "agent" / "crawler_agent", ROOT / "frontend" / "src", ROOT / "runtime"]
    suspicious = re.compile(r"(?i)(jwt_secret|secret_key|password|passwd|token)\s*=\s*['\"][^'\"]{8,}['\"]")
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".vue"}:
                continue
            text = read_text(path)
            for line_no, line in enumerate(text.splitlines(), 1):
                if suspicious.search(line) and "Field(" not in line and "getenv" not in line and "os.environ" not in line:
                    add_failure(f"疑似硬编码敏感值：{rel(path)}:{line_no}")


def scan_frontend_backend_log_routes() -> None:
    platform = ROOT / "frontend" / "src" / "api" / "platform.ts"
    if not platform.exists():
        return
    text = read_text(platform)
    if "/runs/${runId}/logs/tail" in text or "/runs/${runId}/diagnosis" in text:
        add_failure("前端运行日志 API 与后端 REST 资源不一致，应使用 /log-tails 与 /diagnoses")


def main() -> int:
    scan_select_star()
    scan_frontend_direct_network()
    scan_route_contract()
    scan_hardcoded_sensitive_values()
    scan_frontend_backend_log_routes()
    for warning in WARNINGS:
        print(f"WARN: {warning}")
    if FAILURES:
        for failure in FAILURES:
            print(f"FAIL: {failure}", file=sys.stderr)
        print(f"商业契约扫描失败：{len(FAILURES)} 项", file=sys.stderr)
        return 1
    print("商业契约扫描通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
