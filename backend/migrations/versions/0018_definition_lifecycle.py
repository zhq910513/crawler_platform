"""Task definition lifecycle and orchestration decisions.

Revision ID: 0018_definition_lifecycle
Revises: 0017_project_build_center
Create Date: 2026-08-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "0018_definition_lifecycle"
down_revision = "0017_project_build_center"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {item["name"] for item in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    try:
        return {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return set()


def upgrade() -> None:
    table = "crawler_project_task_definition"
    columns = _columns(table)
    with op.batch_alter_table(table) as batch:
        if "discovery_status" not in columns:
            batch.add_column(sa.Column("discovery_status", sa.String(30), nullable=False, server_default="ACTIVE"))
        if "orchestration_status" not in columns:
            batch.add_column(sa.Column("orchestration_status", sa.String(30), nullable=False, server_default="PENDING"))
        if "first_seen_release_id" not in columns:
            batch.add_column(sa.Column("first_seen_release_id", sa.BigInteger(), nullable=True))
            batch.create_foreign_key("fk_task_def_first_release", "crawler_project_release", ["first_seen_release_id"], ["release_id"], ondelete="SET NULL")
        if "last_seen_at" not in columns:
            batch.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        if "ignored_at" not in columns:
            batch.add_column(sa.Column("ignored_at", sa.DateTime(), nullable=True))
        if "ignored_by" not in columns:
            batch.add_column(sa.Column("ignored_by", sa.BigInteger(), nullable=True))
            batch.create_foreign_key("fk_task_def_ignored_by", "sys_user", ["ignored_by"], ["user_id"], ondelete="SET NULL")
        if "ignore_reason" not in columns:
            batch.add_column(sa.Column("ignore_reason", sa.String(500), nullable=False, server_default=""))

    if "definition_status" in _columns(table):
        if "ix_crawler_project_task_definition_definition_status" in _indexes(table):
            op.drop_index("ix_crawler_project_task_definition_definition_status", table_name=table)
        op.get_bind().execute(text("""
            UPDATE crawler_project_task_definition
            SET discovery_status = CASE
                    WHEN definition_status = 'REMOVED' THEN 'REMOVED'
                    WHEN definition_status = 'PARSE_ERROR' THEN 'INVALID'
                    ELSE 'ACTIVE'
                END,
                orchestration_status = CASE
                    WHEN definition_status = 'CREATED' THEN 'ORCHESTRATED'
                    ELSE 'PENDING'
                END,
                first_seen_release_id = COALESCE(first_seen_release_id, latest_release_id),
                last_seen_at = COALESCE(last_seen_at, updated_at)
        """))
        with op.batch_alter_table(table) as batch:
            batch.drop_column("definition_status")

    indexes = _indexes(table)
    for name, cols in {
        "ix_task_def_discovery_status": ["discovery_status"],
        "ix_task_def_orchestration_status": ["orchestration_status"],
        "ix_task_def_first_release": ["first_seen_release_id"],
        "ix_task_def_last_seen_at": ["last_seen_at"],
        "ix_task_def_ignored_at": ["ignored_at"],
        "ix_task_def_ignored_by": ["ignored_by"],
    }.items():
        if name not in indexes:
            op.create_index(name, table, cols)


def downgrade() -> None:
    table = "crawler_project_task_definition"
    indexes = _indexes(table)
    for name in (
        "ix_task_def_ignored_by", "ix_task_def_ignored_at", "ix_task_def_last_seen_at",
        "ix_task_def_first_release", "ix_task_def_orchestration_status", "ix_task_def_discovery_status",
    ):
        if name in indexes:
            op.drop_index(name, table_name=table)
    if "definition_status" not in _columns(table):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("definition_status", sa.String(30), nullable=False, server_default="AVAILABLE"))
        op.get_bind().execute(text("""
            UPDATE crawler_project_task_definition
            SET definition_status = CASE
                WHEN discovery_status = 'REMOVED' THEN 'REMOVED'
                WHEN discovery_status = 'INVALID' THEN 'PARSE_ERROR'
                WHEN orchestration_status = 'ORCHESTRATED' THEN 'CREATED'
                ELSE 'AVAILABLE'
            END
        """))
        op.create_index("ix_crawler_project_task_definition_definition_status", table, ["definition_status"])
    columns = _columns(table)
    with op.batch_alter_table(table) as batch:
        for name in ("ignore_reason", "ignored_by", "ignored_at", "last_seen_at", "first_seen_release_id", "orchestration_status", "discovery_status"):
            if name in columns:
                batch.drop_column(name)
