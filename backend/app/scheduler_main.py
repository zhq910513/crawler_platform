from app.config import settings
from app.init_db import init_db
from app.services.scheduler_service import SchedulerService


if __name__ == "__main__":
    settings.validate_runtime()
    init_db()
    SchedulerService().run_forever()
