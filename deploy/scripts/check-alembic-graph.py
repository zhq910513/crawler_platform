#!/usr/bin/env python3
"""Validate Alembic migration graph before release/deploy.

This checker is deliberately standard-library only. It must run in the generic
Python tool container used by deployment gates, before the project images are
rebuilt and before backend dependencies such as Alembic are installed. The goal
is to catch file-level migration graph problems on old customer hosts without
adding a host Python/npm/jq dependency.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend" / "migrations" / "versions"
EXPECTED_HEAD = "0010_running_center"
MAX_ALEMBIC_VERSION_LEN = 32
OBSOLETE_FILES = {
    "0002_platform_1_0_2_observability.py",
    "0003_expand_schedule_cron_expression.py",
}
EXPECTED_FILES = ["0001_initial_platform.py", "0002_observability.py", "0003_schedule_cron_len.py", "0004_task_panel.py", "0005_110_audit.py", "0006_agent_deploy.py", "0007_account_status.py", "0008_task_contract_subject_binding.py", "0009_contract_runtime_gate.py", "0010_running_center_container_snapshots.py"]


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def _literal_assignments(path: Path) -> Dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: Dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except Exception as exc:  # pragma: no cover - defensive error formatting
                    raise ValueError(f"{path.name}: {target.id} 必须是 Python 字面量") from exc
    return values


def _normalize_down_revision(value: object) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        result: List[str] = []
        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise ValueError(f"down_revision 包含非字符串值：{item!r}")
            result.append(item)
        return tuple(result)
    raise ValueError(f"down_revision 类型不支持：{type(value).__name__}")


def _load_revisions() -> Tuple[Dict[str, str], Dict[str, Tuple[str, ...]]]:
    revisions: Dict[str, str] = {}
    downs: Dict[str, Tuple[str, ...]] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        values = _literal_assignments(path)
        revision = values.get("revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{path.name}: 缺少有效 revision")
        if revision in revisions:
            raise ValueError(f"重复 revision：{revision}，文件：{revisions[revision]} 与 {path.name}")
        revisions[revision] = path.name
        downs[revision] = _normalize_down_revision(values.get("down_revision"))
    return revisions, downs


def _format_mapping(revisions: Dict[str, str], downs: Dict[str, Tuple[str, ...]]) -> str:
    lines = []
    for revision in sorted(revisions):
        down = downs.get(revision, ())
        lines.append(f"  - {revision} ({revisions[revision]}) <- {down or 'base'}")
    return "\n".join(lines)


def main() -> int:
    if not VERSIONS.exists():
        return fail(f"迁移目录不存在：{VERSIONS}")

    obsolete_present = sorted(name for name in OBSOLETE_FILES if (VERSIONS / name).exists())
    if obsolete_present:
        print("检测到已废弃的旧迁移文件，会造成 Alembic multiple heads：", file=sys.stderr)
        for name in obsolete_present:
            print(f"  - backend/migrations/versions/{name}", file=sys.stderr)
        print("请执行：bash deploy/scripts/cleanup-obsolete-migrations.sh，然后 git add -A && git commit。", file=sys.stderr)
        return 1

    filenames = sorted(path.name for path in VERSIONS.glob("*.py") if path.name != "__init__.py")
    if filenames != EXPECTED_FILES:
        print("迁移文件清单不符合当前 1.0.52 发布基线：", file=sys.stderr)
        print(f"  当前：{filenames}", file=sys.stderr)
        print(f"  期望：{EXPECTED_FILES}", file=sys.stderr)
        return 1

    try:
        revisions, downs = _load_revisions()
    except Exception as exc:
        return fail(str(exc))

    for revision, filename in revisions.items():
        if len(revision) > MAX_ALEMBIC_VERSION_LEN:
            return fail(
                f"Alembic revision id 超过 {MAX_ALEMBIC_VERSION_LEN} 字符：{revision}，文件：{filename}。"
                "MySQL 默认 alembic_version.version_num 无法保存。"
            )
        for down_revision in downs.get(revision, ()):  # validate referenced values too
            if len(down_revision) > MAX_ALEMBIC_VERSION_LEN:
                return fail(
                    f"Alembic down_revision 超过 {MAX_ALEMBIC_VERSION_LEN} 字符：{down_revision}，文件：{filename}。"
                    "MySQL 默认 alembic_version.version_num 无法保存。"
                )

    referenced: Set[str] = set()
    roots: List[str] = []
    for revision, down_values in downs.items():
        if not down_values:
            roots.append(revision)
        for down_revision in down_values:
            if down_revision not in revisions:
                return fail(f"迁移 {revision} 引用了不存在的 down_revision：{down_revision}\n当前迁移图：\n{_format_mapping(revisions, downs)}")
            referenced.add(down_revision)

    heads = sorted(set(revisions) - referenced)
    if heads != [EXPECTED_HEAD]:
        print(f"检测到异常 Alembic heads：{heads}", file=sys.stderr)
        print(f"期望唯一 head：{EXPECTED_HEAD}", file=sys.stderr)
        print(f"当前迁移图：\n{_format_mapping(revisions, downs)}", file=sys.stderr)
        return 1

    if roots != ["0001_initial_platform"]:
        print(f"检测到异常 Alembic roots：{roots}", file=sys.stderr)
        print("期望唯一 root：0001_initial_platform", file=sys.stderr)
        print(f"当前迁移图：\n{_format_mapping(revisions, downs)}", file=sys.stderr)
        return 1

    print(f"Alembic 迁移图检查通过：唯一 head={EXPECTED_HEAD}，revision id 均 <= {MAX_ALEMBIC_VERSION_LEN}，未发现废弃迁移文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
