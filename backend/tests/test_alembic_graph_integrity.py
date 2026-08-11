from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"
EXPECTED_FILES = ["0001_initial_platform.py", "0002_observability.py", "0003_schedule_cron_len.py", "0004_task_panel.py", "0005_110_audit.py", "0006_agent_deploy.py", "0007_account_status.py", "0008_task_contract_subject_binding.py", "0009_contract_runtime_gate.py", "0010_running_center_container_snapshots.py"]
EXPECTED_HEAD = "0010_running_center"
OBSOLETE_FILES = {
    "0002_platform_1_0_2_observability.py",
    "0003_expand_schedule_cron_expression.py",
}


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_no_obsolete_migration_files_remain() -> None:
    present = sorted(path.name for path in VERSIONS.glob("*.py") if path.name in OBSOLETE_FILES)
    assert present == []


def test_alembic_has_exactly_one_head() -> None:
    script = _script_directory()
    assert list(script.get_heads()) == [EXPECTED_HEAD]


def test_migration_file_baseline_is_explicit() -> None:
    files = sorted(path.name for path in VERSIONS.glob("*.py"))
    assert files == EXPECTED_FILES


def test_all_revision_ids_fit_mysql_alembic_version_column() -> None:
    script = _script_directory()
    for revision in script.walk_revisions():
        values = [revision.revision]
        down_revision = revision.down_revision
        if isinstance(down_revision, tuple):
            values.extend(value for value in down_revision if value)
        elif down_revision:
            values.append(down_revision)
        assert all(len(value) <= 32 for value in values)


def test_stale_legacy_files_would_create_multiple_heads(tmp_path: Path) -> None:
    """Document the exact regression that broke the test server.

    This test proves why the obsolete long-revision files must be removed from
    Git, not merely superseded by shorter migrations.
    """
    versions = tmp_path / "versions"
    versions.mkdir(parents=True)
    (tmp_path / "script.py.mako").write_text("", encoding="utf-8")
    (tmp_path / "env.py").write_text("", encoding="utf-8")
    (versions / "0001.py").write_text('revision="0001_initial_platform"\ndown_revision=None\n', encoding="utf-8")
    (versions / "0002_new.py").write_text('revision="0002_observability"\ndown_revision="0001_initial_platform"\n', encoding="utf-8")
    (versions / "0003_new.py").write_text('revision="0003_schedule_cron_len"\ndown_revision="0002_observability"\n', encoding="utf-8")
    (versions / "0002_old.py").write_text('revision="0002_platform_1_0_2_observability"\ndown_revision="0001_initial_platform"\n', encoding="utf-8")
    (versions / "0003_old.py").write_text('revision="0003_expand_schedule_cron_expression"\ndown_revision="0002_platform_1_0_2_observability"\n', encoding="utf-8")
    cfg = Config()
    cfg.set_main_option("script_location", str(tmp_path))
    script = ScriptDirectory.from_config(cfg)
    assert sorted(script.get_heads()) == ["0003_expand_schedule_cron_expression", "0003_schedule_cron_len"]


def test_deploy_alembic_graph_checker_has_no_third_party_dependency() -> None:
    checker = ROOT.parent / "deploy" / "scripts" / "check-alembic-graph.py"
    source = checker.read_text(encoding="utf-8")
    assert "from alembic" not in source
    assert "import alembic" not in source
