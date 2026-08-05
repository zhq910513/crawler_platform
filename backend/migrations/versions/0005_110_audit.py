"""1.0.11 audit hardening indexes

Revision ID: 0005_110_audit
Revises: 0004_task_panel
Create Date: 2026-08-04 17:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_110_audit"
down_revision = "0004_task_panel"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _named_index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(index.get("name") == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _index_exists(table_name: str, index_name: str, columns: list[str]) -> bool:
    if not _table_exists(table_name):
        return False
    for index in sa.inspect(op.get_bind()).get_indexes(table_name):
        if index.get("name") == index_name or list(index.get("column_names") or []) == columns:
            return True
    return False


def upgrade() -> None:
    if not _index_exists("crawler_task_run", "idx_run_task_parent_last", ["task_id", "parent_run_id", "run_id"]):
        op.create_index("idx_run_task_parent_last", "crawler_task_run", ["task_id", "parent_run_id", "run_id"], unique=False)


def downgrade() -> None:
    if _named_index_exists("crawler_task_run", "idx_run_task_parent_last"):
        op.drop_index("idx_run_task_parent_last", table_name="crawler_task_run")
