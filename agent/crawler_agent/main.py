from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import docker
import psutil

from crawler_agent.api import PlatformAPI
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
            "protocolVersion": config.protocol_version,
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
            "capabilities": config.capabilities(),
            "currentRuns": {"runIds": sorted(tracked_run_ids), "dockerRunIds": sorted(docker_run_ids), "orphanRunIds": orphan_run_ids},
            "lastError": self.last_error,
        }

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
                    self.handle_container_cleanups(heartbeat_response or {})
                    self.handle_image_updates(heartbeat_response or {})
                    last_heartbeat = now
                if self.active_count() < config.max_slots:
                    claim = self.api.claim()
                    if claim:
                        run_id = int(claim["runId"])
                        with self.lock:
                            if run_id not in self.futures:
                                logger.info("claim received run_id=%s project=%s task=%s", run_id, claim.get("projectCode"), claim.get("taskCode"))
                                self.futures[run_id] = self.pool.submit(self.executor.execute, claim)
            except Exception as exc:
                self.last_error = f"Agent 主循环异常：{exc}"[:4000]
                logger.exception("agent loop failed")
                time.sleep(max(5, config.poll_interval_seconds))
            time.sleep(config.poll_interval_seconds)



def main() -> None:
    AgentApp().loop()


if __name__ == "__main__":
    main()
