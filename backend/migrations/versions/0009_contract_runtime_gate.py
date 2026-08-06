"""contract runtime gate and credential leases

Revision ID: 0009_contract_runtime_gate
Revises: 0008_task_contract
Create Date: 2026-08-06 16:12:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_contract_runtime_gate"
down_revision = "0008_task_contract"
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
    if not _table_exists("crawler_credential_lease"):
        op.create_table(
            "crawler_credential_lease",
            sa.Column("lease_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), nullable=False),
            sa.Column("company_code", sa.String(100), nullable=False),
            sa.Column("platform_code", sa.String(100), nullable=False),
            sa.Column("credential_id", sa.BigInteger(), nullable=True),
            sa.Column("credential_key", sa.String(150), nullable=False),
            sa.Column("slot", sa.String(80), nullable=False, server_default=""),
            sa.Column("run_id", sa.BigInteger(), nullable=True),
            sa.Column("task_id", sa.BigInteger(), nullable=True),
            sa.Column("agent_id", sa.BigInteger(), nullable=True),
            sa.Column("agent_code", sa.String(100), nullable=False, server_default=""),
            sa.Column("lease_status", sa.String(30), nullable=False, server_default="ACTIVE"),
            sa.Column("lease_token_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("lease_until", sa.DateTime(), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("release_reason", sa.String(200), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["company_id"], ["crawler_company.company_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["credential_id"], ["crawler_account_credential.credential_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_id"], ["crawler_task_run.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["task_id"], ["crawler_task.task_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["agent_id"], ["crawler_agent.agent_id"], ondelete="SET NULL"),
        )
    for name, cols in [
        ("ix_cred_lease_company", ["company_id"]),
        ("ix_cred_lease_platform", ["platform_code"]),
        ("ix_cred_lease_credential", ["credential_id"]),
        ("ix_cred_lease_key", ["credential_key"]),
        ("ix_cred_lease_status", ["lease_status"]),
        ("ix_cred_lease_token", ["lease_token_hash"]),
        ("ix_cred_lease_until", ["lease_until"]),
        ("idx_cred_lease_lookup", ["company_id", "platform_code", "credential_key", "lease_status"]),
        ("idx_cred_lease_run", ["run_id", "lease_status"]),
    ]:
        _create_index(name, "crawler_credential_lease", cols)


def downgrade() -> None:
    for name in [
        "idx_cred_lease_run", "idx_cred_lease_lookup", "ix_cred_lease_until", "ix_cred_lease_token",
        "ix_cred_lease_status", "ix_cred_lease_key", "ix_cred_lease_credential", "ix_cred_lease_platform", "ix_cred_lease_company",
    ]:
        _drop_index(name, "crawler_credential_lease")
    if _table_exists("crawler_credential_lease"):
        op.drop_table("crawler_credential_lease")
