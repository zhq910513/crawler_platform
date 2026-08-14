"""agent join invitation lifecycle

Revision ID: 0012_agent_join_invitation
Revises: 0011_preflight_snapshot
Create Date: 2026-08-14 14:43:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_agent_join_invitation"
down_revision = "0011_preflight_snapshot"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _cols(table: str) -> set[str]:
    return {c.get("name") for c in _insp().get_columns(table)} if _table_exists(table) else set()


def _idx_exists(table: str, name: str) -> bool:
    return _table_exists(table) and any(i.get("name") == name for i in _insp().get_indexes(table))


def upgrade() -> None:
    cols = _cols("crawler_agent_join_token")
    if "invitation_status" not in cols:
        op.add_column("crawler_agent_join_token", sa.Column("invitation_status", sa.String(30), nullable=False, server_default="PENDING"))
    if "activated_at" not in cols:
        op.add_column("crawler_agent_join_token", sa.Column("activated_at", sa.DateTime(), nullable=True))
    if "failed_at" not in cols:
        op.add_column("crawler_agent_join_token", sa.Column("failed_at", sa.DateTime(), nullable=True))
    if "failure_stage" not in cols:
        op.add_column("crawler_agent_join_token", sa.Column("failure_stage", sa.String(120), nullable=False, server_default=""))
    if "failure_reason" not in cols:
        op.add_column("crawler_agent_join_token", sa.Column("failure_reason", sa.Text(), nullable=True))
    if not _idx_exists("crawler_agent_join_token", "ix_agent_join_invitation_status"):
        op.create_index("ix_agent_join_invitation_status", "crawler_agent_join_token", ["invitation_status"])


def downgrade() -> None:
    if _idx_exists("crawler_agent_join_token", "ix_agent_join_invitation_status"):
        op.drop_index("ix_agent_join_invitation_status", table_name="crawler_agent_join_token")
    for col in ["failure_reason", "failure_stage", "failed_at", "activated_at", "invitation_status"]:
        if col in _cols("crawler_agent_join_token"):
            op.drop_column("crawler_agent_join_token", col)
