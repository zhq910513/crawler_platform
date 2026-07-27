from app.init_db import init_db
from app.services.scheduler_service import SchedulerService


if __name__ == "__main__":
    init_db()
    SchedulerService().run_forever()
