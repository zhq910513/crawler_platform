"""platform 1.0.2 password schedule observability

Revision ID: 0002_platform_1_0_2_observability
Revises: 0001_initial_platform
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0002_platform_1_0_2_observability"
down_revision = "0001_initial_platform"
branch_labels = None
depends_on = None


def _bind() -> sa.engine.Connection:
    return op.get_bind()


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in set(_inspector().get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {column["name"] for column in _inspector().get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    indexes = {index["name"] for index in _inspector().get_indexes(table_name)}
    unique_constraints = {constraint["name"] for constraint in _inspector().get_unique_constraints(table_name)}
    return index_name in indexes or index_name in unique_constraints


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _column_exists(table_name, column.name):
        return
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if not _column_exists(table_name, column_name):
        return
    with op.batch_alter_table(table_name) as batch:
        batch.drop_column(column_name)


def _alter_column(
    table_name: str,
    column_name: str,
    *,
    existing_type: sa.types.TypeEngine,
    existing_nullable: bool,
    nullable: bool | None = None,
    server_default: str | sa.sql.elements.TextClause | None | bool = False,
) -> None:
    """Alembic helper that is safe on MySQL.

    MySQL CHANGE/MODIFY COLUMN requires existing_type.  A previous version of
    this migration omitted it and could leave customer databases half-migrated:
    new columns existed, but alembic_version still pointed at 0001.  This helper
    is intentionally explicit so rerunning 0002 can recover that state.
    """
    if not _column_exists(table_name, column_name):
        return
    kwargs: dict[str, object] = {
        "existing_type": existing_type,
        "existing_nullable": existing_nullable,
    }
    if nullable is not None:
        kwargs["nullable"] = nullable
    if server_default is not False:
        kwargs["server_default"] = server_default
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column(column_name, **kwargs)


def _create_index_if_missing(table_name: str, index_name: str, columns: Sequence[str], *, unique: bool = False) -> None:
    if _index_exists(table_name, index_name):
        return
    op.create_index(index_name, table_name, list(columns), unique=unique)


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if not _index_exists(table_name, index_name):
        return
    op.drop_index(index_name, table_name=table_name)


def _create_run_event_table() -> None:
    if _table_exists("crawler_run_event"):
        return
    op.create_table(
        "crawler_run_event",
        sa.Column("event_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_level", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def _create_log_chunk_table() -> None:
    if _table_exists("crawler_run_log_chunk"):
        return
    op.create_table(
        "crawler_run_log_chunk",
        sa.Column("chunk_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("stream", sa.String(20), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("offset_start", sa.BigInteger(), nullable=False),
        sa.Column("offset_end", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("run_id", "stream", "seq", name="uk_run_log_chunk_seq"),
    )


def upgrade() -> None:
    # 账号安全字段。add_column 使用 server_default，随后移除默认值，兼容已有数据。
    _add_column_if_missing("sys_user", sa.Column("password_updated_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("sys_user", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    _alter_column(
        "sys_user",
        "must_change_password",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )

    # 日志 V2 run 摘要字段。重复执行时跳过已存在字段，支持半迁移恢复。
    run_columns: list[tuple[sa.Column, sa.types.TypeEngine, bool]] = [
        (sa.Column("log_status", sa.String(30), nullable=False, server_default="PENDING"), sa.String(30), False),
        (sa.Column("log_storage_type", sa.String(30), nullable=False, server_default="DB_CHUNK"), sa.String(30), False),
        (sa.Column("log_path", sa.String(500), nullable=False, server_default=""), sa.String(500), False),
        (sa.Column("log_bytes", sa.BigInteger(), nullable=False, server_default="0"), sa.BigInteger(), False),
        (sa.Column("log_lines", sa.Integer(), nullable=False, server_default="0"), sa.Integer(), False),
        (sa.Column("last_log_seq", sa.Integer(), nullable=False, server_default="0"), sa.Integer(), False),
        (sa.Column("last_log_at", sa.DateTime(), nullable=True), sa.DateTime(), True),
        (sa.Column("log_truncated", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Boolean(), False),
        (sa.Column("failed_stage", sa.String(80), nullable=False, server_default=""), sa.String(80), False),
        (sa.Column("error_type", sa.String(100), nullable=False, server_default=""), sa.String(100), False),
        (sa.Column("error_summary", sa.String(1000), nullable=False, server_default=""), sa.String(1000), False),
        (sa.Column("retryable", sa.Boolean(), nullable=True), sa.Boolean(), True),
        (sa.Column("diagnosis_json", sa.JSON(), nullable=True), sa.JSON(), True),
    ]
    for column, _existing_type, _existing_nullable in run_columns:
        _add_column_if_missing("crawler_task_run", column)

    if _column_exists("crawler_task_run", "diagnosis_json"):
        op.execute("UPDATE crawler_task_run SET diagnosis_json = '{}' WHERE diagnosis_json IS NULL")
        _alter_column(
            "crawler_task_run",
            "diagnosis_json",
            existing_type=sa.JSON(),
            existing_nullable=True,
            nullable=False,
        )

    defaulted_columns: list[tuple[str, sa.types.TypeEngine]] = [
        ("log_status", sa.String(30)),
        ("log_storage_type", sa.String(30)),
        ("log_path", sa.String(500)),
        ("log_bytes", sa.BigInteger()),
        ("log_lines", sa.Integer()),
        ("last_log_seq", sa.Integer()),
        ("log_truncated", sa.Boolean()),
        ("failed_stage", sa.String(80)),
        ("error_type", sa.String(100)),
        ("error_summary", sa.String(1000)),
    ]
    for column_name, existing_type in defaulted_columns:
        _alter_column(
            "crawler_task_run",
            column_name,
            existing_type=existing_type,
            existing_nullable=False,
            server_default=None,
        )

    _create_run_event_table()
    _create_index_if_missing("crawler_run_event", "ix_crawler_run_event_company_id", ["company_id"])
    _create_index_if_missing("crawler_run_event", "ix_crawler_run_event_run_id", ["run_id"])
    _create_index_if_missing("crawler_run_event", "ix_crawler_run_event_event_type", ["event_type"])
    _create_index_if_missing("crawler_run_event", "ix_crawler_run_event_event_level", ["event_level"])
    _create_index_if_missing("crawler_run_event", "ix_crawler_run_event_stage", ["stage"])
    _create_index_if_missing("crawler_run_event", "ix_crawler_run_event_created_at", ["created_at"])
    _create_index_if_missing("crawler_run_event", "idx_run_event_run_created", ["run_id", "created_at"])

    _create_log_chunk_table()
    _create_index_if_missing("crawler_run_log_chunk", "ix_crawler_run_log_chunk_company_id", ["company_id"])
    _create_index_if_missing("crawler_run_log_chunk", "ix_crawler_run_log_chunk_run_id", ["run_id"])
    _create_index_if_missing("crawler_run_log_chunk", "ix_crawler_run_log_chunk_stream", ["stream"])
    _create_index_if_missing("crawler_run_log_chunk", "ix_crawler_run_log_chunk_created_at", ["created_at"])
    _create_index_if_missing("crawler_run_log_chunk", "idx_run_log_chunk_run_seq", ["run_id", "seq"])


def downgrade() -> None:
    _drop_index_if_exists("crawler_run_log_chunk", "idx_run_log_chunk_run_seq")
    _drop_index_if_exists("crawler_run_log_chunk", "ix_crawler_run_log_chunk_created_at")
    _drop_index_if_exists("crawler_run_log_chunk", "ix_crawler_run_log_chunk_stream")
    _drop_index_if_exists("crawler_run_log_chunk", "ix_crawler_run_log_chunk_run_id")
    _drop_index_if_exists("crawler_run_log_chunk", "ix_crawler_run_log_chunk_company_id")
    if _table_exists("crawler_run_log_chunk"):
        op.drop_table("crawler_run_log_chunk")

    _drop_index_if_exists("crawler_run_event", "idx_run_event_run_created")
    _drop_index_if_exists("crawler_run_event", "ix_crawler_run_event_created_at")
    _drop_index_if_exists("crawler_run_event", "ix_crawler_run_event_stage")
    _drop_index_if_exists("crawler_run_event", "ix_crawler_run_event_event_level")
    _drop_index_if_exists("crawler_run_event", "ix_crawler_run_event_event_type")
    _drop_index_if_exists("crawler_run_event", "ix_crawler_run_event_run_id")
    _drop_index_if_exists("crawler_run_event", "ix_crawler_run_event_company_id")
    if _table_exists("crawler_run_event"):
        op.drop_table("crawler_run_event")

    for column_name in [
        "diagnosis_json",
        "retryable",
        "error_summary",
        "error_type",
        "failed_stage",
        "log_truncated",
        "last_log_at",
        "last_log_seq",
        "log_lines",
        "log_bytes",
        "log_path",
        "log_storage_type",
        "log_status",
    ]:
        _drop_column_if_exists("crawler_task_run", column_name)

    for column_name in ["must_change_password", "password_updated_at"]:
        _drop_column_if_exists("sys_user", column_name)
