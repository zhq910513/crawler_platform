"""agent image digest tracking

Revision ID: 0013_agent_image_digest
Revises: 0012_agent_join_invitation
Create Date: 2026-08-14 14:44:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_agent_image_digest"
down_revision = "0012_agent_join_invitation"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _cols(table: str) -> set[str]:
    return {c.get("name") for c in _insp().get_columns(table)} if _table_exists(table) else set()


def upgrade() -> None:
    cols = _cols("crawler_agent")
    if "agent_image" not in cols:
        op.add_column("crawler_agent", sa.Column("agent_image", sa.String(500), nullable=False, server_default=""))
    if "agent_image_digest" not in cols:
        op.add_column("crawler_agent", sa.Column("agent_image_digest", sa.String(120), nullable=False, server_default=""))


def downgrade() -> None:
    for col in ["agent_image_digest", "agent_image"]:
        if col in _cols("crawler_agent"):
            op.drop_column("crawler_agent", col)
