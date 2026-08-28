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
from app.services.build_center_service import BuildCenterService
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
        build_job_payload: dict | None = None

        if not project_id and not target.get("discoveredProjectId"):
            try:
                build_job = BuildCenterService(self.db).start_project_release_build(
                    user=user,
                    company_id=payload.company_id,
                    repository_url=payload.repository_url,
                    ref_name=payload.ref_name,
                )
            except AppError as exc:
                failure = self._build_failure_pipeline(payload, exc)
                raise AppError(exc.message, code=exc.code, http_status=exc.http_status, data=failure) from exc
            return self._build_queued_pipeline(payload, {column.name: getattr(build_job, column.name) for column in build_job.__table__.columns})

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
        if build_job_payload:
            result["buildJob"] = build_job_payload
        result["pipelineStatus"] = "DEPLOYING"
        for step in result["steps"]:
            if step["key"] == "build" and build_job_payload:
                step["status"] = "success"
                step["message"] = f"平台构建完成：{build_job_payload.get('release_version')} / {build_job_payload.get('image_digest')}"
                step["data"] = {**(step.get("data") or {}), "buildJobId": build_job_payload.get("build_job_id")}
            if step["key"] == "deploy":
                step["status"] = "success"
                step["message"] = f"已向 {len(deploy.get('targets') or [])} 个执行节点下发部署指令"
            if step["key"] == "ready":
                step["status"] = "process"
                step["message"] = "等待执行节点拉取镜像并完成运行前自检"
        result["targets"] = deploy.get("targets") or []
        result["message"] = deploy.get("message") or "发布流水线已进入节点自检阶段"
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
            add_step("servers", "选择节点", "error", "请选择至少一个当前公司下的可部署节点", True)
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
            add_step("servers", "选择节点", "error", "所选节点存在不可部署项，必须处理后才能继续", True, {"unavailableServers": unavailable})
            return self._publish_pipeline_payload(payload, steps, blockers)
        add_step("servers", "选择节点", "success", f"已选择 {len(servers)} 个可部署节点", data={"serverIds": selected_ids})

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
            add_step("deploy", "部署节点", "wait", "发布时将向所选节点下发部署指令")
            add_step("ready", "运行前自检", "wait", "等待执行节点拉取镜像并完成自检")
            return self._publish_pipeline_payload(payload, steps, blockers, target={**target, "releaseId": latest.release_id})

        if target.get("discoveredProjectId"):
            if not target.get("selectable") and not target.get("formalProjectId"):
                add_step("release", "确认可发布版本", "error", "已登记版本当前不可接入，请到项目版本页检查项目状态", True, target)
                return self._publish_pipeline_payload(payload, steps, blockers, target=target)
            add_step("build", "构建镜像", "success", "已存在外部构建登记版本，本次无需重新构建", data=target)
            add_step("release", "确认可发布版本", "success", "可接入已登记版本并继续部署", data=target)
            add_step("deploy", "部署节点", "wait", "发布时会先接入项目，再向所选节点下发部署指令")
            add_step("ready", "运行前自检", "wait", "等待执行节点拉取镜像并完成自检")
            return self._publish_pipeline_payload(payload, steps, blockers, target=target)

        build_capability = self._platform_build_capability()
        if not build_capability["enabled"]:
            add_step("build", "构建镜像", "error", build_capability["message"], True, build_capability)
            add_step("release", "确认可发布版本", "wait", "构建镜像通过后才能生成版本")
            add_step("deploy", "部署节点", "wait", "版本生成后才能部署节点")
            add_step("ready", "运行前自检", "wait", "部署指令下发后才会进入自检")
            return self._publish_pipeline_payload(payload, steps, blockers, target=target)
        add_step("build", "构建镜像", "process" if execute else "wait", "平台构建中心已启用；点击发布项目后将拉取源码、执行被动构建契约、构建镜像并登记 Release", data=build_capability)
        add_step("release", "确认可发布版本", "wait", "等待平台构建中心生成不可变版本")
        add_step("deploy", "部署节点", "wait", "版本生成后才能部署节点")
        add_step("ready", "运行前自检", "wait", "部署指令下发后才会进入自检")
        return self._publish_pipeline_payload(payload, steps, blockers, target=target)

    def _build_queued_pipeline(self, payload: ProjectPublishPipelineRequest, build_job: dict) -> dict:
        steps = [
            {"key": "company", "title": "选择公司", "status": "success", "message": "已完成发布前置校验", "blocking": False, "data": {"companyId": payload.company_id}},
            {"key": "servers", "title": "选择节点", "status": "success", "message": f"已选择 {len(payload.server_ids)} 个可部署节点", "blocking": False, "data": {"serverIds": payload.server_ids}},
            {"key": "source", "title": "确认代码仓库", "status": "success", "message": f"仓库地址格式已确认，目标引用：{payload.ref_name or 'main'}", "blocking": False, "data": {"repositoryUrl": payload.repository_url, "refName": payload.ref_name or "main"}},
            {"key": "build", "title": "构建镜像", "status": "process", "message": f"构建任务已启动：#{build_job.get('build_job_id')}，后台正在拉取源码、构建镜像并登记 Release。", "blocking": False, "data": {"buildJob": build_job, "buildJobId": build_job.get("build_job_id"), "async": True}},
            {"key": "release", "title": "确认可发布版本", "status": "wait", "message": "等待后台构建完成并登记不可变 Release", "blocking": False, "data": {}},
            {"key": "deploy", "title": "部署节点", "status": "wait", "message": "Release 登记后将继续向节点下发部署指令", "blocking": False, "data": {}},
            {"key": "ready", "title": "运行前自检", "status": "wait", "message": "部署指令下发后才会进入自检", "blocking": False, "data": {}},
        ]
        return {
            "pipelineStatus": "BUILDING",
            "canContinue": False,
            "steps": steps,
            "blockers": [],
            "target": {"sourceType": "BUILD_JOB", "repositoryUrl": payload.repository_url, "projectCode": self._repo_name(payload.repository_url), "buildJobId": build_job.get("build_job_id")},
            "form": payload.model_dump(by_alias=True),
            "buildJob": build_job,
            "message": "构建任务已在后台启动；页面将轮询构建状态，完成后自动继续发布。",
        }

    def _build_failure_pipeline(self, payload: ProjectPublishPipelineRequest, exc: AppError) -> dict:
        data = exc.data if isinstance(exc.data, dict) else {}
        build_job = data.get("buildJob") or {}
        steps = [
            {"key": "company", "title": "选择公司", "status": "success", "message": "已完成发布前置校验", "blocking": False, "data": {"companyId": payload.company_id}},
            {"key": "servers", "title": "选择节点", "status": "success", "message": f"已选择 {len(payload.server_ids)} 个可部署节点", "blocking": False, "data": {"serverIds": payload.server_ids}},
            {"key": "source", "title": "确认代码仓库", "status": "success", "message": f"仓库地址格式已确认，目标引用：{payload.ref_name or 'main'}", "blocking": False, "data": {"repositoryUrl": payload.repository_url, "refName": payload.ref_name or "main"}},
            {"key": "build", "title": "构建镜像", "status": "error", "message": exc.message, "blocking": True, "data": data},
            {"key": "release", "title": "确认可发布版本", "status": "wait", "message": "构建失败，尚未生成不可变 Release", "blocking": False, "data": {}},
            {"key": "deploy", "title": "部署节点", "status": "wait", "message": "版本生成后才能部署节点", "blocking": False, "data": {}},
            {"key": "ready", "title": "运行前自检", "status": "wait", "message": "部署指令下发后才会进入自检", "blocking": False, "data": {}},
        ]
        return {
            "pipelineStatus": "BLOCKED",
            "canContinue": False,
            "steps": steps,
            "blockers": [{"step": "build", "title": "构建镜像", "message": exc.message, "data": data}],
            "target": {"sourceType": "NONE", "repositoryUrl": payload.repository_url, "projectCode": self._repo_name(payload.repository_url)},
            "form": payload.model_dump(by_alias=True),
            "buildJob": build_job,
            "message": exc.message,
        }

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
            return "节点不存在或不属于当前公司"
        if server.manage_status != "ENABLED":
            return "节点已停用"
        if not server.agent:
            return "节点尚未接入"
        if server.agent.connection_status != "ONLINE" or not server.agent.last_heartbeat_at:
            return "节点尚未上线"
        if server.health_status == "OFFLINE":
            return "节点离线"
        if server.health_status not in {"HEALTHY", "DEGRADED", "UNKNOWN"}:
            return f"健康状态异常：{server.health_status}"
        if server.capacity_status in {"FULL", "DRAINED", "EXHAUSTED"}:
            return f"负载状态不可用：{server.capacity_status}"
        metrics = server.metrics or {}
        if not self._server_reported_address(server, metrics):
            return "节点地址采集中"
        docker_status = str(metrics.get("dockerStatus") or metrics.get("docker_status") or "").upper()
        if docker_status and docker_status not in {"OK", "READY", "UNKNOWN"}:
            return f"容器服务异常：{docker_status}"
        if metrics.get("dockerSockAccessible") is False or metrics.get("dockerSockPerm") is False or metrics.get("docker_sock_perm") is False:
            return "执行权限不可用"
        if metrics.get("projectDataRootWritable") is False or metrics.get("projectDirWritable") is False or metrics.get("project_dir_writable") is False:
            return "工作目录不可写"
        return ""

    def _platform_build_capability(self) -> dict:
        # 平台发布由 crawler_platform 控制。构建中心由平台部署脚本自动启用本地 Docker 执行器、
        # 内置 registry 前缀和构建目录；如果 Docker/Git/registry 仍不可用，继续 fail-closed。
        # 爬虫项目只提供被动构建契约，不能要求业务仓库主动 CI/CD 或保存平台 Token。
        return BuildCenterService(self.db).spider_project_readiness().asdict()


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
        dps_items = list(self.db.scalars(select(CrawlerDiscoveredProjectServer).where(CrawlerDiscoveredProjectServer.discovered_project_id == discovered.discovered_project_id)).all())
        for idx, item in enumerate(dps_items):
            # External discovery proves only that a server relationship was observed.
            # It is not a platform smoke-test result and must not manufacture DEPLOYED/READY facts.
            ps = self._ensure_project_server(project, item.server_id, idx, payload.dispatch_mode)
            ps.disabled_reason = "历史发现节点已接入，等待显式 Release 部署与运行前自检"
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
            raise AppError("请选择至少一个已接入的执行节点，或开启自动选择", code=40051)
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
        if len(servers) < max(1, project.min_available_servers or 1):
            raise AppError(
                "部署目标数量低于项目最小可用节点要求",
                code=40054,
                data={"selectedServerCount": len(servers), "minAvailableServers": project.min_available_servers},
            )
        active_deploying = self.db.scalar(select(func.count(CrawlerProjectServer.project_server_id)).where(
            CrawlerProjectServer.project_id == project.project_id,
            CrawlerProjectServer.server_id.in_([server.server_id for server in servers]),
            CrawlerProjectServer.deployment_status.in_(["DEPLOYING", "ROLLING_BACK", "CLEANING"]),
        )) or 0
        if active_deploying:
            raise AppError("所选节点已有部署/清理动作未完成，请等待状态结束后再重试", code=40053)
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
        existing_by_server = {item.server_id: item for item in self.project_servers.list_by_project(project.project_id)}
        target_rows: list[CrawlerProjectDeploymentTarget] = []
        for idx, server in enumerate(servers):
            existing_ps = existing_by_server.get(server.server_id)
            ps = existing_ps or self._ensure_project_server(project, server.server_id, existing_count + idx, project.dispatch_mode)
            desired_scheduling_status = (
                existing_ps.scheduling_status
                if existing_ps and existing_ps.scheduling_status in {"ENABLED", "RECOVERING", "PAUSED", "DRAINING", "DISABLED"}
                else "ENABLED"
            )
            if not existing_ps:
                ps.deployment_status = "PENDING"
                ps.image_readiness_status = "UNKNOWN"
                ps.scheduling_status = "PAUSED"
                ps.disabled_reason = "已加入执行池，等待首次 Release 部署和运行前自检"
            target = CrawlerProjectDeploymentTarget(
                deployment_id=deployment.deployment_id,
                company_id=project.company_id,
                project_id=project.project_id,
                release_id=release.release_id,
                server_id=server.server_id,
                target_status="PENDING_AGENT",
                image_readiness_status="UNKNOWN",
                last_deployed_at=None,
            )
            self.db.add(target)
            self.db.flush()
            target_rows.append(target)
            strategy_targets.append({
                "targetId": target.target_id,
                "serverId": server.server_id,
                "serverCode": server.server_code,
                "serverName": server.server_name,
                "commandId": "",
                "desiredSchedulingStatus": desired_scheduling_status,
                "status": "PENDING_AGENT",
                "message": "等待 rollout 并发槽位",
            })
        strategy = dict(deployment.strategy or {})
        strategy["maxParallelPulls"] = payload.max_parallel_pulls
        strategy["targets"] = strategy_targets
        strategy["updatedAt"] = utcnow().isoformat()
        deployment.strategy = strategy
        self.db.flush()
        command_service.dispatch_project_deployment_targets(deployment)
        self.db.flush()
        strategy = dict(deployment.strategy or {})
        meta_by_target = {int(item.get("targetId") or 0): item for item in strategy.get("targets", []) if isinstance(item, dict)}
        for target in target_rows:
            server = self.db.get(CrawlerServer, target.server_id)
            ps = existing_by_server.get(target.server_id) or self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.server_id == target.server_id))
            meta = meta_by_target.get(target.target_id, {})
            targets.append({
                "targetId": target.target_id,
                "serverId": target.server_id,
                "serverCode": server.server_code if server else "",
                "serverName": server.server_name if server else "",
                "targetStatus": target.target_status,
                "imageReadinessStatus": target.image_readiness_status,
                "latestImageDigest": ps.latest_image_digest if ps else "",
                "commandId": meta.get("commandId") or "",
            })
        strategy = dict(deployment.strategy or {})
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
                reason = "节点不存在或不属于该公司"
                available = False
            elif not ps:
                # The server pool describes orchestration intent, not an already
                # deployed runtime fact. A node may be selected before the first
                # Release is activated; explicit Release Deployment later proves
                # image readiness and makes the node schedulable.
                reason = "将加入项目执行池；完成 Release 部署和运行前自检后才会参与调度"
                will_create = True
            elif ps.deployment_status != "DEPLOYED":
                reason = "节点已加入执行池，等待 Release 部署和运行前自检"
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
            raise AppError("执行节点配置校验未通过", code=40045, data=analysis)
        existing = {item.server_id: item for item in self.project_servers.list_by_project(project_id)}
        before = [self._project_server_payload(item) for item in existing.values()]
        for idx, item in enumerate(payload.servers):
            ps = existing.get(item.server_id)
            if not ps:
                ps = self._ensure_project_server(project, item.server_id, idx, project.dispatch_mode)
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
            return "节点不存在或不属于该公司"
        if server.manage_status != "ENABLED":
            return "节点已禁用"
        if not server.agent:
            return "节点尚未接入"
        if server.agent.connection_status != "ONLINE" or not server.agent.last_heartbeat_at:
            return "Agent 尚未心跳上线"
        metrics = server.metrics or {}
        if not self._server_reported_address(server, metrics):
            return "节点地址采集中"
        docker_status = str(metrics.get("dockerStatus") or metrics.get("docker_status") or "").upper()
        if docker_status and docker_status not in {"OK", "READY", "UNKNOWN"}:
            return f"Docker 状态异常：{docker_status}"
        if metrics.get("dockerSockPerm") is False or metrics.get("docker_sock_perm") is False:
            return "Agent 无 Docker socket 权限"
        if metrics.get("projectDirWritable") is False or metrics.get("project_dir_writable") is False:
            return "项目运行目录不可写"
        return ""

    @staticmethod
    def _server_reported_address(server: CrawlerServer, metrics: dict) -> str:
        for value in (
            server.server_ip,
            metrics.get("reportedAddress"),
            metrics.get("reported_address"),
            metrics.get("hostIp"),
            metrics.get("host_ip"),
            metrics.get("publicIp"),
            metrics.get("public_ip"),
            metrics.get("observedRemoteAddress"),
            metrics.get("observed_remote_address"),
            metrics.get("hostname"),
        ):
            text = str(value or "").strip()
            if text:
                return text
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
                {"key": "SERVER_PRECHECKED", "status": "SUCCEEDED", "message": "目标节点服务、Docker 与目录权限基础校验已通过", "finishedAt": now},
                {"key": "DISPATCHING_AGENT", "status": "SUCCEEDED", "message": "部署指令已写入目标节点队列", "finishedAt": now},
                {"key": "AGENT_DEPLOY_PREPARE", "status": "PENDING", "message": "等待 Agent 拉取镜像、准备目录并执行运行时自检"},
                {"key": "RELEASE_ACTIVATION", "status": "PENDING", "message": "节点自检完成后才会切换运行版本并同步任务定义"},
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

    def _active_project_release(self, project_id: int, channel_name: str = "stable") -> CrawlerProjectRelease | None:
        channel = self.db.scalar(select(CrawlerReleaseChannel).where(CrawlerReleaseChannel.project_id == project_id, CrawlerReleaseChannel.channel_name == channel_name, CrawlerReleaseChannel.channel_status == "ENABLED"))
        return self.db.get(CrawlerProjectRelease, channel.release_id) if channel and channel.release_id else None

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
        # Registering/building a Release only records an immutable artifact.
        # Runtime channel activation, task-definition sync and ONLINE transition
        # happen only after explicit node deployment + smoke test succeeds.
        project = self.db.get(CrawlerProject, discovered.formal_project_id)
        if not project:
            return
        project.project_name = discovered.project_name
        project.repository_url = discovered.repository_url
        project.image_repository = discovered.image_repository
        release.project_id = project.project_id

    def _ensure_project_server(self, project: CrawlerProject, server_id: int, idx: int, dispatch_mode: str) -> CrawlerProjectServer:
        ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.server_id == server_id))
        if not ps:
            ps = CrawlerProjectServer(
                company_id=project.company_id,
                project_id=project.project_id,
                server_id=server_id,
                priority=100 + idx,
                weight=100,
                max_concurrency=4,
                deployment_status="PENDING",
                scheduling_status="PAUSED",
                image_readiness_status="UNKNOWN",
            )
            ps.server_role = "ACTIVE" if dispatch_mode == "LOAD_BALANCE" else ("PRIMARY" if idx == 0 else "STANDBY")
            self.db.add(ps)
            self.db.flush()
        return ps

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


    def _validate_project_pool(self, project: CrawlerProject) -> None:
        items = self.project_servers.list_by_project(project.project_id)
        enabled = [item for item in items if item.deployment_status == "DEPLOYED" and item.scheduling_status in {"ENABLED", "RECOVERING"}]
        if project.dispatch_mode == "PRIMARY_STANDBY":
            primary_count = sum(1 for item in enabled if item.server_role == "PRIMARY")
            if primary_count != 1:
                raise AppError("主备模式必须且只能配置一个主节点", code=40046)
        if len(enabled) < project.min_available_servers and project.online_status == "ONLINE":
            raise AppError("可接收任务的节点数量低于项目最低要求", code=40047)

    def _project_summary(self, project: CrawlerProject) -> dict:
        latest = self._latest_project_release(project.project_id)
        active = self._active_project_release(project.project_id)
        deployed_count = self.db.scalar(select(func.count(CrawlerProjectServer.project_server_id)).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.deployment_status == "DEPLOYED")) or 0
        execution_count = self.db.scalar(select(func.count(CrawlerProjectServer.project_server_id)).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.deployment_status == "DEPLOYED", CrawlerProjectServer.scheduling_status.in_(["ENABLED", "RECOVERING"]))) or 0
        return {
            **{c.name: getattr(project, c.name) for c in project.__table__.columns},
            "latestVersion": latest.version if latest else "",
            "latestImageDigest": latest.image_digest if latest else "",
            "activeReleaseId": active.release_id if active else None,
            "activeVersion": active.version if active else "",
            "activeImageDigest": active.image_digest if active else "",
            "releaseActivationPending": bool(latest and (not active or latest.release_id != active.release_id)),
            "deployedServerCount": deployed_count,
            "executionServerCount": execution_count,
        }

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
