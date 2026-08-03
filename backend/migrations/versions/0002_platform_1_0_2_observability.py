"""platform 1.0.2 password schedule observability

Revision ID: 0002_platform_1_0_2_observability
Revises: 0001_initial_platform
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_platform_1_0_2_observability"
down_revision = "0001_initial_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sys_user") as batch:
        batch.add_column(sa.Column("password_updated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("sys_user") as batch:
        batch.alter_column("must_change_password", server_default=None)

    with op.batch_alter_table("crawler_task_run") as batch:
        batch.add_column(sa.Column("log_status", sa.String(30), nullable=False, server_default="PENDING"))
        batch.add_column(sa.Column("log_storage_type", sa.String(30), nullable=False, server_default="DB_CHUNK"))
        batch.add_column(sa.Column("log_path", sa.String(500), nullable=False, server_default=""))
        batch.add_column(sa.Column("log_bytes", sa.BigInteger(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("log_lines", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_log_seq", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_log_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("log_truncated", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("failed_stage", sa.String(80), nullable=False, server_default=""))
        batch.add_column(sa.Column("error_type", sa.String(100), nullable=False, server_default=""))
        batch.add_column(sa.Column("error_summary", sa.String(1000), nullable=False, server_default=""))
        batch.add_column(sa.Column("retryable", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("diagnosis_json", sa.JSON(), nullable=True))
    op.execute("UPDATE crawler_task_run SET diagnosis_json = '{}' WHERE diagnosis_json IS NULL")
    with op.batch_alter_table("crawler_task_run") as batch:
        batch.alter_column("diagnosis_json", nullable=False)
    for name in ["log_status", "log_storage_type", "log_path", "log_bytes", "log_lines", "last_log_seq", "log_truncated", "failed_stage", "error_type", "error_summary"]:
        with op.batch_alter_table("crawler_task_run") as batch:
            batch.alter_column(name, server_default=None)

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
    op.create_index("ix_crawler_run_event_company_id", "crawler_run_event", ["company_id"])
    op.create_index("ix_crawler_run_event_run_id", "crawler_run_event", ["run_id"])
    op.create_index("ix_crawler_run_event_event_type", "crawler_run_event", ["event_type"])
    op.create_index("ix_crawler_run_event_event_level", "crawler_run_event", ["event_level"])
    op.create_index("ix_crawler_run_event_stage", "crawler_run_event", ["stage"])
    op.create_index("ix_crawler_run_event_created_at", "crawler_run_event", ["created_at"])
    op.create_index("idx_run_event_run_created", "crawler_run_event", ["run_id", "created_at"])

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
    op.create_index("ix_crawler_run_log_chunk_company_id", "crawler_run_log_chunk", ["company_id"])
    op.create_index("ix_crawler_run_log_chunk_run_id", "crawler_run_log_chunk", ["run_id"])
    op.create_index("ix_crawler_run_log_chunk_stream", "crawler_run_log_chunk", ["stream"])
    op.create_index("ix_crawler_run_log_chunk_created_at", "crawler_run_log_chunk", ["created_at"])
    op.create_index("idx_run_log_chunk_run_seq", "crawler_run_log_chunk", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("idx_run_log_chunk_run_seq", table_name="crawler_run_log_chunk")
    op.drop_index("ix_crawler_run_log_chunk_created_at", table_name="crawler_run_log_chunk")
    op.drop_index("ix_crawler_run_log_chunk_stream", table_name="crawler_run_log_chunk")
    op.drop_index("ix_crawler_run_log_chunk_run_id", table_name="crawler_run_log_chunk")
    op.drop_index("ix_crawler_run_log_chunk_company_id", table_name="crawler_run_log_chunk")
    op.drop_table("crawler_run_log_chunk")
    op.drop_index("idx_run_event_run_created", table_name="crawler_run_event")
    op.drop_index("ix_crawler_run_event_created_at", table_name="crawler_run_event")
    op.drop_index("ix_crawler_run_event_stage", table_name="crawler_run_event")
    op.drop_index("ix_crawler_run_event_event_level", table_name="crawler_run_event")
    op.drop_index("ix_crawler_run_event_event_type", table_name="crawler_run_event")
    op.drop_index("ix_crawler_run_event_run_id", table_name="crawler_run_event")
    op.drop_index("ix_crawler_run_event_company_id", table_name="crawler_run_event")
    op.drop_table("crawler_run_event")
    with op.batch_alter_table("crawler_task_run") as batch:
        batch.drop_column("diagnosis_json")
        batch.drop_column("retryable")
        batch.drop_column("error_summary")
        batch.drop_column("error_type")
        batch.drop_column("failed_stage")
        batch.drop_column("log_truncated")
        batch.drop_column("last_log_at")
        batch.drop_column("last_log_seq")
        batch.drop_column("log_lines")
        batch.drop_column("log_bytes")
        batch.drop_column("log_path")
        batch.drop_column("log_storage_type")
        batch.drop_column("log_status")
    with op.batch_alter_table("sys_user") as batch:
        batch.drop_column("must_change_password")
        batch.drop_column("password_updated_at")
