from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


ROOT = Path(__file__).resolve().parents[1]


def _load_revision(filename: str):
    path = ROOT / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _run_revision_upgrade(connection: sa.Connection, filename: str) -> None:
    module = _load_revision(filename)
    context = MigrationContext.configure(connection)
    module.op = Operations(context)
    module.upgrade()


def test_observability_migration_recovers_half_migrated_database(tmp_path: Path) -> None:
    """0002 must recover the MySQL half-migration state seen on test server.

    A previous 0002 added columns first, then failed on MySQL because
    alter_column(diagnosis_json) lacked existing_type.  Customer databases can
    therefore have 1.0.2 columns already present while alembic_version remains
    at 0001.  Rerunning 0002 must skip existing columns, finish missing tables
    and make diagnosis_json NOT NULL.
    """
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'half.db'}")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE sys_user (user_id INTEGER PRIMARY KEY, password_updated_at DATETIME NULL, must_change_password BOOLEAN NOT NULL)"))
        connection.execute(
            sa.text(
                """
                CREATE TABLE crawler_task_run (
                    run_id INTEGER PRIMARY KEY,
                    log_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
                    log_storage_type VARCHAR(30) NOT NULL DEFAULT 'DB_CHUNK',
                    log_path VARCHAR(500) NOT NULL DEFAULT '',
                    log_bytes BIGINT NOT NULL DEFAULT 0,
                    log_lines INTEGER NOT NULL DEFAULT 0,
                    last_log_seq INTEGER NOT NULL DEFAULT 0,
                    last_log_at DATETIME NULL,
                    log_truncated BOOLEAN NOT NULL DEFAULT 0,
                    failed_stage VARCHAR(80) NOT NULL DEFAULT '',
                    error_type VARCHAR(100) NOT NULL DEFAULT '',
                    error_summary VARCHAR(1000) NOT NULL DEFAULT '',
                    retryable BOOLEAN NULL,
                    diagnosis_json JSON NULL
                )
                """
            )
        )
        connection.execute(sa.text("CREATE TABLE crawler_task_schedule (schedule_id INTEGER PRIMARY KEY, cron_expression VARCHAR(100) NOT NULL)"))
        connection.execute(sa.text("INSERT INTO crawler_task_run (run_id, diagnosis_json) VALUES (1, NULL)"))

        _run_revision_upgrade(connection, "0002_observability.py")
        _run_revision_upgrade(connection, "0002_observability.py")
        _run_revision_upgrade(connection, "0003_schedule_cron_len.py")
        _run_revision_upgrade(connection, "0003_schedule_cron_len.py")

        inspector = sa.inspect(connection)
        assert "crawler_run_event" in inspector.get_table_names()
        assert "crawler_run_log_chunk" in inspector.get_table_names()
        run_columns = {column["name"]: column for column in inspector.get_columns("crawler_task_run")}
        assert run_columns["diagnosis_json"]["nullable"] is False
        schedule_columns = {column["name"]: column for column in inspector.get_columns("crawler_task_schedule")}
        assert getattr(schedule_columns["cron_expression"]["type"], "length", None) == 1000
        diagnosis = connection.execute(sa.text("SELECT diagnosis_json FROM crawler_task_run WHERE run_id = 1")).scalar_one()
        assert diagnosis in ("{}", {})


def test_migration_revision_ids_fit_default_alembic_version_column() -> None:
    """Alembic's default MySQL alembic_version.version_num is VARCHAR(32)."""
    revision_0002 = _load_revision("0002_observability.py")
    revision_0003 = _load_revision("0003_schedule_cron_len.py")
    for value in [revision_0002.revision, revision_0002.down_revision, revision_0003.revision, revision_0003.down_revision]:
        assert len(value) <= 32
    assert revision_0003.down_revision == revision_0002.revision
