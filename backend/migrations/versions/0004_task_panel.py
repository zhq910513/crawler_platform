"""task schedule panel owner and query indexes

Revision ID: 0004_task_panel
Revises: 0003_schedule_cron_len
Create Date: 2026-08-04 16:45:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_task_panel"
down_revision = "0003_schedule_cron_len"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


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


def _named_foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(foreign_key.get("name") == constraint_name for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name))


def _foreign_key_exists(table_name: str, constraint_name: str, columns: list[str]) -> bool:
    if not _table_exists(table_name):
        return False
    for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name):
        if foreign_key.get("name") == constraint_name or list(foreign_key.get("constrained_columns") or []) == columns:
            return True
    return False


def upgrade() -> None:
    if not _column_exists("crawler_task", "owner_user_id"):
        op.add_column("crawler_task", sa.Column("owner_user_id", sa.BigInteger(), nullable=True))
    if not _index_exists("crawler_task", "idx_task_owner_user", ["owner_user_id"]):
        op.create_index("idx_task_owner_user", "crawler_task", ["owner_user_id"], unique=False)
    if not _index_exists("crawler_task_run", "idx_run_task_last", ["task_id", "run_id"]):
        op.create_index("idx_run_task_last", "crawler_task_run", ["task_id", "run_id"], unique=False)
    if op.get_bind().dialect.name != "sqlite" and not _foreign_key_exists("crawler_task", "fk_task_owner_user", ["owner_user_id"]):
        op.create_foreign_key("fk_task_owner_user", "crawler_task", "sys_user", ["owner_user_id"], ["user_id"], ondelete="SET NULL")


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite" and _named_foreign_key_exists("crawler_task", "fk_task_owner_user"):
        op.drop_constraint("fk_task_owner_user", "crawler_task", type_="foreignkey")
    if _named_index_exists("crawler_task_run", "idx_run_task_last"):
        op.drop_index("idx_run_task_last", table_name="crawler_task_run")
    if _named_index_exists("crawler_task", "idx_task_owner_user"):
        op.drop_index("idx_task_owner_user", table_name="crawler_task")
    if _column_exists("crawler_task", "owner_user_id"):
        op.drop_column("crawler_task", "owner_user_id")
