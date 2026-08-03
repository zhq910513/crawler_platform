#!/usr/bin/env python3
"""Validate Alembic migration graph before release/deploy.

This script intentionally checks the migration *files* rather than the target
DB. It catches the production issue where obsolete migration files remained in
backend/migrations/versions and Alembic reported "Multiple head revisions".
"""
from __future__ import annotations

from pathlib import Path
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
VERSIONS = BACKEND / "migrations" / "versions"
EXPECTED_HEAD = "0003_schedule_cron_len"
MAX_ALEMBIC_VERSION_LEN = 32
OBSOLETE_FILES = {
    "0002_platform_1_0_2_observability.py",
    "0003_expand_schedule_cron_expression.py",
}


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


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

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)

    heads = list(script.get_heads())
    if heads != [EXPECTED_HEAD]:
        print(f"检测到异常 Alembic heads：{heads}", file=sys.stderr)
        print(f"期望唯一 head：{EXPECTED_HEAD}", file=sys.stderr)
        return 1

    revisions = list(script.walk_revisions())
    for revision in revisions:
        values = [revision.revision]
        down_revision = revision.down_revision
        if isinstance(down_revision, tuple):
            values.extend(v for v in down_revision if v)
        elif down_revision:
            values.append(down_revision)
        for value in values:
            if len(value) > MAX_ALEMBIC_VERSION_LEN:
                return fail(
                    f"Alembic revision id 超过 {MAX_ALEMBIC_VERSION_LEN} 字符：{value}。"
                    "MySQL 默认 alembic_version.version_num 无法保存。"
                )

    filenames = sorted(path.name for path in VERSIONS.glob("*.py"))
    expected_files = ["0001_initial_platform.py", "0002_observability.py", "0003_schedule_cron_len.py"]
    if filenames != expected_files:
        print("迁移文件清单不符合当前 1.0.2 发布基线：", file=sys.stderr)
        print(f"  当前：{filenames}", file=sys.stderr)
        print(f"  期望：{expected_files}", file=sys.stderr)
        return 1

    print("Alembic 迁移图检查通过：唯一 head=0003_schedule_cron_len，revision id 均 <= 32，未发现废弃迁移文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
