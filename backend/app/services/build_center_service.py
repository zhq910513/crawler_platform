from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import CrawlerProjectBuildJob, SysUser
from app.schemas import ProjectManifest
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
            "buildExecutor": "LOCAL_DOCKER_SUBPROCESS",
            "credentialMode": "HOST_PRECONFIGURED",
        }


class BuildCenterService:
    """Platform-driven spider project build center.

    v1.0.94 implements and auto-wires the smallest safe path: the platform creates the build,
    pulls source in an isolated workspace, executes the spider project's passive
    build contract, builds/pushes a Docker image, reads the immutable digest and
    returns a validated manifest for ProjectService to register as a Release.

    Credential boundaries stay explicit. This code does not invent repository or
    registry credential DB schemas; private repository access and registry auth
    must already be configured on the host/container where this executor runs.
    """

    def __init__(self, db: Session):
        self.db = db

    def spider_project_readiness(self) -> BuildCenterReadiness:
        missing: list[str] = []
        if not settings.crawler_project_build_enabled:
            missing.append("平台构建执行器未启用：CRAWLER_PROJECT_BUILD_ENABLED=1")
        if not self._image_repository_prefix():
            missing.append("镜像仓库命名前缀无法自动确定：请配置 CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX 或 CRAWLER_AGENT_REGISTRY_PUBLIC_HOST/CRAWLER_CONTROL_PUBLIC_BASE_URL")
        for name, binary in {"Git 命令": "git", "Docker 命令": "docker"}.items():
            if shutil.which(binary) is None:
                missing.append(f"{name}不可用：{binary}")
        if shutil.which("docker") is not None and not self._docker_daemon_available():
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
                    "确保构建执行环境可执行 git、docker，且 API 容器已挂载 /var/run/docker.sock。",
                    "构建器调用爬虫项目 scripts/platform_build_contract.sh 生成 manifest，再由平台登记 Release。",
                    "爬虫项目必须提供 scripts/platform_build_contract.sh。",
                ),
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
                "v1.0.94 会在平台发布脚本中自动启用本地构建执行器、构建目录、Docker Socket 和内置 registry 前缀。",
                "私有仓库凭据和外部 registry 凭据的数据库模型仍属于后续版本；当前优先打通平台内置 registry 的最小闭环。",
                "当前实现为同步本地 Docker 构建执行器；分布式构建队列和异步日志流属于后续版本。",
            ),
        )

    def list_jobs(self, company_id: int | None = None, limit: int = 50) -> list[dict]:
        stmt = select(CrawlerProjectBuildJob).order_by(CrawlerProjectBuildJob.created_at.desc()).limit(max(1, min(limit, 200)))
        if company_id:
            stmt = stmt.where(CrawlerProjectBuildJob.company_id == company_id)
        return [self._job_payload(row) for row in self.db.scalars(stmt).all()]

    def get_job(self, build_job_id: int) -> dict:
        job = self.db.get(CrawlerProjectBuildJob, build_job_id)
        if not job:
            raise AppError("构建任务不存在", code=40421, http_status=status.HTTP_404_NOT_FOUND)
        return self._job_payload(job)

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
            raise
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
        self._append_log(job, "CLONE", f"拉取源码：{job.repository_url} ref={job.ref_name}")
        self._run(job, ["git", "clone", "--depth", "1", "--branch", job.ref_name, job.repository_url, str(source)], cwd=workspace.parent)
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
        pre_manifest = self._load_manifest(source / ".release" / "crawler_manifest.prebuild.json")
        project_code = pre_manifest.project_code
        image_repo = self._image_repository_for(project_code)
        push_image_repo = self._push_image_repository_for(project_code, image_repo)
        tag = f"{push_image_repo}:{release_version}"
        self._append_log(job, "DOCKER_BUILD", f"构建镜像：{tag}（Release 对外仓库：{image_repo}）")
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
        self._append_log(job, "DOCKER_PUSH", f"推送镜像：{tag}")
        self._run(job, ["docker", "push", tag], cwd=source)
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
        manifest_path = source / ".release" / "crawler_manifest.json"
        job.manifest_path = str(manifest_path)
        manifest = self._load_manifest(manifest_path)
        if manifest.image_repository != image_repo or manifest.image_digest != digest:
            raise AppError("构建产物 manifest 与镜像 digest 不一致", code=40094, data={"imageRepository": image_repo, "imageDigest": digest})
        return manifest

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

    def _docker_daemon_available(self) -> bool:
        try:
            proc = subprocess.run(["docker", "info"], text=True, capture_output=True, timeout=8)
            return proc.returncode == 0
        except Exception:
            return False

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

    def _resolve_image_digest(self, job: CrawlerProjectBuildJob, tag: str, image_repo: str) -> str:
        output = self._capture(job, ["docker", "image", "inspect", "--format", "{{range .RepoDigests}}{{println .}}{{end}}", tag], cwd=Path(job.workspace_path or "."), allow_empty=True)
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

    @staticmethod
    def _job_payload(job: CrawlerProjectBuildJob) -> dict[str, Any]:
        return {column.name: getattr(job, column.name) for column in job.__table__.columns}
