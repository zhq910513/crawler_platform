"""upgrade crawler platform to multi-tenant agent-v2 architecture

Revision ID: 20260730_01
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260730_01"
down_revision = None
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and any(c["name"] == column for c in inspector.get_columns(table))


def _add(table: str, column: sa.Column) -> None:
    if not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    # 新表先由当前模型创建；旧表再补充 V2 字段。该迁移可用于全新库和 1.0 生产库。
    from app.db import Base
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=op.get_bind())

    _add("crawler_project", sa.Column("company_id", sa.BigInteger(), nullable=True))
    _add("crawler_project", sa.Column("created_by", sa.BigInteger(), nullable=True))
    _add("sys_secret", sa.Column("company_id", sa.BigInteger(), nullable=True))
    _add("sys_secret", sa.Column("project_id", sa.BigInteger(), nullable=True))

    for col in [
        sa.Column("protocol_version", sa.String(20), nullable=False, server_default="2.0"),
        sa.Column("instance_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("capabilities_json", sa.JSON(), nullable=True),
        sa.Column("labels_json", sa.JSON(), nullable=True),
    ]:
        _add("crawler_agent", col)

    for col in [
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("spider_task_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("parameters", sa.JSON(), nullable=True),
    ]:
        _add("crawler_task", col)

    _add("crawler_task_runtime", sa.Column("fixed_spider_release_id", sa.BigInteger(), nullable=True))
    _add("crawler_release_channel", sa.Column("spider_release_id", sa.BigInteger(), nullable=True))

    run_columns = [
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("project_id", sa.BigInteger(), nullable=True),
        sa.Column("spider_release_id", sa.BigInteger(), nullable=True),
        sa.Column("spider_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("starting_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
        sa.Column("lost_at", sa.DateTime(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("root_run_id", sa.BigInteger(), nullable=True),
        sa.Column("lease_token", sa.String(128), nullable=False, server_default=""),
        sa.Column("oom_killed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error_event_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("last_error_code", sa.String(200), nullable=False, server_default=""),
        sa.Column("last_error_type", sa.String(200), nullable=False, server_default=""),
        sa.Column("last_error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_log_seq", sa.BigInteger(), nullable=True),
        sa.Column("terminal_error_code", sa.String(200), nullable=False, server_default=""),
        sa.Column("terminal_error_type", sa.String(200), nullable=False, server_default=""),
        sa.Column("terminal_error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("terminal_error_retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("terminal_error_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("task_spec_json", sa.JSON(), nullable=True),
        sa.Column("resource_manifest_json", sa.JSON(), nullable=True),
        sa.Column("stdout_ack_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("stderr_ack_seq", sa.BigInteger(), nullable=False, server_default="0"),
    ]
    for col in run_columns:
        _add("crawler_task_run", col)

    bind = op.get_bind()
    dialect = bind.dialect.name
    now_expr = "CURRENT_TIMESTAMP"
    # 默认公司和旧数据作用域回填。
    existing = bind.execute(text("SELECT company_id FROM crawler_company WHERE company_code='default' LIMIT 1")).scalar()
    if not existing:
        bind.execute(text(f"INSERT INTO crawler_company(company_code,company_name,status,description,created_at,updated_at) VALUES('default','默认公司','ENABLED','升级兼容默认公司',{now_expr},{now_expr})"))
    company_id = bind.execute(text("SELECT company_id FROM crawler_company WHERE company_code='default' LIMIT 1")).scalar()
    bind.execute(text("UPDATE crawler_project SET company_id=:cid WHERE company_id IS NULL"), {"cid": company_id})
    bind.execute(text("UPDATE sys_secret SET company_id=:cid WHERE company_id IS NULL AND project_id IS NULL"), {"cid": company_id})
    bind.execute(text("UPDATE crawler_task t JOIN crawler_project p ON p.project_id=t.project_id SET t.company_id=p.company_id WHERE t.company_id IS NULL") if dialect == "mysql" else text("UPDATE crawler_task SET company_id=(SELECT company_id FROM crawler_project p WHERE p.project_id=crawler_task.project_id) WHERE company_id IS NULL"))
    if dialect == "mysql":
        bind.execute(text("UPDATE crawler_task_run r JOIN crawler_task t ON t.task_id=r.task_id SET r.company_id=t.company_id,r.project_id=t.project_id WHERE r.company_id IS NULL OR r.project_id IS NULL"))
    else:
        bind.execute(text("UPDATE crawler_task_run SET company_id=(SELECT company_id FROM crawler_task t WHERE t.task_id=crawler_task_run.task_id), project_id=(SELECT project_id FROM crawler_task t WHERE t.task_id=crawler_task_run.task_id) WHERE company_id IS NULL OR project_id IS NULL"))
    bind.execute(text("UPDATE crawler_task_run SET status='ASSIGNED' WHERE status='CLAIMED'"))
    bind.execute(text("UPDATE crawler_task_run SET status='SUCCEEDED' WHERE status='SUCCESS'"))
    bind.execute(text("UPDATE crawler_task_run SET status='TIMED_OUT' WHERE status='TIMEOUT'"))
    bind.execute(text("UPDATE crawler_task_run SET root_run_id=run_id WHERE root_run_id IS NULL"))

    users = bind.execute(text("SELECT user_id, role_type FROM sys_user")).fetchall()
    projects = bind.execute(text("SELECT project_id FROM crawler_project")).fetchall()
    for user_id, role_type in users:
        company_role = "OWNER" if role_type == "SUPER_ADMIN" else "MEMBER"
        project_role = "OWNER" if role_type == "SUPER_ADMIN" else "VIEWER"
        exists = bind.execute(text("SELECT member_id FROM crawler_company_member WHERE company_id=:c AND user_id=:u"), {"c": company_id, "u": user_id}).scalar()
        if not exists:
            bind.execute(text(f"INSERT INTO crawler_company_member(company_id,user_id,role,created_at,updated_at) VALUES(:c,:u,:r,{now_expr},{now_expr})"), {"c": company_id, "u": user_id, "r": company_role})
        for (project_id,) in projects:
            exists = bind.execute(text("SELECT member_id FROM crawler_project_member WHERE project_id=:p AND user_id=:u"), {"p": project_id, "u": user_id}).scalar()
            if not exists:
                bind.execute(text(f"INSERT INTO crawler_project_member(project_id,user_id,role,created_at,updated_at) VALUES(:p,:u,:r,{now_expr},{now_expr})"), {"p": project_id, "u": user_id, "r": project_role})


def downgrade() -> None:
    # V2 迁移包含生产数据回填，不提供破坏性自动降级；请使用升级前数据库备份回滚。
    pass
