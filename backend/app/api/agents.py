from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_agent, get_current_user
from app.models import CrawlerAgent, SysUser
from app.responses import ok
from app.schemas import AgentCommandResult, AgentContainerCleanupResult, AgentHeartbeat, AgentImagePullResult, AgentRegistration, AgentRunClaim, AgentRunHeartbeat, AgentRunResult, AgentRunEventCreate, AgentRunLogChunkCreate, AgentRunLogFinalizeCreate, AgentRunContainerSnapshotCreate
from app.services.agent_service import AgentService
from app.services.server_service import ServerService
from app.services.run_log_service import RunLogService
from app.services.container_snapshot_service import ContainerSnapshotService

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

@router.post("/agent-image-pull-results")
def create_agent_image_pull_result(payload: AgentImagePullResult, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).report_image_pull_result(agent, payload))


@router.post("/agent-container-cleanup-results")
def create_agent_container_cleanup_result(payload: AgentContainerCleanupResult, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).report_container_cleanup_result(agent, payload))


@router.post("/agent-command-results")
def create_agent_command_result(payload: AgentCommandResult, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).report_agent_command_result(agent, payload))




@router.post("/agent-run-heartbeats")
def create_agent_run_heartbeat(payload: AgentRunHeartbeat, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).run_heartbeat(agent, payload))


@router.post("/agent-run-results")
def create_agent_run_result(payload: AgentRunResult, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(AgentService(db).finish_run(agent, payload))

@router.post("/agent-run-events")
def create_agent_run_event(payload: AgentRunEventCreate, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(RunLogService(db).append_event(agent, payload))


@router.post("/agent-run-log-chunks")
def create_agent_run_log_chunk(payload: AgentRunLogChunkCreate, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(RunLogService(db).append_chunk(agent, payload))




@router.post("/agent-container-snapshots")
def create_agent_container_snapshot(payload: AgentRunContainerSnapshotCreate, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(ContainerSnapshotService(db).report(agent, payload))


@router.post("/agent-run-log-finalizations")
def create_agent_run_log_finalization(payload: AgentRunLogFinalizeCreate, agent: CrawlerAgent = Depends(get_agent), db: Session = Depends(get_db)):
    return ok(RunLogService(db).finalize(agent, payload))
