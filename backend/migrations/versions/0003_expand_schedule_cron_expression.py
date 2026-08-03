"""expand schedule cron expression length for business multi-time schedules

Revision ID: 0003_expand_schedule_cron_expression
Revises: 0002_platform_1_0_2_observability
Create Date: 2026-08-03 16:50:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_expand_schedule_cron_expression"
down_revision = "0002_platform_1_0_2_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("crawler_task_schedule") as batch_op:
        batch_op.alter_column(
            "cron_expression",
            existing_type=sa.String(length=100),
            type_=sa.String(length=1000),
            existing_nullable=False,
            existing_server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("crawler_task_schedule") as batch_op:
        batch_op.alter_column(
            "cron_expression",
            existing_type=sa.String(length=1000),
            type_=sa.String(length=100),
            existing_nullable=False,
            existing_server_default=None,
        )
