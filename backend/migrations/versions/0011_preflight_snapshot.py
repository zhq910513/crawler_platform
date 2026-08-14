"""platform preflight snapshot history

Revision ID: 0011_preflight_snapshot
Revises: 0010_running_center
Create Date: 2026-08-14 14:42:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_preflight_snapshot"
down_revision = "0010_running_center"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _idx_exists(table: str, name: str) -> bool:
    return _table_exists(table) and any(i.get("name") == name for i in _insp().get_indexes(table))


def _create_index(name: str, table: str, cols: list[str]) -> None:
    if _table_exists(table) and not _idx_exists(table, name):
        op.create_index(name, table, cols)


def _drop_index(name: str, table: str) -> None:
    if _idx_exists(table, name):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    if not _table_exists("platform_preflight_snapshot"):
        op.create_table(
            "platform_preflight_snapshot",
            sa.Column("snapshot_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("blocking_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("check_source", sa.String(30), nullable=False, server_default="AUTO"),
            sa.Column("check_source_label", sa.String(80), nullable=False, server_default="页面自动检测"),
            sa.Column("control_plane_url", sa.String(500), nullable=False, server_default=""),
            sa.Column("agent_image", sa.String(500), nullable=False, server_default=""),
            sa.Column("agent_image_digest", sa.String(120), nullable=False, server_default=""),
            sa.Column("summary", sa.String(500), nullable=False, server_default=""),
            sa.Column("change_summary", sa.JSON(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.Column("triggered_by", sa.BigInteger(), nullable=True),
            sa.Column("checked_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["triggered_by"], ["sys_user.user_id"], ondelete="SET NULL"),
        )
    for name, cols in [
        ("ix_preflight_snapshot_status", ["status"]),
        ("ix_preflight_snapshot_source", ["check_source"]),
        ("ix_preflight_snapshot_checked_at", ["checked_at"]),
        ("ix_preflight_snapshot_triggered_by", ["triggered_by"]),
    ]:
        _create_index(name, "platform_preflight_snapshot", cols)


def downgrade() -> None:
    for name in ["ix_preflight_snapshot_triggered_by", "ix_preflight_snapshot_checked_at", "ix_preflight_snapshot_source", "ix_preflight_snapshot_status"]:
        _drop_index(name, "platform_preflight_snapshot")
    if _table_exists("platform_preflight_snapshot"):
        op.drop_table("platform_preflight_snapshot")
