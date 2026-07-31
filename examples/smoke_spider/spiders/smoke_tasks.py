from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def run(message: str = "hello", sleep_seconds: float = 0.2, **kwargs: Any) -> dict[str, Any]:
    run_id = os.getenv("CRAWLER_RUN_ID", "unknown")
    project_code = os.getenv("CRAWLER_PROJECT_CODE", "unknown")
    task_code = os.getenv("CRAWLER_TASK_CODE", "unknown")
    work_dir = Path(os.getenv("CRAWLER_WORK_DIR", "/work"))
    log_dir = Path(os.getenv("CRAWLER_LOG_DIR", "/logs"))
    cache_dir = Path(os.getenv("CRAWLER_CACHE_DIR", "/cache"))
    profile_dir = Path(os.getenv("CRAWLER_PROFILE_DIR", "/profiles"))
    for path in (work_dir, log_dir, cache_dir, profile_dir):
        path.mkdir(parents=True, exist_ok=True)
    time.sleep(float(sleep_seconds))
    payload = {
        "runId": run_id,
        "projectCode": project_code,
        "taskCode": task_code,
        "message": message,
        "kwargs": kwargs,
        "workDir": str(work_dir),
        "logDir": str(log_dir),
        "cacheDir": str(cache_dir),
        "profileDir": str(profile_dir),
    }
    (work_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (log_dir / "smoke.log").write_text("smoke task succeeded\n", encoding="utf-8")
    (cache_dir / "cache-marker.txt").write_text("shared cache ok\n", encoding="utf-8")
    return payload
