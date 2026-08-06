"""task contract and subject credential binding

Revision ID: 0008_task_contract
Revises: 0007_account_status
Create Date: 2026-08-06 15:34:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_task_contract"
down_revision = "0007_account_status"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _cols(table: str) -> set[str]:
    return {c["name"] for c in _insp().get_columns(table)} if _table_exists(table) else set()


def _idx_exists(table: str, name: str) -> bool:
    return _table_exists(table) and any(i.get("name") == name for i in _insp().get_indexes(table))


def _add_col(table: str, col: sa.Column) -> None:
    if _table_exists(table) and col.name not in _cols(table):
        op.add_column(table, col)


def _drop_col(table: str, name: str) -> None:
    if _table_exists(table) and name in _cols(table):
        op.drop_column(table, name)


def _create_index(name: str, table: str, cols: list[str], unique: bool = False) -> None:
    if _table_exists(table) and not _idx_exists(table, name):
        op.create_index(name, table, cols, unique=unique)


def _drop_index(name: str, table: str) -> None:
    if _idx_exists(table, name):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    _add_col("crawler_project_task_definition", sa.Column("platform_code", sa.String(100), nullable=False, server_default=""))
    _add_col("crawler_project_task_definition", sa.Column("required_configs", sa.JSON(), nullable=False, server_default="[]"))
    _add_col("crawler_project_task_definition", sa.Column("required_credentials", sa.JSON(), nullable=False, server_default="[]"))
    _add_col("crawler_project_task_definition", sa.Column("output_tables", sa.JSON(), nullable=False, server_default="[]"))
    _add_col("crawler_project_task_definition", sa.Column("contract_version", sa.String(30), nullable=False, server_default="1"))
    _add_col("crawler_project_task_definition", sa.Column("contract_status", sa.String(30), nullable=False, server_default="UNKNOWN"))
    _add_col("crawler_project_task_definition", sa.Column("contract_warnings", sa.JSON(), nullable=False, server_default="[]"))
    _create_index("ix_task_def_platform_code", "crawler_project_task_definition", ["platform_code"])
    _create_index("ix_task_def_contract_status", "crawler_project_task_definition", ["contract_status"])

    _add_col("crawler_task", sa.Column("config_bindings", sa.JSON(), nullable=False, server_default="{}"))
    _add_col("crawler_task", sa.Column("credential_bindings", sa.JSON(), nullable=False, server_default="{}"))
    _add_col("crawler_task", sa.Column("contract_snapshot", sa.JSON(), nullable=False, server_default="{}"))

    _add_col("crawler_account_status_event", sa.Column("subject_type", sa.String(80), nullable=False, server_default=""))
    _add_col("crawler_account_status_event", sa.Column("subject_key", sa.String(200), nullable=False, server_default=""))
    _add_col("crawler_account_status_event", sa.Column("subject_name", sa.String(300), nullable=False, server_default=""))
    _add_col("crawler_account_status_event", sa.Column("affects_credential", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    _create_index("ix_acct_evt_subject_type", "crawler_account_status_event", ["subject_type"])
    _create_index("ix_acct_evt_subject_key", "crawler_account_status_event", ["subject_key"])
    _create_index("idx_acct_evt_subject", "crawler_account_status_event", ["company_id", "platform_code", "subject_type", "subject_key"])

    if not _table_exists("crawler_credential_subject_binding"):
        op.create_table(
            "crawler_credential_subject_binding",
            sa.Column("binding_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("company_code", sa.String(100), nullable=False),
            sa.Column("platform_code", sa.String(100), nullable=False),
            sa.Column("subject_type", sa.String(80), nullable=False),
            sa.Column("subject_key", sa.String(200), nullable=False),
            sa.Column("subject_name", sa.String(300), nullable=False, server_default=""),
            sa.Column("credential_id", sa.BigInteger(), nullable=True),
            sa.Column("credential_key", sa.String(150), nullable=False),
            sa.Column("binding_status", sa.String(30), nullable=False, server_default="ACTIVE"),
            sa.Column("binding_policy", sa.String(50), nullable=False, server_default="BIND_ON_SUCCESS"),
            sa.Column("rebinding_policy", sa.String(50), nullable=False, server_default="MANUAL_ONLY"),
            sa.Column("source", sa.String(40), nullable=False, server_default="TASK_RUN"),
            sa.Column("first_success_run_id", sa.BigInteger(), nullable=True),
            sa.Column("first_success_task_id", sa.BigInteger(), nullable=True),
            sa.Column("first_success_agent_code", sa.String(100), nullable=False, server_default=""),
            sa.Column("first_success_at", sa.DateTime(), nullable=True),
            sa.Column("last_success_run_id", sa.BigInteger(), nullable=True),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column("last_failure_at", sa.DateTime(), nullable=True),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error_code", sa.String(80), nullable=False, server_default=""),
            sa.Column("last_error_summary", sa.String(1000), nullable=False, server_default=""),
            sa.Column("locked_by_run_id", sa.BigInteger(), nullable=True),
            sa.Column("lock_expires_at", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["credential_id"], ["crawler_account_credential.credential_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["first_success_run_id"], ["crawler_task_run.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["first_success_task_id"], ["crawler_task.task_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["last_success_run_id"], ["crawler_task_run.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["locked_by_run_id"], ["crawler_task_run.run_id"], ondelete="SET NULL"),
            sa.UniqueConstraint("company_id", "platform_code", "subject_type", "subject_key", name="uk_cred_subject_binding"),
        )
    for name, cols in [
        ("ix_cred_sub_company", ["company_id"]), ("ix_cred_sub_company_code", ["company_code"]),
        ("ix_cred_sub_platform", ["platform_code"]), ("ix_cred_sub_type", ["subject_type"]),
        ("ix_cred_sub_key", ["subject_key"]), ("ix_cred_sub_credential", ["credential_id"]),
        ("ix_cred_sub_credential_key", ["credential_key"]), ("ix_cred_sub_status", ["binding_status"]),
        ("idx_cred_subject_lookup", ["company_id", "platform_code", "subject_type", "subject_key"]),
        ("idx_cred_subject_credential", ["company_id", "platform_code", "credential_key"]),
    ]:
        _create_index(name, "crawler_credential_subject_binding", cols)


def downgrade() -> None:
    for name, table in [
        ("idx_cred_subject_credential", "crawler_credential_subject_binding"), ("idx_cred_subject_lookup", "crawler_credential_subject_binding"),
        ("ix_cred_sub_status", "crawler_credential_subject_binding"), ("ix_cred_sub_credential_key", "crawler_credential_subject_binding"),
        ("ix_cred_sub_credential", "crawler_credential_subject_binding"), ("ix_cred_sub_key", "crawler_credential_subject_binding"),
        ("ix_cred_sub_type", "crawler_credential_subject_binding"), ("ix_cred_sub_platform", "crawler_credential_subject_binding"),
        ("ix_cred_sub_company_code", "crawler_credential_subject_binding"), ("ix_cred_sub_company", "crawler_credential_subject_binding"),
    ]:
        _drop_index(name, table)
    if _table_exists("crawler_credential_subject_binding"):
        op.drop_table("crawler_credential_subject_binding")
    for name in ["idx_acct_evt_subject", "ix_acct_evt_subject_key", "ix_acct_evt_subject_type"]:
        _drop_index(name, "crawler_account_status_event")
    for col in ["affects_credential", "subject_name", "subject_key", "subject_type"]:
        _drop_col("crawler_account_status_event", col)
    for col in ["contract_snapshot", "credential_bindings", "config_bindings"]:
        _drop_col("crawler_task", col)
    for name in ["ix_task_def_contract_status", "ix_task_def_platform_code"]:
        _drop_index(name, "crawler_project_task_definition")
    for col in ["contract_warnings", "contract_status", "contract_version", "output_tables", "required_credentials", "required_configs", "platform_code"]:
        _drop_col("crawler_project_task_definition", col)
