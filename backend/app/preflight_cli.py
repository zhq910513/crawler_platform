from __future__ import annotations

import argparse
import json

from app.db import SessionLocal
from app.services.system_config_service import SystemConfigService


def main() -> int:
    parser = argparse.ArgumentParser(description="保存平台自检快照")
    parser.add_argument("--source", default="DEPLOY", help="检测来源：DEPLOY/MANUAL/AUTO")
    parser.add_argument("--detected-base-url", default="", help="可选：当前访问入口")
    args = parser.parse_args()
    with SessionLocal() as db:
        payload = SystemConfigService(db).get_system_settings(
            detected_base_url=args.detected_base_url,
            check_source=args.source,
            user=None,
            persist_snapshot=True,
        )
        preflight = payload.get("controlPlanePreflight") or {}
        print(json.dumps({
            "status": preflight.get("status"),
            "blockingCount": preflight.get("blockingCount"),
            "warningCount": preflight.get("warningCount"),
            "checkSource": preflight.get("checkSource"),
            "checkSourceLabel": preflight.get("checkSourceLabel"),
            "summary": preflight.get("summary"),
            "latestSnapshot": preflight.get("latestSnapshot"),
        }, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
