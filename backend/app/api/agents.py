from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_agent, get_current_user
from app.models import CrawlerAgent, SysUser
from app.responses import ok
from app.schemas import AgentHeartbeat, AgentRegistration, AgentRunClaim, AgentRunHeartbeat, AgentRunResult
from app.services.agent_service import AgentService
from app.services.server_service import ServerService

router = APIRouter(tags=["Agent"])


@router.post("/agents")
def create_agent(payload: AgentRegistration, user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok(ServerService(db).register_agent(user, payload))


@router.post("/agent-heartbeats")
def create_agent_heartbeat(payload: AgentHeartbeat, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).heartbeat(agent, payload))


@router.post("/agent-run-claims")
def create_agent_run_claim(payload: AgentRunClaim | None = None, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).claim_run(agent, payload or AgentRunClaim()))


@router.post("/agent-run-heartbeats")
def create_agent_run_heartbeat(payload: AgentRunHeartbeat, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).run_heartbeat(agent, payload))


@router.post("/agent-run-results")
def create_agent_run_result(payload: AgentRunResult, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).finish_run(agent, payload))
