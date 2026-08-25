from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "versions" / "0017_project_build_center.py"


def test_project_build_center_error_message_text_has_no_mysql_server_default() -> None:
    content = MIGRATION.read_text(encoding="utf-8")
    assert 'sa.Column("error_message", sa.Text(), nullable=False),' in content
    assert 'sa.Column("error_message", sa.Text(), nullable=False, server_default=""),' not in content
