from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db import SessionLocal
from app.init_db import init_admin

OBSOLETE_MIGRATION_FILES = {
    "0002_platform_1_0_2_observability.py",
    "0003_expand_schedule_cron_expression.py",
}
EXPECTED_ALEMBIC_HEAD = "0003_schedule_cron_len"
MAX_ALEMBIC_VERSION_LEN = 32


def _remove_obsolete_migration_files(versions_dir: Path) -> None:
    """Remove known-bad 1.0.2 migration files from older packages.

    This is a defensive production safeguard. The release gate still fails if
    these files exist in Git, but a customer host may already have an image or
    worktree containing them. Removing them before ScriptDirectory is loaded
    prevents Alembic from seeing multiple heads.
    """
    for filename in OBSOLETE_MIGRATION_FILES:
        path = versions_dir / filename
        if path.exists():
            path.unlink()


def _validate_alembic_graph(cfg: Config) -> None:
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    if heads != [EXPECTED_ALEMBIC_HEAD]:
        raise RuntimeError(f"Alembic 迁移图异常，期望唯一 head={EXPECTED_ALEMBIC_HEAD}，实际 heads={heads}")
    for revision in script.walk_revisions():
        values = [revision.revision]
        down_revision = revision.down_revision
        if isinstance(down_revision, tuple):
            values.extend(value for value in down_revision if value)
        elif down_revision:
            values.append(down_revision)
        too_long = [value for value in values if len(value) > MAX_ALEMBIC_VERSION_LEN]
        if too_long:
            raise RuntimeError(f"Alembic revision id 超过 {MAX_ALEMBIC_VERSION_LEN} 字符，MySQL version_num 无法保存：{too_long}")


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    versions_dir = backend_dir / "migrations" / "versions"
    _remove_obsolete_migration_files(versions_dir)

    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    _validate_alembic_graph(cfg)
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        init_admin(db)


if __name__ == "__main__":
    main()
