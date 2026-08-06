"""agent onboarding deployment and offline snapshot

Revision ID: 0006_agent_deploy
Revises: 0005_110_audit
Create Date: 2026-08-06 11:52:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_agent_deploy"
down_revision = "0005_110_audit"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _col_exists(table: str, col: str) -> bool:
    return _table_exists(table) and any(c.get("name") == col for c in _insp().get_columns(table))


def _idx_exists(table: str, name: str) -> bool:
    return _table_exists(table) and any(i.get("name") == name for i in _insp().get_indexes(table))


def _create_index(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    if _table_exists(table) and not _idx_exists(table, name):
        op.create_index(name, table, cols, unique=unique)


def _drop_index(name: str, table: str) -> None:
    if _idx_exists(table, name):
        op.drop_index(name, table_name=table)


def _add_col(table: str, col: sa.Column) -> None:
    if _table_exists(table) and not _col_exists(table, col.name):
        op.add_column(table, col)


def _dialect() -> str:
    return op.get_bind().dialect.name


def _add_json_col(table: str, name: str, default_json: str = "{}") -> None:
    if not _table_exists(table) or _col_exists(table, name):
        return
    # MySQL does not allow DEFAULT values on JSON/TEXT/BLOB columns. Add the
    # column as nullable, backfill existing rows, then tighten nullability on
    # dialects that support ALTER COLUMN. This keeps upgrades safe for existing
    # customer databases and remains idempotent after a failed migration retry.
    op.add_column(table, sa.Column(name, sa.JSON(), nullable=True))
    op.execute(sa.text(f"UPDATE {table} SET {name} = :value WHERE {name} IS NULL").bindparams(value=default_json))
    if _dialect() != "sqlite":
        op.alter_column(table, name, existing_type=sa.JSON(), nullable=False)


def _drop_col(table: str, name: str) -> None:
    if _col_exists(table, name):
        op.drop_column(table, name)


def upgrade() -> None:
    _add_json_col("crawler_server", "labels", "{}")
    _add_json_col("crawler_server", "capabilities", "{}")
    _add_col("crawler_server", sa.Column("registry_credential_ref", sa.String(length=200), nullable=False, server_default=""))
    _add_col("crawler_server", sa.Column("work_dir", sa.String(length=500), nullable=False, server_default="/data/crawler-agent"))
    _add_col("crawler_project_task_definition", sa.Column("allow_offline_run", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    _add_json_col("crawler_project_task_definition", "offline_policy", "{}")
    _add_col("crawler_task", sa.Column("allow_offline_run", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    _add_json_col("crawler_task", "offline_policy", "{}")

    if not _table_exists("crawler_agent_join_token"):
        op.create_table(
            "crawler_agent_join_token",
            sa.Column("token_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("token_name", sa.String(120), nullable=False, server_default="Agent 接入令牌"),
            sa.Column("agent_code", sa.String(100), nullable=False),
            sa.Column("agent_name", sa.String(100), nullable=False, server_default=""),
            sa.Column("server_code", sa.String(100), nullable=False),
            sa.Column("server_name", sa.String(100), nullable=False, server_default=""),
            sa.Column("work_dir", sa.String(500), nullable=False, server_default="/data/crawler-agent"),
            sa.Column("max_container_slots", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("labels", sa.JSON(), nullable=False),
            sa.Column("capabilities", sa.JSON(), nullable=False),
            sa.Column("registry_credential_ref", sa.String(200), nullable=False, server_default=""),
            sa.Column("install_mode", sa.String(30), nullable=False, server_default="AUTO"),
            sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("last_preflight_report", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["sys_user.user_id"], ondelete="SET NULL"),
        )
    _create_index("ix_agent_join_company", "crawler_agent_join_token", ["company_id"])
    _create_index("ix_agent_join_token_hash", "crawler_agent_join_token", ["token_hash"], unique=True)
    _create_index("ix_agent_join_status", "crawler_agent_join_token", ["status"])
    _create_index("ix_agent_join_agent_code", "crawler_agent_join_token", ["agent_code"])

    if not _table_exists("crawler_project_deployment"):
        op.create_table(
            "crawler_project_deployment",
            sa.Column("deployment_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("project_id", sa.BigInteger(), nullable=False),
            sa.Column("release_id", sa.BigInteger(), nullable=False),
            sa.Column("deployment_name", sa.String(150), nullable=False, server_default=""),
            sa.Column("strategy", sa.JSON(), nullable=False),
            sa.Column("deployment_status", sa.String(30), nullable=False, server_default="CREATED"),
            sa.Column("created_by", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["crawler_project.project_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["release_id"], ["crawler_project_release.release_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["sys_user.user_id"], ondelete="SET NULL"),
        )
    _create_index("ix_deploy_company", "crawler_project_deployment", ["company_id"])
    _create_index("ix_deploy_project", "crawler_project_deployment", ["project_id"])
    _create_index("ix_deploy_release", "crawler_project_deployment", ["release_id"])
    _create_index("ix_deploy_status", "crawler_project_deployment", ["deployment_status"])

    if not _table_exists("crawler_project_deployment_target"):
        op.create_table(
            "crawler_project_deployment_target",
            sa.Column("target_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("deployment_id", sa.BigInteger(), nullable=False),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("project_id", sa.BigInteger(), nullable=False),
            sa.Column("release_id", sa.BigInteger(), nullable=False),
            sa.Column("server_id", sa.BigInteger(), nullable=False),
            sa.Column("target_status", sa.String(30), nullable=False, server_default="OUTDATED"),
            sa.Column("image_readiness_status", sa.String(30), nullable=False, server_default="OUTDATED"),
            sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
            sa.Column("last_deployed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["deployment_id"], ["crawler_project_deployment.deployment_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["crawler_project.project_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["release_id"], ["crawler_project_release.release_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["crawler_server.server_id"], ondelete="CASCADE"),
            sa.UniqueConstraint("deployment_id", "server_id", name="uk_deploy_target_server"),
        )
    _create_index("ix_deploy_target_company", "crawler_project_deployment_target", ["company_id"])
    _create_index("ix_deploy_target_project", "crawler_project_deployment_target", ["project_id"])
    _create_index("ix_deploy_target_server", "crawler_project_deployment_target", ["server_id"])
    _create_index("ix_deploy_target_status", "crawler_project_deployment_target", ["target_status"])

    if not _table_exists("crawler_offline_run_snapshot"):
        op.create_table(
            "crawler_offline_run_snapshot",
            sa.Column("snapshot_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("agent_id", sa.BigInteger(), nullable=False),
            sa.Column("server_id", sa.BigInteger(), nullable=False),
            sa.Column("snapshot_version", sa.String(100), nullable=False, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("snapshot_status", sa.String(30), nullable=False, server_default="ACTIVE"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["agent_id"], ["crawler_agent.agent_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["crawler_server.server_id"], ondelete="CASCADE"),
        )
    _create_index("ix_offline_snapshot_company", "crawler_offline_run_snapshot", ["company_id"])
    _create_index("ix_offline_snapshot_agent", "crawler_offline_run_snapshot", ["agent_id"])
    _create_index("ix_offline_snapshot_status", "crawler_offline_run_snapshot", ["snapshot_status"])


def downgrade() -> None:
    for name, table in [
        ("ix_offline_snapshot_status", "crawler_offline_run_snapshot"),
        ("ix_offline_snapshot_agent", "crawler_offline_run_snapshot"),
        ("ix_offline_snapshot_company", "crawler_offline_run_snapshot"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_offline_run_snapshot"):
        op.drop_table("crawler_offline_run_snapshot")
    for name, table in [
        ("ix_deploy_target_status", "crawler_project_deployment_target"),
        ("ix_deploy_target_server", "crawler_project_deployment_target"),
        ("ix_deploy_target_project", "crawler_project_deployment_target"),
        ("ix_deploy_target_company", "crawler_project_deployment_target"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_project_deployment_target"):
        op.drop_table("crawler_project_deployment_target")
    for name, table in [
        ("ix_deploy_status", "crawler_project_deployment"),
        ("ix_deploy_release", "crawler_project_deployment"),
        ("ix_deploy_project", "crawler_project_deployment"),
        ("ix_deploy_company", "crawler_project_deployment"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_project_deployment"):
        op.drop_table("crawler_project_deployment")
    for name, table in [
        ("ix_agent_join_agent_code", "crawler_agent_join_token"),
        ("ix_agent_join_status", "crawler_agent_join_token"),
        ("ix_agent_join_token_hash", "crawler_agent_join_token"),
        ("ix_agent_join_company", "crawler_agent_join_token"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_agent_join_token"):
        op.drop_table("crawler_agent_join_token")
    for table, col in [
        ("crawler_task", "offline_policy"),
        ("crawler_task", "allow_offline_run"),
        ("crawler_project_task_definition", "offline_policy"),
        ("crawler_project_task_definition", "allow_offline_run"),
        ("crawler_server", "work_dir"),
        ("crawler_server", "registry_credential_ref"),
        ("crawler_server", "capabilities"),
        ("crawler_server", "labels"),
    ]:
        _drop_col(table, col)
