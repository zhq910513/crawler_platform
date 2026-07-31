"""add company server boundary and project remark

Revision ID: 20260730_04
Revises: 20260730_03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260730_04"
down_revision = "20260730_03"
branch_labels = None
depends_on = None


def _tables():
    return set(inspect(op.get_bind()).get_table_names())


def _has_column(table, column):
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and any(item["name"] == column for item in inspector.get_columns(table))


def _add_column(table, column):
    if not _has_column(table, column.name):
        op.add_column(table, column)


def _index_names(table):
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    names = set(str(item.get("name")) for item in inspector.get_indexes(table) if item.get("name"))
    names.update(str(item.get("name")) for item in inspector.get_unique_constraints(table) if item.get("name"))
    return names


def _fk_names(table):
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return set(str(item.get("name")) for item in inspector.get_foreign_keys(table) if item.get("name"))


def _create_index(name, table, columns, unique=False):
    if table in _tables() and name not in _index_names(table):
        op.create_index(name, table, columns, unique=unique)


def _create_fk(name, source, referent, local_cols, remote_cols, ondelete=None):
    if source in _tables() and referent in _tables() and name not in _fk_names(source):
        op.create_foreign_key(name, source, referent, local_cols, remote_cols, ondelete=ondelete)


def upgrade():
    bind = op.get_bind()

    _add_column("crawler_project", sa.Column("remark", sa.String(500), nullable=False, server_default=""))

    duplicates = bind.execute(text("""
        SELECT company_id, project_name, COUNT(*) AS cnt
        FROM crawler_project
        GROUP BY company_id, project_name
        HAVING COUNT(*) > 1
        LIMIT 5
    """)).fetchall()
    if duplicates:
        raise RuntimeError("同一公司下存在重复项目名称，请先清理 crawler_project 后再迁移")

    _create_index("uk_crawler_project_company_name", "crawler_project", ["company_id", "project_name"], unique=True)

    default_company_id = bind.execute(text("SELECT company_id FROM crawler_company ORDER BY company_id LIMIT 1")).scalar()
    if default_company_id is None:
        raise RuntimeError("crawler_company 为空，无法为 crawler_server 回填 company_id")

    _add_column("crawler_server", sa.Column("company_id", sa.BigInteger(), nullable=True))
    bind.execute(text("UPDATE crawler_server SET company_id = :company_id WHERE company_id IS NULL"), {"company_id": int(default_company_id)})
    try:
        op.alter_column("crawler_server", "company_id", existing_type=sa.BigInteger(), nullable=False)
    except Exception:
        pass
    _create_index("ix_crawler_server_company_id", "crawler_server", ["company_id"])
    _create_fk("fk_crawler_server_company_id", "crawler_server", "crawler_company", ["company_id"], ["company_id"], ondelete="CASCADE")


def downgrade():
    pass
