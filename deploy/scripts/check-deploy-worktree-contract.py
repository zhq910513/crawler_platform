#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check CI/CD deployment worktree hygiene contracts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAILURES: list[str] = []


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def fail(message: str) -> None:
    FAILURES.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def scan_host_helpers() -> None:
    host = ROOT / "deploy/scripts/lib/host.sh"
    text = read(host)
    if "cp_git_restore_mode_only_changes()" not in text:
        fail("host.sh 缺少 Git 权限位漂移自愈函数 cp_git_restore_mode_only_changes")
    for snippet in [
        "cp_ensure_runtime_data_git_excludes()",
        "cp_git_status_filtered()",
        "cp_git_relevant_status()",
        "CP_DEPLOY_IGNORED_UNTRACKED_PATHS",
        "# BEGIN CRAWLER_PLATFORM_RUNTIME_DATA_EXCLUDES",
    ]:
        if snippet not in text:
            fail(f"host.sh 缺少本地运行目录忽略契约：{snippet}")
    for snippet in ["core.fileMode=false", "git reset -q HEAD -- .", "git checkout -q -- ."]:
        if snippet not in text:
            fail(f"Git 权限位漂移自愈函数缺少关键保护：{snippet}")
    forbidden = ["chmod +x deploy/scripts/*.sh", "chmod +x agent/install-linux.sh"]
    for item in forbidden:
        if item in text:
            fail(f"部署权限修复不得 chmod Git 管理脚本：{item}")


def scan_remote_entry() -> None:
    remote = ROOT / "deploy/scripts/remote-auto-deploy.sh"
    text = read(remote)
    if "cp_git_restore_mode_only_changes" not in text:
        fail("remote-auto-deploy.sh 未在部署前调用权限位漂移自愈")
    if "cp_ensure_runtime_data_git_excludes" not in text or "cp_git_status_filtered" not in text:
        fail("remote-auto-deploy.sh 未在脏工作区检查前建立运行目录忽略规则")
    if text.index("cp_ensure_runtime_data_git_excludes") > text.index("cp_git_restore_mode_only_changes"):
        fail("remote-auto-deploy.sh 必须先建立运行目录忽略规则，再检查工作区")
    if "git status --porcelain" in text and "工作区存在未提交改动" in text:
        fail("remote-auto-deploy.sh 仍使用旧的脏工作区一刀切阻断文案")


def scan_workflow_bootstrap() -> None:
    workflow = ROOT / ".github/workflows/deploy-test-server.yml"
    text = read(workflow)
    for snippet in [
        "检测到仅 Git 文件权限位变化",
        "core.fileMode=false",
        "git reset -q HEAD -- .",
        "git checkout -q -- .",
        "[ ! -f deploy/scripts/remote-auto-deploy.sh ]",
        ".git/info/exclude",
        "ensure_runtime_data_ignore",
        "filtered_status",
        "CP_DEPLOY_PUBLIC_HOST",
        "STRICT_AGENT_IMAGE_PREPARE=\"1\"",
    ]:
        if snippet not in text:
            fail(f"GitHub Actions SSH 入口缺少首次升级自愈逻辑：{snippet}")


def scan_internal_script_invocations() -> None:
    pattern = re.compile(r"^\s*\./deploy/scripts/[^\s]+\.sh\b")
    for path in (ROOT / "deploy/scripts").rglob("*.sh"):
        for line_no, line in enumerate(read(path).splitlines(), 1):
            if pattern.search(line):
                fail(f"内部部署脚本调用应使用 bash，避免依赖执行权限：{rel(path)}:{line_no}: {line.strip()}")


def main() -> int:
    scan_host_helpers()
    scan_remote_entry()
    scan_workflow_bootstrap()
    scan_internal_script_invocations()
    if FAILURES:
        print("CI/CD 工作区权限位自愈契约检查失败：", file=sys.stderr)
        for item in FAILURES:
            print("- " + item, file=sys.stderr)
        return 1
    print("CI/CD 工作区权限位自愈契约检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
