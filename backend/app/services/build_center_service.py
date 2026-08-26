from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.services.docker_engine_client import DockerEngineClient, DockerEngineError
from app.errors import AppError
from app.db import SessionLocal
from app.models import CrawlerProjectBuildJob, SysUser
from app.schemas import ProjectDiscoveryCreate, ProjectManifest
from app.utils import utcnow


@dataclass(frozen=True, slots=True)
class BuildCenterReadiness:
    enabled: bool
    implemented: bool
    mode: str
    blocked_reason_code: str
    missing_items: tuple[str, ...]
    message: str
    next_actions: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    diagnostics: dict[str, Any] | None = None

    def asdict(self) -> dict:
        return {
            "enabled": self.enabled,
            "implemented": self.implemented,
            "mode": self.mode,
            "supportedReleasePath": "PLATFORM_MANAGED_BUILD_RELEASE_REGISTRATION",
            "blockedReasonCode": self.blocked_reason_code,
            "missingItems": list(self.missing_items),
            "message": self.message,
            "nextActions": list(self.next_actions),
            "limitations": list(self.limitations),
            "buildContractScript": "scripts/platform_build_contract.sh",
            "manifestOutput": ".release/crawler_manifest.json",
            "releaseOwnership": "crawler_platform",
            "buildExecutor": "LOCAL_DOCKER_CLI_OR_ENGINE_API",
            "credentialMode": "HOST_PRECONFIGURED",
            "diagnostics": self.diagnostics or {},
        }


_ASYNC_BUILD_LOCK = threading.Lock()
_ASYNC_BUILD_THREADS: set[int] = set()


def start_project_release_build_thread(build_job_id: int, user_id: int | None) -> None:
    with _ASYNC_BUILD_LOCK:
        if build_job_id in _ASYNC_BUILD_THREADS:
            return
        _ASYNC_BUILD_THREADS.add(build_job_id)

    def _target() -> None:
        try:
            with SessionLocal() as db:
                BuildCenterService(db).complete_project_release_build(build_job_id, user_id)
        finally:
            with _ASYNC_BUILD_LOCK:
                _ASYNC_BUILD_THREADS.discard(build_job_id)

    thread = threading.Thread(target=_target, name=f"project-build-{build_job_id}", daemon=True)
    thread.start()


class BuildCenterService:
    """Platform-driven spider project build center.

    v1.0.98 adds recovery/cancel/retry lifecycle controls for async build jobs. v1.0.97 starts project builds asynchronously from the publish flow. v1.0.96 implements and observes the smallest safe path: the platform creates the build,
    pulls source in an isolated workspace, executes the spider project's passive
    build contract, builds/pushes a Docker image, reads the immutable digest and
    returns a validated manifest for ProjectService to register as a Release.

    Credential boundaries stay explicit. This code does not invent repository or
    registry credential DB schemas; private repository access and registry auth
    must already be configured on the host/container where this executor runs.

    v1.0.95+ supports Docker Engine API fallback. If the API container has
    /var/run/docker.sock mounted but does not contain the docker CLI binary, the
    build center can still build/push/inspect images through the Docker daemon.
    """

    def __init__(self, db: Session):
        self.db = db

    def spider_project_readiness(self) -> BuildCenterReadiness:
        missing: list[str] = []
        diagnostics = self._executor_diagnostics()
        if not settings.crawler_project_build_enabled:
            missing.append("平台构建执行器未启用：CRAWLER_PROJECT_BUILD_ENABLED=1")
        if not self._image_repository_prefix():
            missing.append("镜像仓库命名前缀无法自动确定：请配置 CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX 或 CRAWLER_AGENT_REGISTRY_PUBLIC_HOST/CRAWLER_CONTROL_PUBLIC_BASE_URL")
        if not diagnostics["gitAvailable"]:
            missing.append("Git 命令不可用：git")
        if not diagnostics["dockerExecutorAvailable"]:
            if not diagnostics["dockerCliAvailable"]:
                missing.append("Docker 执行器不可用：未找到 docker 命令，且 /var/run/docker.sock 不可访问")
            else:
                missing.append("Docker daemon 不可访问：请确认 API 容器已挂载 /var/run/docker.sock 且具备访问权限")
        if missing:
            return BuildCenterReadiness(
                enabled=False,
                implemented=False,
                mode="PLATFORM_BUILD_CENTER_REQUIRED",
                blocked_reason_code="PLATFORM_BUILD_CENTER_NOT_READY",
                missing_items=tuple(missing),
                message="平台构建中心未就绪：" + "、".join(missing) + "。未登记 Release 不能发布；平台需先具备拉取源码、执行被动构建契约、构建镜像、登记 Release 的能力。",
                next_actions=(
                    "执行发布脚本会自动启用 CRAWLER_PROJECT_BUILD_ENABLED=1，并补齐内置 registry 镜像仓库前缀。",
                    "如自动推导出的 registry 地址不符合执行节点访问路径，可显式配置 CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX。",
                    "确保构建执行环境可执行 git，并挂载 /var/run/docker.sock；v1.0.95 起 docker CLI 缺失时会自动走 Docker Engine API。",
                    "构建器调用爬虫项目 scripts/platform_build_contract.sh 生成 manifest，再由平台登记 Release。",
                    "项目发布失败时请先查看返回的 buildJob.buildLogs；v1.0.96 起构建失败会直接带回最近构建日志。",
                    "爬虫项目必须提供 scripts/platform_build_contract.sh。",
                ),
                diagnostics=diagnostics,
            )
        return BuildCenterReadiness(
            enabled=True,
            implemented=True,
            mode="PLATFORM_BUILD_CENTER_READY",
            blocked_reason_code="",
            missing_items=(),
            message="平台构建中心已启用：发布时将由平台拉取源码、执行被动构建契约、构建镜像、登记不可变 Release。",
            next_actions=("点击发布项目后，平台将创建 Build Job 并同步完成最小构建发布闭环。",),
            limitations=(
                "v1.0.96 会在平台发布脚本中自动启用本地构建执行器、构建目录、Docker Socket 和内置 registry 前缀。",
                "当 API 容器没有 docker 命令但已挂载 Docker Socket 时，构建中心会自动使用 Docker Engine API 完成 build/push/inspect。",
                "私有仓库凭据和外部 registry 凭据的数据库模型仍属于后续版本；当前优先打通平台内置 registry 的最小闭环。",
                "当前实现为同步本地 Docker 构建执行器；分布式构建队列和异步日志流属于后续版本。",
            ),
            diagnostics=diagnostics,
        )

    def list_jobs(self, company_id: int | None = None, limit: int = 50) -> list[dict]:
        stmt = select(CrawlerProjectBuildJob).order_by(CrawlerProjectBuildJob.created_at.desc()).limit(max(1, min(limit, 200)))
        if company_id:
            stmt = stmt.where(CrawlerProjectBuildJob.company_id == company_id)
        return [self._job_payload(row) for row in self.db.scalars(stmt).all()]

    def get_job(self, build_job_id: int, auto_resume: bool = True) -> dict:
        job = self.db.get(CrawlerProjectBuildJob, build_job_id)
        if not job:
            raise AppError("构建任务不存在", code=40421, http_status=status.HTTP_404_NOT_FOUND)
        if auto_resume:
            self._refresh_job_execution(job, trigger="GET")
        return self._job_payload(job)

    def cancel_project_release_build(self, build_job_id: int, reason: str = "用户取消构建") -> CrawlerProjectBuildJob:
        job = self.db.get(CrawlerProjectBuildJob, build_job_id)
        if not job:
            raise AppError("构建任务不存在", code=40421, http_status=status.HTTP_404_NOT_FOUND)
        if job.build_status in {"SUCCEEDED", "FAILED", "CANCELED"}:
            return job
        job.build_status = "CANCELED"
        job.current_stage = "CANCELED"
        job.finished_at = utcnow()
        job.error_message = reason or "用户取消构建"
        metadata = dict(job.build_metadata or {})
        metadata["cancelReason"] = job.error_message
        metadata["canceledAt"] = utcnow().isoformat()
        job.build_metadata = metadata
        self._append_log(job, "CANCELED", job.error_message)
        self.db.commit()
        return job

    def retry_project_release_build(self, user: SysUser, build_job_id: int) -> CrawlerProjectBuildJob:
        original = self.db.get(CrawlerProjectBuildJob, build_job_id)
        if not original:
            raise AppError("构建任务不存在", code=40421, http_status=status.HTTP_404_NOT_FOUND)
        if original.build_status in {"PENDING", "RUNNING"}:
            start_project_release_build_thread(original.build_job_id, getattr(user, "user_id", None))
            return original
        readiness = self.spider_project_readiness()
        if not readiness.enabled:
            raise AppError("平台构建中心未就绪", code=40092, data=readiness.asdict())
        job = CrawlerProjectBuildJob(
            company_id=original.company_id,
            repository_url=original.repository_url,
            ref_name=original.ref_name,
            build_status="PENDING",
            current_stage="QUEUED",
            build_metadata={
                "createdBy": getattr(user, "user_id", None),
                "retryOfBuildJobId": original.build_job_id,
                "readiness": readiness.asdict(),
                "executionMode": "ASYNC_BACKGROUND_THREAD",
            },
        )
        self._append_log(job, "QUEUED", f"构建任务已重新入队，来源任务 #{original.build_job_id}。")
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        start_project_release_build_thread(job.build_job_id, getattr(user, "user_id", None))
        return job

    def resume_recoverable_builds(self, limit: int = 20) -> list[int]:
        stmt = (
            select(CrawlerProjectBuildJob)
            .where(CrawlerProjectBuildJob.build_status.in_(("PENDING", "RUNNING")))
            .order_by(CrawlerProjectBuildJob.updated_at.asc(), CrawlerProjectBuildJob.build_job_id.asc())
            .limit(max(1, min(limit, 100)))
        )
        resumed: list[int] = []
        for job in self.db.scalars(stmt).all():
            if self._refresh_job_execution(job, trigger="RECOVERY"):
                resumed.append(job.build_job_id)
        return resumed

    def _refresh_job_execution(self, job: CrawlerProjectBuildJob, trigger: str = "GET") -> bool:
        if job.build_status == "PENDING":
            metadata = dict(job.build_metadata or {})
            metadata["lastResumeTrigger"] = trigger
            metadata["lastResumeCheckAt"] = utcnow().isoformat()
            job.build_metadata = metadata
            self._append_log(job, "QUEUED", "检测到待执行构建任务，已确认后台执行器。")
            self.db.commit()
            start_project_release_build_thread(job.build_job_id, None)
            return True
        if job.build_status == "RUNNING" and job.build_job_id not in _ASYNC_BUILD_THREADS:
            updated = job.updated_at or job.started_at or job.created_at
            age_seconds = max(0.0, (utcnow() - updated).total_seconds())
            if age_seconds >= settings.crawler_project_build_stale_seconds:
                metadata = dict(job.build_metadata or {})
                metadata["autoRequeuedAt"] = utcnow().isoformat()
                metadata["autoRequeueTrigger"] = trigger
                metadata["autoRequeueReason"] = f"RUNNING job stale for {int(age_seconds)}s"
                metadata["autoRequeueCount"] = int(metadata.get("autoRequeueCount") or 0) + 1
                job.build_metadata = metadata
                job.build_status = "PENDING"
                self._append_log(job, "REQUEUED", "检测到构建任务执行器可能已中断，已自动重新入队；平台将从源码拉取开始重新构建。")
                self.db.commit()
                start_project_release_build_thread(job.build_job_id, None)
                return True
        return False

    def start_project_release_build(self, user: SysUser, company_id: int, repository_url: str, ref_name: str = "main") -> CrawlerProjectBuildJob:
        readiness = self.spider_project_readiness()
        if not readiness.enabled:
            raise AppError("平台构建中心未就绪", code=40092, data=readiness.asdict())
        repo = (repository_url or "").strip()
        ref = (ref_name or "main").strip()
        existing = self.db.scalar(
            select(CrawlerProjectBuildJob)
            .where(
                CrawlerProjectBuildJob.company_id == company_id,
                CrawlerProjectBuildJob.repository_url == repo,
                CrawlerProjectBuildJob.ref_name == ref,
                CrawlerProjectBuildJob.build_status.in_(("PENDING", "RUNNING")),
            )
            .order_by(CrawlerProjectBuildJob.created_at.desc(), CrawlerProjectBuildJob.build_job_id.desc())
        )
        if existing:
            start_project_release_build_thread(existing.build_job_id, getattr(user, "user_id", None))
            return existing
        job = CrawlerProjectBuildJob(
            company_id=company_id,
            repository_url=repo,
            ref_name=ref,
            build_status="PENDING",
            current_stage="QUEUED",
            build_metadata={"createdBy": getattr(user, "user_id", None), "readiness": readiness.asdict(), "executionMode": "ASYNC_BACKGROUND_THREAD"},
        )
        self._append_log(job, "QUEUED", "构建任务已入队，HTTP 请求将立即返回，后台继续拉取源码和构建镜像。")
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        start_project_release_build_thread(job.build_job_id, getattr(user, "user_id", None))
        return job

    def complete_project_release_build(self, build_job_id: int, user_id: int | None = None) -> CrawlerProjectBuildJob:
        job = self.db.get(CrawlerProjectBuildJob, build_job_id)
        if not job:
            raise AppError("构建任务不存在", code=40421, http_status=status.HTTP_404_NOT_FOUND)
        if job.build_status in {"SUCCEEDED", "FAILED", "CANCELED"}:
            return job
        user = self.db.get(SysUser, int(user_id)) if user_id else None
        try:
            readiness = self.spider_project_readiness()
            if not readiness.enabled:
                raise AppError("平台构建中心未就绪", code=40092, data=readiness.asdict())
            job.build_status = "RUNNING"
            job.current_stage = "CREATED"
            if not job.started_at:
                job.started_at = utcnow()
            metadata = dict(job.build_metadata or {})
            metadata["readinessAtStart"] = readiness.asdict()
            metadata["workerUserId"] = getattr(user, "user_id", user_id)
            job.build_metadata = metadata
            self._append_log(job, "CREATED", "后台构建已启动。")
            self.db.commit()
            manifest = self._run_build(job)
            job.build_status = "SUCCEEDED"
            job.current_stage = "REGISTER_READY"
            job.finished_at = utcnow()
            job.project_code = manifest.project_code
            job.release_version = manifest.release_version
            job.image_repository = manifest.image_repository
            job.image_digest = manifest.image_digest
            self._append_log(job, "REGISTER_READY", f"构建完成，准备登记 Release：{manifest.project_code} {manifest.release_version} {manifest.image_digest}")
            self.db.commit()
            from app.services.project_service import ProjectService
            discovered = ProjectService(self.db).upsert_discovered(ProjectDiscoveryCreate(company_id=job.company_id, manifest=manifest))
            job.discovered_project_id = discovered.discovered_project_id
            job.release_id = discovered.latest_release_id
            job.current_stage = "REGISTERED"
            self._append_log(job, "REGISTERED", f"Release 已登记：discoveredProjectId={discovered.discovered_project_id} releaseId={discovered.latest_release_id}")
            self.db.commit()
            return job
        except AppError as exc:
            try:
                self.db.refresh(job)
            except Exception:
                pass
            if job.build_status == "CANCELED":
                job.finished_at = job.finished_at or utcnow()
                if not job.error_message:
                    job.error_message = "构建任务已取消"
                self._append_log(job, "CANCELED", job.error_message)
                self.db.commit()
                return job
            job.build_status = "FAILED"
            job.finished_at = utcnow()
            job.error_message = exc.message
            self._append_log(job, "FAILED", exc.message)
            self.db.commit()
            return job
        except Exception as exc:  # pragma: no cover - defensive async guard
            job.build_status = "FAILED"
            job.finished_at = utcnow()
            job.error_message = str(exc)
            self._append_log(job, "FAILED", str(exc))
            self.db.commit()
            return job

    def build_project_release(self, user: SysUser, company_id: int, repository_url: str, ref_name: str = "main") -> tuple[ProjectManifest, CrawlerProjectBuildJob]:
        readiness = self.spider_project_readiness()
        if not readiness.enabled:
            raise AppError("平台构建中心未就绪", code=40092, data=readiness.asdict())
        repo = (repository_url or "").strip()
        ref = (ref_name or "main").strip()
        job = CrawlerProjectBuildJob(
            company_id=company_id,
            repository_url=repo,
            ref_name=ref,
            build_status="RUNNING",
            current_stage="CREATED",
            started_at=utcnow(),
            build_metadata={"createdBy": getattr(user, "user_id", None), "readiness": readiness.asdict()},
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        try:
            manifest = self._run_build(job)
            job.build_status = "SUCCEEDED"
            job.current_stage = "REGISTER_READY"
            job.finished_at = utcnow()
            job.project_code = manifest.project_code
            job.release_version = manifest.release_version
            job.image_repository = manifest.image_repository
            job.image_digest = manifest.image_digest
            self._append_log(job, "REGISTER_READY", f"构建完成，等待登记 Release：{manifest.project_code} {manifest.release_version} {manifest.image_digest}")
            self.db.commit()
            return manifest, job
        except AppError as exc:
            job.build_status = "FAILED"
            job.finished_at = utcnow()
            job.error_message = exc.message
            self._append_log(job, "FAILED", exc.message)
            self.db.commit()
            raise self._with_job_context(job, exc) from exc
        except Exception as exc:  # pragma: no cover - defensive guard
            job.build_status = "FAILED"
            job.finished_at = utcnow()
            job.error_message = str(exc)
            self._append_log(job, "FAILED", str(exc))
            self.db.commit()
            raise AppError("平台构建中心执行失败", code=40093, data=self._job_payload(job)) from exc

    def _run_build(self, job: CrawlerProjectBuildJob) -> ProjectManifest:
        root = Path(settings.crawler_project_build_root).expanduser().resolve()
        workspace = root / f"build-{job.build_job_id}"
        source = workspace / "source"
        if workspace.exists():
            shutil.rmtree(workspace)
        source.parent.mkdir(parents=True, exist_ok=True)
        job.workspace_path = str(workspace)
        self._raise_if_canceled(job)
        self._append_log(job, "CLONE", f"拉取源码：{job.repository_url} ref={job.ref_name}")
        self._run(job, ["git", "clone", "--depth", "1", "--branch", job.ref_name, job.repository_url, str(source)], cwd=workspace.parent)
        self._raise_if_canceled(job)
        git_commit = self._capture(job, ["git", "rev-parse", "--short=12", "HEAD"], cwd=source)
        release_version = self._read_release_version(source)
        self._append_log(job, "CONTRACT", "执行爬虫项目被动构建契约 scripts/platform_build_contract.sh")
        env = {
            "RELEASE_VERSION": release_version,
            "REPOSITORY_URL": job.repository_url,
            "GIT_BRANCH": job.ref_name,
            "GIT_COMMIT": git_commit,
            "OUTPUT_MANIFEST": ".release/crawler_manifest.prebuild.json",
        }
        self._run(job, ["bash", "scripts/platform_build_contract.sh"], cwd=source, env=env)
        self._raise_if_canceled(job)
        pre_manifest = self._load_manifest(source / ".release" / "crawler_manifest.prebuild.json")
        project_code = pre_manifest.project_code
        image_repo = self._image_repository_for(project_code)
        push_image_repo = self._push_image_repository_for(project_code, image_repo)
        tag = f"{push_image_repo}:{release_version}"
        self._append_log(job, "DOCKER_BUILD", f"构建镜像：{tag}（Release 对外仓库：{image_repo}）")
        self._docker_build(job, source, tag, release_version, git_commit)
        self._raise_if_canceled(job)
        self._append_log(job, "DOCKER_PUSH", f"推送镜像：{tag}")
        self._docker_push(job, tag, push_image_repo, release_version)
        self._raise_if_canceled(job)
        digest = self._resolve_image_digest(job, tag, push_image_repo)
        job.git_commit = git_commit
        job.release_version = release_version
        job.image_repository = image_repo
        job.image_digest = digest
        self._append_log(job, "MANIFEST", "生成最终 crawler_manifest.json")
        final_env = {
            "RELEASE_VERSION": release_version,
            "REPOSITORY_URL": job.repository_url,
            "GIT_BRANCH": job.ref_name,
            "GIT_COMMIT": git_commit,
            "IMAGE_REPOSITORY": image_repo,
            "IMAGE_DIGEST": digest,
            "OUTPUT_MANIFEST": ".release/crawler_manifest.json",
        }
        self._run(job, ["bash", "scripts/platform_build_contract.sh"], cwd=source, env=final_env)
        self._raise_if_canceled(job)
        manifest_path = source / ".release" / "crawler_manifest.json"
        job.manifest_path = str(manifest_path)
        manifest = self._load_manifest(manifest_path)
        if manifest.image_repository != image_repo or manifest.image_digest != digest:
            raise AppError("构建产物 manifest 与镜像 digest 不一致", code=40094, data={"imageRepository": image_repo, "imageDigest": digest})
        return manifest

    def _raise_if_canceled(self, job: CrawlerProjectBuildJob) -> None:
        try:
            self.db.refresh(job)
        except Exception:
            return
        if job.build_status == "CANCELED":
            raise AppError(job.error_message or "构建任务已取消", code=40105, data={"buildJobId": job.build_job_id})

    def _read_release_version(self, source: Path) -> str:
        value = ""
        for candidate in (source / "VERSION", source / "version.txt"):
            if candidate.exists():
                value = candidate.read_text(encoding="utf-8").strip()
                break
        if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", value):
            raise AppError("爬虫项目缺少稳定 VERSION，平台不能用 main/dev/latest 生成不可变 Release", code=40095, data={"version": value})
        return value

    def _load_manifest(self, path: Path) -> ProjectManifest:
        if not path.exists():
            raise AppError("被动构建契约未生成 crawler_manifest.json", code=40096, data={"manifestPath": str(path)})
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ProjectManifest.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise AppError("构建产物 manifest 不符合平台协议", code=40097, data={"manifestPath": str(path), "error": str(exc)}) from exc

    def _image_repository_prefix(self) -> str:
        configured = settings.crawler_project_image_repository_prefix.strip().rstrip("/")
        if configured:
            return configured
        registry_host = settings.crawler_agent_registry_public_host.strip()
        if not registry_host and settings.control_plane_public_base_url.strip():
            parsed = urlparse(settings.control_plane_public_base_url.strip())
            registry_host = parsed.hostname or ""
        registry_host = registry_host.strip()
        if registry_host:
            return f"{registry_host}:{settings.crawler_agent_registry_port}/crawler_projects"
        if settings.app_env.lower() not in {"production", "prod"}:
            return f"localhost:{settings.crawler_agent_registry_port}/crawler_projects"
        return ""

    def _executor_diagnostics(self) -> dict[str, Any]:
        docker_client = DockerEngineClient(timeout=8)
        docker_socket_path = docker_client.socket_path
        docker_cli_available = shutil.which("docker") is not None
        docker_daemon_via_cli = self._docker_daemon_available() if docker_cli_available else False
        docker_engine_api_available = docker_client.is_available()
        build_root = Path(settings.crawler_project_build_root).expanduser()
        return {
            "buildEnabled": bool(settings.crawler_project_build_enabled),
            "gitAvailable": shutil.which("git") is not None,
            "dockerCliAvailable": docker_cli_available,
            "dockerDaemonViaCli": docker_daemon_via_cli,
            "dockerSocketPath": docker_socket_path,
            "dockerSocketExists": Path(docker_socket_path).exists(),
            "dockerEngineApiAvailable": docker_engine_api_available,
            "dockerExecutorAvailable": bool((docker_cli_available and docker_daemon_via_cli) or docker_engine_api_available),
            "selectedExecutor": "DOCKER_CLI" if docker_cli_available and docker_daemon_via_cli else ("DOCKER_ENGINE_API" if docker_engine_api_available else "NONE"),
            "imageRepositoryPrefix": self._image_repository_prefix(),
            "buildRoot": str(build_root),
            "buildRootParentExists": build_root.parent.exists(),
        }

    def _docker_executor_available(self) -> bool:
        diagnostics = self._executor_diagnostics()
        return bool(diagnostics["dockerExecutorAvailable"])

    def _docker_daemon_available(self) -> bool:
        try:
            proc = subprocess.run(["docker", "info"], text=True, capture_output=True, timeout=8)
            return proc.returncode == 0
        except Exception:
            return False

    def _use_docker_cli(self) -> bool:
        return shutil.which("docker") is not None and self._docker_daemon_available()

    def _image_repository_for(self, project_code: str) -> str:
        prefix = self._image_repository_prefix().rstrip("/")
        if not prefix:
            raise AppError("镜像仓库命名前缀无法自动确定", code=40099)
        code = re.sub(r"[^A-Za-z0-9_.-]+", "_", project_code or "crawler_project").strip("_") or "crawler_project"
        return f"{prefix}/{code}"

    def _push_image_repository_for(self, project_code: str, public_image_repo: str) -> str:
        configured = settings.crawler_project_image_repository_prefix.strip()
        if configured and not self._is_builtin_registry_repository(public_image_repo):
            return public_image_repo
        if not self._is_builtin_registry_repository(public_image_repo):
            return public_image_repo
        code = re.sub(r"[^A-Za-z0-9_.-]+", "_", project_code or "crawler_project").strip("_") or "crawler_project"
        return f"localhost:{settings.crawler_agent_registry_port}/crawler_projects/{code}"

    def _is_builtin_registry_repository(self, image_repo: str) -> bool:
        try:
            parsed = urlparse("dummy://" + image_repo)
        except Exception:
            return False
        return parsed.port == settings.crawler_agent_registry_port and (parsed.path or "").lstrip("/").startswith("crawler_projects/")

    def _docker_build(self, job: CrawlerProjectBuildJob, source: Path, tag: str, release_version: str, git_commit: str) -> None:
        build_args = {
            "CRAWLER_RELEASE_VERSION": release_version,
            "CRAWLER_BUILD_SHA": git_commit,
            "PIP_INDEX_URL": settings.crawler_project_build_pip_index_url,
        }
        if self._use_docker_cli():
            self._run(
                job,
                [
                    "docker", "build",
                    "--build-arg", f"CRAWLER_RELEASE_VERSION={release_version}",
                    "--build-arg", f"CRAWLER_BUILD_SHA={git_commit}",
                    "--build-arg", f"PIP_INDEX_URL={settings.crawler_project_build_pip_index_url}",
                    "-t", tag,
                    ".",
                ],
                cwd=source,
                env={"DOCKER_BUILDKIT": "1"},
            )
            return
        started = time.monotonic()
        try:
            output = DockerEngineClient(timeout=settings.crawler_project_build_timeout_seconds).build(source, tag, build_args=build_args, platform=settings.crawler_project_build_platform)
        except DockerEngineError as exc:
            raise AppError("Docker Engine API 构建失败", code=40102, data={"image": tag, "error": str(exc)[-4000:]}) from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        self._append_log(job, "DOCKER_BUILD_API", output[-4000:] or "Docker Engine API build completed", exit_code=0, duration_ms=duration_ms)
        self.db.commit()

    def _docker_push(self, job: CrawlerProjectBuildJob, tag: str, image_repository: str, release_version: str) -> None:
        if self._use_docker_cli():
            self._run(job, ["docker", "push", tag], cwd=Path(job.workspace_path or "."))
            return
        started = time.monotonic()
        try:
            output = DockerEngineClient(timeout=settings.crawler_project_build_timeout_seconds).push(image_repository, release_version)
        except DockerEngineError as exc:
            raise AppError("Docker Engine API 推送失败", code=40103, data={"image": tag, "error": str(exc)[-4000:]}) from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        self._append_log(job, "DOCKER_PUSH_API", output[-4000:] or "Docker Engine API push completed", exit_code=0, duration_ms=duration_ms)
        self.db.commit()

    def _resolve_image_digest(self, job: CrawlerProjectBuildJob, tag: str, image_repo: str) -> str:
        if self._use_docker_cli():
            output = self._capture(job, ["docker", "image", "inspect", "--format", "{{range .RepoDigests}}{{println .}}{{end}}", tag], cwd=Path(job.workspace_path or "."), allow_empty=True)
        else:
            try:
                payload = DockerEngineClient(timeout=60).inspect_image(tag)
            except DockerEngineError as exc:
                raise AppError("Docker Engine API 读取镜像 digest 失败", code=40104, data={"image": tag, "error": str(exc)[-2000:]}) from exc
            output = "\n".join(str(item) for item in payload.get("RepoDigests") or [])
            self._append_log(job, "DOCKER_INSPECT_API", output or "Docker Engine API inspect returned no RepoDigests", exit_code=0)
        for line in output.splitlines():
            line = line.strip()
            if line.startswith(image_repo + "@sha256:"):
                return "sha256:" + line.split("@sha256:", 1)[1].strip()
            if "@sha256:" in line:
                return "sha256:" + line.split("@sha256:", 1)[1].strip()
        raise AppError("镜像已推送但未能读取不可变 digest，请检查 registry 是否返回 RepoDigest", code=40098, data={"image": tag, "inspectOutput": output})

    def _run(self, job: CrawlerProjectBuildJob, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        started = time.monotonic()
        proc = subprocess.run(cmd, cwd=str(cwd), env=full_env, text=True, capture_output=True, timeout=settings.crawler_project_build_timeout_seconds)
        duration_ms = int((time.monotonic() - started) * 1000)
        output = "\n".join(part for part in [proc.stdout.strip(), proc.stderr.strip()] if part)
        self._append_log(job, job.current_stage or "RUN", f"$ {' '.join(cmd)}\n{output}".strip(), exit_code=proc.returncode, duration_ms=duration_ms)
        self.db.commit()
        if proc.returncode != 0:
            raise AppError("构建命令执行失败", code=40099, data={"command": cmd, "exitCode": proc.returncode, "output": output[-4000:]})

    def _capture(self, job: CrawlerProjectBuildJob, cmd: list[str], cwd: Path, allow_empty: bool = False) -> str:
        proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=60)
        output = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        self._append_log(job, "CAPTURE", f"$ {' '.join(cmd)}\n{output or err}".strip(), exit_code=proc.returncode)
        if proc.returncode != 0:
            raise AppError("构建信息读取失败", code=40100, data={"command": cmd, "exitCode": proc.returncode, "output": (output + err)[-2000:]})
        if not output and not allow_empty:
            raise AppError("构建信息读取为空", code=40101, data={"command": cmd})
        return output

    def _append_log(self, job: CrawlerProjectBuildJob, stage: str, message: str, exit_code: int | None = None, duration_ms: int | None = None) -> None:
        job.current_stage = stage
        logs = list(job.build_logs or [])
        logs.append({
            "at": utcnow().isoformat(),
            "stage": stage,
            "message": message[-4000:],
            "exitCode": exit_code,
            "durationMs": duration_ms,
        })
        job.build_logs = logs[-200:]

    def _with_job_context(self, job: CrawlerProjectBuildJob, exc: AppError) -> AppError:
        original_data = exc.data if isinstance(exc.data, dict) else ({"errorData": exc.data} if exc.data is not None else {})
        payload = {**original_data, "buildJob": self._job_payload(job)}
        return AppError(exc.message, code=exc.code, http_status=exc.http_status, data=payload)

    @staticmethod
    def _job_payload(job: CrawlerProjectBuildJob) -> dict[str, Any]:
        payload = {column.name: getattr(job, column.name) for column in job.__table__.columns}
        status_value = str(payload.get("build_status") or "").upper()
        payload["can_cancel"] = status_value in {"PENDING", "RUNNING"}
        payload["can_retry"] = status_value in {"FAILED", "CANCELED"}
        payload["is_terminal"] = status_value in {"SUCCEEDED", "FAILED", "CANCELED"}
        payload["active_in_current_process"] = job.build_job_id in _ASYNC_BUILD_THREADS
        return payload
