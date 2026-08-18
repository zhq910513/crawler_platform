"""Agent lifecycle desired state and node snapshots

Revision ID: 0015_agent_lifecycle
Revises: 0014_agent_install_feedback
Create Date: 2026-08-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "0015_agent_lifecycle"
down_revision = "0014_agent_install_feedback"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    bind = op.get_bind()
    try:
        return {col["name"] for col in inspect(bind).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    server_cols = _cols("crawler_server")
    if "desired_state" not in server_cols:
        op.add_column("crawler_server", sa.Column("desired_state", sa.String(30), nullable=False, server_default="ONLINE"))
    if "desired_agent_version" not in server_cols:
        op.add_column("crawler_server", sa.Column("desired_agent_version", sa.String(50), nullable=False, server_default=""))
    if "lifecycle_status" not in server_cols:
        op.add_column("crawler_server", sa.Column("lifecycle_status", sa.String(30), nullable=False, server_default="IDLE"))
    if "lifecycle_action" not in server_cols:
        op.add_column("crawler_server", sa.Column("lifecycle_action", sa.String(50), nullable=False, server_default=""))
    if "lifecycle_error" not in server_cols:
        op.add_column("crawler_server", sa.Column("lifecycle_error", sa.Text(), nullable=True))
        try:
            op.get_bind().execute(text("UPDATE crawler_server SET lifecycle_error = '' WHERE lifecycle_error IS NULL"))
            op.alter_column("crawler_server", "lifecycle_error", existing_type=sa.Text(), nullable=False)
        except Exception:
            pass
    if "lifecycle_started_at" not in server_cols:
        op.add_column("crawler_server", sa.Column("lifecycle_started_at", sa.DateTime(), nullable=True))
    if "previous_manage_status" not in server_cols:
        op.add_column("crawler_server", sa.Column("previous_manage_status", sa.String(20), nullable=False, server_default=""))
    try:
        op.create_index("ix_crawler_server_desired_state", "crawler_server", ["desired_state"])
    except Exception:
        pass
    try:
        op.create_index("ix_crawler_server_lifecycle_status", "crawler_server", ["lifecycle_status"])
    except Exception:
        pass
    try:
        op.create_index("ix_crawler_server_lifecycle_action", "crawler_server", ["lifecycle_action"])
    except Exception:
        pass
    bind = op.get_bind()
    try:
        bind.execute(text("UPDATE crawler_server SET desired_state = CASE WHEN manage_status = 'MAINTENANCE' THEN 'MAINTENANCE' WHEN manage_status = 'DISABLED' THEN 'DISABLED' ELSE 'ONLINE' END WHERE desired_state = 'ONLINE' OR desired_state IS NULL"))
    except Exception:
        pass

    agent_cols = _cols("crawler_agent")
    if "upgrade_stable_count" not in agent_cols:
        op.add_column("crawler_agent", sa.Column("upgrade_stable_count", sa.Integer(), nullable=False, server_default="0"))
    try:
        bind.execute(text("UPDATE crawler_agent SET protocol_version = '1.0' WHERE protocol_version = '3.0' OR protocol_version IS NULL OR protocol_version = ''"))
    except Exception:
        pass

    run_cols = _cols("crawler_task_run")
    if "execution_node_snapshot" not in run_cols:
        op.add_column("crawler_task_run", sa.Column("execution_node_snapshot", sa.JSON(), nullable=True))
        try:
            op.get_bind().execute(text("UPDATE crawler_task_run SET execution_node_snapshot = '{}' WHERE execution_node_snapshot IS NULL"))
            op.alter_column("crawler_task_run", "execution_node_snapshot", existing_type=sa.JSON(), nullable=False)
        except Exception:
            pass


def downgrade() -> None:
    run_cols = _cols("crawler_task_run")
    if "execution_node_snapshot" in run_cols:
        op.drop_column("crawler_task_run", "execution_node_snapshot")
    agent_cols = _cols("crawler_agent")
    if "upgrade_stable_count" in agent_cols:
        op.drop_column("crawler_agent", "upgrade_stable_count")
    server_cols = _cols("crawler_server")
    for index_name in ("ix_crawler_server_lifecycle_action", "ix_crawler_server_lifecycle_status", "ix_crawler_server_desired_state"):
        try:
            op.drop_index(index_name, table_name="crawler_server")
        except Exception:
            pass
    for col in ("previous_manage_status", "lifecycle_started_at", "lifecycle_error", "lifecycle_action", "lifecycle_status", "desired_agent_version", "desired_state"):
        if col in server_cols:
            op.drop_column("crawler_server", col)
