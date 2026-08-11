"""running center and container snapshots

Revision ID: 0010_running_center
Revises: 0009_contract_runtime_gate
Create Date: 2026-08-11 11:36:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_running_center"
down_revision = "0009_contract_runtime_gate"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _idx_exists(table: str, name: str) -> bool:
    return _table_exists(table) and any(i.get("name") == name for i in _insp().get_indexes(table))


def _create_index(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    if _table_exists(table) and not _idx_exists(table, name):
        op.create_index(name, table, cols, unique=unique)


def _drop_index(name: str, table: str) -> None:
    if _idx_exists(table, name):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    if not _table_exists("crawler_run_container_snapshot"):
        op.create_table(
            "crawler_run_container_snapshot",
            sa.Column("snapshot_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("run_id", sa.BigInteger(), nullable=False),
            sa.Column("task_id", sa.BigInteger(), nullable=False),
            sa.Column("project_id", sa.BigInteger(), nullable=False),
            sa.Column("server_id", sa.BigInteger(), nullable=True),
            sa.Column("agent_id", sa.BigInteger(), nullable=True),
            sa.Column("container_id", sa.String(128), nullable=False, server_default=""),
            sa.Column("container_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("image_digest", sa.String(100), nullable=False, server_default=""),
            sa.Column("container_status", sa.String(40), nullable=False, server_default="UNKNOWN"),
            sa.Column("exit_code", sa.Integer(), nullable=True),
            sa.Column("oom_killed", sa.Boolean(), nullable=True),
            sa.Column("restart_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cpu_usage", sa.Float(), nullable=True),
            sa.Column("memory_usage_mb", sa.Float(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("last_log_line", sa.String(1000), nullable=False, server_default=""),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_id"], ["crawler_task_run.run_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["crawler_task.task_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["crawler_project.project_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["crawler_server.server_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["agent_id"], ["crawler_agent.agent_id"], ondelete="SET NULL"),
        )
    for name, cols in [
        ("ix_run_container_company", ["company_id"]),
        ("ix_run_container_run", ["run_id"]),
        ("ix_run_container_task", ["task_id"]),
        ("ix_run_container_project", ["project_id"]),
        ("ix_run_container_server", ["server_id"]),
        ("ix_run_container_agent", ["agent_id"]),
        ("ix_run_container_id", ["container_id"]),
        ("ix_run_container_status", ["container_status"]),
        ("ix_run_container_observed", ["observed_at"]),
        ("idx_run_container_latest", ["run_id", "observed_at"]),
    ]:
        _create_index(name, "crawler_run_container_snapshot", cols)


def downgrade() -> None:
    for name in [
        "idx_run_container_latest", "ix_run_container_observed", "ix_run_container_status", "ix_run_container_id",
        "ix_run_container_agent", "ix_run_container_server", "ix_run_container_project", "ix_run_container_task",
        "ix_run_container_run", "ix_run_container_company",
    ]:
        _drop_index(name, "crawler_run_container_snapshot")
    if _table_exists("crawler_run_container_snapshot"):
        op.drop_table("crawler_run_container_snapshot")
