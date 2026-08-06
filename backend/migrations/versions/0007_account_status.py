"""account status reporting standard

Revision ID: 0007_account_status
Revises: 0006_agent_deploy
Create Date: 2026-08-06 14:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_account_status"
down_revision = "0006_agent_deploy"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _idx_exists(table: str, name: str) -> bool:
    return _table_exists(table) and any(i.get("name") == name for i in _insp().get_indexes(table))


def _create_index(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    if _table_exists(table) and not _idx_exists(table, name):
        op.create_index(name, table, cols, unique=unique)


def _drop_index(name: str, table: str) -> None:
    if _idx_exists(table, name):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    if not _table_exists("crawler_account_credential"):
        op.create_table(
            "crawler_account_credential",
            sa.Column("credential_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("company_code", sa.String(100), nullable=False),
            sa.Column("platform_code", sa.String(100), nullable=False),
            sa.Column("credential_key", sa.String(150), nullable=False),
            sa.Column("credential_name", sa.String(200), nullable=False, server_default=""),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("health_status", sa.String(30), nullable=False, server_default="UNKNOWN"),
            sa.Column("login_status", sa.String(30), nullable=False, server_default="NO_AUTH"),
            sa.Column("usage_status", sa.String(30), nullable=False, server_default="AVAILABLE"),
            sa.Column("last_status_code", sa.String(80), nullable=False, server_default=""),
            sa.Column("last_status_source", sa.String(40), nullable=False, server_default=""),
            sa.Column("last_verified_at", sa.DateTime(), nullable=True),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column("last_failure_at", sa.DateTime(), nullable=True),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status_fresh_until", sa.DateTime(), nullable=True),
            sa.Column("last_verified_agent_code", sa.String(100), nullable=False, server_default=""),
            sa.Column("last_run_id", sa.BigInteger(), nullable=True),
            sa.Column("last_task_id", sa.BigInteger(), nullable=True),
            sa.Column("last_error_summary", sa.String(1000), nullable=False, server_default=""),
            sa.Column("status_metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["last_run_id"], ["crawler_task_run.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["last_task_id"], ["crawler_task.task_id"], ondelete="SET NULL"),
            sa.UniqueConstraint("company_id", "platform_code", "credential_key", name="uk_acct_cred_company_platform_key"),
        )
    _create_index("ix_acct_cred_company", "crawler_account_credential", ["company_id"])
    _create_index("ix_acct_cred_company_code", "crawler_account_credential", ["company_code"])
    _create_index("ix_acct_cred_platform", "crawler_account_credential", ["platform_code"])
    _create_index("ix_acct_cred_key", "crawler_account_credential", ["credential_key"])
    _create_index("ix_acct_cred_enabled", "crawler_account_credential", ["enabled"])
    _create_index("ix_acct_cred_health", "crawler_account_credential", ["health_status"])
    _create_index("ix_acct_cred_login", "crawler_account_credential", ["login_status"])
    _create_index("ix_acct_cred_usage", "crawler_account_credential", ["usage_status"])
    _create_index("ix_acct_cred_status_code", "crawler_account_credential", ["last_status_code"])
    _create_index("ix_acct_cred_last_run", "crawler_account_credential", ["last_run_id"])
    _create_index("ix_acct_cred_last_task", "crawler_account_credential", ["last_task_id"])
    _create_index("idx_acct_cred_lookup", "crawler_account_credential", ["company_id", "platform_code", "credential_key"])
    _create_index("idx_acct_cred_status", "crawler_account_credential", ["company_id", "enabled", "health_status", "login_status"])

    if not _table_exists("crawler_account_status_event"):
        op.create_table(
            "crawler_account_status_event",
            sa.Column("status_event_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("event_uid", sa.String(80), nullable=False),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("company_code", sa.String(100), nullable=False),
            sa.Column("platform_code", sa.String(100), nullable=False),
            sa.Column("credential_key", sa.String(150), nullable=False),
            sa.Column("credential_id", sa.BigInteger(), nullable=True),
            sa.Column("run_id", sa.BigInteger(), nullable=True),
            sa.Column("task_id", sa.BigInteger(), nullable=True),
            sa.Column("agent_id", sa.BigInteger(), nullable=True),
            sa.Column("agent_code", sa.String(100), nullable=False, server_default=""),
            sa.Column("slot", sa.String(80), nullable=False, server_default=""),
            sa.Column("event_type", sa.String(40), nullable=False, server_default="STATUS"),
            sa.Column("status_code", sa.String(80), nullable=False),
            sa.Column("severity", sa.String(10), nullable=False, server_default="INFO"),
            sa.Column("source", sa.String(40), nullable=False, server_default="TASK_RUN"),
            sa.Column("message_sanitized", sa.String(1000), nullable=False, server_default=""),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("payload_sanitized", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["credential_id"], ["crawler_account_credential.credential_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_id"], ["crawler_task_run.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["task_id"], ["crawler_task.task_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["agent_id"], ["crawler_agent.agent_id"], ondelete="SET NULL"),
            sa.UniqueConstraint("event_uid", name="uk_acct_status_event_uid"),
        )
    _create_index("ix_acct_evt_event_uid", "crawler_account_status_event", ["event_uid"], unique=True)
    _create_index("ix_acct_evt_company", "crawler_account_status_event", ["company_id"])
    _create_index("ix_acct_evt_company_code", "crawler_account_status_event", ["company_code"])
    _create_index("ix_acct_evt_platform", "crawler_account_status_event", ["platform_code"])
    _create_index("ix_acct_evt_key", "crawler_account_status_event", ["credential_key"])
    _create_index("ix_acct_evt_credential", "crawler_account_status_event", ["credential_id"])
    _create_index("ix_acct_evt_run", "crawler_account_status_event", ["run_id"])
    _create_index("ix_acct_evt_task", "crawler_account_status_event", ["task_id"])
    _create_index("ix_acct_evt_agent", "crawler_account_status_event", ["agent_id"])
    _create_index("ix_acct_evt_agent_code", "crawler_account_status_event", ["agent_code"])
    _create_index("ix_acct_evt_slot", "crawler_account_status_event", ["slot"])
    _create_index("ix_acct_evt_type", "crawler_account_status_event", ["event_type"])
    _create_index("ix_acct_evt_code", "crawler_account_status_event", ["status_code"])
    _create_index("ix_acct_evt_severity", "crawler_account_status_event", ["severity"])
    _create_index("ix_acct_evt_source", "crawler_account_status_event", ["source"])
    _create_index("ix_acct_evt_observed", "crawler_account_status_event", ["observed_at"])
    _create_index("idx_acct_evt_lookup", "crawler_account_status_event", ["company_id", "platform_code", "credential_key", "created_at"])


def downgrade() -> None:
    for name, table in [
        ("idx_acct_evt_lookup", "crawler_account_status_event"),
        ("ix_acct_evt_observed", "crawler_account_status_event"),
        ("ix_acct_evt_source", "crawler_account_status_event"),
        ("ix_acct_evt_severity", "crawler_account_status_event"),
        ("ix_acct_evt_code", "crawler_account_status_event"),
        ("ix_acct_evt_type", "crawler_account_status_event"),
        ("ix_acct_evt_slot", "crawler_account_status_event"),
        ("ix_acct_evt_agent_code", "crawler_account_status_event"),
        ("ix_acct_evt_agent", "crawler_account_status_event"),
        ("ix_acct_evt_task", "crawler_account_status_event"),
        ("ix_acct_evt_run", "crawler_account_status_event"),
        ("ix_acct_evt_credential", "crawler_account_status_event"),
        ("ix_acct_evt_key", "crawler_account_status_event"),
        ("ix_acct_evt_platform", "crawler_account_status_event"),
        ("ix_acct_evt_company_code", "crawler_account_status_event"),
        ("ix_acct_evt_company", "crawler_account_status_event"),
        ("ix_acct_evt_event_uid", "crawler_account_status_event"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_account_status_event"):
        op.drop_table("crawler_account_status_event")
    for name, table in [
        ("idx_acct_cred_status", "crawler_account_credential"),
        ("idx_acct_cred_lookup", "crawler_account_credential"),
        ("ix_acct_cred_last_task", "crawler_account_credential"),
        ("ix_acct_cred_last_run", "crawler_account_credential"),
        ("ix_acct_cred_status_code", "crawler_account_credential"),
        ("ix_acct_cred_usage", "crawler_account_credential"),
        ("ix_acct_cred_login", "crawler_account_credential"),
        ("ix_acct_cred_health", "crawler_account_credential"),
        ("ix_acct_cred_enabled", "crawler_account_credential"),
        ("ix_acct_cred_key", "crawler_account_credential"),
        ("ix_acct_cred_platform", "crawler_account_credential"),
        ("ix_acct_cred_company_code", "crawler_account_credential"),
        ("ix_acct_cred_company", "crawler_account_credential"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_account_credential"):
        op.drop_table("crawler_account_credential")
