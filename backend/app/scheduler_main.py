from __future__ import annotations

import time

from app.config import settings
from app.db import SessionLocal
from app.services.routing_service import RoutingService
from app.services.run_service import RunService
from app.services.scheduler_service import SchedulerService


def main() -> None:
    while True:
        with SessionLocal() as db:
            SchedulerService(db).dispatch_due_schedules()
            RoutingService(db).reroute_or_wait_unclaimed()
            RunService(db).mark_lost_runs()
        time.sleep(settings.scheduler_poll_seconds)


if __name__ == "__main__":
    main()
