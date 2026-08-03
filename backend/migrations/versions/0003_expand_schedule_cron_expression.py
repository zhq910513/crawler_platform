"""expand schedule cron expression length for business multi-time schedules

Revision ID: 0003_expand_schedule_cron_expression
Revises: 0002_platform_1_0_2_observability
Create Date: 2026-08-03 16:50:00
"""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa

revision = "0003_expand_schedule_cron_expression"
down_revision = "0002_platform_1_0_2_observability"
branch_labels = None
depends_on = None


def _cron_expression_length() -> int | None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "crawler_task_schedule" not in inspector.get_table_names():
        return None
    for column in inspector.get_columns("crawler_task_schedule"):
        if column["name"] != "cron_expression":
            continue
        column_type = column["type"]
        length = getattr(column_type, "length", None)
        if isinstance(length, int):
            return length
        match = re.search(r"\((\d+)\)", str(column_type))
        return int(match.group(1)) if match else None
    return None


def _alter_cron_expression_length(target_length: int, existing_length: int) -> None:
    with op.batch_alter_table("crawler_task_schedule") as batch_op:
        batch_op.alter_column(
            "cron_expression",
            existing_type=sa.String(length=existing_length),
            type_=sa.String(length=target_length),
            existing_nullable=False,
            existing_server_default=None,
        )


def upgrade() -> None:
    current_length = _cron_expression_length()
    if current_length is None or current_length >= 1000:
        return
    _alter_cron_expression_length(1000, current_length)


def downgrade() -> None:
    current_length = _cron_expression_length()
    if current_length is None or current_length <= 100:
        return
    _alter_cron_expression_length(100, current_length)
