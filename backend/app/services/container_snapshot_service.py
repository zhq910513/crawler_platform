from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerAgent, CrawlerRunContainerSnapshot, CrawlerTaskRun
from app.schemas import AgentRunContainerSnapshotCreate
from app.utils import utcnow


class ContainerSnapshotService:
    """Store task-container runtime snapshots without changing the run lifecycle.

    1.0.27 introduces a product-level split between task state and container state:
    each task execution still owns its lifecycle, while Agent can report Docker
    state independently for easier troubleshooting.
    """

    def __init__(self, db: Session):
        self.db = db

    def report(self, agent: CrawlerAgent, payload: AgentRunContainerSnapshotCreate) -> CrawlerRunContainerSnapshot:
        run = self.db.get(CrawlerTaskRun, payload.run_id)
        if not run or run.company_id != agent.company_id:
            raise AppError("运行实例不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        if run.agent_id and run.agent_id != agent.agent_id:
            raise AppError("该运行实例不属于当前 Agent", code=40331, http_status=status.HTTP_403_FORBIDDEN)
        if run.lease_token and run.lease_token != payload.lease_token:
            raise AppError("运行租约无效", code=40131, http_status=status.HTTP_401_UNAUTHORIZED)
        observed_at = payload.observed_at or utcnow()
        snapshot = CrawlerRunContainerSnapshot(
            company_id=run.company_id,
            run_id=run.run_id,
            task_id=run.task_id,
            project_id=run.project_id,
            server_id=run.server_id or agent.server_id,
            agent_id=agent.agent_id,
            container_id=payload.container_id,
            container_name=payload.container_name,
            image_digest=payload.image_digest or run.image_digest,
            container_status=payload.container_status,
            exit_code=payload.exit_code,
            oom_killed=payload.oom_killed,
            restart_count=payload.restart_count,
            cpu_usage=payload.cpu_usage,
            memory_usage_mb=payload.memory_usage_mb,
            started_at=payload.started_at,
            finished_at=payload.finished_at,
            last_log_line=payload.last_log_line,
            payload_json=payload.payload,
            observed_at=observed_at,
        )
        self.db.add(snapshot)
        run.result_payload = {
            **(run.result_payload or {}),
            "container": {
                "snapshotId": None,
                "containerId": payload.container_id,
                "containerName": payload.container_name,
                "imageDigest": payload.image_digest or run.image_digest,
                "containerStatus": payload.container_status,
                "exitCode": payload.exit_code,
                "oomKilled": payload.oom_killed,
                "restartCount": payload.restart_count,
                "cpuUsage": payload.cpu_usage,
                "memoryUsageMb": payload.memory_usage_mb,
                "startedAt": payload.started_at.isoformat() if isinstance(payload.started_at, datetime) else None,
                "finishedAt": payload.finished_at.isoformat() if isinstance(payload.finished_at, datetime) else None,
                "lastLogLine": payload.last_log_line,
                "observedAt": observed_at.isoformat(),
            },
        }
        if payload.container_status in {"FAILED", "TIMED_OUT", "OOM_KILLED", "LOST"} and not run.failed_stage:
            run.failed_stage = "CONTAINER"
        if payload.container_status == "OOM_KILLED" and not run.error_summary:
            run.error_type = "CONTAINER_OOM"
            run.error_summary = "容器内存不足，建议降低并发或提高任务内存限制。"
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def latest_by_run_ids(self, run_ids: list[int]) -> dict[int, CrawlerRunContainerSnapshot]:
        if not run_ids:
            return {}
        rows = list(self.db.scalars(select(CrawlerRunContainerSnapshot).where(CrawlerRunContainerSnapshot.run_id.in_(run_ids)).order_by(CrawlerRunContainerSnapshot.run_id.asc(), desc(CrawlerRunContainerSnapshot.observed_at))).all())
        result: dict[int, CrawlerRunContainerSnapshot] = {}
        for row in rows:
            result.setdefault(row.run_id, row)
        return result
