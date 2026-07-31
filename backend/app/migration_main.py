from __future__ import annotations

from alembic import command
from alembic.config import Config
from pathlib import Path

from app.db import SessionLocal
from app.init_db import init_admin


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        init_admin(db)


if __name__ == "__main__":
    main()
