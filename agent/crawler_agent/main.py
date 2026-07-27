from __future__ import annotations

import os
import platform
import socket
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import docker
import psutil

from crawler_agent import __version__
from crawler_agent.api import PlatformAPI
from crawler_agent.config import config
from crawler_agent.docker_runner import DockerTaskRunner


class AgentApplication:
    def __init__(self) -> None:
        self.api = PlatformAPI(config)
        self.docker = docker.from_env(timeout=120)
        self.executor = ThreadPoolExecutor(max_workers=config.max_slots, thread_name_prefix="crawler-run")
        self.running: dict[int, Future] = {}
        self.last_heartbeat = 0.0
        if config.docker_registry_username and config.docker_registry_password:
            self.docker.login(
                username=config.docker_registry_username,
                password=config.docker_registry_password,
                registry=config.docker_registry or None,
            )

    def registration_payload(self) -> dict[str, Any]:
        docker_version = self.docker.version().get("Version", "")
        return {
            "server_code": config.server_code,
            "server_name": config.server_name,
            "server_ip": config.server_ip,
            "environment": config.environment,
            "max_container_slots": config.max_slots,
            "agent_code": f"agent-{config.server_code}",
            "agent_version": __version__,
            "hostname": socket.gethostname(),
            "os_name": platform.platform(),
            "python_version": sys.version.split()[0],
            "docker_version": docker_version,
            "cpu_count": psutil.cpu_count() or 0,
            "memory_total_bytes": psutil.virtual_memory().total,
        }

    def ensure_registered(self, force: bool = False) -> None:
        if force or not self.api.agent_token:
            self.api.register(self.registration_payload())
            print(f"Agent 注册成功 server_id={self.api.server_id} agent_id={self.api.agent_id}")

    def metric_payload(self, last_error: str = "") -> dict[str, Any]:
        net = psutil.net_io_counters()
        try:
            load_1m, load_5m, _ = os.getloadavg()
        except (AttributeError, OSError):
            load_1m = load_5m = 0.0
        try:
            df = self.docker.df()
            image_bytes = sum(int(item.get("Size", 0) or 0) for item in df.get("Images", []))
            docker_version = self.docker.version().get("Version", "")
        except Exception:
            image_bytes = 0
            docker_version = ""
        return {
            "server_ip": config.server_ip,
            "agent_version": __version__,
            "hostname": socket.gethostname(),
            "os_name": platform.platform(),
            "python_version": sys.version.split()[0],
            "docker_version": docker_version,
            "cpu_count": psutil.cpu_count() or 0,
            "memory_total_bytes": psutil.virtual_memory().total,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(config.disk_path).percent,
            "load_1m": load_1m,
            "load_5m": load_5m,
            "network_sent_bytes": net.bytes_sent,
            "network_received_bytes": net.bytes_recv,
            "running_task_count": len(self.running),
            "process_count": len(psutil.pids()),
            "docker_image_bytes": image_bytes,
            "last_error": last_error,
        }

    def clean_finished(self) -> None:
        finished = [run_id for run_id, future in self.running.items() if future.done()]
        for run_id in finished:
            future = self.running.pop(run_id)
            try:
                future.result()
            except Exception as exc:
                print(f"任务线程异常 run={run_id}: {exc}")

    def submit_claimed(self, items: list[dict[str, Any]]) -> None:
        for payload in items:
            run_id = int(payload["run_id"])
            if run_id in self.running:
                continue
            runner = DockerTaskRunner(self.docker, self.api)
            self.running[run_id] = self.executor.submit(runner.run, payload)
            print(f"已领取任务 run={run_id} task={payload['task_name']}")

    def run_forever(self) -> None:
        self.ensure_registered()
        print(f"Crawler Agent started server={config.server_code} slots={config.max_slots}")
        while True:
            last_error = ""
            try:
                self.clean_finished()
                now = time.monotonic()
                if now - self.last_heartbeat >= config.heartbeat_seconds:
                    self.api.heartbeat(self.metric_payload())
                    self.last_heartbeat = now
                available = max(0, config.max_slots - len(self.running))
                if available:
                    self.submit_claimed(self.api.claim(available))
            except PermissionError:
                self.ensure_registered(force=True)
            except Exception as exc:
                last_error = str(exc)
                print(f"Agent 主循环异常：{exc}")
                try:
                    if time.monotonic() - self.last_heartbeat >= config.heartbeat_seconds:
                        self.api.heartbeat(self.metric_payload(last_error=last_error))
                except Exception:
                    pass
                time.sleep(min(config.poll_seconds * 2, 10))
            time.sleep(config.poll_seconds)


if __name__ == "__main__":
    AgentApplication().run_forever()
