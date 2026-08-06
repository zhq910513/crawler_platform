from __future__ import annotations

from datetime import timedelta
import re
from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    CrawlerCompanyDiscoveryToken,
    CrawlerDiscoveredProject,
    CrawlerDiscoveredProjectServer,
    CrawlerImageArtifact,
    CrawlerProject,
    CrawlerProjectMember,
    CrawlerProjectRelease,
    CrawlerProjectServer,
    CrawlerProjectDeployment,
    CrawlerProjectDeploymentTarget,
    CrawlerProjectTaskDefinition,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerTask,
    CrawlerTaskRun,
    SysUser,
)
from app.repositories.platform import DiscoveredProjectRepository, ProjectRepository, ProjectServerRepository, ServerRepository
from app.schemas import ProjectDiscoveryCreate, ProjectImport, ProjectReleaseDeploy, ProjectServerPoolUpdate, ProjectUpdate
from app.services.permissions import is_super_admin, require_company_scope, require_project_role, scoped_company_id
from app.services.audit import write_operation_log
from app.utils import sha256_text, utcnow


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.discovered = DiscoveredProjectRepository(db)
        self.projects = ProjectRepository(db)
        self.servers = ServerRepository(db)
        self.project_servers = ProjectServerRepository(db)

    def validate_discovery_token(self, payload: ProjectDiscoveryCreate, authorization: str | None) -> None:
        if not authorization or not authorization.startswith("Discovery "):
            raise AppError("项目接入凭证无效", code=40150, http_status=status.HTTP_401_UNAUTHORIZED)
        token_hash = sha256_text(authorization[10:].strip())
        token = self.db.scalar(select(CrawlerCompanyDiscoveryToken).where(CrawlerCompanyDiscoveryToken.token_hash == token_hash, CrawlerCompanyDiscoveryToken.status == "ENABLED"))
        if not token or token.company_id != payload.company_id:
            raise AppError("项目接入凭证无效", code=40151, http_status=status.HTTP_401_UNAUTHORIZED)
        if token.expires_at and token.expires_at < utcnow():
            raise AppError("项目接入凭证已过期", code=40152, http_status=status.HTTP_401_UNAUTHORIZED)
        token.last_used_at = utcnow()

    def list_discovered(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        scoped = scoped_company_id(user, company_id)
        rows = self.discovered.list_projects(scoped)
        return [self._discovered_payload(row) for row in rows]

    def upsert_discovered(self, payload: ProjectDiscoveryCreate) -> CrawlerDiscoveredProject:
        server_codes = self._normalize_server_codes(payload.server_codes or ([payload.server_code] if payload.server_code else []))
        servers = self._resolve_registration_servers(payload.company_id, server_codes)
        manifest = payload.manifest
        self._validate_release_version(manifest.release_version)
        if not manifest.task_definitions:
            raise AppError("manifest 中未发现任务定义，sch.py 解析结果不能为空", code=40043)
        project = self.discovered.by_company_key(payload.company_id, manifest.project_key)
        now = utcnow()
        if not project:
            project = CrawlerDiscoveredProject(
                company_id=payload.company_id,
                project_key=manifest.project_key,
                project_code=manifest.project_code,
                project_name=manifest.project_name,
                repository_url=manifest.repository_url,
                image_repository=manifest.image_repository,
                latest_version=manifest.release_version,
                latest_image_digest=manifest.image_digest,
                discovery_status="READY_TO_IMPORT",
                parse_status="SUCCESS",
                first_deployed_at=now,
                last_deployed_at=now,
                manifest=manifest.model_dump(by_alias=True),
            )
            self.db.add(project)
            self.db.flush()
        else:
            project.project_code = manifest.project_code
            project.project_name = manifest.project_name
            project.repository_url = manifest.repository_url
            project.image_repository = manifest.image_repository
            project.latest_version = manifest.release_version
            project.latest_image_digest = manifest.image_digest
            project.parse_status = "SUCCESS"
            project.parse_error = ""
            project.last_deployed_at = now
            project.manifest = manifest.model_dump(by_alias=True)
            if project.discovery_status != "IMPORTED":
                project.discovery_status = "READY_TO_IMPORT"
        artifact = self._upsert_artifact(manifest, now)
        release = self._upsert_release(payload.company_id, project, artifact.artifact_id, manifest)
        project.latest_release_id = release.release_id
        for server in servers:
            self._upsert_discovered_server(project, server, manifest.image_digest, now)
        if project.formal_project_id:
            self._sync_formal_project(project, release, servers, now)
        self.db.commit()
        return project

    def list_projects(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        if is_super_admin(user):
            rows = self.projects.list_projects(company_id)
        else:
            scoped = scoped_company_id(user, company_id)
            rows = self.projects.list_projects(scoped, user.user_id)
        return [self._project_summary(row) for row in rows]

    def import_project(self, user: SysUser, payload: ProjectImport) -> CrawlerProject:
        discovered = self.discovered.get(payload.discovered_project_id)
        if not discovered:
            raise AppError("待接入项目不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, discovered.company_id)
        if not is_super_admin(user):
            raise AppError("普通用户不能接入项目", code=40341, http_status=status.HTTP_403_FORBIDDEN)
        if discovered.formal_project_id or discovered.discovery_status == "IMPORTED":
            raise AppError("该项目已经接入", code=40041)
        if self.projects.by_company_code(discovered.company_id, discovered.project_code):
            raise AppError("项目编码已存在", code=40042)
        project = CrawlerProject(
            company_id=discovered.company_id,
            discovered_project_id=discovered.discovered_project_id,
            project_key=discovered.project_key,
            project_code=discovered.project_code,
            project_name=discovered.project_name,
            remark=payload.remark,
            repository_url=discovered.repository_url,
            image_repository=discovered.image_repository,
            online_status="READY",
            dispatch_mode=payload.dispatch_mode,
            min_available_servers=payload.min_available_servers,
            max_active_servers=payload.max_active_servers,
            allow_deployed_fallback=payload.allow_deployed_fallback,
            allow_company_pool_fallback=payload.allow_company_pool_fallback,
            default_runtime_mode=payload.default_runtime_mode,
            default_task_max_concurrency=payload.default_task_max_concurrency,
            default_group_max_concurrency=payload.default_group_max_concurrency,
            default_shm_size_mb=payload.default_shm_size_mb,
            default_log_limit_mb=payload.default_log_limit_mb,
            container_config=payload.container_config,
            created_by=user.user_id,
        )
        self.db.add(project)
        self.db.flush()
        self.db.add(CrawlerProjectMember(project_id=project.project_id, user_id=user.user_id, role="OWNER"))
        discovered.formal_project_id = project.project_id
        discovered.discovery_status = "IMPORTED"
        releases = list(self.db.scalars(select(CrawlerProjectRelease).where(CrawlerProjectRelease.discovered_project_id == discovered.discovered_project_id)).all())
        for release in releases:
            release.project_id = project.project_id
        latest_release = self.db.get(CrawlerProjectRelease, discovered.latest_release_id) if discovered.latest_release_id else (releases[-1] if releases else None)
        if latest_release:
            self._bind_release_channel(project, latest_release)
        dps_items = list(self.db.scalars(select(CrawlerDiscoveredProjectServer).where(CrawlerDiscoveredProjectServer.discovered_project_id == discovered.discovered_project_id)).all())
        for idx, item in enumerate(dps_items):
            self._upsert_project_server(project, item.server_id, latest_release, item.latest_image_digest, item.last_deployed_at, idx, payload.dispatch_mode)
        if latest_release:
            self._mark_existing_project_servers_outdated(project, latest_release, utcnow())
            self._sync_task_definitions(project, latest_release)
        write_operation_log(self.db, user, None, operation_type="IMPORT_PROJECT", resource_type="project", resource_id=str(project.project_id), after_data={"projectId": project.project_id, "companyId": project.company_id, "discoveredProjectId": discovered.discovered_project_id, "dispatchMode": project.dispatch_mode})
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError("项目接入数据冲突，请检查版本号或通道", code=40044) from exc
        return project

    def get_project(self, user: SysUser, project_id: int) -> dict:
        project = require_project_role(self.db, user, project_id, "VIEWER")
        return self._project_summary(project)

    def update_project(self, user: SysUser, project_id: int, payload: ProjectUpdate) -> CrawlerProject:
        project = require_project_role(self.db, user, project_id, "OWNER")
        before = {c.name: getattr(project, c.name) for c in project.__table__.columns}
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(project, key, value)
        self._validate_project_pool(project)
        after = {c.name: getattr(project, c.name) for c in project.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_PROJECT", resource_type="project", resource_id=str(project.project_id), before_data=before, after_data=after)
        self.db.commit()
        return project

    def list_project_servers(self, user: SysUser, project_id: int) -> list[dict]:
        require_project_role(self.db, user, project_id, "VIEWER")
        items = self.project_servers.list_by_project(project_id)
        return [self._project_server_payload(item) for item in items]

    def deploy_release_to_servers(self, user: SysUser, project_id: int, payload: ProjectReleaseDeploy) -> dict:
        project = require_project_role(self.db, user, project_id, "OWNER")
        release = self.db.get(CrawlerProjectRelease, payload.release_id) if payload.release_id else self._latest_project_release(project.project_id)
        if not release or release.project_id != project.project_id or release.release_status != "PUBLISHED":
            raise AppError("项目 release 不存在或不可部署", code=40451, http_status=status.HTTP_404_NOT_FOUND)
        if not payload.server_ids:
            raise AppError("请选择至少一台已安装 Agent 的服务器", code=40051)
        servers = []
        unavailable = []
        for server_id in sorted(set(payload.server_ids)):
            server = self.db.get(CrawlerServer, server_id)
            if not server or server.company_id != project.company_id:
                unavailable.append({"serverId": server_id, "reason": "服务器不存在或不属于该公司"})
                continue
            if server.manage_status == "DISABLED":
                unavailable.append({"serverId": server_id, "reason": "服务器已禁用"})
                continue
            if not server.agent:
                unavailable.append({"serverId": server_id, "reason": "该服务器尚未安装或绑定 Agent"})
                continue
            servers.append(server)
        if unavailable:
            raise AppError("部署目标校验未通过", code=40052, data={"unavailableServers": unavailable})
        now = utcnow()
        deployment = CrawlerProjectDeployment(
            company_id=project.company_id,
            project_id=project.project_id,
            release_id=release.release_id,
            deployment_name=payload.reason or f"部署 {release.version}",
            strategy={"prewarmWhenIdle": payload.prewarm_when_idle, "maxParallelPulls": payload.max_parallel_pulls},
            deployment_status="CREATED",
            created_by=user.user_id,
        )
        self.db.add(deployment)
        self.db.flush()
        targets = []
        existing_count = len(self.project_servers.list_by_project(project.project_id))
        for idx, server in enumerate(servers):
            ps = self._upsert_project_server(project, server.server_id, release, release.image_digest, now, existing_count + idx, project.dispatch_mode)
            ps.scheduling_status = "ENABLED" if ps.scheduling_status in {"DISABLED"} else ps.scheduling_status
            target = CrawlerProjectDeploymentTarget(
                deployment_id=deployment.deployment_id,
                company_id=project.company_id,
                project_id=project.project_id,
                release_id=release.release_id,
                server_id=server.server_id,
                target_status=ps.image_readiness_status or "OUTDATED",
                image_readiness_status=ps.image_readiness_status or "OUTDATED",
                last_deployed_at=now,
            )
            self.db.add(target)
            targets.append({"serverId": server.server_id, "serverCode": server.server_code, "serverName": server.server_name, "imageReadinessStatus": ps.image_readiness_status, "latestImageDigest": ps.latest_image_digest})
        deployment.deployment_status = "READY_TO_PREWARM"
        write_operation_log(self.db, user, None, operation_type="DEPLOY_PROJECT_RELEASE", resource_type="project", resource_id=str(project.project_id), after_data={"projectId": project.project_id, "releaseId": release.release_id, "serverIds": [s.server_id for s in servers]})
        self.db.commit()
        return {"deploymentId": deployment.deployment_id, "projectId": project.project_id, "releaseId": release.release_id, "releaseVersion": release.version, "imageRepository": release.image_repository, "imageDigest": release.image_digest, "targets": targets, "message": "部署计划已创建；Agent 心跳会收到待预热镜像，已有运行实例不会被打断。"}

    def list_deployments(self, user: SysUser, project_id: int) -> list[dict]:
        require_project_role(self.db, user, project_id, "VIEWER")
        rows = list(self.db.scalars(select(CrawlerProjectDeployment).where(CrawlerProjectDeployment.project_id == project_id).order_by(CrawlerProjectDeployment.created_at.desc())).all())
        result = []
        for deployment in rows:
            targets = list(self.db.scalars(select(CrawlerProjectDeploymentTarget).where(CrawlerProjectDeploymentTarget.deployment_id == deployment.deployment_id)).all())
            result.append({
                **{c.name: getattr(deployment, c.name) for c in deployment.__table__.columns},
                "targets": [{**{c.name: getattr(target, c.name) for c in target.__table__.columns}, "serverName": (self.db.get(CrawlerServer, target.server_id).server_name if self.db.get(CrawlerServer, target.server_id) else "")} for target in targets],
            })
        return result

    def analyze_server_pool(self, user: SysUser, project_id: int, payload: ProjectServerPoolUpdate) -> dict:
        project = require_project_role(self.db, user, project_id, "OWNER")
        existing = {item.server_id: item for item in self.project_servers.list_by_project(project_id)}
        latest_release = self._latest_project_release(project.project_id)
        current_running = self.db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.project_id == project_id, CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]))) or 0
        future_window = utcnow() + timedelta(minutes=10)
        upcoming = self.db.scalar(select(func.count(CrawlerTask.task_id)).where(CrawlerTask.project_id == project_id, CrawlerTask.status == "ENABLED")) or 0
        details = []
        unavailable = []
        for item in payload.servers:
            ps = existing.get(item.server_id)
            server = self.db.get(CrawlerServer, item.server_id)
            reason = ""
            available = True
            will_create = False
            if not server or server.company_id != project.company_id:
                reason = "服务器不存在或不属于该公司"
                available = False
            elif not ps or ps.deployment_status != "DEPLOYED":
                if latest_release and latest_release.image_digest:
                    reason = "将按项目最新发布版本建立部署记录，Agent 执行时按 digest 拉取镜像"
                    will_create = True
                else:
                    reason = "项目尚无可用发布版本，不能加入执行池"
                    available = False
            elif ps.image_readiness_status not in {"READY", "OUTDATED", "WARMING"}:
                reason = "镜像状态未就绪"
                available = False
            if not available:
                unavailable.append({"serverId": item.server_id, "reason": reason})
            details.append({"serverId": item.server_id, "available": available, "willCreateDeployment": will_create, "reason": reason, "targetSchedulingStatus": item.scheduling_status})
        enabled_count = sum(1 for item in payload.servers if item.scheduling_status in {"ENABLED", "RECOVERING"} and not any(x["serverId"] == item.server_id for x in unavailable))
        return {"projectId": project_id, "canSave": not unavailable and enabled_count >= project.min_available_servers, "enabledServerCount": enabled_count, "minAvailableServers": project.min_available_servers, "currentRunningCount": current_running, "upcomingTaskCountInTenMinutes": upcoming, "unavailableServers": unavailable, "details": details, "p0Risk": enabled_count < project.min_available_servers}

    def update_server_pool(self, user: SysUser, project_id: int, payload: ProjectServerPoolUpdate) -> list[dict]:
        project = require_project_role(self.db, user, project_id, "OWNER")
        analysis = self.analyze_server_pool(user, project_id, payload)
        if not analysis["canSave"]:
            raise AppError("执行服务器池校验未通过", code=40045, data=analysis)
        existing = {item.server_id: item for item in self.project_servers.list_by_project(project_id)}
        before = [self._project_server_payload(item) for item in existing.values()]
        latest_release = self._latest_project_release(project.project_id)
        now = utcnow()
        for idx, item in enumerate(payload.servers):
            ps = existing.get(item.server_id)
            if not ps:
                if not latest_release:
                    raise AppError("项目尚无可用发布版本，不能加入执行池", code=40046)
                ps = self._upsert_project_server(project, item.server_id, latest_release, latest_release.image_digest, now, idx, project.dispatch_mode)
                existing[item.server_id] = ps
            ps.scheduling_status = item.scheduling_status
            ps.server_role = item.server_role
            ps.priority = item.priority
            ps.weight = item.weight
            ps.max_concurrency = item.max_concurrency
            ps.auto_eject_enabled = item.auto_eject_enabled
            ps.auto_recover_enabled = item.auto_recover_enabled
            ps.disabled_reason = payload.reason if item.scheduling_status in {"PAUSED", "DRAINING", "DISABLED"} else ps.disabled_reason if ps.image_readiness_status == "OUTDATED" else ""
        self._validate_project_pool(project)
        after = [self._project_server_payload(item) for item in self.project_servers.list_by_project(project_id)]
        write_operation_log(self.db, user, None, operation_type="UPDATE_PROJECT_SERVER_POOL", resource_type="project", resource_id=str(project.project_id), before_data={"servers": before}, after_data={"servers": after, "reason": payload.reason})
        self.db.commit()
        return self.list_project_servers(user, project_id)

    def _upsert_artifact(self, manifest, now):
        artifact = self.db.scalar(select(CrawlerImageArtifact).where(CrawlerImageArtifact.image_repository == manifest.image_repository, CrawlerImageArtifact.image_digest == manifest.image_digest))
        if artifact:
            return artifact
        artifact = CrawlerImageArtifact(image_repository=manifest.image_repository, image_digest=manifest.image_digest, image_tag=manifest.release_version, supported_arch=manifest.supported_arch, git_commit=manifest.git_commit, build_time=now, artifact_metadata={"runtimeType": manifest.runtime_type})
        self.db.add(artifact)
        self.db.flush()
        return artifact

    @staticmethod
    def _normalize_server_codes(values) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            for raw in str(value or "").split(","):
                code = raw.strip()
                if code and code not in seen:
                    result.append(code)
                    seen.add(code)
        return result

    def _resolve_registration_servers(self, company_id: int, server_codes: list[str]) -> list[CrawlerServer]:
        servers: list[CrawlerServer] = []
        for code in server_codes:
            server = self.servers.by_code(code)
            if not server or server.company_id != company_id:
                raise AppError(f"服务器不存在或不属于该公司：{code}", code=40401, http_status=status.HTTP_404_NOT_FOUND)
            servers.append(server)
        return servers

    def _latest_project_release(self, project_id: int) -> CrawlerProjectRelease | None:
        return self.db.scalar(select(CrawlerProjectRelease).where(CrawlerProjectRelease.project_id == project_id, CrawlerProjectRelease.release_status == "PUBLISHED", CrawlerProjectRelease.parse_status == "SUCCESS").order_by(CrawlerProjectRelease.published_at.desc(), CrawlerProjectRelease.release_id.desc()))

    @staticmethod
    def _validate_release_version(version: str) -> None:
        if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", version or ""):
            raise AppError("releaseVersion 必须是不可变语义版本，例如 1.0.19；main/dev/latest 等浮动版本禁止注册", code=40045)

    def _upsert_release(self, company_id: int, discovered: CrawlerDiscoveredProject, artifact_id: int, manifest) -> CrawlerProjectRelease:
        stmt = select(CrawlerProjectRelease).where(CrawlerProjectRelease.discovered_project_id == discovered.discovered_project_id, CrawlerProjectRelease.version == manifest.release_version)
        release = self.db.scalar(stmt)
        if release:
            conflicts: list[str] = []
            if release.image_repository != manifest.image_repository:
                conflicts.append("imageRepository")
            if release.image_digest != manifest.image_digest:
                conflicts.append("imageDigest")
            if (release.git_commit or "") and manifest.git_commit and release.git_commit != manifest.git_commit:
                conflicts.append("gitCommit")
            if conflicts:
                raise AppError(
                    "项目发布版本不可变：同一 project/releaseVersion 禁止覆盖不同镜像或提交，请递增 patch 版本后重新发布",
                    code=40046,
                    http_status=status.HTTP_409_CONFLICT,
                )
        if not release:
            release = CrawlerProjectRelease(company_id=company_id, discovered_project_id=discovered.discovered_project_id, project_id=discovered.formal_project_id, artifact_id=artifact_id, version=manifest.release_version, release_channel=manifest.release_channel, image_repository=manifest.image_repository, image_digest=manifest.image_digest)
            self.db.add(release)
            self.db.flush()
        release.company_id = company_id
        release.project_id = discovered.formal_project_id
        release.artifact_id = artifact_id
        release.release_channel = manifest.release_channel
        release.image_repository = manifest.image_repository
        release.image_digest = manifest.image_digest
        release.git_branch = manifest.git_branch
        release.git_commit = manifest.git_commit
        release.manifest_version = manifest.manifest_version
        release.manifest = manifest.model_dump(by_alias=True)
        release.release_status = "PUBLISHED"
        release.parse_status = "SUCCESS"
        release.parse_error = ""
        release.published_at = utcnow()
        return release

    def _upsert_discovered_server(self, project: CrawlerDiscoveredProject, server: CrawlerServer, digest: str, now) -> CrawlerDiscoveredProjectServer:
        dps = self.db.scalar(select(CrawlerDiscoveredProjectServer).where(CrawlerDiscoveredProjectServer.discovered_project_id == project.discovered_project_id, CrawlerDiscoveredProjectServer.server_id == server.server_id))
        if not dps:
            dps = CrawlerDiscoveredProjectServer(discovered_project_id=project.discovered_project_id, company_id=project.company_id, server_id=server.server_id)
            self.db.add(dps)
        dps.deployment_status = "DEPLOYED"
        dps.latest_image_digest = digest
        dps.last_deployed_at = now
        return dps

    def _sync_formal_project(self, discovered: CrawlerDiscoveredProject, release: CrawlerProjectRelease, servers: list[CrawlerServer], now) -> None:
        project = self.db.get(CrawlerProject, discovered.formal_project_id)
        if not project:
            return
        project.project_name = discovered.project_name
        project.repository_url = discovered.repository_url
        project.image_repository = discovered.image_repository
        release.project_id = project.project_id
        self._bind_release_channel(project, release)
        existing_count = len(self.project_servers.list_by_project(project.project_id))
        for idx, server in enumerate(servers):
            self._upsert_project_server(project, server.server_id, release, release.image_digest, now, existing_count + idx, project.dispatch_mode)
        self._mark_existing_project_servers_outdated(project, release, now)
        self._sync_task_definitions(project, release)

    def _bind_release_channel(self, project: CrawlerProject, release: CrawlerProjectRelease) -> CrawlerReleaseChannel:
        channel_name = release.release_channel or "stable"
        channel = self.db.scalar(select(CrawlerReleaseChannel).where(CrawlerReleaseChannel.project_id == project.project_id, CrawlerReleaseChannel.channel_name == channel_name))
        if not channel:
            channel = CrawlerReleaseChannel(company_id=project.company_id, project_id=project.project_id, channel_name=channel_name, channel_status="ENABLED")
            self.db.add(channel)
        channel.release_id = release.release_id
        return channel

    def _mark_existing_project_servers_outdated(self, project: CrawlerProject, release: CrawlerProjectRelease, deployed_at) -> None:
        for ps in self.project_servers.list_by_project(project.project_id):
            if ps.latest_release_id == release.release_id and ps.latest_image_digest == release.image_digest:
                continue
            ps.latest_release_id = release.release_id
            ps.latest_image_digest = release.image_digest
            ps.last_deployed_at = deployed_at
            if ps.image_readiness_status == "READY":
                ps.image_readiness_status = "OUTDATED"
                ps.disabled_reason = "项目发布了新镜像，Agent 下次执行时将按 digest 拉取并校验"

    def _upsert_project_server(self, project: CrawlerProject, server_id: int, release: CrawlerProjectRelease | None, digest: str, deployed_at, idx: int, dispatch_mode: str) -> CrawlerProjectServer:
        ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.server_id == server_id))
        if not ps:
            ps = CrawlerProjectServer(company_id=project.company_id, project_id=project.project_id, server_id=server_id, priority=100 + idx, weight=100, max_concurrency=4)
            ps.scheduling_status = "ENABLED"
            ps.server_role = "ACTIVE" if dispatch_mode == "LOAD_BALANCE" else ("PRIMARY" if idx == 0 else "STANDBY")
            self.db.add(ps)
        previous_release_id = ps.latest_release_id
        previous_digest = ps.latest_image_digest
        target_release_id = release.release_id if release else ps.latest_release_id
        ps.deployment_status = "DEPLOYED"
        ps.latest_release_id = target_release_id
        ps.latest_image_digest = digest
        ps.last_deployed_at = deployed_at
        same_image = previous_release_id == target_release_id and previous_digest == digest
        if same_image and ps.image_readiness_status in {"READY", "WARMING", "OUTDATED"}:
            pass
        else:
            ps.image_readiness_status = "OUTDATED"
            ps.disabled_reason = "项目发布了新镜像，Agent 下次执行时将按 digest 拉取并校验"
        return ps


    def _validate_task_contract(self, item: dict) -> tuple[str, list[str]]:
        warnings: list[str] = []
        platform_code = str(item.get("platformCode") or item.get("platform_code") or "").strip().lower()
        if not platform_code:
            warnings.append("缺少 platformCode，平台任务无法在前端按被爬平台归类")
        required_credentials = item.get("requiredCredentials") or item.get("required_credentials") or []
        if required_credentials and not isinstance(required_credentials, list):
            warnings.append("requiredCredentials 必须是列表")
        for idx, cred in enumerate(required_credentials if isinstance(required_credentials, list) else [], start=1):
            if not isinstance(cred, dict):
                warnings.append(f"requiredCredentials[{idx}] 必须是对象")
                continue
            if not str(cred.get("slot") or "").strip():
                warnings.append(f"requiredCredentials[{idx}] 缺少 slot")
            if not str(cred.get("platformCode") or cred.get("platform_code") or platform_code or "").strip():
                warnings.append(f"requiredCredentials[{idx}] 缺少 platformCode")
            modes = cred.get("supportedModes") or cred.get("supported_modes") or []
            if modes and not isinstance(modes, list):
                warnings.append(f"requiredCredentials[{idx}].supportedModes 必须是列表")
        required_configs = item.get("requiredConfigs") or item.get("required_configs") or []
        if required_configs and not isinstance(required_configs, list):
            warnings.append("requiredConfigs 必须是列表")
        for idx, cfg in enumerate(required_configs if isinstance(required_configs, list) else [], start=1):
            if not isinstance(cfg, dict):
                warnings.append(f"requiredConfigs[{idx}] 必须是对象")
                continue
            if not str(cfg.get("slot") or "").strip():
                warnings.append(f"requiredConfigs[{idx}] 缺少 slot")
            if not str(cfg.get("type") or cfg.get("configType") or "").strip():
                warnings.append(f"requiredConfigs[{idx}] 缺少 type/configType")
        output_tables = item.get("outputTables") or item.get("output_tables") or []
        if output_tables and not isinstance(output_tables, list):
            warnings.append("outputTables 必须是列表")
        for idx, table in enumerate(output_tables if isinstance(output_tables, list) else [], start=1):
            if not isinstance(table, dict):
                warnings.append(f"outputTables[{idx}] 必须是对象")
                continue
            if not str(table.get("slot") or "").strip():
                warnings.append(f"outputTables[{idx}] 缺少 slot")
        return ("WARNING" if warnings else "OK"), warnings

    def _sync_task_definitions(self, project: CrawlerProject, release: CrawlerProjectRelease) -> None:
        task_items = (release.manifest or {}).get("taskDefinitions") or []
        seen: set[str] = set()
        for item in task_items:
            key = str(item.get("definitionKey") or "")
            if not key:
                continue
            seen.add(key)
            definition = self.db.scalar(select(CrawlerProjectTaskDefinition).where(CrawlerProjectTaskDefinition.project_id == project.project_id, CrawlerProjectTaskDefinition.definition_key == key))
            if not definition:
                definition = CrawlerProjectTaskDefinition(company_id=project.company_id, project_id=project.project_id, definition_key=key)
                self.db.add(definition)
            old_status = definition.definition_status
            definition.latest_release_id = release.release_id
            definition.task_name = item.get("taskName", key)
            definition.entry_module = item.get("entryModule", "")
            definition.entry_function = item.get("entryFunction", "")
            definition.source_file = item.get("sourceFile", "sch.py")
            definition.source_fingerprint = item.get("sourceFingerprint", "")
            definition.default_params = item.get("defaultParams") or {}
            definition.suggested_cron = item.get("suggestedCron", "")
            definition.execution_mode = item.get("executionMode", "SINGLE")
            definition.idempotency_policy = item.get("idempotencyPolicy", "IDEMPOTENT")
            definition.resource_requirements = item.get("resourceRequirements") or {}
            definition.required_capabilities = item.get("requiredCapabilities") or {}
            definition.platform_code = str(item.get("platformCode") or item.get("platform_code") or "").strip().lower()
            definition.required_configs = item.get("requiredConfigs") or item.get("required_configs") or []
            definition.required_credentials = item.get("requiredCredentials") or item.get("required_credentials") or []
            definition.output_tables = item.get("outputTables") or item.get("output_tables") or []
            definition.contract_version = str(item.get("contractVersion") or item.get("contract_version") or "1")
            definition.contract_status, definition.contract_warnings = self._validate_task_contract(item)
            definition.runtime_mode = item.get("runtimeMode", "SHARED_ENV_ISOLATED")
            definition.task_group = item.get("taskGroup", "default")
            definition.task_max_concurrency = int(item.get("taskMaxConcurrency", 1) or 1)
            definition.group_max_concurrency = int(item.get("groupMaxConcurrency", 4) or 4)
            definition.exclusive_mode = bool(item.get("exclusiveMode", False))
            definition.io_class = item.get("ioClass", "NORMAL")
            definition.shm_size_mb = int(item.get("shmSizeMb", 64) or 64)
            definition.log_limit_mb = int(item.get("logLimitMb", 50) or 50)
            locks = item.get("resourceLocks") or []
            definition.resource_locks = locks if isinstance(locks, list) else []
            definition.secret_refs = item.get("secretRefs") or []
            definition.allow_offline_run = bool(item.get("allowOfflineRun", False))
            definition.offline_policy = item.get("offlinePolicy") or {}
            if old_status in {"REMOVED", "PARSE_ERROR"}:
                definition.definition_status = "AVAILABLE"
        for definition in list(self.db.scalars(select(CrawlerProjectTaskDefinition).where(CrawlerProjectTaskDefinition.project_id == project.project_id)).all()):
            if definition.definition_key not in seen and definition.definition_status != "CREATED":
                definition.definition_status = "REMOVED"
                definition.parse_message = "最新版本 manifest 中未发现该任务定义"

    def _validate_project_pool(self, project: CrawlerProject) -> None:
        items = self.project_servers.list_by_project(project.project_id)
        enabled = [item for item in items if item.deployment_status == "DEPLOYED" and item.scheduling_status in {"ENABLED", "RECOVERING"}]
        if project.dispatch_mode == "PRIMARY_STANDBY":
            primary_count = sum(1 for item in enabled if item.server_role == "PRIMARY")
            if primary_count != 1:
                raise AppError("主备模式必须且只能配置一个主服务器", code=40046)
        if len(enabled) < project.min_available_servers and project.online_status == "ONLINE":
            raise AppError("可调度服务器数量低于项目最低要求", code=40047)

    def _project_summary(self, project: CrawlerProject) -> dict:
        latest = self.db.scalar(select(CrawlerProjectRelease).where(CrawlerProjectRelease.project_id == project.project_id).order_by(CrawlerProjectRelease.published_at.desc()))
        deployed_count = self.db.scalar(select(func.count(CrawlerProjectServer.project_server_id)).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.deployment_status == "DEPLOYED")) or 0
        execution_count = self.db.scalar(select(func.count(CrawlerProjectServer.project_server_id)).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.deployment_status == "DEPLOYED", CrawlerProjectServer.scheduling_status.in_(["ENABLED", "RECOVERING"]))) or 0
        return {**{c.name: getattr(project, c.name) for c in project.__table__.columns}, "latestVersion": latest.version if latest else "", "latestImageDigest": latest.image_digest if latest else "", "deployedServerCount": deployed_count, "executionServerCount": execution_count}

    def _discovered_payload(self, project: CrawlerDiscoveredProject) -> dict:
        deployment_count = self.db.scalar(select(func.count(CrawlerDiscoveredProjectServer.discovered_project_server_id)).where(CrawlerDiscoveredProjectServer.discovered_project_id == project.discovered_project_id)) or 0
        return {**{c.name: getattr(project, c.name) for c in project.__table__.columns}, "deploymentServerCount": deployment_count, "selectable": not project.formal_project_id and project.discovery_status == "READY_TO_IMPORT"}

    def _project_server_payload(self, item: CrawlerProjectServer) -> dict:
        server = self.db.get(CrawlerServer, item.server_id)
        return {**{c.name: getattr(item, c.name) for c in item.__table__.columns}, "serverName": server.server_name if server else "", "serverCode": server.server_code if server else "", "manageStatus": server.manage_status if server else "UNKNOWN", "healthStatus": server.health_status if server else "UNKNOWN", "capacityStatus": server.capacity_status if server else "UNKNOWN"}
