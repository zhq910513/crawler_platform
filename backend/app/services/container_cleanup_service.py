from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerServer, SysUser
from app.utils import utcnow

_PENDING_KEY = "pendingContainerCleanups"
_DONE_KEY = "lastContainerCleanupResults"
_MAX_PENDING = 100
_MAX_DONE = 50


class ContainerCleanupService:
    """Queue idempotent Docker container cleanup commands for the Agent of each server.

    No new database table is required: cleanup commands live in crawler_server.metrics so
    they persist across platform restarts and are picked up by the existing Agent heartbeat.
    """

    def __init__(self, db: Session):
        self.db = db

    def enqueue_project_cleanup(
        self,
        *,
        company_id: int,
        project_id: int,
        project_code: str,
        server_ids: list[int],
        user: SysUser | None,
        reason: str,
    ) -> list[dict[str, Any]]:
        return self._enqueue(
            company_id=company_id,
            project_id=project_id,
            project_code=project_code,
            task_id=None,
            task_code="",
            server_ids=server_ids,
            user=user,
            reason=reason,
        )

    def enqueue_task_cleanup(
        self,
        *,
        company_id: int,
        project_id: int,
        project_code: str,
        task_id: int,
        task_code: str,
        server_ids: list[int],
        user: SysUser | None,
        reason: str,
    ) -> list[dict[str, Any]]:
        return self._enqueue(
            company_id=company_id,
            project_id=project_id,
            project_code=project_code,
            task_id=task_id,
            task_code=task_code,
            server_ids=server_ids,
            user=user,
            reason=reason,
        )

    def pending_for_server(self, server: CrawlerServer) -> list[dict[str, Any]]:
        metrics = dict(server.metrics or {})
        pending = metrics.get(_PENDING_KEY) or []
        return [item for item in pending if isinstance(item, dict)]

    def acknowledge(self, server: CrawlerServer, cleanup_id: str, result: dict[str, Any]) -> bool:
        metrics = dict(server.metrics or {})
        pending = [item for item in metrics.get(_PENDING_KEY) or [] if isinstance(item, dict)]
        kept = [item for item in pending if item.get("cleanupId") != cleanup_id]
        if len(kept) == len(pending):
            metrics[_PENDING_KEY] = kept[-_MAX_PENDING:]
            server.metrics = metrics
            return False
        done = [item for item in metrics.get(_DONE_KEY) or [] if isinstance(item, dict)]
        done.append({"cleanupId": cleanup_id, "reportedAt": utcnow().isoformat(), **result})
        metrics[_PENDING_KEY] = kept[-_MAX_PENDING:]
        metrics[_DONE_KEY] = done[-_MAX_DONE:]
        server.metrics = metrics
        return True

    def _enqueue(
        self,
        *,
        company_id: int,
        project_id: int,
        project_code: str,
        task_id: int | None,
        task_code: str,
        server_ids: list[int],
        user: SysUser | None,
        reason: str,
    ) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        clean_server_ids = sorted({int(item) for item in server_ids if item})
        if not clean_server_ids:
            return commands
        servers = list(self.db.scalars(select(CrawlerServer).where(CrawlerServer.company_id == company_id, CrawlerServer.server_id.in_(clean_server_ids))).all())
        for server in servers:
            command = {
                "cleanupId": f"cleanup-{uuid4().hex}",
                "cleanupScope": "TASK" if task_id else "PROJECT",
                "companyId": company_id,
                "projectId": project_id,
                "projectCode": project_code,
                "taskId": task_id,
                "taskCode": task_code,
                "reason": reason,
                "requestedBy": user.user_id if user else None,
                "createdAt": utcnow().isoformat(),
            }
            metrics = dict(server.metrics or {})
            pending = [item for item in metrics.get(_PENDING_KEY) or [] if isinstance(item, dict)]
            deduped = [item for item in pending if not self._same_target(item, command)]
            deduped.append(command)
            metrics[_PENDING_KEY] = deduped[-_MAX_PENDING:]
            server.metrics = metrics
            commands.append({"serverId": server.server_id, "serverCode": server.server_code, "cleanupId": command["cleanupId"], "cleanupScope": command["cleanupScope"]})
        return commands

    @staticmethod
    def _same_target(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return (
            left.get("cleanupScope") == right.get("cleanupScope")
            and int(left.get("projectId") or 0) == int(right.get("projectId") or 0)
            and int(left.get("taskId") or 0) == int(right.get("taskId") or 0)
        )
