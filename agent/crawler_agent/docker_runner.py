from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import docker
from docker.errors import ImageNotFound
from docker.types import LogConfig

from crawler_agent.api import LeaseLostError, PlatformAPI
from crawler_agent.config import AgentConfig

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
logger = logging.getLogger("crawler_agent.runner")


def _safe(value: Any, default: str = "unknown") -> str:
    text = str(value or default).strip() or default
    return _SAFE_NAME.sub("_", text)[:120]


class RunExecutor:
    """Execute a platform run in an isolated task container.

    The platform's default runtime model is "project environment image + isolated task container":
    all tasks of a project share the same immutable image digest and optional project cache volume,
    while every run still gets an independent container, work directory, log directory and profile
    directory. This keeps environment reuse without letting a blocked task poison the whole project.
    """

    def __init__(self, config: AgentConfig, api: PlatformAPI) -> None:
        self.config = config
        self.api = api
        self.client = docker.from_env()

    def _pull_digest(self, image_repository: str, image_digest: str) -> str:
        if not image_repository:
            raise RuntimeError("任务未提供镜像仓库")
        image_ref = f"{image_repository}@{image_digest}" if image_digest else image_repository
        auth_config = None
        if self.config.registry_username and self.config.registry_password:
            auth_config = {"username": self.config.registry_username, "password": self.config.registry_password}
        if image_digest:
            self.client.images.pull(image_ref, auth_config=auth_config)
            image = self.client.images.get(image_ref)
            repo_digests = set(image.attrs.get("RepoDigests") or [])
            if image_ref not in repo_digests:
                raise RuntimeError(f"镜像 digest 校验失败：期望 {image_ref}，实际 {sorted(repo_digests)}")
        else:
            try:
                self.client.images.get(image_ref)
            except ImageNotFound:
                self.client.images.pull(image_ref, auth_config=auth_config)
        return image_ref

    def _prepare_project_dirs(self, claim: dict[str, Any]) -> dict[str, Path]:
        project_code = _safe(claim.get("projectCode"), f"project_{claim.get('projectId')}")
        task_code = _safe(claim.get("taskCode"), f"task_{claim.get('taskId')}")
        run_id = _safe(claim.get("runId"), "run")
        root = self.config.project_data_root / project_code
        dirs = {
            "projectRoot": root,
            "cache": root / "cache",
            "work": root / "work" / run_id,
            "logs": root / "logs" / run_id,
            "profiles": root / "profiles" / task_code / run_id,
            "tmp": root / "tmp" / run_id,
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        return dirs

    def _volumes(self, dirs: dict[str, Path]) -> dict[str, dict[str, str]]:
        volumes = {
            str(dirs["work"]): {"bind": "/work", "mode": "rw"},
            str(dirs["logs"]): {"bind": "/logs", "mode": "rw"},
            str(dirs["profiles"]): {"bind": "/profiles", "mode": "rw"},
            str(dirs["tmp"]): {"bind": "/tmp/crawler-run", "mode": "rw"},
        }
        if self.config.enable_shared_project_cache:
            volumes[str(dirs["cache"])] = {"bind": "/cache", "mode": "rw"}
        return volumes

    def execute(self, claim: dict[str, Any]) -> None:
        run_id = int(claim["runId"])
        lease_token = str(claim["leaseToken"])
        timeout_seconds = int(claim.get("timeoutSeconds") or self.config.default_timeout_seconds)
        container = None
        stop_event = threading.Event()

        def keepalive() -> None:
            while not stop_event.wait(15):
                try:
                    response = self.api.run_heartbeat(run_id, lease_token)
                    if response.get("cancelRequested"):
                        if container:
                            container.stop(timeout=10)
                        return
                except LeaseLostError:
                    if container:
                        try:
                            container.stop(timeout=10)
                        except Exception:
                            pass
                    return
                except Exception as exc:
                    logger.warning("run_id=%s heartbeat failed: %s", run_id, exc, exc_info=True)
                    continue

        thread = threading.Thread(target=keepalive, daemon=True)
        dirs: dict[str, Path] = {}
        try:
            logger.info("run_id=%s pull start imageRepository=%s imageDigest=%s", run_id, claim.get("imageRepository"), claim.get("imageDigest"))
            image_ref = self._pull_digest(str(claim.get("imageRepository") or ""), str(claim.get("imageDigest") or ""))
            logger.info("run_id=%s pull ok image_ref=%s", run_id, image_ref)
            self.api.run_heartbeat(run_id, lease_token, "镜像校验完成，准备启动共享环境隔离任务容器")
            entry_module = str(claim.get("entryModule") or "")
            entry_function = str(claim.get("entryFunction") or "run")
            if not entry_module:
                raise RuntimeError("任务未提供入口模块")
            parameters = claim.get("parameters") or {}
            dirs = self._prepare_project_dirs(claim)
            command = ["python", "-m", "crawler_runtime", "--entrypoint", f"{entry_module}:{entry_function}", "--kwargs-json", json.dumps(parameters, ensure_ascii=False)]
            environment = {
                "CRAWLER_RUN_ID": str(run_id),
                "CRAWLER_PROJECT_ID": str(claim.get("projectId") or ""),
                "CRAWLER_PROJECT_CODE": str(claim.get("projectCode") or ""),
                "CRAWLER_TASK_ID": str(claim.get("taskId") or ""),
                "CRAWLER_TASK_CODE": str(claim.get("taskCode") or ""),
                "CRAWLER_TASK_GROUP": str(claim.get("taskGroup") or "default"),
                "CRAWLER_RUNTIME_MODE": str(claim.get("runtimeMode") or "SHARED_ENV_ISOLATED"),
                "CRAWLER_IO_CLASS": str(claim.get("ioClass") or "NORMAL"),
                "CRAWLER_RESOURCE_LOCKS_JSON": json.dumps(claim.get("resourceLocks") or [], ensure_ascii=False),
                "CRAWLER_TASK_PARAMS_JSON": json.dumps(parameters, ensure_ascii=False),
                "CRAWLER_ENTRY_MODULE": entry_module,
                "CRAWLER_ENTRY_FUNCTION": entry_function,
                "CRAWLER_WORK_DIR": "/work",
                "CRAWLER_LOG_DIR": "/logs",
                "CRAWLER_CACHE_DIR": "/cache",
                "CRAWLER_PROFILE_DIR": "/profiles",
            }
            if claim.get("shardIndex") is not None:
                environment["CRAWLER_SHARD_INDEX"] = str(claim.get("shardIndex"))
                environment["CRAWLER_SHARD_COUNT"] = str(claim.get("shardCount") or "")
            mem_limit = f"{int(claim.get('memoryLimitMb') or 1024)}m"
            nano_cpus = int(float(claim.get("cpuLimit") or 1.0) * 1_000_000_000)
            shm_size_mb = int(claim.get("shmSizeMb") or self.config.default_shm_size_mb)
            log_limit_mb = int(claim.get("logLimitMb") or 50)
            log_config = LogConfig(type=LogConfig.types.JSON, config={"max-size": f"{max(1, log_limit_mb)}m", "max-file": str(self.config.log_max_file)})
            container_name = f"crawler_{_safe(claim.get('projectCode'))}_{_safe(claim.get('taskCode'))}_{run_id}"
            labels = {
                "crawler.platform.run_id": str(run_id),
                "crawler.platform.company_id": str(claim.get("companyId") or ""),
                "crawler.platform.project_id": str(claim.get("projectId") or ""),
                "crawler.platform.project_code": str(claim.get("projectCode") or ""),
                "crawler.platform.task_id": str(claim.get("taskId") or ""),
                "crawler.platform.task_code": str(claim.get("taskCode") or ""),
                "crawler.platform.runtime_mode": str(claim.get("runtimeMode") or "SHARED_ENV_ISOLATED"),
                "crawler.platform.image_digest": str(claim.get('imageDigest') or ""),
            }
            run_kwargs: dict[str, Any] = {
                "image": image_ref,
                "command": command,
                "detach": True,
                "environment": environment,
                "labels": labels,
                "name": container_name,
                "mem_limit": mem_limit,
                "memswap_limit": mem_limit,
                "nano_cpus": nano_cpus,
                "volumes": self._volumes(dirs),
                "shm_size": f"{shm_size_mb}m",
                "pids_limit": self.config.pids_limit,
                "log_config": log_config,
                "init": True,
                "security_opt": ["no-new-privileges:true"],
                "read_only": self.config.read_only_rootfs,
            }
            if self.config.docker_network:
                run_kwargs["network"] = self.config.docker_network
            if self.config.container_user:
                run_kwargs["user"] = self.config.container_user
            logger.info("run_id=%s container create start name=%s", run_id, container_name)
            container = self.client.containers.run(**run_kwargs)
            logger.info("run_id=%s container created id=%s", run_id, container.id[:12])
            self.api.run_heartbeat(run_id, lease_token, "任务容器已创建并启动")
            thread.start()
            started = time.monotonic()
            while True:
                container.reload()
                if container.status in {"exited", "dead"}:
                    break
                if time.monotonic() - started > timeout_seconds:
                    try:
                        container.stop(timeout=10)
                    except Exception:
                        pass
                    logs = container.logs(tail=200).decode("utf-8", errors="replace")
                    self.api.finish(run_id, lease_token, "TIMED_OUT", {"tailLogs": logs, "workDir": str(dirs.get("work", "")), "logDir": str(dirs.get("logs", ""))}, "任务运行超时")
                    return
                time.sleep(2)
            result = container.wait()
            exit_code = int((result or {}).get("StatusCode", 1))
            logger.info("run_id=%s container exited status_code=%s", run_id, exit_code)
            logs = container.logs(tail=200).decode("utf-8", errors="replace")
            status = "SUCCEEDED" if exit_code == 0 else "FAILED"
            self.api.finish(run_id, lease_token, status, {"exitCode": exit_code, "tailLogs": logs, "workDir": str(dirs.get("work", "")), "logDir": str(dirs.get("logs", ""))}, "" if exit_code == 0 else logs[-4000:])
        except Exception as exc:
            logger.exception("run_id=%s execute failed: %s", run_id, exc)
            try:
                self.api.finish(run_id, lease_token, "FAILED", {"workDir": str(dirs.get("work", "")), "logDir": str(dirs.get("logs", ""))}, str(exc))
            except Exception:
                logger.exception("run_id=%s finish callback failed after execute exception", run_id)
        finally:
            stop_event.set()
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            # 保留 logs/cache/profiles，清理 run 临时目录。work 目录默认保留便于排错。
            tmp = dirs.get("tmp") if dirs else None
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
