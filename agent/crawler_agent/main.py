from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import docker
import psutil

from crawler_agent.api import PlatformAPI
from crawler_agent.config import config
from crawler_agent.docker_runner import RunExecutor


class AgentApp:
    def __init__(self) -> None:
        config.validate_runtime()
        self.api = PlatformAPI(config)
        self.executor = RunExecutor(config, self.api)
        self.pool = ThreadPoolExecutor(max_workers=config.max_slots)
        self.futures: dict[int, Any] = {}
        self.lock = threading.Lock()
        self.docker_client = docker.from_env()

    def active_count(self) -> int:
        with self.lock:
            done = [run_id for run_id, future in self.futures.items() if future.done()]
            for run_id in done:
                self.futures.pop(run_id, None)
            return len(self.futures)

    def heartbeat_payload(self) -> dict[str, Any]:
        running = self.active_count()
        disk = psutil.disk_usage(str(config.run_root.parent if config.run_root.is_absolute() else "/"))
        docker_status = "OK"
        try:
            self.docker_client.ping()
        except Exception as exc:
            docker_status = f"ERROR:{exc}"
        return {
            "agentInstanceId": config.instance_id,
            "agentVersion": config.agent_version,
            "protocolVersion": config.protocol_version,
            "dockerStatus": docker_status,
            "cpuUsage": psutil.cpu_percent(interval=None),
            "memoryUsage": psutil.virtual_memory().percent,
            "diskUsage": disk.percent,
            "loadAverage": os.getloadavg()[0] if hasattr(os, "getloadavg") else 0,
            "runningContainers": running,
            "availableSlots": max(0, config.max_slots - running),
            "capabilities": config.capabilities(),
            "currentRuns": {"runIds": list(self.futures.keys())},
            "lastError": "",
        }

    def loop(self) -> None:
        last_heartbeat = 0.0
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= config.heartbeat_interval_seconds:
                self.api.heartbeat(self.heartbeat_payload())
                last_heartbeat = now
            if self.active_count() < config.max_slots:
                claim = self.api.claim()
                if claim:
                    run_id = int(claim["runId"])
                    with self.lock:
                        if run_id not in self.futures:
                            self.futures[run_id] = self.pool.submit(self.executor.execute, claim)
            time.sleep(config.poll_interval_seconds)


def main() -> None:
    AgentApp().loop()


if __name__ == "__main__":
    main()
