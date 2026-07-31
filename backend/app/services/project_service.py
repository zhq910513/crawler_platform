from __future__ import annotations

from datetime import timedelta
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
    CrawlerProjectTaskDefinition,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerTask,
    CrawlerTaskRun,
    SysUser,
)
from app.repositories.platform import DiscoveredProjectRepository, ProjectRepository, ProjectServerRepository, ServerRepository
from app.schemas import ProjectDiscoveryCreate, ProjectImport, ProjectServerPoolUpdate, ProjectUpdate
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
        server = self.servers.by_code(payload.server_code)
        if not server or server.company_id != payload.company_id:
            raise AppError("服务器不存在或不属于该公司", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        manifest = payload.manifest
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
        self._upsert_discovered_server(project, server, manifest.image_digest, now)
        if project.formal_project_id:
            self._sync_formal_project(project, release, server, now)
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

    def analyze_server_pool(self, user: SysUser, project_id: int, payload: ProjectServerPoolUpdate) -> dict:
        project = require_project_role(self.db, user, project_id, "OWNER")
        existing = {item.server_id: item for item in self.project_servers.list_by_project(project_id)}
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
            if not server or server.company_id != project.company_id:
                reason = "服务器不存在或不属于该公司"
                available = False
            elif not ps or ps.deployment_status != "DEPLOYED":
                reason = "该服务器没有该项目的部署记录，不能直接加入执行池"
                available = False
            elif ps.image_readiness_status not in {"READY", "OUTDATED"}:
                reason = "镜像状态未就绪"
                available = False
            if not available:
                unavailable.append({"serverId": item.server_id, "reason": reason})
            details.append({"serverId": item.server_id, "available": available, "reason": reason, "targetSchedulingStatus": item.scheduling_status})
        enabled_count = sum(1 for item in payload.servers if item.scheduling_status in {"ENABLED", "RECOVERING"} and not any(x["serverId"] == item.server_id for x in unavailable))
        return {"projectId": project_id, "canSave": not unavailable and enabled_count >= project.min_available_servers, "enabledServerCount": enabled_count, "minAvailableServers": project.min_available_servers, "currentRunningCount": current_running, "upcomingTaskCountInTenMinutes": upcoming, "unavailableServers": unavailable, "details": details, "p0Risk": enabled_count < project.min_available_servers}

    def update_server_pool(self, user: SysUser, project_id: int, payload: ProjectServerPoolUpdate) -> list[dict]:
        project = require_project_role(self.db, user, project_id, "OWNER")
        analysis = self.analyze_server_pool(user, project_id, payload)
        if not analysis["canSave"]:
            raise AppError("执行服务器池校验未通过", code=40045, data=analysis)
        existing = {item.server_id: item for item in self.project_servers.list_by_project(project_id)}
        before = [self._project_server_payload(item) for item in existing.values()]
        for item in payload.servers:
            ps = existing[item.server_id]
            ps.scheduling_status = item.scheduling_status
            ps.server_role = item.server_role
            ps.priority = item.priority
            ps.weight = item.weight
            ps.max_concurrency = item.max_concurrency
            ps.auto_eject_enabled = item.auto_eject_enabled
            ps.auto_recover_enabled = item.auto_recover_enabled
            ps.disabled_reason = payload.reason if item.scheduling_status in {"PAUSED", "DRAINING", "DISABLED"} else ""
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

    def _upsert_release(self, company_id: int, discovered: CrawlerDiscoveredProject, artifact_id: int, manifest) -> CrawlerProjectRelease:
        stmt = select(CrawlerProjectRelease).where(CrawlerProjectRelease.discovered_project_id == discovered.discovered_project_id, CrawlerProjectRelease.version == manifest.release_version)
        release = self.db.scalar(stmt)
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

    def _sync_formal_project(self, discovered: CrawlerDiscoveredProject, release: CrawlerProjectRelease, server: CrawlerServer, now) -> None:
        project = self.db.get(CrawlerProject, discovered.formal_project_id)
        if not project:
            return
        project.project_name = discovered.project_name
        project.repository_url = discovered.repository_url
        project.image_repository = discovered.image_repository
        release.project_id = project.project_id
        self._bind_release_channel(project, release)
        index = len(self.project_servers.list_by_project(project.project_id))
        self._upsert_project_server(project, server.server_id, release, release.image_digest, now, index, project.dispatch_mode)
        self._sync_task_definitions(project, release)

    def _bind_release_channel(self, project: CrawlerProject, release: CrawlerProjectRelease) -> CrawlerReleaseChannel:
        channel_name = release.release_channel or "stable"
        channel = self.db.scalar(select(CrawlerReleaseChannel).where(CrawlerReleaseChannel.project_id == project.project_id, CrawlerReleaseChannel.channel_name == channel_name))
        if not channel:
            channel = CrawlerReleaseChannel(company_id=project.company_id, project_id=project.project_id, channel_name=channel_name, channel_status="ENABLED")
            self.db.add(channel)
        channel.release_id = release.release_id
        return channel

    def _upsert_project_server(self, project: CrawlerProject, server_id: int, release: CrawlerProjectRelease | None, digest: str, deployed_at, idx: int, dispatch_mode: str) -> CrawlerProjectServer:
        ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.server_id == server_id))
        if not ps:
            ps = CrawlerProjectServer(company_id=project.company_id, project_id=project.project_id, server_id=server_id, priority=100 + idx, weight=100, max_concurrency=4)
            ps.scheduling_status = "ENABLED"
            ps.server_role = "ACTIVE" if dispatch_mode == "LOAD_BALANCE" else ("PRIMARY" if idx == 0 else "STANDBY")
            self.db.add(ps)
        ps.deployment_status = "DEPLOYED"
        ps.image_readiness_status = "READY" if release and digest == release.image_digest else "OUTDATED"
        ps.latest_release_id = release.release_id if release else ps.latest_release_id
        ps.latest_image_digest = digest
        ps.last_deployed_at = deployed_at
        return ps

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
