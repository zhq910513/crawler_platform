from __future__ import annotations

import logging
import os
import socket
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import docker
import psutil

from crawler_agent.api import PlatformAPI, PlatformUnavailable, UnauthorizedError
from crawler_agent.config import config
from crawler_agent.docker_runner import RunExecutor

LOG_LEVEL = os.getenv("AGENT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("crawler_agent.main")


def disk_inode_usage(path: str) -> float:
    try:
        stat = os.statvfs(path)
        total = stat.f_files or 0
        free = stat.f_ffree or 0
        return round((total - free) * 100 / total, 2) if total else 0.0
    except Exception:
        return 0.0


def path_writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, f".write-test-{os.getpid()}")
        with open(probe, "w", encoding="utf-8") as fp:
            fp.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


class AgentApp:
    def __init__(self) -> None:
        config.validate_runtime()
        self.api = PlatformAPI(config)
        self.last_error = ""
        self.executor = RunExecutor(config, self.api)
        self.pool = ThreadPoolExecutor(max_workers=config.max_slots)
        self.futures: dict[int, Any] = {}
        self.lock = threading.Lock()
        self.docker_client = docker.from_env()
        self.image_prewarm_next_at: dict[str, float] = {}
        self.shutdown_requested = False
        self.next_agent_backup_cleanup_at = 0.0

    def active_count(self) -> int:
        with self.lock:
            done = [run_id for run_id, future in self.futures.items() if future.done()]
            for run_id in done:
                future = self.futures.pop(run_id, None)
                if not future:
                    continue
                exc = future.exception()
                if exc:
                    self.last_error = f"run_id={run_id} worker future failed: {exc}"[:4000]
                    logger.error("run_id=%s worker future failed", run_id, exc_info=(type(exc), exc, exc.__traceback__))
                else:
                    logger.info("run_id=%s worker future completed", run_id)
            return len(self.futures)


    def current_agent_image_actual_digest(self) -> str:
        if not config.image:
            return ""
        try:
            image = self.docker_client.images.get(config.image)
            repo_digests = image.attrs.get("RepoDigests") or []
            for item in repo_digests:
                if "@sha256:" in str(item):
                    return str(item).split("@", 1)[1]
        except Exception:
            return ""
        return ""

    def heartbeat_payload(self) -> dict[str, Any]:
        running = self.active_count()
        docker_run_ids = self.executor.running_platform_run_ids()
        tracked_run_ids = set(self.futures.keys()) | docker_run_ids
        orphan_run_ids = sorted(docker_run_ids - set(self.futures.keys()))
        docker_running_count = max(running, len(docker_run_ids))
        disk = psutil.disk_usage(str(config.run_root.parent if config.run_root.is_absolute() else "/"))
        docker_status = "OK"
        try:
            self.docker_client.ping()
        except Exception as exc:
            docker_status = f"ERROR:{exc}"
        available_slots = max(0, config.max_slots - docker_running_count)
        health_status = "HEALTHY" if docker_status == "OK" else "UNHEALTHY"
        capacity_status = "FULL" if available_slots <= 0 else ("BUSY" if available_slots <= max(1, config.max_slots // 4) else "NORMAL")
        return {
            "agentInstanceId": config.instance_id,
            "agentVersion": config.agent_version,
            "agentImage": config.image,
            "agentImageDigest": config.expected_image_digest,
            "agentImageActualDigest": self.current_agent_image_actual_digest(),
            "protocolVersion": config.protocol_version,
            "hostname": config.hostname or socket.gethostname(),
            "hostIp": config.host_ip,
            "publicIp": config.public_ip,
            "healthStatus": health_status,
            "capacityStatus": capacity_status,
            "dockerStatus": docker_status,
            "cpuUsage": psutil.cpu_percent(interval=None),
            "memoryUsage": psutil.virtual_memory().percent,
            "diskUsage": disk.percent,
            "inodeUsage": disk_inode_usage(str(config.project_data_root)),
            "loadAverage": os.getloadavg()[0] if hasattr(os, "getloadavg") else 0,
            "runningContainers": docker_running_count,
            "availableSlots": available_slots,
            "maxSlots": config.max_slots,
            "projectDataRootWritable": path_writable(str(config.project_data_root)),
            "dockerSockAccessible": docker_status == "OK",
            "timezone": datetime.now().astimezone().tzname() or "",
            "capabilities": {**config.capabilities(), "agentDecommission": True, "agentUpgrade": True, "desiredState": True},
            "currentRuns": {"runIds": sorted(tracked_run_ids), "dockerRunIds": sorted(docker_run_ids), "orphanRunIds": orphan_run_ids},
            "lastError": self.last_error,
        }


    def handle_agent_commands(self, heartbeat_response: dict[str, Any]) -> None:
        commands = heartbeat_response.get("pendingAgentCommands") or []
        if not isinstance(commands, list) or not commands:
            return
        for command in commands[:10]:
            if not isinstance(command, dict):
                continue
            command_id = command.get("commandId")
            command_type = str(command.get("commandType") or "").upper()
            try:
                if command_type == "PROJECT_DEPLOY_PREPARE":
                    result = self.executor.prepare_project_runtime(command)
                    self.api.agent_command_result(command, True, "项目镜像、目录和运行时自检已完成", result)
                elif command_type == "AGENT_UPGRADE":
                    if self.active_count() > 0:
                        raise RuntimeError("仍有 Agent 进程内任务运行，拒绝升级")
                    result = self.executor.prepare_agent_upgrade(command)
                    self.api.agent_command_result(command, True, "新版 Agent 容器已启动，当前 Agent 准备退出", result)
                    self.shutdown_requested = True
                    return
                elif command_type == "AGENT_DECOMMISSION":
                    if self.active_count() > 0:
                        raise RuntimeError("仍有 Agent 进程内任务运行，拒绝退役")
                    result = self.executor.prepare_agent_decommission()
                    self.api.agent_command_result(command, True, "Agent 已停止接收新任务，准备移除自身容器", result)
                    self.shutdown_requested = True
                    try:
                        self.executor.remove_host_agent_credentials()
                        self.executor.remove_current_agent_container(str(result.get("containerId") or ""))
                    finally:
                        return
                else:
                    self.api.agent_command_result(command, False, f"不支持的 Agent 指令类型：{command_type}", {})
            except Exception as exc:
                self.last_error = f"Agent 指令执行失败 command_id={command_id}: {exc}"[:4000]
                logger.warning("agent command failed command_id=%s type=%s error=%s", command_id, command_type, exc, exc_info=True)
                try:
                    self.api.agent_command_result(command, False, str(exc), {})
                except Exception as report_exc:
                    self.last_error = f"Agent 指令结果回报失败 command_id={command_id}: {report_exc}"[:4000]
                    logger.warning("agent command result report failed command_id=%s error=%s", command_id, report_exc, exc_info=True)

    def handle_image_updates(self, heartbeat_response: dict[str, Any]) -> None:
        updates = heartbeat_response.get("pendingImagePulls") or []
        if not isinstance(updates, list) or not updates:
            return
        if self.active_count() > 0:
            logger.info("skip image prewarm because runs are active updates=%s", len(updates))
            return
        now = time.monotonic()
        for item in updates[:3]:
            if not isinstance(item, dict):
                continue
            if not item.get("safeToPrewarm"):
                continue
            key = f"{item.get('projectId')}:{item.get('releaseId')}:{item.get('imageDigest')}"
            next_at = self.image_prewarm_next_at.get(key, 0)
            if now < next_at:
                continue
            ok = self.executor.prewarm_image(item)
            self.image_prewarm_next_at[key] = now + (60 if ok else 300)


    def handle_container_cleanups(self, heartbeat_response: dict[str, Any]) -> None:
        cleanups = heartbeat_response.get("pendingContainerCleanups") or []
        if not isinstance(cleanups, list) or not cleanups:
            return
        for cleanup in cleanups[:20]:
            if not isinstance(cleanup, dict):
                continue
            result = self.executor.cleanup_platform_containers(cleanup)
            try:
                self.api.container_cleanup_result(cleanup, result)
            except Exception as exc:
                self.last_error = f"容器清理结果回报失败：{exc}"[:4000]
                logger.warning("container cleanup result report failed cleanup_id=%s error=%s", cleanup.get("cleanupId"), exc, exc_info=True)


    def loop(self) -> None:
        last_heartbeat = 0.0
        logger.info("agent loop started instance_id=%s server_code=%s agent_code=%s version=%s", config.instance_id, config.server_code, config.agent_code, config.agent_version)
        while True:
            try:
                now = time.monotonic()
                if now - last_heartbeat >= config.heartbeat_interval_seconds:
                    heartbeat_response = self.api.heartbeat(self.heartbeat_payload())
                    self.handle_agent_commands(heartbeat_response or {})
                    if self.shutdown_requested:
                        return
                    self.handle_container_cleanups(heartbeat_response or {})
                    self.handle_image_updates(heartbeat_response or {})
                    if now >= self.next_agent_backup_cleanup_at:
                        removed = self.executor.cleanup_stopped_agent_backups()
                        if removed:
                            logger.info("removed stopped old agent backup containers count=%s", removed)
                        self.next_agent_backup_cleanup_at = now + 60
                    last_heartbeat = now
                if self.active_count() < config.max_slots:
                    claim = self.api.claim()
                    if claim:
                        run_id = int(claim["runId"])
                        with self.lock:
                            if run_id not in self.futures:
                                logger.info("claim received run_id=%s project=%s task=%s", run_id, claim.get("projectCode"), claim.get("taskCode"))
                                self.futures[run_id] = self.pool.submit(self.executor.execute, claim)
            except PlatformUnavailable as exc:
                # 控制端临时不可达时，本次失败不会被控制端接收；下一次成功心跳应代表链路已恢复。
                # 不把 HTTPConnectionPool/Connection refused 这类瞬时网络错误写入 lastError，
                # 避免节点已在线后控制台仍展示过期的“Agent 主循环异常”。
                logger.warning("control plane temporarily unavailable: %s", exc)
                time.sleep(max(5, config.poll_interval_seconds))
            except UnauthorizedError as exc:
                self.last_error = f"Agent 鉴权失败：{exc}"[:4000]
                logger.exception("agent authorization failed")
                time.sleep(max(5, config.poll_interval_seconds))
            except Exception as exc:
                self.last_error = f"Agent 主循环异常：{exc}"[:4000]
                logger.exception("agent loop failed")
                time.sleep(max(5, config.poll_interval_seconds))
            time.sleep(config.poll_interval_seconds)



def main() -> None:
    AgentApp().loop()


if __name__ == "__main__":
    main()
