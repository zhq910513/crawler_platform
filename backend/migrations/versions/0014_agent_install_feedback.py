"""Agent install feedback and actual digest

Revision ID: 0014_agent_install_feedback
Revises: 0013_agent_image_digest
Create Date: 2026-08-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0014_agent_install_feedback"
down_revision = "0013_agent_image_digest"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    bind = op.get_bind()
    try:
        return {col["name"] for col in inspect(bind).get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    cols = _cols("crawler_agent")
    if "agent_image_actual_digest" not in cols:
        op.add_column("crawler_agent", sa.Column("agent_image_actual_digest", sa.String(120), nullable=False, server_default=""))


def downgrade() -> None:
    cols = _cols("crawler_agent")
    if "agent_image_actual_digest" in cols:
        op.drop_column("crawler_agent", "agent_image_actual_digest")
