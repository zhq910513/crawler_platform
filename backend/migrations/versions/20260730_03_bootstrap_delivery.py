"""add bootstrap delivery, deployment logs, latest-release guard metadata

Revision ID: 20260730_03
Revises: 20260730_02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260730_03"
down_revision = "20260730_02"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and any(item["name"] == column for item in inspector.get_columns(table))


def _add_column(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def _index_names(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    names = {str(item.get("name")) for item in inspector.get_indexes(table) if item.get("name")}
    names.update(str(item.get("name")) for item in inspector.get_unique_constraints(table) if item.get("name"))
    return names


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    if table in _tables() and name not in _index_names(table):
        op.create_index(name, table, columns, unique=unique)


def _create_table_if_missing(name: str, *columns, **kwargs) -> None:
    if name not in _tables():
        op.create_table(name, *columns, **kwargs)


def upgrade() -> None:
    _add_column("crawler_project", sa.Column("deployment_mode", sa.String(30), nullable=False, server_default="BOOTSTRAP"))
    _add_column("crawler_project", sa.Column("online_status", sa.String(30), nullable=False, server_default="DRAFT"))
    _add_column("crawler_project", sa.Column("min_agent_version", sa.String(50), nullable=False, server_default="2.0.0"))
    _create_index("ix_crawler_project_deployment_mode", "crawler_project", ["deployment_mode"])
    _create_index("ix_crawler_project_online_status", "crawler_project", ["online_status"])

    for column in [
        sa.Column("entry_module", sa.String(300), nullable=False, server_default=""),
        sa.Column("entry_function", sa.String(120), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="MANUAL"),
        sa.Column("source_file", sa.String(300), nullable=False, server_default=""),
        sa.Column("source_fingerprint", sa.String(100), nullable=False, server_default=""),
        sa.Column("resource_requirements", sa.JSON(), nullable=True),
    ]:
        _add_column("crawler_task", column)
    _create_index("ix_crawler_task_entry_module", "crawler_task", ["entry_module"])
    _create_index("ix_crawler_task_entry_function", "crawler_task", ["entry_function"])
    _create_index("ix_crawler_task_source_type", "crawler_task", ["source_type"])
    _create_index("idx_task_project_entry", "crawler_task", ["project_id", "entry_module", "entry_function"])

    _create_table_if_missing(
        "crawler_project_bootstrap_token",
        sa.Column("token_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("crawler_company.company_id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_name", sa.String(120), nullable=False, server_default="default"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("allowed_repo", sa.String(500), nullable=False, server_default=""),
        sa.Column("permissions_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("sys_user.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_index("ix_crawler_project_bootstrap_token_token_hash", "crawler_project_bootstrap_token", ["token_hash"], unique=True)
    _create_index("ix_crawler_project_bootstrap_token_project_id", "crawler_project_bootstrap_token", ["project_id"])
    _create_index("ix_crawler_project_bootstrap_token_company_id", "crawler_project_bootstrap_token", ["company_id"])
    _create_index("idx_bootstrap_token_project", "crawler_project_bootstrap_token", ["project_id", "status"])

    _create_table_if_missing(
        "crawler_deployment_log",
        sa.Column("deployment_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("crawler_company.company_id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_id", sa.BigInteger(), sa.ForeignKey("crawler_project_bootstrap_token.token_id", ondelete="SET NULL"), nullable=True),
        sa.Column("server_code", sa.String(100), nullable=False, server_default=""),
        sa.Column("agent_code", sa.String(100), nullable=False, server_default=""),
        sa.Column("stage", sa.String(50), nullable=False, server_default="BOOTSTRAP"),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("git_branch", sa.String(100), nullable=False, server_default=""),
        sa.Column("git_commit", sa.String(100), nullable=False, server_default=""),
        sa.Column("image_repository", sa.String(500), nullable=False, server_default=""),
        sa.Column("image_digest", sa.String(255), nullable=False, server_default=""),
        sa.Column("release_id", sa.BigInteger(), sa.ForeignKey("crawler_spider_release.release_id", ondelete="SET NULL"), nullable=True),
        sa.Column("preflight_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_index("idx_deploy_project_time", "crawler_deployment_log", ["project_id", "created_at"])
    _create_index("ix_crawler_deployment_log_company_id", "crawler_deployment_log", ["company_id"])
    _create_index("ix_crawler_deployment_log_project_id", "crawler_deployment_log", ["project_id"])
    _create_index("ix_crawler_deployment_log_status", "crawler_deployment_log", ["status"])
    _create_index("ix_crawler_deployment_log_stage", "crawler_deployment_log", ["stage"])

    _create_table_if_missing(
        "crawler_task_change_log",
        sa.Column("change_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("crawler_task.task_id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("sys_user.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_type", sa.String(50), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    _create_index("ix_crawler_task_change_log_task_id", "crawler_task_change_log", ["task_id"])
    _create_index("ix_crawler_task_change_log_project_id", "crawler_task_change_log", ["project_id"])
    _create_index("ix_crawler_task_change_log_change_type", "crawler_task_change_log", ["change_type"])
    _create_index("ix_crawler_task_change_log_created_at", "crawler_task_change_log", ["created_at"])


def downgrade() -> None:
    pass
