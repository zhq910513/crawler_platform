from __future__ import annotations

import json
import logging
import os
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

    def _report_image_pull(self, payload: dict[str, Any], status: str, message: str = "") -> None:
        project_id = int(payload.get("projectId") or 0)
        image_digest = str(payload.get("imageDigest") or "")
        if not project_id or not image_digest:
            return
        try:
            release_id = payload.get("releaseId")
            self.api.image_pull_result(
                project_id=project_id,
                release_id=int(release_id) if release_id not in (None, "") else None,
                image_repository=str(payload.get("imageRepository") or ""),
                image_digest=image_digest,
                pull_status=status,
                message=message[:4000],
            )
        except Exception as exc:
            logger.warning("report image pull result failed project_id=%s digest=%s status=%s error=%s", project_id, image_digest, status, exc, exc_info=True)


    def running_platform_run_ids(self) -> set[int]:
        """Return run ids of platform task containers still running on this Docker host.

        This lets a restarted Agent advertise containers it did not create in the
        current process, preventing the platform from prematurely marking those
        runs LOST while the old task container is still alive.
        """
        run_ids: set[int] = set()
        try:
            containers = self.client.containers.list(filters={"label": "crawler.platform.run_id"})
        except Exception as exc:
            logger.warning("scan platform containers failed: %s", exc, exc_info=True)
            return run_ids
        for container in containers:
            try:
                labels = container.labels or {}
                run_id = labels.get("crawler.platform.run_id")
                if run_id is not None:
                    run_ids.add(int(run_id))
            except (TypeError, ValueError):
                continue
        return run_ids

    def prepare_project_runtime(self, command: dict[str, Any]) -> dict[str, Any]:
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        project_id = str(payload.get("projectId") or command.get("projectId") or "")
        project_code = _safe(payload.get("projectCode") or command.get("projectCode") or project_id or "project")
        release_id = str(payload.get("releaseId") or command.get("releaseId") or "")
        image_repository = str(payload.get("imageRepository") or "")
        image_digest = str(payload.get("imageDigest") or "")
        image_ref = self._pull_digest(image_repository, image_digest)
        root = self.config.project_data_root / project_code
        dirs = {
            "projectRoot": root,
            "cache": root / "cache",
            "work": root / "work",
            "logs": root / "logs",
            "profiles": root / "profiles",
            "tmp": root / "tmp",
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        smoke = self._runtime_smoke_test(command, image_ref) if payload.get("smokeTest", True) else {"skipped": True}
        return {
            "imageRef": image_ref,
            "projectRoot": str(root),
            "releaseId": release_id,
            "projectId": project_id,
            "smokeTest": smoke,
        }

    def _runtime_smoke_test(self, command: dict[str, Any], image_ref: str) -> dict[str, Any]:
        command_id = str(command.get("commandId") or "")
        labels = {
            "crawler.platform.command_id": command_id,
            "crawler.platform.command_type": str(command.get("commandType") or "PROJECT_DEPLOY_PREPARE"),
            "crawler.platform.project_id": str(command.get("projectId") or ""),
            "crawler.platform.release_id": str(command.get("releaseId") or ""),
        }
        container = None
        started = time.monotonic()
        try:
            kwargs: dict[str, Any] = {
                "image": image_ref,
                "command": ["python", "-c", "import crawler_runtime; print('crawler_runtime import ok')"],
                "detach": True,
                "labels": labels,
                "name": f"crawler_deploy_check_{_safe(command_id, 'command')}",
                "init": True,
                "mem_limit": "512m",
                "memswap_limit": "512m",
                "nano_cpus": 500_000_000,
                "security_opt": ["no-new-privileges:true"],
            }
            if self.config.docker_network:
                kwargs["network"] = self.config.docker_network
            if self.config.container_user:
                kwargs["user"] = self.config.container_user
            container = self.client.containers.run(**kwargs)
            while time.monotonic() - started <= 60:
                container.reload()
                if container.status in {"exited", "dead"}:
                    break
                time.sleep(1)
            else:
                try:
                    container.stop(timeout=5)
                except Exception:
                    pass
                raise RuntimeError("运行时自检超时：60 秒内未退出")
            result = container.wait() or {}
            exit_code = int(result.get("StatusCode", 1))
            logs = self._container_logs_text(container, tail=100)
            if exit_code != 0:
                raise RuntimeError(f"运行时自检失败 exitCode={exit_code} logs={logs[-1000:]}")
            return {"exitCode": exit_code, "logsTail": logs[-1000:]}
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    logger.warning("deploy smoke test container remove failed command_id=%s", command_id, exc_info=True)

    def prewarm_image(self, image_task: dict[str, Any]) -> bool:
        image_repository = str(image_task.get("imageRepository") or "")
        image_digest = str(image_task.get("imageDigest") or "")
        project_code = str(image_task.get("projectCode") or image_task.get("projectId") or "unknown")
        logger.info("prewarm image start project=%s imageRepository=%s imageDigest=%s", project_code, image_repository, image_digest)
        try:
            image_ref = self._pull_digest(image_repository, image_digest)
            self._report_image_pull(image_task, "READY", f"预热完成：{image_ref}")
            logger.info("prewarm image ok project=%s image_ref=%s", project_code, image_ref)
            return True
        except Exception as exc:
            message = f"预热失败：{exc}"
            self._report_image_pull(image_task, "FAILED", message)
            logger.warning("prewarm image failed project=%s error=%s", project_code, exc, exc_info=True)
            return False



    def prepare_agent_upgrade(self, upgrade: dict[str, Any]) -> dict[str, Any]:
        running_ids = sorted(self.running_platform_run_ids())
        if running_ids:
            raise RuntimeError(f"仍有平台任务容器运行，拒绝升级 Agent：{running_ids}")
        payload = upgrade.get("payload") if isinstance(upgrade.get("payload"), dict) else upgrade
        target_image = str((payload or {}).get("agentImage") or (payload or {}).get("targetImage") or "").strip()
        target_version = str((payload or {}).get("targetVersion") or "").strip()
        target_digest = str((payload or {}).get("expectedImageDigest") or (payload or {}).get("targetDigest") or "").strip()
        if not target_image:
            raise RuntimeError("Agent 升级缺少目标镜像")
        current_ref = str(os.getenv("HOSTNAME") or "").strip()
        if not current_ref:
            raise RuntimeError("无法识别当前 Agent 容器，拒绝自动升级")
        current = self.client.containers.get(current_ref)
        old_name = getattr(current, "name", "") or f"crawler-agent-old-{current.id[:12]}"
        backup_name = f"{old_name}-old-{int(time.time())}"
        env: dict[str, str] = {}
        for item in (current.attrs.get("Config", {}) or {}).get("Env", []) or []:
            if isinstance(item, str) and "=" in item:
                key, value = item.split("=", 1)
                env[key] = value
        if target_version:
            env["AGENT_AGENT_VERSION"] = target_version
        env["AGENT_IMAGE"] = target_image
        env["AGENT_EXPECTED_IMAGE_DIGEST"] = target_digest
        env["AGENT_INSTANCE_ID"] = f"upgrade-{int(time.time())}-{os.urandom(3).hex()}"
        host_config = current.attrs.get("HostConfig", {}) or {}
        binds = list(host_config.get("Binds") or [])
        network_mode = str(host_config.get("NetworkMode") or "host")
        restart_policy = {"Name": "always"}
        logger.info("agent upgrade pull image=%s target_version=%s digest=%s", target_image, target_version, target_digest)
        self.client.images.pull(target_image)
        try:
            current.update(restart_policy={"Name": "no"})
            current.rename(backup_name)
        except Exception as exc:
            raise RuntimeError(f"保留旧 Agent 容器失败：{exc}") from exc
        new_container = None
        try:
            new_container = self.client.containers.run(
                target_image,
                detach=True,
                name=old_name,
                restart_policy=restart_policy,
                network_mode=network_mode,
                environment=env,
                volumes=binds,
            )
            time.sleep(3)
            new_container.reload()
            if new_container.status != "running":
                logs = self._container_logs_text(new_container, tail=80)[-1000:]
                raise RuntimeError(f"新 Agent 容器启动后未保持运行 status={new_container.status} logs={logs}")
            return {
                "oldContainerId": current.id,
                "oldContainerName": backup_name,
                "newContainerId": new_container.id,
                "newContainerName": old_name,
                "targetImage": target_image,
                "targetVersion": target_version,
                "expectedImageDigest": target_digest,
                "rollbackAvailable": True,
            }
        except Exception as exc:
            try:
                if new_container is not None:
                    new_container.remove(force=True)
            except Exception:
                logger.warning("remove failed upgraded agent container failed", exc_info=True)
            try:
                current.reload()
                if getattr(current, "status", "") == "running":
                    current.stop(timeout=10)
                current.rename(old_name)
                current.update(restart_policy={"Name": "always"})
                current.start()
            except Exception:
                logger.warning("restore old agent container failed backup_name=%s", backup_name, exc_info=True)
            raise RuntimeError(f"Agent 升级启动失败，已尝试恢复旧容器：{exc}") from exc


    def cleanup_stopped_agent_backups(self) -> int:
        removed = 0
        try:
            containers = self.client.containers.list(all=True, filters={"name": "crawler-agent-old"})
        except Exception as exc:
            logger.warning("scan old agent backup containers failed: %s", exc, exc_info=True)
            return 0
        for container in containers:
            try:
                name = getattr(container, "name", "") or ""
                if not name.startswith("crawler-agent-old-"):
                    continue
                container.reload()
                if getattr(container, "status", "") == "running":
                    continue
                container.remove(force=True, v=False)
                removed += 1
            except Exception:
                logger.warning("remove stopped old agent backup failed name=%s", getattr(container, "name", ""), exc_info=True)
        return removed

    def prepare_agent_decommission(self) -> dict[str, Any]:
        running_ids = sorted(self.running_platform_run_ids())
        if running_ids:
            raise RuntimeError(f"仍有平台任务容器运行，拒绝退役 Agent：{running_ids}")
        container_ref = str(os.getenv("HOSTNAME") or "").strip()
        if not container_ref:
            raise RuntimeError("无法识别当前 Agent 容器，拒绝自动退役")
        container = self.client.containers.get(container_ref)
        container.update(restart_policy={"Name": "no"})
        return {"containerId": container.id, "containerName": getattr(container, "name", "") or "", "restartPolicy": "no", "dataPreserved": True}

    def remove_host_agent_credentials(self) -> None:
        config_dir = str(os.getenv("AGENT_HOST_CONFIG_DIR") or "").strip()
        if not config_dir:
            return
        env_file = Path(config_dir) / ".env"
        try:
            env_file.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("remove host agent credentials failed path=%s error=%s", env_file, exc)

    def remove_current_agent_container(self, container_id: str) -> None:
        target = str(container_id or "").strip()
        if not target:
            return
        # 平台已收到退役成功回报后再删除自身容器。Docker daemon 通过挂载的
        # docker.sock 执行删除；业务数据目录不删除，避免误伤项目缓存/运行数据。
        self.client.api.remove_container(target, force=True, v=False)

    def cleanup_platform_containers(self, cleanup: dict[str, Any]) -> dict[str, Any]:
        scope = str(cleanup.get("cleanupScope") or "PROJECT").upper()
        project_id = str(cleanup.get("projectId") or "").strip()
        task_id = str(cleanup.get("taskId") or "").strip()
        filters = {"label": [f"crawler.platform.project_id={project_id}"]}
        if scope == "TASK" and task_id:
            filters["label"].append(f"crawler.platform.task_id={task_id}")
        stopped = 0
        removed = 0
        failed = 0
        messages: list[str] = []
        try:
            containers = self.client.containers.list(all=True, filters=filters)
        except Exception as exc:
            return {"success": False, "stoppedCount": 0, "removedCount": 0, "failedCount": 1, "message": f"查询容器失败：{exc}"}
        for container in containers:
            name = getattr(container, "name", "") or ""
            try:
                container.reload()
                if container.status not in {"exited", "dead", "created"}:
                    container.stop(timeout=10)
                    stopped += 1
                container.remove(force=True)
                removed += 1
            except Exception as exc:
                failed += 1
                messages.append(f"{name or container.id[:12]}: {exc}")
        message = f"清理完成：scope={scope} projectId={project_id} taskId={task_id or '-'} stopped={stopped} removed={removed} failed={failed}"
        if messages:
            message += "；" + "；".join(messages)
        logger.info("container cleanup result cleanup_id=%s %s", cleanup.get("cleanupId"), message)
        return {"success": failed == 0, "stoppedCount": stopped, "removedCount": removed, "failedCount": failed, "message": message[:4000]}

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

    def _upload_text_logs(self, run_id: int, lease_token: str, text: str, stream: str = "stdout", start_seq: int = 1) -> int:
        if not text:
            return start_seq - 1
        chunk_bytes = 32 * 1024
        encoded = text.encode("utf-8", errors="replace")
        offset = 0
        seq = start_seq
        while offset < len(encoded):
            part = encoded[offset:offset + chunk_bytes].decode("utf-8", errors="replace")
            self.api.log_chunk(run_id, lease_token, stream, seq, offset, part)
            offset += len(part.encode("utf-8", errors="replace"))
            seq += 1
        return seq - 1

    def _container_logs_text(self, container: Any, tail: int | None = None) -> str:
        data = container.logs(stdout=True, stderr=True, tail=tail) if tail is not None else container.logs(stdout=True, stderr=True)
        return data.decode("utf-8", errors="replace")

    def _diagnosis_from_logs(self, status: str, logs: str, stage: str = "FINISH") -> dict[str, Any]:
        lower = logs.lower()
        error_type = ""
        if status == "TIMED_OUT":
            error_type = "NETWORK_TIMEOUT"
        elif "captcha" in lower or "验证码" in logs:
            error_type = "CAPTCHA_BLOCKED"
        elif "403" in lower:
            error_type = "HTTP_403"
        elif "429" in lower:
            error_type = "HTTP_429"
        elif "timeout" in lower or "timed out" in lower or "超时" in logs:
            error_type = "NETWORK_TIMEOUT"
        elif "traceback" in lower or "exception" in lower:
            error_type = "UNKNOWN_ERROR"
        summary = (logs[-1000:] if logs else status)
        return {
            "failedStage": stage if status not in {"SUCCEEDED", "PARTIAL_SUCCESS"} else "",
            "errorType": error_type,
            "errorSummary": summary if status not in {"SUCCEEDED", "PARTIAL_SUCCESS"} else "",
            "retryable": status in {"TIMED_OUT"} or error_type in {"NETWORK_TIMEOUT", "HTTP_429"},
            "diagnosis": {"summary": summary, "suggestion": "查看错误附近日志，确认目标站点、账号、网络和数据库状态。"},
        }


    def _container_snapshot_payload(self, container, image_digest: str, status: str, exit_code: int | None = None, last_log_line: str = "") -> dict[str, Any]:
        cpu_usage = None
        memory_usage_mb = None
        oom_killed = None
        restart_count = 0
        started_at = None
        finished_at = None
        container_id = ""
        container_name = ""
        try:
            container.reload()
            attrs = container.attrs or {}
            state = attrs.get("State") or {}
            container_id = (container.id or "")[:64]
            container_name = getattr(container, "name", "") or ""
            oom_killed = state.get("OOMKilled")
            restart_count = int(attrs.get("RestartCount") or 0)
            started_at = state.get("StartedAt") or None
            finished_at = state.get("FinishedAt") or None
            try:
                stats = container.stats(stream=False)
                memory_usage_mb = round(float((stats.get("memory_stats") or {}).get("usage") or 0) / 1024 / 1024, 2)
            except Exception:
                pass
        except Exception:
            pass
        payload: dict[str, Any] = {
            "containerId": container_id,
            "containerName": container_name,
            "imageDigest": image_digest,
            "containerStatus": status,
            "exitCode": exit_code,
            "oomKilled": oom_killed,
            "restartCount": restart_count,
            "cpuUsage": cpu_usage,
            "memoryUsageMb": memory_usage_mb,
            "startedAt": started_at if started_at and not str(started_at).startswith("0001-") else None,
            "finishedAt": finished_at if finished_at and not str(finished_at).startswith("0001-") else None,
            "lastLogLine": last_log_line[-1000:],
            "payload": {"dockerStatus": getattr(container, "status", "") or ""},
        }
        return payload

    def _report_container_snapshot(self, run_id: int, lease_token: str, container, image_digest: str, status: str, exit_code: int | None = None, last_log_line: str = "") -> None:
        if not container:
            return
        try:
            self.api.container_snapshot(run_id, lease_token, **self._container_snapshot_payload(container, image_digest, status, exit_code, last_log_line))
        except Exception as exc:
            logger.warning("run_id=%s report container snapshot failed: %s", run_id, exc, exc_info=True)


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
            self.api.run_event(run_id, lease_token, "IMAGE_PULL_START", "DOCKER", "开始拉取并校验任务镜像")
            image_ref = self._pull_digest(str(claim.get("imageRepository") or ""), str(claim.get("imageDigest") or ""))
            self._report_image_pull(claim, "READY", f"运行前镜像拉取和 digest 校验完成：{image_ref}")
            logger.info("run_id=%s pull ok image_ref=%s", run_id, image_ref)
            self.api.run_event(run_id, lease_token, "IMAGE_PULL_OK", "DOCKER", "镜像拉取和 digest 校验完成", payload={"imageRef": image_ref})
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
                "CRAWLER_COMPANY_ID": str(claim.get("companyId") or ""),
                "CRAWLER_PROJECT_ID": str(claim.get("projectId") or ""),
                "CRAWLER_PROJECT_CODE": str(claim.get("projectCode") or ""),
                "CRAWLER_TASK_ID": str(claim.get("taskId") or ""),
                "CRAWLER_TASK_CODE": str(claim.get("taskCode") or ""),
                "CRAWLER_TASK_GROUP": str(claim.get("taskGroup") or "default"),
                "CRAWLER_RELEASE_ID": str(claim.get("releaseId") or ""),
                "CRAWLER_RELEASE_VERSION": str(claim.get("releaseVersion") or ""),
                "CRAWLER_IMAGE_REPOSITORY": str(claim.get("imageRepository") or ""),
                "CRAWLER_IMAGE_DIGEST": str(claim.get("imageDigest") or ""),
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
            self.api.run_event(run_id, lease_token, "CONTAINER_CREATE_START", "DOCKER", "开始创建任务容器", payload={"containerName": container_name})
            container = self.client.containers.run(**run_kwargs)
            logger.info("run_id=%s container created id=%s", run_id, container.id[:12])
            self.api.run_event(run_id, lease_token, "CONTAINER_CREATED", "DOCKER", "任务容器已创建并启动", payload={"containerId": container.id[:12], "containerName": container_name})
            self._report_container_snapshot(run_id, lease_token, container, str(claim.get("imageDigest") or ""), "RUNNING")
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
                    logs = self._container_logs_text(container)
                    self._upload_text_logs(run_id, lease_token, logs, "stdout", 1)
                    diagnosis = self._diagnosis_from_logs("TIMED_OUT", logs, "DOCKER")
                    self.api.finalize_logs(run_id, lease_token, "TRUNCATED" if len(logs.encode("utf-8", errors="replace")) > log_limit_mb * 1024 * 1024 else "COMPLETE", logPath=str(dirs.get("logs", "")), logTruncated=False, **diagnosis)
                    self.api.run_event(run_id, lease_token, "RUN_TIMED_OUT", "DOCKER", "任务运行超时", "ERROR", {"timeoutSeconds": timeout_seconds})
                    self._report_container_snapshot(run_id, lease_token, container, str(claim.get("imageDigest") or ""), "TIMED_OUT", None, logs[-1000:])
                    self.api.finish(run_id, lease_token, "TIMED_OUT", {"tailLogs": logs[-4000:], "workDir": str(dirs.get("work", "")), "logDir": str(dirs.get("logs", ""))}, "任务运行超时")
                    return
                time.sleep(2)
            result = container.wait()
            exit_code = int((result or {}).get("StatusCode", 1))
            logger.info("run_id=%s container exited status_code=%s", run_id, exit_code)
            logs = self._container_logs_text(container)
            status = "SUCCEEDED" if exit_code == 0 else "FAILED"
            self._upload_text_logs(run_id, lease_token, logs, "stdout", 1)
            diagnosis = self._diagnosis_from_logs(status, logs, "FINISH")
            self._report_container_snapshot(run_id, lease_token, container, str(claim.get("imageDigest") or ""), "EXITED" if exit_code == 0 else "FAILED", exit_code, logs[-1000:])
            self.api.finalize_logs(run_id, lease_token, "COMPLETE", logPath=str(dirs.get("logs", "")), logTruncated=False, **diagnosis)
            self.api.run_event(run_id, lease_token, "RUN_SUCCEEDED" if exit_code == 0 else "RUN_FAILED", "FINISH", "任务执行成功" if exit_code == 0 else "任务执行失败", "INFO" if exit_code == 0 else "ERROR", {"exitCode": exit_code})
            self.api.finish(run_id, lease_token, status, {"exitCode": exit_code, "tailLogs": logs[-4000:], "workDir": str(dirs.get("work", "")), "logDir": str(dirs.get("logs", ""))}, "" if exit_code == 0 else logs[-4000:])
        except Exception as exc:
            logger.exception("run_id=%s execute failed: %s", run_id, exc)
            try:
                message = str(exc)
                if container is None:
                    self._report_image_pull(claim, "FAILED", message)
                diagnosis = self._diagnosis_from_logs("FAILED", message, "AGENT")
                self.api.run_event(run_id, lease_token, "AGENT_EXECUTE_FAILED", "AGENT", message, "ERROR", {"errorType": diagnosis.get("errorType") or "UNKNOWN_ERROR", "retryable": True})
                self.api.log_chunk(run_id, lease_token, "stderr", 1, 0, message)
                self.api.finalize_logs(run_id, lease_token, "FAILED", logPath=str(dirs.get("logs", "")), logTruncated=False, **diagnosis)
                self.api.finish(run_id, lease_token, "FAILED", {"workDir": str(dirs.get("work", "")), "logDir": str(dirs.get("logs", ""))}, message)
            except Exception:
                logger.exception("run_id=%s finish callback failed after execute exception", run_id)
        finally:
            stop_event.set()
            if container:
                try:
                    self._report_container_snapshot(run_id, lease_token, container, str(claim.get("imageDigest") or ""), "CLEANED")
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            # 保留 logs/cache/profiles，清理 run 临时目录。work 目录默认保留便于排错。
            tmp = dirs.get("tmp") if dirs else None
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
