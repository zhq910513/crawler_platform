"""Project build center jobs

Revision ID: 0017_project_build_center
Revises: 0016_company_resource_pool
Create Date: 2026-08-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0017_project_build_center"
down_revision = "0016_company_resource_pool"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    try:
        return {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}
    except Exception:
        return set()


def upgrade() -> None:
    if "crawler_project_build_job" not in _tables():
        op.create_table(
            "crawler_project_build_job",
            sa.Column("build_job_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("crawler_company.company_id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("crawler_project.project_id", ondelete="SET NULL"), nullable=True),
            sa.Column("discovered_project_id", sa.BigInteger(), sa.ForeignKey("crawler_discovered_project.discovered_project_id", ondelete="SET NULL"), nullable=True),
            sa.Column("release_id", sa.BigInteger(), sa.ForeignKey("crawler_project_release.release_id", ondelete="SET NULL"), nullable=True),
            sa.Column("repository_url", sa.String(500), nullable=False),
            sa.Column("ref_name", sa.String(120), nullable=False, server_default="main"),
            sa.Column("git_commit", sa.String(100), nullable=False, server_default=""),
            sa.Column("project_code", sa.String(100), nullable=False, server_default=""),
            sa.Column("release_version", sa.String(100), nullable=False, server_default=""),
            sa.Column("image_repository", sa.String(500), nullable=False, server_default=""),
            sa.Column("image_digest", sa.String(100), nullable=False, server_default=""),
            sa.Column("build_status", sa.String(30), nullable=False, server_default="PENDING"),
            sa.Column("current_stage", sa.String(80), nullable=False, server_default="PENDING"),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("workspace_path", sa.String(1000), nullable=False, server_default=""),
            sa.Column("manifest_path", sa.String(1000), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("build_logs", sa.JSON(), nullable=False),
            sa.Column("build_metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    indexes = _indexes("crawler_project_build_job")
    for name, columns in {
        "ix_crawler_project_build_job_company_id": ["company_id"],
        "ix_crawler_project_build_job_project_id": ["project_id"],
        "ix_crawler_project_build_job_discovered_project_id": ["discovered_project_id"],
        "ix_crawler_project_build_job_release_id": ["release_id"],
        "ix_crawler_project_build_job_project_code": ["project_code"],
        "ix_crawler_project_build_job_release_version": ["release_version"],
        "ix_crawler_project_build_job_image_digest": ["image_digest"],
        "ix_crawler_project_build_job_build_status": ["build_status"],
        "ix_crawler_project_build_job_current_stage": ["current_stage"],
        "idx_project_build_company_status": ["company_id", "build_status", "created_at"],
    }.items():
        if name not in indexes:
            try:
                op.create_index(name, "crawler_project_build_job", columns)
            except Exception:
                pass


def downgrade() -> None:
    if "crawler_project_build_job" not in _tables():
        return
    for name in (
        "idx_project_build_company_status",
        "ix_crawler_project_build_job_current_stage",
        "ix_crawler_project_build_job_build_status",
        "ix_crawler_project_build_job_image_digest",
        "ix_crawler_project_build_job_release_version",
        "ix_crawler_project_build_job_project_code",
        "ix_crawler_project_build_job_release_id",
        "ix_crawler_project_build_job_discovered_project_id",
        "ix_crawler_project_build_job_project_id",
        "ix_crawler_project_build_job_company_id",
    ):
        try:
            op.drop_index(name, table_name="crawler_project_build_job")
        except Exception:
            pass
    op.drop_table("crawler_project_build_job")
