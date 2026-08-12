from __future__ import annotations

from datetime import timedelta
import re
from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    CrawlerAgent,
    CrawlerCompany,
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
    CrawlerTaskSchedule,
    CrawlerTaskServerTarget,
    SysUser,
)
from app.repositories.platform import DiscoveredProjectRepository, ProjectRepository, ProjectServerRepository, ServerRepository
from app.schemas import ProjectDiscoveryCreate, ProjectImport, ProjectPublishPipelineRequest, ProjectReleaseDeploy, ProjectServerPoolUpdate, ProjectUpdate
from app.services.permissions import is_super_admin, require_company_scope, require_project_role, scoped_company_id
from app.services.audit import write_operation_log
from app.services.container_cleanup_service import ContainerCleanupService
from app.services.agent_command_service import AgentCommandService
from app.utils import sha256_text, utcnow


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.discovered = DiscoveredProjectRepository(db)
        self.projects = ProjectRepository(db)
        self.servers = ServerRepository(db)
        self.project_servers = ProjectServerRepository(db)

    def validate_discovery_token(self, payload: ProjectDiscoveryCreate, authorization: str | None) -> int:
        if not authorization or not authorization.startswith("Discovery "):
            raise AppError("项目接入凭证无效", code=40150, http_status=status.HTTP_401_UNAUTHORIZED)
        token_hash = sha256_text(authorization[10:].strip())
        token = self.db.scalar(select(CrawlerCompanyDiscoveryToken).where(CrawlerCompanyDiscoveryToken.token_hash == token_hash, CrawlerCompanyDiscoveryToken.status == "ENABLED"))
        if not token:
            raise AppError("项目接入凭证无效", code=40151, http_status=status.HTTP_401_UNAUTHORIZED)
        if token.expires_at and token.expires_at < utcnow():
            raise AppError("项目接入凭证已过期", code=40152, http_status=status.HTTP_401_UNAUTHORIZED)

        manifest_company_code = (payload.manifest.company_code or "").strip()
        target_company_id = payload.company_id
        if manifest_company_code:
            company = self.db.scalar(select(CrawlerCompany).where(CrawlerCompany.company_code == manifest_company_code, CrawlerCompany.status == "ENABLED"))
            if not company:
                raise AppError("项目声明的公司编码不存在或已禁用", code=40153, http_status=status.HTTP_401_UNAUTHORIZED, data={"companyCode": manifest_company_code})
            if target_company_id and target_company_id != company.company_id:
                raise AppError("项目声明的公司编码与 companyId 不一致", code=40154, http_status=status.HTTP_401_UNAUTHORIZED, data={"companyCode": manifest_company_code, "companyId": target_company_id})
            target_company_id = company.company_id

        if not target_company_id:
            target_company_id = token.company_id
        if token.company_id != target_company_id:
            raise AppError("项目接入凭证与目标公司不匹配", code=40151, http_status=status.HTTP_401_UNAUTHORIZED)

        payload.company_id = target_company_id
        token.last_used_at = utcnow()
        return target_company_id

    def list_discovered(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        scoped = scoped_company_id(user, company_id)
        rows = self.discovered.list_projects(scoped)
        return [self._discovered_payload(row) for row in rows]

    def upsert_discovered(self, payload: ProjectDiscoveryCreate) -> CrawlerDiscoveredProject:
        company_id = payload.company_id
        if not company_id:
            raise AppError("缺少项目归属公司：请提供 crawler_project.json.companyCode 或 companyId", code=40047)
        servers: list[CrawlerServer] = []
        manifest = payload.manifest
        self._validate_release_version(manifest.release_version)
        if not manifest.task_definitions:
            raise AppError("manifest 中未发现任务定义，sch.py 解析结果不能为空", code=40043)
        project = self.discovered.by_company_key(company_id, manifest.project_key)
        now = utcnow()
        if not project:
            project = CrawlerDiscoveredProject(
                company_id=company_id,
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
        release = self._upsert_release(company_id, project, artifact.artifact_id, manifest)
        project.latest_release_id = release.release_id
        if project.formal_project_id:
            self._sync_formal_project(project, release, servers, now)
        self.db.commit()
        return project

    def list_projects(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        if is_super_admin(user):
            rows = self.projects.list_projects(company_id)
        else:
            scoped = scoped_company_id(user, company_id)
            rows = self.projects.list_projects(scoped)
        return [self._project_summary(row) for row in rows if row.status != "ARCHIVED"]

    def analyze_publish_pipeline(self, user: SysUser, payload: ProjectPublishPipelineRequest) -> dict:
        return self._build_publish_pipeline(user, payload, execute=False)

    def run_publish_pipeline(self, user: SysUser, payload: ProjectPublishPipelineRequest) -> dict:
        analysis = self._build_publish_pipeline(user, payload, execute=False)
        if not analysis["canContinue"]:
            raise AppError("发布流水线前置检查未通过", code=40080, data=analysis)
        target = analysis.get("target") or {}
        project_id = target.get("projectId")
        if not project_id and target.get("discoveredProjectId"):
            project = self.import_project(user, ProjectImport(discovered_project_id=int(target["discoveredProjectId"]), remark="通过项目发布助手接入", dispatch_mode="LOAD_BALANCE"))
            project_id = project.project_id
        if not project_id:
            raise AppError("发布流水线未找到可部署项目版本", code=40081, data=analysis)
        deploy = self.deploy_release_to_servers(
            user,
            int(project_id),
            ProjectReleaseDeploy(server_ids=payload.server_ids, reason="项目发布助手流水线发布"),
        )
        result = self._build_publish_pipeline(user, payload, execute=True)
        result["deployment"] = deploy
        result["pipelineStatus"] = "DEPLOYING"
        for step in result["steps"]:
            if step["key"] == "deploy":
                step["status"] = "success"
                step["message"] = f"已向 {len(deploy.get('targets') or [])} 台服务器下发部署指令"
            if step["key"] == "ready":
                step["status"] = "process"
                step["message"] = "等待服务器拉取镜像并完成运行前自检"
        result["targets"] = deploy.get("targets") or []
        result["message"] = deploy.get("message") or "发布流水线已进入服务器自检阶段"
        return result

    def _build_publish_pipeline(self, user: SysUser, payload: ProjectPublishPipelineRequest, execute: bool = False) -> dict:
        steps: list[dict] = []
        blockers: list[dict] = []

        def add_step(key: str, title: str, status_value: str, message: str, blocking: bool = False, data: dict | None = None) -> None:
            item = {"key": key, "title": title, "status": status_value, "message": message, "blocking": blocking, "data": data or {}}
            steps.append(item)
            if blocking:
                blockers.append({"step": key, "title": title, "message": message, "data": data or {}})

        company = self.db.get(CrawlerCompany, payload.company_id) if payload.company_id else None
        if not company:
            add_step("company", "选择公司", "error", "请选择有效的项目所属公司", True)
            return self._publish_pipeline_payload(payload, steps, blockers)
        try:
            require_company_scope(user, company.company_id)
            if company.status != "ENABLED":
                add_step("company", "选择公司", "error", "公司已停用，不能发布项目", True, {"companyId": company.company_id})
                return self._publish_pipeline_payload(payload, steps, blockers)
            add_step("company", "选择公司", "success", f"已选择：{company.company_name}", data={"companyId": company.company_id, "companyCode": company.company_code})
        except AppError as exc:
            add_step("company", "选择公司", "error", exc.message, True)
            return self._publish_pipeline_payload(payload, steps, blockers)

        selected_ids = sorted(set(int(item) for item in payload.server_ids if item))
        if not selected_ids:
            add_step("servers", "选择服务器", "error", "请选择至少一台当前公司下的可部署服务器", True)
            return self._publish_pipeline_payload(payload, steps, blockers)
        servers: list[CrawlerServer] = []
        unavailable: list[dict] = []
        for server_id in selected_ids:
            server = self.db.get(CrawlerServer, server_id)
            reason = self._server_block_reason_for_company(company.company_id, server)
            if reason:
                unavailable.append({"serverId": server_id, "serverName": server.server_name if server else "", "reason": reason})
            elif server:
                servers.append(server)
        if unavailable:
            add_step("servers", "选择服务器", "error", "所选服务器存在不可部署项，必须处理后才能继续", True, {"unavailableServers": unavailable})
            return self._publish_pipeline_payload(payload, steps, blockers)
        add_step("servers", "选择服务器", "success", f"已选择 {len(servers)} 台可部署服务器", data={"serverIds": selected_ids})

        repo = (payload.repository_url or "").strip()
        ref_name = (payload.ref_name or "main").strip()
        if not self._is_repository_url(repo):
            add_step("source", "确认代码仓库", "error", "Git 仓库地址必须以 https://、http:// 或 git@ 开头", True)
            return self._publish_pipeline_payload(payload, steps, blockers)
        if not ref_name:
            add_step("source", "确认代码仓库", "error", "请填写分支或标签", True)
            return self._publish_pipeline_payload(payload, steps, blockers)
        add_step("source", "确认代码仓库", "success", f"仓库地址格式已确认，目标引用：{ref_name}", data={"repositoryUrl": repo, "refName": ref_name})

        target = self._find_publish_target(company.company_id, repo)
        if target.get("projectId"):
            latest = self._latest_project_release(int(target["projectId"]))
            if not latest:
                add_step("release", "确认可发布版本", "error", "项目尚无可部署版本，请先完成平台构建中心配置或外部构建注册", True, target)
                return self._publish_pipeline_payload(payload, steps, blockers, target=target)
            add_step("build", "构建镜像", "success", "已存在可部署镜像版本，本次无需重新构建", data={"releaseId": latest.release_id, "version": latest.version})
            add_step("release", "确认可发布版本", "success", f"已确认版本 {latest.version}", data={"releaseId": latest.release_id, "imageDigest": latest.image_digest})
            add_step("deploy", "部署服务器", "wait", "发布时将向所选服务器下发部署指令")
            add_step("ready", "运行前自检", "wait", "等待服务器拉取镜像并完成自检")
            return self._publish_pipeline_payload(payload, steps, blockers, target={**target, "releaseId": latest.release_id})

        if target.get("discoveredProjectId"):
            if not target.get("selectable") and not target.get("formalProjectId"):
                add_step("release", "确认可发布版本", "error", "已登记版本当前不可接入，请到项目版本页检查项目状态", True, target)
                return self._publish_pipeline_payload(payload, steps, blockers, target=target)
            add_step("build", "构建镜像", "success", "已存在外部构建登记版本，本次无需重新构建", data=target)
            add_step("release", "确认可发布版本", "success", "可接入已登记版本并继续部署", data=target)
            add_step("deploy", "部署服务器", "wait", "发布时会先接入项目，再向所选服务器下发部署指令")
            add_step("ready", "运行前自检", "wait", "等待服务器拉取镜像并完成自检")
            return self._publish_pipeline_payload(payload, steps, blockers, target=target)

        build_capability = self._platform_build_capability()
        if not build_capability["enabled"]:
            add_step("build", "构建镜像", "error", build_capability["message"], True, build_capability)
            add_step("release", "确认可发布版本", "wait", "构建镜像通过后才能生成版本")
            add_step("deploy", "部署服务器", "wait", "版本生成后才能部署服务器")
            add_step("ready", "运行前自检", "wait", "部署指令下发后才会进入自检")
            return self._publish_pipeline_payload(payload, steps, blockers, target=target)
        add_step("build", "构建镜像", "process" if execute else "wait", "平台构建中心已配置，下一步将拉取代码并构建镜像", data=build_capability)
        add_step("release", "确认可发布版本", "wait", "等待构建产物生成不可变版本")
        add_step("deploy", "部署服务器", "wait", "版本生成后才能部署服务器")
        add_step("ready", "运行前自检", "wait", "部署指令下发后才会进入自检")
        return self._publish_pipeline_payload(payload, steps, blockers, target=target)

    def _publish_pipeline_payload(self, payload: ProjectPublishPipelineRequest, steps: list[dict], blockers: list[dict], target: dict | None = None) -> dict:
        return {
            "pipelineStatus": "BLOCKED" if blockers else "READY_TO_PUBLISH",
            "canContinue": not blockers,
            "steps": steps,
            "blockers": blockers,
            "target": target or {},
            "form": payload.model_dump(by_alias=True),
            "message": "发布流水线前置检查通过" if not blockers else blockers[0]["message"],
        }

    def _find_publish_target(self, company_id: int, repository_url: str) -> dict:
        normalized = self._normalized_repo(repository_url)
        repo_name = self._repo_name(repository_url)
        project = self.db.scalar(
            select(CrawlerProject).where(
                CrawlerProject.company_id == company_id,
                CrawlerProject.status != "ARCHIVED",
                (CrawlerProject.repository_url == repository_url) | (CrawlerProject.project_code == repo_name),
            ).order_by(CrawlerProject.project_id.desc())
        )
        if not project:
            rows = list(self.db.scalars(select(CrawlerProject).where(CrawlerProject.company_id == company_id, CrawlerProject.status != "ARCHIVED")).all())
            project = next((row for row in rows if self._normalized_repo(row.repository_url) == normalized or row.project_code == repo_name), None)
        if project:
            return {"sourceType": "PROJECT", "projectId": project.project_id, "projectCode": project.project_code, "projectName": project.project_name}
        discovered = None
        rows = list(self.db.scalars(select(CrawlerDiscoveredProject).where(CrawlerDiscoveredProject.company_id == company_id).order_by(CrawlerDiscoveredProject.updated_at.desc())).all())
        for row in rows:
            if self._normalized_repo(row.repository_url) == normalized or row.project_code == repo_name or row.project_key == repo_name:
                discovered = row
                break
        if discovered:
            latest_release = self.db.scalar(select(CrawlerProjectRelease).where(CrawlerProjectRelease.discovered_project_id == discovered.discovered_project_id, CrawlerProjectRelease.release_status == "PUBLISHED", CrawlerProjectRelease.parse_status == "SUCCESS").order_by(CrawlerProjectRelease.published_at.desc(), CrawlerProjectRelease.release_id.desc()))
            data = {"sourceType": "DISCOVERED", "discoveredProjectId": discovered.discovered_project_id, "projectCode": discovered.project_code, "projectName": discovered.project_name, "formalProjectId": discovered.formal_project_id, "releaseId": latest_release.release_id if latest_release else None, "discoveryStatus": discovered.discovery_status, "selectable": (not discovered.formal_project_id and discovered.discovery_status == "READY_TO_IMPORT")}
            if discovered.formal_project_id:
                data["projectId"] = discovered.formal_project_id
            return data
        return {"sourceType": "NONE", "repositoryUrl": repository_url, "projectCode": repo_name}

    def _server_block_reason_for_company(self, company_id: int, server: CrawlerServer | None) -> str:
        if not server or server.company_id != company_id:
            return "服务器不存在或不属于当前公司"
        if server.manage_status != "ENABLED":
            return "服务器已停用"
        if not server.agent:
            return "服务器尚未接入"
        if server.agent.connection_status != "ONLINE" or not server.agent.last_heartbeat_at:
            return "服务器尚未上线"
        if server.health_status == "OFFLINE":
            return "服务器离线"
        if server.health_status not in {"HEALTHY", "DEGRADED", "UNKNOWN"}:
            return f"健康状态异常：{server.health_status}"
        if server.capacity_status in {"FULL", "DRAINED", "EXHAUSTED"}:
            return f"容量状态不可用：{server.capacity_status}"
        metrics = server.metrics or {}
        docker_status = str(metrics.get("dockerStatus") or metrics.get("docker_status") or "").upper()
        if docker_status and docker_status not in {"OK", "READY", "UNKNOWN"}:
            return f"容器服务异常：{docker_status}"
        if metrics.get("dockerSockAccessible") is False or metrics.get("dockerSockPerm") is False or metrics.get("docker_sock_perm") is False:
            return "执行权限不可用"
        if metrics.get("projectDataRootWritable") is False or metrics.get("projectDirWritable") is False or metrics.get("project_dir_writable") is False:
            return "工作目录不可写"
        return ""

    def _platform_build_capability(self) -> dict:
        # 1.0.44 继续保持发布助手强流水线与阻断判断。平台构建执行器还未落地，
        # 因此不能因为某些系统配置存在就放行到“构建成功/可部署”。
        missing = ["平台构建执行器", "代码仓库读取凭据", "镜像仓库推送凭据"]
        return {
            "enabled": False,
            "implemented": False,
            "missingItems": missing,
            "message": "平台构建中心未就绪：" + "、".join(missing) + " 尚未完成，发布流水线必须在此卡住。",
        }


    @staticmethod
    def _is_repository_url(value: str) -> bool:
        return bool(re.match(r"^(https?://[^\s]+|git@[^\s:]+:[^\s]+)(\.git)?$", (value or "").strip(), re.I))

    @staticmethod
    def _normalized_repo(value: str) -> str:
        raw = (value or "").strip().replace("\\", "/")
        raw = re.sub(r"\.git$", "", raw, flags=re.I)
        raw = re.sub(r"^git@([^:]+):", r"https://\1/", raw, flags=re.I)
        return raw.lower().rstrip("/")

    @classmethod
    def _repo_name(cls, value: str) -> str:
        normalized = cls._normalized_repo(value)
        name = normalized.split("/")[-1] if normalized else "crawler_project"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "crawler_project"

    def import_project(self, user: SysUser, payload: ProjectImport) -> CrawlerProject:
        discovered = self.discovered.get(payload.discovered_project_id)
        if not discovered:
            raise AppError("待接入项目不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, discovered.company_id)
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

    def delete_project(self, user: SysUser, project_id: int) -> dict:
        project = require_project_role(self.db, user, project_id, "OWNER")
        active_statuses = {"QUEUED", "ROUTED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}
        active_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(CrawlerTaskRun.project_id == project_id, CrawlerTaskRun.run_status.in_(active_statuses))) or 0)
        if active_count:
            raise AppError("项目存在运行中实例，不能删除，请等待结束后再操作", code=40058, http_status=status.HTTP_400_BAD_REQUEST)
        run_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(CrawlerTaskRun.project_id == project_id)) or 0)
        task_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTask).where(CrawlerTask.project_id == project_id)) or 0)
        before = self._project_summary(project)
        cleanup_commands = ContainerCleanupService(self.db).enqueue_project_cleanup(
            company_id=project.company_id,
            project_id=project.project_id,
            project_code=project.project_code,
            server_ids=self._project_cleanup_server_ids(project_id),
            user=user,
            reason="删除项目后清理项目容器",
        )

        if run_count > 0:
            project.status = "ARCHIVED"
            project.online_status = "SUSPENDED"
            for task in self.db.scalars(select(CrawlerTask).where(CrawlerTask.project_id == project_id)).all():
                task.status = "ARCHIVED"
            for schedule in self.db.scalars(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.project_id == project_id)).all():
                schedule.schedule_status = "DISABLED"
                schedule.next_run_at = None
            for ps in self.db.scalars(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project_id)).all():
                ps.scheduling_status = "DISABLED"
                ps.disabled_reason = "项目已删除归档，等待 Agent 清理项目容器"
            after = self._project_summary(project)
            write_operation_log(self.db, user, None, operation_type="ARCHIVE_PROJECT", resource_type="project", resource_id=str(project.project_id), before_data=before, after_data={**after, "taskCount": task_count, "runCount": run_count, "containerCleanupCommands": cleanup_commands})
            self.db.commit()
            return {"project_id": project_id, "deleted": False, "archived": True, "task_count": task_count, "run_count": run_count, "container_cleanup_commands": cleanup_commands}

        discovered_id = project.discovered_project_id
        if discovered_id:
            discovered = self.db.get(CrawlerDiscoveredProject, discovered_id)
            if discovered and discovered.formal_project_id == project.project_id:
                discovered.formal_project_id = None
                discovered.discovery_status = "READY_TO_IMPORT"
        self.db.query(CrawlerTaskServerTarget).filter(CrawlerTaskServerTarget.task_id.in_(select(CrawlerTask.task_id).where(CrawlerTask.project_id == project_id))).delete(synchronize_session=False)
        self.db.query(CrawlerTaskSchedule).filter(CrawlerTaskSchedule.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerProjectServer).filter(CrawlerProjectServer.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerProjectMember).filter(CrawlerProjectMember.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerReleaseChannel).filter(CrawlerReleaseChannel.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerProjectDeploymentTarget).filter(CrawlerProjectDeploymentTarget.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerProjectDeployment).filter(CrawlerProjectDeployment.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerProjectTaskDefinition).filter(CrawlerProjectTaskDefinition.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerProjectRelease).filter(CrawlerProjectRelease.project_id == project_id).delete(synchronize_session=False)
        self.db.query(CrawlerTask).filter(CrawlerTask.project_id == project_id).delete(synchronize_session=False)
        write_operation_log(self.db, user, None, operation_type="DELETE_PROJECT", resource_type="project", resource_id=str(project.project_id), before_data=before, after_data={"deleted": True, "taskCount": task_count, "runCount": 0, "containerCleanupCommands": cleanup_commands})
        self.db.delete(project)
        self.db.commit()
        return {"project_id": project_id, "deleted": True, "archived": False, "task_count": task_count, "run_count": 0, "container_cleanup_commands": cleanup_commands}

    def deploy_release_to_servers(self, user: SysUser, project_id: int, payload: ProjectReleaseDeploy) -> dict:
        project = require_project_role(self.db, user, project_id, "OWNER")
        release = self.db.get(CrawlerProjectRelease, payload.release_id) if payload.release_id else self._latest_project_release(project.project_id)
        if not release or release.project_id != project.project_id or release.release_status != "PUBLISHED":
            raise AppError("项目 release 不存在或不可部署", code=40451, http_status=status.HTTP_404_NOT_FOUND)
        self._validate_release_contract(release)
        target_server_ids = sorted(set(payload.server_ids or []))
        if payload.auto_select and not target_server_ids:
            target_server_ids = [server.server_id for server in self._auto_select_deploy_servers(project)]
        if not target_server_ids:
            raise AppError("请选择至少一台已安装 Agent 的服务器，或开启自动选择", code=40051)
        servers = []
        unavailable = []
        for server_id in target_server_ids:
            server = self.db.get(CrawlerServer, server_id)
            reason = self._server_deploy_block_reason(project, server)
            if reason:
                unavailable.append({"serverId": server_id, "reason": reason})
                continue
            servers.append(server)
        if unavailable:
            raise AppError("部署目标校验未通过", code=40052, data={"unavailableServers": unavailable})
        active_deploying = self.db.scalar(select(func.count(CrawlerProjectServer.project_server_id)).where(
            CrawlerProjectServer.project_id == project.project_id,
            CrawlerProjectServer.server_id.in_([server.server_id for server in servers]),
            CrawlerProjectServer.deployment_status.in_(["DEPLOYING", "ROLLING_BACK", "CLEANING"]),
        )) or 0
        if active_deploying:
            raise AppError("所选服务器已有部署/清理动作未完成，请等待状态结束后再重试", code=40053)
        now = utcnow()
        deployment = CrawlerProjectDeployment(
            company_id=project.company_id,
            project_id=project.project_id,
            release_id=release.release_id,
            deployment_name=payload.reason or f"一键部署 {release.version}",
            strategy=self._initial_deployment_strategy(project, release, payload, servers),
            deployment_status="DISPATCHING_AGENT",
            created_by=user.user_id,
        )
        self.db.add(deployment)
        self.db.flush()
        targets = []
        command_service = AgentCommandService(self.db)
        existing_count = len(self.project_servers.list_by_project(project.project_id))
        strategy_targets: list[dict] = []
        for idx, server in enumerate(servers):
            ps = self._upsert_project_server(project, server.server_id, release, release.image_digest, now, existing_count + idx, project.dispatch_mode)
            desired_scheduling_status = "ENABLED"
            ps.deployment_status = "DEPLOYING"
            ps.image_readiness_status = "DEPLOYING"
            ps.scheduling_status = "PAUSED"
            ps.disabled_reason = "项目首次/版本部署中：等待 Agent 完成镜像拉取、目录准备和运行时自检"
            target = CrawlerProjectDeploymentTarget(
                deployment_id=deployment.deployment_id,
                company_id=project.company_id,
                project_id=project.project_id,
                release_id=release.release_id,
                server_id=server.server_id,
                target_status="PENDING_AGENT",
                image_readiness_status="DEPLOYING",
                last_deployed_at=None,
            )
            self.db.add(target)
            self.db.flush()
            command = command_service.enqueue_project_deploy_prepare(
                server=server,
                project_id=project.project_id,
                project_code=project.project_code,
                release_id=release.release_id,
                release_version=release.version,
                image_repository=release.image_repository,
                image_digest=release.image_digest,
                deployment_id=deployment.deployment_id,
                target_id=target.target_id,
                desired_scheduling_status=desired_scheduling_status,
                reason=payload.reason or "项目一键部署",
            )
            target.target_status = "DISPATCHED"
            strategy_targets.append({
                "targetId": target.target_id,
                "serverId": server.server_id,
                "serverCode": server.server_code,
                "serverName": server.server_name,
                "commandId": command["commandId"],
                "status": "DISPATCHED",
                "message": "已下发 Agent 部署指令，等待心跳执行",
            })
            targets.append({
                "targetId": target.target_id,
                "serverId": server.server_id,
                "serverCode": server.server_code,
                "serverName": server.server_name,
                "targetStatus": target.target_status,
                "imageReadinessStatus": target.image_readiness_status,
                "latestImageDigest": ps.latest_image_digest,
                "commandId": command["commandId"],
            })
        strategy = dict(deployment.strategy or {})
        strategy["targets"] = strategy_targets
        strategy["updatedAt"] = utcnow().isoformat()
        deployment.strategy = strategy
        deployment.deployment_status = "DEPLOYING"
        write_operation_log(self.db, user, None, operation_type="DEPLOY_PROJECT_RELEASE", resource_type="project", resource_id=str(project.project_id), after_data={"projectId": project.project_id, "releaseId": release.release_id, "serverIds": [s.server_id for s in servers], "deploymentId": deployment.deployment_id})
        self.db.commit()
        return {
            "deploymentId": deployment.deployment_id,
            "projectId": project.project_id,
            "releaseId": release.release_id,
            "releaseVersion": release.version,
            "imageRepository": release.image_repository,
            "imageDigest": release.image_digest,
            "deploymentStatus": deployment.deployment_status,
            "steps": strategy.get("steps", []),
            "targets": targets,
            "message": "一键部署单已创建；Agent 心跳会执行镜像拉取、项目目录准备和运行时自检，成功前不会放开任务调度。",
        }

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

    def _validate_release_contract(self, release: CrawlerProjectRelease) -> None:
        manifest = release.manifest or {}
        task_items = manifest.get("taskDefinitions") or []
        if not isinstance(task_items, list) or not task_items:
            raise AppError("项目 release 未包含任务定义，不能部署", code=40054)
        seen: set[str] = set()
        errors: list[str] = []
        for idx, item in enumerate(task_items, start=1):
            if not isinstance(item, dict):
                errors.append(f"taskDefinitions[{idx}] 不是对象")
                continue
            key = str(item.get("definitionKey") or "").strip()
            entry_module = str(item.get("entryModule") or "").strip()
            entry_function = str(item.get("entryFunction") or "").strip()
            if not key:
                errors.append(f"taskDefinitions[{idx}] 缺少 definitionKey")
            elif key in seen:
                errors.append(f"taskDefinitions[{idx}] definitionKey 重复：{key}")
            else:
                seen.add(key)
            if not entry_module:
                errors.append(f"taskDefinitions[{idx}] 缺少 entryModule")
            if not entry_function:
                errors.append(f"taskDefinitions[{idx}] 缺少 entryFunction")
        if errors:
            raise AppError("项目 release 契约校验未通过", code=40055, data={"errors": errors})
        if not str(release.image_repository or "").strip() or not str(release.image_digest or "").strip():
            raise AppError("项目 release 缺少镜像仓库或 digest，不能部署", code=40056)

    def _server_deploy_block_reason(self, project: CrawlerProject, server: CrawlerServer | None) -> str:
        if not server or server.company_id != project.company_id:
            return "服务器不存在或不属于该公司"
        if server.manage_status != "ENABLED":
            return "服务器已禁用"
        if not server.agent:
            return "服务器未接入 Agent"
        if server.agent.connection_status != "ONLINE" or not server.agent.last_heartbeat_at:
            return "Agent 尚未心跳上线"
        metrics = server.metrics or {}
        docker_status = str(metrics.get("dockerStatus") or metrics.get("docker_status") or "").upper()
        if docker_status and docker_status not in {"OK", "READY", "UNKNOWN"}:
            return f"Docker 状态异常：{docker_status}"
        if metrics.get("dockerSockPerm") is False or metrics.get("docker_sock_perm") is False:
            return "Agent 无 Docker socket 权限"
        if metrics.get("projectDirWritable") is False or metrics.get("project_dir_writable") is False:
            return "项目运行目录不可写"
        return ""

    def _auto_select_deploy_servers(self, project: CrawlerProject) -> list[CrawlerServer]:
        selected: list[CrawlerServer] = []
        seen: set[int] = set()
        existing_pool = list(self.db.scalars(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id).order_by(CrawlerProjectServer.priority.asc(), CrawlerProjectServer.project_server_id.asc())).all())
        for item in existing_pool:
            server = self.db.get(CrawlerServer, item.server_id)
            if item.scheduling_status in {"ENABLED", "RECOVERING"} and not self._server_deploy_block_reason(project, server):
                selected.append(server)
                seen.add(server.server_id)
        if len(selected) >= project.min_available_servers:
            return selected[: max(project.min_available_servers, 1)]
        company_servers = list(self.db.scalars(select(CrawlerServer).where(CrawlerServer.company_id == project.company_id, CrawlerServer.manage_status == "ENABLED").order_by(CrawlerServer.server_id.asc())).all())
        for server in company_servers:
            if server.server_id in seen:
                continue
            if self._server_deploy_block_reason(project, server):
                continue
            selected.append(server)
            seen.add(server.server_id)
            if len(selected) >= max(project.min_available_servers, 1):
                break
        return selected

    def _initial_deployment_strategy(self, project: CrawlerProject, release: CrawlerProjectRelease, payload: ProjectReleaseDeploy, servers: list[CrawlerServer]) -> dict:
        now = utcnow().isoformat()
        manifest = release.manifest or {}
        task_items = manifest.get("taskDefinitions") or []
        return {
            "mode": "ONE_CLICK_PROJECT_DEPLOY",
            "autoSelect": bool(payload.auto_select),
            "reason": payload.reason or "项目一键部署",
            "source": {
                "repositoryUrl": project.repository_url,
                "gitBranch": release.git_branch,
                "gitCommit": release.git_commit,
            },
            "release": {
                "releaseId": release.release_id,
                "version": release.version,
                "imageRepository": release.image_repository,
                "imageDigest": release.image_digest,
                "taskCount": len(task_items),
            },
            "selectedServers": [{"serverId": server.server_id, "serverCode": server.server_code, "serverName": server.server_name} for server in servers],
            "steps": [
                {"key": "SOURCE_CONFIRMED", "status": "SUCCEEDED", "message": "已固化 release、git commit 与镜像 digest", "finishedAt": now},
                {"key": "CONTRACT_VALIDATED", "status": "SUCCEEDED", "message": "任务定义与镜像契约已通过平台校验", "finishedAt": now},
                {"key": "SERVER_PRECHECKED", "status": "SUCCEEDED", "message": "目标服务器 Agent、Docker 与目录权限基础校验已通过", "finishedAt": now},
                {"key": "DISPATCHING_AGENT", "status": "SUCCEEDED", "message": "部署指令已写入目标服务器队列", "finishedAt": now},
                {"key": "AGENT_DEPLOY_PREPARE", "status": "PENDING", "message": "等待 Agent 拉取镜像、准备目录并执行运行时自检"},
            ],
            "targets": [],
            "createdAt": now,
        }

    def _upsert_artifact(self, manifest, now):
        artifact = self.db.scalar(select(CrawlerImageArtifact).where(CrawlerImageArtifact.image_repository == manifest.image_repository, CrawlerImageArtifact.image_digest == manifest.image_digest))
        if artifact:
            return artifact
        artifact = CrawlerImageArtifact(image_repository=manifest.image_repository, image_digest=manifest.image_digest, image_tag=manifest.release_version, supported_arch=manifest.supported_arch, git_commit=manifest.git_commit, build_time=now, artifact_metadata={"runtimeType": manifest.runtime_type})
        self.db.add(artifact)
        self.db.flush()
        return artifact

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
            if ps.image_readiness_status in {"READY", "WARMING", "OUTDATED", "UNKNOWN", "FAILED"}:
                ps.image_readiness_status = "OUTDATED"
                ps.disabled_reason = "项目发布了新镜像，执行节点下次执行时将按 digest 拉取并校验"

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

    def _project_cleanup_server_ids(self, project_id: int) -> list[int]:
        values: set[int] = set()
        project_servers = self.db.scalars(select(CrawlerProjectServer.server_id).where(CrawlerProjectServer.project_id == project_id)).all()
        values.update(int(item) for item in project_servers if item)
        task_targets = self.db.scalars(
            select(CrawlerTaskServerTarget.server_id)
            .join(CrawlerTask, CrawlerTask.task_id == CrawlerTaskServerTarget.task_id)
            .where(CrawlerTask.project_id == project_id)
        ).all()
        values.update(int(item) for item in task_targets if item)
        run_servers = self.db.scalars(select(CrawlerTaskRun.server_id).where(CrawlerTaskRun.project_id == project_id, CrawlerTaskRun.server_id.is_not(None))).all()
        values.update(int(item) for item in run_servers if item)
        return sorted(values)

    def _project_server_payload(self, item: CrawlerProjectServer) -> dict:
        server = self.db.get(CrawlerServer, item.server_id)
        return {**{c.name: getattr(item, c.name) for c in item.__table__.columns}, "serverName": server.server_name if server else "", "serverCode": server.server_code if server else "", "manageStatus": server.manage_status if server else "UNKNOWN", "healthStatus": server.health_status if server else "UNKNOWN", "capacityStatus": server.capacity_status if server else "UNKNOWN"}
