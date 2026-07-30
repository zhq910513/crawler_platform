from __future__ import annotations

import shutil
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete

from app.config import settings
from app.db import SessionLocal
from app.init_db import init_db
from app.models import CrawlerServerMetric
from app.utils import utcnow


def cleanup_metrics() -> None:
    cutoff = utcnow() - timedelta(days=settings.metric_retention_days)
    with SessionLocal() as db:
        db.execute(delete(CrawlerServerMetric).where(CrawlerServerMetric.recorded_at < cutoff))
        db.commit()


def cleanup_logs() -> None:
    root = Path(settings.task_log_root)
    cutoff = utcnow().date() - timedelta(days=settings.task_log_retention_days)
    if not root.exists():
        return
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            date_value = __import__("datetime").date.fromisoformat(child.name)
        except ValueError:
            continue
        if date_value < cutoff:
            shutil.rmtree(child, ignore_errors=True)


def run_forever() -> None:
    settings.validate_runtime()
    init_db()
    while True:
        try:
            cleanup_metrics()
            cleanup_logs()
        except Exception as exc:
            print(f"Worker cleanup error: {exc!r}")
        time.sleep(3600)


if __name__ == "__main__":
    run_forever()
