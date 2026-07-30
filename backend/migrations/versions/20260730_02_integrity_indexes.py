"""finalize V2 scope integrity and query indexes

Revision ID: 20260730_02
Revises: 20260730_01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260730_02"
down_revision = "20260730_01"
branch_labels = None
depends_on = None




def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and any(item["name"] == column for item in inspector.get_columns(table))


def _add_column(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def _index_names(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    names = {str(item.get("name")) for item in inspector.get_indexes(table) if item.get("name")}
    names.update(str(item.get("name")) for item in inspector.get_unique_constraints(table) if item.get("name"))
    return names


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if table not in inspect(op.get_bind()).get_table_names():
        return
    if name not in _index_names(table):
        op.create_index(name, table, columns, unique=unique)


def _foreign_key_columns(table: str) -> set[tuple[str, ...]]:
    inspector = inspect(op.get_bind())
    return {
        tuple(str(column) for column in item.get("constrained_columns") or [])
        for item in inspector.get_foreign_keys(table)
    }


def _create_mysql_fk(
    name: str,
    table: str,
    columns: list[str],
    referent_table: str,
    referent_columns: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    if tuple(columns) in _foreign_key_columns(table):
        return

    left = " AND ".join(f"t.`{column}` IS NOT NULL" for column in columns)
    join = " AND ".join(
        f"t.`{column}` = r.`{referent}`"
        for column, referent in zip(columns, referent_columns, strict=True)
    )
    first_ref = referent_columns[0]
    orphan_count = bind.execute(text(
        f"SELECT COUNT(*) FROM `{table}` t "
        f"LEFT JOIN `{referent_table}` r ON {join} "
        f"WHERE {left} AND r.`{first_ref}` IS NULL"
    )).scalar() or 0
    if orphan_count:
        raise RuntimeError(
            f"cannot add foreign key {name}: {table}.{columns} has {orphan_count} orphan rows"
        )
    op.create_foreign_key(
        name,
        table,
        referent_table,
        columns,
        referent_columns,
        ondelete=ondelete,
    )


def upgrade() -> None:
    bind = op.get_bind()
    _add_column("crawler_task_run", sa.Column("runtime_json", sa.JSON(), nullable=True))

    # These columns are mandatory tenant boundaries. The first migration has
    # already backfilled all legacy rows before this constraint is applied.
    if bind.dialect.name == "mysql":
        op.alter_column("crawler_project", "company_id", existing_type=sa.BigInteger(), nullable=False)
        op.alter_column("crawler_task", "company_id", existing_type=sa.BigInteger(), nullable=False)
        op.alter_column("crawler_task_run", "company_id", existing_type=sa.BigInteger(), nullable=False)
        op.alter_column("crawler_task_run", "project_id", existing_type=sa.BigInteger(), nullable=False)

    # Existing 1.0 tables do not receive model indexes from metadata.create_all.
    # Add only the V2 indexes needed by tenant queries, claiming and SSE/error views.
    _create_index("ix_crawler_project_company_id", "crawler_project", ["company_id"])
    _create_index("ix_sys_secret_company_id", "sys_secret", ["company_id"])
    _create_index("ix_sys_secret_project_id", "sys_secret", ["project_id"])
    _create_index("ix_crawler_task_company_id", "crawler_task", ["company_id"])
    _create_index("ix_crawler_task_run_company_id", "crawler_task_run", ["company_id"])
    _create_index("ix_crawler_task_run_project_id", "crawler_task_run", ["project_id"])
    _create_index("idx_run_project_created", "crawler_task_run", ["project_id", "created_at"])
    _create_index("idx_run_status_lease", "crawler_task_run", ["status", "lease_expires_at"])
    _create_index("uk_run_parent_retry", "crawler_task_run", ["parent_run_id"], unique=True)
    _create_index("ix_crawler_agent_last_heartbeat_at", "crawler_agent", ["last_heartbeat_at"])

    # MySQL production databases get referential integrity for all fields added
    # to pre-existing tables. Fresh databases already have these constraints.
    _create_mysql_fk("fk_project_company_v2", "crawler_project", ["company_id"], "crawler_company", ["company_id"], ondelete="RESTRICT")
    _create_mysql_fk("fk_project_created_by_v2", "crawler_project", ["created_by"], "sys_user", ["user_id"], ondelete="SET NULL")
    _create_mysql_fk("fk_secret_company_v2", "sys_secret", ["company_id"], "crawler_company", ["company_id"], ondelete="CASCADE")
    _create_mysql_fk("fk_secret_project_v2", "sys_secret", ["project_id"], "crawler_project", ["project_id"], ondelete="CASCADE")
    _create_mysql_fk("fk_task_company_v2", "crawler_task", ["company_id"], "crawler_company", ["company_id"], ondelete="RESTRICT")
    _create_mysql_fk("fk_runtime_release_v2", "crawler_task_runtime", ["fixed_spider_release_id"], "crawler_spider_release", ["release_id"], ondelete="SET NULL")
    _create_mysql_fk("fk_channel_release_v2", "crawler_release_channel", ["spider_release_id"], "crawler_spider_release", ["release_id"], ondelete="SET NULL")
    _create_mysql_fk("fk_run_company_v2", "crawler_task_run", ["company_id"], "crawler_company", ["company_id"], ondelete="RESTRICT")
    _create_mysql_fk("fk_run_project_v2", "crawler_task_run", ["project_id"], "crawler_project", ["project_id"], ondelete="RESTRICT")
    _create_mysql_fk("fk_run_release_v2", "crawler_task_run", ["spider_release_id"], "crawler_spider_release", ["release_id"], ondelete="SET NULL")
    _create_mysql_fk("fk_run_entry_v2", "crawler_task_run", ["spider_entry_id"], "crawler_spider_entry", ["entry_id"], ondelete="SET NULL")
    _create_mysql_fk("fk_run_root_v2", "crawler_task_run", ["root_run_id"], "crawler_task_run", ["run_id"], ondelete="SET NULL")


def downgrade() -> None:
    # Production rollback is backup-based. Removing tenant constraints while V2
    # data exists would be destructive and is intentionally unsupported.
    pass
