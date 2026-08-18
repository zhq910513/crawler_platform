"""Company scoped multi data resource pool

Revision ID: 0016_company_resource_pool
Revises: 0015_agent_lifecycle
Create Date: 2026-08-18
"""
from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, select, text

revision = "0016_company_resource_pool"
down_revision = "0015_agent_lifecycle"
branch_labels = None
depends_on = None

LEGACY_RESOURCE_TYPE_MAP = {
    "MYSQL_MAIN": ("RELATIONAL_DB", "MYSQL", "MAIN_DB", "HOST_PORT", "mysql_main", "主业务数据库"),
    "REDIS_CACHE": ("CACHE_DB", "REDIS", "COOKIE_CACHE", "HOST_PORT", "redis_cache", "账号缓存库"),
    "MONGO_RAW": ("DOCUMENT_DB", "MONGODB", "RAW_STORAGE", "URI", "mongo_raw", "原始数据存储"),
    "OSS_MEDIA": ("OBJECT_STORAGE", "ALIYUN_OSS", "MEDIA_STORAGE", "CLOUD_SERVICE", "oss_media", "媒体存储"),
}


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    try:
        return {item["name"] for item in inspect(bind).get_indexes(table)}
    except Exception:
        return set()


def _unique_constraints(table: str) -> set[str]:
    bind = op.get_bind()
    try:
        return {item["name"] for item in inspect(bind).get_unique_constraints(table) if item.get("name")}
    except Exception:
        return set()


def upgrade() -> None:
    tables = _tables()
    if "company_resource_config" not in tables:
        op.create_table(
            "company_resource_config",
            sa.Column("resource_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
            sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("crawler_company.company_id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("crawler_project.project_id", ondelete="CASCADE"), nullable=True),
            sa.Column("resource_name", sa.String(100), nullable=False),
            sa.Column("resource_code", sa.String(100), nullable=False),
            sa.Column("resource_category", sa.String(50), nullable=False),
            sa.Column("resource_engine", sa.String(50), nullable=False),
            sa.Column("resource_role", sa.String(50), nullable=False),
            sa.Column("connection_mode", sa.String(50), nullable=False, server_default="HOST_PORT"),
            sa.Column("config_encrypted", sa.Text(), nullable=False),
            sa.Column("config_masked_snapshot", sa.JSON(), nullable=True),
            sa.Column("config_summary", sa.JSON(), nullable=True),
            sa.Column("remark", sa.String(1000), nullable=False, server_default=""),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("test_status", sa.String(50), nullable=False, server_default="NOT_TESTED"),
            sa.Column("last_test_at", sa.DateTime(), nullable=True),
            sa.Column("last_test_message", sa.String(1000), nullable=False, server_default=""),
            sa.Column("legacy_resource_type", sa.String(50), nullable=True),
            sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("sys_user.user_id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("sys_user.user_id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("company_id", "resource_code", name="uk_company_resource_code"),
        )
    indexes = _indexes("company_resource_config")
    for name, columns in {
        "ix_company_resource_config_company_id": ["company_id"],
        "ix_company_resource_config_project_id": ["project_id"],
        "ix_company_resource_config_resource_category": ["resource_category"],
        "ix_company_resource_config_resource_engine": ["resource_engine"],
        "ix_company_resource_config_resource_role": ["resource_role"],
        "ix_company_resource_config_enabled": ["enabled"],
        "ix_company_resource_config_test_status": ["test_status"],
        "ix_company_resource_company_engine_role": ["company_id", "resource_engine", "resource_role"],
    }.items():
        if name not in indexes:
            try:
                op.create_index(name, "company_resource_config", columns)
            except Exception:
                pass
    _migrate_legacy_secrets()


def _migrate_legacy_secrets() -> None:
    bind = op.get_bind()
    tables = _tables()
    if "sys_secret" not in tables:
        return
    resources = sa.table(
        "company_resource_config",
        sa.column("company_id", sa.BigInteger()),
        sa.column("project_id", sa.BigInteger()),
        sa.column("resource_name", sa.String()),
        sa.column("resource_code", sa.String()),
        sa.column("resource_category", sa.String()),
        sa.column("resource_engine", sa.String()),
        sa.column("resource_role", sa.String()),
        sa.column("connection_mode", sa.String()),
        sa.column("config_encrypted", sa.Text()),
        sa.column("config_masked_snapshot", sa.JSON()),
        sa.column("config_summary", sa.JSON()),
        sa.column("remark", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("test_status", sa.String()),
        sa.column("last_test_message", sa.String()),
        sa.column("legacy_resource_type", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    sys_secret = sa.table(
        "sys_secret",
        sa.column("company_id", sa.BigInteger()),
        sa.column("project_id", sa.BigInteger()),
        sa.column("secret_code", sa.String()),
        sa.column("secret_name", sa.String()),
        sa.column("encrypted_value", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    rows = bind.execute(select(sys_secret).where(sys_secret.c.secret_code.like("company_resource:%"))).mappings().all()
    now = datetime.now(UTC).replace(tzinfo=None)
    for row in rows:
        secret_code = row.get("secret_code") or ""
        legacy_type = secret_code.split(":")[-1]
        if legacy_type not in LEGACY_RESOURCE_TYPE_MAP or not row.get("company_id"):
            continue
        category, engine, role, mode, resource_code, default_name = LEGACY_RESOURCE_TYPE_MAP[legacy_type]
        exists = bind.execute(
            text("SELECT resource_id FROM company_resource_config WHERE company_id = :company_id AND resource_code = :resource_code"),
            {"company_id": row["company_id"], "resource_code": resource_code},
        ).first()
        if exists:
            continue
        bind.execute(
            resources.insert().values(
                company_id=row["company_id"],
                project_id=row.get("project_id"),
                resource_name=row.get("secret_name") or default_name,
                resource_code=resource_code,
                resource_category=category,
                resource_engine=engine,
                resource_role=role,
                connection_mode=mode,
                config_encrypted=row.get("encrypted_value") or "",
                config_masked_snapshot=None,
                config_summary=None,
                remark=f"由系统从旧版 {legacy_type} 自动迁移生成。",
                enabled=bool(row.get("enabled", True)),
                test_status="NOT_TESTED",
                last_test_message="由旧版资源配置迁移生成，尚未执行新版基础配置校验。",
                legacy_resource_type=legacy_type,
                created_at=row.get("created_at") or now,
                updated_at=row.get("updated_at") or now,
            )
        )


def downgrade() -> None:
    if "company_resource_config" not in _tables():
        return
    for index_name in (
        "ix_company_resource_company_engine_role",
        "ix_company_resource_config_test_status",
        "ix_company_resource_config_enabled",
        "ix_company_resource_config_resource_role",
        "ix_company_resource_config_resource_engine",
        "ix_company_resource_config_resource_category",
        "ix_company_resource_config_project_id",
        "ix_company_resource_config_company_id",
    ):
        try:
            op.drop_index(index_name, table_name="company_resource_config")
        except Exception:
            pass
    op.drop_table("company_resource_config")
