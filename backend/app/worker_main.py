from __future__ import annotations

import time

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import CrawlerAgent, CrawlerProjectServer, CrawlerServer
from app.services.alert_service import AlertService
from app.services.routing_service import RoutingService
from app.utils import utcnow


def main() -> None:
    while True:
        with SessionLocal() as db:
            agents = list(db.scalars(select(CrawlerAgent).where(CrawlerAgent.connection_status.in_(["ONLINE", "STALE"]))).all())
            for agent in agents:
                if not agent.last_heartbeat_at:
                    continue
                delta = (utcnow() - agent.last_heartbeat_at).total_seconds()
                server = db.get(CrawlerServer, agent.server_id)
                if delta > settings.agent_offline_seconds:
                    agent.connection_status = "OFFLINE"
                    if server:
                        server.health_status = "UNHEALTHY"
                        for ps in db.scalars(select(CrawlerProjectServer).where(CrawlerProjectServer.server_id == server.server_id, CrawlerProjectServer.scheduling_status.in_(["ENABLED", "RECOVERING"]))).all():
                            if ps.auto_eject_enabled:
                                ps.scheduling_status = "AUTO_EJECTED"
                                ps.disabled_reason = "Agent 离线，系统自动摘除"
                elif delta > settings.agent_stale_seconds:
                    agent.connection_status = "STALE"
            RoutingService(db).reroute_or_wait_unclaimed(commit=False)
            AlertService(db).process_pending()
            db.commit()
        time.sleep(10)


if __name__ == "__main__":
    main()
