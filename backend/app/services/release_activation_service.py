from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CrawlerProject,
    CrawlerProjectDeployment,
    CrawlerProjectDeploymentTarget,
    CrawlerProjectRelease,
    CrawlerProjectServer,
    CrawlerReleaseChannel,
)
from app.services.task_definition_lifecycle_service import TaskDefinitionLifecycleService
from app.utils import utcnow


class ReleaseActivationService:
    """Activate a project release only after deployment targets are actually ready.

    Registration/build creates an immutable release artifact. Deployment proves that
    the runtime can pull and self-check the image. Only then does this service move
    the release channel and expose the release manifest to task orchestration.
    """

    def __init__(self, db: Session):
        self.db = db
        self.definitions = TaskDefinitionLifecycleService(db)

    def activate_deployment(self, deployment: CrawlerProjectDeployment) -> dict:
        project = self.db.get(CrawlerProject, deployment.project_id)
        release = self.db.get(CrawlerProjectRelease, deployment.release_id)
        if not project or not release:
            return {"activated": False, "reason": "项目或 Release 不存在"}
        if deployment.deployment_status != "DEPLOYED":
            return {"activated": False, "reason": "部署尚未完成"}

        targets = list(self.db.scalars(
            select(CrawlerProjectDeploymentTarget).where(
                CrawlerProjectDeploymentTarget.deployment_id == deployment.deployment_id
            )
        ).all())
        ready_targets = [item for item in targets if item.target_status == "DEPLOYED" and item.image_readiness_status == "READY"]
        ready_count = len(ready_targets)
        if not targets or ready_count != len(targets):
            return {"activated": False, "reason": "仍有部署目标未完成运行前自检"}
        if ready_count < max(1, project.min_available_servers or 1):
            # Keep the old channel active. Deployment may be technically finished,
            # but the candidate release has not reached its availability floor.
            # Runtime status must still be derived from the currently active
            # channel; a blocked upgrade must not demote a healthy stable project.
            self.refresh_project_runtime_status(project)
            self._write_activation_strategy(
                deployment,
                status="BLOCKED",
                message=f"已部署节点仅 {ready_count} 个，低于最小可用节点 {project.min_available_servers}",
            )
            self.db.flush()
            return {
                "activated": False,
                "reason": "最小可用节点不足",
                "readyServerCount": ready_count,
                "minAvailableServers": project.min_available_servers,
            }

        # Candidate readiness lives on DeploymentTarget. Only after every selected
        # target has passed smoke test do we atomically promote ProjectServer runtime
        # facts to the new Release. Until this point the previous stable runtime is
        # untouched and remains routable.
        strategy = dict(deployment.strategy or {})
        target_meta = strategy.get("targets") if isinstance(strategy.get("targets"), list) else []
        meta_by_server = {int(item.get("serverId") or 0): item for item in target_meta if isinstance(item, dict)}
        promoted_server_ids = {item.server_id for item in ready_targets}
        now = utcnow()
        for target in ready_targets:
            ps = self.db.scalar(select(CrawlerProjectServer).where(
                CrawlerProjectServer.project_id == project.project_id,
                CrawlerProjectServer.server_id == target.server_id,
            ))
            if not ps:
                continue
            desired = str(meta_by_server.get(target.server_id, {}).get("desiredSchedulingStatus") or "ENABLED")
            ps.latest_release_id = release.release_id
            ps.latest_image_digest = release.image_digest
            ps.deployment_status = "DEPLOYED"
            ps.image_readiness_status = "READY"
            ps.scheduling_status = desired if desired in {"ENABLED", "RECOVERING", "PAUSED", "DRAINING", "DISABLED"} else "ENABLED"
            ps.disabled_reason = ""
            ps.last_deployed_at = target.last_deployed_at or now
        # Nodes outside this rollout keep their old image as a factual record, but
        # after stable promotion they are explicitly OUTDATED and cannot route the
        # new Release until a later deployment prepares them.
        for ps in self.db.scalars(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id)).all():
            if ps.server_id in promoted_server_ids or not ps.latest_release_id:
                continue
            if ps.latest_release_id != release.release_id:
                ps.image_readiness_status = "OUTDATED"
                ps.disabled_reason = f"当前节点仍运行旧 Release，stable 已激活 {release.version}"
        self.db.flush()

        channel_name = release.release_channel or "stable"
        channel = self.db.scalar(
            select(CrawlerReleaseChannel).where(
                CrawlerReleaseChannel.project_id == project.project_id,
                CrawlerReleaseChannel.channel_name == channel_name,
            )
        )
        if not channel:
            channel = CrawlerReleaseChannel(
                company_id=project.company_id,
                project_id=project.project_id,
                channel_name=channel_name,
                channel_status="ENABLED",
            )
            self.db.add(channel)
        channel.release_id = release.release_id
        channel.channel_status = "ENABLED"

        sync_result = self.definitions.sync_from_release(project, release)
        if project.status == "ENABLED" and project.online_status not in {"SUSPENDED", "OFFLINE"}:
            project.online_status = "ONLINE"
        self._write_activation_strategy(
            deployment,
            status="SUCCEEDED",
            message=f"Release {release.version} 已激活，{ready_count} 个节点已通过运行前自检",
            extra={"definitionSync": sync_result, "readyServerCount": ready_count},
        )
        self.db.flush()
        return {
            "activated": True,
            "releaseId": release.release_id,
            "releaseVersion": release.version,
            "channel": channel_name,
            "readyServerCount": ready_count,
            "definitionSync": sync_result,
        }

    def refresh_project_runtime_status(self, project: CrawlerProject) -> str:
        channel = self.db.scalar(
            select(CrawlerReleaseChannel).where(
                CrawlerReleaseChannel.project_id == project.project_id,
                CrawlerReleaseChannel.channel_name == "stable",
                CrawlerReleaseChannel.channel_status == "ENABLED",
            )
        )
        release_id = channel.release_id if channel else None
        ready_count = self.ready_server_count(project.project_id, release_id) if release_id else 0
        if project.status != "ENABLED" or project.online_status in {"SUSPENDED", "OFFLINE"}:
            return project.online_status
        project.online_status = "ONLINE" if ready_count >= max(1, project.min_available_servers or 1) else "READY"
        self.db.flush()
        return project.online_status

    def ready_server_count(self, project_id: int, release_id: int | None) -> int:
        if not release_id:
            return 0
        return int(
            self.db.scalar(
                select(func.count(CrawlerProjectServer.project_server_id)).where(
                    CrawlerProjectServer.project_id == project_id,
                    CrawlerProjectServer.latest_release_id == release_id,
                    CrawlerProjectServer.deployment_status == "DEPLOYED",
                    CrawlerProjectServer.image_readiness_status == "READY",
                    CrawlerProjectServer.scheduling_status.in_(["ENABLED", "RECOVERING"]),
                )
            )
            or 0
        )

    @staticmethod
    def _write_activation_strategy(
        deployment: CrawlerProjectDeployment,
        *,
        status: str,
        message: str,
        extra: dict | None = None,
    ) -> None:
        strategy = dict(deployment.strategy or {})
        steps = strategy.get("steps") if isinstance(strategy.get("steps"), list) else []
        activation = None
        for step in steps:
            if isinstance(step, dict) and step.get("key") == "RELEASE_ACTIVATION":
                activation = step
                break
        if activation is None:
            activation = {"key": "RELEASE_ACTIVATION", "title": "激活运行版本"}
            steps.append(activation)
        activation.update({"status": status, "message": message})
        if extra:
            activation["data"] = extra
        strategy["steps"] = steps
        strategy["activatedAt"] = utcnow().isoformat() if status == "SUCCEEDED" else strategy.get("activatedAt")
        strategy["updatedAt"] = utcnow().isoformat()
        deployment.strategy = strategy
